"""
Cliente de Google Gemini para generar reportes de portafolio institucionales.

API key:
- Streamlit Cloud: st.secrets["GEMINI_API_KEY"]
- Local: env var GEMINI_API_KEY o input en la UI (cached en session_state)

Uso:
    from core.ai import generate_report_stream
    for chunk in generate_report_stream(context_dict, kind="completo"):
        st.write(chunk)
"""
from __future__ import annotations
import os
import json
from typing import Iterator, Optional
import streamlit as st


# Modelo por default. Se puede sobrescribir desde la UI.
DEFAULT_MODEL = "gemini-2.5-flash"

# Modelos disponibles (label -> id)
MODELOS = {
    "Gemini 2.5 Flash (rapido, free tier OK)":  "gemini-2.5-flash",
    "Gemini 2.5 Pro (profundo, requiere pago)": "gemini-2.5-pro",
}

# Modelo de fallback si el principal falla por cuota
FALLBACK_MODEL = "gemini-2.5-flash"


SYSTEM_PROMPT = """Eres un Senior Portfolio Manager con experiencia combinada de:
- Equity Research Analyst (cobertura institucional)
- Quantitative Analyst (factor models, risk attribution)
- Financial Writer (estilo Bloomberg / Morningstar / JP Morgan / BlackRock)

Tu rol es generar reportes institucionales sobre portafolios de inversion
argentinos/globales, con calidad equivalente a research de wealth management
premium (Bloomberg, Morningstar, JPM, BlackRock Aladdin, Goldman PWM, Koyfin,
MSCI Analytics).

INPUT
Recibis un objeto JSON con metricas YA pre-calculadas por el backend:
posiciones valuadas, P&L nominal y real, equity curve summary, volatilidad,
correlaciones, exposiciones, contexto macro argentino, etc.

REGLAS DURAS
1. NUNCA recalcules metricas que ya vienen. Interpreta, contextualiza,
   detecta patrones, explica.
2. NUNCA inventes datos. Si una metrica no esta en el JSON, decilo explicito
   ("dato no disponible en este corte"). Trabaja con lo que hay.
3. NUNCA des consejos especificos de compra/venta individuales. Usa lenguaje
   institucional: "podria considerarse", "seria razonable evaluar", "una
   reduccion marginal de exposicion a X mejoraria el perfil de riesgo".
4. NUNCA uses emojis. NUNCA lenguaje informal o frases infantiles.
5. SI uses lenguaje financiero profesional, sofisticado, elegante.

ESTILO
- Markdown limpio. Titulos jerarquicos (## seccion / ### subseccion), bullets,
  tablas cuando aplique.
- Cada seccion tiene que aportar insight, no solo describir.
- Detecta concentraciones peligrosas, correlaciones altas, sesgos sectoriales,
  exposicion cambiaria, falta de diversificacion real ("falsa diversificacion").
- En contexto argentino entendes: inflacion, dolar (MEP/CCL/blue/cripto/oficial),
  riesgo pais EMBI, tasas, devaluacion, CEDEARs como cobertura cambiaria,
  bonos hard dollar (AE38, GD30, AL30), bonos CER, cobertura inflacionaria.
- Si el JSON trae un bloque "benchmarks", usa siempre EL MISMO PERIODO que la
  equity curve del portfolio para comparar (ya viene calculado asi). Si el
  portfolio rindio X% y un benchmark rindio Y%, la diferencia se expresa en
  puntos porcentuales (pp): "el portfolio rindio X pp por debajo/encima de Z".
  Distingue claramente "rendimiento nominal" (sin descontar inflacion) de
  "rendimiento real" (descontando CER). Para Argentina, la metrica relevante
  es casi siempre la real.

OUTPUT
Markdown profesional. Lenguaje en espanol rioplatense neutral (no anglicismos
forzados, no traduces "Sharpe" o "drawdown" - se usan asi). Estructura segun
el USER PROMPT (la cantidad y orden de secciones la dicta el tipo de reporte).
"""


# Templates de USER PROMPT por tipo de reporte
KINDS = {
    "comparativa": {
        "label": "Performance comparada",
        "description": "Como rindio el portfolio vs Merval, SPY, USD MEP e inflacion",
        "sections": [
            "1. Executive Summary (focused on retorno vs benchmarks)",
            "2. Tabla de retornos del periodo: portfolio, Merval, SPY (USD y ARS), USD MEP buy & hold, inflacion CER. Incluir la diferencia portfolio vs cada benchmark.",
            "3. Performance Analysis (que estrategias hubieran rendido mas y por que). Foco en: si batio o no a la inflacion, si convino vs solo dolar MEP, si convino vs un cedear-only o un equity-only argentino.",
            "4. Risk-adjusted return: contextualiza Sharpe / Sortino / vol del portfolio vs lo que se hubiera obtenido en los benchmarks (a igualdad de riesgo, que hubiera convenido?).",
            "5. AI Insights: 3-5 conclusiones puntuales (ej: 'estar en cedears caros respecto del MEP te costo X pp', 'dolarizar buy&hold hubiera dado Y%').",
            "6. Veredicto final: el portfolio fue eficiente, neutro o ineficiente vs las alternativas pasivas para el periodo? Score (Bueno / Aceptable / Mejorable).",
        ],
    },
    "completo": {
        "label": "Reporte completo",
        "description": "Las 10 secciones del framework institucional",
        "sections": [
            "1. Executive Summary",
            "2. Portfolio Snapshot (valor, retornos, vol, Sharpe, Sortino, MaxDD, beta, alpha, VaR, concentracion top holdings)",
            "3. Performance Analysis (absoluto, relativo, benchmark, attribution, winners & losers, momentum, consistency)",
            "4. Risk Analysis (volatilidad, drawdowns, downside risk, concentracion, correlaciones, sectorial, geografica, monetaria, sensibilidad)",
            "5. Diversification Analysis (real vs falsa diversificacion, overlap sectorial/geografico/cambiario)",
            "6. Argentine Macro Context (inflacion, dolar, riesgo pais, tasas, exposicion ARS, cobertura cambiaria/inflacionaria)",
            "7. Rebalancing Suggestions (racional institucional, no consejos directos)",
            "8. Scenario & Stress Testing (caida S&P, suba tasas USA, crisis AR, devaluacion ARS, caida commodities, rally tech)",
            "9. AI Insights (dependencias ocultas, sesgos, exposicion indirecta, riesgos no obvios, fortalezas estrategicas)",
            "10. Final Portfolio Assessment (evaluacion general, score, calidad, resiliencia)",
        ],
    },
    "executive": {
        "label": "Executive brief",
        "description": "Resumen ejecutivo en una pagina",
        "sections": [
            "1. Executive Summary",
            "2. Portfolio Snapshot",
            "9. AI Insights (3-5 insights clave)",
            "10. Final Portfolio Assessment",
        ],
    },
    "riesgo": {
        "label": "Foco en riesgo",
        "description": "Profundizacion en risk management",
        "sections": [
            "1. Executive Summary (focused on risk)",
            "4. Risk Analysis (extensivo)",
            "5. Diversification Analysis",
            "8. Scenario & Stress Testing",
            "9. AI Insights de riesgo",
        ],
    },
    "macro": {
        "label": "Foco macro AR",
        "description": "Posicionamiento ante el contexto argentino",
        "sections": [
            "1. Executive Summary",
            "6. Argentine Macro Context (extensivo)",
            "4. Risk Analysis (con foco en exposicion cambiaria/inflacionaria)",
            "7. Rebalancing Suggestions (foco en cobertura)",
        ],
    },
    "rebalanceo": {
        "label": "Foco en rebalanceo",
        "description": "Plan de optimizacion del portafolio",
        "sections": [
            "1. Executive Summary",
            "5. Diversification Analysis",
            "7. Rebalancing Suggestions (extensivo, con racional cuantitativo)",
            "9. AI Insights de optimizacion",
        ],
    },
}


# -----------------------------------------------------------------------------
# API KEY
# -----------------------------------------------------------------------------
def get_api_key() -> Optional[str]:
    """
    Busca la API key en orden:
    1. st.session_state["gemini_api_key"] (input en UI)
    2. st.secrets["GEMINI_API_KEY"] (Streamlit Cloud)
    3. os.environ["GEMINI_API_KEY"] (local)
    """
    if "gemini_api_key" in st.session_state and st.session_state["gemini_api_key"]:
        return st.session_state["gemini_api_key"]
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY")


def has_api_key() -> bool:
    return bool(get_api_key())


# -----------------------------------------------------------------------------
# GENERACION
# -----------------------------------------------------------------------------
def _build_user_prompt(context: dict, kind: str) -> str:
    """Arma el USER prompt con la estructura solicitada y el context JSON."""
    kind_info = KINDS.get(kind, KINDS["completo"])
    sections_md = "\n".join(f"- {s}" for s in kind_info["sections"])

    context_json = json.dumps(context, ensure_ascii=False, indent=2, default=str)

    return f"""Genera un **{kind_info['label']}** sobre el siguiente portafolio.

## Secciones obligatorias (en este orden)

{sections_md}

## Datos del portafolio (JSON)

```json
{context_json}
```

## Indicaciones finales

- Comenza el reporte directamente con la primera seccion (sin titulo global).
- Cada seccion debe aportar interpretacion + insight, no descripcion lineal.
- Si encontras una concentracion >20% en un solo activo, una correlacion alta
  con un solo factor, una exposicion cambiaria sesgada o un gap significativo
  contra benchmarks, destacalo en la seccion correspondiente.
- En "Argentine Macro Context", considera la brecha cambiaria, la inflacion
  acumulada YTD/interanual, el riesgo pais EMBI y la evolucion del Merval que
  vienen en el JSON.
- En "Final Portfolio Assessment", asigna un score subjetivo (Bajo / Medio /
  Alto) a: calidad de diversificacion, perfil riesgo-retorno, resiliencia
  macroeconomica.
"""


def _friendly_error(err: Exception, model: str) -> tuple[str, bool]:
    """
    Traduce un error de Gemini a un mensaje amigable + flag de "es transient"
    (True si vale la pena reintentar).
    """
    msg = str(err)
    # 503 - servicio saturado (transient)
    if "503" in msg or "UNAVAILABLE" in msg.upper():
        return (
            "El modelo está saturado momentáneamente (demanda alta del lado de Google). "
            "Estamos reintentando automáticamente...",
            True,
        )
    # 429 - cuota agotada
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg.upper():
        # Distinguir: limit 0 (modelo no incluido en el free tier) vs limit > 0 (espera)
        if "limit: 0" in msg or "FreeTier" in msg and "Pro" in model:
            return (
                f"**Cuota agotada para `{model}`.** El **free tier de Google no "
                f"incluye Gemini 2.5 Pro** — solo Flash. Opciones:\n\n"
                f"- Cambiá el modelo a **Gemini 2.5 Flash** en el selector "
                f"de arriba (sí está incluido en el free tier).\n"
                f"- O activá billing en [aistudio.google.com]"
                f"(https://aistudio.google.com/apikey) para habilitar Pro.",
                False,
            )
        # Quota por minuto/dia
        return (
            f"Cuota del free tier agotada (por minuto o por día). Esperá "
            f"unos minutos antes de reintentar, o cambiá a un modelo con "
            f"menos demanda. Detalle técnico: `{msg[:200]}...`",
            False,
        )
    # 401/403 - auth
    if any(x in msg for x in ["401", "403", "API key not valid", "PERMISSION_DENIED"]):
        return (
            "La API key no es válida o no tiene permisos sobre Gemini. "
            "Verificá que copiaste bien la key en `secrets.toml` y que "
            "tenga habilitado el acceso a la Gemini API.",
            False,
        )
    return (f"Error inesperado: `{msg[:300]}`", False)


def generate_report_stream(context: dict, kind: str = "completo",
                           model: str = DEFAULT_MODEL) -> Iterator[str]:
    """
    Genera un reporte usando Gemini en modo streaming.
    - Yieldea chunks de texto a medida que llegan.
    - Reintenta automáticamente hasta 2 veces ante errores 503 (servicio saturado).
    - Traduce errores 429/503/401 a mensajes amigables.
    """
    import time

    api_key = get_api_key()
    if not api_key:
        yield ("**Falta configurar la API key de Gemini.** Pega tu key en el "
               "campo de configuracion de arriba, o configurala en "
               "`.streamlit/secrets.toml` con `GEMINI_API_KEY = \"...\"`.")
        return

    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError:
        yield "**Falta instalar `google-genai`.** Corre `pip install google-genai`."
        return

    client = genai.Client(api_key=api_key)
    user_prompt = _build_user_prompt(context, kind)
    config = gtypes.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.4,
        max_output_tokens=8192,
    )

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        any_chunk_received = False
        try:
            response = client.models.generate_content_stream(
                model=model,
                contents=user_prompt,
                config=config,
            )
            for chunk in response:
                text = getattr(chunk, "text", None)
                if text:
                    any_chunk_received = True
                    yield text
            # Si llegamos hasta acá sin excepción, la generación terminó OK
            return
        except Exception as e:
            friendly, transient = _friendly_error(e, model)
            if any_chunk_received:
                # Falló en el medio, no podemos reintentar limpio
                yield f"\n\n**Error en medio de la generación:** {friendly}"
                return
            if transient and attempt < max_retries:
                wait = 2 * attempt  # 2s, 4s
                yield f"\n_{friendly} (intento {attempt}/{max_retries}, esperando {wait}s)_\n\n"
                time.sleep(wait)
                continue
            yield f"\n\n{friendly}"
            return
