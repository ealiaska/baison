"""PDF-счёт-оценка в фирменных цветах baisón (антрацит / тициановый).

Шрифт: Arial с Windows (кириллица); без шрифта — Helvetica (кириллица не
отобразится, но файл создастся).
"""
import os
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ---- Фирменные цвета ----
ANTHRACITE = colors.HexColor("#1b1f25")
ANTHRACITE_SOFT = colors.HexColor("#f2f3f5")
TIZIAN = colors.HexColor("#c2451e")
INK_500 = colors.HexColor("#5b6572")
BORDER = colors.HexColor("#e4e7ec")

_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"


def _register_fonts():
    """Arial (Windows) поддерживает кириллицу; ищем, если есть."""
    global _FONT, _FONT_BOLD
    candidates = [
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"),
        "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    bold_candidates = [
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arialbd.ttf"),
        "/usr/share/fonts/truetype/msttcorefonts/Arial-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    try:
        for path in candidates:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont("BaisA", path))
                _FONT = "BaisA"
                break
        for path in bold_candidates:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont("BaisB", path))
                _FONT_BOLD = "BaisB"
                break
    except Exception:
        _FONT, _FONT_BOLD = "Helvetica", "Helvetica-Bold"


_registered = False


def money(value) -> str:
    try:
        return f"{float(value or 0):,.0f}".replace(",", " ") + " ₸"
    except (TypeError, ValueError):
        return "0 ₸"


def build_invoice_pdf(inv) -> bytes:
    """Собирает PDF по счёту (Invoice) и возвращает байты."""
    global _registered
    if not _registered:
        _register_fonts()
        _registered = True

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Счёт {inv.number}", author="baisón",
    )

    brand = ParagraphStyle(
        "brand", fontName=_FONT_BOLD, fontSize=26, leading=30,
        textColor=TIZIAN, spaceAfter=0)
    doc_title = ParagraphStyle(
        "doctitle", fontName=_FONT_BOLD, fontSize=17, leading=21,
        textColor=ANTHRACITE)
    meta = ParagraphStyle(
        "meta", fontName=_FONT, fontSize=10.5, leading=15, textColor=INK_500)
    cell = ParagraphStyle(
        "cell", fontName=_FONT, fontSize=10.5, leading=14, textColor=ANTHRACITE)
    cell_bold = ParagraphStyle(
        "cellbold", parent=cell, fontName=_FONT_BOLD)
    head_cell = ParagraphStyle(
        "headcell", parent=cell, fontName=_FONT_BOLD,
        textColor=colors.white)
    head_cell_r = ParagraphStyle(
        "headcellr", parent=head_cell, alignment=2)
    total_cell = ParagraphStyle(
        "total", fontName=_FONT_BOLD, fontSize=12, leading=16, textColor=TIZIAN)
    foot = ParagraphStyle(
        "foot", fontName=_FONT, fontSize=9, leading=13,
        textColor=INK_500, alignment=1)

    valid_until = inv.valid_until.strftime("%d.%m.%Y") if inv.valid_until else "—"
    created = inv.created_at.strftime("%d.%m.%Y")
    story = []
    client = inv.client
    client_name = client.name if client else "—"
    client_extra = []
    if client and client.phone:
        client_extra.append(client.phone)
    if client and client.company:
        client_extra.append(client.company)

    # ---------- Шапка ----------
    head = Table([
        [Paragraph("baisón", brand),
         Paragraph("Счёт-оценка", ParagraphStyle(
             "dt", parent=doc_title, alignment=2))],
        [Paragraph(
            f"№ {inv.number}  ·  от {created}", meta),
         Paragraph(
             ("Действителен до " + valid_until),
             ParagraphStyle("v", parent=meta, alignment=2))],
    ], colWidths=[95 * mm, 95 * mm])
    head.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(head)
    story.append(Spacer(1, 8))
    client_line = f"<b>Клиент:</b> {client_name}"
    if client_extra:
        client_line += "  ·  " + "  ·  ".join(client_extra)
    story.append(Paragraph(client_line, cell))

    # линейка
    rule = Table([[""]], colWidths=[190 * mm], rowHeights=[2.2])
    rule.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TIZIAN),
        ("LINEBELOW", (0, 0), (-1, -1), 0, TIZIAN),
    ]))
    story.append(Spacer(1, 8))
    story.append(rule)
    story.append(Spacer(1, 12))

    # ---------- Таблица позиций ----------
    rows = [[
        Paragraph("№", head_cell),
        Paragraph("Наименование", head_cell),
        Paragraph("Кол-во", head_cell_r),
        Paragraph("Цена", head_cell_r),
        Paragraph("Сумма", head_cell_r),
    ]]
    for i, item in enumerate(inv.items, 1):
        name = item.product_name or (
            item.product.name if item.product else "—")
        rows.append([
            Paragraph(str(i), cell),
            Paragraph(name, cell),
            Paragraph(f"{float(item.qty or 0):g}",
                      ParagraphStyle("r", parent=cell, alignment=2)),
            Paragraph(money(item.price),
                      ParagraphStyle("r", parent=cell, alignment=2)),
            Paragraph(money(item.total),
                      ParagraphStyle("r", parent=cell, alignment=2)),
        ])
    rows.append([
        "", "", "",
        Paragraph("<b>ИТОГО</b>", ParagraphStyle("rb", parent=cell_bold, alignment=2)),
        Paragraph(money(inv.total), ParagraphStyle("rt", parent=total_cell, alignment=2)),
    ])

    data = Table(rows, colWidths=[12 * mm, 86 * mm, 24 * mm, 34 * mm, 34 * mm],
                 repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), ANTHRACITE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, ANTHRACITE_SOFT]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
        ("BACKGROUND", (0, -1), (-1, -1), ANTHRACITE_SOFT),
        ("LINEABOVE", (0, -1), (-1, -1), 1.2, TIZIAN),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    data.setStyle(TableStyle(style))
    story.append(data)

    if inv.comment:
        story.append(Spacer(1, 14))
        story.append(Paragraph(f"<b>Комментарий:</b> {inv.comment}", cell))

    story.append(Spacer(1, 30))
    story.append(Paragraph(
        "ТОО «Байсон»  ·  Кызылорда, ул. Мустафы Шокая, 48 и 57  ·  "
        "+7 775 059 48 48  ·  baison.kz", foot))

    doc.build(story)
    return buf.getvalue()
