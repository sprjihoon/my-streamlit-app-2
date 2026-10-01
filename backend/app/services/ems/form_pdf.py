"""우체국 A4 양식 PDF에 접수 데이터만 덮어 쓴다.

로고, 표, 안내 문구는 템플릿 그대로 둔다.
샘플로 박혀 있던 값만 지우고 같은 칸에 접수 값을 넣는다.
EMS, EMS 프리미엄, K-Packet은 우체국 출력 파일이 서로 다르다.
"""

from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path
from typing import Any

import fitz
from reportlab.graphics.barcode import code128
from reportlab.pdfgen.canvas import Canvas

from backend.app.services.ems.fields import format_recipient_tel

TEMPLATE = Path(__file__).with_name("ems_nml_a4_v1p.pdf")
PREMIUM_TEMPLATE = Path(__file__).with_name("ems_nml_a4_v1p_p.pdf")
KPACKET_TEMPLATE = Path(__file__).with_name("kpacket_a4_v2p.pdf")

# 좌표는 각 답안지에서 잰 값이다. EMS는 EG053055332KR, 프리미엄은 UP901002522KR.
_EMS_LAYOUT = {
    "tracking": (123.72, 82.08),
    "weight": (423.24, 320.76),
    "volume": (423.24, 337.8),
    "zip": (382.56, 303.84),
    "dims": (501.84, 340.08),
    "country_baseline": 355.44,
    "office": (491.76, 398.88),
    "signature": (293.28, 429.12),
    "fee_right": 544.0,
    "recipient_width": 230,
    "recipient_next_x": None,
    "premium_weights": False,
    "national_phone": False,
}
_PREMIUM_LAYOUT = {
    "tracking": (124.08, 82.08),
    "weight": (420.36, 320.76),
    "volume": (420.36, 337.80),
    "zip": (373.56, 303.84),
    "dims": (500.16, 340.08),
    "country_baseline": 357.84,
    "office": (491.76, 393.72),
    "signature": (297.12, 429.12),
    "fee_right": 547.39,
    "recipient_width": 180,
    "recipient_next_x": 311.28,
    "premium_weights": True,
    "national_phone": True,
}

# 정답 PDF(EG053055332KR)에서 잰 값. 덮는 칸은 표 선과 고정 글귀를 피한다.
_BARCODE = (119.0, 93.0, 270.0, 130.0)
_COVERS = (
    (120.0, 63.5, 280.0, 88.0),  # 등기번호
    (310.0, 124.0, 340.0, 136.0),  # 연
    (346.0, 124.0, 370.0, 136.0),  # 월
    (376.0, 124.0, 398.0, 136.0),  # 일
    (404.0, 124.0, 436.0, 136.0),  # 시분
    (486.0, 123.5, 545.0, 136.5),  # 우편용국기호
    (89.0, 141.0, 275.0, 153.6),  # 보내는 전화
    (344.0, 140.4, 550.0, 153.6),  # 받는 전화
    (92.0, 159.2, 275.0, 174.6),  # 보내는 이름
    (348.0, 158.8, 552.0, 174.6),  # 받는 이름
    (56.0, 186.4, 278.0, 248.0),  # 보내는 주소
    (314.0, 191.0, 555.0, 250.0),  # 받는 주소
    (348.0, 278.2, 552.0, 290.8),  # 이메일
    (116.0, 294.0, 192.0, 307.6),  # 보내는 우편번호
    (374.0, 292.4, 424.0, 307.2),  # 받는 우편번호
    (464.0, 291.4, 555.0, 307.2),  # 국가명
    (414.0, 309.2, 468.0, 323.2),  # 실제중량
    (414.0, 326.4, 468.0, 340.2),  # 부피중량
    (508.0, 310.2, 544.5, 322.4),  # 요금 숫자. '원'은 남긴다
    (498.0, 333.3, 550.0, 342.2),  # 가로*세로*높이 값
    (519.0, 342.2, 541.0, 358.5),  # 국가코드 1
    (545.0, 342.2, 566.0, 358.5),  # 국가코드 2
    (250.0, 420.4, 360.0, 431.8),  # 발송인 서명
    (478.0, 388.5, 560.0, 402.0),  # 접수국 서명
    (28.4, 342.8, 166.4, 355.0),
    (168.2, 342.8, 196.6, 355.0),
    (198.2, 342.8, 238.2, 355.0),
    (240.0, 342.8, 279.8, 355.0),
    (281.4, 342.8, 321.6, 355.0),
    (323.2, 342.8, 363.4, 355.0),
    (28.4, 356.8, 166.4, 369.2),
    (168.2, 356.8, 196.6, 369.2),
    (198.2, 356.8, 238.2, 369.2),
    (240.0, 356.8, 279.8, 369.2),
    (281.4, 356.8, 321.6, 369.2),
    (323.2, 356.8, 363.4, 369.2),
    (28.4, 371.2, 166.4, 384.4),
    (168.2, 371.2, 196.6, 384.4),
    (198.2, 371.2, 238.2, 384.4),
    (240.0, 371.2, 279.8, 384.4),
    (281.4, 371.2, 321.6, 384.4),
    (323.2, 371.2, 363.4, 384.4),
)
_MERCHANDISE_MARK = (132.8, 400.2, 140.2, 409.2)
_ITEM_BASELINE = 351.24
_ITEM_PITCH = 14.4
_RULE = 0.75
_RULE_SNAP = 2.6

_CJK_BUFFER: bytes | None = None
_CJK_PAGES: set[int] = set()


def render_label_pdf(data: dict[str, Any]) -> bytes:
    method = str(data.get("shipping_method") or "EMS")
    if method == "KPACKET":
        return _render(KPACKET_TEMPLATE, data, _fill_kpacket)
    if method == "EMS_PREMIUM":
        return _render(PREMIUM_TEMPLATE, data, lambda page, shipment, barcode: _fill_page(page, shipment, barcode, _PREMIUM_LAYOUT))
    return _render(TEMPLATE, data, _fill_page)


def _render(template: Path, data: dict[str, Any], fill) -> bytes:
    if not template.is_file():
        raise FileNotFoundError(f"우체국 양식 PDF가 없습니다: {template}")
    _CJK_PAGES.clear()
    doc = fitz.open(template)
    try:
        barcode = _barcode_pixmap(str(data.get("regino") or ""))
        for page in doc:
            fill(page, data, barcode)
        return doc.tobytes(deflate=True, garbage=4)
    finally:
        doc.close()


def _table_rules(page: fitz.Page) -> tuple[list, list]:
    """검은 표 선만 모은다. 바코드 막대처럼 가는 선은 빼 둔다."""
    horizontal: list[tuple[float, float, float, fitz.Rect]] = []
    vertical: list[tuple[float, float, float, fitz.Rect]] = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        fill = drawing.get("fill")
        # 흰 칸은 빼고, 검은 선과 회색 선은 같은 굵기로 다시 그린다.
        if not fill or fill[0] > 0.92:
            continue
        width, height = rect.width, rect.height
        if width > 6 and 0.4 < height < 1.8:
            horizontal.append((rect.y0 + height / 2, rect.x0, rect.x1, rect))
        elif height > 6 and 0.4 < width < 1.8:
            vertical.append((rect.x0 + width / 2, rect.y0, rect.y1, rect))
    return _snap_rules(horizontal), _snap_rules(vertical)


def _snap_rules(items: list[tuple[float, float, float, fitz.Rect]]) -> list[tuple[float, list, list]]:
    """겹치는 두 줄만 한 줄로 합친다. 좌우로 떨어진 선은 그대로 둔다."""
    pending = sorted(items, key=lambda row: (row[0], row[1]))
    used = [False] * len(pending)
    snapped = []
    for index, item in enumerate(pending):
        if used[index]:
            continue
        group = [item]
        used[index] = True
        grew = True
        while grew:
            grew = False
            for other_index, other in enumerate(pending):
                if used[other_index]:
                    continue
                if any(
                    abs(other[0] - row[0]) <= _RULE_SNAP and other[1] <= row[2] + 1.2 and row[1] <= other[2] + 1.2
                    for row in group
                ):
                    group.append(other)
                    used[other_index] = True
                    grew = True
        center = sum(row[0] for row in group) / len(group)
        spans = _merge_spans((row[1], row[2]) for row in group)
        snapped.append((center, spans, [row[3] for row in group]))
    return snapped


def _merge_spans(spans) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + 1.2:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _paint_uniform_rules(page: fitz.Page, rules: tuple[list, list]) -> None:
    horizontal, vertical = rules
    pad = 0.45
    for _center, _spans, rects in horizontal:
        for rect in rects:
            page.draw_rect(
                fitz.Rect(rect.x0, rect.y0 - pad, rect.x1, rect.y1 + pad),
                color=(1, 1, 1),
                fill=(1, 1, 1),
                width=0,
            )
    for _center, _spans, rects in vertical:
        for rect in rects:
            page.draw_rect(
                fitz.Rect(rect.x0 - pad, rect.y0, rect.x1 + pad, rect.y1),
                color=(1, 1, 1),
                fill=(1, 1, 1),
                width=0,
            )
    half = _RULE / 2
    for center, spans, _rects in horizontal:
        for start, end in spans:
            page.draw_rect(
                fitz.Rect(start, center - half, end, center + half),
                color=(0, 0, 0),
                fill=(0, 0, 0),
                width=0,
            )
    for center, spans, _rects in vertical:
        for start, end in spans:
            page.draw_rect(
                fitz.Rect(center - half, start, center + half, end),
                color=(0, 0, 0),
                fill=(0, 0, 0),
                width=0,
            )


def _fill_page(page: fitz.Page, data: dict[str, Any], barcode: fitz.Pixmap, layout: dict[str, Any] | None = None) -> None:
    layout = layout or _EMS_LAYOUT
    sender = data.get("sender") or {}
    recipient = dict(data.get("recipient") or {})
    if layout.get("national_phone"):
        shown = format_recipient_tel(str(recipient.get("phone") or ""), str(recipient.get("country") or ""))
        if shown:
            recipient["phone"] = shown
    items, actual_g, volume_g = _weights_for_layout(data, layout)
    is_doc = data.get("contents_type") == "document"
    rules = _table_rules(page)
    for box in _COVERS:
        page.add_redact_annot(fitz.Rect(*box), fill=(1, 1, 1))
    if is_doc:
        page.add_redact_annot(fitz.Rect(*_MERCHANDISE_MARK), fill=(1, 1, 1))
    # 글자만 지운다. 로고 이미지와 표 선은 템플릿에 남긴다.
    page.apply_redactions(images=0, graphics=0, text=0)
    page.draw_rect(fitz.Rect(*_BARCODE), color=(1, 1, 1), fill=(1, 1, 1), width=0)
    if barcode.width:
        page.insert_image(fitz.Rect(*_BARCODE), pixmap=barcode, keep_proportion=True)
    _paint_uniform_rules(page, rules)

    _at(page, layout["tracking"], data.get("regino"), 17.99, "hebi")
    _center(page, 308.6, 341.0, 132.84, data.get("posted_year"), 6.96)
    _center(page, 341.0, 373.4, 132.84, _two(data.get("posted_month")), 6.96)
    _center(page, 373.4, 400.4, 132.84, _two(data.get("posted_day")), 6.96)
    clock = ""
    if data.get("posted_hour") and data.get("posted_min"):
        clock = f"{_two(data.get('posted_hour'))}:{_two(data.get('posted_min'))}"
    _center(page, 400.4, 438.2, 132.84, clock, 6.96)
    _at(page, (492.0, 133.32), data.get("post_office_code"), 8.04)
    _at(page, (88.75, 151.32), _phone(sender.get("tel")), 9.96, "hebi")
    _at(page, (343.27, 149.88), _phone(recipient.get("phone")), 9.96, "hebi")
    _at(page, (93.0, 170.64), sender.get("name"), 9.96, "hebi")
    _at(page, (350.88, 170.28), recipient.get("name"), 9.96, "hebi")
    _lines(page, 61.68, 197.52, sender.get("address"), 9.96, 210, 12.96, "hebi", next_x=56.76)
    _lines(
        page, 316.2, 202.92, _recipient_address(recipient), 9.96,
        layout["recipient_width"], 12.96, "hebi", next_x=layout["recipient_next_x"],
    )
    _at(page, (350.88, 287.76), recipient.get("email"), 8.04, "hebi")
    _at(page, (119.4, 305.28), _spaced_digits(sender.get("zip")), 9.96, "hebi")
    _at(page, layout["zip"], recipient.get("zip"), 9.96, "hebi")
    country = str(recipient.get("country_name") or "").strip().upper()
    _at(page, (459.18, 302.76), f" {country}" if country else "", 9.96, "hebi")
    _at(page, layout["weight"], _grams(actual_g), 9.96, "hebi")
    _at(page, layout["volume"], _grams(volume_g), 9.96, "hebi")
    fee = data.get("ems_fee")
    if fee is not None:
        _right(page, layout["fee_right"], 319.68, f"{int(fee):,} ", 8.04)
    _at(page, layout["dims"], _dims(data), 6.0)
    code = str(recipient.get("country") or "").upper()
    baseline = layout["country_baseline"]
    _center(page, 517.3, 542.8, baseline, code[:1], 12.96, "hebi")
    _center(page, 542.8, 567.7, baseline, code[1:2], 12.96, "hebi")
    _at(page, layout["signature"], sender.get("name"), 6.96)
    _at(page, layout["office"], data.get("post_office"), 8.04)

    for index, item in enumerate(items):
        baseline = _ITEM_BASELINE + index * _ITEM_PITCH
        price = ""
        if item.get("unit_price_usd") not in (None, ""):
            price = _money(float(item.get("unit_price_usd") or 0) * int(item.get("quantity") or 1))
        _at(page, (29.4, baseline), item.get("name_en"), 6.96)
        _center(page, 167.5, 197.4, baseline, item.get("quantity"), 6.96)
        _center(page, 197.4, 239.0, baseline, item.get("net_weight_g"), 6.96)
        _center(page, 239.0, 280.8, baseline, price, 6.96)
        _at(page, (284.28, baseline), item.get("print_hs") or item.get("hs_code"), 6.0)
        _center(page, 322.4, 364.2, baseline, item.get("origin_country"), 6.96)
    if data.get("status") == "canceled":
        _at(page, (40.0, 22.0), "취소된 접수", 11, color=(0.75, 0.05, 0.05))


def _font_for(page: fitz.Page, text: str, font: str) -> str:
    if any(ord(ch) > 127 for ch in text):
        _ensure_cjk(page)
        return "ems"
    return font


def _at(
    page: fitz.Page,
    point: tuple[float, float],
    value: Any,
    size: float,
    font: str = "helv",
    color: tuple[float, float, float] = (0, 0, 0),
) -> None:
    text = str(value if value is not None else "")
    if not text.strip():
        return
    page.insert_text(point, text, fontsize=size, fontname=_font_for(page, text, font), color=color)


def _center(
    page: fitz.Page,
    x0: float,
    x1: float,
    baseline: float,
    value: Any,
    size: float,
    font: str = "helv",
) -> None:
    text = str(value or "").strip()
    if not text:
        return
    fontname = _font_for(page, text, font)
    width = fitz.get_text_length(text, fontname=fontname, fontsize=size)
    page.insert_text(((x0 + x1 - width) / 2, baseline), text, fontsize=size, fontname=fontname, color=(0, 0, 0))


def _right(page: fitz.Page, x1: float, baseline: float, value: Any, size: float, font: str = "helv") -> None:
    text = str(value or "")
    if not text.strip():
        return
    fontname = _font_for(page, text, font)
    width = fitz.get_text_length(text, fontname=fontname, fontsize=size)
    page.insert_text((x1 - width, baseline), text, fontsize=size, fontname=fontname, color=(0, 0, 0))


def _lines(
    page: fitz.Page,
    x: float,
    baseline: float,
    value: Any,
    size: float,
    width: float,
    leading: float,
    font: str,
    next_x: float | None = None,
) -> None:
    text = " ".join(str(value or "").split())
    if not text:
        return
    fontname = _font_for(page, text, font)
    words = text.split(" ")
    rows: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if fitz.get_text_length(trial, fontname=fontname, fontsize=size) <= width or not current:
            current = trial
        else:
            rows.append(current)
            current = word
    if current:
        rows.append(current)
    hang = x if next_x is None else next_x
    for index, row in enumerate(rows[:4]):
        page.insert_text((x if index == 0 else hang, baseline + index * leading), row, fontsize=size, fontname=fontname, color=(0, 0, 0))


def _ensure_cjk(page: fitz.Page) -> None:
    global _CJK_BUFFER
    key = page.number
    if key in _CJK_PAGES:
        return
    if _CJK_BUFFER is None:
        _CJK_BUFFER = fitz.Font("korea").buffer
    page.insert_font(fontname="ems", fontbuffer=_CJK_BUFFER)
    _CJK_PAGES.add(key)


def _barcode_pixmap(value: str) -> fitz.Pixmap:
    code = "".join(ch for ch in (value or "NO-TRACKING") if 32 <= ord(ch) < 127) or "NO-TRACKING"
    bar = code128.Code128(code, barHeight=32, barWidth=0.62, humanReadable=False)
    packet = BytesIO()
    canvas = Canvas(packet, pagesize=(bar.width + 6, bar.height + 8))
    bar.drawOn(canvas, 3, 4)
    canvas.save()
    src = fitz.open(stream=packet.getvalue(), filetype="pdf")
    try:
        return src[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    finally:
        src.close()


def _recipient_address(recipient: dict[str, Any]) -> str:
    parts = [recipient.get("addr3"), recipient.get("addr2"), recipient.get("addr1")]
    return "\n".join(str(part).strip() for part in parts if str(part or "").strip())


def _phone(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "-" in text:
        parts = [part.strip().lstrip("+") for part in text.split("-") if part.strip()]
        body = "- ".join(parts)
    else:
        digits = "".join(ch for ch in text if ch.isdigit())
        rest = digits[2:] if digits.startswith("82") and len(digits) > 6 else ""
        if rest and len(rest) > 4:
            body = f"82- {rest[:2]}- {rest[2:-4]}- {rest[-4:]}"
        else:
            body = text.lstrip("+")
    return f" {body}"


def _spaced_digits(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return " ".join(digits)


def _grams(value: Any) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    if number <= 0:
        return ""
    return f"{number} g"


def _dims(data: dict[str, Any]) -> str:
    if data.get("contents_type") == "document":
        return ""
    length = int(data.get("boxlength") or 0)
    width = int(data.get("boxwidth") or 0)
    height = int(data.get("boxheight") or 0)
    if not (length and width and height):
        return ""
    return f"{length} * {width} * {height}"


def _two(value: Any) -> str:
    text = str(value or "").strip()
    if text.isdigit() and len(text) == 1:
        return text.zfill(2)
    return text


def _money(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"


def _weights_for_layout(data: dict[str, Any], layout: dict[str, Any]):
    items = [dict(item) for item in list(data.get("items") or []) if item.get("name_en")][:3]
    actual = data.get("totweight")
    volume = data.get("volume_weight")
    if not layout.get("premium_weights") or data.get("contents_type") == "document":
        return items, actual, volume
    shown_actual, shown_volume = _premium_shown_weights(data)
    raw = str(int(data.get("totweight") or 0))
    if len(items) == 1:
        net = str(items[0].get("net_weight_g") or "").strip()
        if not net or net == raw:
            items[0]["net_weight_g"] = str(shown_actual)
    return items, shown_actual, shown_volume


def _premium_shown_weights(data: dict[str, Any]) -> tuple[int, int]:
    """프리미엄 답안지는 실중량 칸에 운임중량, 부피중량 칸에 cm³/6000을 넣는다."""
    length = int(data.get("boxlength") or 0)
    width = int(data.get("boxwidth") or 0)
    height = int(data.get("boxheight") or 0)
    raw = int(data.get("totweight") or 0)
    try:
        premium_volume = int(data.get("volume_weight") or 0)
    except (TypeError, ValueError):
        premium_volume = 0
    if length and width and height and premium_volume <= 0:
        premium_volume = math.ceil((length * width * height) / 5)
    shown_volume = int((length * width * height) / 6) if length and width and height else premium_volume
    return max(raw, premium_volume), shown_volume


_KPACKET_BARCODE = (98.16, 149.04, 274.08, 172.68)
_KPACKET_COVERS = (
    (68.4, 337.7, 210.0, 347.4),
    (126.5, 347.5, 211.5, 360.2),
    (211.8, 347.5, 246.0, 360.2),
    (246.8, 347.5, 272.95, 360.2),
    (176.4, 361.0, 246.0, 374.2),
    (246.8, 361.0, 308.0, 374.2),
    (100.5, 368.15, 170.0, 376.9),
    (140.0, 173.6, 270.0, 185.5),
    (316.0, 196.4, 391.8, 214.8),
    (393.2, 196.4, 409.8, 214.8),
    (411.0, 196.4, 428.8, 214.8),
    (429.8, 196.4, 459.8, 214.8),
    (461.0, 196.4, 494.5, 214.8),
    (495.6, 196.4, 515.0, 214.8),
    (405.0, 296.0, 430.0, 307.5),
    (430.5, 296.0, 460.0, 308.2),
    (426.0, 364.2, 520.0, 373.5),
    (104.5, 193.2, 270.0, 205.2),
    (69.2, 204.0, 280.0, 225.5),
    (80.0, 250.3, 142.0, 262.2),
    (96.0, 264.5, 190.0, 276.4),
    (205.0, 264.5, 280.0, 276.4),
    (69.2, 279.2, 280.0, 292.4),
    (69.2, 293.3, 308.0, 316.6),
    (70.0, 326.6, 250.0, 338.6),
)
_KPACKET_PITCH = 19.8


def _fill_kpacket(page: fitz.Page, data: dict[str, Any], barcode: fitz.Pixmap) -> None:
    sender = data.get("sender") or {}
    recipient = data.get("recipient") or {}
    items = [item for item in list(data.get("items") or []) if item.get("name_en")][:5]
    rules = _table_rules(page)
    for box in _KPACKET_COVERS:
        page.add_redact_annot(fitz.Rect(*box), fill=(1, 1, 1))
    page.apply_redactions(images=0, graphics=0, text=0)
    page.draw_rect(fitz.Rect(*_KPACKET_BARCODE), color=(1, 1, 1), fill=(1, 1, 1), width=0)
    if barcode.width:
        page.insert_image(fitz.Rect(*_KPACKET_BARCODE), pixmap=barcode, keep_proportion=True)
    _paint_uniform_rules(page, rules)

    order_no = str(data.get("order_no") or "").strip()
    if order_no:
        _at(page, (68.64, 345.36), f"OrderNo. {order_no}", 6.96, "hebi")
    posted = _kpacket_date(data)
    if posted:
        _at(page, (127.44, 357.12), posted, 9.0, "hebi")
    weight = int(data.get("totweight") or 0)
    if weight > 0:
        _at(page, (212.52, 357.12), f"{weight}g", 9.0, "hebi")
    fee = data.get("ems_fee")
    if fee is not None and str(fee).strip() != "":
        _at(page, (247.08, 357.12), str(int(fee)), 9.0, "hebi")
    volume = _kpacket_volume_g(data)
    if volume > 0:
        _at(page, (176.76, 370.92), f"volume {volume}g", 9.0, "hebi")
    _at(page, (247.08, 370.92), "Country :    ", 9.0, "hebi")
    _at(page, (287.28, 370.92), str(recipient.get("country") or "").upper(), 9.0, "hebi")
    _at(page, (100.92, 374.28), _dims(data), 6.96, "hebi")
    _at(page, (158.28, 182.40), data.get("regino"), 8.04, "hebi")

    total_value = 0.0
    for index, item in enumerate(items):
        shift = index * _KPACKET_PITCH
        qty = int(item.get("quantity") or 1)
        unit = float(item.get("unit_price_usd") or 0)
        total_value += unit * qty
        _at(page, (316.20, 208.56 + shift), item.get("name_en"), 8.04, "hebi")
        _at(page, (399.84, 208.56 + shift), qty, 8.04, "hebi")
        _at(page, (413.88, 208.08 + shift), item.get("net_weight_g"), 6.0, "hebi")
        _at(page, (441.12, 208.56 + shift), _money(unit * qty), 8.04, "hebi")
        _at(page, (464.04, 207.60 + shift), item.get("print_hs") or item.get("hs_code"), 5.04, "hebi")
        _at(page, (500.40, 208.56 + shift), item.get("origin_country"), 8.04, "hebi")
    if weight > 0:
        _at(page, (413.64, 304.68), weight, 6.0, "hebi")
    if items:
        _at(page, (440.88, 305.16), _money(total_value), 8.04, "hebi")
    _at(page, (432.36, 371.04), sender.get("name"), 6.0)

    _at(page, (105.60, 202.08), _kpacket_sender_tel(sender.get("tel")), 8.04, "hebi")
    _at(page, (69.60, 212.04), sender.get("name"), 8.04, "hebi")
    _at(page, (69.60, 221.76), sender.get("address"), 8.04, "hebi")
    _at(page, (86.76, 259.32), _spaced_digits(sender.get("zip")), 8.04, "hebi")
    _at(page, (97.20, 273.48), _kpacket_recipient_tel(recipient.get("phone"), recipient.get("country")), 8.04, "hebi")
    zipcode = str(recipient.get("zip") or "").strip()
    if zipcode:
        _at(page, (210.96, 273.48), f"ZIP: {zipcode}", 8.04, "hebi")
    _at(page, (69.60, 289.32), recipient.get("name"), 9.0, "hebi")
    street = " ".join(
        part for part in (str(recipient.get("addr3") or "").strip(), str(recipient.get("addr2") or "").strip()) if part
    )
    _at(page, (69.60, 303.24), street, 9.0, "hebi")
    _at(page, (69.60, 313.32), recipient.get("addr1"), 9.0, "hebi")
    country_name = str(recipient.get("country_name") or "").strip().upper()
    _at(page, (74.64, 335.64), country_name, 8.04, "hebi")
    if data.get("status") == "canceled":
        _at(page, (40.0, 22.0), "취소된 접수", 11, color=(0.75, 0.05, 0.05))


def _kpacket_date(data: dict[str, Any]) -> str:
    year = str(data.get("posted_year") or "").strip()
    month = str(data.get("posted_month") or "").strip()
    day = str(data.get("posted_day") or "").strip()
    if not (year and month and day):
        return ""
    return f"{year}.{_two(month)}.{_two(day)}.actual"


def _kpacket_volume_g(data: dict[str, Any]) -> int:
    length = int(data.get("boxlength") or 0)
    width = int(data.get("boxwidth") or 0)
    height = int(data.get("boxheight") or 0)
    if length and width and height:
        return int((length * width * height) / 6)
    try:
        return int(data.get("volume_weight") or 0)
    except (TypeError, ValueError):
        return 0


def _kpacket_sender_tel(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if digits.startswith("82") and len(digits) > 6:
        rest = digits[2:]
        if len(rest) > 4:
            return f"Tel: 82- {rest[:2]}- {rest[2:-4]}- {rest[-4:]}"
    text = str(value or "").strip()
    return f"Tel: {text}" if text else ""


def _kpacket_recipient_tel(phone: Any, country: Any) -> str:
    shown = format_recipient_tel(str(phone or ""), str(country or ""))
    if not shown:
        return ""
    return "Tel: " + shown.replace("-", "- ")
