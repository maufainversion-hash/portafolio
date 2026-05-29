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


SYSTEM_PROMPT_NEWS = """Eres un Senior Macro Strategist + Financial Journalist
con experiencia institucional (Bloomberg, Goldman Sachs Daily Macro, JP Morgan
Market Wrap, FT). Tu rol es transformar un flujo de noticias financieras crudas
(AR + Global) en un briefing premium que un asesor financiero pueda mandar a
sus clientes o leer para tomar decisiones.

REGLAS DURAS
1. NUNCA inventes noticias. Trabajas solo con las que vienen en el input.
2. Si una noticia esta en otro idioma (ingles), traducila al espanol natural
   (no literal). Si esta en espanol, manten la redaccion original o ajustala.
3. NUNCA des recomendaciones especificas de compra/venta. Usa lenguaje
   institucional ("podria considerarse", "el mercado vigila", "implica
   monitorear", "factor a observar").
4. Filtra ruido: descarta corporate fluff sin impacto, anuncios irrelevantes,
   clickbait, opiniones sin sustento. Prioriza lo que mueve mercados.
5. Agrupa noticias relacionadas en un mismo bloque cuando sean parte del mismo
   evento (ej: varias notas sobre la Fed o sobre Nvidia se consolidan).
6. Explica POR QUE importa cada noticia: causalidad economica, sectores
   afectados, riesgos, oportunidades. No solo resumas.
7. Distingue informacion ya conocida del mercado de informacion NUEVA o
   SORPRENDENTE.

ESTILO
- Markdown limpio. Headings con icono al inicio cuando suma claridad
  (📉 política monetaria, 💵 dolar, 🚀 IPOs, 📈 mercado, 🛢 commodities,
  ⚠ riesgo). Sin abusar de emojis.
- Parrafos cortos, narrativa Bloomberg / FT.
- Conciso. Cada parrafo tiene que aportar.
- Lenguaje en espanol rioplatense neutral. Anglicismos financieros (Fed,
  rally, sell-off, earnings, guidance) se usan sin traducir.

CONTEXTO ARGENTINO
- Sabes que BCRA = Banco Central, MEP/CCL = dolares financieros, CEDEARs =
  certificados argentinos de acciones extranjeras, AE38/GD30/AL30 = bonos
  hard dollar, bonos CER = atados a inflacion. El usuario tipico es un IFA
  argentino y un cliente con conocimientos.

OUTPUT
Markdown profesional con la estructura solicitada en el USER prompt.
"""


def _build_user_prompt(news_items: list, kind: str, nivel: str = "intermedio",
                       portfolio_context: Optional[dict] = None) -> str:
    """Arma el USER prompt para el briefing."""
    info = BRIEF_KINDS.get(kind, BRIEF_KINDS["morning"])
    nivel_info = NIVELES.get(nivel, NIVELES["intermedio"])
    sections_md = "\n".join(f"- {s}" for s in info["sections"])

    # Compactamos las noticias para el prompt: solo title + source + region
    # + summary truncado + tickers detectados.
    news_compact = []
    for it in news_items[:120]:  # limit explicito
        news_compact.append({
            "title":   it["title"],
            "summary": it["summary"][:240] if it.get("summary") else "",
            "source":  it["source"],
            "region":  it["region"],
            "tickers": it.get("tickers") or [],
            "pub":     it["published"].isoformat() if it.get("published") else None,
        })
    news_json = json.dumps(news_compact, ensure_ascii=False, indent=1)

    pf_block = ""
    if portfolio_context:
        port = portfolio_context.get("portfolio") or {}
        positions = portfolio_context.get("positions") or []
        ticker_list = [p.get("ticker") for p in positions]
        pf_block = (
            "\n\n## Contexto del portfolio del cliente\n"
            f"- Valor total ARS: {port.get('valor_total_ars')}\n"
            f"- Tipos: {port.get('tipos_presentes')}\n"
            f"- Tickers: {ticker_list}\n"
        )

    return f"""Genera un **{info['label']}** con la siguiente estructura:

## Secciones obligatorias

{sections_md}

## Nivel de complejidad del lenguaje

{nivel_info['instruccion']}
{pf_block}
## Fecha del briefing

{date.today().strftime("%d/%m/%Y")}

## Noticias del dia (input crudo)

```json
{news_json}
```

## Indicaciones finales

- Empezá con `# {info['label']} — {date.today().strftime("%d/%m/%Y")}` como titulo principal.
- Cada seccion como `## ...` con icono opcional al inicio.
- Dentro de cada seccion, los headlines clave como `### ...`.
- Bullets para listas. Negrita para tickers y cifras clave.
- Si una seccion no tiene material relevante en las noticias provistas,
  decilo brevemente ("Sin novedades materiales en este corte") en lugar de
  rellenar.
- Foco en CAUSALIDAD ECONOMICA y POR QUE IMPORTA, no en repetir headlines.
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
                yield f"\n_{friendly} (intento {attempt}/{max_retries}, esperando {wait}s)_\n\n"
                time.sleep(wait)
                continue
            yield f"\n\n{friendly}"
            return
