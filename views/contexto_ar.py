"""
Vista Contexto AR: cotizaciones de dolar (oficial / MEP / CCL / blue),
brecha cambiaria, riesgo pais, Merval, inflacion historica.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.data import (
    get_dolares, get_riesgo_pais, get_inflacion_mensual,
    get_merval, get_history,
)


def render():
    st.subheader("Contexto Argentino")

    # ---------- DOLAR ----------
    dolares = get_dolares()
    if not dolares:
        st.error("No se pudo obtener cotizaciones de dolar.")
    else:
        st.markdown("**Cotizaciones del dolar**")
        cols = st.columns(4)
        for col, casa in zip(cols, ["oficial", "blue", "mep", "contadoconliqui"]):
            data = dolares.get(casa, {})
            nombre = data.get("nombre", casa.title())
            venta = data.get("venta")
            with col:
                st.metric(nombre, f"$ {venta:,.2f}" if venta else "—")

        # Brecha vs oficial
        oficial = dolares.get("oficial", {}).get("venta")
        if oficial:
            st.markdown("**Brecha cambiaria vs oficial**")
            brecha_cols = st.columns(3)
            for col, casa in zip(brecha_cols, ["blue", "mep", "contadoconliqui"]):
                v = dolares.get(casa, {}).get("venta")
                if v:
                    brecha = (v / oficial - 1) * 100
                    label = dolares.get(casa, {}).get("nombre", casa)
                    col.metric(f"Brecha {label}", f"{brecha:+.2f}%")

    st.divider()

    # ---------- RIESGO PAIS + MERVAL ----------
    c1, c2 = st.columns(2)
    with c1:
        rp = get_riesgo_pais()
        st.metric("Riesgo pais (EMBI)", f"{rp:,.0f} pb" if rp else "—")
    with c2:
        mv = get_merval()
        st.metric("Merval (^MERV)", f"{mv:,.2f}" if mv else "—")

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
            line=dict(color="#22c55e", width=2),
            fill="tozeroy", fillcolor="rgba(34,197,94,0.10)",
            name="Merval",
        ))
        fig.update_layout(
            height=300, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor="#1f2937"), yaxis=dict(gridcolor="#1f2937"),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---------- INFLACION ----------
    st.markdown("**Inflacion mensual (INDEC)**")
    infl = get_inflacion_mensual()
    if infl.empty:
        st.info("No se pudo cargar la serie de inflacion.")
    else:
        ultimos = infl.tail(24)
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=ultimos["fecha"], y=ultimos["valor"],
            marker_color="#f59e0b",
        ))
        fig.update_layout(
            height=320, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor="#1f2937"),
            yaxis=dict(gridcolor="#1f2937", title="% mensual"),
        )
        st.plotly_chart(fig, use_container_width=True)
