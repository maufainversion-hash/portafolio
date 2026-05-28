"""
TuPortafolioIA — Entrypoint.
Streamlit app con navegacion horizontal por tabs (streamlit-option-menu)
y ruteo manual a cada vista.
"""
import streamlit as st
from streamlit_option_menu import option_menu

from core.db import init_db
from views import dashboard, allocation, performance, rebalanceo, contexto_ar


st.set_page_config(
    page_title="TuPortafolioIA",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS sutil para look mas premium
st.markdown(
    """
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
        [data-testid="stMetricValue"] { font-size: 1.6rem; }
        [data-testid="stMetricLabel"] { color: #9ca3af; }
        .stApp { background: #0a0e1a; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Inicializar DB + seed
init_db(seed=True)

# Encabezado
col_title, _ = st.columns([3, 1])
with col_title:
    st.markdown(
        "<h2 style='margin:0;color:#e5e7eb;'>📊 TuPortafolioIA</h2>"
        "<p style='margin:0;color:#9ca3af;font-size:0.9rem;'>"
        "Seguimiento y analisis de portafolio — contexto argentino</p>",
        unsafe_allow_html=True,
    )

# Navegacion horizontal estilo screenshot
selected = option_menu(
    menu_title=None,
    options=["Dashboard", "Allocation", "Performance", "Rebalanceo", "Contexto AR"],
    icons=["bar-chart-fill", "pie-chart-fill", "graph-up-arrow",
           "sliders", "flag-fill"],
    orientation="horizontal",
    default_index=0,
    styles={
        "container": {
            "padding": "0.4rem 0",
            "background-color": "#0a0e1a",
            "border-bottom": "1px solid #1f2937",
            "margin-bottom": "1rem",
        },
        "icon": {"color": "#22c55e", "font-size": "1rem"},
        "nav-link": {
            "color": "#9ca3af",
            "font-size": "0.95rem",
            "text-align": "center",
            "margin": "0 0.25rem",
            "padding": "0.5rem 1rem",
            "border-radius": "0.5rem",
            "--hover-color": "#111827",
        },
        "nav-link-selected": {
            "background-color": "#111827",
            "color": "#ffffff",
            "font-weight": "600",
        },
    },
)

# Router
if selected == "Dashboard":
    dashboard.render()
elif selected == "Allocation":
    allocation.render()
elif selected == "Performance":
    performance.render()
elif selected == "Rebalanceo":
    rebalanceo.render()
elif selected == "Contexto AR":
    contexto_ar.render()
