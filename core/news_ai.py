"""
Generador de briefings financieros con Gemini.

Toma una lista de noticias (output de core.news.fetch_all_news) y un opcional
contexto de portfolio, y produce un Morning Review / Evening Wrap / etc.

Reusa el cliente y la API key de core.ai.
"""
from __future__ import annotations
import json
from datetime import date
from typing import Iterator, Optional

from core.ai import (
    get_api_key, _friendly_error,
    DEFAULT_MODEL, MODELOS, NIVELES,
)


# Tipos de briefings disponibles
BRIEF_KINDS = {
    "morning": {
        "label": "Morning Review",
        "description": "Briefing de apertura: lo que paso anoche y lo que hay que mirar hoy",
        "sections": [
            "1. Resumen ejecutivo (3-5 puntos clave de la jornada/agenda)",
            "2. Argentina (politica monetaria, dolar, BCRA, riesgo pais, BYMA, "
            "bonos, sectores destacados)",
            "3. Mercados globales (Fed, ECB, China, geopolitica, earnings, "
            "tecnologia/IA, commodities, bonos USA, crypto)",
            "4. Macro Trends detectadas (risk-on/off, presion inflacionaria, "
            "rotacion sectorial, themes dominantes)",
            "5. Watchlist Impact (si hay portfolio context, como impacta la "
            "informacion en las posiciones del cliente; sino, omitir)",
        ],
    },
    "evening": {
        "label": "Evening Wrap",
        "description": "Cierre del dia: que pasó hoy y por que importa",
        "sections": [
            "1. Resumen ejecutivo del cierre",
            "2. Argentina (lo que se movio en BYMA, MEP/CCL, riesgo pais, bonos)",
            "3. Wall Street y mercados globales (cierres clave, sectores ganadores/perdedores)",
            "4. Eventos relevantes del dia y sus implicancias",
            "5. Look-ahead (que hay que mirar manana / esta semana)",
        ],
    },
    "argentina": {
        "label": "Argentina Daily Brief",
        "description": "Solo Argentina, mas en profundidad",
        "sections": [
            "1. Resumen ejecutivo macro AR (foco politica monetaria + cambiaria + fiscal)",
            "2. Mercado local: BYMA, Merval, bonos hard dollar (AE38, GD30, AL30), bonos CER, "
            "panel general y CEDEARs lideres",
            "3. Dolar: oficial, MEP, CCL, blue, brecha y dinamica reciente",
            "4. Sectores destacados (energia, agro, bancos, real estate)",
            "5. Eventos politicos / regulatorios con impacto en mercados",
            "6. Watchlist Impact si hay portfolio context",
        ],
    },
    "global": {
        "label": "Global Macro Brief",
        "description": "Foco global: Fed, China, earnings, IA, commodities",
        "sections": [
            "1. Resumen ejecutivo macro global",
            "2. Fed / ECB / BoJ / PBoC: politica monetaria, expectativas de tasas",
            "3. Wall Street: indices principales, earnings relevantes, sectores en movimiento",
            "4. China y emergentes",
            "5. Geopolitica con impacto financiero (Medio Oriente, Ucrania, Taiwan, comercio)",
            "6. Commodities (petroleo, oro, granos) y crypto",
        ],
    },
    "themes": {
        "label": "AI Theme Detection",
        "description": "Que temas dominan el flujo de noticias hoy",
        "sections": [
            "1. Top 3-5 themes dominantes detectados en el flujo de noticias "
            "(ej: AI boom, energia nuclear, space economy, de-dollarization, "
            "commodity cycle, EM rally, etc).",
            "2. Por cada theme: evidencia (que noticias lo respaldan), sectores "
            "/ tickers expuestos, momentum (en aceleracion o consolidando), "
            "riesgos asociados.",
            "3. Conclusion: como podria posicionarse un portfolio diversificado "
            "ante estos themes en el corto plazo.",
        ],
    },
    "watchlist": {
        "label": "Watchlist Impact",
        "description": "Impacto especifico de las noticias en TU portfolio",
        "sections": [
            "1. Resumen: que noticias del feed son relevantes para las posiciones del cliente",
            "2. Por cada ticker del portfolio, si hay alguna noticia que lo impacte "
            "(directa o indirecta), explicar: noticia, magnitud del impacto "
            "(directo/indirecto/sectorial), direccion (positivo/negativo/neutro), "
            "horizonte (intradiario/corto plazo/estructural).",
            "3. Sintesis: alertas accionables (ej: 'monitorear apertura BYMA por "
            "ruido cambiario', 'earnings de XYZ esta semana').",
        ],
    },
}


SYSTEM_PROMPT_NEWS = """Sos un Senior Macro Strategist + Financial Journalist (estilo Bloomberg/Goldman/FT). Transformas noticias crudas en briefings premium para IFAs argentinos y sus clientes.

REGLAS:
- Trabajas SOLO con las noticias del input. Nunca inventes.
- Traducis ingles al espanol natural.
- Nunca recomendaciones directas de compra/venta. Lenguaje institucional ("el mercado vigila", "factor a observar").
- Filtra ruido (corporate fluff, clickbait, anuncios sin impacto). Prioriza lo que mueve mercados.
- Agrupa noticias del mismo evento en un solo bloque.
- Explica POR QUE importa (causalidad, sectores, riesgos, oportunidades), no solo resumas.
- Distingue info ya conocida de info NUEVA o sorprendente.

ESTILO:
- Markdown limpio. Headings con icono donde suma (📉💵🚀📈🛢⚠), sin abusar.
- Parrafos cortos, narrativa Bloomberg/FT, conciso. Espanol rioplatense neutral. Anglicismos financieros (Fed, rally, sell-off, earnings) se mantienen.

CONTEXTO AR: BCRA, MEP/CCL, CEDEARs (acciones extranjeras en pesos), AE38/GD30/AL30 (bonos hard dollar), bonos CER (atan a inflacion).
"""


def _build_user_prompt(news_items: list, kind: str, nivel: str = "intermedio",
                       portfolio_context: Optional[dict] = None) -> str:
    """Arma el USER prompt para el briefing. Formato compacto para minimizar tokens."""
    info = BRIEF_KINDS.get(kind, BRIEF_KINDS["morning"])
    nivel_info = NIVELES.get(nivel, NIVELES["intermedio"])
    sections_md = "\n".join(f"- {s}" for s in info["sections"])

    # Formato compacto: una linea por noticia. [AR|Src] Title — Summary (TK)
    # + dedup soft por prefijo de titulo (mismo evento en varios feeds).
    seen_prefixes = set()
    lines = []
    for it in news_items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        # Dedup: si los primeros 50 chars del titulo ya aparecieron, skip
        key = title[:50].lower()
        if key in seen_prefixes:
            continue
        seen_prefixes.add(key)

        region = "AR" if it["region"] == "AR" else "GL"
        src = it["source"]
        # Summary mas corto (110 chars). Si esta vacio, no agregamos separador.
        summary = (it.get("summary") or "")[:110]
        tickers = it.get("tickers") or []
        tk_str = f" ({','.join(tickers)})" if tickers else ""
        sum_str = f" — {summary}" if summary else ""
        lines.append(f"[{region}|{src}] {title}{sum_str}{tk_str}")
        if len(lines) >= 70:  # cap a 70 items unicos
            break
    news_block = "\n".join(lines)

    pf_block = ""
    if portfolio_context:
        positions = portfolio_context.get("positions") or []
        # Solo tickers y tipos, sin datos financieros extra
        tickers = [p.get("ticker") for p in positions if p.get("ticker")]
        tipos = sorted({p.get("tipo") for p in positions if p.get("tipo")})
        if tickers:
            pf_block = (f"\n## Portfolio del cliente\n"
                        f"Tickers: {','.join(tickers)}. Tipos: {','.join(tipos)}.\n")

    return f"""Genera **{info['label']}** ({date.today().strftime("%d/%m/%Y")}).

## Estructura obligatoria
{sections_md}

## Nivel de lenguaje
{nivel_info['instruccion']}
{pf_block}
## Noticias del dia ({len(lines)} headlines)

{news_block}

## Formato de salida
- Titulo `# {info['label']} — {date.today().strftime("%d/%m/%Y")}`.
- Secciones `## ...` con icono donde suma claridad.
- Headlines clave como `### ...`.
- Bullets, negrita para tickers y cifras.
- Si una seccion no tiene material relevante, "Sin novedades materiales en este corte" (no rellenes).
- Foco en CAUSALIDAD y POR QUE IMPORTA, no repetir headlines.
"""


def generate_briefing_stream(news_items: list, kind: str = "morning",
                             model: str = DEFAULT_MODEL,
                             nivel: str = "intermedio",
                             portfolio_context: Optional[dict] = None) -> Iterator[str]:
    """Genera un briefing usando Gemini en streaming."""
    import time
    api_key = get_api_key()
    if not api_key:
        yield ("**Falta configurar la API key de Gemini.** Configurala en el "
               "tab **Research IA** o en `.streamlit/secrets.toml`.")
        return
    if not news_items:
        yield "**Sin noticias para procesar.** Refrescá el feed primero."
        return

    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError:
        yield "**Falta `google-genai`.** Corre `pip install google-genai`."
        return

    client = genai.Client(api_key=api_key)
    user_prompt = _build_user_prompt(news_items, kind, nivel, portfolio_context)
    config = gtypes.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT_NEWS,
        temperature=0.35,
        max_output_tokens=8192,
    )

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        any_chunk = False
        try:
            resp = client.models.generate_content_stream(
                model=model, contents=user_prompt, config=config,
            )
            for chunk in resp:
                text = getattr(chunk, "text", None)
                if text:
                    any_chunk = True
                    yield text
            return
        except Exception as e:
            friendly, transient = _friendly_error(e, model)
            if any_chunk:
                yield f"\n\n**Error en medio:** {friendly}"
                return
            if transient and attempt < max_retries:
                wait = 2 * attempt
                # Marcamos los mensajes de retry con un prefijo invisible
                # (zero-width space + tag) para que la UI pueda filtrarlos.
                yield (f"\n<!-- retry -->_{friendly} "
                       f"(intento {attempt}/{max_retries}, esperando {wait}s)_\n\n")
                time.sleep(wait)
                continue
            # Fallo final: marcamos como error para que la UI no persista
            yield f"\n<!-- error-final -->\n\n**No se pudo generar el briefing.** {friendly}"
            return
