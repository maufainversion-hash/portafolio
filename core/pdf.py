"""
Generador de PDF institucional estilo banking (cabecera azul oscura, KPIs en
barras, tablas con header oscuro, etc).

Inspirado en informes de cartera de Balanz / IOL / PPI. Usa fpdf2 con DejaVu
para soporte Unicode (✓, →, ±, …) y matplotlib charts ya generados como PNG.
"""
from __future__ import annotations
import io
import os
import re
from datetime import datetime
from typing import Optional
from fpdf import FPDF
from fpdf.enums import XPos, YPos


# ===================== PALETA "BANKING" =====================
COLOR_HEADER_BG  = (15, 36, 64)      # azul oscuro casi negro
COLOR_HEADER_TXT = (255, 255, 255)   # blanco
COLOR_ACCENT     = (37, 99, 235)     # azul fuerte (referencia tipo CTA banking)
COLOR_GREEN      = (16, 185, 129)    # verde institucional
COLOR_RED        = (220, 38, 38)     # rojo institucional
COLOR_DARK       = (15, 23, 42)      # azul-grafito para body
COLOR_TEXT       = (30, 41, 59)
COLOR_DIM        = (107, 114, 128)
COLOR_FAINT      = (148, 163, 184)
COLOR_BG_ROW     = (248, 250, 252)
COLOR_BG_TOTAL   = (235, 244, 255)   # azul muy claro para fila TOTAL

# Tipografía Unicode (DejaVu, disponible en Ubuntu/Streamlit Cloud).
# Solo necesitamos Regular y Bold (italic se emula con Regular si falta).
DEJAVU_DIR = "/usr/share/fonts/truetype/dejavu"
DEJAVU_REG = os.path.join(DEJAVU_DIR, "DejaVuSans.ttf")
DEJAVU_BLD = os.path.join(DEJAVU_DIR, "DejaVuSans-Bold.ttf")
HAS_DEJAVU = os.path.exists(DEJAVU_REG) and os.path.exists(DEJAVU_BLD)


class InstitutionalPDF(FPDF):
    """PDF con header / footer estilo banking + branding del IFA."""

    def __init__(self, titulo: str = "Informe de Cartera",
                 fecha_label: str = "",
                 ifa_profile: Optional[dict] = None,
                 logo_bytes: Optional[bytes] = None):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.titulo = titulo
        self.fecha_label = fecha_label
        self.ifa = ifa_profile or {}
        self.logo_bytes = logo_bytes  # PNG/JPG ya descargado (o None)
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(20, 30, 20)
        # Cargar DejaVu si esta disponible (soporta Unicode)
        if HAS_DEJAVU:
            self.add_font("DejaVu", "", DEJAVU_REG)
            self.add_font("DejaVu", "B", DEJAVU_BLD)
            # No hay Italic regular en DejaVu Sans; usamos la Bold como fallback I.
            self.add_font("DejaVu", "I", DEJAVU_REG)
            self._font = "DejaVu"
        else:
            self._font = "Helvetica"

    def header(self):
        # Banda azul oscura compacta
        self.set_fill_color(*COLOR_HEADER_BG)
        self.rect(0, 0, 210, 18, "F")
        # Logo del IFA a la izquierda si esta
        x_text = 15
        if self.logo_bytes:
            try:
                buf = io.BytesIO(self.logo_bytes)
                self.image(buf, x=15, y=3, h=12)
                x_text = 30
            except Exception:
                pass
        # Titulo
        self.set_xy(x_text, 5)
        self.set_text_color(*COLOR_HEADER_TXT)
        self.set_font(self._font, "B", 12)
        self.cell(120, 6, _safe(self.titulo.upper()))
        # Fecha / subtitulo a la derecha
        self.set_xy(125, 7)
        self.set_font(self._font, "", 9)
        if self.fecha_label:
            self.cell(70, 4, _safe(self.fecha_label), align="R")
        # Espacio bajo banda
        self.set_y(22)

    def footer(self):
        # Linea separadora
        self.set_y(-22)
        self.set_draw_color(*COLOR_FAINT)
        self.set_line_width(0.2)
        self.line(20, self.get_y(), 190, self.get_y())

        # Datos del IFA (si estan configurados)
        ifa_line = self._ifa_footer_line()
        if ifa_line:
            self.set_y(-19)
            self.set_text_color(*COLOR_ACCENT)
            self.set_font(self._font, "B", 8)
            self.cell(0, 3.5, _safe(ifa_line), align="C")

        # Disclaimer (default o el del IFA si lo configuro)
        self.set_y(-15)
        self.set_text_color(*COLOR_DIM)
        self.set_font(self._font, "I", 7)
        disclaimer = self.ifa.get("disclaimer") or (
            "Este informe tiene caracter informativo y educativo. No "
            "constituye asesoramiento financiero ni recomendacion de "
            "compra/venta. Las inversiones en mercados de capitales "
            "conllevan riesgos."
        )
        self.multi_cell(0, 3, _safe(disclaimer), align="C")

        # Numero de pagina
        self.set_y(-7)
        self.set_font(self._font, "", 7.5)
        self.set_text_color(*COLOR_DIM)
        self.cell(0, 3.5, f"pag {self.page_no()}", align="C")

    def _ifa_footer_line(self) -> str:
        """Compone la linea de contacto del IFA en el footer."""
        if not self.ifa:
            return ""
        parts = []
        nombre = self.ifa.get("nombre")
        if nombre:
            parts.append(nombre)
        for key in ("matricula", "empresa", "email", "telefono"):
            v = self.ifa.get(key)
            if v:
                parts.append(v)
        return "  ·  ".join(parts)


# ===================== HELPERS =====================
def _safe(text: str) -> str:
    """Si no hay DejaVu, sanitizamos para latin1. Si hay, dejamos Unicode."""
    if HAS_DEJAVU:
        return text
    replacements = {
        "—": "-", "–": "-", "•": "-", "✓": "OK", "✗": "X",
        "→": "->", "←": "<-", "▲": "^", "▼": "v",
        "“": '"', "”": '"', "‘": "'", "’": "'",
        "🇦🇷": "[AR]", "🇺🇸": "[US]", "🌎": "",
        "📊": "", "📈": "", "📉": "", "💡": "", "🎯": "",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


def _fmt_money(v) -> str:
    if v is None:
        return "—"
    try:
        return f"$ {float(v):,.0f}".replace(",", ".")
    except Exception:
        return str(v)


def _fmt_pct(v, signed: bool = True) -> str:
    if v is None:
        return "—"
    try:
        fmt = "+.2f" if signed else ".2f"
        return f"{float(v):{fmt}}%"
    except Exception:
        return str(v)


# ===================== SECCIONES =====================
def _emit_header_kpis(pdf: InstitutionalPDF, context: dict):
    """3 KPIs grandes con barra coloreada arriba (estilo banking)."""
    port = context.get("portfolio") or {}
    metrics = context.get("metrics") or {}

    valor = port.get("valor_total_ars")
    pnl_pct = port.get("pnl_nominal_pct")
    pnl_real_pct = port.get("pnl_real_pct")

    kpis = [
        ("Valor total", _fmt_money(valor), "en pesos arg.", COLOR_ACCENT),
        ("Rendimiento", _fmt_pct(pnl_pct) if pnl_pct is not None else "—",
         "nominal",
         COLOR_GREEN if (pnl_pct is not None and pnl_pct >= 0) else COLOR_RED),
        ("Rendimiento real", _fmt_pct(pnl_real_pct) if pnl_real_pct is not None else "—",
         "vs inflacion (CER)",
         COLOR_GREEN if (pnl_real_pct is not None and pnl_real_pct >= 0) else COLOR_RED),
    ]

    pdf.ln(2)
    box_w = (pdf.w - pdf.l_margin - pdf.r_margin - 8) / 3  # 8 = gaps
    box_h = 26
    y0 = pdf.get_y()
    for i, (label, valor_str, sub, color) in enumerate(kpis):
        x = pdf.l_margin + i * (box_w + 4)
        # Barra coloreada arriba (4mm de alto)
        pdf.set_fill_color(*color)
        pdf.rect(x, y0, box_w, 2.5, "F")
        # Valor grande
        pdf.set_xy(x, y0 + 5)
        pdf.set_font(pdf._font, "B", 18)
        pdf.set_text_color(*color)
        pdf.cell(box_w, 9, _safe(valor_str), align="L")
        # Label upper case
        pdf.set_xy(x, y0 + 15)
        pdf.set_font(pdf._font, "B", 8)
        pdf.set_text_color(*COLOR_ACCENT)
        pdf.cell(box_w, 4, _safe(label.upper()))
        # Sub-label
        pdf.set_xy(x, y0 + 20)
        pdf.set_font(pdf._font, "I", 8)
        pdf.set_text_color(*COLOR_DIM)
        pdf.cell(box_w, 4, _safe(sub))
    pdf.set_y(y0 + box_h)
    # Linea divisoria
    pdf.set_draw_color(*COLOR_FAINT); pdf.set_line_width(0.3)
    pdf.line(20, pdf.get_y() + 2, 190, pdf.get_y() + 2)
    pdf.ln(8)


def _emit_section_title(pdf: InstitutionalPDF, num: str, titulo: str):
    pdf.ln(4)
    pdf.set_font(pdf._font, "B", 14)
    pdf.set_text_color(*COLOR_ACCENT)
    pdf.cell(0, 7, _safe(f"{num}. {titulo}"),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)


def _emit_resumen_table(pdf: InstitutionalPDF, context: dict):
    """Tabla 'Evolucion de la cartera' tipo estado de cuenta."""
    port = context.get("portfolio") or {}
    metrics = context.get("metrics") or {}
    benchmarks = context.get("benchmarks") or {}

    valor_actual = port.get("valor_total_ars")
    pnl_nominal = port.get("pnl_nominal_ars")
    pnl_real    = port.get("pnl_real_ars")
    inicio_eq   = metrics.get("valor_inicial_ars")
    desde       = metrics.get("equity_curve_desde")
    hasta       = metrics.get("equity_curve_hasta")

    rows = []
    if inicio_eq is not None and desde:
        rows.append((f"Valor inicial al {desde}", _fmt_money(inicio_eq), None))
    if metrics.get("retorno_periodo_pct") is not None:
        rows.append(("Variacion de mercado (periodo)",
                     _fmt_pct(metrics["retorno_periodo_pct"]),
                     metrics["retorno_periodo_pct"]))
    if pnl_nominal is not None:
        rows.append(("Resultado por tenencia (nominal)",
                     _fmt_money(pnl_nominal), pnl_nominal))
    if pnl_real is not None:
        rows.append(("Resultado real (descontando inflacion)",
                     _fmt_money(pnl_real), pnl_real))
    if valor_actual is not None and hasta:
        rows.append((f"VALOR FINAL AL {hasta}",
                     _fmt_money(valor_actual), None))

    if not rows:
        return

    _render_kv_table(pdf, "Concepto", "Monto", rows, last_is_total=True)


def _render_kv_table(pdf: InstitutionalPDF, h1: str, h2: str, rows: list,
                     last_is_total: bool = False):
    """Tabla key-value con header azul oscuro. rows = [(label, str_val, signed_val_or_None)]"""
    page_w = pdf.w - pdf.l_margin - pdf.r_margin
    col_w1 = page_w * 0.62
    col_w2 = page_w * 0.38
    # Header
    pdf.set_font(pdf._font, "B", 9)
    pdf.set_fill_color(*COLOR_HEADER_BG)
    pdf.set_text_color(*COLOR_HEADER_TXT)
    pdf.cell(col_w1, 7, _safe(h1), border=0, fill=True, align="L")
    pdf.cell(col_w2, 7, _safe(h2), border=0, fill=True, align="R")
    pdf.ln()
    # Body
    fill_row = False
    n = len(rows)
    for i, (label, val_str, signed) in enumerate(rows):
        is_total = last_is_total and (i == n - 1)
        if is_total:
            pdf.set_fill_color(*COLOR_BG_TOTAL)
            pdf.set_font(pdf._font, "B", 10)
            pdf.set_text_color(*COLOR_ACCENT)
        else:
            pdf.set_fill_color(*COLOR_BG_ROW if fill_row else (255, 255, 255))
            pdf.set_font(pdf._font, "", 9.5)
            pdf.set_text_color(*COLOR_TEXT)
        pdf.cell(col_w1, 6.5, _safe(label), border=0, fill=True, align="L")
        # Color del valor
        if signed is not None and not is_total:
            try:
                sv = float(signed)
                if sv > 0:
                    pdf.set_text_color(*COLOR_GREEN)
                elif sv < 0:
                    pdf.set_text_color(*COLOR_RED)
            except Exception:
                pass
        pdf.cell(col_w2, 6.5, _safe(val_str), border=0, fill=True, align="R")
        pdf.ln()
        fill_row = not fill_row
    # Linea inferior
    pdf.set_draw_color(*COLOR_HEADER_BG); pdf.set_line_width(0.4)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.l_margin + page_w, y)
    pdf.ln(4)


def _render_md_table(pdf: InstitutionalPDF, lines: list):
    """Tabla markdown convertida al estilo banking."""
    rows = []
    for line in lines:
        if TABLE_SEP_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if not rows:
        return
    headers = rows[0]
    body = rows[1:]
    ncols = len(headers)
    page_w = pdf.w - pdf.l_margin - pdf.r_margin
    col_w = page_w / ncols

    pdf.set_font(pdf._font, "B", 9)
    pdf.set_fill_color(*COLOR_HEADER_BG)
    pdf.set_text_color(*COLOR_HEADER_TXT)
    for h in headers:
        pdf.cell(col_w, 7, _safe(h), border=0, fill=True, align="L")
    pdf.ln()

    fill_row = False
    for r in body:
        pdf.set_fill_color(*COLOR_BG_ROW if fill_row else (255, 255, 255))
        pdf.set_font(pdf._font, "", 9)
        pdf.set_text_color(*COLOR_TEXT)
        for cell in r:
            txt = cell.replace("**", "")
            # Detectar si la celda es un porcentaje o monto con signo
            if re.match(r"^[+-][\d.,]+", txt):
                if txt.startswith("+"):
                    pdf.set_text_color(*COLOR_GREEN)
                else:
                    pdf.set_text_color(*COLOR_RED)
                pdf.set_font(pdf._font, "B", 9)
            else:
                pdf.set_text_color(*COLOR_TEXT)
                pdf.set_font(pdf._font, "", 9)
            txt_safe = _safe(txt)
            # Truncar si no entra
            while pdf.get_string_width(txt_safe) > col_w - 2 and len(txt_safe) > 3:
                txt_safe = txt_safe[:-1]
            pdf.cell(col_w, 6, txt_safe, border=0, fill=True, align="L")
        pdf.ln()
        fill_row = not fill_row
    pdf.ln(2)


def _emit_charts(pdf: InstitutionalPDF, charts: dict):
    """Sección 'Composición y evolución' con los charts PNG."""
    if not charts:
        return
    _emit_section_title(pdf, "2", "Composicion y evolucion")
    if charts.get("equity"):
        pdf.set_font(pdf._font, "B", 10.5)
        pdf.set_text_color(*COLOR_DARK)
        pdf.cell(0, 5, _safe("Como evoluciono tu cartera"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font(pdf._font, "", 9)
        pdf.set_text_color(*COLOR_DIM)
        pdf.multi_cell(0, 4, _safe(
            "Evolucion diaria del valor en pesos. Linea hacia arriba = ganancia."))
        pdf.ln(1)
        try:
            buf = io.BytesIO(charts["equity"]); pdf.image(buf, x=pdf.l_margin, w=170)
            pdf.ln(3)
        except Exception:
            pass

    if charts.get("allocation"):
        if pdf.get_y() > 200:
            pdf.add_page()
        pdf.set_font(pdf._font, "B", 10.5)
        pdf.set_text_color(*COLOR_DARK)
        pdf.cell(0, 5, _safe("Composicion por tipo de activo"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font(pdf._font, "", 9)
        pdf.set_text_color(*COLOR_DIM)
        pdf.multi_cell(0, 4, _safe(
            "Distribucion del capital invertido por clase de activo."))
        pdf.ln(1)
        try:
            buf = io.BytesIO(charts["allocation"]); pdf.image(buf, x=pdf.l_margin, w=170)
            pdf.ln(3)
        except Exception:
            pass

    if charts.get("benchmarks"):
        if pdf.get_y() > 200:
            pdf.add_page()
        pdf.set_font(pdf._font, "B", 10.5)
        pdf.set_text_color(*COLOR_DARK)
        pdf.cell(0, 5, _safe("Comparacion con alternativas pasivas"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font(pdf._font, "", 9)
        pdf.set_text_color(*COLOR_DIM)
        pdf.multi_cell(0, 4, _safe(
            "Tu portfolio (verde) vs Merval, S&P 500 en pesos, dolar MEP "
            "buy & hold e inflacion (CER) en el mismo periodo."))
        pdf.ln(1)
        try:
            buf = io.BytesIO(charts["benchmarks"]); pdf.image(buf, x=pdf.l_margin, w=170)
            pdf.ln(3)
        except Exception:
            pass


# ===================== PARSER MARKDOWN =====================
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$")
HR_RE      = re.compile(r"^-{3,}$")
BULLET_RE  = re.compile(r"^[\*\-]\s+(.+)$")
NUM_RE     = re.compile(r"^\d+\.\s+(.+)$")
TABLE_SEP_RE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$")


def _strip_md_inline(text: str):
    pattern = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)")
    parts = pattern.split(text)
    out = []
    for p in parts:
        if not p:
            continue
        if p.startswith("**") and p.endswith("**"):
            out.append((p[2:-2], "B"))
        elif p.startswith("*") and p.endswith("*"):
            out.append((p[1:-1], "I"))
        elif p.startswith("`") and p.endswith("`"):
            out.append((p[1:-1], "C"))
        else:
            out.append((p, ""))
    return out


def _render_paragraph(pdf: InstitutionalPDF, text: str, size: int = 10):
    fragments = _strip_md_inline(text)
    pdf.set_text_color(*COLOR_TEXT)
    for txt, style in fragments:
        if style == "C":
            pdf.set_font(pdf._font, "", size - 0.5)
        else:
            pdf.set_font(pdf._font, style, size)
        pdf.write(5, _safe(txt))
    pdf.ln(5.5)


def _render_md_body(pdf: InstitutionalPDF, md: str):
    """Renderea el cuerpo markdown del LLM con el estilo banking."""
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            pdf.ln(1.5); i += 1; continue

        # Heading
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            text = re.sub(r"^\*+|\*+$", "", m.group(2))
            sizes = {1: 15, 2: 13, 3: 11.5, 4: 10.5}
            pdf.ln(2 if level > 1 else 4)
            pdf.set_font(pdf._font, "B", sizes.get(level, 11))
            pdf.set_text_color(*COLOR_ACCENT if level <= 2 else COLOR_DARK)
            pdf.multi_cell(0, 6.5, _safe(text))
            if level == 2:
                pdf.set_draw_color(*COLOR_ACCENT); pdf.set_line_width(0.3)
                y = pdf.get_y(); pdf.line(20, y, 60, y)
            pdf.ln(1); i += 1; continue

        # HR
        if HR_RE.match(line.strip()):
            pdf.ln(2); pdf.set_draw_color(*COLOR_FAINT); pdf.set_line_width(0.2)
            y = pdf.get_y(); pdf.line(20, y, 190, y); pdf.ln(3); i += 1; continue

        # Tabla markdown
        if line.lstrip().startswith("|") and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i+1].strip()):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i]); i += 1
            _render_md_table(pdf, table_lines); continue

        # Bullet
        m = BULLET_RE.match(line.strip())
        if m:
            indent = len(line) - len(line.lstrip())
            pdf.set_x(20 + indent * 1.5 + 4)
            pdf.set_font(pdf._font, "B", 10)
            pdf.set_text_color(*COLOR_ACCENT)
            pdf.cell(4, 5, _safe("•" if HAS_DEJAVU else "-"))
            pdf.set_text_color(*COLOR_TEXT)
            _render_paragraph(pdf, m.group(1), size=10); i += 1; continue

        # Lista numerada
        m = NUM_RE.match(line.strip())
        if m:
            num_match = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
            num, txt = num_match.group(1), num_match.group(2)
            pdf.set_x(24); pdf.set_font(pdf._font, "B", 10)
            pdf.set_text_color(*COLOR_ACCENT); pdf.cell(7, 5, f"{num}.")
            pdf.set_text_color(*COLOR_TEXT)
            _render_paragraph(pdf, txt, size=10); i += 1; continue

        # Parrafo
        _render_paragraph(pdf, line, size=10); i += 1


# ===================== API PUBLICA =====================
def markdown_to_pdf(md_text: str, titulo: str = "Informe de Cartera",
                    context: dict = None, charts: dict = None,
                    cliente_friendly: bool = True,
                    nivel: str = "intermedio") -> bytes:
    """
    Construye el PDF estilo banking.

    - Header con titulo + fecha en banda azul oscura, logo del IFA si esta.
    - 3 KPIs grandes con barra coloreada (valor, rendimiento, rendimiento real).
    - Seccion 1: evolucion de la cartera (tabla concepto/monto estilo banking).
    - Seccion 2: composicion y evolucion (charts PNG).
    - Seccion 3+: analisis del LLM (markdown renderizado).
    - Footer en cada pagina con datos del IFA + disclaimer + pagina.
    """
    pf_meta = (context or {}).get("portfolio_meta") or {}
    cliente = pf_meta.get("cliente") or pf_meta.get("nombre") or ""
    hoy = datetime.now().strftime("%d/%m/%Y")
    fecha_label = f"Posicion consolidada al {hoy}"
    if cliente:
        fecha_label = f"Cliente: {cliente}  ·  {fecha_label}"

    # Branding del IFA
    try:
        from core.db import get_ifa_profile
        ifa = get_ifa_profile()
    except Exception:
        ifa = {}

    logo_bytes = None
    logo_url = (ifa or {}).get("logo_url")
    if logo_url:
        try:
            import requests as _rq
            r = _rq.get(logo_url, timeout=6)
            if r.status_code == 200:
                logo_bytes = r.content
        except Exception:
            pass

    pdf = InstitutionalPDF(
        titulo=titulo, fecha_label=fecha_label,
        ifa_profile=ifa, logo_bytes=logo_bytes,
    )
    pdf.add_page()

    if context:
        # Modo "Informe de cartera": KPIs + tabla concepto/monto + charts + analisis
        _emit_header_kpis(pdf, context)
        _emit_section_title(pdf, "1", "Como evoluciono tu cartera")
        _emit_resumen_table(pdf, context)
        if charts:
            _emit_charts(pdf, charts)
        if md_text and md_text.strip():
            _emit_section_title(pdf, "3", "Analisis detallado")
            _render_md_body(pdf, md_text)
    else:
        # Modo "Briefing": solo el cuerpo markdown del LLM, sin secciones de cartera
        if md_text and md_text.strip():
            _render_md_body(pdf, md_text)

    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return out.encode("latin-1") if isinstance(out, str) else bytes(out)
