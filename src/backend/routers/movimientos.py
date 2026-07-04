# routers/movimientos.py
# Endpoints de movimientos
#
# GET    /movimientos              → lista con filtros
# POST   /movimientos              → registra ingreso o gasto
# GET    /movimientos/{id}         → detalle
# PUT    /movimientos/{id}         → edita (solo el propietario)
# DELETE /movimientos/{id}         → elimina (solo el propietario)
# POST   /movimientos/importar     → importa desde CSV o Excel

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from typing import Annotated
from datetime import date
import sqlite3
import csv
import io

from database import get_db
from routers.auth import current_user

router = APIRouter(prefix="/movimientos", tags=["movimientos"])


# ------------------------------------------------------------
# Schemas
# ------------------------------------------------------------

class MovimientoCreate(BaseModel):
    cuenta_id: int
    categoria_id: int
    importe: float
    tipo: str        # 'ingreso' | 'gasto'
    descripcion: str | None = None
    fecha: date


class MovimientoUpdate(BaseModel):
    categoria_id: int | None = None
    importe: float | None = None
    tipo: str | None = None
    descripcion: str | None = None
    fecha: date | None = None


class MovimientoResponse(BaseModel):
    id: int
    cuenta_id: int
    categoria_id: int
    usuario_id: int
    importe: float
    tipo: str
    descripcion: str | None
    fecha: str
    creado_en: str
    # Campos extra para mostrar en el frontend
    categoria_nombre: str | None = None
    cuenta_nombre: str | None = None
    usuario_nombre: str | None = None


# ------------------------------------------------------------
# Utilidad: obtener movimiento con datos enriquecidos
# ------------------------------------------------------------

def get_movimiento_detalle(conn: sqlite3.Connection, movimiento_id: int):
    return conn.execute(
        """SELECT m.*,
                  c.nombre AS categoria_nombre,
                  cu.nombre AS cuenta_nombre,
                  u.nombre  AS usuario_nombre
           FROM movimientos m
           LEFT JOIN categorias c  ON m.categoria_id = c.id
           LEFT JOIN cuentas    cu ON m.cuenta_id    = cu.id
           LEFT JOIN usuarios   u  ON m.usuario_id   = u.id
           WHERE m.id = ?""",
        (movimiento_id,)
    ).fetchone()


# ------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------

@router.get("", response_model=list[MovimientoResponse])
async def listar_movimientos(
    _: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
    cuenta_id: int | None = None,
    categoria_id: int | None = None,
    tipo: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    limite: int = 100,
    offset: int = 0,
):
    """
    Lista movimientos con filtros opcionales:
    - cuenta_id: filtra por cuenta
    - categoria_id: filtra por categoría
    - tipo: 'ingreso' | 'gasto'
    - fecha_desde / fecha_hasta: rango de fechas
    - limite / offset: paginación
    """
    query = """
        SELECT m.*,
               c.nombre  AS categoria_nombre,
               cu.nombre AS cuenta_nombre,
               u.nombre  AS usuario_nombre
        FROM movimientos m
        LEFT JOIN categorias c  ON m.categoria_id = c.id
        LEFT JOIN cuentas    cu ON m.cuenta_id    = cu.id
        LEFT JOIN usuarios   u  ON m.usuario_id   = u.id
        WHERE 1=1
    """
    params = []

    if cuenta_id is not None:
        query += " AND m.cuenta_id = ?"
        params.append(cuenta_id)

    if categoria_id is not None:
        query += " AND m.categoria_id = ?"
        params.append(categoria_id)

    if tipo is not None:
        if tipo not in ("ingreso", "gasto"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El tipo debe ser 'ingreso' o 'gasto'",
            )
        query += " AND m.tipo = ?"
        params.append(tipo)

    if fecha_desde is not None:
        query += " AND m.fecha >= ?"
        params.append(str(fecha_desde))

    if fecha_hasta is not None:
        query += " AND m.fecha <= ?"
        params.append(str(fecha_hasta))

    query += " ORDER BY m.fecha DESC, m.creado_en DESC LIMIT ? OFFSET ?"
    params.extend([limite, offset])

    movimientos = conn.execute(query, params).fetchall()
    return [dict(m) for m in movimientos]


@router.post("", response_model=MovimientoResponse, status_code=status.HTTP_201_CREATED)
async def crear_movimiento(
    datos: MovimientoCreate,
    user: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
):
    """Registra un nuevo ingreso o gasto."""
    if datos.tipo not in ("ingreso", "gasto"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El tipo debe ser 'ingreso' o 'gasto'",
        )

    if datos.importe <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El importe debe ser mayor que 0",
        )

    # Verificar que la cuenta existe
    cuenta = conn.execute(
        "SELECT id FROM cuentas WHERE id = ?", (datos.cuenta_id,)
    ).fetchone()
    if cuenta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuenta no encontrada",
        )

    # Verificar que la categoría existe y es accesible por el usuario
    categoria = conn.execute(
        """SELECT id FROM categorias
           WHERE id = ? AND (usuario_id IS NULL OR usuario_id = ?)""",
        (datos.categoria_id, user["id"]),
    ).fetchone()
    if categoria is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría no encontrada",
        )

    cursor = conn.execute(
        """INSERT INTO movimientos
           (cuenta_id, categoria_id, usuario_id, importe, tipo, descripcion, fecha)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            datos.cuenta_id,
            datos.categoria_id,
            user["id"],
            datos.importe,
            datos.tipo,
            datos.descripcion,
            str(datos.fecha),
        ),
    )
    conn.commit()

    nuevo = get_movimiento_detalle(conn, cursor.lastrowid)
    return dict(nuevo)


@router.get("/{movimiento_id}", response_model=MovimientoResponse)
async def detalle_movimiento(
    movimiento_id: int,
    _: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
):
    """Detalle de un movimiento."""
    movimiento = get_movimiento_detalle(conn, movimiento_id)
    if movimiento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movimiento no encontrado",
        )
    return dict(movimiento)


@router.put("/{movimiento_id}", response_model=MovimientoResponse)
async def editar_movimiento(
    movimiento_id: int,
    datos: MovimientoUpdate,
    user: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
):
    """Edita un movimiento. Solo el propietario puede editarlo."""
    movimiento = conn.execute(
        "SELECT * FROM movimientos WHERE id = ?", (movimiento_id,)
    ).fetchone()

    if movimiento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movimiento no encontrado",
        )

    if movimiento["usuario_id"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para editar este movimiento",
        )

    if datos.tipo is not None and datos.tipo not in ("ingreso", "gasto"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El tipo debe ser 'ingreso' o 'gasto'",
        )

    if datos.importe is not None and datos.importe <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El importe debe ser mayor que 0",
        )

    # Construir la query de actualización solo con los campos enviados
    campos = {}
    if datos.categoria_id is not None:
        campos["categoria_id"] = datos.categoria_id
    if datos.importe is not None:
        campos["importe"] = datos.importe
    if datos.tipo is not None:
        campos["tipo"] = datos.tipo
    if datos.descripcion is not None:
        campos["descripcion"] = datos.descripcion
    if datos.fecha is not None:
        campos["fecha"] = str(datos.fecha)

    if campos:
        set_clause = ", ".join(f"{k} = ?" for k in campos)
        valores = list(campos.values()) + [movimiento_id]
        conn.execute(
            f"UPDATE movimientos SET {set_clause} WHERE id = ?", valores
        )
        conn.commit()

    actualizado = get_movimiento_detalle(conn, movimiento_id)
    return dict(actualizado)


@router.delete("/{movimiento_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_movimiento(
    movimiento_id: int,
    user: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
):
    """Elimina un movimiento. Solo el propietario puede eliminarlo."""
    movimiento = conn.execute(
        "SELECT * FROM movimientos WHERE id = ?", (movimiento_id,)
    ).fetchone()

    if movimiento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movimiento no encontrado",
        )

    if movimiento["usuario_id"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para eliminar este movimiento",
        )

    conn.execute("DELETE FROM movimientos WHERE id = ?", (movimiento_id,))
    conn.commit()


@router.post("/importar", status_code=status.HTTP_201_CREATED)
async def importar_movimientos(
    user: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
    file: UploadFile = File(...),
    cuenta_id: int = 1,
):
    """
    Importa movimientos desde un fichero CSV.

    Formato esperado del CSV (con cabecera):
        fecha,tipo,importe,categoria,descripcion
        2024-01-15,gasto,45.50,Alimentación,Supermercado
        2024-01-16,ingreso,1500.00,Nómina,Nómina enero

    - fecha: formato YYYY-MM-DD
    - tipo: 'ingreso' o 'gasto'
    - importe: número positivo (punto como separador decimal)
    - categoria: nombre exacto de una categoría existente
    - descripcion: opcional
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se admiten ficheros CSV. Para Excel, exporta como CSV primero.",
        )

    contenido = await file.read()
    texto = contenido.decode("utf-8-sig")  # utf-8-sig elimina el BOM si existe
    reader = csv.DictReader(io.StringIO(texto))

    insertados = 0
    errores = []

    for i, fila in enumerate(reader, start=2):  # start=2 porque la fila 1 es la cabecera
        try:
            # Buscar la categoría por nombre
            categoria = conn.execute(
                """SELECT id FROM categorias
                   WHERE nombre = ? AND (usuario_id IS NULL OR usuario_id = ?)""",
                (fila.get("categoria", "").strip(), user["id"]),
            ).fetchone()

            if categoria is None:
                errores.append(f"Fila {i}: categoría '{fila.get('categoria')}' no encontrada")
                continue

            tipo = fila.get("tipo", "").strip().lower()
            if tipo not in ("ingreso", "gasto"):
                errores.append(f"Fila {i}: tipo '{tipo}' no válido")
                continue

            importe = float(fila.get("importe", 0))
            if importe <= 0:
                errores.append(f"Fila {i}: importe debe ser mayor que 0")
                continue

            conn.execute(
                """INSERT INTO movimientos
                   (cuenta_id, categoria_id, usuario_id, importe, tipo, descripcion, fecha)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    cuenta_id,
                    categoria["id"],
                    user["id"],
                    importe,
                    tipo,
                    fila.get("descripcion", "").strip() or None,
                    fila.get("fecha", "").strip(),
                ),
            )
            insertados += 1

        except Exception as e:
            errores.append(f"Fila {i}: {str(e)}")

    conn.commit()

    return {
        "insertados": insertados,
        "errores": errores,
        "mensaje": f"{insertados} movimiento(s) importado(s) correctamente"
                   + (f", {len(errores)} error(es)" if errores else ""),
    }