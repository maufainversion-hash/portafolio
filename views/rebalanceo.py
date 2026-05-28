"""
Vista Rebalanceo: placeholder. Implementacion completa en bloque 2.
"""
import streamlit as st

from core.portfolio import load_tenencias, valuar_tenencias, convertir_a


def render():
    st.subheader("Rebalanceo")
    st.info(
        "🚧 Modulo en construccion. Llega en el **bloque 2** con:\n\n"
        "- Pesos objetivo por activo y por tipo\n"
        "- Optimizacion de Sharpe (PyPortfolioOpt)\n"
        "- Risk parity y minimum variance\n"
        "- Frontera eficiente interactiva\n"
        "- Simulacion Monte Carlo\n"
        "- Sugerencias de compra/venta con costo estimado"
    )

    df = load_tenencias()
    if df.empty:
        return

    with st.spinner("Cargando situacion actual..."):
        df_val = valuar_tenencias(df)
        df_val = convertir_a(df_val, "ARS", tipo_dolar="mep")

    st.markdown("**Situacion actual (preview)**")

    agg = (
        df_val.groupby("tipo")["valor_actual_ars"]
              .sum().reset_index().sort_values("valor_actual_ars", ascending=False)
    )
    total = agg["valor_actual_ars"].sum()
    if total > 0:
        agg["peso_pct"] = agg["valor_actual_ars"] / total * 100

    st.dataframe(
        agg.rename(columns={
            "tipo": "Tipo", "valor_actual_ars": "Valor (ARS)", "peso_pct": "Peso %",
        }),
        hide_index=True, use_container_width=True,
        column_config={
            "Valor (ARS)": st.column_config.NumberColumn(format="$ %.2f"),
            "Peso %":      st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
