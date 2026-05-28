"""
Vista Performance: equity curve, metricas cuantitativas (Sharpe, Sortino, CAGR,
MaxDD, Calmar, VaR), retornos rolling.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.portfolio import load_tenencias, equity_curve
from core.metrics import (
    returns_from_prices, summary, rolling_sharpe, rolling_volatility,
)


PERIODOS = {
    "1 mes":   "1mo",
    "3 meses": "3mo",
    "6 meses": "6mo",
    "1 año":   "1y",
    "2 años":  "2y",
    "5 años":  "5y",
}


def render():
    st.subheader("Performance")

    df = load_tenencias()
    if df.empty:
        st.info("No tenes tenencias cargadas.")
        return

    periodo_label = st.selectbox("Periodo", options=list(PERIODOS.keys()), index=2)
    periodo = PERIODOS[periodo_label]

    with st.spinner("Calculando equity curve..."):
        curve = equity_curve(df, period=periodo)

    if curve.empty:
        st.warning("No se pudo construir la equity curve (sin historico disponible).")
        return

    # Equity curve
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=curve.index, y=curve.values, mode="lines",
        line=dict(color="#22c55e", width=2),
        fill="tozeroy", fillcolor="rgba(34,197,94,0.10)",
        name="Valor (ARS)",
    ))
    fig.update_layout(
        height=380, margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#1f2937"), yaxis=dict(gridcolor="#1f2937"),
        title=dict(text=f"Equity curve — {periodo_label}", font=dict(size=14)),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Metricas
    st.markdown("**Metricas cuantitativas**")
    stats = summary(curve)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CAGR",         f"{stats['cagr']*100:+.2f}%")
    c2.metric("Volatilidad",  f"{stats['volatility']*100:.2f}%")
    c3.metric("Sharpe",       f"{stats['sharpe']:.2f}")
    c4.metric("Sortino",      f"{stats['sortino']:.2f}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Max Drawdown", f"{stats['max_drawdown']*100:.2f}%")
    c6.metric("Calmar",       f"{stats['calmar']:.2f}")
    c7.metric("VaR 95%",      f"{stats['var_95']*100:.2f}%")
    total_ret = (curve.iloc[-1] / curve.iloc[0] - 1) * 100
    c8.metric("Retorno total", f"{total_ret:+.2f}%")

    st.divider()

    # Rolling
    rets = returns_from_prices(curve)
    if len(rets) < 30:
        st.info("Hace falta al menos 30 dias de historia para los graficos rolling.")
        return

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Sharpe rolling 30d**")
        rs = rolling_sharpe(rets, window=30)
        _line_chart(rs, "Sharpe 30d", color="#22c55e")
    with col_b:
        st.markdown("**Volatilidad rolling 30d**")
        rv = rolling_volatility(rets, window=30) * 100
        _line_chart(rv, "Vol 30d (%)", color="#f59e0b")

    st.divider()
    st.markdown("**Drawdown**")
    dd = (curve / curve.cummax() - 1) * 100
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dd.index, y=dd.values, mode="lines",
        line=dict(color="#ef4444", width=1.5),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.15)",
    ))
    fig.update_layout(
        height=240, margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#1f2937"),
        yaxis=dict(gridcolor="#1f2937", title="Drawdown (%)"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _line_chart(s: pd.Series, name: str, color: str = "#22c55e"):
    if s is None or s.empty:
        st.info("Sin datos.")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines",
        line=dict(color=color, width=1.5), name=name,
    ))
    fig.update_layout(
        height=240, margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#1f2937"), yaxis=dict(gridcolor="#1f2937"),
    )
    st.plotly_chart(fig, use_container_width=True)
