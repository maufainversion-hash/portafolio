"""
Sistema de moneda de display global.

La app puede mostrar todos los valores en ARS, USD MEP o USD CCL.
La eleccion vive en st.session_state["display_ccy"] (default: ARS) y se
controla con un selector global en app.py.

Helpers principales:
    - get_display_ccy()    -> "ARS" | "USD_MEP" | "USD_CCL"
    - get_fx_for_display() -> tipo de cambio a aplicar (1.0 si ARS)
    - convert_ars(v_ars)   -> valor convertido a la moneda de display
    - fmt_display(v_ars)   -> string formateado con simbolo correcto
"""
from __future__ import annotations
from typing import Optional
import pandas as pd
import streamlit as st

from core.data import get_dolares


# Opciones disponibles en el selector
OPCIONES = {
    "ARS":     ("ARS",      "$",   None),    # sin conversion
    "USD_MEP": ("USD MEP",  "US$", "mep"),
    "USD_CCL": ("USD CCL",  "US$", "contadoconliqui"),
}


def get_display_ccy() -> str:
    """Devuelve el codigo de moneda de display. Default 'ARS'."""
    return st.session_state.get("display_ccy", "ARS")


def get_display_meta() -> tuple[str, str, Optional[str]]:
    """Devuelve (label, simbolo, casa_dolarapi) para la moneda activa."""
    return OPCIONES.get(get_display_ccy(), OPCIONES["ARS"])


def get_fx_for_display() -> float:
    """
    Factor de division para pasar de ARS a la moneda de display.
    ARS -> 1.0, USD_MEP -> precio MEP, USD_CCL -> precio CCL.
    Si no se pudo obtener el FX, devuelve 1.0 (fallback seguro).
    """
    label, sym, casa = get_display_meta()
    if casa is None:
        return 1.0
    fx = get_dolares().get(casa, {}).get("venta")
    return float(fx) if fx and fx > 0 else 1.0


def convert_ars(v_ars):
    """Convierte un valor en ARS a la moneda de display. NaN-safe."""
    if v_ars is None or (hasattr(pd, 'isna') and pd.isna(v_ars)):
        return v_ars
    return float(v_ars) / get_fx_for_display()


def fmt_display(v_ars, sin_simbolo: bool = False) -> str:
    """
    Formatea un valor en ARS a la moneda de display: '$ 1.234.567,89' o
    'US$ 8.640,12'. NaN -> '—'.
    """
    if v_ars is None or pd.isna(v_ars):
        return "—"
    v = convert_ars(v_ars)
    _, sym, _ = get_display_meta()
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s if sin_simbolo else f"{sym} {s}"


def display_symbol() -> str:
    """Simbolo de la moneda activa."""
    return get_display_meta()[1]


def display_label() -> str:
    """Label corto: ARS / USD MEP / USD CCL."""
    return get_display_meta()[0]
