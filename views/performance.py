"""
Vista Performance: equity curve, metricas cuantitativas (Sharpe, Sortino, CAGR,
MaxDD, Calmar, VaR), retornos rolling.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.portfolio import load_tenencias, equity_curve, benchmark_curves
from core.metrics import (
    returns_from_prices, summary, rolling_sharpe, rolling_volatility,
)
from core.ui import style_fig, fmt_pct, kpi_card, kpi_row


# Paleta por benchmark
BM_COLORS = {
    "Portfolio":   "#34d399",
    "Merval":      "#60a5fa",
    "SPY (ARS)":   "#a78bfa",
    "USD MEP":     "#fbbf24",
    "Inflación":   "#fb7185",
}


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
        line=dict(color="#34d399", width=2),
        fill="tozeroy", fillcolor="rgba(52,211,153,0.10)",
        name="Valor (ARS)",
    ))
    style_fig(fig, height=380)
    fig.update_layout(title=dict(text=f"Equity curve — {periodo_label}", font=dict(size=14)))
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
        _line_chart(rs, "Sharpe 30d", color="#34d399")
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
        line=dict(color="#fb7185", width=1.5),
        fill="tozeroy", fillcolor="rgba(251,113,133,0.15)",
    ))
    style_fig(fig, height=240)
    fig.update_layout(yaxis=dict(title="Drawdown (%)"))
    st.plotly_chart(fig, use_container_width=True)

    # =========================================================================
    # COMPARATIVA VS BENCHMARKS
    # =========================================================================
    st.divider()
    st.markdown("### 📊 Vs Benchmarks")
    st.caption(
        "Tu portfolio comparado contra alternativas pasivas, todo normalizado "
        "a base 100 al inicio del periodo. Si la linea esta por encima de 100, "
        "ganaste; si esta abajo, perdiste."
    )

    seleccion = st.multiselect(
        "Mostrar",
        options=["Portfolio", "Merval", "SPY (ARS)", "USD MEP", "Inflación"],
        default=["Portfolio", "Merval", "SPY (ARS)", "USD MEP", "Inflación"],
        key="perf_bm_select",
    )

    with st.spinner("Calculando curvas de benchmarks..."):
        df_bm = benchmark_curves(period=periodo)

    if df_bm.empty:
        st.info("No se pudieron calcular las curvas de benchmarks.")
    else:
        # KPIs de retorno final por benchmark
        kpis = []
        for col in ["Portfolio", "Merval", "SPY (ARS)", "USD MEP", "Inflación"]:
            if col not in df_bm.columns:
                continue
            serie = df_bm[col].dropna()
            if serie.empty:
                continue
            ret = serie.iloc[-1] - 100
            es_inflacion = (col == "Inflación")
            # Inflacion "positivo" significa que el peso pierde valor -> negativo para vos
            kpis.append(kpi_card(
                col, f"{ret:+.2f}%",
                delta=None,
                positive=(ret >= 0) if not es_inflacion else (ret <= 0),
            ))
        st.markdown(
            f'<div class="kpi-grid" style="grid-template-columns:repeat({len(kpis)},1fr);">'
            f'{"".join(kpis)}</div>',
            unsafe_allow_html=True,
        )

        # Chart de lineas
        fig = go.Figure()
        for col in seleccion:
            if col not in df_bm.columns:
                continue
            serie = df_bm[col].dropna()
            if serie.empty:
                continue
            color = BM_COLORS.get(col, "#9ca3af")
            # Portfolio mas grueso para destacar
            width = 3 if col == "Portfolio" else 1.5
            fig.add_trace(go.Scatter(
                x=serie.index, y=serie.values, mode="lines",
                line=dict(color=color, width=width),
                name=col,
                hovertemplate=f"<b>{col}</b><br>%{{x|%d %b %Y}}<br>"
                              f"%{{y:.2f}} ({{:+.2f}}%)<extra></extra>".replace(
                                  "{:+.2f}", "%{y:.2f}-100"),
            ))

        # Linea horizontal de referencia en 100
        fig.add_hline(y=100, line_dash="dot", line_color="rgba(255,255,255,0.3)",
                      annotation_text="base", annotation_position="top right")

        style_fig(fig, height=420)
        fig.update_layout(
            yaxis=dict(title="Indice base 100"),
            legend=dict(orientation="h", y=-0.15, font=dict(size=12)),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Resumen interpretativo
        if "Portfolio" in df_bm.columns:
            port_ret = df_bm["Portfolio"].dropna().iloc[-1] - 100
            comparaciones = []
            for col in ["Merval", "SPY (ARS)", "USD MEP", "Inflación"]:
                if col not in df_bm.columns or df_bm[col].dropna().empty:
                    continue
                bm_ret = df_bm[col].dropna().iloc[-1] - 100
                diff = port_ret - bm_ret
                signo = "ganó" if diff > 0 else "perdió"
                cls = "pnl-pos" if diff > 0 else "pnl-neg"
                comparaciones.append(
                    f"<span class='kpi-delta {cls}' style='margin:.2rem;'>"
                    f"vs <b>{col}</b>: {signo} <b>{diff:+.2f} pp</b></span>"
                )
            if comparaciones:
                st.markdown(
                    f"<div style='margin-top:.6rem;'>{''.join(comparaciones)}</div>",
                    unsafe_allow_html=True,
                )


def _line_chart(s: pd.Series, name: str, color: str = "#34d399"):
    if s is None or s.empty:
        st.info("Sin datos.")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines",
        line=dict(color=color, width=1.5), name=name,
    ))
    style_fig(fig, height=240)
    st.plotly_chart(fig, use_container_width=True)
