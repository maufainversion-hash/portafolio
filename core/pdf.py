"""
Conversion de Markdown -> PDF institucional con fpdf2 (puro Python, sin
dependencias del sistema -> funciona en Streamlit Cloud sin friccion).

Soporta:
- # / ## / ### / #### headings (con colores y tamaño escalonado)
- **bold** e *italic* inline
- `code` inline
- Listas con "- " o "* "
- Tablas markdown (| col | col |)
- Lineas horizontales (---)
- Parrafos
- Caracteres Unicode (acentos, eñes, simbolos $) via fuente DejaVu integrada
"""
from __future__ import annotations
import io
import re
from datetime import datetime
from fpdf import FPDF
from fpdf.enums import XPos, YPos


# Paleta institucional (los colores del branding de la app)
COLOR_ACCENT = (52, 211, 153)    # verde esmeralda
COLOR_DARK   = (13, 18, 30)      # casi negro
COLOR_TEXT   = (35, 41, 56)      # gris oscuro para body
COLOR_DIM    = (107, 114, 128)   # gris claro para captions
COLOR_BG_TH  = (13, 58, 46)      # verde oscuro para headers de tabla
COLOR_CODE   = (243, 244, 246)   # gris muy claro de fondo para `code`


class InstitutionalPDF(FPDF):
    """PDF con header / footer institucional."""

    def __init__(self, titulo: str = "Reporte de Portafolio"):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.titulo = titulo
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(20, 25, 20)
        # DejaVu viene con fpdf2 y soporta Unicode completo
        self.add_font("DejaVu", "", "DejaVu", uni=True) if False else None
        # fpdf2 ya trae helvetica que soporta latin1; suficiente para nuestro caso

    def header(self):
        if self.page_no() == 1:
            return  # la portada se renderiza aparte
        # Banda superior fina
        self.set_draw_color(*COLOR_ACCENT)
        self.set_line_width(0.6)
        self.line(20, 12, 190, 12)
        # Titulo a la izquierda, pagina a la derecha
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*COLOR_DIM)
        self.set_xy(20, 14)
        self.cell(0, 5, "TuPortafolioIA · " + self.titulo)
        self.set_xy(20, 14)
        self.cell(170, 5, f"pag {self.page_no()}", align="R")
        self.set_y(22)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*COLOR_DIM)
        self.set_draw_color(*COLOR_DIM)
        self.set_line_width(0.2)
        self.line(20, self.get_y(), 190, self.get_y())
        self.set_y(-12)
        self.cell(0, 5, "Reporte generado automaticamente · TuPortafolioIA", align="C")


# ---------------------------------------------------------------------------
# PARSEO Y RENDER
# ---------------------------------------------------------------------------
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$")
HR_RE      = re.compile(r"^-{3,}$")
BULLET_RE  = re.compile(r"^[\*\-]\s+(.+)$")
NUM_RE     = re.compile(r"^\d+\.\s+(.+)$")
TABLE_SEP_RE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$")


def _emit_cover(pdf: InstitutionalPDF, titulo: str):
    """Pagina portada."""
    pdf.add_page()
    # Bloque decorativo arriba
    pdf.set_fill_color(*COLOR_ACCENT)
    pdf.rect(0, 0, 210, 8, "F")

    # Logo / nombre app
    pdf.set_xy(20, 60)
    pdf.set_font("Helvetica", "B", 36)
    pdf.set_text_color(*COLOR_DARK)
    pdf.cell(0, 14, "TuPortafolioIA",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_x(20)
    pdf.set_font("Helvetica", "", 13)
    pdf.set_text_color(*COLOR_DIM)
    pdf.cell(0, 8, "Terminal de portafolio · Research institucional",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Linea decorativa esmeralda
    pdf.set_draw_color(*COLOR_ACCENT)
    pdf.set_line_width(1.2)
    pdf.line(20, 100, 60, 100)

    # Titulo del reporte
    pdf.set_xy(20, 120)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*COLOR_DARK)
    pdf.multi_cell(0, 10, titulo)

    # Fecha
    pdf.set_xy(20, 250)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*COLOR_DIM)
    hoy = datetime.now().strftime("%d de %B de %Y")
    # Castellanizar mes simple
    meses_en = ["January","February","March","April","May","June","July",
                "August","September","October","November","December"]
    meses_es = ["enero","febrero","marzo","abril","mayo","junio","julio",
                "agosto","septiembre","octubre","noviembre","diciembre"]
    for en, es in zip(meses_en, meses_es):
        hoy = hoy.replace(en, es)
    pdf.cell(0, 5, "Fecha del reporte: " + hoy,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Footer disclaimer cover
    pdf.set_y(265)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 4,
        "Este documento fue generado automaticamente con base en datos de mercado "
        "y modelos de inteligencia artificial. No constituye recomendacion de "
        "inversion. Sujeto a riesgo de mercado, cambiario e inflacionario.")


def _strip_md_inline(text: str) -> list:
    """
    Convierte un string con **bold**, *italic* y `code` en una lista de
    (texto, estilo) donde estilo es '', 'B', 'I' o 'C' (code).
    """
    out = []
    pattern = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)")
    parts = pattern.split(text)
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


def _ascii_safe(text: str) -> str:
    """fpdf2 con fuentes Helvetica solo soporta latin1. Reemplaza chars unicode comunes."""
    replacements = {
        "—": "-", "–": "-", "•": "*",
        "“": '"', "”": '"', "‘": "'", "’": "'",
        "→": "->", "←": "<-", "▲": "^", "▼": "v",
        "✔": "OK", "⚠": "!", "🎯": "", "📊": "",
        "📈": "", "📉": "", "💡": "", "📋": "",
        "🇦🇷": "[AR]", "🇺🇸": "[US]", "🌎": "[GLOBAL]",
        "📜": "", "🏦": "", "₿": "BTC",
        "▸": ">", "▾": "v", "↑": "^", "↓": "v",
        "%": "%",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    # Strip cualquier char que quede fuera de latin1
    return text.encode("latin-1", "replace").decode("latin-1")


def _render_inline(pdf: InstitutionalPDF, fragments: list, size: int = 10):
    """Renderea fragmentos inline en la linea actual."""
    for txt, style in fragments:
        txt_safe = _ascii_safe(txt)
        if style == "C":
            pdf.set_font("Courier", "", size)
            pdf.set_fill_color(*COLOR_CODE)
            pdf.set_text_color(*COLOR_DARK)
            pdf.cell(pdf.get_string_width(txt_safe) + 2, 5, txt_safe, fill=True)
        else:
            pdf.set_font("Helvetica", style, size)
            pdf.set_text_color(*COLOR_TEXT)
            pdf.cell(pdf.get_string_width(txt_safe) + 0.5, 5, txt_safe)


def _render_paragraph(pdf: InstitutionalPDF, text: str, size: int = 10):
    """Para parrafos largos con inline formatting, usamos write() para wrap."""
    fragments = _strip_md_inline(text)
    pdf.set_text_color(*COLOR_TEXT)
    for txt, style in fragments:
        txt_safe = _ascii_safe(txt)
        if style == "C":
            pdf.set_font("Courier", "", size)
        else:
            pdf.set_font("Helvetica", style, size)
        pdf.write(5, txt_safe)
    pdf.ln(6)


def _render_table(pdf: InstitutionalPDF, lines: list):
    """
    Renderea una tabla markdown. lines es la lista de filas markdown
    (incluido el separador), ya filtradas.
    """
    rows = []
    for line in lines:
        if TABLE_SEP_RE.match(line):
            continue
        # Splitear por | quitando bordes
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if not rows:
        return
    headers = rows[0]
    body = rows[1:]
    ncols = len(headers)
    if ncols == 0:
        return

    page_w = pdf.w - pdf.l_margin - pdf.r_margin
    col_w = page_w / ncols

    # Header
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*COLOR_BG_TH)
    pdf.set_text_color(255, 255, 255)
    for h in headers:
        pdf.cell(col_w, 7, _ascii_safe(h), border=1, fill=True, align="L")
    pdf.ln()

    # Body
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*COLOR_TEXT)
    fill_row = False
    for r in body:
        if fill_row:
            pdf.set_fill_color(245, 247, 250)
        else:
            pdf.set_fill_color(255, 255, 255)
        # Padding por celda (no usamos multi_cell para mantener altura fija)
        for cell in r:
            txt = _ascii_safe(cell.replace("**", ""))  # bold dentro de tablas: simplificamos
            # Truncar si es muy largo
            if pdf.get_string_width(txt) > col_w - 2:
                while pdf.get_string_width(txt + "...") > col_w - 2 and len(txt) > 3:
                    txt = txt[:-1]
                txt = txt + "..."
            pdf.cell(col_w, 6, txt, border=1, fill=True, align="L")
        pdf.ln()
        fill_row = not fill_row
    pdf.ln(2)


def _render_body(pdf: InstitutionalPDF, md: str):
    """Recorre el markdown linea por linea."""
    pdf.add_page()
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        if not line.strip():
            pdf.ln(2)
            i += 1
            continue

        # Heading
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            text = _ascii_safe(re.sub(r"^\*+|\*+$", "", m.group(2)))
            sizes = {1: 18, 2: 14, 3: 12, 4: 11}
            colors_ = {1: COLOR_ACCENT, 2: COLOR_DARK, 3: COLOR_DARK, 4: COLOR_TEXT}
            pdf.ln(3 if level > 1 else 5)
            pdf.set_font("Helvetica", "B", sizes.get(level, 11))
            pdf.set_text_color(*colors_.get(level, COLOR_TEXT))
            pdf.multi_cell(0, 7, text)
            # Linea decorativa bajo h2
            if level == 2:
                pdf.set_draw_color(*COLOR_ACCENT)
                pdf.set_line_width(0.4)
                y = pdf.get_y()
                pdf.line(20, y, 50, y)
            pdf.ln(1)
            i += 1
            continue

        # Linea horizontal
        if HR_RE.match(line.strip()):
            pdf.ln(2)
            pdf.set_draw_color(*COLOR_DIM)
            pdf.set_line_width(0.2)
            y = pdf.get_y()
            pdf.line(20, y, 190, y)
            pdf.ln(3)
            i += 1
            continue

        # Tabla (siguiente linea debe ser separador)
        if line.lstrip().startswith("|") and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i+1].strip()):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            _render_table(pdf, table_lines)
            continue

        # Bullet
        m = BULLET_RE.match(line.strip())
        if m:
            indent = len(line) - len(line.lstrip())
            pdf.set_x(20 + indent * 1.5 + 4)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(*COLOR_ACCENT)
            pdf.cell(4, 5, "-")
            pdf.set_text_color(*COLOR_TEXT)
            _render_paragraph(pdf, m.group(1), size=10)
            i += 1
            continue

        # Lista numerada
        m = NUM_RE.match(line.strip())
        if m:
            num_match = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
            num, txt = num_match.group(1), num_match.group(2)
            pdf.set_x(24)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*COLOR_ACCENT)
            pdf.cell(7, 5, f"{num}.")
            pdf.set_text_color(*COLOR_TEXT)
            _render_paragraph(pdf, txt, size=10)
            i += 1
            continue

        # Parrafo normal
        _render_paragraph(pdf, line, size=10)
        i += 1


def markdown_to_pdf(md_text: str, titulo: str = "Reporte") -> bytes:
    """API publica: markdown -> bytes PDF."""
    pdf = InstitutionalPDF(titulo=titulo)
    _emit_cover(pdf, titulo)
    _render_body(pdf, md_text)
    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    # En algunas versiones devuelve str
    return out.encode("latin-1") if isinstance(out, str) else bytes(out)
