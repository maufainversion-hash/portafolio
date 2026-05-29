"""
Agregador de noticias financieras AR + Global via RSS.

Diseño:
- Lista curada de feeds que sabemos que responden bien.
- Cache de 15 min por feed (st.cache_data).
- Cada item normalizado a dict: {id, title, summary, source, region,
  link, published_at, tickers}.
- fetch_all_news(region=...) trae todo agrupado y ordenado por fecha desc.
"""
from __future__ import annotations
import hashlib
import re
from datetime import datetime, timezone
from typing import Optional
import streamlit as st

# Import defensivo: si feedparser no esta instalado (puede pasar si Streamlit
# Cloud no termino de instalar las deps del ultimo redeploy), la app no debe
# crashear entera. has_feedparser() permite a las vistas mostrar un mensaje
# amable en lugar de un traceback rojo.
try:
    import feedparser
    _HAS_FEEDPARSER = True
except ImportError:
    feedparser = None
    _HAS_FEEDPARSER = False


def has_feedparser() -> bool:
    return _HAS_FEEDPARSER


# Lista curada de feeds. (label, url, region)
FEEDS = [
    # Argentina
    ("Ámbito Economía",   "https://www.ambito.com/rss/economia.xml", "AR"),
    ("Ámbito Finanzas",   "https://www.ambito.com/rss/finanzas.xml", "AR"),
    # Global
    ("Yahoo Finance",     "https://finance.yahoo.com/news/rssindex", "Global"),
    ("MarketWatch",       "http://feeds.marketwatch.com/marketwatch/topstories", "Global"),
    ("CNBC Top",          "https://www.cnbc.com/id/100003114/device/rss/rss.html", "Global"),
    ("CNBC Business",     "https://www.cnbc.com/id/10001147/device/rss/rss.html", "Global"),
    ("Investing.com",     "https://www.investing.com/rss/news.rss", "Global"),
    ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss", "Global"),
    ("FT Markets",        "https://www.ft.com/markets?format=rss", "Global"),
    ("WSJ Markets",       "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "Global"),
]


# Regex simple para detectar tickers en mayusculas dentro del titulo
# (ej: "Apple (AAPL) ...", "Tesla shares jump", "Bitcoin")
_TICKER_PATTERN = re.compile(r"\b([A-Z]{2,5})\b")
_KNOWN_TICKERS = {
    # Big tech / mainstream
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "NFLX",
    "AMD", "INTC", "ORCL", "CRM", "ADBE", "AVGO", "QCOM", "DELL",
    # Banks / financials
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "BX",
    # Otros
    "BRKB", "V", "MA", "PYPL", "DIS", "KO", "PEP", "WMT", "MCD",
    "BA", "CAT", "LMT", "RTX", "PFE", "JNJ", "UNH", "TM", "BABA",
    # Indices / ETFs
    "SPY", "QQQ", "DIA", "VTI", "EEM", "GLD", "TLT", "FXI",
    # Crypto
    "BTC", "ETH", "SOL", "DOGE",
    # AR / locales que pueden aparecer
    "MELI", "GGAL", "YPF", "PAMP", "TXAR", "BMA",
}


def _hash_id(text: str) -> str:
    """ID estable a partir del link o titulo."""
    return hashlib.md5(text.encode("utf-8", "replace")).hexdigest()[:12]


def _clean_html(text: str) -> str:
    """Strip HTML tags + decode entities + trim. Robusto a HTML mal formado."""
    if not text:
        return ""
    import html as _html
    # 1. Decode HTML entities (&amp;, &nbsp;, etc) primero
    text = _html.unescape(text)
    # 2. Quitar tags (cualquier <...>)
    text = re.sub(r"<[^>]*>", " ", text)
    # 3. Quitar caracteres de control que rompen markdown/HTML downstream
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    # 4. Quitar pares de comillas/angulares sueltos que escaparon a tags
    text = text.replace("<", "").replace(">", "")
    # 5. Whitespace collapse
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_tickers(title: str, summary: str) -> list[str]:
    """Extrae tickers conocidos del headline y summary."""
    text = f"{title} {summary}"
    found = set()
    for m in _TICKER_PATTERN.finditer(text):
        sym = m.group(1)
        if sym in _KNOWN_TICKERS:
            found.add(sym)
    return sorted(found)


def _parse_date(entry) -> Optional[datetime]:
    """Extrae el datetime del entry, robusto a varios formatos."""
    for key in ("published_parsed", "updated_parsed"):
        v = entry.get(key)
        if v:
            try:
                return datetime(*v[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


@st.cache_data(ttl=900, show_spinner=False)
def _fetch_feed(url: str, source: str, region: str) -> list[dict]:
    """Trae un feed y normaliza items. Devuelve lista (puede estar vacia)."""
    if not _HAS_FEEDPARSER:
        return []
    try:
        f = feedparser.parse(url)
        out = []
        for e in f.entries[:30]:  # max 30 por feed
            title = _clean_html(e.get("title", "")).strip()
            if not title:
                continue
            summary = _clean_html(e.get("summary", "") or e.get("description", ""))
            if len(summary) > 600:
                summary = summary[:600] + "…"
            link = e.get("link", "")
            published = _parse_date(e)
            out.append({
                "id":         _hash_id(link or title),
                "title":      title,
                "summary":    summary,
                "source":     source,
                "region":     region,
                "link":       link,
                "published":  published,
                "tickers":    _extract_tickers(title, summary),
            })
        return out
    except Exception:
        return []


def fetch_all_news(region: str = "all", limit: int = 80) -> list[dict]:
    """
    Trae noticias de todos los feeds configurados.
    region: 'all' | 'AR' | 'Global'.
    Ordena por fecha desc y trunca a `limit`.
    """
    all_items = []
    for source, url, src_region in FEEDS:
        if region != "all" and src_region != region:
            continue
        items = _fetch_feed(url, source, src_region)
        all_items.extend(items)

    # Ordenar por fecha desc (los sin fecha al final)
    def _sort_key(it):
        dt = it.get("published")
        return dt if dt else datetime(1970, 1, 1, tzinfo=timezone.utc)
    all_items.sort(key=_sort_key, reverse=True)

    return all_items[:limit]


def fetch_stats() -> dict:
    """Stats del cache: cuantos feeds OK, cuantos items por region."""
    items = fetch_all_news("all", limit=500)
    return {
        "total":  len(items),
        "ar":     sum(1 for i in items if i["region"] == "AR"),
        "global": sum(1 for i in items if i["region"] == "Global"),
        "sources": sorted({i["source"] for i in items}),
        "last_update": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
