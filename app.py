"""
TuPortafolioIA — Entrypoint.
Streamlit app con navegacion horizontal por tabs (streamlit-option-menu)
y ruteo manual a cada vista.
"""
import streamlit as st
from streamlit_option_menu import option_menu

from core.db import (
    init_db, list_portfolios, create_portfolio, rename_portfolio,
    delete_portfolio,
)
from core.active_portfolio import (
    get_active_portfolio_id, set_active_portfolio, get_active_portfolio_info,
)
from core.ui import inject_css
from views import (
    dashboard, cartera, allocation, performance, rebalanceo, contexto_ar,
    research,
)


st.set_page_config(
    page_title="TuPortafolioIA",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_css()

# Inicializar DB (sin seed; el usuario arranca con cartera vacia)
init_db(seed=False)

# Encabezado + selectores globales (portfolio + moneda)
col_h, col_pf, col_ccy = st.columns([3, 2, 1])
with col_h:
    st.markdown(
        """
        <div style="margin-bottom:.4rem;">
          <div style="display:flex;align-items:center;gap:.6rem;">
            <span style="font-size:1.7rem;">📊</span>
            <span style="font-family:'Sora',sans-serif;font-weight:700;font-size:1.9rem;
                background:linear-gradient(90deg,#e8edf5,#34d399);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
                TuPortafolioIA</span>
          </div>
          <p style="margin:.1rem 0 0;color:#8b96a8;font-size:.92rem;">
            Terminal de portafolio · contexto argentino</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Selector de portfolio activo + popover para CRUD
with col_pf:
    st.markdown("<div style='height:.4rem;'></div>", unsafe_allow_html=True)
    portfolios = list_portfolios()
    if not portfolios:
        st.warning("Sin portfolios. Crea uno desde el botón ⚙ →")
        ids, labels = [], []
    else:
        ids = [p["id"] for p in portfolios]
        labels = [
            (f"{p['nombre']} · {p['cliente']}" if p['cliente']
             else p['nombre']) + f"  ({p['n_tenencias']})"
            for p in portfolios
        ]
    active_id = get_active_portfolio_id()
    sel_col, btn_col = st.columns([4, 1])
    with sel_col:
        if ids:
            try:
                idx = ids.index(active_id) if active_id in ids else 0
            except ValueError:
                idx = 0
            chosen = st.selectbox(
                "Portfolio activo", options=ids,
                format_func=lambda i: labels[ids.index(i)],
                index=idx,
                label_visibility="collapsed",
                key="active_portfolio_selector",
            )
            if chosen != active_id:
                set_active_portfolio(chosen)
                st.rerun()
    with btn_col:
        with st.popover("⚙", use_container_width=True):
            st.markdown("**Gestionar clientes / portfolios**")
            info = get_active_portfolio_info()

            # Crear nuevo
            with st.form("nuevo_pf", clear_on_submit=True):
                st.markdown("*Crear nuevo*")
                nombre_n = st.text_input("Nombre", placeholder="Ej: Juan Perez")
                cliente_n = st.text_input("Cliente (opcional)",
                                          placeholder="Nombre del titular")
                notas_n = st.text_input("Notas (opcional)")
                if st.form_submit_button("Crear", type="primary",
                                         use_container_width=True):
                    try:
                        new_id = create_portfolio(nombre_n, cliente_n, notas_n)
                        set_active_portfolio(new_id)
                        st.success(f"Portfolio '{nombre_n}' creado.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

            if info:
                st.divider()
                st.markdown(f"*Editar el activo: **{info['nombre']}***")
                with st.form("editar_pf"):
                    nombre_e = st.text_input("Nombre", value=info["nombre"])
                    cliente_e = st.text_input("Cliente", value=info["cliente"] or "")
                    notas_e = st.text_input("Notas", value=info["notas"] or "")
                    ce, cb = st.columns(2)
                    with ce:
                        if st.form_submit_button("Guardar",
                                                 use_container_width=True):
                            try:
                                rename_portfolio(info["id"], nombre_e,
                                                 cliente_e, notas_e)
                                st.success("Actualizado.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                    with cb:
                        if st.form_submit_button("🗑 Eliminar este",
                                                 use_container_width=True,
                                                 help="Borra el portfolio y todas sus tenencias"):
                            try:
                                delete_portfolio(info["id"])
                                st.session_state["active_portfolio_id"] = None
                                st.success("Eliminado.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

with col_ccy:
    st.markdown("<div style='height:.6rem;'></div>", unsafe_allow_html=True)
    ccy_labels = {"ARS": "ARS", "USD_MEP": "USD MEP", "USD_CCL": "USD CCL"}
    ccy_choice = st.radio(
        "Moneda", options=list(ccy_labels.keys()),
        format_func=lambda k: ccy_labels[k],
        horizontal=True, label_visibility="collapsed",
        index=list(ccy_labels.keys()).index(
            st.session_state.get("display_ccy", "ARS")),
        key="display_ccy",
    )

# Navegacion horizontal estilo screenshot
selected = option_menu(
    menu_title=None,
    options=["Dashboard", "Cartera", "Allocation", "Performance",
             "Rebalanceo", "Contexto AR", "Research IA"],
    icons=["bar-chart-fill", "wallet2", "pie-chart-fill", "graph-up-arrow",
           "sliders", "flag-fill", "stars"],
    orientation="horizontal",
    default_index=0,
    styles={
        "container": {
            "padding": "0.5rem 0",
            "background-color": "rgba(0,0,0,0)",
            "border-bottom": "1px solid rgba(255,255,255,0.07)",
            "margin-bottom": "1.4rem",
        },
        "icon": {"color": "#34d399", "font-size": "0.95rem"},
        "nav-link": {
            "color": "#8b96a8",
            "font-family": "Sora, sans-serif",
            "font-size": "0.92rem",
            "text-align": "center",
            "margin": "0 0.2rem",
            "padding": "0.55rem 1.1rem",
            "border-radius": "10px",
            "--hover-color": "#131a2a",
        },
        "nav-link-selected": {
            "background": "linear-gradient(160deg,#131a2a,#0d121e)",
            "color": "#e8edf5",
            "font-weight": "600",
            "border": "1px solid rgba(52,211,153,0.35)",
            "box-shadow": "0 8px 24px -12px rgba(52,211,153,0.4)",
        },
    },
)

# Router
if selected == "Dashboard":
    dashboard.render()
elif selected == "Cartera":
    cartera.render()
elif selected == "Allocation":
    allocation.render()
elif selected == "Performance":
    performance.render()
elif selected == "Rebalanceo":
    rebalanceo.render()
elif selected == "Contexto AR":
    contexto_ar.render()
elif selected == "Research IA":
    research.render()
