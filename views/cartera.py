"""
Vista Cartera: gestion de tenencias.
- Alta con filtro por tipo + ticker.
- Listado de tenencias actuales con boton de eliminar.
"""
import io
import os
from datetime import date
import pandas as pd
import streamlit as st

from core.portfolio import (
    load_tenencias, add_tenencia, delete_tenencia, delete_all_tenencias,
    parse_csv_tenencias, bulk_add_tenencias,
)
from core.ui import fmt_money

# Paths a CSV versionados
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_MAUFA = os.path.join(_BASE_DIR, "data", "maufa_tenencias.csv")
CSV_TEMPLATE = os.path.join(_BASE_DIR, "data", "template_tenencias.csv")


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
    from core.active_portfolio import get_active_portfolio_label
    st.subheader("Cartera")
    st.caption(
        f"Editando: **{get_active_portfolio_label()}** · "
        "Cambia el portfolio desde el selector en la esquina superior derecha."
    )

    _alta()
    st.divider()
    _importar()
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


def _importar():
    with st.expander("📥 Importar tenencias en bloque", expanded=False):
        st.markdown(
            "Formato esperado: `ticker,tipo,cantidad,precio_compra,moneda_compra,fecha_compra`. "
            "Tipos validos: accion_ar, cedear, accion_us, etf, bono, fci, cripto. "
            "Moneda: ARS o USD. Fecha: YYYY-MM-DD."
        )

        tab_maufa, tab_csv, tab_paste = st.tabs([
            "🏷 Portafolio Maufa", "📄 Subir CSV", "📋 Pegar CSV",
        ])

        # ----- Portafolio Maufa -----
        with tab_maufa:
            st.caption("Carga las 10 tenencias del portafolio real (TXAR, YPFD, AE38, "
                       "FXI, LMT, MELI, META, PFE, TM, V).")
            df_maufa = pd.read_csv(CSV_MAUFA)
            st.dataframe(df_maufa, use_container_width=True, hide_index=True)
            col_a, col_b = st.columns([1, 3])
            with col_a:
                reemplazar_m = st.checkbox("Reemplazar todo", value=True, key="m_replace",
                                           help="Borra tenencias actuales antes de cargar.")
            if col_b.button("Cargar portafolio Maufa", type="primary",
                            use_container_width=True, key="btn_maufa"):
                _ejecutar_import(df_maufa, reemplazar_m)

        # ----- CSV upload -----
        with tab_csv:
            with open(CSV_TEMPLATE, "rb") as f:
                st.download_button("⬇ Descargar plantilla CSV", data=f.read(),
                                   file_name="template_tenencias.csv",
                                   mime="text/csv", use_container_width=False)
            up = st.file_uploader("Subir archivo CSV", type=["csv"], key="csv_up")
            if up is not None:
                try:
                    df_up = pd.read_csv(up)
                except Exception as e:
                    st.error(f"No pude leer el CSV: {e}")
                    return
                st.dataframe(df_up, use_container_width=True, hide_index=True)
                col_a, col_b = st.columns([1, 3])
                with col_a:
                    reemplazar_u = st.checkbox("Reemplazar todo", value=False,
                                               key="u_replace")
                if col_b.button("Cargar CSV", type="primary",
                                use_container_width=True, key="btn_csv"):
                    _ejecutar_import(df_up, reemplazar_u)

        # ----- Paste -----
        with tab_paste:
            txt = st.text_area(
                "Pega aca tu CSV (con header)", height=180,
                placeholder="ticker,tipo,cantidad,precio_compra,moneda_compra,fecha_compra\n"
                            "GGAL.BA,accion_ar,100,4500,ARS,2024-06-01",
                key="csv_paste",
            )
            if txt.strip():
                try:
                    df_p = pd.read_csv(io.StringIO(txt))
                except Exception as e:
                    st.error(f"No pude parsear: {e}")
                    return
                st.dataframe(df_p, use_container_width=True, hide_index=True)
                col_a, col_b = st.columns([1, 3])
                with col_a:
                    reemplazar_p = st.checkbox("Reemplazar todo", value=False,
                                               key="p_replace")
                if col_b.button("Cargar pegado", type="primary",
                                use_container_width=True, key="btn_paste"):
                    _ejecutar_import(df_p, reemplazar_p)


def _ejecutar_import(df_csv: pd.DataFrame, reemplazar: bool):
    df_clean, errores = parse_csv_tenencias(df_csv)
    if errores:
        st.error("No pude importar. Errores encontrados:")
        for e in errores:
            st.markdown(f"- {e}")
        return
    if reemplazar:
        n_borradas = delete_all_tenencias()
        if n_borradas > 0:
            st.warning(f"Se borraron {n_borradas} tenencias previas.")
    n = bulk_add_tenencias(df_clean)
    st.success(f"✔ Se importaron {n} tenencias.")
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
