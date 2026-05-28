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
# Tipos que cotizan en BYMA y para los que probamos data912 primero.
_TIPOS_AR = {"accion_ar", "cedear", "bono"}


@st.cache_data(ttl=300, show_spinner=False)
def get_last_price(ticker: str, tipo: Optional[str] = None) -> Optional[float]:
    """
    Ultimo precio de cierre.
    Para tipos argentinos (accion_ar / cedear / bono) intenta data912 primero
    (BYMA en vivo, sin sufijo .BA, con ajuste /100 para bonos) y cae a yfinance.
    Para US / ETF / cripto usa yfinance directo.
    """
    if tipo in _TIPOS_AR:
        try:
            from core.data_ar import get_price_ar
            p = get_price_ar(ticker, tipo)
            if p is not None:
                return p
        except Exception:
            pass

    # Fallback: yfinance
    try:
        t = _yticker(ticker)
        hist = t.history(period="5d", auto_adjust=False)
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


@st.cache_data(ttl=900, show_spinner=False)
def get_history(ticker: str, period: str = "6mo",
                tipo: Optional[str] = None) -> pd.DataFrame:
    """
    Historico OHLC desde yfinance. DataFrame vacio si falla.
    Para tipos argentinos sin sufijo .BA, probamos agregando .BA porque
    asi es como cotizan en Yahoo (TXAR -> TXAR.BA).
    """
    candidatos = [ticker]
    if tipo in _TIPOS_AR and isinstance(ticker, str) and not ticker.upper().endswith(".BA"):
        candidatos.insert(0, f"{ticker}.BA")
    try:
        for tk in candidatos:
            t = _yticker(tk)
            df = t.history(period=period, auto_adjust=False)
            if df is not None and not df.empty:
                return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def get_info(ticker: str) -> dict:
    """
    Info fundamental (sector, country, etc).
    Para tickers BYMA con sufijo .BA o cedears sin sufijo (MELI, AAPL...),
    yfinance.info muchas veces vuelve vacio. Probamos primero el ticker como
    viene; si no trae sector/country, reintentamos con el underlying en US.
    """
    candidatos = [ticker]
    # Strip .BA y probar tambien el underlying
    if isinstance(ticker, str):
        up = ticker.upper()
        if up.endswith(".BA"):
            candidatos.append(up[:-3])
    for tk in candidatos:
        try:
            t = _yticker(tk)
            info = t.info or {}
            if info.get("sector") or info.get("country") or info.get("longName"):
                return info
        except Exception:
            continue
    return {}


# -----------------------------------------------------------------------------
# DOLAR ARGENTINA
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def get_dolares() -> dict:
    """
    Devuelve dict con cotizaciones oficiales, MEP, CCL, blue, cripto, mayorista, tarjeta.
    Estructura: {'oficial': {'compra': X, 'venta': Y}, 'mep': {...}, ...}

    Nota: dolarapi llama "bolsa" al MEP; aca lo exponemos como 'mep' (y mantenemos
    'bolsa' como alias para no romper consumidores).
    """
    # alias casa-de-dolarapi -> claves internas usadas en la app
    ALIAS = {"bolsa": "mep"}
    try:
        r = requests.get("https://dolarapi.com/v1/dolares", timeout=10)
        r.raise_for_status()
        data = r.json()
        out = {}
        for item in data:
            casa = item.get("casa", "").lower()
            entry = {
                "compra": item.get("compra"),
                "venta":  item.get("venta"),
                "fecha":  item.get("fechaActualizacion"),
                "nombre": item.get("nombre"),
            }
            out[casa] = entry
            if casa in ALIAS:
                out[ALIAS[casa]] = entry
        return out
    except Exception:
        return {}


def get_fx_rate(tipo: str = "mep") -> Optional[float]:
    """Atajo: devuelve la venta del tipo de dolar pedido."""
    d = get_dolares()
    return d.get(tipo, {}).get("venta")


# Mapeo casa interna -> nombre del endpoint en argentinadatos
_HISTORIC_CASA = {
    "oficial": "oficial",
    "blue":    "blue",
    "mep":     "bolsa",      # MEP en argentinadatos se llama "bolsa"
    "bolsa":   "bolsa",
    "ccl":     "contadoconliqui",
    "contadoconliqui": "contadoconliqui",
    "cripto":  "cripto",
    "mayorista": "mayorista",
}


@st.cache_data(ttl=3600, show_spinner=False)
def get_dolar_historic(casa: str = "mep") -> pd.DataFrame:
    """
    Serie historica diaria de una cotizacion de dolar via argentinadatos.
    DataFrame con columnas [fecha, compra, venta]. Vacio si falla.
    """
    casa_api = _HISTORIC_CASA.get(casa.lower(), casa.lower())
    try:
        r = requests.get(
            f"https://api.argentinadatos.com/v1/cotizaciones/dolares/{casa_api}",
            timeout=15,
        )
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        if df.empty:
            return df
        df["fecha"] = pd.to_datetime(df["fecha"])
        df["compra"] = pd.to_numeric(df["compra"], errors="coerce")
        df["venta"]  = pd.to_numeric(df["venta"], errors="coerce")
        return df.sort_values("fecha").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


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


@st.cache_data(ttl=1800, show_spinner=False)
def get_riesgo_pais_historic() -> pd.DataFrame:
    """Serie diaria historica del EMBI Argentina. DataFrame [fecha, valor]."""
    try:
        r = requests.get(
            "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais",
            timeout=15,
        )
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        if df.empty:
            return df
        df["fecha"] = pd.to_datetime(df["fecha"])
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
        return df.sort_values("fecha").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


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
