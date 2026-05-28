"""
Sistema de diseño premium: CSS global, helpers de KPI cards en HTML,
formato de numeros y styling de figuras Plotly.
"""
import pandas as pd
import streamlit as st

# Paleta central (coherente con .streamlit/config.toml)
ACCENT  = "#34d399"
POS     = "#34d399"
NEG     = "#fb7185"
TEXT    = "#e8edf5"
DIM     = "#8b96a8"
GRID    = "rgba(255,255,255,0.05)"

def inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=Onest:wght@400;500;600&display=swap');

        :root{
            --bg:#07090f; --surface:#0d121e; --surface2:#131a2a;
            --border:rgba(255,255,255,0.07); --border-hover:rgba(52,211,153,0.35);
            --text:#e8edf5; --dim:#8b96a8; --faint:#5a6478;
            --accent:#34d399; --pos:#34d399; --neg:#fb7185; --radius:16px;
        }
        html, body, [class*="css"]{ font-family:'Onest',sans-serif; }
        .stApp{ background:
            radial-gradient(1200px 600px at 20% -10%, rgba(52,211,153,0.06), transparent 60%),
            var(--bg); }
        .block-container{ padding-top:1.2rem; padding-bottom:2.5rem; max-width:1280px; }
        h1,h2,h3,h4{ font-family:'Sora',sans-serif !important; letter-spacing:-0.02em; color:var(--text); }

        /* KPI cards */
        .kpi-grid{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:0.2rem 0 0.6rem; }
        @media (max-width:900px){ .kpi-grid{ grid-template-columns:repeat(2,1fr);} }
        .kpi{
            background:linear-gradient(160deg, var(--surface2), var(--surface));
            border:1px solid var(--border); border-radius:var(--radius);
            padding:1.15rem 1.3rem; transition:all .25s ease; position:relative; overflow:hidden;
        }
        .kpi:hover{ border-color:var(--border-hover); transform:translateY(-2px);
            box-shadow:0 12px 30px -12px rgba(52,211,153,0.25); }
        .kpi-label{ font-size:.72rem; letter-spacing:.08em; text-transform:uppercase;
            color:var(--dim); margin-bottom:.55rem; font-weight:600; }
        .kpi-value{ font-family:'Sora',sans-serif; font-weight:700; font-size:1.7rem;
            color:var(--text); font-variant-numeric:tabular-nums; line-height:1.1; }
        .kpi-delta{ margin-top:.5rem; display:inline-flex; align-items:center; gap:.3rem;
            font-size:.85rem; font-weight:600; padding:.15rem .5rem; border-radius:999px;
            font-variant-numeric:tabular-nums; }
        .kpi-delta.pos{ color:var(--pos); background:rgba(52,211,153,0.12); }
        .kpi-delta.neg{ color:var(--neg); background:rgba(251,113,133,0.12); }

        /* Tabla de posiciones custom */
        .pos-table{ width:100%; border-collapse:separate; border-spacing:0 6px; }
        .pos-table th{ font-size:.72rem; text-transform:uppercase; letter-spacing:.06em;
            color:var(--faint); text-align:right; padding:.2rem .9rem; font-weight:600; }
        .pos-table th:first-child{ text-align:left; }
        .pos-table td{ background:var(--surface); padding:.7rem .9rem; text-align:right;
            font-variant-numeric:tabular-nums; color:var(--text); border-top:1px solid var(--border);
            border-bottom:1px solid var(--border); }
        .pos-table td:first-child{ text-align:left; border-left:1px solid var(--border);
            border-radius:10px 0 0 10px; }
        .pos-table td:last-child{ border-right:1px solid var(--border); border-radius:0 10px 10px 0; }
        .tk-badge{ font-family:'Sora',sans-serif; font-weight:600; }
        .tk-tipo{ color:var(--faint); font-size:.78rem; margin-left:.4rem; }
        .pnl-pos{ color:var(--pos); } .pnl-neg{ color:var(--neg); }

        /* Limpiar header default de Streamlit */
        [data-testid="stHeader"]{ background:transparent; }
        #MainMenu, footer{ visibility:hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )

def fmt_money(v, simbolo="$"):
    if v is None or pd.isna(v):
        return "—"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{simbolo} {s}"

def fmt_pct(v):
    if v is None or pd.isna(v):
        return "—"
    return f"{v:+.2f}%"

def kpi_card(label, value, delta=None, positive=True):
    delta_html = ""
    if delta:
        cls = "pos" if positive else "neg"
        arrow = "▲" if positive else "▼"
        delta_html = f'<div class="kpi-delta {cls}">{arrow} {delta}</div>'
    return (
        f'<div class="kpi"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>{delta_html}</div>'
    )

def kpi_row(cards_html):
    st.markdown(f'<div class="kpi-grid">{"".join(cards_html)}</div>',
                unsafe_allow_html=True)

def style_fig(fig, height=320):
    """Aplica el tema premium a cualquier figura Plotly."""
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=10, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Onest, sans-serif", color=DIM, size=12),
        xaxis=dict(gridcolor=GRID, zeroline=False),
        yaxis=dict(gridcolor=GRID, zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig
