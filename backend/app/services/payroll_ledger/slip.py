"""급여대장 한 사람 분으로 급여명세서 A4 PDF를 만든다."""
from __future__ import annotations

import fitz

from backend.app.services.employment_contract.pdf import render_page_pngs

_BLACK = (0, 0, 0)
_LEFT = 36
_RIGHT = 559
_PAY_ITEMS = (
    ("기본급", "base_pay"),
    ("시간외근로수당", "overtime_pay"),
    ("휴일수당", "holiday_pay"),
    ("야간근로수당", "night_pay"),
    ("직책수당", "position_allowance"),
    ("특근수당", "special_pay"),
    ("인센티브", "incentive_pay"),
    ("차량지원금", "vehicle_allowance"),
    ("식대", "meal_allowance"),
    ("정산수당", "settlement_pay"),
    ("연차수당", "annual_leave_pay"),
    ("근태공제", "attendance_deduction"),
    ("상여금", "bonus_pay"),
)
_DED_ITEMS = (
    ("소득세", "income_tax"),
    ("국민연금", "pension"),
    ("연말정산환수", "year_end_tax"),
    ("주민세", "local_tax"),
    ("고용보험", "employment"),
    ("보험료정산", "insurance_adjust"),
    ("건강보험", "health"),
    ("장기요양", "care"),
    ("기지급액", "prepaid"),
)
_BASIS = (
    ("총근로일수", "work_days"),
    ("기본근로시간", "base_hours"),
    ("연장근로시간", "overtime_hours"),
    ("휴일근로시간", "holiday_hours"),
    ("야간근로시간", "night_hours"),
    ("통상시급", "hourly"),
)
_METHODS = (
    "시간외근로수당  연장근무시간×통상시급×1.5",
    "야간근로수당  야간근로시간×통상시급×0.5",
    "휴일근로수당  휴일근로시간×통상시급×1.5",
    "소득세·주민세  간이세액표 적용",
    "국민연금  월평균보수액×4.75%",
    "고용보험  과세대상임금×0.9%",
    "건강보험  과세대상임금×3.595%",
    "장기요양보험  건강보험료×13.14%",
)


def _num(value) -> str:
    return f"{int(value or 0):,}"


def _hours(value) -> str:
    number = float(value or 0)
    shown = str(int(number)) if number.is_integer() else f"{number:g}"
    return f"{shown}시간"


def _mask_rrn(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 7:
        return ""
    return f"{digits[:6]}-{digits[6]}******"


def render_slip_pdf(ledger: dict, line: dict, *, masked_rrn: str | None = None) -> bytes:
    doc = fitz.open()
    _draw_page(doc, ledger, line, masked_rrn)
    return doc.tobytes()


def render_bundle_pdf(ledger: dict, lines: list[dict], mask) -> bytes:
    doc = fitz.open()
    for line in lines:
        _draw_page(doc, ledger, line, mask(str(line.get("resident_id") or "")))
    if doc.page_count == 0:
        doc.new_page(width=595, height=842)
    return doc.tobytes()


def slip_preview_pages(pdf: bytes) -> list[str]:
    import base64

    return [base64.b64encode(image).decode("ascii") for image in render_page_pngs(pdf)]


def _draw_page(doc: fitz.Document, ledger: dict, line: dict, masked_rrn: str | None) -> None:
    page = doc.new_page(width=595, height=842)
    font = fitz.Font("korea")
    page.insert_font(fontname="korea", fontbuffer=font.buffer)
    form = _Sheet(page, font)
    form.draw(ledger, line, masked_rrn or _mask_rrn(str(line.get("resident_id") or "")))


class _Sheet:
    def __init__(self, page, font):
        self.page = page
        self.font = font

    def _width(self, text: str, size: float) -> float:
        return fitz.get_text_length(text, fontname="korea", fontsize=size)

    def _put(self, rect: fitz.Rect, text: str, size: float = 8, align: int = 1) -> None:
        value = str(text or "").strip()
        if not value:
            return
        pad = 2
        inner = max(rect.width - pad * 2, 6)
        use = size
        while use > 5 and self._width(value, use) > inner:
            use -= 0.2
        text_w = self._width(value, use)
        if align == 2:
            x = rect.x1 - pad - text_w
        elif align == 0:
            x = rect.x0 + pad
        else:
            x = rect.x0 + (rect.width - text_w) / 2
        baseline = min(rect.y0 + (rect.height + use * 0.7) / 2, rect.y1 - 1.2)
        self.page.insert_text((x, baseline), value, fontsize=use, fontname="korea", color=_BLACK)

    def _line(self, x0, y0, x1, y1, width=0.6) -> None:
        self.page.draw_line(fitz.Point(x0, y0), fitz.Point(x1, y1), color=_BLACK, width=width)

    def _box(self, x0, y0, x1, y1, width=1.0) -> None:
        self.page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=_BLACK, width=width)

    def draw(self, ledger: dict, line: dict, masked_rrn: str) -> None:
        company = ledger.get("company_name") or "틸리언"
        period = ledger.get("period_label") or ""
        year = ledger.get("year")
        month = ledger.get("month")
        self._put(fitz.Rect(160, 28, 435, 54), "급 여 명 세 서", 16)
        self._put(fitz.Rect(_LEFT, 58, 220, 76), company, 10, 0)
        self._put(fitz.Rect(220, 58, 400, 76), "임금산정기간", 8, 0)
        self._put(fitz.Rect(300, 58, 500, 76), period, 9, 0)
        self._put(fitz.Rect(430, 58, _RIGHT, 76), "지급일  매달 15일", 8, 2)
        y = 82
        self._box(_LEFT, y, _RIGHT, y + 44, 1.1)
        self._line(110, y, 110, y + 44)
        self._line(250, y, 250, y + 44)
        self._line(320, y, 320, y + 44)
        self._line(430, y, 430, y + 44)
        self._line(_LEFT, y + 22, _RIGHT, y + 22)
        self._put(fitz.Rect(_LEFT, y, 110, y + 22), "성명", 8)
        self._put(fitz.Rect(110, y, 250, y + 22), line.get("employee_name") or "", 9)
        self._put(fitz.Rect(250, y, 320, y + 22), "주민번호", 8)
        self._put(fitz.Rect(320, y, 430, y + 22), masked_rrn, 8)
        self._put(fitz.Rect(430, y, _RIGHT, y + 22), "직무", 8)
        self._put(fitz.Rect(_LEFT, y + 22, 110, y + 44), "소속", 8)
        self._put(fitz.Rect(110, y + 22, 250, y + 44), line.get("affiliation") or "", 8)
        self._put(fitz.Rect(250, y + 22, 320, y + 44), "통상시급", 8)
        self._put(fitz.Rect(320, y + 22, 430, y + 44), _num(line.get("hourly")), 8, 2)
        self._put(fitz.Rect(430, y + 22, _RIGHT, y + 44), f"{year}년 {int(month):02d}월", 8)

        top = 138
        rows = max(len(_PAY_ITEMS), len(_DED_ITEMS), len(_BASIS) + 2)
        row_h = 18
        table_h = 22 + rows * row_h + 22
        pay_x = 168
        ded_x = 300
        basis_x = 392
        bottom = top + table_h
        self._box(_LEFT, top, _RIGHT, bottom, 1.1)
        self._line(pay_x, top, pay_x, bottom)
        self._line(ded_x - 90, top, ded_x - 90, bottom)
        self._line(ded_x, top, ded_x, bottom)
        self._line(basis_x, top, basis_x, bottom)
        self._line(_LEFT, top + 22, _RIGHT, top + 22)
        self._put(fitz.Rect(_LEFT, top, pay_x, top + 22), "지급액", 8)
        self._put(fitz.Rect(pay_x, top, ded_x - 90, top + 22), "금액", 8)
        self._put(fitz.Rect(ded_x - 90, top, ded_x, top + 22), "공제액", 8)
        self._put(fitz.Rect(ded_x, top, basis_x, top + 22), "금액", 8)
        self._put(fitz.Rect(basis_x, top, _RIGHT, top + 22), "산출근거", 8)

        for index in range(rows):
            y0 = top + 22 + index * row_h
            self._line(_LEFT, y0 + row_h, basis_x, y0 + row_h, 0.35)
            if index < len(_PAY_ITEMS):
                label, key = _PAY_ITEMS[index]
                self._put(fitz.Rect(_LEFT, y0, pay_x, y0 + row_h), label, 7.4, 0)
                self._put(fitz.Rect(pay_x, y0, ded_x - 90, y0 + row_h), _num(line.get(key)), 7.6, 2)
            if index < len(_DED_ITEMS):
                label, key = _DED_ITEMS[index]
                self._put(fitz.Rect(ded_x - 90, y0, ded_x, y0 + row_h), label, 7.4, 0)
                self._put(fitz.Rect(ded_x, y0, basis_x, y0 + row_h), _num(line.get(key)), 7.6, 2)
            if index == 0:
                self._put(fitz.Rect(basis_x, y0, _RIGHT, y0 + row_h), "기초자료", 7.4)
            elif index <= len(_BASIS):
                label, key = _BASIS[index - 1]
                raw = line.get(key)
                shown = str(raw or "") if key == "work_days" else (_num(raw) if key == "hourly" else _hours(raw))
                self._put(fitz.Rect(basis_x, y0, 490, y0 + row_h), label, 6.8, 0)
                self._put(fitz.Rect(490, y0, _RIGHT, y0 + row_h), shown, 6.8, 2)
            elif index == len(_BASIS) + 1:
                self._put(fitz.Rect(basis_x, y0, _RIGHT, y0 + row_h), "계산방법", 7.4)

        method_top = top + 22 + (len(_BASIS) + 2) * row_h
        for offset, text in enumerate(_METHODS):
            y0 = method_top + offset * 12
            if y0 + 12 > bottom - 24:
                break
            self._put(fitz.Rect(basis_x + 2, y0, _RIGHT - 2, y0 + 12), text, 6.2, 0)

        total_y = bottom - 22
        self._line(_LEFT, total_y, _RIGHT, total_y, 0.9)
        self._put(fitz.Rect(_LEFT, total_y, pay_x, bottom), "지급 합계", 8)
        self._put(fitz.Rect(pay_x, total_y, ded_x - 90, bottom), _num(line.get("gross_pay")), 9, 2)
        self._put(fitz.Rect(ded_x - 90, total_y, ded_x, bottom), "공제계", 8)
        self._put(fitz.Rect(ded_x, total_y, basis_x, bottom), _num(line.get("deduction_total")), 9, 2)
        self._put(fitz.Rect(basis_x, total_y, 490, bottom), "차인지급액", 8)
        self._put(fitz.Rect(490, total_y, _RIGHT, bottom), _num(line.get("net_pay")), 10, 2)

        thanks = bottom + 18
        self._put(fitz.Rect(_LEFT, thanks, _RIGHT, thanks + 22), "귀하의 노고에 감사드립니다.", 10)
        self._put(fitz.Rect(_LEFT, thanks + 28, _RIGHT, thanks + 48), company, 10, 2)
        self._put(
            fitz.Rect(_LEFT, 800, _RIGHT, 820),
            "이 명세서는 그달 급여대장 자료로 작성되었습니다.",
            7,
        )
