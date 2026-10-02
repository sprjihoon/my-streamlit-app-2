"""우체국 신형 C형 송장. 용지는 111×171mm 이고, 이 출력은 글자가 가로가 되도록 171×111mm 로 둔다.

칸 위치는 2026-10-02 실접수 답안지(exc2016C)에서 쟀다.
집배코드(A1, 135, 102 등)는 우체국 출력에만 있고 접수 API 응답에는 없어서 비워 둔다.
"""

from __future__ import annotations

import re
from io import BytesIO

import fitz
from reportlab.graphics.barcode import code128
from reportlab.pdfgen.canvas import Canvas

# 답안지 페이지. 171mm × 111mm.
PAGE_W = 484.72
PAGE_H = 314.65

_ZIP_BAR = fitz.Rect(18.0, 120.1, 103.2, 154.2)
_TRACK_BAR = fitz.Rect(172.1, 225.1, 319.6, 275.0)
_SIDE_BAR = fitz.Rect(426.1, 41.5, 435.1, 130.0)


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _tracking(value: object) -> str:
    digits = _digits(value)
    if len(digits) == 13:
        return f"{digits[:5]}-{digits[5:9]}-{digits[9:]}"
    return str(value or "").strip()


def _phone_m(value: object) -> str:
    digits = _digits(value)
    if len(digits) == 11 and digits.startswith("010"):
        return f"M: {digits[:3]}) {digits[3:7]}-{digits[7:]}"
    if len(digits) >= 9:
        return f"M: {digits}"
    return ""


def _phone_t(value: object) -> str:
    digits = _digits(value)
    if len(digits) == 11:
        return f"T: {digits[:3]}-{digits[3:7]}-{digits[7:]}"
    if len(digits) == 12:
        return f"T: {digits[:4]}-{digits[4:7]}-{digits[7:]}"
    if digits:
        return f"T: {digits}"
    return ""


def _date(value: object) -> str:
    digits = _digits(value)
    if len(digits) >= 8:
        return f"{digits[:4]}/{digits[4:6]}/{digits[6:8]}"
    return ""


def _barcode_pixmap(value: str) -> fitz.Pixmap:
    code = "".join(ch for ch in (value or "0") if ch.isdigit()) or "0"
    bar = code128.Code128(code, barHeight=40, barWidth=0.7, humanReadable=False)
    packet = BytesIO()
    canvas = Canvas(packet, pagesize=(bar.width + 4, bar.height + 4))
    bar.drawOn(canvas, 2, 2)
    canvas.save()
    src = fitz.open(stream=packet.getvalue(), filetype="pdf")
    try:
        return src[0].get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False)
    finally:
        src.close()


def _advance(text: str, size: float, font: str) -> float:
    """찍힌 글자 너비. CJK 폰트의 text_length 는 실제보다 짧다."""
    doc = fitz.open()
    try:
        sheet = doc.new_page(width=800, height=80)
        if font == "korea":
            sheet.insert_font(fontname="korea", fontbuffer=fitz.Font("korea").buffer)
        sheet.insert_text((0, 40), text, fontname=font, fontsize=size)
        width = 0.0
        for block in sheet.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                box = line["bbox"]
                width = max(width, box[2] - box[0])
        return width
    finally:
        doc.close()


def _h(page: fitz.Page, x: float, baseline: float, text: str, size: float, font: str = "korea") -> float:
    if not text:
        return x
    page.insert_text((x, baseline), text, fontname=font, fontsize=size)
    return x + _advance(text, size, font)


def _v(page: fitz.Page, x: float, bottom: float, text: str, size: float, font: str = "korea") -> None:
    if text:
        page.insert_text((x, bottom), text, fontname=font, fontsize=size, rotate=90)


def build_domestic_label_pdf(item: dict) -> bytes:
    sender_name = str(item.get("print_sender_name") or item.get("api_sender_name") or "")
    sender_phone = str(item.get("print_sender_phone") or item.get("api_sender_phone") or "")
    sender_zip = _digits(item.get("print_sender_zip") or item.get("api_sender_zip") or "")
    sender_addr1 = str(item.get("print_sender_addr1") or item.get("api_sender_addr1") or "")
    sender_addr2 = str(item.get("print_sender_addr2") or item.get("api_sender_addr2") or "")
    rec_name = str(item.get("recipient_name") or "")
    rec_phone = str(item.get("recipient_phone") or "")
    rec_zip = _digits(item.get("recipient_zip") or "")
    rec_addr1 = str(item.get("recipient_addr1") or "")
    rec_addr2 = str(item.get("recipient_addr2") or "")
    goods = str(item.get("goods_name") or "")
    order_no = str(item.get("order_no") or "")
    tracking = _tracking(item.get("tracking_no"))
    tracking_digits = _digits(item.get("tracking_no"))
    office = str(item.get("post_office") or "")
    applied = _date(item.get("res_date") or item.get("created_at"))
    notes = str(item.get("notes") or "")
    goods_line = f"{goods},, 수량:1, {order_no}♠".strip(" ,")

    doc = fitz.open()
    try:
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page.insert_font(fontname="korea", fontbuffer=fitz.Font("korea").buffer)
        if item.get("status") == "canceled":
            page.insert_text((2, 28), "취소된 접수", fontname="korea", fontsize=8, color=(0.75, 0.05, 0.05))

        _h(page, 2.15, 47.26, f"접수국 : {office}".strip(), 6.96)
        _h(page, 2.15, 62.26, "주문인:", 6.96)
        _h(page, 33.11, 62.26, sender_name, 6.96)
        _h(page, 2.15, 72.22, f"고객 주문처: {sender_name}", 6.96)
        contact = _h(page, 2.15, 82.18, "문의처: ", 6.96)
        _h(page, contact, 82.18, _digits(sender_phone), 6.96, font="hebo")
        order_label = _h(page, 2.15, 91.18, "주문번호: ", 6.96)
        _h(page, order_label, 91.18, order_no, 6.96, font="hebo")
        _h(page, 103.31, 100.18, "요금: 계약요금", 6.96)
        _h(page, 87.71, 118.18, "신청일 :", 6.96)
        _h(page, 117.11, 118.18, applied, 6.96, font="hebo")
        _h(page, 138.71, 142.36, "(1/1)", 8.04, font="hebo")
        _h(page, 37.19, 168.95, rec_zip, 12, font="hebo")
        goods_end = _h(page, 3.11, 187.36, f"{goods},, 수량:1, ", 8.04)
        goods_end = _h(page, goods_end, 187.36, order_no, 8.04, font="hebo")
        _h(page, goods_end, 187.36, "♠", 8.04)
        _h(page, 5.15, 293.26, notes, 6.96)

        _h(page, 185.15, 69.38, sender_addr1, 8.04)
        _h(page, 185.15, 77.42, sender_addr2, 8.04)
        _h(page, 363.23, 73.40, sender_zip, 9.96, font="hebo")
        _h(page, 186.23, 96.65, sender_name, 9)
        _h(page, 341.15, 97.18, _phone_m(sender_phone), 6.96, font="hebo")
        _h(page, 189.11, 118.07, rec_addr1, 7.8)
        _h(page, 189.11, 135.52, rec_addr2, 11)
        _h(page, 186.23, 169.92, rec_name, 11)
        _h(page, 187.19, 187.61, _phone_t(rec_phone), 9, font="hebo")
        _h(page, 187.07, 195.07, "※ 고객님의 개인정보 보호를 위하여 임시 가상번호를 사용합니다.", 6)
        _h(page, 185.27, 210.32, "등기번호:", 9.96)
        _h(page, 231.23, 210.45, tracking, 14.04, font="hebo")

        _v(page, 428.03, 294.84, f"{rec_addr1} {rec_addr2}".strip(), 6.96)
        _v(page, 438.95, 294.12, rec_name, 6.96)
        _v(page, 438.95, 238.20, _digits(rec_phone), 6.96, font="hebo")
        _v(page, 443.02, 116.04, tracking, 7.93, font="hebo")
        _v(page, 450.95, 265.20, f"{goods},, 수량:1,", 6.96)
        _v(page, 452.03, 294.12, "내용품 :", 6.96)

        if rec_zip:
            page.insert_image(_ZIP_BAR, pixmap=_barcode_pixmap(rec_zip), keep_proportion=False)
        if tracking_digits:
            page.insert_image(_TRACK_BAR, pixmap=_barcode_pixmap(tracking_digits), keep_proportion=False)
            page.insert_image(_SIDE_BAR, pixmap=_barcode_pixmap(tracking_digits), keep_proportion=False, rotate=90)
        return doc.tobytes()
    finally:
        doc.close()
