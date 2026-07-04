# routers/cuentas.py
# Endpoints de cuentas
#
# GET  /cuentas          → lista todas las cuentas
# GET  /cuentas/{id}     → detalle con saldo calculado
# GET  /cuentas/{id}/saldo → saldo actual

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Annotated
import sqlite3

from database import get_db
from routers.auth import current_user

router = APIRouter(prefix="/cuentas", tags=["cuentas"])


# ------------------------------------------------------------
# Schemas
# ------------------------------------------------------------

class CuentaResponse(BaseModel):
    id: int
    nombre: str
    tipo: str
    saldo_inicial: float
    usuario_id: int | None  # None = cuenta común


class CuentaDetalleResponse(CuentaResponse):
    saldo_actual: float
    total_ingresos: float
    total_gastos: float


class SaldoResponse(BaseModel):
    cuenta_id: int
    saldo_inicial: float
    total_ingresos: float
    total_gastos: float
    saldo_actual: float


# ------------------------------------------------------------
# Utilidad: calcula el saldo de una cuenta
# ------------------------------------------------------------

def calcular_saldo(conn: sqlite3.Connection, cuenta_id: int) -> dict:
    """
    Saldo actual = saldo_inicial
                 + suma de ingresos
                 - suma de gastos
                 + transferencias recibidas (completadas)
                 - transferencias enviadas (completadas)
    """
    cuenta = conn.execute(
        "SELECT * FROM cuentas WHERE id = ?", (cuenta_id,)
    ).fetchone()

    if cuenta is None:
        return None

    ingresos = conn.execute(
        """SELECT COALESCE(SUM(importe), 0)
           FROM movimientos
           WHERE cuenta_id = ? AND tipo = 'ingreso'""",
        (cuenta_id,)
    ).fetchone()[0]

    gastos = conn.execute(
        """SELECT COALESCE(SUM(importe), 0)
           FROM movimientos
           WHERE cuenta_id = ? AND tipo = 'gasto'""",
        (cuenta_id,)
    ).fetchone()[0]

    transferencias_recibidas = conn.execute(
        """SELECT COALESCE(SUM(importe), 0)
           FROM transferencias
           WHERE cuenta_destino_id = ? AND completada = 1""",
        (cuenta_id,)
    ).fetchone()[0]

    transferencias_enviadas = conn.execute(
        """SELECT COALESCE(SUM(importe), 0)
           FROM transferencias
           WHERE cuenta_origen_id = ? AND completada = 1""",
        (cuenta_id,)
    ).fetchone()[0]

    saldo_actual = (
        cuenta["saldo_inicial"]
        + ingresos
        - gastos
        + transferencias_recibidas
        - transferencias_enviadas
    )

    return {
        "saldo_inicial": cuenta["saldo_inicial"],
        "total_ingresos": ingresos,
        "total_gastos": gastos,
        "saldo_actual": saldo_actual,
    }


# ------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------

@router.get("", response_model=list[CuentaResponse])
async def listar_cuentas(
    _: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Devuelve las tres cuentas del hogar:
    - cuenta común (usuario_id NULL)
    - cuenta personal del usuario A
    - cuenta personal del usuario B
    """
    cuentas = conn.execute(
        "SELECT * FROM cuentas ORDER BY tipo DESC, id ASC"
    ).fetchall()

    return [dict(c) for c in cuentas]


@router.get("/{cuenta_id}", response_model=CuentaDetalleResponse)
async def detalle_cuenta(
    cuenta_id: int,
    _: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
):
    """Detalle de una cuenta con saldo calculado."""
    cuenta = conn.execute(
        "SELECT * FROM cuentas WHERE id = ?", (cuenta_id,)
    ).fetchone()

    if cuenta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuenta no encontrada",
        )

    saldo = calcular_saldo(conn, cuenta_id)

    return {**dict(cuenta), **saldo}


@router.get("/{cuenta_id}/saldo", response_model=SaldoResponse)
async def saldo_cuenta(
    cuenta_id: int,
    _: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
):
    """Saldo actual desglosado: saldo inicial, ingresos, gastos y neto."""
    cuenta = conn.execute(
        "SELECT id FROM cuentas WHERE id = ?", (cuenta_id,)
    ).fetchone()

    if cuenta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuenta no encontrada",
        )

    saldo = calcular_saldo(conn, cuenta_id)

    return {"cuenta_id": cuenta_id, **saldo}