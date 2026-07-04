# routers/informes.py
# Endpoints de informes y análisis
#
# GET /informes/resumen          → ingresos, gastos y saldo neto del mes
# GET /informes/por-categoria    → gastos agrupados por categoría (con %)
# GET /informes/evolucion        → evolución mes a mes (para gráficas)
# GET /informes/por-persona      → comparativa de gastos entre los dos usuarios

from fastapi import APIRouter, Depends
from typing import Annotated
from datetime import date
import sqlite3

from database import get_db
from routers.auth import current_user

router = APIRouter(prefix="/informes", tags=["informes"])


# ------------------------------------------------------------
# Utilidad: rango de fechas por defecto (mes actual)
# ------------------------------------------------------------

def rango_mes_actual():
    hoy = date.today()
    inicio = date(hoy.year, hoy.month, 1)
    # Último día del mes
    if hoy.month == 12:
        fin = date(hoy.year + 1, 1, 1).replace(day=1)
    else:
        fin = date(hoy.year, hoy.month + 1, 1)
    from datetime import timedelta
    fin = fin - timedelta(days=1)
    return inicio, fin


# ------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------

@router.get("/resumen")
async def resumen(
    _: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    cuenta_id: int | None = None,
):
    """
    Resumen del período: total ingresos, total gastos y saldo neto.
    Por defecto muestra el mes actual.
    Filtro opcional por cuenta.
    """
    if fecha_desde is None or fecha_hasta is None:
        fecha_desde, fecha_hasta = rango_mes_actual()

    filtro_cuenta = "AND cuenta_id = ?" if cuenta_id else ""
    params_base = [str(fecha_desde), str(fecha_hasta)]
    if cuenta_id:
        params_base.append(cuenta_id)

    ingresos = conn.execute(
        f"""SELECT COALESCE(SUM(importe), 0)
            FROM movimientos
            WHERE tipo = 'ingreso'
              AND fecha BETWEEN ? AND ?
              {filtro_cuenta}""",
        params_base,
    ).fetchone()[0]

    gastos = conn.execute(
        f"""SELECT COALESCE(SUM(importe), 0)
            FROM movimientos
            WHERE tipo = 'gasto'
              AND fecha BETWEEN ? AND ?
              {filtro_cuenta}""",
        params_base,
    ).fetchone()[0]

    # Transferencias confirmadas recibidas y enviadas en el período
    transferencias_recibidas = conn.execute(
        f"""SELECT COALESCE(SUM(importe), 0)
            FROM transferencias
            WHERE completada = 1
              AND fecha BETWEEN ? AND ?
              {"AND cuenta_destino_id = ?" if cuenta_id else ""}""",
        params_base,
    ).fetchone()[0]

    transferencias_enviadas = conn.execute(
        f"""SELECT COALESCE(SUM(importe), 0)
            FROM transferencias
            WHERE completada = 1
              AND fecha BETWEEN ? AND ?
              {"AND cuenta_origen_id = ?" if cuenta_id else ""}""",
        params_base,
    ).fetchone()[0]

    num_movimientos = conn.execute(
        f"""SELECT COUNT(*)
            FROM movimientos
            WHERE fecha BETWEEN ? AND ?
            {filtro_cuenta}""",
        params_base,
    ).fetchone()[0]

    return {
        "periodo": {
            "fecha_desde": str(fecha_desde),
            "fecha_hasta": str(fecha_hasta),
        },
        "ingresos": round(ingresos, 2),
        "gastos": round(gastos, 2),
        "saldo_neto": round(ingresos - gastos, 2),
        "transferencias_recibidas": round(transferencias_recibidas, 2),
        "transferencias_enviadas": round(transferencias_enviadas, 2),
        "num_movimientos": num_movimientos,
    }


@router.get("/por-categoria")
async def por_categoria(
    _: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    tipo: str = "gasto",        # 'ingreso' | 'gasto'
    cuenta_id: int | None = None,
):
    """
    Gastos o ingresos agrupados por categoría con porcentaje sobre el total.
    Por defecto muestra gastos del mes actual.
    """
    if fecha_desde is None or fecha_hasta is None:
        fecha_desde, fecha_hasta = rango_mes_actual()

    params = [tipo, str(fecha_desde), str(fecha_hasta)]
    filtro_cuenta = ""
    if cuenta_id:
        filtro_cuenta = "AND m.cuenta_id = ?"
        params.append(cuenta_id)

    filas = conn.execute(
        f"""SELECT c.nombre AS categoria,
                   c.id     AS categoria_id,
                   COALESCE(SUM(m.importe), 0) AS total
            FROM categorias c
            LEFT JOIN movimientos m
              ON m.categoria_id = c.id
             AND m.tipo    = ?
             AND m.fecha BETWEEN ? AND ?
             {filtro_cuenta}
            WHERE c.tipo = ?
            GROUP BY c.id, c.nombre
            ORDER BY total DESC""",
        params + [tipo],
    ).fetchall()

    total_general = sum(f["total"] for f in filas)

    resultado = []
    for f in filas:
        porcentaje = round((f["total"] / total_general * 100), 1) if total_general > 0 else 0
        resultado.append({
            "categoria_id": f["categoria_id"],
            "categoria": f["categoria"],
            "total": round(f["total"], 2),
            "porcentaje": porcentaje,
        })

    return {
        "periodo": {
            "fecha_desde": str(fecha_desde),
            "fecha_hasta": str(fecha_hasta),
        },
        "tipo": tipo,
        "total": round(total_general, 2),
        "categorias": resultado,
    }


@router.get("/evolucion")
async def evolucion(
    _: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
    meses: int = 6,             # cuántos meses hacia atrás mostrar
    cuenta_id: int | None = None,
):
    """
    Evolución mes a mes de ingresos y gastos.
    Por defecto muestra los últimos 6 meses.
    Útil para renderizar gráficas de tendencias en el frontend.
    """
    from datetime import timedelta
    import calendar

    hoy = date.today()
    resultado = []

    for i in range(meses - 1, -1, -1):
        # Calcular el mes correspondiente
        mes = hoy.month - i
        anio = hoy.year
        while mes <= 0:
            mes += 12
            anio -= 1

        inicio = date(anio, mes, 1)
        fin = date(anio, mes, calendar.monthrange(anio, mes)[1])

        params = [str(inicio), str(fin)]
        filtro_cuenta = ""
        if cuenta_id:
            filtro_cuenta = "AND cuenta_id = ?"
            params.append(cuenta_id)

        ingresos = conn.execute(
            f"""SELECT COALESCE(SUM(importe), 0)
                FROM movimientos
                WHERE tipo = 'ingreso'
                  AND fecha BETWEEN ? AND ?
                  {filtro_cuenta}""",
            params,
        ).fetchone()[0]

        gastos = conn.execute(
            f"""SELECT COALESCE(SUM(importe), 0)
                FROM movimientos
                WHERE tipo = 'gasto'
                  AND fecha BETWEEN ? AND ?
                  {filtro_cuenta}""",
            params,
        ).fetchone()[0]

        resultado.append({
            "mes": f"{anio}-{mes:02d}",
            "etiqueta": inicio.strftime("%b %Y"),
            "ingresos": round(ingresos, 2),
            "gastos": round(gastos, 2),
            "saldo_neto": round(ingresos - gastos, 2),
        })

    return {
        "meses": meses,
        "cuenta_id": cuenta_id,
        "datos": resultado,
    }


@router.get("/por-persona")
async def por_persona(
    _: Annotated[dict, Depends(current_user)],
    conn: sqlite3.Connection = Depends(get_db),
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    tipo: str = "gasto",        # 'ingreso' | 'gasto'
):
    """
    Comparativa de gastos o ingresos entre los dos usuarios del hogar.
    Por defecto muestra gastos del mes actual.
    """
    if fecha_desde is None or fecha_hasta is None:
        fecha_desde, fecha_hasta = rango_mes_actual()

    usuarios = conn.execute("SELECT id, nombre FROM usuarios").fetchall()

    resultado = []
    total_general = 0

    for usuario in usuarios:
        total = conn.execute(
            """SELECT COALESCE(SUM(importe), 0)
               FROM movimientos
               WHERE usuario_id = ?
                 AND tipo = ?
                 AND fecha BETWEEN ? AND ?""",
            (usuario["id"], tipo, str(fecha_desde), str(fecha_hasta)),
        ).fetchone()[0]

        total_general += total

        # Desglose por categoría para este usuario
        categorias = conn.execute(
            """SELECT c.nombre AS categoria,
                      COALESCE(SUM(m.importe), 0) AS total
               FROM movimientos m
               JOIN categorias c ON m.categoria_id = c.id
               WHERE m.usuario_id = ?
                 AND m.tipo = ?
                 AND m.fecha BETWEEN ? AND ?
               GROUP BY c.id, c.nombre
               ORDER BY total DESC""",
            (usuario["id"], tipo, str(fecha_desde), str(fecha_hasta)),
        ).fetchall()

        resultado.append({
            "usuario_id": usuario["id"],
            "usuario": usuario["nombre"],
            "total": round(total, 2),
            "categorias": [
                {"categoria": c["categoria"], "total": round(c["total"], 2)}
                for c in categorias
            ],
        })

    # Añadir porcentaje sobre el total del hogar
    for r in resultado:
        r["porcentaje"] = round(
            (r["total"] / total_general * 100), 1
        ) if total_general > 0 else 0

    return {
        "periodo": {
            "fecha_desde": str(fecha_desde),
            "fecha_hasta": str(fecha_hasta),
        },
        "tipo": tipo,
        "total_hogar": round(total_general, 2),
        "usuarios": resultado,
    }