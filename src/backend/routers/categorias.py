# routers/categorias.py
# Endpoints de categorías
#
# GET    /categorias        → lista categorías del sistema + propias del usuario
# POST   /categorias        → crea categoría personalizada
# PUT    /categorias/{id}   → edita nombre (sistema y propias)
# DELETE /categorias/{id}   → elimina (solo propias)

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Annotated
import sqlite3

from database import get_db
from routers.auth import current_user

router = APIRouter(prefix="/categorias", tags=["categorias"])


# ------------------------------------------------------------
# Schemas
# ------------------------------------------------------------

class CategoriaResponse(BaseModel):
    id: int
    nombre: str
    tipo: str
    usuario_id: int | None
    es_sistema: bool


class CategoriaCreate(BaseModel):
    nombre: str
    tipo: str  # 'ingreso' | 'gasto'


class CategoriaUpdate(BaseModel):
    nombre: str


# ------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------

@router.get("", response_model=list[CategoriaResponse])
async def listar_categorias(
    user: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
    tipo: str | None = None,  # filtro opcional: 'ingreso' | 'gasto'
):
    """
    Devuelve las categorías del sistema (es_sistema=1)
    más las categorías personales del usuario autenticado.
    Filtro opcional por tipo: ?tipo=ingreso o ?tipo=gasto
    """
    query = """
        SELECT * FROM categorias
        WHERE (usuario_id IS NULL OR usuario_id = ?)
    """
    params = [user["id"]]

    if tipo:
        if tipo not in ("ingreso", "gasto"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El tipo debe ser 'ingreso' o 'gasto'",
            )
        query += " AND tipo = ?"
        params.append(tipo)

    query += " ORDER BY es_sistema DESC, tipo ASC, nombre ASC"

    categorias = conn.execute(query, params).fetchall()
    return [dict(c) for c in categorias]


@router.post("", response_model=CategoriaResponse, status_code=status.HTTP_201_CREATED)
async def crear_categoria(
    datos: CategoriaCreate,
    user: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
):
    """Crea una categoría personalizada para el usuario autenticado."""
    if datos.tipo not in ("ingreso", "gasto"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El tipo debe ser 'ingreso' o 'gasto'",
        )

    # Comprobar que no existe ya una categoría con ese nombre para este usuario
    existente = conn.execute(
        """SELECT id FROM categorias
           WHERE nombre = ? AND (usuario_id = ? OR usuario_id IS NULL)""",
        (datos.nombre, user["id"]),
    ).fetchone()

    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una categoría con ese nombre",
        )

    cursor = conn.execute(
        """INSERT INTO categorias (nombre, tipo, usuario_id, es_sistema)
           VALUES (?, ?, ?, 0)""",
        (datos.nombre, datos.tipo, user["id"]),
    )
    conn.commit()

    nueva = conn.execute(
        "SELECT * FROM categorias WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()

    return dict(nueva)


@router.put("/{categoria_id}", response_model=CategoriaResponse)
async def editar_categoria(
    categoria_id: int,
    datos: CategoriaUpdate,
    user: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Edita el nombre de una categoría.
    - Categorías del sistema: cualquier usuario puede renombrarlas
    - Categorías personales: solo el propietario
    """
    categoria = conn.execute(
        "SELECT * FROM categorias WHERE id = ?", (categoria_id,)
    ).fetchone()

    if categoria is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría no encontrada",
        )

    # Si es personal, verificar que pertenece al usuario
    if not categoria["es_sistema"] and categoria["usuario_id"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para editar esta categoría",
        )

    conn.execute(
        "UPDATE categorias SET nombre = ? WHERE id = ?",
        (datos.nombre, categoria_id),
    )
    conn.commit()

    actualizada = conn.execute(
        "SELECT * FROM categorias WHERE id = ?", (categoria_id,)
    ).fetchone()

    return dict(actualizada)


@router.delete("/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_categoria(
    categoria_id: int,
    user: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Elimina una categoría personal del usuario autenticado.
    Las categorías del sistema no se pueden eliminar.
    """
    categoria = conn.execute(
        "SELECT * FROM categorias WHERE id = ?", (categoria_id,)
    ).fetchone()

    if categoria is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría no encontrada",
        )

    if categoria["es_sistema"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Las categorías del sistema no se pueden eliminar",
        )

    if categoria["usuario_id"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para eliminar esta categoría",
        )

    # Comprobar que no hay movimientos usando esta categoría
    en_uso = conn.execute(
        "SELECT COUNT(*) FROM movimientos WHERE categoria_id = ?",
        (categoria_id,)
    ).fetchone()[0]

    if en_uso > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede eliminar: hay {en_uso} movimiento(s) con esta categoría",
        )

    conn.execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
    conn.commit()