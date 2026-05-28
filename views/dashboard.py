"""
Dashboard principal: KPIs, equity curve, donut de allocation y tabla de posiciones.
Incluye formulario para agregar nuevas tenencias.
"""
from datetime import date
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.portfolio import (
    load_tenencias, valuar_tenencias, convertir_a, equity_curve,
    add_tenencia, delete_tenencia,
)
from core.data import get_dolares
from core.ui import fmt_money, fmt_pct, kpi_card, kpi_row, style_fig


def _fmt_money(v: float, simbolo: str = "$") -> str:
    if pd.isna(v) or v is None:
        return "—"
    return f"{simbolo} {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(v: float) -> str:
    if pd.isna(v) or v is None:
        return "—"
    return f"{v:+.2f}%"


def render():
    st.subheader("Dashboard")

    df = load_tenencias()
    if df.empty:
        st.info("No tenes tenencias cargadas. Agrega una desde el formulario de abajo.")
        _formulario_alta(expanded=True)
        return

    with st.spinner("Trayendo precios..."):
        df_val = valuar_tenencias(df)
        df_val = convertir_a(df_val, "ARS", tipo_dolar="mep")
        df_val = convertir_a(df_val, "USD", tipo_dolar="mep")

    # P&L se calcula SOLO sobre posiciones con precio valido,
    # para no contar como perdida total las que no se pudieron valuar.
    validos = df_val[df_val["precio_actual"].notna()].copy()
    sin_precio = len(df_val) - len(validos)

    valor_ars = validos["valor_actual_ars"].sum()
    valor_usd = validos["valor_actual_usd"].sum()
    costo_ars = validos["costo_ars"].sum()
    pnl_ars   = valor_ars - costo_ars
    pnl_pct   = (pnl_ars / costo_ars * 100) if costo_ars else 0

    if sin_precio > 0:
        st.warning(
            f"⚠️ {sin_precio} de {len(df_val)} posiciones sin precio actual "
            "(Yahoo puede estar limitando el acceso). El P&L se calcula sobre las valuadas."
        )

    # KPIs premium (HTML cards)
    kpi_row([
        kpi_card("Valor total (ARS)", fmt_money(valor_ars, "$")),
        kpi_card("Valor total (USD MEP)", fmt_money(valor_usd, "US$")),
        kpi_card("P&L total (ARS)", fmt_money(pnl_ars, "$"),
                 delta=fmt_pct(pnl_pct), positive=(pnl_ars >= 0)),
        kpi_card("Posiciones valuadas", f"{len(validos)} / {len(df_val)}"),
    ])

    st.divider()

    # Equity curve + Donut
    col_chart, col_donut = st.columns([2, 1])
    with col_chart:
        st.markdown("**Equity curve (6 meses, ARS)**")
        with st.spinner("Calculando equity curve..."):
            curve = equity_curve(df, period="6mo")
        if curve.empty:
            st.warning("No se pudo calcular la equity curve (sin datos historicos).")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=curve.index, y=curve.values,
                mode="lines", line=dict(color="#22c55e", width=2),
                fill="tozeroy", fillcolor="rgba(34,197,94,0.10)",
                name="Valor",
            ))
            style_fig(fig, height=320)
            st.plotly_chart(fig, use_container_width=True)

    with col_donut:
        st.markdown("**Allocation por tipo**")
        agg = df_val.groupby("tipo")["valor_actual_ars"].sum().reset_index()
        if not agg.empty and agg["valor_actual_ars"].sum() > 0:
            fig = px.pie(agg, names="tipo", values="valor_actual_ars", hole=0.62,
                         color_discrete_sequence=["#34d399","#2dd4bf","#22d3ee","#60a5fa","#a78bfa","#f472b6","#fbbf24"])
            fig.update_traces(textposition="outside", textinfo="percent")
            style_fig(fig, height=320)
            fig.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.08))
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Tabla de posiciones custom (HTML premium)
    st.markdown("**Posiciones**")
    filas = ""
    for _, r in df_val.iterrows():
        pnl = r.get("pnl_ars")
        pnl_p = r.get("pnl_pct")
        cls = "pnl-pos" if (pd.notna(pnl) and pnl >= 0) else "pnl-neg"
        filas += (
            "<tr>"
            f"<td><span class='tk-badge'>{r['ticker']}</span>"
            f"<span class='tk-tipo'>{r['tipo']}</span></td>"
            f"<td>{r['cantidad']:.4f}</td>"
            f"<td>{fmt_money(r.get('precio_actual'))}</td>"
            f"<td>{fmt_money(r.get('valor_actual_ars'))}</td>"
            f"<td class='{cls}'>{fmt_money(pnl)}</td>"
            f"<td class='{cls}'>{fmt_pct(pnl_p)}</td>"
            "</tr>"
        )
    st.markdown(
        "<table class='pos-table'><thead><tr>"
        "<th>Activo</th><th>Cantidad</th><th>P. actual</th>"
        "<th>Valor (ARS)</th><th>P&L (ARS)</th><th>P&L %</th>"
        "</tr></thead><tbody>" + filas + "</tbody></table>",
        unsafe_allow_html=True,
    )

    # Eliminar tenencia
    with st.expander("Eliminar tenencia"):
        ids = df_val["id"].tolist()
        labels = [f"{r['ticker']} ({r['tipo']}) — id {r['id']}" for _, r in df_val.iterrows()]
        if ids:
            elegido = st.selectbox("Tenencia a eliminar", options=ids,
                                   format_func=lambda i: labels[ids.index(i)])
            if st.button("Eliminar", type="primary"):
                delete_tenencia(int(elegido))
                st.success("Tenencia eliminada.")
                st.rerun()

    _formulario_alta()


def _formulario_alta(expanded: bool = False):
    with st.expander("➕ Agregar tenencia", expanded=expanded):
        with st.form("alta_tenencia", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                ticker = st.text_input("Ticker (ej: GGAL.BA, AAPL, BTC-USD)").strip()
                tipo = st.selectbox("Tipo", options=[
                    "accion_ar", "cedear", "accion_us", "etf", "bono", "fci", "cripto",
                ])
                cantidad = st.number_input("Cantidad", min_value=0.0, value=1.0, step=1.0, format="%.6f")
            with c2:
                precio = st.number_input("Precio de compra", min_value=0.0, value=0.0, format="%.2f")
                moneda = st.selectbox("Moneda compra", options=["ARS", "USD"])
                fecha = st.date_input("Fecha de compra", value=date.today())
            ok = st.form_submit_button("Agregar", type="primary", use_container_width=True)
            if ok:
                if not ticker or cantidad <= 0 or precio <= 0:
                    st.error("Completa ticker, cantidad y precio.")
                else:
                    add_tenencia(ticker, tipo, cantidad, precio, moneda, fecha)
                    st.success(f"Tenencia {ticker} agregada.")
                    st.rerun()
