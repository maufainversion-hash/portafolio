"""
Vista Rebalanceo: MVP.

Funcionalidad:
- Pesos objetivo por TIPO de activo (sliders).
- Comparacion actual vs objetivo (tabla + grafico de barras).
- Sugerencias de monto a comprar/vender por tipo.
- Validacion: la suma de objetivos debe ser 100%.
- Presets rapidos (60/30/10, conservador, agresivo, equally weighted).

Optimizacion cuantitativa (Sharpe, risk parity, frontera eficiente, Monte Carlo)
queda como extension futura.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.portfolio import load_tenencias, valuar_tenencias, convertir_a
from core.ui import fmt_pct, kpi_card, kpi_row, style_fig
from core.currency import fmt_display, display_label, display_symbol


# Labels visibles e icono por tipo (mismos que dashboard)
_TIPO_META = {
    "accion_ar": ("Acciones AR",  "🇦🇷"),
    "cedear":    ("Cedears",      "🌎"),
    "accion_us": ("Acciones US",  "🇺🇸"),
    "etf":       ("ETFs",         "📊"),
    "bono":      ("Bonos",        "📜"),
    "fci":       ("FCIs",         "🏦"),
    "cripto":    ("Cripto",       "₿"),
}
_TIPO_ORDER = ["accion_ar", "cedear", "accion_us", "etf", "bono", "fci", "cripto"]

# Presets de pesos objetivo (en %) por tipo
PRESETS = {
    "Conservador": {"bono": 60, "accion_ar": 10, "cedear": 20, "fci": 10},
    "Balanceado":  {"bono": 30, "accion_ar": 20, "cedear": 40, "fci": 10},
    "Agresivo":    {"bono": 10, "accion_ar": 30, "cedear": 50, "cripto": 10},
    "Equal weight": {},  # se completa dinamico segun los tipos presentes
}


def render():
    st.subheader("Rebalanceo")

    df = load_tenencias()
    if df.empty:
        st.info("Sin tenencias para rebalancear. Carga tu cartera desde el tab **Cartera**.")
        return

    with st.spinner("Valuando situacion actual..."):
        df_val = valuar_tenencias(df)
        df_val = convertir_a(df_val, "ARS", tipo_dolar="mep")

    df_val = df_val[df_val["valor_actual_ars"].notna()
                    & (df_val["valor_actual_ars"] > 0)].copy()
    if df_val.empty:
        st.warning("No hay posiciones con valor actual para rebalancear.")
        return

    # Tipos presentes + agregado
    agg = (df_val.groupby("tipo")["valor_actual_ars"].sum()
                 .reset_index().sort_values("valor_actual_ars", ascending=False))
    total_ars = agg["valor_actual_ars"].sum()
    agg["peso_actual_pct"] = agg["valor_actual_ars"] / total_ars * 100
    tipos_presentes = agg["tipo"].tolist()

    # ---------- Bloque 1: KPIs y selector de preset ----------
    ccy = display_label()
    kpi_row([
        kpi_card(f"Total cartera ({ccy})", fmt_display(total_ars)),
        kpi_card("Tipos en cartera", f"{len(tipos_presentes)}"),
        kpi_card("Posiciones", f"{len(df_val)}"),
        kpi_card("Modo", "Pesos objetivo por tipo"),
    ])

    st.markdown("### 🎯 Pesos objetivo")

    # Inicializar pesos objetivo en session_state con el peso actual si no existen.
    # Esto evita el warning "widget had value set via Session State API".
    for tipo in tipos_presentes:
        key = f"reb_obj_{tipo}"
        if key not in st.session_state:
            peso_actual = float(agg[agg["tipo"] == tipo]["peso_actual_pct"].iloc[0])
            st.session_state[key] = round(peso_actual, 1)

    c_preset, c_apply, c_reset = st.columns([3, 1, 1])
    with c_preset:
        preset = st.selectbox(
            "Preset (opcional)",
            options=["— Personalizado —"] + list(PRESETS.keys()),
            index=0, key="reb_preset",
        )
    with c_apply:
        st.markdown("<div style='height:1.75rem;'></div>", unsafe_allow_html=True)
        aplicar = st.button("Aplicar preset",
                            use_container_width=True,
                            disabled=(preset == "— Personalizado —"))
    with c_reset:
        st.markdown("<div style='height:1.75rem;'></div>", unsafe_allow_html=True)
        if st.button("Resetear", use_container_width=True,
                     help="Volver a los pesos actuales de la cartera"):
            for t in tipos_presentes:
                peso_actual = float(agg[agg["tipo"] == t]["peso_actual_pct"].iloc[0])
                st.session_state[f"reb_obj_{t}"] = round(peso_actual, 1)
            st.rerun()

    if aplicar and preset != "— Personalizado —":
        if preset == "Equal weight":
            base = 100.0 / len(tipos_presentes)
            for t in tipos_presentes:
                st.session_state[f"reb_obj_{t}"] = round(base, 1)
        else:
            for t in tipos_presentes:
                st.session_state[f"reb_obj_{t}"] = float(PRESETS[preset].get(t, 0))
        st.rerun()

    # Render de sliders SOLO con key (sin value=, para evitar conflicto)
    objetivos = {}
    cols = st.columns(min(len(tipos_presentes), 4))
    for i, tipo in enumerate(tipos_presentes):
        label, icon = _TIPO_META.get(tipo, (tipo, "•"))
        with cols[i % len(cols)]:
            objetivos[tipo] = st.slider(
                f"{icon} {label}", 0.0, 100.0,
                step=0.5, key=f"reb_obj_{tipo}",
                format="%.1f%%",
            )

    suma = sum(objetivos.values())
    if abs(suma - 100) > 0.5:
        st.warning(f"⚠️ Los pesos objetivo suman **{suma:.1f}%**. Ajustalos para que totalicen 100%.")
        return
    else:
        st.success(f"✔ Pesos objetivo: {suma:.1f}%")

    # ---------- Bloque 2: Tabla comparativa con sugerencias ----------
    st.markdown("### 📊 Plan de rebalanceo")
    _tabla_plan(agg, objetivos, total_ars)

    # ---------- Bloque 3: Grafico actual vs objetivo ----------
    st.markdown("### 📈 Distribucion actual vs objetivo")
    _grafico_actual_vs_objetivo(agg, objetivos)


def _tabla_plan(agg: pd.DataFrame, objetivos: dict, total_ars: float):
    """Tabla HTML con: tipo, peso actual %, peso objetivo %, gap %, monto a operar."""
    filas = ""
    total_buy = 0.0
    total_sell = 0.0
    for _, r in agg.iterrows():
        tipo = r["tipo"]
        label, icon = _TIPO_META.get(tipo, (tipo, "•"))
        actual_pct = float(r["peso_actual_pct"])
        actual_ars = float(r["valor_actual_ars"])
        obj_pct = objetivos.get(tipo, 0.0)
        obj_ars = total_ars * obj_pct / 100
        gap_ars = obj_ars - actual_ars  # positivo: comprar, negativo: vender
        gap_pct = obj_pct - actual_pct
        accion = "Comprar" if gap_ars > 0 else ("Vender" if gap_ars < 0 else "Mantener")
        cls = "pnl-pos" if gap_ars > 0 else ("pnl-neg" if gap_ars < 0 else "")

        if gap_ars > 0:
            total_buy += gap_ars
        else:
            total_sell += abs(gap_ars)

        filas += (
            "<tr>"
            f"<td><span class='tk-badge'>{icon} {label}</span></td>"
            f"<td>{actual_pct:.2f}%</td>"
            f"<td>{obj_pct:.2f}%</td>"
            f"<td class='{cls}'>{gap_pct:+.2f}%</td>"
            f"<td>{fmt_display(actual_ars)}</td>"
            f"<td>{fmt_display(obj_ars)}</td>"
            f"<td class='{cls}'><b>{accion}</b> {fmt_display(abs(gap_ars))}</td>"
            "</tr>"
        )

    ccy = display_label()
    st.markdown(
        f"<table class='pos-table'><thead><tr>"
        f"<th>Tipo</th><th>Peso actual</th><th>Peso objetivo</th><th>Gap</th>"
        f"<th>Valor actual ({ccy})</th><th>Valor objetivo ({ccy})</th>"
        f"<th>Accion sugerida</th>"
        f"</tr></thead><tbody>{filas}</tbody></table>",
        unsafe_allow_html=True,
    )

    # Resumen abajo
    st.markdown(
        f"<div style='margin-top:.8rem;display:flex;gap:1rem;flex-wrap:wrap;'>"
        f"<span class='kpi-delta pos'>↑ Total a comprar: {fmt_display(total_buy)}</span>"
        f"<span class='kpi-delta neg'>↓ Total a vender: {fmt_display(total_sell)}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if total_buy > 0 and total_sell == 0:
        st.caption("💡 Necesitas inyectar capital para llegar al objetivo (solo compras).")
    elif total_sell > 0 and total_buy == 0:
        st.caption("💡 Vas a retirar capital con este rebalanceo (solo ventas).")
    elif total_buy > 0 and total_sell > 0:
        st.caption(f"💡 Rebalanceo neutro de capital: vender {fmt_display(total_sell)} "
                   f"y comprar {fmt_display(total_buy)}.")


def _grafico_actual_vs_objetivo(agg: pd.DataFrame, objetivos: dict):
    """Bar chart agrupado: actual vs objetivo por tipo."""
    labels = []
    actual_vals = []
    obj_vals = []
    for _, r in agg.iterrows():
        tipo = r["tipo"]
        label, icon = _TIPO_META.get(tipo, (tipo, "•"))
        labels.append(f"{icon} {label}")
        actual_vals.append(float(r["peso_actual_pct"]))
        obj_vals.append(objetivos.get(tipo, 0.0))

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=actual_vals, name="Actual",
        marker_color="#60a5fa",
        text=[f"{v:.1f}%" for v in actual_vals], textposition="outside",
        hovertemplate="<b>%{x}</b><br>Actual: %{y:.2f}%<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=labels, y=obj_vals, name="Objetivo",
        marker_color="#34d399",
        text=[f"{v:.1f}%" for v in obj_vals], textposition="outside",
        hovertemplate="<b>%{x}</b><br>Objetivo: %{y:.2f}%<extra></extra>",
    ))
    style_fig(fig, height=340)
    fig.update_layout(
        barmode="group",
        yaxis=dict(title="Peso (%)", ticksuffix="%"),
        legend=dict(orientation="h", y=-0.18),
        bargap=0.25, bargroupgap=0.1,
    )
    st.plotly_chart(fig, use_container_width=True)
