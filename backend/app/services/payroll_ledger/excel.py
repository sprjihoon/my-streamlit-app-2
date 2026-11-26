"""급여대장을 엑셀 서식으로 읽고 적는다."""
from __future__ import annotations

from datetime import datetime, date
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
def _blank_line() -> dict:
    return {
        "user_id": 0,
        "contract_id": None,
        "seq": 0,
        "employee_name": "",
        "affiliation": "",
        "hire_date": "",
        "resident_id": "",
        "work_days": "",
        "base_hours": 0,
        "overtime_hours": 0,
        "holiday_hours": 0,
        "night_hours": 0,
        "extra_hours": 0,
        "hourly": 0,
        "base_pay": 0,
        "overtime_pay": 0,
        "holiday_pay": 0,
        "night_pay": 0,
        "position_allowance": 0,
        "vehicle_allowance": 0,
        "meal_allowance": 0,
        "annual_leave_pay": 0,
        "special_pay": 0,
        "incentive_pay": 0,
        "attendance_deduction": 0,
        "settlement_pay": 0,
        "bonus_pay": 0,
        "income_tax": 0,
        "local_tax": 0,
        "pension": 0,
        "health": 0,
        "care": 0,
        "employment": 0,
        "year_end_tax": 0,
        "insurance_adjust": 0,
        "prepaid": 0,
        "gross_pay": 0,
        "deduction_total": 0,
        "net_pay": 0,
    }


def _number(value, default=0):
    if value is None or value == "":
        return default
    if isinstance(value, str):
        text = value.replace(",", "").strip()
        if not text:
            return default
        return float(text)
    return float(value)


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def parse_payroll_xlsx(content: bytes) -> dict:
    """급여대장 시트의 계산된 값을 그대로 읽는다."""
    book = load_workbook(BytesIO(content), data_only=True)
    if "급여대장" not in book.sheetnames:
        raise ValueError("급여대장 시트가 없습니다.")
    ws = book["급여대장"]
    header_row = 5
    for row in range(1, 16):
        if _text(ws.cell(row, 2).value) == "성명":
            header_row = row
            break
    start = header_row + 3
    title = ws["A1"].value
    if isinstance(title, datetime):
        year, month = title.year, title.month
    else:
        text = _text(title)
        parts = text.replace(".", "-").split("-")
        if len(parts) < 2 or not parts[0].isdigit():
            raise ValueError("급여대장의 날짜를 읽지 못했습니다.")
        year, month = int(parts[0]), int(parts[1])
    lines = []
    row = start
    while row <= ws.max_row:
        marker = _text(ws.cell(row, 1).value)
        name = _text(ws.cell(row, 2).value)
        if marker == "합계" or not name:
            break
        line = _blank_line()
        line.update({
            "seq": int(_number(ws.cell(row, 1).value, len(lines) + 1)),
            "employee_name": name,
            "work_days": _text(ws.cell(row, 3).value),
            "base_hours": _number(ws.cell(row, 4).value),
            "overtime_hours": _number(ws.cell(row, 5).value),
            "base_pay": int(round(_number(ws.cell(row, 6).value))),
            "overtime_pay": int(round(_number(ws.cell(row, 7).value))),
            "holiday_pay": int(round(_number(ws.cell(row, 8).value))),
            "annual_leave_pay": int(round(_number(ws.cell(row, 9).value))),
            "gross_pay": int(round(_number(ws.cell(row, 10).value))),
            "income_tax": int(round(_number(ws.cell(row, 11).value))),
            "pension": int(round(_number(ws.cell(row, 12).value))),
            "year_end_tax": int(round(_number(ws.cell(row, 13).value))),
            "deduction_total": int(round(_number(ws.cell(row, 14).value))),
            "net_pay": int(round(_number(ws.cell(row, 15).value))),
            "affiliation": _text(ws.cell(row + 1, 1).value),
            "hire_date": _text(ws.cell(row + 1, 2).value),
            "holiday_hours": _number(ws.cell(row + 1, 3).value),
            "night_hours": _number(ws.cell(row + 1, 4).value),
            "hourly": _number(ws.cell(row + 1, 5).value),
            "night_pay": int(round(_number(ws.cell(row + 1, 6).value))),
            "special_pay": int(round(_number(ws.cell(row + 1, 7).value))),
            "incentive_pay": int(round(_number(ws.cell(row + 1, 8).value))),
            "attendance_deduction": int(round(_number(ws.cell(row + 1, 9).value))),
            "local_tax": int(round(_number(ws.cell(row + 1, 11).value))),
            "employment": int(round(_number(ws.cell(row + 1, 12).value))),
            "insurance_adjust": int(round(_number(ws.cell(row + 1, 13).value))),
            "resident_id": _text(ws.cell(row + 2, 1).value),
            "extra_hours": _number(ws.cell(row + 2, 3).value),
            "vehicle_allowance": int(round(_number(ws.cell(row + 2, 6).value))),
            "meal_allowance": int(round(_number(ws.cell(row + 2, 7).value))),
            "settlement_pay": int(round(_number(ws.cell(row + 2, 8).value))),
            "bonus_pay": int(round(_number(ws.cell(row + 2, 9).value))),
            "health": int(round(_number(ws.cell(row + 2, 11).value))),
            "care": int(round(_number(ws.cell(row + 2, 12).value))),
            "prepaid": int(round(_number(ws.cell(row + 2, 13).value))),
        })
        lines.append(line)
        row += 3
    if not lines:
        raise ValueError("급여대장에서 직원을 찾지 못했습니다.")
    return {
        "year": year,
        "month": month,
        "company_name": _text(ws["L3"].value) or "틸리언",
        "period_label": _text(ws["B3"].value),
        "lines": lines,
    }


def render_payroll_xlsx(ledger: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "급여대장"

    thin = Border(
        left=Side(style="thin", color="BFCBD9"),
        right=Side(style="thin", color="BFCBD9"),
        top=Side(style="thin", color="BFCBD9"),
        bottom=Side(style="thin", color="BFCBD9"),
    )
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    header_fill = PatternFill("solid", fgColor="E8EEF7")
    total_fill = PatternFill("solid", fgColor="F4F7FB")
    title_font = Font(name="맑은 고딕", size=16, bold=True)
    font = Font(name="맑은 고딕", size=9)
    bold = Font(name="맑은 고딕", size=9, bold=True)

    ws.merge_cells("A1:G2")
    ws.merge_cells("H1:O2")
    ws["A1"] = f"{ledger['year']}-{ledger['month']:02d}-01"
    ws["H1"] = "급여대장"
    ws["A1"].font = title_font
    ws["H1"].font = title_font
    ws["A1"].alignment = center
    ws["H1"].alignment = center

    ws["A3"] = "임금산정기간"
    ws.merge_cells("B3:C3")
    ws["B3"] = ledger["period_label"]
    ws.merge_cells("L3:O3")
    ws["L3"] = ledger["company_name"]
    for cell in ("A3", "B3", "L3"):
        ws[cell].font = bold
        ws[cell].alignment = center

    headers = {
        "A4": "인적사항",
        "C4": "임금계산기초사항",
        "F4": "지급내역",
        "J4": "총급여액",
        "K4": "공제내역",
        "O4": "차감수령액",
        "A5": "순번",
        "B5": "성명",
        "C5": "근로일수",
        "D5": "기본근로시간수",
        "E5": "연장근로시간수",
        "F5": "기본급",
        "G5": "시간외근로수당",
        "H5": "휴일수당",
        "I5": "연차수당",
        "K5": "소득세",
        "L5": "국민연금",
        "M5": "연말정산환수",
        "N5": "공제합계",
        "A6": "소속",
        "B6": "입사일",
        "C6": "휴일근로시간수",
        "D6": "야간근로시간수",
        "E6": "시급",
        "F6": "야간근로수당",
        "G6": "특근수당",
        "H6": "인센티브",
        "I6": "근태공제",
        "K6": "주민세",
        "L6": "고용보험",
        "M6": "보험료정산",
        "A7": "주민번호",
        "C7": "가산근로산정시간",
        "D7": "추가부양가족수",
        "F7": "차량지원금",
        "G7": "식대",
        "H7": "정산수당",
        "I7": "직책·상여",
        "K7": "건강보험",
        "L7": "장기요양",
        "M7": "기지급액",
    }
    for coord, value in headers.items():
        ws[coord] = value
    merges = ("A4:B4", "C4:E4", "F4:I4", "K4:N4", "A7:B7", "J4:J7", "O4:O7")
    for ref in merges:
        ws.merge_cells(ref)
    for row in ws.iter_rows(min_row=4, max_row=7, min_col=1, max_col=15):
        for cell in row:
            cell.font = bold
            cell.fill = header_fill
            cell.alignment = center
            cell.border = thin

    money_cols = set("FGHIJKLMNO")
    start = 8
    for index, line in enumerate(ledger["lines"]):
        row = start + index * 3
        values = {
            row: {
                "A": line["seq"],
                "B": line["employee_name"],
                "C": line["work_days"],
                "D": line["base_hours"],
                "E": line["overtime_hours"],
                "F": line["base_pay"],
                "G": line["overtime_pay"],
                "H": line["holiday_pay"],
                "I": line["annual_leave_pay"],
                "J": line["gross_pay"],
                "K": line["income_tax"],
                "L": line["pension"],
                "M": line["year_end_tax"],
                "N": line["deduction_total"],
                "O": line["net_pay"],
            },
            row + 1: {
                "A": line["affiliation"],
                "B": line["hire_date"],
                "C": line["holiday_hours"],
                "D": line["night_hours"],
                "E": line["hourly"],
                "F": line["night_pay"],
                "G": line["special_pay"],
                "H": line["incentive_pay"],
                "I": line["attendance_deduction"],
                "K": line["local_tax"],
                "L": line["employment"],
                "M": line["insurance_adjust"],
            },
            row + 2: {
                "A": line["resident_id"],
                "C": line["extra_hours"],
                "D": 0,
                "F": line["vehicle_allowance"],
                "G": line["meal_allowance"],
                "H": line["settlement_pay"],
                "I": line["position_allowance"] + line["bonus_pay"],
                "K": line["health"],
                "L": line["care"],
                "M": line["prepaid"],
            },
        }
        for row_no, cols in values.items():
            for col, value in cols.items():
                cell = ws[f"{col}{row_no}"]
                cell.value = value
                cell.font = font
                cell.alignment = center if col != "A" or row_no == row else left
                cell.border = thin
                if col in money_cols and isinstance(value, (int, float)):
                    cell.number_format = "#,##0"
        for col in "ABCDEFGHIJKLMNO":
            for offset in range(3):
                cell = ws[f"{col}{row + offset}"]
                cell.border = thin
                cell.font = font
        ws.merge_cells(start_row=row, start_column=10, end_row=row + 2, end_column=10)
        ws.merge_cells(start_row=row, start_column=14, end_row=row + 2, end_column=14)
        ws.merge_cells(start_row=row, start_column=15, end_row=row + 2, end_column=15)

    total_row = start + len(ledger["lines"]) * 3
    ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row + 2, end_column=2)
    ws[f"A{total_row}"] = "합계"
    totals = ledger["totals"]
    total_values = {
        total_row: {
            "F": totals["base_pay"],
            "G": totals["overtime_pay"],
            "H": totals["holiday_pay"],
            "I": totals["annual_leave_pay"],
            "J": totals["gross_pay"],
            "K": totals["income_tax"],
            "L": totals["pension"],
            "M": totals["year_end_tax"],
            "N": totals["deduction_total"],
            "O": totals["net_pay"],
        },
        total_row + 1: {
            "F": totals["night_pay"],
            "G": totals["special_pay"],
            "H": totals["incentive_pay"],
            "I": totals["attendance_deduction"],
            "K": totals["local_tax"],
            "L": totals["employment"],
            "M": totals["insurance_adjust"],
        },
        total_row + 2: {
            "F": totals["vehicle_allowance"],
            "G": totals["meal_allowance"],
            "H": totals["settlement_pay"],
            "I": totals["position_allowance"] + totals["bonus_pay"],
            "K": totals["health"],
            "L": totals["care"],
            "M": totals["prepaid"],
        },
    }
    for row_no, cols in total_values.items():
        for col, value in cols.items():
            cell = ws[f"{col}{row_no}"]
            cell.value = value
            cell.number_format = "#,##0"
    for row_no in range(total_row, total_row + 3):
        for col in range(1, 16):
            cell = ws.cell(row_no, col)
            cell.font = bold
            cell.fill = total_fill
            cell.alignment = center
            cell.border = thin
    ws.merge_cells(start_row=total_row, start_column=10, end_row=total_row + 2, end_column=10)
    ws.merge_cells(start_row=total_row, start_column=14, end_row=total_row + 2, end_column=14)
    ws.merge_cells(start_row=total_row, start_column=15, end_row=total_row + 2, end_column=15)

    widths = {
        "A": 16, "B": 14, "C": 14, "D": 14, "E": 14,
        "F": 14, "G": 14, "H": 12, "I": 12, "J": 14,
        "K": 12, "L": 12, "M": 12, "N": 14, "O": 14,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.row_dimensions[1].height = 22
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.print_title_rows = "1:7"
    ws.page_setup.horizontalCentered = True
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddFooter.center.text = "근로계약 급여를 기준으로 만든 급여대장"
    last = total_row + 2
    ws.print_area = f"A1:O{last}"
    ws.freeze_panes = "A8"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
