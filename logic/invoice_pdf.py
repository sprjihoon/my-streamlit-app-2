# -*- coding: utf-8 -*-
"""
logic/invoice_pdf.py – PDF Invoice Template
────────────────────────────────────────────────────
Shared template class (InvoicePDF) for all invoice‑related pages.
• ReportLab + NanumGothic 폰트 내장
• 한·영 다국어 지원 (lang='ko' | 'en')
• add_header / add_company_block / add_items_table / add_footer helpers

Streamlit 의존성 없음 - 순수 Python 클래스.

Usage:
    from logic.invoice_pdf import InvoicePDF

    inv = InvoicePDF('invoice_240428.pdf', lang='ko')
    inv.add_header('INV-2404-001', '2025-04-28')
    inv.add_company_block(seller_dict, buyer_dict)
    inv.add_items_table(items_list)  # [{desc, qty, unit_price}, ...]
    inv.build()
"""

from __future__ import annotations

import os
from datetime import date
from typing import List, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 폰트 경로 설정
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

# 폰트 등록 (존재하는 경우에만)
_font_path = os.path.join(ASSETS_DIR, "NanumGothic.ttf")
_font_bold_path = os.path.join(ASSETS_DIR, "NanumGothic-Bold.ttf")

if os.path.exists(_font_path):
    pdfmetrics.registerFont(TTFont("NanumGothic", _font_path))
if os.path.exists(_font_bold_path):
    pdfmetrics.registerFont(TTFont("NanumGothic-Bold", _font_bold_path))


class InvoicePDF:
    """Lightweight builder class for 1‑page invoices."""

    def __init__(self, filename: str, lang: str = "ko"):
        """
        InvoicePDF 초기화.
        
        Args:
            filename: 출력 PDF 파일명
            lang: 언어 설정 ('ko' 또는 'en')
        """
        self.filename = filename
        self.lang = lang
        self.buffer = []
        self._init_doc()
        self._init_styles()

    # ────────────────────────────────────
    # Internal helpers
    # ────────────────────────────────────
    def _init_doc(self):
        self.doc = SimpleDocTemplate(
            self.filename,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=22 * mm,
            bottomMargin=18 * mm,
            title="Invoice",
        )

    def _init_styles(self):
        # 폰트 존재 여부에 따라 폰트 선택
        font_name = "NanumGothic" if os.path.exists(_font_path) else "Helvetica"
        font_bold = "NanumGothic-Bold" if os.path.exists(_font_bold_path) else "Helvetica-Bold"
        
        self.h1 = ParagraphStyle(
            "Heading1",
            fontName=font_bold,
            fontSize=18,
            leading=22,
            spaceAfter=6 * mm,
        )
        self.body = ParagraphStyle(
            "Body",
            fontName=font_name,
            fontSize=10.5,
            leading=14,
        )
        self.tbl_hdr = ParagraphStyle(
            "TblHeader",
            fontName=font_bold,
            fontSize=9.5,
            leading=13,
        )

    # ────────────────────────────────────
    # Public builder API
    # ────────────────────────────────────
    def add_header(self, inv_no: str, inv_date: str | date):
        """
        인보이스 헤더 추가.
        
        Args:
            inv_no: 인보이스 번호
            inv_date: 인보이스 날짜
        """
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        
        # 로고가 없을 경우 텍스트로 대체
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=48 * mm, height=14 * mm)
        else:
            logo = Paragraph("<b>INVOICE</b>", self.h1)
        
        inv_date = inv_date if isinstance(inv_date, str) else inv_date.strftime("%Y-%m-%d")
        meta = Paragraph(
            f"""
            <para align=right>
            <b>{'청구서' if self.lang == 'ko' else 'INVOICE'}</b><br/>
            No : {inv_no}<br/>
            Date : {inv_date}
            </para>
            """,
            self.body,
        )
        self.buffer.extend([
            Table(
                [[logo, meta]],
                colWidths=[72 * mm, 90 * mm],
                style=[("VALIGN", (0, 0), (-1, -1), "TOP")]
            ),
            Spacer(1, 6 * mm),
        ])

    def add_company_block(self, seller: Dict[str, str], buyer: Dict[str, str]):
        """
        발행자/수신자 정보 블록 추가.
        
        Args:
            seller: 발행자 정보 딕셔너리
            buyer: 수신자 정보 딕셔너리
        """
        fmt = lambda d: "<br/>".join(d.values())
        t = Table(
            [
                [
                    Paragraph("<b>From / 발행자</b>", self.tbl_hdr),
                    Paragraph("<b>To / 수신자</b>", self.tbl_hdr)
                ],
                [
                    Paragraph(fmt(seller), self.body),
                    Paragraph(fmt(buyer), self.body)
                ],
            ],
            colWidths=[78 * mm, 78 * mm],
        )
        t.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.4, "black"),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, "black"),
                    ("BACKGROUND", (0, 0), (-1, 0), "#F4F4F4"),
                ]
            )
        )
        self.buffer.extend([t, Spacer(1, 6 * mm)])

    def add_items_table(self, items: List[Dict]) -> int:
        """
        인보이스 항목 테이블 추가.
        
        Args:
            items: 항목 리스트 [{desc, qty, unit_price}, ...]
        
        Returns:
            총 금액
        """
        header = (
            ["번호", "항목", "수량", "단가", "금액"]
            if self.lang == "ko"
            else ["No", "Description", "Qty", "Unit", "Amount"]
        )
        data = [header]
        total = 0
        for i, it in enumerate(items, 1):
            amt = it["qty"] * it["unit_price"]
            total += amt
            data.append([
                i,
                it["desc"],
                f"{it['qty']:,}",
                f"{it['unit_price']:,}",
                f"{amt:,}",
            ])
        data.append(["", "", "", "Subtotal", f"{total:,}"])
        
        # 폰트 존재 여부에 따라 폰트 선택
        font_bold = "NanumGothic-Bold" if os.path.exists(_font_bold_path) else "Helvetica-Bold"
        
        tbl = Table(data, colWidths=[14 * mm, 72 * mm, 24 * mm, 32 * mm, 32 * mm])
        tbl.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), font_bold),
                    ("BACKGROUND", (0, 0), (-1, 0), "#ECECEC"),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -2), 0.25, "#AAAAAA"),
                    ("BOX", (0, -1), (-1, -1), 0.6, "black"),
                    ("FONTNAME", (0, -1), (-1, -1), font_bold),
                ]
            )
        )
        self.buffer.append(tbl)
        return total

    def add_footer(self, note: str):
        """
        푸터(비고) 추가.
        
        Args:
            note: 비고 내용
        """
        self.buffer.extend([Spacer(1, 4 * mm), Paragraph(note, self.body)])

    def build(self):
        """PDF 파일 생성."""
        self.doc.build(self.buffer)


def create_invoice_pdf(
    filename: str,
    inv_no: str,
    inv_date: str,
    seller: Dict[str, str],
    buyer: Dict[str, str],
    items: List[Dict],
    note: str = "",
    lang: str = "ko"
) -> str:
    """
    인보이스 PDF 생성 헬퍼 함수.
    
    Args:
        filename: 출력 파일명
        inv_no: 인보이스 번호
        inv_date: 인보이스 날짜
        seller: 발행자 정보
        buyer: 수신자 정보
        items: 항목 리스트 [{desc, qty, unit_price}, ...]
        note: 비고
        lang: 언어 ('ko' 또는 'en')
    
    Returns:
        생성된 파일 경로
    """
    inv = InvoicePDF(filename, lang=lang)
    inv.add_header(inv_no, inv_date)
    inv.add_company_block(seller, buyer)
    inv.add_items_table(items)
    if note:
        inv.add_footer(note)
    inv.build()
    return filename

