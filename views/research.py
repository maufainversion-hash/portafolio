"""
Vista Research IA: genera reportes institucionales con Google Gemini.

Flow:
1. Si no hay API key, mostrar input para que el usuario la pegue.
2. Selector de tipo de reporte + modelo.
3. Boton "Generar reporte".
4. Streaming en vivo del markdown generado.
5. Persiste el ultimo reporte en session_state para no perderlo al navegar.
"""
import streamlit as st

from core.ai import (
    KINDS, MODELOS, DEFAULT_MODEL, NIVELES,
    has_api_key, generate_report_stream,
)
from core.ai_data import build_portfolio_context
from core.pdf import markdown_to_pdf
from core.pdf_charts import build_all_charts


def render():
    from core.active_portfolio import get_active_portfolio_label
    st.subheader("Research IA")
    st.caption(
        f"Reporte sobre: **{get_active_portfolio_label()}** · "
        "Cambia el portfolio desde el selector arriba a la derecha."
    )

    _bloque_api_key()

    if not has_api_key():
        st.info(
            "Para generar reportes, configura tu API key de Gemini arriba. "
            "Podes obtener una gratuita en [aistudio.google.com/apikey]"
            "(https://aistudio.google.com/apikey)."
        )
        return

    # Selectores
    c1, c2 = st.columns(2)
    with c1:
        kind_label = st.selectbox(
            "Tipo de reporte",
            options=list(KINDS.keys()),
            format_func=lambda k: f"{KINDS[k]['label']} — {KINDS[k]['description']}",
            key="ai_kind",
        )
    with c2:
        nivel_label = st.selectbox(
            "Nivel de complejidad del lenguaje",
            options=list(NIVELES.keys()),
            format_func=lambda n: f"{NIVELES[n]['label']} — {NIVELES[n]['description']}",
            index=1,  # intermedio por default
            key="ai_nivel",
        )
    c3, c4 = st.columns([2, 1])
    with c3:
        modelo_label = st.selectbox(
            "Modelo Gemini",
            options=list(MODELOS.keys()),
            key="ai_modelo",
        )
        modelo = MODELOS[modelo_label]
    with c4:
        st.markdown("<div style='height:1.75rem;'></div>", unsafe_allow_html=True)
        generar = st.button("Generar reporte", type="primary",
                            use_container_width=True)

    # Render del ultimo reporte (si hay)
    if generar:
        _generar(kind_label, modelo, nivel_label)
    elif "ai_last_report" in st.session_state:
        st.divider()
        st.caption(
            f"Ultimo reporte: **{st.session_state.get('ai_last_kind_label', '?')}** "
            f"· modelo: {st.session_state.get('ai_last_modelo', '?')}"
        )
        _render_report(st.session_state["ai_last_report"])


def _bloque_api_key():
    """Input de API key con boton para guardar en session_state."""
    with st.expander("🔑 Configurar API key de Gemini",
                     expanded=not has_api_key()):
        st.markdown(
            "Obtene una key gratis en "
            "[Google AI Studio](https://aistudio.google.com/apikey). "
            "Tambien podes definirla en `.streamlit/secrets.toml` "
            "con `GEMINI_API_KEY = \"...\"` o como variable de entorno "
            "`GEMINI_API_KEY`."
        )
        col_a, col_b = st.columns([3, 1])
        with col_a:
            key_input = st.text_input(
                "API key", type="password",
                value=st.session_state.get("gemini_api_key", ""),
                placeholder="AIza...",
                key="gemini_api_key_input",
                label_visibility="collapsed",
            )
        with col_b:
            if st.button("Guardar", use_container_width=True):
                st.session_state["gemini_api_key"] = key_input.strip()
                st.rerun()
        if has_api_key():
            st.success("✔ API key configurada para esta sesion.")


def _generar(kind: str, modelo: str, nivel: str = "intermedio"):
    """Construye el contexto, llama a Gemini en stream y guarda el resultado."""
    with st.spinner("Construyendo contexto del portafolio..."):
        ctx = build_portfolio_context()

    if not ctx.get("portfolio"):
        st.warning("No hay datos suficientes del portafolio para generar un reporte. "
                   "Agrega tenencias desde el tab **Cartera**.")
        return

    st.divider()
    st.caption(
        f"Generando **{KINDS[kind]['label']}** ({NIVELES[nivel]['label']}) "
        f"con `{modelo}` ..."
    )

    # Streaming en vivo
    placeholder = st.empty()
    buffer = ""

    for chunk in generate_report_stream(ctx, kind=kind, model=modelo, nivel=nivel):
        buffer += chunk
        placeholder.markdown(buffer + " ▌")

    placeholder.markdown(buffer)

    # Heuristica: si el output empieza con "**Error" o tiene menos de 200 chars
    # probablemente es un mensaje de error, no un reporte real.
    es_error = (
        buffer.lstrip().startswith("**")
        and ("error" in buffer.lower()[:120] or
             "cuota" in buffer.lower()[:200] or
             "saturad" in buffer.lower()[:200])
    ) or len(buffer.strip()) < 200

    if es_error:
        # No persistimos errores, no mostramos boton de descarga
        st.info("Cuando el modelo responda, vas a ver el reporte aca y el botón "
                "de descarga. Intentá de nuevo o cambiá de modelo.")
        return

    # Persistimos solo reportes validos
    st.session_state["ai_last_report"] = buffer
    st.session_state["ai_last_kind_label"] = KINDS[kind]["label"]
    st.session_state["ai_last_kind_key"]   = kind
    st.session_state["ai_last_modelo"]     = modelo
    st.session_state["ai_last_nivel"]      = nivel

    _download_buttons(buffer, KINDS[kind]["label"], kind)


def _render_report(md: str):
    """Render premium del markdown del reporte."""
    st.markdown(md)
    kind_key = st.session_state.get("ai_last_kind_key", "reporte")
    kind_label = st.session_state.get("ai_last_kind_label", "Reporte")
    _download_buttons(md, kind_label, kind_key)


def _download_buttons(md_text: str, titulo: str, kind: str):
    """Botones de descarga: PDF enriquecido (principal) + Markdown (secundario)."""
    col_pdf, col_md = st.columns([1, 1])
    with col_pdf:
        try:
            # Re-construir contexto y charts para el PDF (rapido por cache)
            with st.spinner("Armando PDF con gráficos..."):
                ctx = build_portfolio_context()
                charts = build_all_charts(ctx)
                pdf_bytes = markdown_to_pdf(
                    md_text, titulo=titulo,
                    context=ctx, charts=charts,
                    cliente_friendly=True,
                    nivel=st.session_state.get("ai_last_nivel", "intermedio"),
                )
            st.download_button(
                "⬇ Descargar reporte (PDF)",
                data=pdf_bytes,
                file_name=f"reporte_{kind}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary",
            )
        except Exception as e:
            st.error(f"No se pudo generar el PDF: {e}")
    with col_md:
        st.download_button(
            "⬇ Descargar Markdown",
            data=md_text,
            file_name=f"reporte_{kind}.md",
            mime="text/markdown",
            use_container_width=True,
        )
