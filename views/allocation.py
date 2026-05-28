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
from core.ui import style_fig


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
    st.markdown("**Sunburst tipo → ticker**")
    if not df_val.empty:
        fig = px.sunburst(
            df_val, path=["tipo", "ticker"], values="valor_actual_ars",
            color="valor_actual_ars",
            color_continuous_scale=["#0a0e1a", "#34d399"],
        )
        style_fig(fig, height=480)
        st.plotly_chart(fig, use_container_width=True)


def _treemap(df: pd.DataFrame, field: str, titulo: str):
    agg = allocation_by(df, field, "valor_actual_ars")
    agg = agg[agg["valor_actual_ars"] > 0]
    if agg.empty or agg["valor_actual_ars"].sum() <= 0:
        st.info("Sin datos para graficar.")
        return
    fig = px.treemap(
        agg, path=[field], values="valor_actual_ars",
        color="peso_pct",
        color_continuous_scale=["#0a0e1a", "#34d399"],
    )
    style_fig(fig, height=400)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        agg.rename(columns={field: titulo,
                            "valor_actual_ars": "Valor (ARS)",
                            "peso_pct": "Peso %"}),
        hide_index=True, use_container_width=True,
        column_config={
            "Valor (ARS)": st.column_config.NumberColumn(format="$ %.2f"),
            "Peso %":      st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
