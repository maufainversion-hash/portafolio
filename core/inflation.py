"""
Calculo del factor de ajuste por inflacion (CER) entre dos fechas.

Usa la serie mensual de INDEC desde argentinadatos.com.
factor(desde, hasta) = prod((1 + ipc_m/100)) para cada mes entre [desde, hasta).

Si la fecha cae a mitad de mes, se prorratea linealmente sobre el mes
completo (aproximacion: dias_transcurridos / dias_del_mes).
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional
import pandas as pd
import streamlit as st
from calendar import monthrange

from core.data import get_inflacion_mensual


@st.cache_data(ttl=3600, show_spinner=False)
def _serie_indexada() -> pd.DataFrame:
    """Trae la serie mensual con index = fecha (primer dia del mes)."""
    df = get_inflacion_mensual()
    if df.empty:
        return df
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.normalize()
    # Aseguramos que la fecha sea el primer dia del mes
    df["fecha"] = df["fecha"].apply(lambda d: d.replace(day=1))
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna(subset=["valor"]).sort_values("fecha").reset_index(drop=True)
    return df


def cer_factor(fecha_desde, fecha_hasta=None) -> Optional[float]:
    """
    Factor de ajuste entre dos fechas (1.0 = sin cambio).
    Por ej., 1.32 significa que algo costaba 100 y al ajustar ahora vale 132.
    Devuelve None si no hay datos suficientes.
    """
    df = _serie_indexada()
    if df.empty:
        return None

    if isinstance(fecha_desde, str):
        fecha_desde = datetime.fromisoformat(fecha_desde).date()
    if fecha_hasta is None:
        fecha_hasta = date.today()
    if isinstance(fecha_hasta, str):
        fecha_hasta = datetime.fromisoformat(fecha_hasta).date()

    if fecha_desde >= fecha_hasta:
        return 1.0

    factor = 1.0
    # Iteramos mes a mes desde el mes de fecha_desde al mes de fecha_hasta
    cur = date(fecha_desde.year, fecha_desde.month, 1)
    end_month = date(fecha_hasta.year, fecha_hasta.month, 1)

    while cur <= end_month:
        # IPC del mes 'cur' (corresponde al cierre del mes)
        ipc_row = df[df["fecha"] == pd.Timestamp(cur)]
        if ipc_row.empty:
            # No tenemos el dato (mes muy reciente o muy viejo): saltamos
            cur = _next_month(cur)
            continue
        ipc = float(ipc_row.iloc[0]["valor"]) / 100.0

        # Fraccion del mes a aplicar
        days_in_month = monthrange(cur.year, cur.month)[1]
        if cur.year == fecha_desde.year and cur.month == fecha_desde.month:
            # Primer mes: dias restantes desde fecha_desde
            dias_aplicables = days_in_month - fecha_desde.day + 1
            frac = dias_aplicables / days_in_month
        elif cur.year == fecha_hasta.year and cur.month == fecha_hasta.month:
            # Ultimo mes: dias hasta fecha_hasta
            frac = fecha_hasta.day / days_in_month
        else:
            frac = 1.0

        factor *= (1 + ipc) ** frac
        cur = _next_month(cur)

    return factor


def _next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)
