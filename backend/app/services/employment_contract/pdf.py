"""날인된 근로계약서를 샘플 양식과 같은 칸 배치로 만든다."""
from __future__ import annotations

from pathlib import Path

import fitz

from backend.app.services.employment_contract.seal import mark_is_signature

_SEAL_PATH = Path(__file__).resolve().parents[2] / "assets" / "seal.png"

_LEFT = 69.24
_RIGHT = 539.4
_LABEL = 120.18
_BLACK = (0, 0, 0)


def _num(value) -> str:
    return f"{int(value or 0):,}"


def _pay_cell(value, dash_if_zero: bool = False) -> str:
    amount = int(value or 0)
    if dash_if_zero and amount == 0:
        return "-"
    return _num(amount)


def _hours(value) -> str:
    number = float(value or 0)
    shown = str(int(number)) if number.is_integer() else f"{number:g}"
    return f"{shown} 시간"


def _date_parts(value: str) -> tuple[str, str, str]:
    text = (value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        year, month, day = text[:10].split("-")
        return str(int(year)), str(int(month)), str(int(day))
    return "", "", ""


def _date(value: str) -> str:
    year, month, day = _date_parts(value)
    if not year:
        return ""
    return f"{year}년 {month}월 {day}일"


def render_contract_pdf(
    doc_id: int,
    company: dict,
    fields: dict,
    calc: dict,
    completed_at: str,
    *,
    preview: bool = False,
    employee_mark: bytes | None = None,
) -> bytes:
    form = _Form(doc_id, employee_mark)
    form.draw_contract(company, fields, calc, preview=preview)
    form.draw_consent(company, fields)
    form.draw_pledge(company, fields)
    _ = completed_at
    return form.doc.tobytes()


def render_page_pngs(pdf: bytes, zoom: float = 2.0) -> list[bytes]:
    """A4 미리보기와 인쇄에 쓰는 페이지 이미지."""
    doc = fitz.open(stream=pdf, filetype="pdf")
    matrix = fitz.Matrix(zoom, zoom)
    return [page.get_pixmap(matrix=matrix, alpha=False).tobytes("png") for page in doc]


def _seal_bytes() -> bytes:
    if not _SEAL_PATH.is_file():
        raise ValueError("회사 직인 파일이 없습니다.")
    pix = fitz.Pixmap(_SEAL_PATH.read_bytes())
    if not pix.alpha:
        return pix.tobytes("png")
    n = pix.n
    width, height = pix.width, pix.height
    samples = pix.samples
    min_x, min_y, max_x, max_y = width, height, 0, 0
    found = False
    for y in range(height):
        row = y * width * n
        for x in range(width):
            if samples[row + x * n + 3] < 16:
                continue
            found = True
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if not found:
        return pix.tobytes("png")
    pad = 8
    x0 = max(0, min_x - pad)
    y0 = max(0, min_y - pad)
    x1 = min(width, max_x + pad + 1)
    y1 = min(height, max_y + pad + 1)
    crop_w = x1 - x0
    crop_h = y1 - y0
    cropped = bytearray(crop_w * crop_h * n)
    for y in range(crop_h):
        src = ((y0 + y) * width + x0) * n
        dst = y * crop_w * n
        cropped[dst:dst + crop_w * n] = samples[src:src + crop_w * n]
    return fitz.Pixmap(pix.colorspace, crop_w, crop_h, bytes(cropped), 1).tobytes("png")


def _clean(value, fallback: str = "") -> str:
    return str(value or "").strip() or fallback


def _birth(resident_id: str) -> str:
    digits = "".join(ch for ch in str(resident_id or "") if ch.isdigit())
    if len(digits) < 7:
        return ""
    year = int(digits[0:2])
    month = int(digits[2:4])
    day = int(digits[4:6])
    century = {
        "1": 1900, "2": 1900, "5": 1900, "6": 1900,
        "3": 2000, "4": 2000, "7": 2000, "8": 2000,
        "9": 1800, "0": 1800,
    }.get(digits[6])
    if century is None or not (1 <= month <= 12 and 1 <= day <= 31):
        return ""
    return f"{century + year}년 {month}월 {day}일"


class _Form:
    def __init__(self, doc_id: int, employee_mark: bytes | None = None):
        self.doc = fitz.open()
        self.doc.set_metadata({"title": f"근로계약서 {doc_id}" if doc_id else "근로계약서"})
        self.font = fitz.Font("korea")
        self.employee_mark = employee_mark or None
        self.page = self.doc.new_page(width=595, height=842)
        self._use_font()

    def _use_font(self) -> None:
        self.page.insert_font(fontname="korea", fontbuffer=self.font.buffer)

    def _line(self, x0: float, y0: float, x1: float, y1: float, width: float = 0.55) -> None:
        self.page.draw_line(fitz.Point(x0, y0), fitz.Point(x1, y1), color=_BLACK, width=width)

    def _box(self, x0: float, y0: float, x1: float, y1: float, width: float = 1.15) -> None:
        self.page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=_BLACK, width=width)

    def _width(self, text: str, size: float) -> float:
        return fitz.get_text_length(text, fontname="korea", fontsize=size)

    def _put(
        self,
        rect: fitz.Rect,
        text: str,
        size: float = 7,
        align: int = fitz.TEXT_ALIGN_CENTER,
        min_size: float = 4.6,
        top: bool = False,
    ) -> None:
        value = str(text or "").strip()
        if not value:
            return
        pad = 1.5
        inner = max(rect.width - pad * 2, 8)
        if top or "\n" in value:
            box = fitz.Rect(rect.x0 + pad, rect.y0 + 1.0, rect.x1 - pad, rect.y1 - 0.4)
            self.page.insert_textbox(box, value, fontsize=size, fontname="korea", align=align, color=_BLACK)
            return
        use = size
        while use > min_size and self._width(value, use) > inner:
            use -= 0.2
        text_w = self._width(value, use)
        if align == fitz.TEXT_ALIGN_RIGHT:
            x = rect.x1 - pad - text_w
        elif align == fitz.TEXT_ALIGN_LEFT:
            x = rect.x0 + pad
        else:
            x = rect.x0 + (rect.width - text_w) / 2
        baseline = min(rect.y0 + (rect.height + use * 0.7) / 2, rect.y1 - 1.1)
        self.page.insert_text((x, baseline), value, fontsize=use, fontname="korea", color=_BLACK)

    def _write(self, x: float, y: float, text: str, size: float = 7) -> None:
        value = str(text or "")
        if not value:
            return
        self.page.insert_text((x, y), value, fontsize=size, fontname="korea", color=_BLACK)

    def _stack(self, rect: fitz.Rect, lines: list[str], size: float) -> None:
        gap = size + 1.5
        baseline = rect.y0 + (rect.height - (gap * (len(lines) - 1) + size)) / 2 + size * 0.78
        for line in lines:
            width = self._width(line, size)
            x = rect.x0 + max((rect.width - width) / 2, 0.6)
            self.page.insert_text((x, baseline), line, fontsize=size, fontname="korea", color=_BLACK)
            baseline += gap

    def _paragraphs(self, x: float, y: float, width: float, lines: list[str], size: float, gap: float, fit: bool = False) -> None:
        if fit:
            while size > 5.2 and any(self._width(line, size) > width for line in lines):
                size -= 0.15
        cursor = y
        for line in lines:
            current = ""
            for ch in line:
                trial = current + ch
                if current and self._width(trial, size) > width:
                    self._write(x, cursor, current, size)
                    cursor += gap
                    current = ch
                else:
                    current = trial
            self._write(x, cursor, current, size)
            cursor += gap

    def draw_contract(self, company: dict, fields: dict, calc: dict, *, preview: bool) -> None:
        self._write_title()
        self._draw_grid()
        self._fill_header(company, fields)
        self._fill_terms(fields)
        self._fill_pay(fields, calc)
        self._fill_closing(company, fields)
        _ = preview

    def _write_title(self) -> None:
        self._put(fitz.Rect(140, 16, 455, 46), "근 로 계 약 서", 12.5)

    def _draw_grid(self) -> None:
        self._box(_LEFT, 49.44, _RIGHT, 794.28)
        thin = (
            (61.02, _LABEL, _RIGHT),
            (72.54, _LEFT, _RIGHT),
            (84.06, _LABEL, _RIGHT),
            (95.58, _LEFT, _RIGHT),
            (137.82, _LEFT, _RIGHT),
            (149.34, _LABEL, _RIGHT),
            (160.86, _LEFT, _RIGHT),
            (172.38, _LEFT, _RIGHT),
            (183.90, _LEFT, _RIGHT),
            (207.24, _LABEL, _RIGHT),
            (218.46, _LABEL, _RIGHT),
            (291.18, _LEFT, _RIGHT),
            (302.70, _LEFT, _RIGHT),
            (326.82, _LEFT, _RIGHT),
            (350.82, _LEFT, _RIGHT),
            (374.22, _LABEL, _RIGHT),
            (375.42, _LABEL, _RIGHT),
            (425.94, _LABEL, _RIGHT),
            (444.78, _LABEL, _RIGHT),
        )
        for y, x0, x1 in thin:
            self._line(x0, y, x1, y, 0.55)
        self._line(171.06, 195.42, 374.58, 195.42, 0.55)
        self._line(423.42, 195.42, _RIGHT, 195.42, 0.55)
        self._line(171.06, 456.30, _RIGHT, 456.30, 0.55)
        for y in (119.04, 362.76, 389.40, 413.88, 468.24, 530.28, 550.80, 597.96, 713.64):
            self._line(_LEFT if y not in (362.76, 389.40, 413.88, 468.24) else _LABEL, y, _RIGHT, y, 1.15)

        self._line(_LABEL, 49.44, _LABEL, 95.58, 0.6)
        self._line(_LABEL, 137.82, _LABEL, 550.80, 0.6)
        self._line(221.94, 49.44, 221.94, 95.58, 0.55)
        self._line(374.58, 49.44, 374.58, 61.02, 0.55)
        self._line(473.34, 49.44, 473.34, 61.02, 0.55)
        self._line(323.70, 72.54, 323.70, 84.06, 0.55)
        self._line(423.42, 72.54, 423.42, 84.06, 0.55)
        self._line(374.58, 160.86, 374.58, 207.24, 0.55)
        self._line(473.34, 160.86, 473.34, 183.90, 0.55)
        self._line(171.06, 183.90, 171.06, 207.24, 0.55)
        self._line(423.42, 183.90, 423.42, 207.24, 0.55)
        for x in (171.06, 272.82, 374.58, 473.34):
            self._line(x, 362.76, x, 389.40, 0.55)
        for x in (171.06, 221.94, 272.82, 323.70, 374.58, 423.42, 473.34):
            self._line(x, 425.94, x, 468.24, 0.55)

    def _fill_header(self, company: dict, fields: dict) -> None:
        self._put(fitz.Rect(_LEFT, 49.44, _LABEL, 72.54), "(갑)사용자", 7)
        self._put(fitz.Rect(_LABEL, 49.44, 221.94, 61.02), "사업체명", 7)
        self._put(fitz.Rect(221.94, 49.44, 374.58, 61.02), _clean(company.get("company_name"), "틸리언"), 7)
        self._put(fitz.Rect(374.58, 49.44, 473.34, 61.02), "대표자", 7)
        self._put(fitz.Rect(473.34, 49.44, _RIGHT, 61.02), _clean(company.get("representative")), 7)
        self._put(fitz.Rect(_LABEL, 61.02, 221.94, 72.54), "주소", 7)
        self._put(fitz.Rect(221.94, 61.02, _RIGHT, 72.54), _clean(company.get("address")), 7)
        self._put(fitz.Rect(_LEFT, 72.54, _LABEL, 95.58), "(을)근로자", 7)
        self._put(fitz.Rect(_LABEL, 72.54, 221.94, 84.06), "성명", 7)
        self._put(fitz.Rect(221.94, 72.54, 323.70, 84.06), _clean(fields.get("employee_name")), 7)
        self._put(fitz.Rect(323.70, 72.54, 423.42, 84.06), "주민등록번호", 7)
        self._put(fitz.Rect(423.42, 72.54, _RIGHT, 84.06), _clean(fields.get("resident_id")), 6.4)
        self._put(fitz.Rect(_LABEL, 84.06, 221.94, 95.58), "주소", 7)
        self._put(fitz.Rect(221.94, 84.06, _RIGHT, 95.58), _clean(fields.get("address")), 7)
        self._put(
            fitz.Rect(_LEFT + 2, 96.2, _RIGHT - 2, 118.2),
            '위 당사자는 다음과 같이 자유의사로 포괄임금제 근로계약을 체결하고, 신의성실의 원칙에 의하여 이행할 것을 약정하며, '
            '"을"의 사규에 위배되는 행위로 인하여 발생하는 불이익에 대해서는 이의를 제기하지 않을 것을 서약 합니다.',
            6.2,
            fitz.TEXT_ALIGN_LEFT,
            top=True,
        )

    def _fill_terms(self, fields: dict) -> None:
        self._put(fitz.Rect(_LEFT, 119.04, _RIGHT, 137.82), '가. "을"의 계약내용(조건)', 7, fitz.TEXT_ALIGN_LEFT)
        self._put(fitz.Rect(_LEFT, 137.82, _LABEL, 160.86), "① 계약기간", 7)
        self._period(fields)
        self._put(fitz.Rect(_LEFT, 160.86, _LABEL, 172.38), "② 근로장소", 7)
        self._put(fitz.Rect(_LABEL, 160.86, 374.58, 172.38), "사업장 또는 (갑)이 지정하는 장소", 7)
        self._put(fitz.Rect(374.58, 160.86, 473.34, 172.38), "급여지급형태", 6.2)
        self._put(fitz.Rect(473.34, 160.86, _RIGHT, 172.38), "연봉제 / 월급제", 6)
        self._put(fitz.Rect(_LEFT, 172.38, _LABEL, 183.90), "③ 업무/직종", 6.4)
        self._put(fitz.Rect(_LABEL, 172.38, 374.58, 183.90), _clean(fields.get("job_title")), 7)
        self._put(fitz.Rect(374.58, 172.38, 473.34, 183.90), "직급", 7)
        self._put(fitz.Rect(473.34, 172.38, _RIGHT, 183.90), _clean(fields.get("rank_title")), 7)
        self._put(fitz.Rect(_LABEL, 183.90, 171.06, 207.24), "평일", 7)
        self._put(
            fitz.Rect(171.06, 183.90, 374.58, 195.42),
            _clean(fields.get("weekday_hours"), "09:00~18:00"),
            7,
        )
        self._put(fitz.Rect(374.58, 183.90, 423.42, 207.24), "휴게시간", 6.2)
        self._put(
            fitz.Rect(423.42, 183.90, _RIGHT, 195.42),
            _clean(fields.get("break_time"), "1시간 (12~13)"),
            6.2,
        )
        self._put(fitz.Rect(_LEFT, 210, _LABEL, 280), "④ 근로시간", 7)
        self._paragraphs(
            124,
            228,
            408,
            [
                '▷ 업무상 필요한 경우 "갑"과 "을"이 협의하여 시업 종업시간, 휴게시간을 1일 소정근로시간 8시간 내에서 조정할 수 있다.',
                '▷ "갑"은"을"과 합의하여 1주 12시간 근로시간을 연장할 수 있다.',
                '▷ "갑"과 "을"은 소정근로시간외에 시간외 근무에 동의하며 해당시간의 시간외 수당을 연봉에 포함하여 산정 지급한다.',
                "▷ 근로기준법 제 51조에서 정하고 있는 2주단위 탄력적 근로시간제를 적용하기로 한다.",
            ],
            6.5,
            12.2,
            fit=True,
        )
        self._put(fitz.Rect(_LEFT, 291.18, _LABEL, 302.70), "⑤ 근 로 일", 6.5)
        self._put(
            fitz.Rect(_LABEL, 291.18, _RIGHT, 302.70),
            _clean(fields.get("work_days"), "주중 평균 5일 근무"),
            7,
            fitz.TEXT_ALIGN_LEFT,
        )
        self._put(fitz.Rect(_LEFT, 302.70, _LABEL, 326.82), "⑥ 휴    일", 7)
        self._put(
            fitz.Rect(_LABEL, 302.70, _RIGHT, 326.82),
            "일요일(1주 만근자에 한함), 근로자의 날, 관공서 공휴일에 관한 규정에 따른 법정공휴일",
            6.6,
            fitz.TEXT_ALIGN_LEFT,
        )
        self._put(fitz.Rect(_LEFT, 326.82, _LABEL, 350.82), "⑦ 휴    가", 7)
        self._put(
            fitz.Rect(_LABEL, 326.82, _RIGHT, 350.82),
            "연차휴가는 「근로기준법」 제60조에 의한다",
            6.4,
            fitz.TEXT_ALIGN_LEFT,
        )

    def _period(self, fields: dict) -> None:
        start = _date(fields.get("contract_start") or "")
        end = _date(fields.get("contract_end") or "")
        self._put(fitz.Rect(230, 137.82, 276, 149.34), "부터", 7)
        self._put(fitz.Rect(400, 137.82, 446, 149.34), "까지", 7)
        if start:
            self._put(fitz.Rect(_LABEL, 137.82, 230, 149.34), start, 6.4, fitz.TEXT_ALIGN_RIGHT)
        if end:
            self._put(fitz.Rect(300, 137.82, 400, 149.34), end, 6.4, fitz.TEXT_ALIGN_RIGHT)

    def _fill_pay(self, fields: dict, calc: dict) -> None:
        self._put(fitz.Rect(_LABEL, 350.82, _RIGHT, 362.76), "[년간] (연봉제근로자에 한함)", 7, fitz.TEXT_ALIGN_LEFT)
        headers = ("구분", "총연봉액", "월급여액", "공제합계", "실수령액")
        annual_x = (_LABEL, 171.06, 272.82, 374.58, 473.34, _RIGHT)
        for index, label in enumerate(headers):
            self._put(fitz.Rect(annual_x[index], 362.76, annual_x[index + 1], 374.22), label, 7)
        values = (
            "산정금액",
            _num(calc.get("annual")),
            _num(calc.get("gross")),
            _num(calc.get("deduction_total")),
            _num(calc.get("net")),
        )
        for index, label in enumerate(values):
            self._put(fitz.Rect(annual_x[index], 375.42, annual_x[index + 1], 389.40), label, 7)
        self._put(
            fitz.Rect(_LABEL, 389.40, _RIGHT, 404),
            "(실수령액 기준 계약임.)",
            7,
            fitz.TEXT_ALIGN_LEFT,
        )
        self._put(fitz.Rect(_LABEL, 413.88, 250, 425.94), "[월급여액 세부내역]", 7, fitz.TEXT_ALIGN_LEFT)
        gross = _num(calc.get("gross"))
        self._put(fitz.Rect(250, 413.88, 430, 425.94), f"월 급여액   {gross} 원", 7)
        self._line(336, 423.2, 392, 423.2, 0.4)

        detail_x = (_LABEL, 171.06, 221.94, 272.82, 323.70, 374.58, 423.42, 473.34, _RIGHT)
        detail_headers = (
            "통상시급(원)",
            "기본급",
            ("월통상", "연장수당"),
            ("월통상", "휴일수당"),
            ("월통상", "야간수당"),
            "식대",
            "차량유지비",
            "직책수당",
        )
        for index, label in enumerate(detail_headers):
            cell = fitz.Rect(detail_x[index], 425.94, detail_x[index + 1], 444.78)
            if isinstance(label, tuple):
                self._stack(cell, list(label), 5.6)
            else:
                self._put(cell, label, 6.0)
        self._put(fitz.Rect(_LABEL, 444.78, 171.06, 468.24), _num(calc.get("hourly")), 7)
        hour_values = (
            _hours(calc.get("base_hours")),
            _hours(calc.get("overtime_hours")),
            _hours(calc.get("holiday_hours")),
            _hours(calc.get("night_hours")),
        )
        for index, label in enumerate(hour_values):
            self._put(fitz.Rect(detail_x[index + 1], 444.78, detail_x[index + 2], 456.30), label, 6.4)
        amounts = (
            _pay_cell(calc.get("base_pay")),
            _pay_cell(calc.get("overtime_pay"), True),
            _pay_cell(calc.get("holiday_pay"), True),
            _pay_cell(calc.get("night_pay"), True),
            _pay_cell(calc.get("meal_allowance"), True),
            _pay_cell(calc.get("vehicle_allowance")),
            _pay_cell(calc.get("position_allowance")),
        )
        for index, label in enumerate(amounts):
            self._put(fitz.Rect(detail_x[index + 1], 456.30, detail_x[index + 2], 468.24), label, 6.5)
        self._stack(fitz.Rect(_LEFT, 418, _LABEL, 462), ["⑧임금구성", "항목 및", "계산방법"], 5.6)
        self._paragraphs(
            124,
            480,
            408,
            [
                "기본급은 주휴시간을 포함하여 월소정 근로시간에 대한 임금으로 한다.",
                "월통상 연장, 야간, 휴일수당은 매월 근로계약에 의해 고정적으로 발생하는 연장·야간·휴일근로시간에 대한 임금으로 산정하며 이에 초과분에 대해서는 별도 산정하여 추가적으로 지급하기로 한다.",
                "연차휴가를 사용하는 경우 수당을 지급치 아니하며, 연차휴가일수 및 수당은 계약일로부터 1년 후 정산한다.",
            ],
            6.2,
            10.4,
        )
        pay_day = int(fields.get("pay_day") or 15)
        self._put(fitz.Rect(_LEFT, 530.28, _LABEL, 550.80), "⑨ 임금지급방법", 5.2)
        self._put(
            fitz.Rect(_LABEL, 530.28, _RIGHT, 550.80),
            f'매월 {pay_day}일 (전 월 초일부터 말일까지 산정) "을"에게 직접 지급(현금 또는 "을"명의의 예금계좌)한다.',
            6.5,
            fitz.TEXT_ALIGN_LEFT,
        )

    def _fill_closing(self, company: dict, fields: dict) -> None:
        self._write(78, 562, "나. 계약의 해지", 7)
        self._paragraphs(
            124,
            574,
            408,
            [
                "▷ 본인이 업무수행을 충분히 이행하지 못한 것으로 인정될 경우나 부정행위를 하였을 경우",
                "▷ 본인의 고의 및 과실로 사업장에 재산상 손실, 명예를 실추시켰을 경우",
                "▷ 취업규칙을 위반하는 행위를 하였을 경우",
            ],
            6.2,
            10.4,
        )
        self._write(78, 608, "다. 특약사항", 7)
        self._paragraphs(
            118,
            620,
            414,
            [
                "▷ 본인의 부주의로 발생된 사고는 본인이 민·형사상 책임을 지며 배상하여야 한다.",
                "▷사업장 내에서 알게된 급여를 포함한 모든 기밀 및 개인 정보와 관련하여 외부유출 또는 타인에게 공개, 제공할 수 없고 사업장내에서 알게된 모든 사항에 대해서 외부로 유출할 수 없고, 이를 위반하였을 때 손해배상책임을 진다.",
                '▷ 퇴직절차 : 계약일로부터 중도퇴직 시 퇴직예정일로부터 30일전에 사전통지 하고 사직서를 제출하여야 하며, "갑"의 승인 후 퇴직처리하며 그렇지 아니한 경우에는 무단결근으로 간주한다.',
                "▷을은 입사후 6개월 이내 퇴사할 경우 제공한 물품을 반납해야 하고, 분실 또는 손실이 있을 경우 갑에게 배상하기로 한다.",
                "▷을은 본인의 임금내역을 동료를 포함한 타인에 누설치 않기로 하고, 만일 이를 위반한 경우 취업규칙이내 사내내규에 따라 징계처분을 받는데 동의한다.",
                "▷을은 갑의 고객의 연락처 등을 영업 등 개인의 목적으로 사용할 수 없으며 이를 위반한 경우 법에서 정하고 있는 처벌 및 손해배상 등을 감수한다.",
                "▷을은 본인의 개인정보를 급여 및 4대보험업무 관련자에게 제공하는 데 동의한다. (서명)",
            ],
            5.3,
            8.8,
        )
        self._put(
            fitz.Rect(_LEFT, 716, _RIGHT, 748),
            "본 계약서에 명시되지 아니한 사항은 근로기준법 ,취업규칙, 사업장관례 의하며,\n"
            "근로자 본인은 취업규칙을 충분히 숙지하였으므로 이에 확인 함",
            7,
        )
        representative = _clean(company.get("representative"))
        employee = _clean(fields.get("employee_name"))
        self._stamp_employer(representative)
        self._ink_line(300, _RIGHT - 8, 762, f"/(을) 근로자   {employee}   (서명 또는 인)", 7, employee)
        self._put(fitz.Rect(_LEFT, 778, _RIGHT, 792), "본 계약서의 사본을 받았음을 확인합니다. (서명 또는 인)", 7)

    def _stamp_employer(self, representative: str) -> None:
        """회사 도장을 갑 대표자 이름과 (인) 위에 올린다. 미리보기와 보관본이 같다."""
        size = 7.0
        baseline = 762.0
        x = _LEFT + 10
        prefix = "(갑) 사용자  "
        self._write(x, baseline, prefix, size)
        name = representative or "장지훈"
        name_x = x + len(prefix) * size
        self._write(name_x, baseline, name, size)
        name_w = max(len(name), 2) * size
        mark_x = name_x + name_w + size
        self._write(mark_x, baseline, "(인)", size)
        seal = _seal_bytes()
        stamp = 44.0
        center_x = name_x + name_w * 0.85
        center_y = baseline + 6
        self.page.insert_image(
            fitz.Rect(center_x - stamp / 2, center_y - stamp / 2, center_x + stamp / 2, center_y + stamp / 2),
            stream=seal,
            keep_proportion=True,
            overlay=True,
        )

    def _ink_line(self, x0: float, x1: float, baseline: float, text: str, size: float, employee: str) -> None:
        value = str(text or "").strip()
        if not value:
            return
        use = size
        while use > 7 and len(value) * use > (x1 - x0):
            use -= 0.3
        text_w = len(value) * use
        x = x0 + max((x1 - x0 - text_w) / 2, 0)
        self._write(x, baseline, value, use)
        self._stamp_worker(x, use, value, baseline, employee)

    def _stamp_worker(self, start: float, size: float, text: str, baseline: float, employee: str) -> None:
        mark = self.employee_mark
        if not mark:
            return
        if mark_is_signature(mark) and employee and employee in text:
            name_at = text.find(employee)
            anchor = start + (name_at + len(employee) / 2) * size
            pix = fitz.Pixmap(mark)
            height = 22.0
            width = min(108.0, height * pix.width / max(pix.height, 1))
            if anchor + width / 2 > _RIGHT - 10:
                anchor = _RIGHT - 10 - width / 2
            rect = fitz.Rect(anchor - width / 2, baseline - height + 3, anchor + width / 2, baseline + 3)
        else:
            index = text.rfind("인")
            if index < 0:
                index = max(len(text) - 1, 0)
            anchor = start + (index + 0.5) * size
            stamp = 34.0
            if anchor + stamp / 2 > _RIGHT - 10:
                anchor = _RIGHT - 10 - stamp / 2
            rect = fitz.Rect(anchor - stamp / 2, baseline - stamp * 0.62, anchor + stamp / 2, baseline + stamp * 0.38)
        self.page.insert_image(rect, stream=mark, keep_proportion=True, overlay=True)

    def draw_consent(self, company: dict, fields: dict) -> None:
        self.page = self.doc.new_page(width=595, height=842)
        self._use_font()
        self._put(fitz.Rect(70, 28, 525, 68), "야간, 휴일 및 연장근로 동의서", 16)
        resident = _clean(fields.get("resident_id"))
        employee = _clean(fields.get("employee_name"))
        self._write(122, 142, f"주민번호:  {resident}", 7.2)
        self._write(122, 164, f"성   명:  {employee}", 7.6)
        self._write(71, 228, "본인은 근로기준법의 규정에 의한 야간, 휴일 및 연장(시간외)근로에", 12.5)
        self._write(71, 248, "동의합니다.", 12.5)
        year, month, day = _date_parts(str(fields.get("hire_date") or ""))
        if year:
            self._put(fitz.Rect(150, 372, 445, 408), f"{year}  년     {month}  월     {day}  일", 11)
        else:
            self._put(fitz.Rect(150, 372, 445, 408), "년          월          일", 11)
        self._ink_line(150, 445, 448, f"위본인      {employee}      (인)", 11, employee)
        company_name = _clean(company.get("company_name"), "틸리언")
        self._put(fitz.Rect(150, 500, 445, 540), f"{company_name}          대표귀하", 11)

    def draw_pledge(self, company: dict, fields: dict) -> None:
        """정보보호 서약서. 근로계약서와 같은 PDF에 이어서 보관한다."""
        self.page = self.doc.new_page(width=595, height=842)
        self._use_font()
        company_name = _clean(company.get("company_name"), "틸리언")
        self._put(fitz.Rect(140, 48, 455, 82), "정보보호 서약서", 18)
        self._line(231, 84.6, 364, 84.6, 1.0)

        left, right = 79.44, 514.68
        row_a, row_b, row_c, bottom = 106.32, 123.0, 139.68, 778.2
        col_b, col_c, col_d = 186.48, 293.52, 406.8
        self._box(left, row_a, right, bottom, 0.9)
        self._line(left, row_b, right, row_b, 0.7)
        self._line(left, row_c, right, row_c, 0.7)
        for x in (col_b, col_c, col_d):
            self._line(x, row_a, x, row_c, 0.7)

        self._put(fitz.Rect(left, row_a, col_b, row_b), "성명", 11)
        self._cell_value(fitz.Rect(col_b, row_a, col_c, row_b), _clean(fields.get("employee_name")), 10)
        self._put(fitz.Rect(col_c, row_a, col_d, row_b), "연락처", 11)
        self._cell_value(fitz.Rect(col_d, row_a, right, row_b), _clean(fields.get("phone")), 9)
        self._put(fitz.Rect(left, row_b, col_b, row_c), "생년월일", 11)
        self._cell_value(fitz.Rect(col_b, row_b, col_c, row_c), _birth(fields.get("resident_id")), 8)
        self._put(fitz.Rect(col_c, row_b, col_d, row_c), "직급", 11)
        self._cell_value(fitz.Rect(col_d, row_b, right, row_c), _clean(fields.get("rank_title")), 10)

        text_left = left + 18
        text_right = right - 12
        paragraphs = [
            f"본인은 {company_name} (이하, '회사'라 함)을 퇴직함에 있어 아래 사항을 충분히 숙지하고, 성실히 준수할 것을 서약합니다.",
            "1. 회사에 재직한 기간 중 독자적으로 또는 다른 사람과 함께 취득한 기술정보 (발명, 특허, 개발, 생산 등 제반 기술) 및 경영정보 (재무, 관리, 기획, 영업, 인사 등 제반정보) 등 모든 영업비밀은 전적으로 회사의 소유이며, 회사가 사용하거나 처분할 권리가 있음을 인정합니다.",
            "2. 어떠한 장소에 어떠한 방법으로도 회사의 영업비밀 및 자산을 보유하거나 저장되고 있지 않음을 확인합니다.",
            "3. 재직기간 중 취득한 회사의 모든 영업비밀 (경영 및 기술정보)은 퇴사 후에도 회사의 업무 인수, 인계와 관련 없는 어떠한 회사내외 제3자에게도 누설하지 않겠습니다.",
            "4. 퇴직 후 3년간 회사의 영업비밀을 이용하여 창업하거나 경쟁관계에 있는 회사 기타 제3자를 위하여 영업비밀을 누설하거나 사용하지 않겠습니다.",
            "5. 회사의 영업비밀 보호를 위한 노력에 적극 협조할 뿐 아니라, 그에 따른 법적 도덕적 의무를 성실히 이행하겠습니다.",
            "본인은 위의 사항을 충분히 숙지하여 이를 성실히 준수할 것이며 만일 이를 위반하였을 경우 부정경쟁방지 및 영업비밀에 관한 법률 등 관련 법령에 따라 민·형사상의 책임 뿐만 아니라 제반 손해 배상의 책임 등 불이익을 감수할 것이며, 회사에 끼친 손해에 대해 지체없이 변상, 복구할 것을 서약합니다.",
        ]
        cursor = self._flow_pledge(paragraphs, text_left, text_right, 156)
        year, month, day = _date_parts(str(fields.get("hire_date") or ""))
        date_text = f"{year}년  {month}월  {day}일" if year else "년     월     일"
        employee = _clean(fields.get("employee_name"))
        sign_text = f"서약자 :  {employee}   (인)"
        cursor = max(cursor + 18, 612)
        self._write_fitted(text_left, text_right, cursor, date_text, 11, align="center")
        self._ink_line(text_left, text_right, cursor + 42, sign_text, 11, employee)
        self._write_fitted(text_left, text_right, min(cursor + 92, bottom - 28), company_name, 14, align="center")

    def _flow_pledge(self, paragraphs: list[str], x: float, right: float, top: float) -> float:
        """돋움은 글자마다 글자 크기만큼 넓다. 그 폭으로 박스 안에서 줄을 나눈다."""
        size = 10.0
        gap = 15.5
        paragraph_gap = 9.0
        width = right - x
        while size > 8.0:
            cursor = top
            for index, paragraph in enumerate(paragraphs):
                if index:
                    cursor += paragraph_gap
                cursor += gap * len(self._wrap_em(paragraph, size, width))
            if cursor < 590:
                break
            size -= 0.4
            gap = size + 5.2
        cursor = top + size
        for index, paragraph in enumerate(paragraphs):
            if index:
                cursor += paragraph_gap
            for line in self._wrap_em(paragraph, size, width):
                self._write(x, cursor, line, size)
                cursor += gap
        return cursor

    def _cell_value(self, rect: fitz.Rect, text: str, size: float) -> None:
        value = str(text or "").strip()
        if not value:
            return
        use = self._em_size(value, rect.width, size)
        text_w = len(value) * use
        x = rect.x0 + max((rect.width - text_w) / 2, 3)
        baseline = rect.y0 + (rect.height + use * 0.72) / 2
        self._write(x, baseline, value, use)

    def _em_size(self, text: str, width: float, size: float) -> float:
        use = size
        while use > 6 and text and len(text) * use > width - 8:
            use -= 0.2
        return use

    def _wrap_em(self, text: str, size: float, width: float) -> list[str]:
        lines: list[str] = []
        current = ""
        limit = max(width, size * 4)
        for ch in text:
            trial = current + ch
            if current and len(trial) * size > limit:
                lines.append(current.rstrip())
                current = "" if ch == " " else ch
            else:
                current = trial
        if current:
            lines.append(current)
        return lines or [""]

    def _write_fitted(self, x0: float, x1: float, baseline: float, text: str, size: float, align: str) -> None:
        value = str(text or "").strip()
        if not value:
            return
        use = size
        while use > 7 and len(value) * use > (x1 - x0):
            use -= 0.3
        text_w = len(value) * use
        if align == "center":
            x = x0 + max((x1 - x0 - text_w) / 2, 0)
        else:
            x = x0
        self._write(x, baseline, value, use)
