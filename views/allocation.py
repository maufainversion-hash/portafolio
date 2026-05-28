"""
Vista Allocation: distribucion del portafolio por tipo, moneda, sector y pais.
Sector/pais via yfinance.info (puede tardar y devolver 'Sin dato').
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from core.portfolio import (
    load_tenencias, valuar_tenencias, convertir_a, enriquecer_con_info,
    allocation_by,
)
from core.ui import style_fig, fmt_money

# Paleta categorica premium (esmeralda + teal + sky + violeta + rose + amber...)
PALETA = ["#34d399", "#2dd4bf", "#22d3ee", "#60a5fa", "#a78bfa",
          "#f472b6", "#fbbf24", "#fb7185", "#94a3b8", "#10b981"]


def _ticker_display(t: str) -> str:
    """Quita sufijo .BA para mostrar en graficos."""
    return t[:-3] if isinstance(t, str) and t.upper().endswith(".BA") else t


def render():
    st.subheader("Allocation")

    df = load_tenencias()
    if df.empty:
        st.info("No tenes tenencias cargadas.")
        return

    with st.spinner("Valuando portafolio..."):
        df_val = valuar_tenencias(df)
        df_val = convertir_a(df_val, "ARS", tipo_dolar="mep")

    # Filtramos posiciones sin precio o con valor 0/NaN para que los graficos
    # (treemap/sunburst) no rompan con ZeroDivisionError.
    df_val = df_val[df_val["valor_actual_ars"].notna()
                    & (df_val["valor_actual_ars"] > 0)].copy()
    if df_val.empty:
        st.warning("No hay posiciones con valor actual para graficar (Yahoo no devolvio precios).")
        return

    # Columna con ticker "limpio" para los displays
    df_val["ticker_display"] = df_val["ticker"].apply(_ticker_display)

    enriquecer = st.toggle(
        "Enriquecer con sector y pais (yfinance, mas lento)",
        value=False,
    )
    if enriquecer:
        with st.spinner("Buscando sector / pais..."):
            df_val = enriquecer_con_info(df_val)
    else:
        df_val["sector"]  = "Sin dato"
        df_val["country"] = "Sin dato"

    # Tabs internos para no saturar
    tab1, tab2, tab3, tab4 = st.tabs(["Por tipo", "Por moneda", "Por sector", "Por pais"])

    with tab1:
        _treemap(df_val, "tipo", "Distribucion por tipo de activo")

    with tab2:
        _treemap(df_val, "moneda_nativa", "Distribucion por moneda nativa")

    with tab3:
        if not enriquecer:
            st.info("Activa el toggle para traer sector via yfinance.")
        else:
            _treemap(df_val, "sector", "Distribucion por sector")

    with tab4:
        if not enriquecer:
            st.info("Activa el toggle para traer pais via yfinance.")
        else:
            _treemap(df_val, "country", "Distribucion por pais")

    st.divider()
    st.markdown("**Composicion: tipo → activo**")
    if not df_val.empty:
        fig = px.sunburst(
            df_val, path=["tipo", "ticker_display"], values="valor_actual_ars",
            color="tipo",
            color_discrete_sequence=PALETA,
            custom_data=["valor_actual_ars"],
        )
        fig.update_traces(
            hovertemplate="<b>%{label}</b><br>Valor: $%{customdata[0]:,.0f}<br>%{percentRoot:.1%} del total<extra></extra>",
            textfont=dict(size=13),
            insidetextorientation="radial",
        )
        style_fig(fig, height=480)
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)


def _treemap(df: pd.DataFrame, field: str, titulo: str):
    agg = allocation_by(df, field, "valor_actual_ars")
    agg = agg[agg["valor_actual_ars"] > 0]
    if agg.empty or agg["valor_actual_ars"].sum() <= 0:
        st.info("Sin datos para graficar.")
        return

    fig = px.treemap(
        agg, path=[field], values="valor_actual_ars",
        color=field,
        color_discrete_sequence=PALETA,
        custom_data=["peso_pct"],
    )
    fig.update_traces(
        textfont=dict(size=14, family="Sora, sans-serif"),
        hovertemplate="<b>%{label}</b><br>Valor: $%{value:,.0f}<br>Peso: %{customdata[0]:.2f}%<extra></extra>",
        marker=dict(line=dict(color="#0a0e1a", width=2)),
    )
    style_fig(fig, height=380)
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=10), coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    # Tabla compacta debajo
    st.markdown(
        "<table class='pos-table' style='margin-top:.6rem;'>"
        "<thead><tr><th>{}</th><th>Valor (ARS)</th><th>Peso</th></tr></thead><tbody>".format(titulo),
        unsafe_allow_html=True,
    )
    filas = ""
    for _, r in agg.iterrows():
        filas += (
            "<tr>"
            f"<td><span class='tk-badge'>{r[field]}</span></td>"
            f"<td>{fmt_money(r['valor_actual_ars'])}</td>"
            f"<td>{r['peso_pct']:.2f}%</td>"
            "</tr>"
        )
    st.markdown(filas + "</tbody></table>", unsafe_allow_html=True)
