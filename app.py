"""
TuPortafolioIA — Entrypoint.
Streamlit app con navegacion horizontal por tabs (streamlit-option-menu)
y ruteo manual a cada vista.
"""
import streamlit as st
from streamlit_option_menu import option_menu

from core.db import init_db
from core.ui import inject_css
from views import (
    dashboard, cartera, allocation, performance, rebalanceo, contexto_ar,
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

# Encabezado
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

# Navegacion horizontal estilo screenshot
selected = option_menu(
    menu_title=None,
    options=["Dashboard", "Cartera", "Allocation", "Performance", "Rebalanceo", "Contexto AR"],
    icons=["bar-chart-fill", "wallet2", "pie-chart-fill", "graph-up-arrow",
           "sliders", "flag-fill"],
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
