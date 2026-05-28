"""
Fuente de precios argentina via data912.com (snapshot en vivo de BYMA).

Endpoints publicos sin auth:
- /live/arg_stocks    -> acciones lideres y panel general (ALUA, GGAL, TXAR, YPFD, ...)
- /live/arg_cedears   -> cedears (AAPL, MELI, LMT, FXI, ...)
- /live/arg_bonds     -> bonos soberanos en pesos (AE38, AL30, GD30, ...)
- /live/arg_notes     -> letras / notas del tesoro

Para bonos, el precio viene "por cada 100 VN" (lamina) - hay que dividir por 100
para que cuadre con la valuacion por unidad de Balanz/IOL.
"""
from __future__ import annotations
from typing import Optional
import pandas as pd
import requests
import streamlit as st

BASE = "https://data912.com/live"

# Endpoints disponibles
ENDPOINTS = {
    "stocks":  f"{BASE}/arg_stocks",
    "cedears": f"{BASE}/arg_cedears",
    "bonds":   f"{BASE}/arg_bonds",
    "notes":   f"{BASE}/arg_notes",
}


@st.cache_data(ttl=180, show_spinner=False)
def _fetch(kind: str) -> pd.DataFrame:
    """Trae el snapshot de un endpoint. DataFrame vacio si falla."""
    url = ENDPOINTS.get(kind)
    if not url:
        return pd.DataFrame()
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        if df.empty:
            return df
        df["symbol"] = df["symbol"].astype(str).str.upper()
        return df
    except Exception:
        return pd.DataFrame()


def get_arg_snapshot() -> dict[str, pd.DataFrame]:
    """Snapshot de los 4 mercados."""
    return {k: _fetch(k) for k in ENDPOINTS.keys()}


# tipo (codigo interno) -> endpoint(s) a consultar en orden
_TIPO_TO_KINDS = {
    "accion_ar": ["stocks"],
    "cedear":    ["cedears"],
    "bono":      ["bonds", "notes"],
    "fci":       [],   # no hay feed publico, fallback a Yahoo
}


def get_price_ar(ticker: str, tipo: str) -> Optional[float]:
    """
    Precio actual de un ticker AR (en ARS) usando data912.
    Para bonos divide por 100 (data912 cotiza por lamina de 100 VN).
    Devuelve None si no encuentra el ticker.
    """
    sym = ticker.upper().strip()
    # Acepta tickers con sufijo .BA por compatibilidad con la version anterior
    if sym.endswith(".BA"):
        sym = sym[:-3]

    kinds = _TIPO_TO_KINDS.get(tipo, [])
    for kind in kinds:
        df = _fetch(kind)
        if df.empty or "symbol" not in df.columns:
            continue
        row = df[df["symbol"] == sym]
        if row.empty:
            continue
        # Preferimos 'c' (close). Si es 0/None, caemos a px_bid.
        price = row.iloc[0].get("c")
        if not price or pd.isna(price):
            price = row.iloc[0].get("px_bid")
        if not price or pd.isna(price) or price <= 0:
            continue
        price = float(price)
        if tipo == "bono":
            price = price / 100.0
        return price
    return None
