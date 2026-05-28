"""
Vista Cartera: gestion de tenencias.
- Alta con filtro por tipo + ticker.
- Listado de tenencias actuales con boton de eliminar.
"""
from datetime import date
import pandas as pd
import streamlit as st

from core.portfolio import load_tenencias, add_tenencia, delete_tenencia
from core.ui import fmt_money


# Catalogo de tipos de activo (label visible -> codigo interno)
TIPOS = {
    "Accion AR":        "accion_ar",
    "CEDEAR":           "cedear",
    "Accion US / ADR":  "accion_us",
    "ETF":              "etf",
    "Bono":             "bono",
    "FCI":              "fci",
    "Cripto":           "cripto",
}

# Ejemplos por tipo para guiar al usuario
EJEMPLOS = {
    "accion_ar": "GGAL.BA, YPFD.BA, PAMP.BA",
    "cedear":    "AAPL.BA, MSFT.BA, KO.BA",
    "accion_us": "AAPL, MSFT, TSLA, NVDA",
    "etf":       "SPY, QQQ, VTI, EEM",
    "bono":      "AL30.BA, GD30.BA",
    "fci":       "Codigo del FCI",
    "cripto":    "BTC-USD, ETH-USD, SOL-USD",
}


def render():
    st.subheader("Cartera")

    _alta()
    st.divider()
    _listado()


def _alta():
    st.markdown("### ➕ Agregar tenencia")

    # El selector de tipo va FUERA del form para que el placeholder del ticker
    # reaccione en vivo al cambiar tipo.
    col_t, col_e = st.columns([1, 2])
    with col_t:
        tipo_label = st.selectbox("Tipo de activo", options=list(TIPOS.keys()),
                                  key="alta_tipo_label")
    tipo_code = TIPOS[tipo_label]
    with col_e:
        st.markdown(
            f"<div style='padding-top:1.95rem;color:#8b96a8;font-size:.88rem;'>"
            f"Ejemplos: <span style='color:#34d399;'>{EJEMPLOS[tipo_code]}</span></div>",
            unsafe_allow_html=True,
        )

    with st.form("alta_tenencia", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            ticker = st.text_input("Ticker", placeholder=EJEMPLOS[tipo_code]).strip()
            cantidad = st.number_input("Cantidad", min_value=0.0, value=1.0,
                                       step=1.0, format="%.6f")
        with c2:
            precio = st.number_input("Precio de compra", min_value=0.0,
                                     value=0.0, format="%.2f")
            moneda = st.selectbox("Moneda compra",
                                  options=["ARS", "USD"],
                                  index=(1 if tipo_code in ("accion_us", "etf", "cripto") else 0))
        with c3:
            fecha = st.date_input("Fecha de compra", value=date.today())
            st.markdown("&nbsp;", unsafe_allow_html=True)
            ok = st.form_submit_button("Agregar tenencia", type="primary",
                                       use_container_width=True)

        if ok:
            if not ticker or cantidad <= 0 or precio <= 0:
                st.error("Completa ticker, cantidad y precio (> 0).")
            else:
                add_tenencia(ticker, tipo_code, cantidad, precio, moneda, fecha)
                st.success(f"✔ Tenencia {ticker.upper()} agregada.")
                st.rerun()


def _listado():
    st.markdown("### 📋 Mis tenencias")
    df = load_tenencias()
    if df.empty:
        st.info("Todavia no agregaste tenencias. Usa el formulario de arriba para empezar.")
        return

    # Tabla compacta con boton eliminar por fila
    df = df.sort_values("ticker").reset_index(drop=True)
    header = st.columns([1.2, 1.2, 0.9, 1.2, 0.7, 1.1, 0.7])
    headers = ["Ticker", "Tipo", "Cantidad", "P. compra", "Moneda", "Fecha", ""]
    for h, c in zip(headers, header):
        c.markdown(
            f"<div style='font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;"
            f"color:#5a6478;font-weight:600;'>{h}</div>",
            unsafe_allow_html=True,
        )

    for _, r in df.iterrows():
        cols = st.columns([1.2, 1.2, 0.9, 1.2, 0.7, 1.1, 0.7])
        cols[0].markdown(f"**{r['ticker']}**")
        cols[1].markdown(f"<span style='color:#8b96a8;'>{r['tipo']}</span>",
                         unsafe_allow_html=True)
        cols[2].write(f"{r['cantidad']:.4f}")
        cols[3].write(fmt_money(r["precio_compra"]))
        cols[4].write(r["moneda_compra"])
        cols[5].write(str(r["fecha_compra"]))
        if cols[6].button("🗑", key=f"del_{r['id']}", help="Eliminar"):
            delete_tenencia(int(r["id"]))
            st.rerun()
