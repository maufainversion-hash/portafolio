"""
Vista Contexto AR: cotizaciones de dolar (oficial / MEP / CCL / blue / cripto / mayorista),
brecha cambiaria, riesgo pais, Merval, inflacion historica (mensual, YTD, interanual).
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.data import (
    get_dolares, get_riesgo_pais, get_inflacion_mensual,
    get_merval, get_history,
)
from core.ui import style_fig, fmt_money, kpi_card, kpi_row


def render():
    st.subheader("Contexto Argentino")

    # ---------- DOLAR ----------
    dolares = get_dolares()
    if not dolares:
        st.error("No se pudo obtener cotizaciones de dolar.")
    else:
        _bloque_dolar(dolares)

    st.divider()

    # ---------- RIESGO PAIS + MERVAL ----------
    _bloque_riesgo_merval()

    st.divider()

    # ---------- MERVAL HISTORICO ----------
    st.markdown("**Merval — ultimos 6 meses**")
    hist = get_history("^MERV", period="6mo")
    if hist.empty:
        st.info("No se pudo cargar el historico del Merval.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist.index, y=hist["Close"], mode="lines",
            line=dict(color="#34d399", width=2),
            fill="tozeroy", fillcolor="rgba(52,211,153,0.10)",
            name="Merval",
        ))
        style_fig(fig, height=300)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---------- INFLACION ----------
    _bloque_inflacion()


# -----------------------------------------------------------------------------
def _bloque_dolar(dolares: dict):
    """Cards premium por tipo de dolar + brecha vs oficial."""
    st.markdown("**Cotizaciones del dolar**")

    # 6 tipos en 2 filas de 3 (o 1 fila de 6 segun ancho)
    casas = [
        ("oficial",        "Oficial"),
        ("mayorista",      "Mayorista"),
        ("blue",           "Blue"),
        ("mep",            "MEP (Bolsa)"),
        ("contadoconliqui","CCL"),
        ("cripto",         "Cripto"),
    ]
    cards = []
    for casa, label in casas:
        d = dolares.get(casa, {})
        venta = d.get("venta")
        cards.append(kpi_card(label, fmt_money(venta) if venta else "—"))

    # Render en grid 6 columnas via CSS inline (override del grid de 4)
    st.markdown(
        f'<div class="kpi-grid" style="grid-template-columns:repeat(6,1fr);">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )

    # Brecha vs oficial — pill style
    oficial = dolares.get("oficial", {}).get("venta")
    if not oficial:
        return
    st.markdown("<div style='margin-top:.8rem;color:#8b96a8;font-size:.85rem;'>"
                "Brecha cambiaria vs oficial:</div>", unsafe_allow_html=True)
    pills = []
    for casa, label in [("blue","Blue"), ("mep","MEP"),
                        ("contadoconliqui","CCL"), ("cripto","Cripto")]:
        v = dolares.get(casa, {}).get("venta")
        if not v:
            continue
        brecha = (v / oficial - 1) * 100
        cls = "kpi-delta pos" if brecha >= 0 else "kpi-delta neg"
        arrow = "▲" if brecha >= 0 else "▼"
        pills.append(
            f'<span class="{cls}" style="margin:0 .3rem;font-size:.82rem;">'
            f'<b style="color:var(--text);font-weight:600;">{label}</b> '
            f'{arrow} {brecha:+.2f}%</span>'
        )
    st.markdown(
        f"<div style='margin-top:.4rem;'>{''.join(pills)}</div>",
        unsafe_allow_html=True,
    )


def _bloque_riesgo_merval():
    rp = get_riesgo_pais()
    mv = get_merval()

    # Sparkline 6m del Merval
    hist = get_history("^MERV", period="6mo")
    mv_var = None
    if not hist.empty and len(hist) > 5:
        mv_var = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100

    cards = [
        kpi_card("Riesgo pais (EMBI)", f"{rp:,.0f} pb" if rp else "—"),
        kpi_card(
            "Merval (^MERV)",
            f"{mv:,.0f}" if mv else "—",
            delta=(f"{mv_var:+.2f}% 6m" if mv_var is not None else None),
            positive=(mv_var is not None and mv_var >= 0),
        ),
    ]
    st.markdown(
        f'<div class="kpi-grid" style="grid-template-columns:repeat(2,1fr);">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def _bloque_inflacion():
    infl = get_inflacion_mensual()
    if infl.empty:
        st.info("No se pudo cargar la serie de inflacion.")
        return

    df = infl.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.sort_values("fecha")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")

    # Metricas: ultimo, acumulado YTD, interanual (12 meses)
    ultimo = df.iloc[-1]
    ultimo_v = float(ultimo["valor"]) if pd.notna(ultimo["valor"]) else None

    anio_actual = ultimo["fecha"].year
    ytd_df = df[df["fecha"].dt.year == anio_actual]
    ytd_acum = (((ytd_df["valor"] / 100 + 1).prod() - 1) * 100) if not ytd_df.empty else None

    ult12 = df.tail(12)
    interanual = (((ult12["valor"] / 100 + 1).prod() - 1) * 100) if len(ult12) >= 12 else None

    fecha_label = ultimo["fecha"].strftime("%b %Y").capitalize()

    cards = [
        kpi_card(f"Inflacion {fecha_label}",
                 f"{ultimo_v:.2f}%" if ultimo_v is not None else "—"),
        kpi_card(f"Acumulado YTD {anio_actual}",
                 f"{ytd_acum:.2f}%" if ytd_acum is not None else "—"),
        kpi_card("Interanual (12m)",
                 f"{interanual:.2f}%" if interanual is not None else "—"),
    ]
    st.markdown(
        f'<div class="kpi-grid" style="grid-template-columns:repeat(3,1fr);">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("**Inflacion mensual (INDEC) — ultimos 24 meses**")
    ultimos = df.tail(24).copy()
    ultimos["acum"] = ((ultimos["valor"] / 100 + 1).cumprod() - 1) * 100

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=ultimos["fecha"], y=ultimos["valor"],
        marker_color="#f59e0b", name="Mensual",
        hovertemplate="<b>%{x|%b %Y}</b><br>%{y:.2f}% mensual<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=ultimos["fecha"], y=ultimos["acum"],
        mode="lines+markers", name="Acumulado 24m",
        line=dict(color="#fb7185", width=2),
        marker=dict(size=5),
        yaxis="y2",
        hovertemplate="<b>%{x|%b %Y}</b><br>Acum 24m: %{y:.2f}%<extra></extra>",
    ))
    style_fig(fig, height=340)
    fig.update_layout(
        yaxis=dict(title="% mensual"),
        yaxis2=dict(title="% acumulado", overlaying="y", side="right",
                    gridcolor="rgba(255,255,255,0)"),
        legend=dict(orientation="h", y=-0.18),
    )
    st.plotly_chart(fig, use_container_width=True)
