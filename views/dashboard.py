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
    agregar_pnl_real,
)
from core.metrics import returns_from_prices, volatility
from core.data import get_history
from core.ui import fmt_money, fmt_pct, kpi_card, kpi_row, style_fig
from core.currency import (
    fmt_display, convert_ars, display_label, display_symbol,
)


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
        df_val = agregar_pnl_real(df_val)
        curve = equity_curve(df, period="6mo")

    # P&L se calcula SOLO sobre posiciones con precio valido,
    # para no contar como perdida total las que no se pudieron valuar.
    validos = df_val[df_val["precio_actual"].notna()].copy()
    sin_precio = len(df_val) - len(validos)

    valor_ars = validos["valor_actual_ars"].sum()
    valor_usd = validos["valor_actual_usd"].sum()
    costo_ars = validos["costo_ars"].sum()
    pnl_ars   = valor_ars - costo_ars
    pnl_pct   = (pnl_ars / costo_ars * 100) if costo_ars else 0

    # P&L real (ajustado por inflacion CER)
    costo_real_ars = validos["costo_real_ars"].sum() if "costo_real_ars" in validos else costo_ars
    pnl_real_ars   = valor_ars - costo_real_ars
    pnl_real_pct   = (pnl_real_ars / costo_real_ars * 100) if costo_real_ars else 0

    # Volatilidad anualizada (a partir de la equity curve en pesos)
    vol_anual = None
    if not curve.empty and len(curve) > 5:
        rets = returns_from_prices(curve)
        if not rets.empty:
            vol_anual = volatility(rets, annualize=True) * 100

    if sin_precio > 0:
        st.warning(
            f"⚠️ {sin_precio} de {len(df_val)} posiciones sin precio actual "
            "(Yahoo puede estar limitando el acceso). El P&L se calcula sobre las valuadas."
        )

    # Fila 1: valor + P&L
    ccy = display_label()
    kpi_row([
        kpi_card(f"Valor total ({ccy})", fmt_display(valor_ars)),
        kpi_card(f"P&L nominal ({ccy})", fmt_display(pnl_ars),
                 delta=fmt_pct(pnl_pct), positive=(pnl_ars >= 0)),
        kpi_card(f"P&L real (vs CER)", fmt_display(pnl_real_ars),
                 delta=fmt_pct(pnl_real_pct), positive=(pnl_real_ars >= 0)),
        kpi_card("Posiciones valuadas", f"{len(validos)} / {len(df_val)}"),
    ])

    # Fila 2: rendimientos
    kpi_row([
        kpi_card("Rendimiento", fmt_pct(pnl_pct),
                 delta=None, positive=(pnl_pct >= 0)),
        kpi_card("Volatilidad anual",
                 f"{vol_anual:.2f}%" if vol_anual is not None else "—"),
        kpi_card("Rendimiento real (CER)", fmt_pct(pnl_real_pct),
                 delta=None, positive=(pnl_real_pct >= 0)),
        kpi_card("Periodo equity",
                 f"{len(curve)} dias" if not curve.empty else "—"),
    ])

    st.divider()

    # Equity curve + Donut
    col_chart, col_donut = st.columns([2, 1])
    with col_chart:
        st.markdown(f"**Equity curve (6 meses, {ccy})**")
        if curve.empty:
            st.warning("No se pudo calcular la equity curve (sin datos historicos).")
        else:
            curve_disp = curve.apply(convert_ars)
            sym = display_symbol()
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=curve_disp.index, y=curve_disp.values,
                mode="lines", line=dict(color="#34d399", width=2),
                fill="tozeroy", fillcolor="rgba(52,211,153,0.10)",
                name="Valor",
                hovertemplate=f"<b>%{{x|%d %b %Y}}</b><br>{sym} %{{y:,.0f}}<extra></extra>",
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
    col_h, col_sp = st.columns([3, 1])
    with col_h:
        st.markdown("**Posiciones**")
    with col_sp:
        mostrar_spark = st.toggle("Sparklines 30d", value=False,
                                  help="Mini chart de 30 dias por activo (mas lento)")
    sparks = _calcular_sparklines(df_val) if mostrar_spark else {}
    _render_posiciones_agrupadas(df_val, sparks)

    # Detalle por activo (drill-down)
    st.divider()
    _render_detalle_ticker(df_val)

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


def _render_detalle_ticker(df_val: pd.DataFrame):
    """Drill-down: selector + chart historico + metricas del activo."""
    st.markdown("### 🔍 Detalle por activo")
    tickers = df_val["ticker"].tolist()
    if not tickers:
        return

    col_sel, col_per = st.columns([2, 1])
    with col_sel:
        ticker = st.selectbox("Elegi un activo", options=tickers,
                              key="dash_drilldown_ticker")
    with col_per:
        periodo_label = st.selectbox(
            "Periodo",
            options=["1 mes", "3 meses", "6 meses", "1 año", "2 años"],
            index=2, key="dash_drilldown_periodo")
    periodo_map = {"1 mes": "1mo", "3 meses": "3mo", "6 meses": "6mo",
                   "1 año": "1y", "2 años": "2y"}
    periodo = periodo_map[periodo_label]

    row = df_val[df_val["ticker"] == ticker].iloc[0]

    # KPIs de la posicion
    kpi_row([
        kpi_card("Ticker", ticker),
        kpi_card("Tipo", row["tipo"]),
        kpi_card("Cantidad", f"{row['cantidad']:.4f}"),
        kpi_card("Peso en cartera",
                 f"{(row['valor_actual_ars'] / df_val['valor_actual_ars'].sum() * 100):.2f}%"),
    ])
    kpi_row([
        kpi_card("Precio actual", fmt_money(row.get("precio_actual"))),
        kpi_card("Precio compra", fmt_money(row.get("precio_compra"))),
        kpi_card("P&L nominal",
                 fmt_display(row.get("pnl_ars")),
                 delta=fmt_pct(row.get("pnl_pct")),
                 positive=(row.get("pnl_pct", 0) or 0) >= 0),
        kpi_card("P&L real (CER)",
                 fmt_pct(row.get("pnl_real_pct")),
                 positive=(row.get("pnl_real_pct", 0) or 0) >= 0),
    ])

    # Historico
    with st.spinner(f"Trayendo historico de {ticker}..."):
        hist = get_history(ticker, period=periodo, tipo=row["tipo"])
    if hist is None or hist.empty:
        st.info(f"No hay historico disponible para {ticker} en este periodo.")
        return

    # Buy price line
    buy_price = row.get("precio_compra")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist.index, y=hist["Close"], mode="lines",
        line=dict(color="#34d399", width=2),
        fill="tozeroy", fillcolor="rgba(52,211,153,0.10)",
        name=ticker,
        hovertemplate=f"<b>{ticker}</b><br>%{{x|%d %b %Y}}<br>%{{y:,.2f}}<extra></extra>",
    ))
    if buy_price:
        fig.add_hline(y=buy_price, line_dash="dot", line_color="#a78bfa",
                      annotation_text=f"compra {buy_price:.2f}",
                      annotation_position="top right",
                      annotation_font_color="#a78bfa")
    style_fig(fig, height=340)
    fig.update_layout(yaxis=dict(title="Precio (moneda nativa)"))
    st.plotly_chart(fig, use_container_width=True)

    # Mini estadisticas del activo
    closes = hist["Close"].dropna()
    if len(closes) > 2:
        ret_periodo = (closes.iloc[-1] / closes.iloc[0] - 1) * 100
        rets = closes.pct_change().dropna()
        vol_periodo = rets.std() * (252 ** 0.5) * 100 if len(rets) > 5 else None
        maxi = closes.max()
        mini = closes.min()
        dd_max = (closes / closes.cummax() - 1).min() * 100
        kpi_row([
            kpi_card(f"Retorno {periodo_label}", f"{ret_periodo:+.2f}%",
                     positive=(ret_periodo >= 0)),
            kpi_card("Vol. anual", f"{vol_periodo:.2f}%" if vol_periodo else "—"),
            kpi_card("Maximo periodo", f"{maxi:,.2f}"),
            kpi_card("Max Drawdown", f"{dd_max:.2f}%",
                     positive=False),
        ])


def _calcular_sparklines(df_val: pd.DataFrame) -> dict:
    """Genera un SVG inline por ticker con los precios de los ultimos 30 dias.
    Devuelve {ticker: svg_str}. Si yfinance falla, omite el ticker."""
    out = {}
    for _, r in df_val.iterrows():
        try:
            hist = get_history(r["ticker"], period="1mo", tipo=r["tipo"])
            if hist is None or hist.empty:
                continue
            closes = hist["Close"].dropna().tolist()
            if len(closes) < 3:
                continue
            out[r["ticker"]] = _spark_svg(closes)
        except Exception:
            continue
    return out


def _spark_svg(values: list, w: int = 90, h: int = 24) -> str:
    """SVG line chart minimal en una sola fila. Color verde si sube, rosa si baja."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    rng = hi - lo if hi > lo else 1
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = (i / (n - 1)) * (w - 2) + 1
        y = h - 1 - ((v - lo) / rng) * (h - 2)
        pts.append(f"{x:.1f},{y:.1f}")
    points = " ".join(pts)
    sube = values[-1] >= values[0]
    color = "#34d399" if sube else "#fb7185"
    fill_color = "rgba(52,211,153,0.18)" if sube else "rgba(251,113,133,0.18)"
    # Polygon de fill (cierra al borde inferior)
    fill_pts = points + f" {w-1:.1f},{h-1} 1,{h-1}"
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'xmlns="http://www.w3.org/2000/svg" style="vertical-align:middle;">'
        f'<polygon points="{fill_pts}" fill="{fill_color}" stroke="none"/>'
        f'<polyline points="{points}" stroke="{color}" stroke-width="1.5" '
        f'fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


def _render_posiciones_agrupadas(df_val: pd.DataFrame, sparks: dict = None):
    """Tabla agrupada por tipo, cada grupo colapsable con sus sub-totales."""
    ccy = display_label()
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

        # Filas (todo reexpresado en la moneda activa)
        filas = ""
        for _, r in grupo.iterrows():
            pnl = r.get("pnl_ars")
            pnl_p = r.get("pnl_pct")
            pnl_real_p = r.get("pnl_real_pct")
            cls = "pnl-pos" if (pd.notna(pnl) and pnl >= 0) else "pnl-neg"
            cls_real = "pnl-pos" if (pd.notna(pnl_real_p) and pnl_real_p >= 0) else "pnl-neg"
            spark_html = ""
            if sparks:
                spark_html = sparks.get(r["ticker"], "")
            spark_cell = f"<td>{spark_html}</td>" if sparks is not None else ""
            filas += (
                "<tr>"
                f"<td><span class='tk-badge'>{r['ticker']}</span></td>"
                f"{spark_cell}"
                f"<td>{r['cantidad']:.4f}</td>"
                f"<td>{fmt_money(r.get('precio_actual'))}</td>"
                f"<td>{fmt_display(r.get('valor_actual_ars'))}</td>"
                f"<td class='{cls}'>{fmt_display(pnl)}</td>"
                f"<td class='{cls}'>{fmt_pct(pnl_p)}</td>"
                f"<td class='{cls_real}'>{fmt_pct(pnl_real_p)}</td>"
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
              <span class="grp-total">{fmt_display(sub_valor)}</span>
              <span class="grp-delta {sub_cls}">{fmt_pct(sub_pct)}</span>
            </span>
          </summary>
          <table class="pos-table">
            <thead><tr>
              <th>Activo</th>{("<th>30d</th>" if sparks is not None else "")}<th>Cantidad</th><th>P. actual</th>
              <th>Valor ({ccy})</th><th>P&L ({ccy})</th><th>P&L %</th><th>P&L real %</th>
            </tr></thead>
            <tbody>{filas}</tbody>
          </table>
        </details>
        """)

    st.markdown("".join(bloques), unsafe_allow_html=True)
