"""날인된 근로계약서를 다시 출력할 수 있는 PDF로 만든다."""
from __future__ import annotations

from pathlib import Path

import fitz

_SEAL_PATH = Path(__file__).resolve().parents[2] / "assets" / "seal.png"


def _won(value: int) -> str:
    return f"{int(value):,}원"


def _date(value: str) -> str:
    text = (value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        year, month, day = text[:10].split("-")
        return f"{year}년 {month}월 {day}일"
    return text or "—"


def _period(start: str, end: str) -> str:
    if start and end:
        return f"{_date(start)} 부터 {_date(end)} 까지"
    if start:
        return f"{_date(start)} 부터"
    return "별도 정함"


def render_contract_pdf(
    doc_id: int,
    company: dict,
    fields: dict,
    calc: dict,
    completed_at: str,
    *,
    preview: bool = False,
) -> bytes:
    pen = _Pen()
    company_name = company.get("company_name") or "틸리언"
    pen.center("근 로 계 약 서", 18)
    pen.blank(6)
    pen.line(f"(갑) 사용자    사업체명 {_text(company_name)}    대표자 {_text(company.get('representative'))}")
    pen.line(f"주소 {_text(company.get('address'))}")
    pen.blank(4)
    pen.line("(을) 근로자 기재")
    pen.line(f"성명  {_blank(fields.get('employee_name'))}")
    pen.line(f"주민등록번호  {_blank(fields.get('resident_id'))}")
    pen.line(f"주소  {_blank(fields.get('address'))}")
    pen.line(f"연락처  {_blank(fields.get('phone'))}")
    pen.line(
        f"직무 {_text(fields.get('job_title'))}    직급 {_text(fields.get('rank_title'))}"
        f"    입사일 {_date(fields.get('hire_date') or '')}"
    )
    pen.blank(6)
    pen.paragraph(
        '위 당사자는 다음과 같이 자유의사로 포괄임금제 근로계약을 체결하고, 신의성실의 원칙에 의하여 이행할 것을 약정하며, '
        '"을"의 사규에 위배되는 행위로 인하여 발생하는 불이익에 대해서는 이의를 제기하지 않을 것을 서약합니다.'
    )
    pen.blank(4)
    pen.line("가. 계약내용", 11)
    pen.paragraph(f"① 계약기간  {_period(fields.get('contract_start') or '', fields.get('contract_end') or '')}")
    pen.paragraph('② 근로장소  사업장 또는 (갑)이 지정하는 장소')
    pen.paragraph(f"③ 업무  {_text(fields.get('job_title'))}    직급 {_text(fields.get('rank_title'))}")
    pen.paragraph(
        f"④ 근로시간  평일 {_text(fields.get('weekday_hours'), '09:00~18:00')}"
        f"    휴게시간 {_text(fields.get('break_time'), '1시간 (12~13)')}"
    )
    pen.paragraph("업무상 필요한 경우 시업·종업시간과 휴게시간을 1일 소정근로시간 8시간 안에서 조정할 수 있다.")
    pen.paragraph('갑은 을과 합의하여 1주 12시간 한도로 근로시간을 연장할 수 있다.')
    pen.paragraph("소정근로시간 외 시간외 근무에 동의하며, 해당 수당은 연봉에 포함하여 산정·지급한다.")
    pen.paragraph("근로기준법 제51조에서 정한 2주 단위 탄력적 근로시간제를 적용한다.")
    pen.paragraph(f"⑤ 근로일  {_text(fields.get('work_days'), '주중 평균 5일 근무')}")
    pen.paragraph("⑥ 휴일  일요일(1주 만근자에 한함), 근로자의 날, 관공서의 공휴일에 관한 규정에 따른 법정공휴일")
    pen.paragraph("⑦ 휴가  연차휴가는 근로기준법 제60조에 따른다.")
    pen.paragraph("⑧ 임금  실수령액 기준으로 정한 포괄임금이며, 월 급여 구성은 아래와 같다.")
    pen.blank(2)
    pen.line(
        f"총연봉 {_won(calc['annual'])}    월급여 {_won(calc['gross'])}"
        f"    공제합계 {_won(calc['deduction_total'])}    실수령액 {_won(calc['net'])}"
    )
    pen.line(f"통상시급 {_won(calc['hourly'])}")
    pen.line(f"기본급 {_won(calc['base_pay'])}  ({_hours(calc['base_hours'])})")
    pen.line(f"연장수당 {_won(calc['overtime_pay'])}  ({_hours(calc['overtime_hours'])})")
    pen.line(f"휴일수당 {_won(calc['holiday_pay'])}  ({_hours(calc['holiday_hours'])})")
    pen.line(f"야간수당 {_won(calc['night_pay'])}  ({_hours(calc['night_hours'])})")
    pen.line(f"식대 {_won(calc['meal_allowance'])}    차량유지비 {_won(calc['vehicle_allowance'])}    직책수당 {_won(calc['position_allowance'])}")
    pen.paragraph(
        "공제  국민연금 {pension}  건강보험 {health}  장기요양 {care}  소득세 {income_tax}  주민세 {local_tax}  고용보험 {employment}".format(
            pension=_won(calc["pension"]),
            health=_won(calc["health"]),
            care=_won(calc["care"]),
            income_tax=_won(calc["income_tax"]),
            local_tax=_won(calc["local_tax"]),
            employment=_won(calc["employment"]),
        )
    )
    pen.paragraph("기본급은 주휴시간을 포함한 월 소정근로시간에 대한 임금으로 한다.")
    pen.paragraph("월 통상 연장·야간·휴일수당은 이 계약으로 고정되어 발생하는 시간에 대한 임금이며, 이를 넘는 시간은 따로 계산하여 지급한다.")
    pen.paragraph("연차휴가를 사용하면 수당을 지급하지 않으며, 연차일수와 수당은 계약일부터 1년 뒤에 정산한다.")
    pay_day = int(fields.get("pay_day") or 15)
    pen.paragraph(f"⑨ 임금지급  매월 {pay_day}일(전월 1일부터 말일까지) 을에게 직접 지급한다.")
    pen.blank(4)
    pen.line("나. 계약의 해지", 11)
    pen.paragraph("업무수행을 충분히 이행하지 못한 것으로 인정되거나 부정행위를 한 경우")
    pen.paragraph("고의 또는 과실로 사업장에 재산상 손실을 입히거나 명예를 실추시킨 경우")
    pen.paragraph("취업규칙을 위반한 경우")
    pen.blank(4)
    pen.line("다. 특약사항", 11)
    pen.paragraph("본인 부주의로 발생한 사고는 본인이 민사상·형사상 책임을 지고 배상한다.")
    pen.paragraph("사업장에서 알게 된 급여를 포함한 기밀과 개인정보를 외부에 유출하거나 타인에게 제공할 수 없으며, 위반하면 손해배상 책임을 진다.")
    pen.paragraph("중도퇴직은 퇴직예정일 30일 전에 알리고 사직서를 제출하며, 갑의 승인 후 퇴직한다. 그렇지 않으면 무단결근으로 본다.")
    pen.paragraph("입사 후 6개월 안에 퇴사하면 지급한 물품을 반환하고, 분실 또는 훼손이 있으면 갑에게 배상한다.")
    pen.paragraph("본인 임금 내역을 동료를 포함한 타인에게 누설하지 않으며, 위반하면 취업규칙과 사규에 따른 징계에 동의한다.")
    pen.paragraph("갑의 고객 연락처를 영업 등 개인 목적으로 사용할 수 없으며, 위반하면 법령상 처벌과 손해배상을 감수한다.")
    pen.paragraph("본인 개인정보를 급여 및 4대보험 업무 관련자에게 제공하는 데 동의한다.")
    pen.blank(4)
    pen.paragraph("본 계약서에 적지 않은 사항은 근로기준법, 취업규칙, 사업장 관례에 따른다.")
    pen.paragraph("근로자 본인은 취업규칙을 충분히 숙지하였음을 확인한다.")
    pen.blank(8)
    pen.line(f"날인일 {_date(completed_at)}")
    pen.blank(4)
    pen.line_with_seal(
        f"(갑) {company_name}  {_text(company.get('representative'))}  (인)",
        _seal_bytes(),
    )
    pen.line(f"(을) {_text(fields.get('employee_name'))}  (서명 또는 인)")
    pen.line("본 계약서의 사본을 받았음을 확인합니다. (서명 또는 인)")
    pen.blank(10)
    pen.line("야간, 휴일 및 연장근로 동의서", 12)
    pen.blank(3)
    pen.paragraph("본인은 근로기준법에서 정한 야간, 휴일 및 연장(시간외)근로에 동의합니다.")
    pen.blank(4)
    pen.line(f"주민등록번호 {_text(fields.get('resident_id'))}")
    pen.line(f"성명 {_text(fields.get('employee_name'))}  (인)")
    pen.blank(4)
    pen.line(f"{company_name}  대표 귀하")
    pen.blank(8)
    if preview:
        pen.line("미리보기    이 장은 출력 확인용이며 날인 보관본이 아닙니다.", 8)
    else:
        pen.line(f"문서번호 {doc_id}    이 문서는 날인 시점의 계약 내용입니다.", 8)

    total = pen.doc.page_count
    for index, page in enumerate(pen.doc, start=1):
        page.insert_font(fontname="korea", fontbuffer=pen.font.buffer)
        page.insert_text(
            (500, 820),
            f"{index}/{total}",
            fontsize=8,
            fontname="korea",
            color=(0.35, 0.35, 0.35),
        )
    return pen.doc.tobytes()


def render_page_pngs(pdf: bytes, zoom: float = 2.0) -> list[bytes]:
    """A4 미리보기와 인쇄에 쓰는 페이지 이미지."""
    doc = fitz.open(stream=pdf, filetype="pdf")
    matrix = fitz.Matrix(zoom, zoom)
    return [page.get_pixmap(matrix=matrix, alpha=False).tobytes("png") for page in doc]


def _seal_bytes() -> bytes:
    if not _SEAL_PATH.is_file():
        raise ValueError("회사 직인 파일이 없습니다.")
    return _SEAL_PATH.read_bytes()


def _blank(value) -> str:
    text = str(value or "").strip()
    return text or "＿" * 24


def _text(value, fallback: str = "—") -> str:
    text = str(value or "").strip()
    return text or fallback


def _hours(value) -> str:
    number = float(value or 0)
    if number.is_integer():
        return f"{int(number)}시간"
    return f"{number:g}시간"


class _Pen:
    def __init__(self):
        self.doc = fitz.open()
        self.font = fitz.Font("korea")
        self.page = None
        self.y = 0.0
        self.new_page()

    def new_page(self) -> None:
        self.page = self.doc.new_page(width=595, height=842)
        self.page.insert_font(fontname="korea", fontbuffer=self.font.buffer)
        self.y = 46

    def _width(self, text: str, size: float) -> float:
        return fitz.get_text_length(text, fontname="korea", fontsize=size)

    def _wrap(self, text: str, size: float) -> list[str]:
        lines: list[str] = []
        for paragraph in text.split("\n"):
            current = ""
            for ch in paragraph:
                trial = current + ch
                if current and self._width(trial, size) > 490:
                    lines.append(current)
                    current = ch
                else:
                    current = trial
            lines.append(current)
        return lines or [""]

    def _draw(self, text: str, size: float, gap: float, align_center: bool = False) -> None:
        for line in self._wrap(text, size):
            if self.y > 790:
                self.new_page()
            if align_center and line:
                width = self._width(line, size)
                x = (595 - width) / 2
            else:
                x = 48
            self.page.insert_text((x, self.y), line, fontsize=size, fontname="korea", color=(0, 0, 0))
            self.y += size + gap

    def center(self, text: str, size: float) -> None:
        self._draw(text, size, 6, align_center=True)

    def line(self, text: str, size: float = 9.5) -> None:
        self._draw(text, size, 4)

    def line_with_seal(self, text: str, seal: bytes) -> None:
        if self.y > 720:
            self.new_page()
        baseline = self.y
        self.line(text)
        text_width = min(self._width(text, 9.5), 340)
        x = 56 + text_width
        rect = fitz.Rect(x, baseline - 58, x + 78, baseline + 20)
        self.page.insert_image(rect, stream=seal, keep_proportion=True)
        self.y = max(self.y, baseline + 24)

    def paragraph(self, text: str) -> None:
        self._draw(text, 9, 3.5)

    def blank(self, height: float) -> None:
        self.y += height
