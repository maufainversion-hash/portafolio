"""
Dashboard principal: KPIs, equity curve, donut de allocation y tabla de posiciones.
La gestion de tenencias (alta/baja) vive en el tab Cartera.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.portfolio import (
    load_tenencias, valuar_tenencias, convertir_a, equity_curve,
)
from core.ui import fmt_money, fmt_pct, kpi_card, kpi_row, style_fig


def render():
    st.subheader("Dashboard")

    df = load_tenencias()
    if df.empty:
        st.info("Todavia no tenes tenencias cargadas. Ir al tab **Cartera** para agregar tu primer activo.")
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

    # Tabla de posiciones agrupada por tipo (HTML premium con <details>)
    st.markdown("**Posiciones**")
    _render_posiciones_agrupadas(df_val)

    st.caption("Gestiona tus tenencias (alta/baja) desde el tab **Cartera**.")


# Labels visibles e icono por tipo
_TIPO_META = {
    "accion_ar": ("Acciones AR",  "🇦🇷"),
    "cedear":    ("Cedears",      "🌎"),
    "accion_us": ("Acciones US",  "🇺🇸"),
    "etf":       ("ETFs",         "📊"),
    "bono":      ("Bonos",        "📜"),
    "fci":       ("FCIs",         "🏦"),
    "cripto":    ("Cripto",       "₿"),
}
# Orden de aparicion
_TIPO_ORDER = ["accion_ar", "cedear", "accion_us", "etf", "bono", "fci", "cripto"]


def _render_posiciones_agrupadas(df_val: pd.DataFrame):
    """Tabla agrupada por tipo, cada grupo colapsable con sus sub-totales."""
    bloques = []
    for tipo in _TIPO_ORDER:
        grupo = df_val[df_val["tipo"] == tipo]
        if grupo.empty:
            continue
        label, icon = _TIPO_META.get(tipo, (tipo, "•"))

        # Sub-totales del grupo (solo posiciones con valor valido)
        g_valid = grupo[grupo["valor_actual_ars"].notna()]
        sub_valor = g_valid["valor_actual_ars"].sum()
        sub_costo = g_valid["costo_ars"].sum() if "costo_ars" in g_valid else 0
        sub_pnl = sub_valor - sub_costo
        sub_pct = (sub_pnl / sub_costo * 100) if sub_costo else 0
        sub_cls = "pnl-pos" if sub_pnl >= 0 else "pnl-neg"

        # Filas
        filas = ""
        for _, r in grupo.iterrows():
            pnl = r.get("pnl_ars")
            pnl_p = r.get("pnl_pct")
            cls = "pnl-pos" if (pd.notna(pnl) and pnl >= 0) else "pnl-neg"
            filas += (
                "<tr>"
                f"<td><span class='tk-badge'>{r['ticker']}</span></td>"
                f"<td>{r['cantidad']:.4f}</td>"
                f"<td>{fmt_money(r.get('precio_actual'))}</td>"
                f"<td>{fmt_money(r.get('valor_actual_ars'))}</td>"
                f"<td class='{cls}'>{fmt_money(pnl)}</td>"
                f"<td class='{cls}'>{fmt_pct(pnl_p)}</td>"
                "</tr>"
            )

        bloques.append(f"""
        <details class="pos-group" open>
          <summary>
            <span class="grp-left">
              <span class="grp-chevron">▸</span>
              <span class="grp-icon">{icon}</span>
              <span class="grp-label">{label}</span>
              <span class="grp-count">{len(grupo)}</span>
            </span>
            <span class="grp-right">
              <span class="grp-total">{fmt_money(sub_valor)}</span>
              <span class="grp-delta {sub_cls}">{fmt_pct(sub_pct)}</span>
            </span>
          </summary>
          <table class="pos-table">
            <thead><tr>
              <th>Activo</th><th>Cantidad</th><th>P. actual</th>
              <th>Valor (ARS)</th><th>P&L (ARS)</th><th>P&L %</th>
            </tr></thead>
            <tbody>{filas}</tbody>
          </table>
        </details>
        """)

    st.markdown("".join(bloques), unsafe_allow_html=True)
