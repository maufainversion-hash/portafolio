"""
Logica del portafolio:
- Cargar tenencias desde DB
- Valuar a precios actuales en multiples monedas (ARS / USD MEP / USD CCL / USD oficial)
- Calcular P&L
- Allocation por distintos campos
- Equity curve historica (sumando precio * cantidad)
"""
from __future__ import annotations
from typing import Optional
import pandas as pd
import numpy as np

from core.db import get_session, Tenencia
from core.data import get_last_price, get_history, get_dolares, get_info


# -----------------------------------------------------------------------------
# CARGA
# -----------------------------------------------------------------------------
def load_tenencias() -> pd.DataFrame:
    """Devuelve un DataFrame con todas las tenencias. Vacio si no hay."""
    with get_session() as s:
        rows = s.query(Tenencia).all()
        if not rows:
            return pd.DataFrame(columns=[
                "id", "ticker", "tipo", "cantidad", "precio_compra",
                "moneda_compra", "fecha_compra",
            ])
        data = [{
            "id":             r.id,
            "ticker":         r.ticker,
            "tipo":           r.tipo,
            "cantidad":       r.cantidad,
            "precio_compra":  r.precio_compra,
            "moneda_compra":  r.moneda_compra,
            "fecha_compra":   r.fecha_compra,
        } for r in rows]
        return pd.DataFrame(data)


def add_tenencia(ticker: str, tipo: str, cantidad: float, precio_compra: float,
                 moneda_compra: str, fecha_compra) -> int:
    with get_session() as s:
        t = Tenencia(
            ticker=ticker.upper().strip(),
            tipo=tipo,
            cantidad=float(cantidad),
            precio_compra=float(precio_compra),
            moneda_compra=moneda_compra,
            fecha_compra=fecha_compra,
        )
        s.add(t)
        s.commit()
        return t.id


def delete_tenencia(id_: int) -> None:
    with get_session() as s:
        obj = s.get(Tenencia, id_)
        if obj:
            s.delete(obj)
            s.commit()


def delete_all_tenencias() -> int:
    """Borra todas las tenencias. Devuelve cuantas habia."""
    with get_session() as s:
        n = s.query(Tenencia).delete()
        s.commit()
        return n


COLUMNAS_CSV = ["ticker", "tipo", "cantidad", "precio_compra",
                "moneda_compra", "fecha_compra"]
TIPOS_VALIDOS = {"accion_ar", "cedear", "accion_us", "etf", "bono", "fci", "cripto"}


def parse_csv_tenencias(df_csv: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Valida un DataFrame con tenencias. Devuelve (df_limpio, lista_de_errores).
    Columnas esperadas: ticker, tipo, cantidad, precio_compra, moneda_compra, fecha_compra
    """
    errores = []
    faltantes = [c for c in COLUMNAS_CSV if c not in df_csv.columns]
    if faltantes:
        errores.append(f"Faltan columnas: {', '.join(faltantes)}")
        return pd.DataFrame(), errores

    df = df_csv[COLUMNAS_CSV].copy()
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df["tipo"] = df["tipo"].astype(str).str.strip().str.lower()
    df["moneda_compra"] = df["moneda_compra"].astype(str).str.strip().str.upper()
    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce")
    df["precio_compra"] = pd.to_numeric(df["precio_compra"], errors="coerce")
    df["fecha_compra"] = pd.to_datetime(df["fecha_compra"], errors="coerce").dt.date

    for i, row in df.iterrows():
        if not row["ticker"]:
            errores.append(f"Fila {i+1}: ticker vacio")
        if row["tipo"] not in TIPOS_VALIDOS:
            errores.append(f"Fila {i+1}: tipo invalido '{row['tipo']}' "
                           f"(validos: {', '.join(sorted(TIPOS_VALIDOS))})")
        if pd.isna(row["cantidad"]) or row["cantidad"] <= 0:
            errores.append(f"Fila {i+1}: cantidad invalida")
        if pd.isna(row["precio_compra"]) or row["precio_compra"] <= 0:
            errores.append(f"Fila {i+1}: precio_compra invalido")
        if row["moneda_compra"] not in ("ARS", "USD"):
            errores.append(f"Fila {i+1}: moneda_compra debe ser ARS o USD")
        if pd.isna(row["fecha_compra"]):
            errores.append(f"Fila {i+1}: fecha_compra invalida (usar YYYY-MM-DD)")

    return df, errores


def bulk_add_tenencias(df: pd.DataFrame) -> int:
    """Inserta varias tenencias. Devuelve cuantas inserto."""
    n = 0
    with get_session() as s:
        for _, r in df.iterrows():
            s.add(Tenencia(
                ticker=r["ticker"],
                tipo=r["tipo"],
                cantidad=float(r["cantidad"]),
                precio_compra=float(r["precio_compra"]),
                moneda_compra=r["moneda_compra"],
                fecha_compra=r["fecha_compra"],
            ))
            n += 1
        s.commit()
    return n


# -----------------------------------------------------------------------------
# VALUACION
# -----------------------------------------------------------------------------
def _moneda_nativa(tipo: str) -> str:
    """Moneda en la que cotiza el ticker en yfinance segun el tipo."""
    if tipo in ("accion_us", "etf", "cripto"):
        return "USD"
    # accion_ar, cedear, bono, fci -> ARS
    return "ARS"


def valuar_tenencias(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Agrega columnas:
      - precio_actual (en moneda nativa)
      - moneda_nativa
      - valor_actual_nativo
      - costo_nativo (cantidad * precio_compra, asumiendo misma moneda)
      - pnl_nativo, pnl_pct
    """
    if df is None:
        df = load_tenencias()
    if df.empty:
        return df

    df = df.copy()
    precios, monedas = [], []
    for _, row in df.iterrows():
        p = get_last_price(row["ticker"], row["tipo"])
        precios.append(p if p is not None else np.nan)
        monedas.append(_moneda_nativa(row["tipo"]))

    df["precio_actual"]       = precios
    df["moneda_nativa"]       = monedas
    df["valor_actual_nativo"] = df["cantidad"] * df["precio_actual"]
    df["costo_nativo"]        = df["cantidad"] * df["precio_compra"]
    df["pnl_nativo"]          = df["valor_actual_nativo"] - df["costo_nativo"]
    df["pnl_pct"]             = np.where(
        df["costo_nativo"] > 0,
        df["pnl_nativo"] / df["costo_nativo"] * 100,
        0.0,
    )
    return df


def agregar_pnl_real(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega columnas de P&L "real" ajustado por inflacion (CER):
      - cer_factor: factor de ajuste desde fecha_compra hasta hoy
      - costo_real_ars: costo nominal ajustado por inflacion
      - pnl_real_ars: valor_actual_ars - costo_real_ars
      - pnl_real_pct: pnl_real_ars / costo_real_ars * 100

    Asume que df ya pasó por convertir_a(..., "ARS").
    Solo aplica CER a tenencias compradas en pesos (moneda_compra == "ARS").
    Para las compradas en USD, costo_real_ars = costo_ars (no se ajusta).
    """
    if df.empty or "costo_ars" not in df.columns:
        return df

    from core.inflation import cer_factor as _cer

    df = df.copy()
    factores = []
    for _, r in df.iterrows():
        fecha = r.get("fecha_compra")
        moneda = r.get("moneda_compra", "ARS")
        if moneda != "ARS" or pd.isna(fecha):
            factores.append(1.0)
            continue
        try:
            f = _cer(fecha)
            factores.append(float(f) if f else 1.0)
        except Exception:
            factores.append(1.0)

    df["cer_factor"]     = factores
    df["costo_real_ars"] = df["costo_ars"] * df["cer_factor"]
    df["pnl_real_ars"]   = df["valor_actual_ars"] - df["costo_real_ars"]
    df["pnl_real_pct"]   = np.where(
        df["costo_real_ars"] > 0,
        df["pnl_real_ars"] / df["costo_real_ars"] * 100,
        0.0,
    )
    return df


def convertir_a(df: pd.DataFrame, moneda_destino: str = "ARS",
                tipo_dolar: str = "mep") -> pd.DataFrame:
    """
    Agrega columnas valor_actual_<moneda_destino> y pnl_<moneda_destino>
    convirtiendo USD<->ARS con la cotizacion elegida.
    moneda_destino: 'ARS' o 'USD'
    tipo_dolar: oficial / mep / ccl / blue (segun dolarapi)
    """
    if df.empty:
        return df

    dolares = get_dolares()
    fx = dolares.get(tipo_dolar, {}).get("venta")
    if fx is None or fx == 0:
        fx = 1.0  # fallback para no romper

    def _conv(row, col_origen):
        val = row[col_origen]
        if pd.isna(val):
            return np.nan
        nat = row["moneda_nativa"]
        if nat == moneda_destino:
            return val
        if nat == "USD" and moneda_destino == "ARS":
            return val * fx
        if nat == "ARS" and moneda_destino == "USD":
            return val / fx
        return val

    sufijo = moneda_destino.lower()
    df = df.copy()
    df[f"valor_actual_{sufijo}"] = df.apply(lambda r: _conv(r, "valor_actual_nativo"), axis=1)
    df[f"costo_{sufijo}"]        = df.apply(lambda r: _conv(r, "costo_nativo"), axis=1)
    df[f"pnl_{sufijo}"]          = df[f"valor_actual_{sufijo}"] - df[f"costo_{sufijo}"]
    return df


# -----------------------------------------------------------------------------
# ALLOCATION
# -----------------------------------------------------------------------------
def allocation_by(df: pd.DataFrame, field: str, valor_col: str = "valor_actual_ars") -> pd.DataFrame:
    """Agrupa por field y suma valor_col. Devuelve DataFrame con columnas [field, valor, peso_pct]."""
    if df.empty or field not in df.columns or valor_col not in df.columns:
        return pd.DataFrame()
    agg = df.groupby(field, dropna=False)[valor_col].sum().reset_index()
    total = agg[valor_col].sum()
    if total > 0:
        agg["peso_pct"] = agg[valor_col] / total * 100
    else:
        agg["peso_pct"] = 0
    return agg.sort_values(valor_col, ascending=False).reset_index(drop=True)


def enriquecer_con_info(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega columnas sector y country pedidos a yfinance.info (puede ser lento)."""
    if df.empty:
        return df
    sectores, paises = [], []
    for tk in df["ticker"]:
        info = get_info(tk)
        sectores.append(info.get("sector") or "Sin dato")
        paises.append(info.get("country") or "Sin dato")
    df = df.copy()
    df["sector"]  = sectores
    df["country"] = paises
    return df


# -----------------------------------------------------------------------------
# EQUITY CURVE
# -----------------------------------------------------------------------------
def equity_curve(df: pd.DataFrame, period: str = "6mo") -> pd.Series:
    """
    Calcula valor diario del portafolio en moneda nativa de cada ticker,
    convertido a ARS usando el tipo de cambio MEP actual (snapshot, no historico).
    Para MVP es aceptable; en bloque 2 se mejora con FX historico.
    """
    if df.empty:
        return pd.Series(dtype=float)

    dolares = get_dolares()
    fx = dolares.get("mep", {}).get("venta") or 1.0

    total: Optional[pd.Series] = None
    for _, row in df.iterrows():
        hist = get_history(row["ticker"], period=period, tipo=row["tipo"])
        if hist.empty:
            continue
        precios = hist["Close"].copy()
        # convertir a ARS si esta en USD
        if _moneda_nativa(row["tipo"]) == "USD":
            precios = precios * fx
        valor = precios * row["cantidad"]
        total = valor if total is None else total.add(valor, fill_value=0)

    if total is None:
        return pd.Series(dtype=float)
    total.index = pd.to_datetime(total.index).tz_localize(None)
    return total.sort_index()
