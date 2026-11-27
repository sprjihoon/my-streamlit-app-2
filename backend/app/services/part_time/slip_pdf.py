"""알바 한 사람 분의 급여명세서 A4 PDF. 관리자가 출력해서 건넨다."""
from __future__ import annotations

import fitz

_LEFT = 36
_RIGHT = 559
_BLACK = (0, 0, 0)


def render_part_time_slips_pdf(company: str, year: int, month: int, slips: list[dict]) -> bytes:
    doc = fitz.open()
    for slip in slips:
        _draw_slip(doc, company or "틸리언", int(year), int(month), slip)
    if doc.page_count == 0:
        page = doc.new_page(width=595, height=842)
        _font(page)
        page.insert_text((36, 80), "이 달 급여명세서가 없습니다.", fontsize=12, fontname="korea", color=_BLACK)
    return doc.tobytes()


def _font(page) -> None:
    font = fitz.Font("korea")
    page.insert_font(fontname="korea", fontbuffer=font.buffer)


def _won(value) -> str:
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


def _deductions(slip: dict) -> list[tuple[str, int]]:
    freelance = slip.get("withholding_kind") == "business_3_3" or slip.get("pay_regime") == "business"
    if freelance:
        rows = [("소득세 3%", slip.get("income_tax")), ("지방소득세 0.3%", slip.get("local_tax"))]
    else:
        rows = [
            ("소득세", slip.get("income_tax")),
            ("지방소득세", slip.get("local_tax")),
            ("고용보험", slip.get("employment_insurance")),
            ("국민연금", slip.get("pension")),
            ("건강보험", slip.get("health")),
            ("장기요양보험", slip.get("care")),
        ]
    rows.append(("공제합계", slip.get("deduction_total")))
    return [(label, int(amount or 0)) for label, amount in rows]


class _Pen:
    def __init__(self, doc: fitz.Document, title: str):
        self.doc = doc
        self.title = title
        self.page = doc.new_page(width=595, height=842)
        _font(self.page)
        self.y = 36

    def _gap(self, height: float) -> None:
        if self.y + height <= 800:
            return
        self.page = self.doc.new_page(width=595, height=842)
        _font(self.page)
        self.y = 36
        self.text(self.title, 11)
        self.y += 8

    def text(self, value: str, size: float = 10, x: float = _LEFT, width: float = _RIGHT - _LEFT, align: int = 0) -> None:
        shown = str(value or "")
        if not shown:
            return
        text_w = fitz.get_text_length(shown, fontname="korea", fontsize=size)
        if align == 2:
            origin_x = x + width - text_w
        elif align == 1:
            origin_x = x + (width - text_w) / 2
        else:
            origin_x = x
        self.page.insert_text((origin_x, self.y + size), shown, fontsize=size, fontname="korea", color=_BLACK)

    def rule(self) -> None:
        self.page.draw_line(fitz.Point(_LEFT, self.y), fitz.Point(_RIGHT, self.y), color=_BLACK, width=0.6)

    def row(self, left: str, right: str, *, bold: bool = False) -> None:
        self._gap(18)
        size = 10 if bold else 9
        self.page.draw_rect(fitz.Rect(_LEFT, self.y, _RIGHT, self.y + 18), color=_BLACK, width=0.4)
        self.page.insert_text((_LEFT + 6, self.y + 13), left, fontsize=size, fontname="korea", color=_BLACK)
        right_w = fitz.get_text_length(right, fontname="korea", fontsize=size)
        self.page.insert_text((_RIGHT - 8 - right_w, self.y + 13), right, fontsize=size, fontname="korea", color=_BLACK)
        self.y += 18

    def work_row(self, cells: list[str], header: bool = False) -> None:
        self._gap(16)
        widths = (110, 180, 70, _RIGHT - _LEFT - 360)
        x = _LEFT
        self.page.draw_rect(fitz.Rect(_LEFT, self.y, _RIGHT, self.y + 16), color=_BLACK, width=0.35)
        for cell, width in zip(cells, widths):
            shown = str(cell or "")
            text_w = fitz.get_text_length(shown, fontname="korea", fontsize=8)
            origin_x = x + width - 4 - text_w if shown.endswith(("원", "시간")) else x + 4
            self.page.insert_text((origin_x, self.y + 12), shown, fontsize=8, fontname="korea", color=_BLACK)
            x += width
        self.y += 16


def _draw_slip(doc: fitz.Document, company: str, year: int, month: int, slip: dict) -> None:
    name = slip.get("name") or ""
    pen = _Pen(doc, f"{name} 급여명세서 계속")
    pen.text("급여명세서", 18, align=1)
    pen.y = 64
    pen.text(company, 11)
    pen.y = 64
    pen.text(f"{year}년 {month:02d}월", 11, align=2)
    pen.y = 86
    pen.rule()
    pen.y += 8
    masked = _mask_rrn(slip.get("resident_id") or "")
    who = f"성명  {name}"
    if masked:
        who += f"    주민번호  {masked}"
    who += f"    시급  {_won(slip.get('hourly_wage'))}원"
    pen.text(who, 10)
    pen.y += 18
    pen.text(f"근로 {int(slip.get('work_days') or 0)}일 / {_hours(slip.get('basic_hours'))}", 10)
    pen.y += 22

    pen.text("지급", 11)
    pen.y += 16
    gross = int(slip.get("taxable_pay") or 0) + int(slip.get("nontaxable_pay") or 0)
    pen.row("근무수당", f"{_won(slip.get('base_pay'))}원")
    pen.row("주휴수당", f"{_won(slip.get('weekly_holiday_pay'))}원")
    pen.row("총지급액", f"{_won(gross)}원", bold=True)
    pen.y += 10

    pen.text("공제", 11)
    pen.y += 16
    for label, amount in _deductions(slip):
        pen.row(label, f"{_won(amount)}원", bold=label == "공제합계")
    pen.y += 12
    pen._gap(28)
    pen.page.draw_rect(fitz.Rect(_LEFT, pen.y, _RIGHT, pen.y + 26), color=_BLACK, width=1.2)
    pen.page.insert_text((_LEFT + 8, pen.y + 18), "실지급액", fontsize=12, fontname="korea", color=_BLACK)
    net = f"{_won(slip.get('net_pay'))}원"
    net_w = fitz.get_text_length(net, fontname="korea", fontsize=12)
    pen.page.insert_text((_RIGHT - 8 - net_w, pen.y + 18), net, fontsize=12, fontname="korea", color=_BLACK)
    pen.y += 38

    pen.text("근무내역", 11)
    pen.y += 16
    pen.work_row(["근무일", "근무시간", "시간", "근무수당"], header=True)
    for line in slip.get("lines") or []:
        shift = line.get("shift_label") or ""
        if not shift:
            shift = "~".join(part for part in (line.get("start_time") or "", line.get("end_time") or "") if part) or "—"
        pen.work_row([
            str(line.get("work_date") or ""),
            shift,
            _hours(line.get("hours")),
            f"{_won(line.get('pay'))}원",
        ])
    pen.y += 14
    pen._gap(28)
    freelance = slip.get("withholding_kind") == "business_3_3" or slip.get("pay_regime") == "business"
    note = (
        "실지급액은 총지급액에서 소득세 3%와 지방소득세 0.3%를 뺀 금액입니다."
        if freelance
        else "실지급액은 총지급액에서 소득세와 근로자 보험료를 뺀 금액입니다. 산재보험은 회사가 따로 냅니다."
    )
    pen.text(note, 8)
    pen.y += 16
    pen.text(company, 10, align=2)
