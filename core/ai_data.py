"""
Builder del JSON de contexto que se pasa a Gemini.

Centraliza TODO lo que la app ya calcula:
- Portfolio summary
- Positions
- Performance metrics
- Risk metrics
- Concentration / diversification
- Macro AR
- Benchmark snapshot

Si una metrica no se puede calcular, la dejamos como null y el system prompt
le indica al LLM que en ese caso declare "dato no disponible".
"""
from __future__ import annotations
from datetime import date
import numpy as np
import pandas as pd

from core.portfolio import (
    load_tenencias, valuar_tenencias, convertir_a, equity_curve,
    agregar_pnl_real,
)
from core.metrics import (
    returns_from_prices, volatility, sharpe, sortino, cagr,
    max_drawdown, var_historic,
)
from core.data import get_dolares, get_riesgo_pais, get_inflacion_mensual, get_merval


def _safe(value, default=None):
    """Convierte NaN / None / inf en default JSON-safe."""
    if value is None:
        return default
    try:
        if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
            return default
        if hasattr(value, "item"):
            value = value.item()
        return value
    except Exception:
        return default


def build_portfolio_context() -> dict:
    """
    Construye el JSON de contexto completo. Si hay algo que falla, se devuelve
    null en ese campo (no lanzamos excepcion para que el LLM siga andando).
    """
    out: dict = {
        "generated_at": str(date.today()),
        "portfolio": None,
        "positions": [],
        "metrics": None,
        "risk_metrics": None,
        "concentration": None,
        "macro_ar": None,
        "benchmark": None,
        "notes": [],
    }

    # Tenencias + valuacion
    df = load_tenencias()
    if df.empty:
        out["notes"].append("El usuario no tiene tenencias cargadas.")
        return out

    df_val = valuar_tenencias(df)
    df_val = convertir_a(df_val, "ARS", tipo_dolar="mep")
    df_val = convertir_a(df_val, "USD", tipo_dolar="mep")
    df_val = agregar_pnl_real(df_val)
    df_val = df_val[df_val["valor_actual_ars"].notna()
                    & (df_val["valor_actual_ars"] > 0)].copy()

    if df_val.empty:
        out["notes"].append("Ninguna posicion tiene precio actual disponible.")
        return out

    total_ars = float(df_val["valor_actual_ars"].sum())
    total_usd = float(df_val["valor_actual_usd"].sum())
    costo_ars = float(df_val["costo_ars"].sum())
    costo_real_ars = float(df_val["costo_real_ars"].sum())
    pnl_ars = total_ars - costo_ars
    pnl_pct = (pnl_ars / costo_ars * 100) if costo_ars else 0
    pnl_real_ars = total_ars - costo_real_ars
    pnl_real_pct = (pnl_real_ars / costo_real_ars * 100) if costo_real_ars else 0

    out["portfolio"] = {
        "moneda_base":     "ARS",
        "valor_total_ars": _safe(total_ars),
        "valor_total_usd_mep": _safe(total_usd),
        "costo_ars":       _safe(costo_ars),
        "costo_real_ars":  _safe(costo_real_ars),
        "pnl_nominal_ars": _safe(pnl_ars),
        "pnl_nominal_pct": _safe(pnl_pct),
        "pnl_real_ars":    _safe(pnl_real_ars),
        "pnl_real_pct":    _safe(pnl_real_pct),
        "n_posiciones":    int(len(df_val)),
        "tipos_presentes": sorted(df_val["tipo"].unique().tolist()),
    }

    # Posiciones individuales
    for _, r in df_val.iterrows():
        out["positions"].append({
            "ticker":            r["ticker"],
            "tipo":              r["tipo"],
            "cantidad":          _safe(r["cantidad"]),
            "precio_compra":     _safe(r["precio_compra"]),
            "moneda_compra":     r.get("moneda_compra"),
            "fecha_compra":      str(r.get("fecha_compra")),
            "precio_actual":     _safe(r["precio_actual"]),
            "moneda_nativa":     r.get("moneda_nativa"),
            "valor_actual_ars":  _safe(r["valor_actual_ars"]),
            "peso_pct":          _safe(r["valor_actual_ars"] / total_ars * 100),
            "pnl_ars":           _safe(r.get("pnl_ars")),
            "pnl_pct":           _safe(r.get("pnl_pct")),
            "pnl_real_pct":      _safe(r.get("pnl_real_pct")),
            "cer_factor":        _safe(r.get("cer_factor")),
        })

    # Equity curve + metricas (CAGR, vol, sharpe, sortino, MaxDD, VaR)
    curve = equity_curve(df, period="6mo")
    if not curve.empty and len(curve) > 5:
        rets = returns_from_prices(curve)
        out["metrics"] = {
            "equity_curve_dias":  int(len(curve)),
            "equity_curve_desde": str(curve.index[0].date()),
            "equity_curve_hasta": str(curve.index[-1].date()),
            "valor_inicial_ars":  _safe(float(curve.iloc[0])),
            "valor_final_ars":    _safe(float(curve.iloc[-1])),
            "retorno_periodo_pct": _safe((float(curve.iloc[-1]) / float(curve.iloc[0]) - 1) * 100),
            "cagr_pct":           _safe(cagr(curve) * 100),
            "volatilidad_anual_pct": _safe(volatility(rets, annualize=True) * 100),
            "sharpe":             _safe(sharpe(rets)),
            "sortino":            _safe(sortino(rets)),
            "var_95_pct":         _safe(var_historic(rets, alpha=0.05) * 100),
            "max_drawdown_pct":   _safe(max_drawdown(curve) * 100),
        }

        # Risk metrics adicionales
        dd_actual = (curve.iloc[-1] / curve.cummax().iloc[-1] - 1) * 100
        out["risk_metrics"] = {
            "drawdown_actual_pct": _safe(float(dd_actual)),
            "dias_en_drawdown":    _safe(int((curve < curve.cummax()).sum())),
            "skew":                _safe(float(rets.skew())) if len(rets) > 3 else None,
            "kurtosis":            _safe(float(rets.kurtosis())) if len(rets) > 3 else None,
            "peor_dia_pct":        _safe(float(rets.min()) * 100) if not rets.empty else None,
            "mejor_dia_pct":       _safe(float(rets.max()) * 100) if not rets.empty else None,
            "dias_positivos_pct":  _safe(float((rets > 0).sum() / len(rets) * 100)) if len(rets) else None,
        }
    else:
        out["notes"].append("Equity curve insuficiente: no se calcularon CAGR, Sharpe, Sortino, MaxDD ni VaR.")

    # Concentracion y diversificacion
    df_val["peso_pct"] = df_val["valor_actual_ars"] / total_ars * 100
    top5_share = df_val.nlargest(5, "valor_actual_ars")["peso_pct"].sum()
    top1_share = float(df_val["peso_pct"].max())
    by_tipo = (df_val.groupby("tipo")["valor_actual_ars"].sum() / total_ars * 100).to_dict()
    by_moneda_nativa = (df_val.groupby("moneda_nativa")["valor_actual_ars"].sum() / total_ars * 100).to_dict()
    hhi = float((df_val["peso_pct"] ** 2).sum())  # 0-10000
    out["concentration"] = {
        "top_1_holding_pct": _safe(top1_share),
        "top_5_holdings_pct": _safe(float(top5_share)),
        "hhi_index":         _safe(hhi),
        "hhi_label":         ("alta" if hhi > 2500 else "media" if hhi > 1500 else "baja"),
        "exposure_by_tipo":  {k: round(v, 2) for k, v in by_tipo.items()},
        "exposure_by_moneda_nativa": {k: round(v, 2) for k, v in by_moneda_nativa.items()},
    }

    # Macro AR
    dolares = get_dolares() or {}
    macro = {}
    for casa, label in [("oficial","oficial"), ("mep","mep"),
                        ("contadoconliqui","ccl"), ("blue","blue"),
                        ("cripto","cripto"), ("mayorista","mayorista")]:
        v = dolares.get(casa, {}).get("venta")
        if v:
            macro[f"dolar_{label}_venta"] = float(v)
    oficial = dolares.get("oficial", {}).get("venta")
    if oficial:
        for casa, label in [("mep","mep"), ("contadoconliqui","ccl"),
                            ("blue","blue"), ("cripto","cripto")]:
            v = dolares.get(casa, {}).get("venta")
            if v:
                macro[f"brecha_{label}_pct"] = round((v / oficial - 1) * 100, 2)

    rp = get_riesgo_pais()
    if rp:
        macro["riesgo_pais_pb"] = float(rp)
    mv = get_merval()
    if mv:
        macro["merval_close"] = float(mv)

    infl = get_inflacion_mensual()
    if not infl.empty:
        infl = infl.copy()
        infl["fecha"] = pd.to_datetime(infl["fecha"])
        infl = infl.sort_values("fecha")
        ultimo = infl.iloc[-1]
        macro["inflacion_ultimo_mes_pct"] = float(ultimo["valor"])
        macro["inflacion_ultimo_mes_fecha"] = ultimo["fecha"].strftime("%Y-%m")
        anio = ultimo["fecha"].year
        ytd = infl[infl["fecha"].dt.year == anio]
        macro["inflacion_ytd_acumulada_pct"] = round(
            float(((ytd["valor"] / 100 + 1).prod() - 1) * 100), 2)
        ult12 = infl.tail(12)
        if len(ult12) >= 12:
            macro["inflacion_interanual_pct"] = round(
                float(((ult12["valor"] / 100 + 1).prod() - 1) * 100), 2)

    out["macro_ar"] = macro or None

    return out
