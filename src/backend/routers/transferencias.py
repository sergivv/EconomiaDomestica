# routers/transferencias.py
# Endpoints de transferencias
#
# GET  /transferencias                    → lista con filtro pendientes/completadas
# POST /transferencias                    → crea transferencia entre cuentas
# PUT  /transferencias/{id}/confirmar     → confirma transferencia pendiente

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Annotated
from datetime import date
import sqlite3

from database import get_db
from routers.auth import current_user

router = APIRouter(prefix="/transferencias", tags=["transferencias"])


# ------------------------------------------------------------
# Schemas
# ------------------------------------------------------------

class TransferenciaCreate(BaseModel):
    cuenta_origen_id: int
    cuenta_destino_id: int
    importe: float
    fecha: date
    descripcion: str | None = None


class TransferenciaResponse(BaseModel):
    id: int
    cuenta_origen_id: int
    cuenta_destino_id: int
    importe: float
    fecha: str
    descripcion: str | None
    completada: bool
    creado_en: str
    # Campos extra para mostrar en el frontend
    cuenta_origen_nombre: str | None = None
    cuenta_destino_nombre: str | None = None


# ------------------------------------------------------------
# Utilidad: obtener transferencia con datos enriquecidos
# ------------------------------------------------------------

def get_transferencia_detalle(conn: sqlite3.Connection, transferencia_id: int):
    return conn.execute(
        """SELECT t.*,
                  co.nombre AS cuenta_origen_nombre,
                  cd.nombre AS cuenta_destino_nombre
           FROM transferencias t
           LEFT JOIN cuentas co ON t.cuenta_origen_id  = co.id
           LEFT JOIN cuentas cd ON t.cuenta_destino_id = cd.id
           WHERE t.id = ?""",
        (transferencia_id,)
    ).fetchone()


# ------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------

@router.get("", response_model=list[TransferenciaResponse])
async def listar_transferencias(
    _: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
    completada: bool | None = None,  # None = todas, True = completadas, False = pendientes
):
    """
    Lista transferencias entre cuentas.
    Filtro opcional: ?completada=false (pendientes) | ?completada=true (completadas)
    """
    query = """
        SELECT t.*,
               co.nombre AS cuenta_origen_nombre,
               cd.nombre AS cuenta_destino_nombre
        FROM transferencias t
        LEFT JOIN cuentas co ON t.cuenta_origen_id  = co.id
        LEFT JOIN cuentas cd ON t.cuenta_destino_id = cd.id
        WHERE 1=1
    """
    params = []

    if completada is not None:
        query += " AND t.completada = ?"
        params.append(1 if completada else 0)

    query += " ORDER BY t.fecha DESC, t.creado_en DESC"

    transferencias = conn.execute(query, params).fetchall()
    return [dict(t) for t in transferencias]


@router.post("", response_model=TransferenciaResponse, status_code=status.HTTP_201_CREATED)
async def crear_transferencia(
    datos: TransferenciaCreate,
    _: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Crea una transferencia entre dos cuentas.
    Se crea como pendiente (completada=0) hasta que se confirme manualmente.
    Uso habitual: asignación mensual de la cuenta común a las personales.
    """
    if datos.importe <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El importe debe ser mayor que 0",
        )

    if datos.cuenta_origen_id == datos.cuenta_destino_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las cuentas de origen y destino deben ser distintas",
        )

    # Verificar que ambas cuentas existen
    for cuenta_id in (datos.cuenta_origen_id, datos.cuenta_destino_id):
        cuenta = conn.execute(
            "SELECT id FROM cuentas WHERE id = ?", (cuenta_id,)
        ).fetchone()
        if cuenta is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cuenta {cuenta_id} no encontrada",
            )

    cursor = conn.execute(
        """INSERT INTO transferencias
           (cuenta_origen_id, cuenta_destino_id, importe, fecha, descripcion, completada)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (
            datos.cuenta_origen_id,
            datos.cuenta_destino_id,
            datos.importe,
            str(datos.fecha),
            datos.descripcion,
        ),
    )
    conn.commit()

    nueva = get_transferencia_detalle(conn, cursor.lastrowid)
    return dict(nueva)


@router.put("/{transferencia_id}/confirmar", response_model=TransferenciaResponse)
async def confirmar_transferencia(
    transferencia_id: int,
    _: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Confirma una transferencia pendiente.
    A partir de este momento se tiene en cuenta en el cálculo de saldos.
    """
    transferencia = conn.execute(
        "SELECT * FROM transferencias WHERE id = ?", (transferencia_id,)
    ).fetchone()

    if transferencia is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transferencia no encontrada",
        )

    if transferencia["completada"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La transferencia ya está confirmada",
        )

    conn.execute(
        "UPDATE transferencias SET completada = 1 WHERE id = ?",
        (transferencia_id,)
    )
    conn.commit()

    confirmada = get_transferencia_detalle(conn, transferencia_id)
    return dict(confirmada)