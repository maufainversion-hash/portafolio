"""
Conectores a datos externos:
- yfinance (precios, historico, info sectorial)
- dolarapi.com (cotizaciones dolar oficial/MEP/CCL/blue)
- argentinadatos.com (riesgo pais, inflacion)
- criptoya.com (precios crypto en ARS)
- yfinance ^MERV (Merval)

Todas las funciones usan st.cache_data para evitar rate limits.
"""
from __future__ import annotations
import time
from typing import Optional
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# Session que impersona Chrome para sortear el bloqueo de Yahoo a IPs cloud.
try:
    from curl_cffi import requests as _cffi
    _YF_SESSION = _cffi.Session(impersonate="chrome")
except Exception:
    _YF_SESSION = None

def _yticker(tk: str):
    """Devuelve un yf.Ticker usando la session impersonada si esta disponible."""
    try:
        if _YF_SESSION is not None:
            return yf.Ticker(tk, session=_YF_SESSION)
    except Exception:
        pass
    return yf.Ticker(tk)


# -----------------------------------------------------------------------------
# YFINANCE
# -----------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def get_last_price(ticker: str) -> Optional[float]:
    """Ultimo precio de cierre disponible. None si falla."""
    try:
        t = _yticker(ticker)
        hist = t.history(period="5d", auto_adjust=False)
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


@st.cache_data(ttl=900, show_spinner=False)
def get_history(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Historico OHLC. DataFrame vacio si falla."""
    try:
        t = _yticker(ticker)
        df = t.history(period=period, auto_adjust=False)
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def get_info(ticker: str) -> dict:
    """Info fundamental (sector, country, etc). Dict vacio si falla."""
    try:
        t = _yticker(ticker)
        info = t.info or {}
        return info
    except Exception:
        return {}


# -----------------------------------------------------------------------------
# DOLAR ARGENTINA
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def get_dolares() -> dict:
    """
    Devuelve dict con cotizaciones oficiales, MEP, CCL, blue, cripto.
    Estructura: {'oficial': {'compra': X, 'venta': Y}, 'mep': {...}, ...}
    """
    try:
        r = requests.get("https://dolarapi.com/v1/dolares", timeout=10)
        r.raise_for_status()
        data = r.json()
        out = {}
        for item in data:
            casa = item.get("casa", "").lower()
            out[casa] = {
                "compra": item.get("compra"),
                "venta":  item.get("venta"),
                "fecha":  item.get("fechaActualizacion"),
                "nombre": item.get("nombre"),
            }
        return out
    except Exception:
        return {}


def get_fx_rate(tipo: str = "mep") -> Optional[float]:
    """Atajo: devuelve la venta del tipo de dolar pedido."""
    d = get_dolares()
    return d.get(tipo, {}).get("venta")


# -----------------------------------------------------------------------------
# RIESGO PAIS / INFLACION
# -----------------------------------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def get_riesgo_pais() -> Optional[float]:
    try:
        r = requests.get(
            "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais/ultimo",
            timeout=10,
        )
        r.raise_for_status()
        return float(r.json().get("valor"))
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_inflacion_mensual() -> pd.DataFrame:
    """Serie mensual de inflacion. DataFrame con columnas: fecha, valor."""
    try:
        r = requests.get(
            "https://api.argentinadatos.com/v1/finanzas/indices/inflacion",
            timeout=10,
        )
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        if not df.empty:
            df["fecha"] = pd.to_datetime(df["fecha"])
            df = df.sort_values("fecha").reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


# -----------------------------------------------------------------------------
# MERVAL
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def get_merval() -> Optional[float]:
    try:
        df = get_history("^MERV", period="5d")
        if df.empty:
            return None
        return float(df["Close"].iloc[-1])
    except Exception:
        return None


# -----------------------------------------------------------------------------
# CRYPTO ARS (criptoya)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def get_crypto_ars(symbol: str = "usdt", volumen: float = 0.1) -> dict:
    """
    Precios crypto en ARS desde criptoya.
    Ej: get_crypto_ars('usdt') -> {'binance': {'bid': X, 'ask': Y}, ...}
    """
    try:
        r = requests.get(
            f"https://criptoya.com/api/{symbol}/ars/{volumen}",
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}
