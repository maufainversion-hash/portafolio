"""
Vista Briefing: motor de noticias financieras con IA.

Layout:
- Header con stats (last update, n items, n sources).
- Generador de briefings IA: tipo + nivel + modelo + boton "Generar".
- Streaming del briefing.
- Boton de PDF del briefing.
- Tabs:
    * Headlines en vivo (cards con filtros region/source/ticker)
    * Watchlist Impact (noticias que tocan tu cartera)
"""
import streamlit as st

from core.news import fetch_all_news, fetch_stats, FEEDS, has_feedparser
from core.news_ai import BRIEF_KINDS, generate_briefing_stream
from core.ai import MODELOS, NIVELES, has_api_key, DEFAULT_MODEL
from core.ai_data import build_portfolio_context
from core.pdf import markdown_to_pdf


def render():
    from core.active_portfolio import get_active_portfolio_label
    st.subheader("Briefing IA")
    st.caption(
        "Motor de noticias financieras AR + Global con resumen institucional "
        "automatizado. Cliente activo: "
        f"**{get_active_portfolio_label()}**"
    )

    if not has_feedparser():
        st.error(
            "**Falta el paquete `feedparser`.** Streamlit Cloud todavia no "
            "instaló todas las dependencias. Esperá 1-2 min y refrescá la "
            "página, o reiniciá la app desde **Manage app → Reboot**. Si el "
            "problema persiste, revisá los logs de install en Manage app."
        )
        return

    # --- Stats compactas ---
    with st.spinner("Actualizando feeds..."):
        stats = fetch_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Headlines", stats["total"])
    c2.metric("Argentina", stats["ar"])
    c3.metric("Global", stats["global"])
    c4.metric("Fuentes", len(stats["sources"]))

    if st.button("🔄 Refrescar feeds ahora",
                 help="Limpia el cache RSS y vuelve a traer todas las fuentes"):
        # Streamlit caches dont have explicit clear for the wrapped fn,
        # asi que limpiamos todo el cache de data
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # --- Generador de briefings IA ---
    st.markdown("### 🧠 Generar briefing")
    if not has_api_key():
        st.info(
            "Para generar briefings necesitás una API key de Gemini. "
            "Configurala en el tab **Research IA** o en `secrets.toml`."
        )

    c_kind, c_nivel = st.columns(2)
    with c_kind:
        kind = st.selectbox(
            "Tipo de briefing",
            options=list(BRIEF_KINDS.keys()),
            format_func=lambda k: f"{BRIEF_KINDS[k]['label']} — {BRIEF_KINDS[k]['description']}",
            key="news_kind",
        )
    with c_nivel:
        nivel = st.selectbox(
            "Nivel de complejidad",
            options=list(NIVELES.keys()),
            format_func=lambda n: f"{NIVELES[n]['label']}",
            index=1,
            key="news_nivel",
        )
    c_modelo, c_pf, c_btn = st.columns([2, 1, 1])
    with c_modelo:
        modelo_label = st.selectbox(
            "Modelo Gemini",
            options=list(MODELOS.keys()),
            key="news_modelo",
        )
        modelo = MODELOS[modelo_label]
    with c_pf:
        st.markdown("<div style='height:1.75rem;'></div>", unsafe_allow_html=True)
        usar_pf = st.checkbox(
            "Incluir portfolio", value=(kind in ("watchlist", "morning")),
            help="Pasa las posiciones del cliente activo al briefing para análisis de impacto",
        )
    with c_btn:
        st.markdown("<div style='height:1.75rem;'></div>", unsafe_allow_html=True)
        generar = st.button("Generar", type="primary", use_container_width=True,
                            disabled=not has_api_key())

    if generar and has_api_key():
        _generar(kind, modelo, nivel, usar_pf)
    elif "news_last_brief" in st.session_state:
        st.divider()
        st.caption(f"Último briefing: **{st.session_state.get('news_last_kind_label')}** · {st.session_state.get('news_last_modelo')}")
        st.markdown(st.session_state["news_last_brief"])
        _download_briefing(st.session_state["news_last_brief"],
                           st.session_state.get("news_last_kind_label", "briefing"))

    st.divider()

    # --- Tabs con noticias raw ---
    tab_all, tab_ar, tab_global = st.tabs(["📰 Todas", "🇦🇷 Argentina", "🌎 Global"])
    with tab_all:
        _render_news_grid(fetch_all_news("all", limit=80))
    with tab_ar:
        _render_news_grid(fetch_all_news("AR", limit=40))
    with tab_global:
        _render_news_grid(fetch_all_news("Global", limit=60))


# -----------------------------------------------------------------------------
def _generar(kind: str, modelo: str, nivel: str, usar_pf: bool):
    """Genera el briefing en streaming."""
    with st.spinner("Cargando noticias para el briefing..."):
        items = fetch_all_news("all", limit=120)
    if not items:
        st.warning("No hay noticias en este momento.")
        return

    portfolio_ctx = None
    if usar_pf:
        try:
            portfolio_ctx = build_portfolio_context()
        except Exception:
            portfolio_ctx = None

    st.divider()
    st.caption(
        f"Generando **{BRIEF_KINDS[kind]['label']}** "
        f"({NIVELES[nivel]['label']}) con `{modelo}`..."
    )

    placeholder = st.empty()
    buffer = ""
    for chunk in generate_briefing_stream(items, kind=kind, model=modelo,
                                          nivel=nivel,
                                          portfolio_context=portfolio_ctx):
        buffer += chunk
        placeholder.markdown(buffer + " ▌")

    placeholder.markdown(buffer)

    # Heuristica: si es solo error, no persistir
    if (buffer.lstrip().startswith("**") and len(buffer.strip()) < 250) or \
       len(buffer.strip()) < 200:
        return

    st.session_state["news_last_brief"] = buffer
    st.session_state["news_last_kind"] = kind
    st.session_state["news_last_kind_label"] = BRIEF_KINDS[kind]["label"]
    st.session_state["news_last_modelo"] = modelo

    _download_briefing(buffer, BRIEF_KINDS[kind]["label"])


def _download_briefing(md: str, titulo: str):
    """Botones para descargar el briefing (PDF / Markdown)."""
    col_pdf, col_md = st.columns(2)
    with col_pdf:
        try:
            pdf_bytes = markdown_to_pdf(
                md, titulo=titulo,
                context=None, charts=None,   # briefing no usa charts de portfolio
                cliente_friendly=False,
            )
            st.download_button(
                "⬇ Descargar briefing (PDF)",
                data=pdf_bytes,
                file_name=f"briefing_{titulo.lower().replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary",
            )
        except Exception as e:
            st.error(f"Error PDF: {e}")
    with col_md:
        st.download_button(
            "⬇ Descargar Markdown",
            data=md,
            file_name=f"briefing_{titulo.lower().replace(' ', '_')}.md",
            mime="text/markdown",
            use_container_width=True,
        )


# -----------------------------------------------------------------------------
def _render_news_grid(items: list):
    """Cards con las noticias. 2 columnas en grid."""
    if not items:
        st.info("Sin noticias en este corte.")
        return

    # Filtros
    sources = sorted({i["source"] for i in items})
    fc1, fc2 = st.columns([2, 3])
    with fc1:
        src_filter = st.multiselect("Fuente", options=sources,
                                    default=[], key=f"src_f_{id(items)}")
    with fc2:
        text_filter = st.text_input("Buscar", placeholder="Filtrar por palabra (ej: Fed, Milei, IA...)",
                                    key=f"q_f_{id(items)}")

    filtered = items
    if src_filter:
        filtered = [i for i in filtered if i["source"] in src_filter]
    if text_filter:
        q = text_filter.lower()
        filtered = [i for i in filtered
                    if q in i["title"].lower() or q in i["summary"].lower()]

    st.caption(f"{len(filtered)} de {len(items)} headlines")

    # CSS de las cards (una sola vez por render)
    st.markdown("""
    <style>
    .news-card {
        background: linear-gradient(160deg, var(--surface2), var(--surface));
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1rem 1.1rem;
        margin-bottom: 12px;
        transition: all .25s ease;
    }
    .news-card:hover {
        border-color: var(--border-hover);
    }
    .news-card .title {
        font-family: 'Sora', sans-serif;
        font-weight: 600;
        color: var(--text);
        font-size: 1rem;
        line-height: 1.35;
        margin-bottom: .35rem;
    }
    .news-card .summary {
        color: var(--dim);
        font-size: .88rem;
        line-height: 1.45;
        margin-bottom: .55rem;
    }
    .news-card .meta {
        display: flex;
        gap: .4rem;
        flex-wrap: wrap;
        align-items: center;
        font-size: .75rem;
    }
    .news-card .meta .src {
        background: rgba(52,211,153,0.12);
        color: var(--accent);
        padding: .12rem .55rem;
        border-radius: 999px;
        font-weight: 600;
    }
    .news-card .meta .reg {
        background: rgba(255,255,255,0.05);
        color: var(--dim);
        padding: .12rem .55rem;
        border-radius: 999px;
    }
    .news-card .meta .tk {
        background: rgba(96,165,250,0.12);
        color: #60a5fa;
        padding: .12rem .5rem;
        border-radius: 999px;
        font-family: 'Sora', sans-serif;
        font-weight: 600;
    }
    .news-card .meta .when {
        color: var(--faint);
        margin-left: auto;
    }
    </style>
    """, unsafe_allow_html=True)

    # 2 columnas
    cols = st.columns(2)
    for i, it in enumerate(filtered):
        col = cols[i % 2]
        with col:
            _render_card(it)


def _render_card(it: dict):
    """Renderiza una sola card. HTML para el wrapper/badges, markdown nativo
    para el link (asi no se rompe el parser con caracteres en el href)."""
    # Sanitizar todo lo que va al HTML inline
    title = _escape(it.get("title") or "")
    source = _escape(it.get("source") or "")
    region = _escape(it.get("region") or "")
    summary = _escape((it.get("summary") or "")[:220])
    if len(it.get("summary") or "") > 220:
        summary = summary + "…"

    # Tickers como badges
    tickers_html = "".join(
        f'<span class="tk">{_escape(t)}</span>'
        for t in (it.get("tickers") or [])
    )

    when = ""
    if it.get("published"):
        try:
            when = it["published"].strftime("%d %b %H:%M")
        except Exception:
            pass

    # Wrapper sin el link (el link va aparte como markdown nativo)
    st.markdown(
        f'<div class="news-card">'
        f'<div class="title">{title}</div>'
        f'<div class="summary">{summary}</div>'
        f'<div class="meta">'
        f'<span class="src">{source}</span>'
        f'<span class="reg">{region}</span>'
        f'{tickers_html}'
        f'<span class="when">{when}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    # Link como markdown nativo (Streamlit lo escapa solo)
    if it.get("link"):
        st.markdown(
            f'<div style="margin-top:-8px;margin-bottom:14px;padding-left:1.1rem;">'
            f'<a href="{_escape(it["link"])}" target="_blank" '
            f'style="color:#34d399;font-size:.82rem;text-decoration:none;">'
            f'Leer noticia →</a></div>',
            unsafe_allow_html=True,
        )


def _escape(text: str) -> str:
    """HTML-escape robusto. Usa stdlib html.escape para cubrir todos los chars."""
    import html as _html
    if not text:
        return ""
    return _html.escape(str(text), quote=True)
