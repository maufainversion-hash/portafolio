"""
Genera graficos PNG con matplotlib para embeber en el PDF de reportes.

Diseño:
- Fondo blanco / texto oscuro (mejor para impresion).
- Paleta consistente con el branding (esmeralda + colores categoricos).
- Tamaños pensados para A4 con margenes (~ 17cm de ancho util).

Cada funcion devuelve bytes (PNG) listos para embeber con fpdf2 via
pdf.image(data=bytes_or_buf, ...).
"""
from __future__ import annotations
import io
from typing import Optional
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # sin display
import matplotlib.pyplot as plt
import numpy as np


# Paleta (mismo branding que la app)
COLOR_PORTFOLIO = "#10b981"   # esmeralda mas saturado para impresion
COLOR_DARK      = "#0d1220"
COLOR_TEXT      = "#1f2937"
COLOR_DIM       = "#6b7280"
PALETA_CAT = [
    "#10b981",  # esmeralda
    "#2dd4bf",  # teal
    "#06b6d4",  # cyan
    "#3b82f6",  # azul
    "#8b5cf6",  # violeta
    "#ec4899",  # rosa
    "#f59e0b",  # ambar
    "#ef4444",  # rojo
]


def _setup_style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.facecolor":   "white",
        "figure.facecolor": "white",
        "axes.edgecolor":   COLOR_DIM,
        "axes.labelcolor":  COLOR_TEXT,
        "xtick.color":      COLOR_DIM,
        "ytick.color":      COLOR_DIM,
        "axes.grid":        True,
        "grid.color":       "#e5e7eb",
        "grid.linestyle":   "--",
        "grid.linewidth":   0.5,
        "axes.spines.top":   False,
        "axes.spines.right": False,
    })


def _fig_to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def chart_equity_curve(curve: pd.Series, titulo: str = "Evolución de tu cartera") -> Optional[bytes]:
    """Linea de la equity curve en ARS."""
    if curve is None or curve.empty:
        return None
    _setup_style()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(curve.index, curve.values, color=COLOR_PORTFOLIO, linewidth=2.2)
    ax.fill_between(curve.index, curve.values, alpha=0.12, color=COLOR_PORTFOLIO)
    ax.set_title(titulo, fontsize=13, fontweight="bold", color=COLOR_DARK,
                 loc="left", pad=14)
    ax.set_xlabel("")
    ax.set_ylabel("Valor en ARS")
    # Formato del eje Y como miles/millones
    def _fmt(y, _pos):
        if abs(y) >= 1e6:
            return f"${y/1e6:.1f}M"
        if abs(y) >= 1e3:
            return f"${y/1e3:.0f}K"
        return f"${y:.0f}"
    from matplotlib.ticker import FuncFormatter
    ax.yaxis.set_major_formatter(FuncFormatter(_fmt))
    # Anotacion del inicio y fin
    v0, vf = float(curve.iloc[0]), float(curve.iloc[-1])
    ret_pct = (vf / v0 - 1) * 100
    color_ret = COLOR_PORTFOLIO if ret_pct >= 0 else "#ef4444"
    ax.annotate(
        f"{ret_pct:+.2f}%",
        xy=(curve.index[-1], vf),
        xytext=(8, 0), textcoords="offset points",
        fontsize=11, fontweight="bold", color=color_ret,
        va="center",
    )
    fig.tight_layout()
    return _fig_to_png(fig)


def chart_allocation_donut(positions: list,
                           titulo: str = "Composición por tipo de activo") -> Optional[bytes]:
    """Donut de allocation por tipo. positions = list[dict] con tipo y valor_actual_ars."""
    if not positions:
        return None
    df = pd.DataFrame(positions)
    if "tipo" not in df.columns or "valor_actual_ars" not in df.columns:
        return None
    agg = df.groupby("tipo")["valor_actual_ars"].sum().sort_values(ascending=False)
    if agg.empty or agg.sum() <= 0:
        return None

    labels_map = {
        "accion_ar": "Acciones AR", "cedear": "Cedears",
        "accion_us": "Acciones US", "etf": "ETFs",
        "bono": "Bonos", "fci": "FCIs", "cripto": "Cripto",
    }
    labels = [labels_map.get(k, k) for k in agg.index]
    sizes = agg.values
    colors = PALETA_CAT[:len(labels)]

    _setup_style()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=None, colors=colors,
        autopct=lambda p: f"{p:.1f}%" if p > 3 else "",
        startangle=90, pctdistance=0.78,
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2),
        textprops=dict(color="white", fontsize=10, fontweight="bold"),
    )
    ax.set_title(titulo, fontsize=13, fontweight="bold", color=COLOR_DARK,
                 loc="left", pad=14)
    ax.legend(wedges, [f"{l} ({s/sizes.sum()*100:.1f}%)" for l, s in zip(labels, sizes)],
              loc="center left", bbox_to_anchor=(1.02, 0.5),
              frameon=False, fontsize=10, labelcolor=COLOR_TEXT)
    # Valor total en el centro
    total = sizes.sum()
    txt = f"${total/1e6:.2f}M" if total >= 1e6 else f"${total/1e3:.0f}K"
    ax.text(0, 0, txt, ha="center", va="center",
            fontsize=14, fontweight="bold", color=COLOR_DARK)
    fig.tight_layout()
    return _fig_to_png(fig)


def chart_vs_benchmarks(benchmarks: dict,
                        titulo: str = "Tu cartera vs alternativas pasivas") -> Optional[bytes]:
    """Bar horizontal: portfolio + cada benchmark."""
    if not benchmarks:
        return None
    portfolio_pct = benchmarks.get("portfolio_retorno_pct")
    comp = benchmarks.get("comparativas", {})
    if portfolio_pct is None or not comp:
        return None

    rows = [("Tu portfolio", portfolio_pct)]
    label_map = {
        "merval_ars_pct":       "Merval (ARS)",
        "spy_en_ars_pct":       "S&P 500 (en ARS)",
        "usd_mep_buyhold_pct":  "USD MEP (buy & hold)",
        "inflacion_acumulada_pct": "Inflación (CER)",
    }
    for k, label in label_map.items():
        if k in comp and comp[k] is not None:
            rows.append((label, comp[k]))

    labels = [r[0] for r in rows]
    values = [r[1] for r in rows]
    colors = [COLOR_PORTFOLIO if i == 0 else
              ("#fb7185" if v < 0 else "#94a3b8") for i, v in enumerate(values)]
    # Si es inflacion, color especifico
    for i, l in enumerate(labels):
        if "Inflación" in l:
            colors[i] = "#f59e0b"

    _setup_style()
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.barh(labels, values, color=colors, edgecolor="white", linewidth=1.5)
    ax.axvline(0, color=COLOR_DIM, linewidth=0.8)
    ax.set_title(titulo, fontsize=13, fontweight="bold", color=COLOR_DARK,
                 loc="left", pad=14)
    ax.set_xlabel("Retorno del período (%)")
    ax.invert_yaxis()  # Portfolio arriba
    # Anotaciones de los valores al final de cada barra
    max_abs = max(abs(v) for v in values) if values else 1
    for bar, v in zip(bars, values):
        x = bar.get_width()
        offset = max_abs * 0.02 * (1 if x >= 0 else -1)
        ax.text(x + offset, bar.get_y() + bar.get_height() / 2,
                f"{v:+.2f}%", va="center",
                ha="left" if x >= 0 else "right",
                fontsize=10, fontweight="bold",
                color=COLOR_DARK)
    # Espacio extra para los labels
    ax.set_xlim(min(values) - max_abs * 0.15,
                max(values) + max_abs * 0.18)
    fig.tight_layout()
    return _fig_to_png(fig)


def build_all_charts(context: dict) -> dict:
    """Genera todos los charts disponibles a partir del context JSON.
    Devuelve dict {nombre: bytes_png}."""
    out = {}
    try:
        from core.portfolio import (
            load_tenencias, valuar_tenencias, convertir_a, equity_curve,
        )
        df = load_tenencias()
        curve = equity_curve(df, period="6mo")
        png = chart_equity_curve(curve)
        if png:
            out["equity"] = png
    except Exception:
        pass

    positions = context.get("positions") or []
    png = chart_allocation_donut(positions)
    if png:
        out["allocation"] = png

    bm = context.get("benchmarks")
    if bm:
        png = chart_vs_benchmarks(bm)
        if png:
            out["benchmarks"] = png

    return out
