"""
작업지시서 PDF 생성
──────────────────
프리패킹 작업지시서를 A4 PDF로 생성한다.
- 헤더: 날짜, 요일, 공급처, 총 예측 수량
- 조합 테이블: 조합명, 구성 SKU, 바코드, 구성수량, 예측수량, 필요수량
- 단일 SKU 테이블: 상품명, 바코드, 예측수량
"""
from __future__ import annotations

import io
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

FONT = "NanumGothic"
FONT_B = "NanumGothicBold"
_registered = False


def _register_font():
    global _registered
    if _registered:
        return
    base = os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets")
    if not os.path.isdir(base):
        base = os.path.join("/app", "assets")
    reg = os.path.join(base, "NanumGothic.ttf")
    bold = os.path.join(base, "NanumGothic-Bold.ttf")
    try:
        if os.path.exists(reg):
            pdfmetrics.registerFont(TTFont(FONT, reg))
            pdfmetrics.registerFont(TTFont(FONT_B, bold if os.path.exists(bold) else reg))
            registerFontFamily(FONT, normal=FONT, bold=FONT_B)
            _registered = True
    except Exception:
        pass


def _p(text: str, size: int = 8, bold: bool = False, color: colors.Color = colors.black) -> Paragraph:
    fn = FONT_B if bold and _registered else (FONT if _registered else "Helvetica")
    style = ParagraphStyle("_", fontName=fn, fontSize=size, leading=size + 3, textColor=color)
    return Paragraph(str(text), style)


def generate_work_order_pdf(data: dict) -> bytes:
    _register_font()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )

    elements: list = []
    fn = FONT_B if _registered else "Helvetica-Bold"
    fn_r = FONT if _registered else "Helvetica"

    target_date = data.get("target_date", "")
    weekday_name = data.get("weekday_name", "")
    supplier = data.get("supplier_filter", "전체")
    total_qty = data.get("total_predicted_qty", 0)
    total_items = data.get("total_items", 0)
    combo_count = data.get("combination_count", 0)
    sku_count = data.get("single_sku_count", 0)
    items = data.get("items", [])

    elements.append(_p("프리패킹 작업지시서", 18, bold=True))
    elements.append(Spacer(1, 4 * mm))

    header_data = [
        [_p("대상일", 9, bold=True), _p(f"{target_date} ({weekday_name})", 9),
         _p("공급처", 9, bold=True), _p(supplier or "전체", 9)],
        [_p("총 예측수량", 9, bold=True), _p(f"{total_qty:,}개", 9, bold=True, color=colors.HexColor("#2563eb")),
         _p("항목 수", 9, bold=True), _p(f"조합 {combo_count} + SKU {sku_count} = {total_items}건", 9)],
        [_p("출력일시", 9, bold=True), _p(datetime.now().strftime("%Y-%m-%d %H:%M"), 9),
         _p("", 9), _p("", 9)],
    ]
    ht = Table(header_data, colWidths=[25 * mm, 55 * mm, 25 * mm, 65 * mm])
    ht.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f3f4f6")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(ht)
    elements.append(Spacer(1, 6 * mm))

    combos = [it for it in items if it.get("target_type") == "combination"]
    singles = [it for it in items if it.get("target_type") != "combination"]

    if combos:
        elements.append(_p(f"■ 조합 ({len(combos)}건)", 11, bold=True))
        elements.append(Spacer(1, 2 * mm))

        for ci, combo in enumerate(combos):
            pred_qty = combo.get("predicted_qty", 0)
            sku_items = combo.get("items", [])
            conf = combo.get("confidence_score", 0)

            elements.append(_p(
                f"조합 #{ci + 1}  —  {len(sku_items)}종 구성  |  "
                f"예측: {pred_qty}세트  |  신뢰도: {conf * 100:.0f}%",
                9, bold=True, color=colors.HexColor("#7c3aed"),
            ))
            elements.append(Spacer(1, 1 * mm))

            rows = [
                [_p("상품명", 8, bold=True), _p("옵션", 8, bold=True),
                 _p("바코드", 8, bold=True), _p("구성", 8, bold=True),
                 _p("필요수량", 8, bold=True), _p("체크", 8, bold=True)],
            ]
            for sku in sku_items:
                qty_per = sku.get("qty", 1)
                need = qty_per * pred_qty
                rows.append([
                    _p(sku.get("product_name", "")[:30], 8),
                    _p(sku.get("option_name", "")[:20], 8),
                    _p(sku.get("barcode", "") or sku.get("sku_code", ""), 7),
                    _p(f"x{qty_per}", 8),
                    _p(f"{need:,}개", 9, bold=True, color=colors.HexColor("#059669")),
                    _p("☐", 12),
                ])

            t = Table(rows, colWidths=[50 * mm, 30 * mm, 30 * mm, 14 * mm, 24 * mm, 14 * mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ede9fe")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("ALIGN", (3, 0), (5, -1), "CENTER"),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 4 * mm))

    if singles:
        if combos:
            elements.append(Spacer(1, 2 * mm))
        elements.append(_p(f"■ 단일 SKU ({len(singles)}건)", 11, bold=True))
        elements.append(Spacer(1, 2 * mm))

        rows = [
            [_p("#", 8, bold=True), _p("상품명", 8, bold=True), _p("옵션", 8, bold=True),
             _p("바코드", 8, bold=True), _p("예측수량", 8, bold=True),
             _p("신뢰도", 8, bold=True), _p("체크", 8, bold=True)],
        ]
        for si, sku in enumerate(singles):
            pred = sku.get("predicted_qty", 0)
            conf = sku.get("confidence_score", 0)
            bc = sku.get("barcode", "") or sku.get("sku_code", "")
            rows.append([
                _p(str(si + 1), 8),
                _p(sku.get("target_name", "")[:30], 8),
                _p((sku.get("option_name", "") or "")[:20], 8),
                _p(bc, 7),
                _p(f"{pred:,}개", 9, bold=True, color=colors.HexColor("#2563eb")),
                _p(f"{conf * 100:.0f}%", 8),
                _p("☐", 12),
            ])

        t = Table(rows, colWidths=[10 * mm, 48 * mm, 28 * mm, 30 * mm, 22 * mm, 14 * mm, 14 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fef3c7")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (4, 0), (6, -1), "CENTER"),
        ]))
        elements.append(t)

    elements.append(Spacer(1, 10 * mm))
    elements.append(_p("담당자 서명: ____________________          확인일시: ____________________", 9))

    doc.build(elements)
    return buf.getvalue()
