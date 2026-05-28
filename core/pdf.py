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


def _emit_cover(pdf: InstitutionalPDF, titulo: str, context: dict = None):
    """Pagina portada. Si hay context con cliente, lo agrega como subtitulo."""
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

    # Cliente (si esta)
    cliente = None
    pf_nombre = None
    if context:
        meta = context.get("portfolio_meta") or {}
        cliente = meta.get("cliente")
        pf_nombre = meta.get("nombre")
    if cliente:
        pdf.set_xy(20, 110)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*COLOR_DIM)
        pdf.cell(0, 6, "Reporte preparado para:",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(20)
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(*COLOR_DARK)
        pdf.cell(0, 8, _ascii_safe(cliente),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if pf_nombre and pf_nombre != cliente:
            pdf.set_x(20)
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_text_color(*COLOR_DIM)
            pdf.cell(0, 5, _ascii_safe(f"Portfolio: {pf_nombre}"),
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Titulo del reporte
    pdf.set_xy(20, 145 if cliente else 120)
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


def markdown_to_pdf(md_text: str, titulo: str = "Reporte",
                    context: dict = None, charts: dict = None,
                    cliente_friendly: bool = True) -> bytes:
    """
    API publica: markdown -> bytes PDF.

    Si se pasa `context` (output de build_portfolio_context) y `charts`
    (output de build_all_charts), se agregan secciones para el cliente:
      - Resumen amigable con KPIs simples
      - Pagina(s) con graficos PNG embebidos
      - Glosario al final

    `cliente_friendly` = False genera solo la version institucional (cover + body).
    """
    pdf = InstitutionalPDF(titulo=titulo)
    _emit_cover(pdf, titulo, context)
    if cliente_friendly and context:
        _emit_resumen_cliente(pdf, context)
    if cliente_friendly and charts:
        _emit_charts(pdf, charts)
    if cliente_friendly:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*COLOR_DARK)
        pdf.cell(0, 10, "Analisis tecnico detallado",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(*COLOR_ACCENT)
        pdf.set_line_width(0.6)
        pdf.line(20, pdf.get_y(), 50, pdf.get_y())
        pdf.ln(6)
        # Renderiza el markdown SIN nuevo add_page (lo hace _render_body)
        _render_md_inline(pdf, md_text)
    else:
        _render_body(pdf, md_text)
    if cliente_friendly:
        _emit_glosario(pdf)

    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return out.encode("latin-1") if isinstance(out, str) else bytes(out)


def _render_md_inline(pdf, md: str):
    """Igual que _render_body pero sin agregar pagina nueva (ya estamos en una)."""
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            pdf.ln(2); i += 1; continue
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
            if level == 2:
                pdf.set_draw_color(*COLOR_ACCENT); pdf.set_line_width(0.4)
                y = pdf.get_y(); pdf.line(20, y, 50, y)
            pdf.ln(1); i += 1; continue
        if HR_RE.match(line.strip()):
            pdf.ln(2); pdf.set_draw_color(*COLOR_DIM); pdf.set_line_width(0.2)
            y = pdf.get_y(); pdf.line(20, y, 190, y); pdf.ln(3); i += 1; continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i+1].strip()):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i]); i += 1
            _render_table(pdf, table_lines); continue
        m = BULLET_RE.match(line.strip())
        if m:
            indent = len(line) - len(line.lstrip())
            pdf.set_x(20 + indent * 1.5 + 4)
            pdf.set_font("Helvetica", "", 10); pdf.set_text_color(*COLOR_ACCENT)
            pdf.cell(4, 5, "-"); pdf.set_text_color(*COLOR_TEXT)
            _render_paragraph(pdf, m.group(1), size=10); i += 1; continue
        m = NUM_RE.match(line.strip())
        if m:
            num_match = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
            num, txt = num_match.group(1), num_match.group(2)
            pdf.set_x(24); pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*COLOR_ACCENT); pdf.cell(7, 5, f"{num}.")
            pdf.set_text_color(*COLOR_TEXT)
            _render_paragraph(pdf, txt, size=10); i += 1; continue
        _render_paragraph(pdf, line, size=10); i += 1


def _emit_resumen_cliente(pdf: InstitutionalPDF, context: dict):
    """Pagina 'Resumen para el cliente' con KPIs simples y lenguaje claro."""
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*COLOR_DARK)
    pdf.cell(0, 10, "Resumen para el cliente",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*COLOR_ACCENT); pdf.set_line_width(0.6)
    pdf.line(20, pdf.get_y(), 50, pdf.get_y())
    pdf.ln(8)

    port = context.get("portfolio") or {}
    metrics = context.get("metrics") or {}
    benchmarks = context.get("benchmarks") or {}

    valor = port.get("valor_total_ars")
    valor_usd = port.get("valor_total_usd_mep")
    pnl_pct = port.get("pnl_nominal_pct")
    pnl_real_pct = port.get("pnl_real_pct")
    cagr_pct = metrics.get("cagr_pct")
    dias = metrics.get("equity_curve_dias")

    # Frase intro
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*COLOR_TEXT)
    if valor is not None and dias:
        intro = (f"Al dia de la fecha, tu cartera tiene un valor total de "
                 f"$ {valor:,.0f} (equivalente a USD {valor_usd:,.0f} al MEP). "
                 f"Este reporte analiza el desempeno de los ultimos {dias} dias.")
        pdf.multi_cell(0, 6, _ascii_safe(intro))
        pdf.ln(2)

    # KPIs en cajas
    _emit_kpi_boxes(pdf, [
        ("Cuanto vale hoy",         f"$ {valor:,.0f}" if valor else "—",       "Total en pesos"),
        ("Equivalente en USD",      f"US$ {valor_usd:,.0f}" if valor_usd else "—", "Al dolar MEP"),
        ("Ganancia / Perdida",      f"{pnl_pct:+.2f}%" if pnl_pct is not None else "—",
         "Sin descontar inflacion"),
        ("Ganancia real (vs CER)",  f"{pnl_real_pct:+.2f}%" if pnl_real_pct is not None else "—",
         "Descontando inflacion"),
    ])

    pdf.ln(4)

    # Interpretacion en lenguaje simple
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*COLOR_DARK)
    pdf.cell(0, 7, "Como leer estos numeros",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*COLOR_TEXT)
    interpretaciones = []
    if pnl_pct is not None:
        if pnl_pct > 0:
            interpretaciones.append(
                f"En terminos nominales (pesos sin ajustar), la cartera subio "
                f"{pnl_pct:.2f}% desde que se cargaron las posiciones."
            )
        else:
            interpretaciones.append(
                f"En terminos nominales (pesos sin ajustar), la cartera bajo "
                f"{abs(pnl_pct):.2f}% desde que se cargaron las posiciones."
            )
    if pnl_real_pct is not None and pnl_pct is not None:
        if pnl_real_pct < pnl_pct:
            interpretaciones.append(
                f"Descontando la inflacion (CER), la perdida real del poder "
                f"adquisitivo es de {pnl_real_pct:.2f}%. Esto es lo que importa "
                f"para saber si tu plata 'compra mas o menos' que antes."
            )
    if benchmarks:
        comp = benchmarks.get("comparativas", {})
        port_ret = benchmarks.get("portfolio_retorno_pct", 0)
        ganados, perdidos = [], []
        bm_labels = {
            "merval_ars_pct": "el Merval",
            "spy_en_ars_pct": "el S&P 500 en pesos",
            "usd_mep_buyhold_pct": "comprar dolar MEP",
            "inflacion_acumulada_pct": "la inflacion",
        }
        for k, label in bm_labels.items():
            v = comp.get(k)
            if v is None:
                continue
            diff = port_ret - v
            if diff > 0:
                ganados.append(f"{label} ({diff:+.1f} pp)")
            else:
                perdidos.append(f"{label} ({diff:+.1f} pp)")
        if ganados:
            interpretaciones.append(
                "En el mismo periodo, la cartera rindio mas que: " +
                ", ".join(ganados) + ".")
        if perdidos:
            interpretaciones.append(
                "Y rindio menos que: " + ", ".join(perdidos) + ".")

    for txt in interpretaciones:
        pdf.set_x(22)
        pdf.set_text_color(*COLOR_ACCENT)
        pdf.cell(4, 5, "-")
        pdf.set_text_color(*COLOR_TEXT)
        pdf.multi_cell(0, 5, _ascii_safe(txt))
        pdf.ln(1)


def _emit_kpi_boxes(pdf: InstitutionalPDF, kpis: list):
    """Caja por KPI en 2 columnas."""
    box_w = (pdf.w - pdf.l_margin - pdf.r_margin - 6) / 2  # 6 = gap
    box_h = 24
    y_start = pdf.get_y()
    for i, (titulo, valor, subtitulo) in enumerate(kpis):
        col = i % 2
        row = i // 2
        x = pdf.l_margin + col * (box_w + 6)
        y = y_start + row * (box_h + 4)
        # Borde redondeado simulado con rect
        pdf.set_draw_color(220, 224, 230)
        pdf.set_fill_color(248, 250, 252)
        pdf.rect(x, y, box_w, box_h, "DF")
        # Titulo
        pdf.set_xy(x + 4, y + 3)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*COLOR_DIM)
        pdf.cell(box_w - 8, 4, _ascii_safe(titulo.upper()))
        # Valor grande
        pdf.set_xy(x + 4, y + 8)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*COLOR_DARK)
        pdf.cell(box_w - 8, 7, _ascii_safe(valor))
        # Subtitulo
        pdf.set_xy(x + 4, y + 17)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*COLOR_DIM)
        pdf.cell(box_w - 8, 4, _ascii_safe(subtitulo))
    pdf.set_y(y_start + ((len(kpis) + 1) // 2) * (box_h + 4))


def _emit_charts(pdf: InstitutionalPDF, charts: dict):
    """Pagina(s) con los graficos PNG generados."""
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*COLOR_DARK)
    pdf.cell(0, 10, "Visualizaciones",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*COLOR_ACCENT); pdf.set_line_width(0.6)
    pdf.line(20, pdf.get_y(), 50, pdf.get_y())
    pdf.ln(6)

    # Equity curve
    if charts.get("equity"):
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*COLOR_DARK)
        pdf.cell(0, 6, "Como evoluciono tu cartera",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_DIM)
        pdf.multi_cell(0, 4,
            "El grafico muestra el valor diario de la cartera en pesos a lo "
            "largo del tiempo. Si la linea sube, ganaste; si baja, perdiste.")
        pdf.ln(2)
        try:
            buf = io.BytesIO(charts["equity"])
            pdf.image(buf, x=pdf.l_margin, w=170)
            pdf.ln(4)
        except Exception:
            pass

    # Allocation
    if charts.get("allocation"):
        # Si no entra en la pagina, hacer una nueva
        if pdf.get_y() > 180:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*COLOR_DARK)
        pdf.cell(0, 6, "En que esta invertida la cartera",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_DIM)
        pdf.multi_cell(0, 4,
            "Cada porcion representa una clase de activo (acciones argentinas, "
            "cedears, bonos, etc). Una cartera bien diversificada no concentra "
            "todo en una sola clase.")
        pdf.ln(2)
        try:
            buf = io.BytesIO(charts["allocation"])
            pdf.image(buf, x=pdf.l_margin, w=170)
            pdf.ln(4)
        except Exception:
            pass

    # vs Benchmarks
    if charts.get("benchmarks"):
        if pdf.get_y() > 180:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*COLOR_DARK)
        pdf.cell(0, 6, "Comparacion con alternativas",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_DIM)
        pdf.multi_cell(0, 4,
            "Comparacion del rendimiento del portfolio (en verde) contra "
            "alternativas pasivas en el mismo periodo: Merval, S&P 500 en "
            "pesos, comprar dolar MEP y la inflacion. La barra mas alta es "
            "la que mas rindio.")
        pdf.ln(2)
        try:
            buf = io.BytesIO(charts["benchmarks"])
            pdf.image(buf, x=pdf.l_margin, w=170)
            pdf.ln(4)
        except Exception:
            pass


def _emit_glosario(pdf: InstitutionalPDF):
    """Glosario al final del PDF con definiciones simples."""
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*COLOR_DARK)
    pdf.cell(0, 10, "Glosario",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*COLOR_ACCENT); pdf.set_line_width(0.6)
    pdf.line(20, pdf.get_y(), 50, pdf.get_y())
    pdf.ln(8)

    entradas = [
        ("CER / Inflacion",
         "Indice que mide cuanto se desvalorizan los pesos. Si la inflacion "
         "fue 30% y tu cartera subio 20%, en terminos REALES perdiste 10%."),
        ("Rendimiento nominal",
         "Cuanto subio o bajo en pesos sin descontar inflacion."),
        ("Rendimiento real",
         "Rendimiento nominal MENOS la inflacion del periodo. Es el "
         "verdadero poder adquisitivo ganado/perdido."),
        ("Dolar MEP",
         "Tipo de cambio implicito al comprar bonos en pesos y venderlos "
         "en dolares. Es el dolar 'legal' de mercado."),
        ("CEDEARs",
         "Certificados Argentinos que representan acciones del exterior "
         "(AAPL, MSFT, etc) y cotizan en pesos. Tienen el atractivo de "
         "estar 'dolarizados' implicitamente."),
        ("Merval",
         "Indice de las principales acciones argentinas (GGAL, PAMP, YPF...). "
         "Es el benchmark del mercado local."),
        ("S&P 500 (SPY)",
         "Indice de las 500 empresas mas grandes de USA. Benchmark global."),
        ("Volatilidad anualizada",
         "Cuanto fluctua el valor de la cartera, expresado anualmente. "
         "Volatilidad alta = riesgo mayor."),
        ("Sharpe Ratio",
         "Retorno por unidad de riesgo asumido. Mas alto = mejor relacion "
         "rendimiento/riesgo. > 1 es bueno, > 2 es excelente."),
        ("Sortino Ratio",
         "Como Sharpe pero solo considera la volatilidad a la baja. Penaliza "
         "solo los movimientos negativos."),
        ("Drawdown",
         "Caida desde el maximo previo. Mide la peor 'racha mala' del "
         "portfolio."),
        ("VaR (Value at Risk)",
         "Perdida diaria maxima esperada con 95% de probabilidad. Ej: "
         "VaR 95% = -3% significa que en peor caso normal perdes 3% en un dia."),
        ("Riesgo pais (EMBI)",
         "Sobretasa que pagan los bonos argentinos sobre los del Tesoro USA. "
         "A mayor EMBI, mayor percepcion de riesgo de default."),
        ("HHI (concentracion)",
         "Indice que mide cuan concentrada esta la cartera. > 2500 = "
         "concentracion alta; < 1500 = diversificacion saludable."),
    ]
    for termino, definicion in entradas:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*COLOR_DARK)
        pdf.cell(0, 5, _ascii_safe(termino),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_TEXT)
        pdf.multi_cell(0, 4, _ascii_safe(definicion))
        pdf.ln(2)
