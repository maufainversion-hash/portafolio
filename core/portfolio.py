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
from core.data import get_last_price, get_history, get_dolares, get_info, get_dolar_historic


# -----------------------------------------------------------------------------
# CARGA
# -----------------------------------------------------------------------------
def _resolve_pid(portfolio_id: Optional[int] = None) -> Optional[int]:
    """Devuelve el portfolio_id explicito o el activo de session_state."""
    if portfolio_id is not None:
        return portfolio_id
    try:
        from core.active_portfolio import get_active_portfolio_id
        return get_active_portfolio_id()
    except Exception:
        return None


def load_tenencias(portfolio_id: Optional[int] = None) -> pd.DataFrame:
    """Devuelve las tenencias del portfolio activo (o explicito). Vacio si no hay."""
    pid = _resolve_pid(portfolio_id)
    with get_session() as s:
        q = s.query(Tenencia)
        if pid is not None:
            q = q.filter(Tenencia.portfolio_id == pid)
        rows = q.all()
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
                 moneda_compra: str, fecha_compra,
                 portfolio_id: Optional[int] = None) -> int:
    pid = _resolve_pid(portfolio_id)
    with get_session() as s:
        t = Tenencia(
            portfolio_id=pid,
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


def delete_all_tenencias(portfolio_id: Optional[int] = None) -> int:
    """Borra todas las tenencias del portfolio activo. Devuelve cuantas habia."""
    pid = _resolve_pid(portfolio_id)
    with get_session() as s:
        q = s.query(Tenencia)
        if pid is not None:
            q = q.filter(Tenencia.portfolio_id == pid)
        n = q.delete()
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


def bulk_add_tenencias(df: pd.DataFrame, portfolio_id: Optional[int] = None) -> int:
    """Inserta varias tenencias en el portfolio activo (o explicito)."""
    pid = _resolve_pid(portfolio_id)
    n = 0
    with get_session() as s:
        for _, r in df.iterrows():
            s.add(Tenencia(
                portfolio_id=pid,
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


# -----------------------------------------------------------------------------
# BENCHMARKS NORMALIZADOS
# -----------------------------------------------------------------------------
def benchmark_curves(period: str = "6mo") -> pd.DataFrame:
    """
    Devuelve un DataFrame con curvas DIARIAS normalizadas a 100 al inicio para:
      - Portfolio (usando equity_curve)
      - Merval (^MERV en ARS)
      - SPY en ARS (SPY USD * MEP histórico)
      - USD MEP (buy & hold)
      - Inflación CER (interpolación lineal del IPC mensual)

    Índice = fechas comunes (intersección). Columnas faltantes quedan NaN.
    """
    from core.inflation import _serie_indexada
    from datetime import date, timedelta

    # 1) Portfolio
    df_tenencias = load_tenencias()
    if df_tenencias.empty:
        return pd.DataFrame()
    port_curve = equity_curve(df_tenencias, period=period)
    if port_curve.empty:
        return pd.DataFrame()

    fecha_desde = port_curve.index[0]
    fecha_hasta = port_curve.index[-1]

    # 2) Merval
    merv_hist = get_history("^MERV", period="1y")
    merv = pd.Series(dtype=float)
    if not merv_hist.empty:
        merv_hist.index = pd.to_datetime(merv_hist.index).tz_localize(None)
        merv = merv_hist.loc[
            (merv_hist.index >= fecha_desde) & (merv_hist.index <= fecha_hasta),
            "Close",
        ]

    # 3) SPY en ARS (precio SPY USD * MEP del día)
    spy_hist = get_history("SPY", period="1y")
    mep_df = get_dolar_historic("mep")
    spy_ars = pd.Series(dtype=float)
    if not spy_hist.empty and not mep_df.empty:
        spy_hist.index = pd.to_datetime(spy_hist.index).tz_localize(None)
        spy = spy_hist.loc[
            (spy_hist.index >= fecha_desde) & (spy_hist.index <= fecha_hasta),
            "Close",
        ]
        mep_filt = mep_df[(mep_df["fecha"] >= fecha_desde)
                          & (mep_df["fecha"] <= fecha_hasta)].copy()
        if not mep_filt.empty and not spy.empty:
            mep_filt = mep_filt.set_index("fecha")["venta"]
            # Reindex MEP a las mismas fechas que SPY, forward-fill para los gaps
            mep_aligned = mep_filt.reindex(spy.index).ffill().bfill()
            spy_ars = spy * mep_aligned

    # 4) USD MEP buy & hold
    usd_mep = pd.Series(dtype=float)
    if not mep_df.empty:
        mep_filt = mep_df[(mep_df["fecha"] >= fecha_desde)
                          & (mep_df["fecha"] <= fecha_hasta)].copy()
        if not mep_filt.empty:
            usd_mep = mep_filt.set_index("fecha")["venta"]

    # 5) Inflacion acumulada (mensual interpolada a diario)
    inflacion = pd.Series(dtype=float)
    try:
        infl_serie = _serie_indexada()
        if not infl_serie.empty:
            # Cumulativo: cada mes vale (1 + ipc/100) acumulado desde el inicio
            infl_filt = infl_serie[
                (infl_serie["fecha"] >= fecha_desde - pd.Timedelta(days=31))
                & (infl_serie["fecha"] <= fecha_hasta)
            ].copy()
            if not infl_filt.empty:
                infl_filt = infl_filt.set_index("fecha")
                infl_filt["factor"] = (infl_filt["valor"] / 100 + 1).cumprod()
                # Index diario para interpolacion
                full_idx = pd.date_range(start=fecha_desde, end=fecha_hasta, freq="D")
                infl_daily = infl_filt["factor"].reindex(
                    infl_filt.index.union(full_idx)).interpolate(method="time").reindex(full_idx).ffill().bfill()
                # Re-normalizar a 1.0 al inicio
                if not infl_daily.empty and infl_daily.iloc[0] > 0:
                    inflacion = infl_daily / infl_daily.iloc[0]
    except Exception:
        pass

    # 6) Armar DataFrame normalizado (base 100 al inicio de cada serie)
    def _norm(s: pd.Series) -> pd.Series:
        if s.empty or pd.isna(s.iloc[0]) or s.iloc[0] == 0:
            return s
        return s / s.iloc[0] * 100

    out = pd.DataFrame({
        "Portfolio":   _norm(port_curve),
        "Merval":      _norm(merv),
        "SPY (ARS)":   _norm(spy_ars),
        "USD MEP":     _norm(usd_mep),
        "Inflación":   inflacion * 100 if not inflacion.empty else inflacion,
    })
    # Indice unico (deduplicar fechas)
    out = out.loc[~out.index.duplicated(keep="first")]
    return out.sort_index()
