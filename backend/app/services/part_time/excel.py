"""노무사에게 넘기는 일용근로대장. 신고 알바만 넣는다."""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

_THIN = Border(
    left=Side(style="thin", color="D0D5DD"),
    right=Side(style="thin", color="D0D5DD"),
    top=Side(style="thin", color="D0D5DD"),
    bottom=Side(style="thin", color="D0D5DD"),
)
_HEAD = PatternFill("solid", fgColor="F3F4F6")
_FONT = Font(name="맑은 고딕", size=9)
_BOLD = Font(name="맑은 고딕", size=9, bold=True)
_TITLE = Font(name="맑은 고딕", size=14, bold=True)


def _write_row(ws, row: int, values: list, header: bool = False) -> None:
    for col, value in enumerate(values, start=1):
        cell = ws.cell(row, col, value)
        cell.font = _BOLD if header else _FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _THIN
        if header:
            cell.fill = _HEAD
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            cell.number_format = "#,##0"


def render_part_time_xlsx(year: int, month: int, company: dict, people: list[dict]) -> bytes:
    book = Workbook()
    summary = book.active
    summary.title = "일용근로대장"
    summary["A1"] = f"{year}년 {month}월 일용근로대장"
    summary["A1"].font = _TITLE
    summary["A2"] = company.get("company_name") or "틸리언"
    summary["C2"] = company.get("business_number") or ""
    summary["A2"].font = _BOLD
    summary["C2"].font = _FONT
    summary["A3"] = "신고 알바만 넣습니다. 미신고 알바는 이 파일에 없습니다."
    summary["A3"].font = _FONT

    headers = [
        "성명",
        "주민등록번호",
        "근로일수",
        "보수지급기초일수",
        "일평균근로시간",
        "총근로시간",
        "시급",
        "근무수당",
        "주휴시간",
        "주휴수당",
        "총지급액(과세소득)",
        "비과세소득",
        "임금총액",
        "근로소득공제",
        "산출세액",
        "세액공제",
        "소득세",
        "지방소득세",
        "공제합계",
        "차인지급액",
    ]
    _write_row(summary, 5, headers, header=True)
    for index, person in enumerate(people):
        _write_row(summary, 6 + index, [
            person["name"],
            person["resident_id"],
            person["work_days"],
            person["work_days"],
            person["average_hours"],
            person["basic_hours"],
            person["hourly_wage"],
            person["base_pay"],
            person["weekly_holiday_hours"],
            person["weekly_holiday_pay"],
            person["taxable_pay"],
            person["nontaxable_pay"],
            person["taxable_pay"] + person["nontaxable_pay"],
            person["earned_income_deduction"],
            person["calculated_tax"],
            person["tax_credit"],
            person["income_tax"],
            person["local_tax"],
            person["deduction_total"],
            person["net_pay"],
        ])
    for col in range(1, len(headers) + 1):
        summary.column_dimensions[get_column_letter(col)].width = 16
    summary.column_dimensions["B"].width = 18
    summary.row_dimensions[5].height = 32
    summary.freeze_panes = "A6"
    summary.auto_filter.ref = f"A5:T{max(5, 5 + len(people))}"
    summary.page_setup.orientation = "landscape"
    summary.page_setup.fitToPage = True
    summary.page_setup.fitToWidth = 1
    summary.page_setup.fitToHeight = 1
    summary.sheet_properties.pageSetUpPr.fitToPage = True
    summary.print_title_rows = "1:5"
    summary.page_setup.paperSize = summary.PAPERSIZE_A4
    summary.oddFooter.center.text = f"{year}년 {month}월 일용근로대장"

    hours = book.create_sheet("근무시간")
    hours["A1"] = f"{year}년 {month}월 근무시간"
    hours["A1"].font = _TITLE
    day_headers = ["성명", "주민등록번호", *[str(day) for day in range(1, 32)], "합계"]
    _write_row(hours, 3, day_headers, header=True)
    for index, person in enumerate(people):
        by_day = person.get("hours_by_day") or {}
        row = [person["name"], person["resident_id"]]
        for day in range(1, 32):
            row.append(by_day.get(day, ""))
        row.append(person["basic_hours"])
        _write_row(hours, 4 + index, row)
    hours.column_dimensions["A"].width = 12
    hours.column_dimensions["B"].width = 18
    for col in range(3, 35):
        hours.column_dimensions[get_column_letter(col)].width = 5
    hours.freeze_panes = "C4"
    hours.page_setup.orientation = "landscape"
    hours.page_setup.fitToPage = True
    hours.page_setup.fitToWidth = 1
    hours.page_setup.fitToHeight = 1
    hours.sheet_properties.pageSetUpPr.fitToPage = True
    hours.print_title_rows = "1:3"
    hours.page_setup.paperSize = hours.PAPERSIZE_A4
    hours.oddFooter.center.text = f"{year}년 {month}월 근무시간"

    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()
