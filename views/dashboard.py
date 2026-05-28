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
        st.info("No tenes tenencias cargadas. Agrega una desde el formulario lateral.")
        _formulario_alta()
        return

    with st.spinner("Trayendo precios..."):
        df_val = valuar_tenencias(df)
        df_val = convertir_a(df_val, "ARS", tipo_dolar="mep")
        df_val = convertir_a(df_val, "USD", tipo_dolar="mep")

    valor_ars = df_val["valor_actual_ars"].sum()
    valor_usd = df_val["valor_actual_usd"].sum()
    costo_ars = df_val["costo_ars"].sum()
    pnl_ars   = valor_ars - costo_ars
    pnl_pct   = (pnl_ars / costo_ars * 100) if costo_ars else 0

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valor total (ARS)", _fmt_money(valor_ars, "$"))
    c2.metric("Valor total (USD MEP)", _fmt_money(valor_usd, "US$"))
    c3.metric("P&L total (ARS)", _fmt_money(pnl_ars, "$"), _fmt_pct(pnl_pct))
    c4.metric("Posiciones", f"{len(df_val)}")

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
            fig.update_layout(
                height=320, margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(gridcolor="#1f2937"), yaxis=dict(gridcolor="#1f2937"),
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_donut:
        st.markdown("**Allocation por tipo**")
        agg = df_val.groupby("tipo")["valor_actual_ars"].sum().reset_index()
        if not agg.empty and agg["valor_actual_ars"].sum() > 0:
            fig = px.pie(agg, names="tipo", values="valor_actual_ars",
                         hole=0.55, color_discrete_sequence=px.colors.sequential.Greens_r)
            fig.update_layout(
                height=320, margin=dict(l=10, r=10, t=10, b=10),
                showlegend=True, legend=dict(orientation="h", y=-0.05),
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Tabla de posiciones
    st.markdown("**Posiciones**")
    cols_show = [
        "ticker", "tipo", "cantidad", "precio_compra", "precio_actual",
        "valor_actual_ars", "pnl_ars", "pnl_pct",
    ]
    tabla = df_val[cols_show].copy()
    tabla = tabla.rename(columns={
        "ticker": "Ticker", "tipo": "Tipo", "cantidad": "Cant.",
        "precio_compra": "P. compra", "precio_actual": "P. actual",
        "valor_actual_ars": "Valor (ARS)", "pnl_ars": "P&L (ARS)", "pnl_pct": "P&L %",
    })
    st.dataframe(
        tabla,
        use_container_width=True, hide_index=True,
        column_config={
            "P. compra":   st.column_config.NumberColumn(format="%.2f"),
            "P. actual":   st.column_config.NumberColumn(format="%.2f"),
            "Valor (ARS)": st.column_config.NumberColumn(format="$ %.2f"),
            "P&L (ARS)":   st.column_config.NumberColumn(format="$ %.2f"),
            "P&L %":       st.column_config.NumberColumn(format="%.2f%%"),
        },
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


def _formulario_alta():
    with st.sidebar:
        st.markdown("### Agregar tenencia")
        with st.form("alta_tenencia", clear_on_submit=True):
            ticker = st.text_input("Ticker (ej: GGAL.BA, AAPL, BTC-USD)").strip()
            tipo = st.selectbox("Tipo", options=[
                "accion_ar", "cedear", "accion_us", "etf", "bono", "fci", "cripto",
            ])
            cantidad = st.number_input("Cantidad", min_value=0.0, value=1.0, step=1.0, format="%.6f")
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
