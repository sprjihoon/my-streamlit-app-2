# -*- coding: utf-8 -*-
"""
logic/estimate_pdf.py – 물류대행 서비스 견적서 PDF 템플릿
────────────────────────────────────────────────────────────────
청구서와 별도로 운영되는 견적서 전용 PDF 생성 모듈.
• ReportLab + NanumGothic 폰트
• 문서번호, 견적일자, 수신, 건명, 공급자 정보
• 항목 테이블 (품명, 수량, 단가, 금액, 비고)
• 합계, 부가세, 견적금액
• 유효기간 및 주의사항

Usage:
    from logic.estimate_pdf import create_estimate_pdf
    
    pdf_bytes = create_estimate_pdf(
        estimate_date="2025-12-30",
        recipient_name="업체명 귀하",
        title="물류대행 서비스 견적서",
        supplier_info={...},
        items=[...],
    )
"""

from __future__ import annotations

import io
import os
from datetime import datetime
from typing import List, Dict, Any

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
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

# 폰트 이름
FONT_NAME = "NanumGothic"
FONT_NAME_BOLD = "NanumGothicBold"

# assets 디렉토리 경로
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

_font_registered = False


def _register_korean_font():
    """한글 TTF 폰트 등록 (assets 폴더 우선, 시스템 폰트 대체)"""
    global _font_registered, FONT_NAME, FONT_NAME_BOLD
    if _font_registered:
        return True
    
    # 1. assets 폴더의 나눔고딕 시도
    nanum_path = os.path.join(ASSETS_DIR, "NanumGothic.ttf")
    nanum_bold_path = os.path.join(ASSETS_DIR, "NanumGothic-Bold.ttf")
    
    try:
        if os.path.exists(nanum_path):
            FONT_NAME = "NanumGothic"
            FONT_NAME_BOLD = "NanumGothicBold"
            pdfmetrics.registerFont(TTFont(FONT_NAME, nanum_path))
            if os.path.exists(nanum_bold_path):
                pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, nanum_bold_path))
            else:
                pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, nanum_path))
            registerFontFamily(FONT_NAME, normal=FONT_NAME, bold=FONT_NAME_BOLD)
            _font_registered = True
            return True
    except Exception as e:
        print(f"Assets NanumGothic font registration failed: {e}")
    
    # 2. Windows 맑은 고딕 시도
    try:
        regular_path = r"C:\Windows\Fonts\malgun.ttf"
        bold_path = r"C:\Windows\Fonts\malgunbd.ttf"
        if os.path.exists(regular_path):
            FONT_NAME = "Malgun"
            FONT_NAME_BOLD = "MalgunBold"
            pdfmetrics.registerFont(TTFont(FONT_NAME, regular_path))
            if os.path.exists(bold_path):
                pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, bold_path))
            else:
                pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, regular_path))
            registerFontFamily(FONT_NAME, normal=FONT_NAME, bold=FONT_NAME_BOLD)
            _font_registered = True
            return True
    except Exception as e:
        print(f"Malgun font registration failed: {e}")
    
    # 3. Windows 시스템 나눔고딕 시도
    try:
        nanum_sys = r"C:\Windows\Fonts\NanumGothic.ttf"
        nanum_sys_bold = r"C:\Windows\Fonts\NanumGothicBold.ttf"
        if os.path.exists(nanum_sys):
            FONT_NAME = "Nanum"
            FONT_NAME_BOLD = "NanumBold"
            pdfmetrics.registerFont(TTFont(FONT_NAME, nanum_sys))
            if os.path.exists(nanum_sys_bold):
                pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, nanum_sys_bold))
            else:
                pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, nanum_sys))
            registerFontFamily(FONT_NAME, normal=FONT_NAME, bold=FONT_NAME_BOLD)
            _font_registered = True
            return True
    except Exception as e:
        print(f"System NanumGothic font registration failed: {e}")
    
    print("WARNING: No Korean font found. PDF will use Helvetica")
    return False


# 모듈 로드 시 폰트 등록
_font_available = _register_korean_font()


def _get_font():
    """사용 가능한 폰트 반환"""
    if _font_available:
        return FONT_NAME, FONT_NAME_BOLD
    return "Helvetica", "Helvetica-Bold"


class EstimatePDF:
    """물류대행 서비스 견적서 PDF 빌더"""
    
    def __init__(self, buffer: io.BytesIO):
        self.buffer = buffer
        self.elements = []
        self.font_name, self.font_bold = _get_font()
        self._init_doc()
        self._init_styles()
    
    def _init_doc(self):
        self.doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
            title="물류대행 서비스 견적서",
        )
    
    def _init_styles(self):
        self.title_style = ParagraphStyle(
            "Title",
            fontName=self.font_bold,
            fontSize=18,
            leading=24,
            alignment=1,  # CENTER
            textColor=colors.black,
        )
        self.header_style = ParagraphStyle(
            "Header",
            fontName=self.font_bold,
            fontSize=10,
            leading=14,
            textColor=colors.black,
        )
        self.body_style = ParagraphStyle(
            "Body",
            fontName=self.font_name,
            fontSize=9,
            leading=12,
            textColor=colors.black,
        )
        self.small_style = ParagraphStyle(
            "Small",
            fontName=self.font_name,
            fontSize=8,
            leading=10,
            textColor=colors.black,
        )
        self.notice_style = ParagraphStyle(
            "Notice",
            fontName=self.font_name,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#555555"),
        )
    
    def build(
        self,
        doc_number: str,
        estimate_date: str,
        recipient_name: str,
        title: str,
        supplier_info: Dict[str, str],
        items: List[Dict[str, Any]],
        stamp_holder: str = "",
        manager: str = "",
        company_name: str = "",
        recipient_contact: str = "",
        recipient_email: str = "",
        validity_days: int = 15,
    ):
        """견적서 PDF 생성"""
        
        # 1. 제목
        self._add_title_section(doc_number, estimate_date, stamp_holder, manager)
        
        # 2. 수신/연락처/이메일/건명
        self._add_recipient_section(
            recipient_name, title,
            recipient_contact=recipient_contact,
            recipient_email=recipient_email,
        )
        
        # 3. 공급자 정보
        self._add_supplier_section(supplier_info)
        
        # 4. 항목 테이블
        subtotal, vat, total = self._add_items_table(items)
        
        # 5. 합계
        self._add_summary_section(subtotal, vat, total)
        
        # 6. 유효기간 및 주의사항
        self._add_notice_section(validity_days)
        
        # 7. 하단 - 상기와 같이 견적 드립니다 + 회사명
        self._add_footer_section(estimate_date, company_name)
        
        # PDF 빌드
        self.doc.build(self.elements)
    
    def _add_title_section(
        self,
        doc_number: str,
        estimate_date: str,
        stamp_holder: str,
        manager: str,
    ):
        """제목 및 문서번호 섹션"""
        
        # 담당/대표 정보 (오른쪽 상단)
        right_info = f"""
        <para align=right>
        <font size=8>담당: {manager or '-'}</font><br/>
        <font size=8>대표: {stamp_holder or '-'}</font>
        </para>
        """
        
        # 제목 테이블
        title_table = Table(
            [
                [
                    "",
                    Paragraph("<b>물류대행 서비스 견적서</b>", self.title_style),
                    Paragraph(right_info, self.small_style),
                ]
            ],
            colWidths=[30 * mm, 120 * mm, 30 * mm],
        )
        title_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ]))
        
        self.elements.append(title_table)
        self.elements.append(Spacer(1, 3 * mm))
        
        # 문서번호/견적일자
        meta_table = Table(
            [
                [
                    Paragraph("<b>문서번호</b>", self.header_style),
                    Paragraph(doc_number, self.body_style),
                    Paragraph("<b>견적일자</b>", self.header_style),
                    Paragraph(estimate_date, self.body_style),
                ]
            ],
            colWidths=[25 * mm, 60 * mm, 25 * mm, 60 * mm],
        )
        meta_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#E0E0E0")),
            ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#E0E0E0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        
        self.elements.append(meta_table)
        self.elements.append(Spacer(1, 2 * mm))
    
    def _add_recipient_section(
        self,
        recipient_name: str,
        title: str,
        recipient_contact: str = "",
        recipient_email: str = "",
    ):
        """수신/연락처/이메일/건명 섹션"""
        rows = [
            [
                Paragraph("<b>수신</b>", self.header_style),
                Paragraph(recipient_name or "-", self.body_style),
            ],
        ]
        if recipient_contact:
            rows.append([
                Paragraph("<b>연락처</b>", self.header_style),
                Paragraph(recipient_contact, self.body_style),
            ])
        if recipient_email:
            rows.append([
                Paragraph("<b>이메일</b>", self.header_style),
                Paragraph(recipient_email, self.body_style),
            ])
        rows.append([
            Paragraph("<b>건명</b>", self.header_style),
            Paragraph(title, self.body_style),
        ])
        table = Table(rows, colWidths=[25 * mm, 145 * mm])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E0E0E0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        
        self.elements.append(table)
        self.elements.append(Spacer(1, 2 * mm))
    
    def _add_supplier_section(self, supplier_info: Dict[str, str]):
        """공급자 정보 섹션"""
        biz_no = supplier_info.get("사업자번호", "")
        name = supplier_info.get("상호", "")
        address = supplier_info.get("소재지", "")
        biz_type = supplier_info.get("업태", "")
        biz_item = supplier_info.get("종목", "")
        
        table = Table(
            [
                [
                    Paragraph("<b>공급자</b>", self.header_style),
                    Paragraph("<b>사업자번호</b>", self.small_style),
                    Paragraph(biz_no, self.small_style),
                    Paragraph("<b>상호</b>", self.small_style),
                    Paragraph(name, self.small_style),
                ],
                [
                    "",
                    Paragraph("<b>소재지</b>", self.small_style),
                    Paragraph(address, self.small_style),
                    "",
                    "",
                ],
                [
                    "",
                    Paragraph("<b>업태</b>", self.small_style),
                    Paragraph(biz_type, self.small_style),
                    Paragraph("<b>종목</b>", self.small_style),
                    Paragraph(biz_item, self.small_style),
                ],
            ],
            colWidths=[25 * mm, 25 * mm, 50 * mm, 20 * mm, 50 * mm],
        )
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E0E0E0")),
            ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#F5F5F5")),
            ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#F5F5F5")),
            ("BACKGROUND", (3, 2), (3, 2), colors.HexColor("#F5F5F5")),
            ("SPAN", (0, 0), (0, 2)),
            ("SPAN", (2, 1), (4, 1)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        
        self.elements.append(table)
        self.elements.append(Spacer(1, 3 * mm))
    
    def _add_items_table(self, items: List[Dict[str, Any]]) -> tuple:
        """항목 테이블 추가"""
        
        # 헤더
        header = [
            Paragraph("<b>No</b>", self.small_style),
            Paragraph("<b>품명</b>", self.small_style),
            Paragraph("<b>수량</b>", self.small_style),
            Paragraph("<b>단가</b>", self.small_style),
            Paragraph("<b>금액</b>", self.small_style),
            Paragraph("<b>비고</b>", self.small_style),
        ]
        
        data = [header]
        subtotal = 0
        
        for i, item in enumerate(items, 1):
            qty = int(float(item.get("수량", 0)))
            unit_price = int(float(item.get("단가", 0)))
            amount = int(float(item.get("금액", qty * unit_price)))
            subtotal += amount
            
            data.append([
                Paragraph(str(i), self.small_style),
                Paragraph(str(item.get("항목", "")), self.small_style),
                Paragraph(f"{qty:,}" if qty else "", self.small_style),
                Paragraph(f"{unit_price:,}" if unit_price else "", self.small_style),
                Paragraph(f"{amount:,}" if amount else "", self.small_style),
                Paragraph(str(item.get("비고", "") or ""), self.small_style),
            ])
        
        table = Table(
            data,
            colWidths=[10 * mm, 58 * mm, 15 * mm, 15 * mm, 20 * mm, 52 * mm],
        )
        
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
            ("FONTNAME", (0, 0), (-1, -1), self.font_name),
            ("FONTNAME", (0, 0), (-1, 0), self.font_bold),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 1), (4, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        
        self.elements.append(table)
        
        # 부가세 계산 (10%)
        vat = int(subtotal * 0.1)
        total = subtotal + vat
        
        return subtotal, vat, total
    
    def _add_summary_section(self, subtotal: int, vat: int, total: int):
        """합계 섹션"""
        
        table = Table(
            [
                [
                    Paragraph("<b>합계</b>", self.header_style),
                    "",
                    Paragraph(f"₩ {subtotal:,}", self.body_style),
                ],
            ],
            colWidths=[25 * mm, 120 * mm, 25 * mm],
        )
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#E0E0E0")),
            ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        
        self.elements.append(table)
        
        # 합계 금액, 부가세, 견적금액
        summary_table = Table(
            [
                [
                    Paragraph("<b>합계 금액</b>", self.small_style),
                    Paragraph(f"₩ {subtotal:,}", self.body_style),
                    Paragraph("<b>부가세</b>", self.small_style),
                    Paragraph(f"₩ {vat:,}", self.body_style),
                    Paragraph("<b>견적금액</b>", self.small_style),
                    Paragraph(f"<b>₩ {total:,}</b>", self.header_style),
                ],
            ],
            colWidths=[25 * mm, 35 * mm, 20 * mm, 30 * mm, 25 * mm, 35 * mm],
        )
        summary_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#E0E0E0")),
            ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#E0E0E0")),
            ("BACKGROUND", (4, 0), (4, 0), colors.HexColor("#E0E0E0")),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("ALIGN", (3, 0), (3, 0), "RIGHT"),
            ("ALIGN", (5, 0), (5, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        
        self.elements.append(summary_table)
        self.elements.append(Spacer(1, 5 * mm))
    
    def _add_notice_section(self, validity_days: int = 15):
        """유효기간 및 주의사항 섹션"""
        
        notices = [
            f"• 본 견적서는 발행일로부터 {validity_days}일간 유효합니다.",
            "• 본 견적은 예상 물량 기준이며, 실제 작업량에 따라 변동될 수 있습니다.",
            "• 추가 작업 발생 시 별도 비용이 청구될 수 있습니다.",
            "• 부가세(VAT)는 별도입니다.",
        ]
        
        notice_text = "<br/>".join(notices)
        
        table = Table(
            [
                [
                    Paragraph("<b>안내사항</b>", self.header_style),
                    Paragraph(notice_text, self.notice_style),
                ],
            ],
            colWidths=[25 * mm, 145 * mm],
        )
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#E0E0E0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        
        self.elements.append(table)
    
    def _add_footer_section(self, estimate_date: str, company_name: str):
        """하단 섹션 - 상기와 같이 견적 드립니다 + 날짜 + 회사명"""
        
        self.elements.append(Spacer(1, 8 * mm))
        
        # "상기와 같이 견적 드립니다." 문구
        request_text = Paragraph(
            "<para align=center><b>상기와 같이 견적 드립니다.</b></para>",
            self.header_style
        )
        self.elements.append(request_text)
        self.elements.append(Spacer(1, 5 * mm))
        
        # 날짜 (한국어 형식)
        try:
            dt = datetime.strptime(estimate_date, "%Y-%m-%d")
            weekdays = ['월', '화', '수', '목', '금', '토', '일']
            date_str = f"{dt.year}년 {dt.month:02d}월 {dt.day:02d}일 {weekdays[dt.weekday()]}요일"
        except:
            date_str = estimate_date
        
        date_text = Paragraph(
            f"<para align=center>{date_str}</para>",
            self.body_style
        )
        self.elements.append(date_text)
        self.elements.append(Spacer(1, 10 * mm))
        
        # 회사명 (가운데 정렬)
        company_text = Paragraph(
            f"<para align=center><b>{company_name}</b></para>",
            self.title_style
        )
        self.elements.append(company_text)


def create_estimate_pdf(
    estimate_date: str,
    recipient_name: str,
    title: str,
    supplier_info: Dict[str, str],
    items: List[Dict[str, Any]],
    stamp_holder: str = "",
    manager: str = "",
    company_name: str = "",
    recipient_contact: str = "",
    recipient_email: str = "",
    validity_days: int = 15,
) -> bytes:
    """
    물류대행 서비스 견적서 PDF 생성.
    
    Args:
        estimate_date: 견적일자 (YYYY-MM-DD)
        recipient_name: 수신자명 (업체명 등)
        title: 건명
        supplier_info: 공급자 정보 {사업자번호, 상호, 소재지, 업태, 종목}
        items: 항목 리스트 [{항목, 수량, 단가, 금액, 비고}, ...]
        stamp_holder: 대표자명
        manager: 담당자명
        company_name: 회사명 (하단에 표시)
        recipient_contact: 수신자 연락처
        recipient_email: 수신자 이메일
        validity_days: 견적 유효기간 (일, 기본 15일)
    
    Returns:
        PDF 바이트 데이터
    """
    buffer = io.BytesIO()
    
    # 문서번호 생성
    doc_number = f"EST-{estimate_date.replace('-', '')}"
    
    pdf = EstimatePDF(buffer)
    pdf.build(
        doc_number=doc_number,
        estimate_date=estimate_date,
        recipient_name=recipient_name,
        title=title,
        supplier_info=supplier_info,
        items=items,
        stamp_holder=stamp_holder,
        manager=manager,
        company_name=company_name,
        recipient_contact=recipient_contact,
        recipient_email=recipient_email,
        validity_days=validity_days,
    )
    
    buffer.seek(0)
    return buffer.getvalue()
