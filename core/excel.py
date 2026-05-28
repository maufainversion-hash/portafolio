"""
Generador de reporte Excel multi-hoja con graficos nativos.

Hojas:
1. Resumen        - KPIs, datos del cliente, donut allocation, line equity.
2. Posiciones     - Tabla de tenencias con P&L y formato condicional.
3. Performance    - Equity curve, drawdown, metricas cuant.
4. Benchmarks     - Comparativa vs Merval/SPY/MEP/Inflacion + chart de barras.
5. Composicion    - Allocation por tipo y por moneda con charts pie.
"""
from __future__ import annotations
import io
from datetime import datetime
from typing import Optional
import pandas as pd
import xlsxwriter

from core.ai_data import build_portfolio_context
from core.portfolio import (
    load_tenencias, valuar_tenencias, convertir_a, equity_curve,
    agregar_pnl_real, benchmark_curves,
)
from core.metrics import returns_from_prices, volatility, sharpe, sortino, max_drawdown, cagr
from core.db import get_ifa_profile


# Paleta consistente con la app
COLOR_HEADER = "#0F2440"
COLOR_ACCENT = "#2563EB"
COLOR_GREEN  = "#10B981"
COLOR_RED    = "#DC2626"
COLOR_DIM    = "#6B7280"
COLOR_BG_ROW = "#F8FAFC"


def _setup_formats(wb: xlsxwriter.Workbook) -> dict:
    """Defina formatos reutilizables."""
    return {
        "title": wb.add_format({
            "font_name": "Calibri", "font_size": 18, "bold": True,
            "font_color": COLOR_HEADER,
        }),
        "subtitle": wb.add_format({
            "font_name": "Calibri", "font_size": 10, "italic": True,
            "font_color": COLOR_DIM,
        }),
        "section": wb.add_format({
            "font_name": "Calibri", "font_size": 13, "bold": True,
            "font_color": COLOR_ACCENT,
            "border_color": COLOR_ACCENT, "bottom": 2,
        }),
        "kpi_label": wb.add_format({
            "font_name": "Calibri", "font_size": 8, "bold": True,
            "font_color": COLOR_ACCENT,
            "bg_color": COLOR_BG_ROW,
            "border": 1, "border_color": "#E5E7EB",
            "align": "center", "valign": "vcenter",
            "top": 4, "top_color": COLOR_ACCENT,
        }),
        "kpi_value": wb.add_format({
            "font_name": "Calibri", "font_size": 16, "bold": True,
            "font_color": COLOR_HEADER,
            "bg_color": "white",
            "border": 1, "border_color": "#E5E7EB",
            "align": "center", "valign": "vcenter",
        }),
        "kpi_value_pos": wb.add_format({
            "font_name": "Calibri", "font_size": 16, "bold": True,
            "font_color": COLOR_GREEN, "bg_color": "white",
            "border": 1, "border_color": "#E5E7EB",
            "align": "center", "valign": "vcenter",
        }),
        "kpi_value_neg": wb.add_format({
            "font_name": "Calibri", "font_size": 16, "bold": True,
            "font_color": COLOR_RED, "bg_color": "white",
            "border": 1, "border_color": "#E5E7EB",
            "align": "center", "valign": "vcenter",
        }),
        "table_header": wb.add_format({
            "font_name": "Calibri", "font_size": 10, "bold": True,
            "font_color": "white", "bg_color": COLOR_HEADER,
            "border": 1, "border_color": COLOR_HEADER,
            "align": "left", "valign": "vcenter",
        }),
        "table_cell": wb.add_format({
            "font_name": "Calibri", "font_size": 10,
            "border": 1, "border_color": "#E5E7EB",
            "align": "left", "valign": "vcenter",
        }),
        "table_cell_alt": wb.add_format({
            "font_name": "Calibri", "font_size": 10,
            "bg_color": COLOR_BG_ROW,
            "border": 1, "border_color": "#E5E7EB",
            "align": "left", "valign": "vcenter",
        }),
        "money_ars": wb.add_format({
            "font_name": "Calibri", "font_size": 10,
            "num_format": '"$ "#,##0.00;[Red]"-$ "#,##0.00',
            "border": 1, "border_color": "#E5E7EB",
            "align": "right",
        }),
        "money_ars_alt": wb.add_format({
            "font_name": "Calibri", "font_size": 10,
            "num_format": '"$ "#,##0.00;[Red]"-$ "#,##0.00',
            "bg_color": COLOR_BG_ROW,
            "border": 1, "border_color": "#E5E7EB",
            "align": "right",
        }),
        "pct": wb.add_format({
            "font_name": "Calibri", "font_size": 10,
            "num_format": '+0.00%;[Red]-0.00%',
            "border": 1, "border_color": "#E5E7EB",
            "align": "right", "bold": True,
        }),
        "pct_alt": wb.add_format({
            "font_name": "Calibri", "font_size": 10,
            "num_format": '+0.00%;[Red]-0.00%',
            "bg_color": COLOR_BG_ROW,
            "border": 1, "border_color": "#E5E7EB",
            "align": "right", "bold": True,
        }),
        "qty": wb.add_format({
            "font_name": "Calibri", "font_size": 10,
            "num_format": '#,##0.0000',
            "border": 1, "border_color": "#E5E7EB",
            "align": "right",
        }),
        "qty_alt": wb.add_format({
            "font_name": "Calibri", "font_size": 10,
            "num_format": '#,##0.0000',
            "bg_color": COLOR_BG_ROW,
            "border": 1, "border_color": "#E5E7EB",
            "align": "right",
        }),
        "date_header": wb.add_format({
            "font_name": "Calibri", "font_size": 10, "bold": True,
            "font_color": "white", "bg_color": COLOR_HEADER,
            "align": "center",
        }),
        "footer": wb.add_format({
            "font_name": "Calibri", "font_size": 8, "italic": True,
            "font_color": COLOR_DIM,
        }),
    }


def _hoja_resumen(wb, fmts, context: dict, ifa: dict):
    ws = wb.add_worksheet("Resumen")
    ws.set_column(0, 0, 22)
    ws.set_column(1, 7, 18)
    ws.hide_gridlines(2)

    port = context.get("portfolio") or {}
    pf_meta = context.get("portfolio_meta") or {}
    metrics = context.get("metrics") or {}

    # Titulo
    ws.merge_range(0, 0, 0, 7, "INFORME DE CARTERA", fmts["title"])
    sub = []
    if pf_meta.get("cliente"): sub.append(f"Cliente: {pf_meta['cliente']}")
    sub.append(f"Posicion al {datetime.now().strftime('%d/%m/%Y')}")
    if ifa.get("nombre"): sub.append(f"Asesor: {ifa['nombre']}")
    ws.merge_range(1, 0, 1, 7, " · ".join(sub), fmts["subtitle"])

    # KPI Row 1 (4 KPIs)
    valor = port.get("valor_total_ars") or 0
    valor_usd = port.get("valor_total_usd_mep") or 0
    pnl_pct = port.get("pnl_nominal_pct")
    pnl_real_pct = port.get("pnl_real_pct")
    vol = None
    if metrics.get("volatilidad_anual_pct") is not None:
        vol = metrics["volatilidad_anual_pct"]

    kpis = [
        ("VALOR TOTAL (ARS)", valor, "money", None),
        ("VALOR USD MEP", valor_usd, "money_usd", None),
        ("RENDIMIENTO NOMINAL",
         (pnl_pct or 0) / 100, "pct", "pos" if (pnl_pct or 0) >= 0 else "neg"),
        ("RENDIMIENTO REAL (CER)",
         (pnl_real_pct or 0) / 100, "pct", "pos" if (pnl_real_pct or 0) >= 0 else "neg"),
    ]
    row = 3
    for col, (label, val, kind, sign) in enumerate(kpis):
        c = col * 2
        ws.merge_range(row, c, row, c + 1, label, fmts["kpi_label"])
        # Valor
        if sign == "pos":
            valfmt = fmts["kpi_value_pos"]
        elif sign == "neg":
            valfmt = fmts["kpi_value_neg"]
        else:
            valfmt = fmts["kpi_value"]
        if kind == "pct":
            valfmt = wb_clone_with_numformat(wb, valfmt, '+0.00%;-0.00%')
        elif kind == "money":
            valfmt = wb_clone_with_numformat(wb, valfmt, '"$ "#,##0')
        elif kind == "money_usd":
            valfmt = wb_clone_with_numformat(wb, valfmt, '"US$ "#,##0')
        ws.merge_range(row + 1, c, row + 2, c + 1, val, valfmt)
    ws.set_row(row + 1, 28)
    ws.set_row(row + 2, 6)

    # KPI Row 2 (volatilidad + posiciones)
    row2 = 8
    if vol is not None:
        ws.merge_range(row2, 0, row2, 1, "VOLATILIDAD ANUAL", fmts["kpi_label"])
        ws.merge_range(row2 + 1, 0, row2 + 2, 1, vol / 100,
                       wb_clone_with_numformat(wb, fmts["kpi_value"], '0.00%'))
    n_pos = port.get("n_posiciones") or 0
    ws.merge_range(row2, 2, row2, 3, "N° POSICIONES", fmts["kpi_label"])
    ws.merge_range(row2 + 1, 2, row2 + 2, 3, n_pos, fmts["kpi_value"])

    tipos = ", ".join(port.get("tipos_presentes") or [])
    ws.merge_range(row2, 4, row2, 7, "TIPOS DE ACTIVOS", fmts["kpi_label"])
    ws.merge_range(row2 + 1, 4, row2 + 2, 7, tipos,
                   wb_clone_with_numformat(wb, fmts["kpi_value"], '@'))
    ws.set_row(row2 + 1, 24)

    # ALLOCATION (chart pie + tabla pequeña)
    row3 = 13
    ws.merge_range(row3, 0, row3, 3, "Composicion por tipo de activo", fmts["section"])
    positions = context.get("positions") or []
    if positions:
        df_pos = pd.DataFrame(positions)
        agg = df_pos.groupby("tipo")["valor_actual_ars"].sum().sort_values(ascending=False)
        # Tabla origen (oculta abajo)
        ws.write(row3 + 1, 0, "Tipo", fmts["table_header"])
        ws.write(row3 + 1, 1, "Valor (ARS)", fmts["table_header"])
        ws.write(row3 + 1, 2, "Peso %", fmts["table_header"])
        total = agg.sum()
        for i, (tipo, val) in enumerate(agg.items()):
            r = row3 + 2 + i
            f = fmts["table_cell"] if i % 2 == 0 else fmts["table_cell_alt"]
            fm = fmts["money_ars"] if i % 2 == 0 else fmts["money_ars_alt"]
            ws.write(r, 0, str(tipo), f)
            ws.write(r, 1, float(val), fm)
            ws.write(r, 2, float(val) / total,
                     wb_clone_with_numformat(wb,
                         fmts["table_cell"] if i % 2 == 0 else fmts["table_cell_alt"],
                         '0.00%'))
        n = len(agg)
        # Chart pie
        chart = wb.add_chart({"type": "doughnut"})
        chart.add_series({
            "name":       "Allocation",
            "categories": ["Resumen", row3 + 2, 0, row3 + 1 + n, 0],
            "values":     ["Resumen", row3 + 2, 1, row3 + 1 + n, 1],
            "data_labels": {"percentage": True, "font": {"color": "white", "bold": True}},
            "points": [{"fill": {"color": c}} for c in
                       ["#10B981", "#06B6D4", "#3B82F6", "#8B5CF6",
                        "#EC4899", "#F59E0B", "#EF4444"][:n]],
        })
        chart.set_title({"name": "Por tipo de activo",
                         "name_font": {"size": 12, "bold": True, "color": COLOR_HEADER}})
        chart.set_size({"width": 380, "height": 240})
        chart.set_legend({"position": "right"})
        ws.insert_chart(row3 + 1, 4, chart, {"x_offset": 10})

    # Footer
    ws.write(row3 + 12, 0,
             "Este informe tiene caracter informativo y educativo. No constituye "
             "asesoramiento financiero ni recomendacion.",
             fmts["footer"])


def _hoja_posiciones(wb, fmts, context: dict):
    ws = wb.add_worksheet("Posiciones")
    ws.set_column(0, 0, 12)   # Ticker
    ws.set_column(1, 1, 14)   # Tipo
    ws.set_column(2, 2, 12)   # Cantidad
    ws.set_column(3, 6, 16)   # precios y valores
    ws.set_column(7, 9, 12)   # %s
    ws.hide_gridlines(2)

    ws.merge_range(0, 0, 0, 9, "POSICIONES ACTUALES", fmts["title"])

    headers = ["Ticker", "Tipo", "Cantidad", "P. compra", "P. actual",
               "Valor (ARS)", "P&L (ARS)", "P&L %", "P&L real %", "Peso %"]
    for c, h in enumerate(headers):
        ws.write(2, c, h, fmts["table_header"])

    positions = context.get("positions") or []
    if not positions:
        ws.write(3, 0, "Sin posiciones cargadas.", fmts["table_cell"])
        return

    total = sum((p.get("valor_actual_ars") or 0) for p in positions)
    for i, p in enumerate(positions):
        r = 3 + i
        alt = i % 2 == 1
        f = fmts["table_cell_alt"] if alt else fmts["table_cell"]
        qf = fmts["qty_alt"] if alt else fmts["qty"]
        mf = fmts["money_ars_alt"] if alt else fmts["money_ars"]
        pf = fmts["pct_alt"] if alt else fmts["pct"]

        ws.write(r, 0, p["ticker"], f)
        ws.write(r, 1, p["tipo"], f)
        ws.write(r, 2, p.get("cantidad") or 0, qf)
        ws.write(r, 3, p.get("precio_compra") or 0, mf)
        ws.write(r, 4, p.get("precio_actual") or 0, mf)
        ws.write(r, 5, p.get("valor_actual_ars") or 0, mf)
        ws.write(r, 6, p.get("pnl_ars") or 0, mf)
        ws.write(r, 7, (p.get("pnl_pct") or 0) / 100, pf)
        if p.get("pnl_real_pct") is not None:
            ws.write(r, 8, (p["pnl_real_pct"] or 0) / 100, pf)
        else:
            ws.write(r, 8, "—", f)
        ws.write(r, 9, ((p.get("valor_actual_ars") or 0) / total if total else 0),
                 wb_clone_with_numformat(wb, pf, '0.00%'))

    # Fila total
    tr = 3 + len(positions)
    total_fmt = wb.add_format({
        "font_name": "Calibri", "font_size": 10, "bold": True,
        "bg_color": "#EBF4FF", "font_color": COLOR_ACCENT,
        "border": 1, "border_color": COLOR_ACCENT, "align": "right",
    })
    ws.merge_range(tr, 0, tr, 4, "TOTAL CARTERA", total_fmt)
    ws.write(tr, 5, total,
             wb_clone_with_numformat(wb, total_fmt, '"$ "#,##0.00'))
    pnl_total = sum((p.get("pnl_ars") or 0) for p in positions)
    ws.write(tr, 6, pnl_total,
             wb_clone_with_numformat(wb, total_fmt, '"$ "#,##0.00;[Red]"-$ "#,##0.00'))
    ws.merge_range(tr, 7, tr, 9, "", total_fmt)


def _hoja_performance(wb, fmts):
    ws = wb.add_worksheet("Performance")
    ws.set_column(0, 0, 14)
    ws.set_column(1, 1, 18)
    ws.hide_gridlines(2)

    ws.merge_range(0, 0, 0, 5, "PERFORMANCE Y RIESGO", fmts["title"])

    df = load_tenencias()
    if df.empty:
        ws.write(2, 0, "Sin tenencias.", fmts["table_cell"])
        return
    curve = equity_curve(df, period="6mo")
    if curve.empty:
        ws.write(2, 0, "Sin equity curve disponible.", fmts["table_cell"])
        return

    # Metricas
    rets = returns_from_prices(curve)
    stats = [
        ("CAGR (anualizado)",    cagr(curve)),
        ("Volatilidad anual",    volatility(rets, True)),
        ("Sharpe Ratio",         sharpe(rets)),
        ("Sortino Ratio",        sortino(rets)),
        ("Max Drawdown",         max_drawdown(curve)),
        ("Retorno periodo",      curve.iloc[-1] / curve.iloc[0] - 1),
        ("Dias periodo",         len(curve)),
    ]
    ws.merge_range(2, 0, 2, 1, "Metricas cuantitativas", fmts["section"])
    ws.write(3, 0, "Metrica", fmts["table_header"])
    ws.write(3, 1, "Valor", fmts["table_header"])
    for i, (name, val) in enumerate(stats):
        r = 4 + i
        alt = i % 2 == 1
        f = fmts["table_cell_alt"] if alt else fmts["table_cell"]
        ws.write(r, 0, name, f)
        if "Sharpe" in name or "Sortino" in name:
            ws.write(r, 1, val,
                     wb_clone_with_numformat(wb,
                         fmts["table_cell_alt"] if alt else fmts["table_cell"],
                         '0.000'))
        elif "Dias" in name:
            ws.write(r, 1, val, f)
        else:
            ws.write(r, 1, val,
                     wb_clone_with_numformat(wb,
                         fmts["table_cell_alt"] if alt else fmts["table_cell"],
                         '+0.00%;[Red]-0.00%'))

    # Datos de la equity curve (para chart)
    ws.merge_range(2, 3, 2, 5, "Equity curve diaria", fmts["section"])
    ws.write(3, 3, "Fecha", fmts["table_header"])
    ws.write(3, 4, "Valor (ARS)", fmts["table_header"])
    date_fmt = wb.add_format({"font_name": "Calibri", "font_size": 9,
                              "num_format": "yyyy-mm-dd",
                              "border": 1, "border_color": "#E5E7EB",
                              "align": "center"})
    money_small = wb.add_format({"font_name": "Calibri", "font_size": 9,
                                  "num_format": '"$ "#,##0',
                                  "border": 1, "border_color": "#E5E7EB",
                                  "align": "right"})
    for i, (idx, val) in enumerate(curve.items()):
        r = 4 + i
        ws.write_datetime(r, 3, idx.to_pydatetime(), date_fmt)
        ws.write(r, 4, float(val), money_small)

    # Chart line de equity
    n = len(curve)
    chart = wb.add_chart({"type": "line"})
    chart.add_series({
        "name":       "Portfolio (ARS)",
        "categories": ["Performance", 4, 3, 4 + n - 1, 3],
        "values":     ["Performance", 4, 4, 4 + n - 1, 4],
        "line":       {"color": COLOR_GREEN, "width": 2.25},
    })
    chart.set_title({"name": "Equity curve (6 meses)",
                     "name_font": {"size": 12, "bold": True, "color": COLOR_HEADER}})
    chart.set_legend({"position": "bottom"})
    chart.set_size({"width": 600, "height": 280})
    chart.set_x_axis({"date_axis": True, "num_format": "mmm yyyy"})
    chart.set_y_axis({"num_format": '"$ "#,##0'})
    ws.insert_chart(13, 0, chart)


def _hoja_benchmarks(wb, fmts, context: dict):
    ws = wb.add_worksheet("Benchmarks")
    ws.set_column(0, 0, 24)
    ws.set_column(1, 2, 16)
    ws.hide_gridlines(2)

    ws.merge_range(0, 0, 0, 4, "COMPARATIVA VS BENCHMARKS", fmts["title"])

    bm = context.get("benchmarks")
    if not bm:
        ws.write(2, 0, "Sin datos de benchmarks (equity curve insuficiente).",
                 fmts["table_cell"])
        return

    port_ret = bm.get("portfolio_retorno_pct", 0) / 100
    comp = bm.get("comparativas", {})
    dias = bm.get("dias_calendario")

    ws.merge_range(2, 0, 2, 4,
        f"Periodo: {bm.get('periodo_desde')} a {bm.get('periodo_hasta')} ({dias} dias)",
        fmts["subtitle"])

    # Tabla de retornos
    ws.write(4, 0, "Activo / Benchmark", fmts["table_header"])
    ws.write(4, 1, "Retorno periodo", fmts["table_header"])
    ws.write(4, 2, "Diferencia vs portfolio", fmts["table_header"])

    rows = [("Tu portfolio", port_ret, 0)]
    label_map = {
        "merval_ars_pct":       "Merval (ARS)",
        "spy_en_ars_pct":       "S&P 500 (en ARS)",
        "spy_usd_pct":          "S&P 500 (USD)",
        "usd_mep_buyhold_pct":  "USD MEP (buy & hold)",
        "inflacion_acumulada_pct": "Inflacion CER",
    }
    for key, label in label_map.items():
        v = comp.get(key)
        if v is None:
            continue
        v_dec = v / 100
        rows.append((label, v_dec, port_ret - v_dec))

    for i, (label, val, diff) in enumerate(rows):
        r = 5 + i
        alt = i % 2 == 1
        is_port = i == 0
        f = fmts["table_cell_alt"] if alt else fmts["table_cell"]
        if is_port:
            f = wb.add_format({
                "font_name": "Calibri", "font_size": 10, "bold": True,
                "bg_color": "#EBF4FF", "font_color": COLOR_ACCENT,
                "border": 1, "border_color": COLOR_ACCENT,
            })
        ws.write(r, 0, label, f)
        ws.write(r, 1, val, wb_clone_with_numformat(wb, f, '+0.00%;[Red]-0.00%'))
        if i == 0:
            ws.write(r, 2, "—", f)
        else:
            ws.write(r, 2, diff,
                     wb_clone_with_numformat(wb, f, '+0.00 "pp";[Red]-0.00 "pp"'))

    # Chart de barras horizontal
    chart = wb.add_chart({"type": "bar"})
    chart.add_series({
        "name":       "Retorno",
        "categories": ["Benchmarks", 5, 0, 5 + len(rows) - 1, 0],
        "values":     ["Benchmarks", 5, 1, 5 + len(rows) - 1, 1],
        "data_labels": {"value": True, "num_format": '0.00%'},
        "fill":       {"color": COLOR_ACCENT},
        "points": [
            {"fill": {"color": COLOR_GREEN if i == 0 else
                      (COLOR_RED if v[1] < 0 else "#94A3B8")}}
            for i, v in enumerate(rows)
        ],
    })
    chart.set_title({"name": "Retornos comparados",
                     "name_font": {"size": 12, "bold": True, "color": COLOR_HEADER}})
    chart.set_legend({"none": True})
    chart.set_x_axis({"num_format": '+0.00%;-0.00%'})
    chart.set_size({"width": 600, "height": 280})
    ws.insert_chart(5, 4, chart, {"x_offset": 30})


def _hoja_benchmark_curves(wb, fmts):
    """Hoja con las curvas diarias normalizadas a 100 y chart line comparativo."""
    ws = wb.add_worksheet("Equity vs BMs")
    ws.set_column(0, 0, 14)
    ws.set_column(1, 5, 13)
    ws.hide_gridlines(2)

    ws.merge_range(0, 0, 0, 5, "EQUITY CURVES COMPARADAS (base 100)", fmts["title"])

    df = benchmark_curves(period="6mo")
    if df.empty:
        ws.write(2, 0, "Sin datos.", fmts["table_cell"])
        return

    cols = ["Portfolio", "Merval", "SPY (ARS)", "USD MEP", "Inflación"]
    cols = [c for c in cols if c in df.columns]

    ws.write(2, 0, "Fecha", fmts["table_header"])
    for ci, col in enumerate(cols):
        ws.write(2, ci + 1, col, fmts["table_header"])

    date_fmt = wb.add_format({"font_name": "Calibri", "font_size": 9,
                              "num_format": "yyyy-mm-dd",
                              "border": 1, "border_color": "#E5E7EB",
                              "align": "center"})
    num_fmt = wb.add_format({"font_name": "Calibri", "font_size": 9,
                             "num_format": '0.00',
                             "border": 1, "border_color": "#E5E7EB",
                             "align": "right"})
    for i, (idx, row) in enumerate(df.iterrows()):
        r = 3 + i
        ws.write_datetime(r, 0, idx.to_pydatetime(), date_fmt)
        for ci, col in enumerate(cols):
            v = row[col]
            if pd.isna(v):
                ws.write_blank(r, ci + 1, None, num_fmt)
            else:
                ws.write(r, ci + 1, float(v), num_fmt)
    n = len(df)

    # Chart line
    chart = wb.add_chart({"type": "line"})
    colors = {"Portfolio": COLOR_GREEN, "Merval": "#60A5FA",
              "SPY (ARS)": "#A78BFA", "USD MEP": "#FBBF24",
              "Inflación": "#FB7185"}
    for ci, col in enumerate(cols):
        chart.add_series({
            "name":       col,
            "categories": ["Equity vs BMs", 3, 0, 3 + n - 1, 0],
            "values":     ["Equity vs BMs", 3, ci + 1, 3 + n - 1, ci + 1],
            "line":       {"color": colors.get(col, "#9CA3AF"),
                           "width": 2.5 if col == "Portfolio" else 1.5},
        })
    chart.set_title({"name": "Equity curves comparadas (base 100)",
                     "name_font": {"size": 12, "bold": True, "color": COLOR_HEADER}})
    chart.set_legend({"position": "bottom"})
    chart.set_size({"width": 650, "height": 320})
    chart.set_y_axis({"num_format": "0"})
    ws.insert_chart(2, 7, chart)


def wb_clone_with_numformat(wb, base_fmt, numfmt: str):
    """Crea un Format nuevo basado en otro, cambiando solo num_format.
    xlsxwriter no permite modificar formatos in-place asi que clonamos."""
    props = base_fmt.__dict__.copy() if hasattr(base_fmt, "__dict__") else {}
    # Estrategia simple: creamos un format nuevo con num_format. Para mantener
    # consistencia visual, asumimos que el usuario llama esto en celdas
    # donde el formato visual ya esta dado por el background.
    return wb.add_format({"num_format": numfmt,
                          "border": 1, "border_color": "#E5E7EB",
                          "align": "right", "bold": True,
                          "font_name": "Calibri", "font_size": 10})


def build_excel_report() -> bytes:
    """Construye el Excel completo y devuelve los bytes para download_button."""
    ctx = build_portfolio_context()
    ifa = get_ifa_profile() or {}

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    fmts = _setup_formats(wb)

    _hoja_resumen(wb, fmts, ctx, ifa)
    _hoja_posiciones(wb, fmts, ctx)
    _hoja_performance(wb, fmts)
    _hoja_benchmarks(wb, fmts, ctx)
    _hoja_benchmark_curves(wb, fmts)

    wb.close()
    return buf.getvalue()
