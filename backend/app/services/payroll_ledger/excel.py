"""급여대장을 엑셀 서식으로 읽고 적는다."""
from __future__ import annotations

import calendar
from copy import copy
from datetime import datetime, date
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "assets" / "payroll_ledger_template.xlsx"
SKIP_SHEETS = {"급여대장", "급여명세서", "2023년 조견표", "급여명세서 수령 확인"}


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
        "industrial": 0,
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


def _formula(cell) -> bool:
    return isinstance(cell.value, str) and cell.value.startswith("=")


def _fill_cell(cell, value) -> None:
    if _formula(cell):
        return
    cell.value = value


def _sheet_ref(sheet_name: str, coord: str) -> str:
    quoted = sheet_name.replace("'", "''")
    return f"='{quoted}'!{coord}"


def _safe_sheet_title(affiliation: str, name: str, taken: set[str]) -> str:
    base = " ".join(part for part in ((affiliation or "").strip(), (name or "").strip()) if part) or "직원"
    base = "".join(ch for ch in base if ch not in r":\/?*[]")[:31] or "직원"
    title = base
    index = 2
    while title in taken or title in SKIP_SHEETS:
        suffix = f" {index}"
        title = f"{base[:31 - len(suffix)]}{suffix}"
        index += 1
    return title


def _person_sheets(book) -> dict[str, object]:
    found = {}
    for sheet_name in book.sheetnames:
        if sheet_name in SKIP_SHEETS:
            continue
        ws = book[sheet_name]
        name = _text(ws["B3"].value)
        if name:
            found[name] = ws
    return found


def _fill_person_sheet(ws, line: dict, company: str) -> None:
    _fill_cell(ws["B3"], (line.get("employee_name") or "").strip())
    if company:
        _fill_cell(ws["D3"], company)
    if line.get("affiliation"):
        _fill_cell(ws["B5"], line["affiliation"])
    if line.get("resident_id"):
        _fill_cell(ws["B6"], line["resident_id"])
    hire = line.get("hire_date") or ""
    if hire and not _formula(ws["B9"]):
        try:
            ws["B9"] = datetime.strptime(str(hire)[:10], "%Y-%m-%d")
        except ValueError:
            ws["B9"] = hire
    _fill_cell(ws["H20"], int(line.get("net_pay") or 0))
    _fill_cell(ws["D20"], int(line.get("vehicle_allowance") or 0))
    _fill_cell(ws["E20"], int(line.get("meal_allowance") or 0))
    _fill_cell(ws["E24"], int(line.get("income_tax") or 0))
    _fill_cell(ws["B24"], int(line.get("pension") or 0))
    _fill_cell(ws["B13"], line.get("base_hours") or 0)
    _fill_cell(ws["C13"], line.get("overtime_hours") or 0)
    _fill_cell(ws["D13"], line.get("holiday_hours") or 0)
    _fill_cell(ws["E13"], line.get("night_hours") or 0)
    _fill_cell(ws["F13"], line.get("work_days") or "만근")
    _fill_cell(ws["I33"], int(line.get("position_allowance") or 0))
    _fill_cell(ws["I39"], int(line.get("annual_leave_pay") or 0))
    _fill_cell(ws["H40"], int(line.get("incentive_pay") or 0))
    _fill_cell(ws["G33"], int(line.get("special_pay") or 0))
    _fill_cell(ws["M39"], int(line.get("year_end_tax") or 0))
    _fill_cell(ws["M40"], int(line.get("insurance_adjust") or 0))
    _fill_cell(ws["M41"], int(line.get("prepaid") or 0))
    if not _formula(ws["I40"]):
        _fill_cell(ws["I40"], int(line.get("attendance_deduction") or 0))
    elif not _formula(ws["H33"]):
        _fill_cell(ws["H33"], int(line.get("attendance_deduction") or 0))
    _fill_cell(ws["H41"], int(line.get("bonus_pay") or 0) or int(line.get("settlement_pay") or 0))


def _apply_style(cell, snapshot: dict) -> None:
    cell.font = copy(snapshot["font"])
    cell.border = copy(snapshot["border"])
    cell.fill = copy(snapshot["fill"])
    cell.alignment = copy(snapshot["alignment"])
    cell.number_format = snapshot["number_format"]


def _row_style(ws, row: int) -> list[dict]:
    return [
        {
            "font": copy(ws.cell(row, col).font),
            "border": copy(ws.cell(row, col).border),
            "fill": copy(ws.cell(row, col).fill),
            "alignment": copy(ws.cell(row, col).alignment),
            "number_format": ws.cell(row, col).number_format,
        }
        for col in range(1, 16)
    ]


def _unmerge_from(ws, min_row: int) -> None:
    for ref in [str(rng) for rng in ws.merged_cells.ranges if rng.min_row >= min_row]:
        ws.unmerge_cells(ref)


def _write_person_block(ws, start: int, sheet_name: str, seq_formula, styles: list[list[dict]]) -> None:
    for offset, src_row in enumerate((39, 40, 41)):
        row = start + offset
        for col in range(1, 16):
            cell = ws.cell(row, col)
            _apply_style(cell, styles[offset][col - 1])
            letter = cell.column_letter
            if offset == 0 and letter == "A":
                cell.value = seq_formula
            elif letter in "JNO" and offset > 0:
                cell.value = None
            else:
                cell.value = _sheet_ref(sheet_name, f"{letter}{src_row}")
        ws.cell(start, 10).value = _sheet_ref(sheet_name, "J39")
        ws.cell(start, 14).value = _sheet_ref(sheet_name, "N39")
        ws.cell(start, 15).value = _sheet_ref(sheet_name, "O39")
    ws.merge_cells(start_row=start, start_column=10, end_row=start + 2, end_column=10)
    ws.merge_cells(start_row=start, start_column=14, end_row=start + 2, end_column=14)
    ws.merge_cells(start_row=start, start_column=15, end_row=start + 2, end_column=15)
    ws.merge_cells(start_row=start + 2, start_column=1, end_row=start + 2, end_column=2)


def _write_total_block(ws, start: int, person_starts: list[int], styles: list[list[dict]]) -> None:
    for offset in range(3):
        row = start + offset
        for col in range(1, 16):
            cell = ws.cell(row, col)
            _apply_style(cell, styles[offset][col - 1])
            cell.value = None
        if offset == 0:
            ws.cell(row, 1).value = "합계"
        for col in "FGHIJKLM":
            rows = [person + offset for person in person_starts]
            if rows:
                ws[f"{col}{row}"] = "=" + "+".join(f"{col}{r}" for r in rows)
        if offset == 0:
            ws.cell(row, 10).value = f"=SUM(F{start}:I{start + 2})"
            ws.cell(row, 14).value = f"=SUM(K{start}:M{start + 2})"
            ws.cell(row, 15).value = f"=J{start}-N{start}"
    ws.merge_cells(start_row=start, start_column=1, end_row=start + 2, end_column=2)
    ws.merge_cells(start_row=start, start_column=10, end_row=start + 2, end_column=10)
    ws.merge_cells(start_row=start, start_column=14, end_row=start + 2, end_column=14)
    ws.merge_cells(start_row=start, start_column=15, end_row=start + 2, end_column=15)


def _rewrite_summary(ws, sheet_names: list[str]) -> None:
    person_styles = [_row_style(ws, row) for row in (8, 9, 10)]
    total_styles = [_row_style(ws, row) for row in (32, 33, 34)]
    _unmerge_from(ws, 8)
    for row in range(8, 80):
        for col in range(1, 16):
            ws.cell(row, col).value = None
    starts = []
    for index, sheet_name in enumerate(sheet_names):
        start = 8 + index * 3
        starts.append(start)
        seq = 1 if index == 0 else f"=A{starts[index - 1]}+1"
        _write_person_block(ws, start, sheet_name, seq, person_styles)
    reserved = max(8, len(sheet_names))
    total_row = 8 + reserved * 3
    _write_total_block(ws, total_row, starts, total_styles)
    last = total_row + 2
    ws.print_area = f"A1:O{last}"
    for row in range(8, last + 1):
        ws.row_dimensions[row].height = 18


def _fill_receipt_names(ws, names: list[str]) -> None:
    for index in range(20):
        cell = ws.cell(4 + index, 2)
        cell.value = names[index] if index < len(names) else None


def _extend_statement_slots(ws, count: int) -> None:
    if count <= 8:
        return
    for index in range(8, count):
        ledger_row = 8 + index * 3
        src = 1 + (index - 1) * 3
        dest = 1 + index * 3
        for offset in range(3):
            for col in range(31, 45):
                sample = ws.cell(src + offset, col).value
                if not isinstance(sample, str) or "급여대장!" not in sample:
                    continue
                old_row = 8 + (index - 1) * 3 + offset
                ws.cell(dest + offset, col).value = sample.replace(f"!A{old_row}", f"!A{ledger_row + offset}").replace(
                    f"!B{old_row}", f"!B{ledger_row + offset}"
                ).replace(f"!C{old_row}", f"!C{ledger_row + offset}").replace(
                    f"!D{old_row}", f"!D{ledger_row + offset}"
                ).replace(f"!E{old_row}", f"!E{ledger_row + offset}").replace(
                    f"!F{old_row}", f"!F{ledger_row + offset}"
                ).replace(f"!G{old_row}", f"!G{ledger_row + offset}").replace(
                    f"!H{old_row}", f"!H{ledger_row + offset}"
                ).replace(f"!I{old_row}", f"!I{ledger_row + offset}").replace(
                    f"!J{old_row}", f"!J{ledger_row + offset}"
                ).replace(f"!K{old_row}", f"!K{ledger_row + offset}").replace(
                    f"!L{old_row}", f"!L{ledger_row + offset}"
                ).replace(f"!M{old_row}", f"!M{ledger_row + offset}").replace(
                    f"!N{old_row}", f"!N{ledger_row + offset}"
                )


def fill_official_xlsx(ledger: dict) -> bytes:
    """10월 급여대장 엑셀 양식에 그달 인원·금액을 넣어 노무사 전달용으로 만든다."""
    if not TEMPLATE_PATH.is_file():
        return render_payroll_xlsx(ledger)
    year = int(ledger["year"])
    month = int(ledger["month"])
    last = calendar.monthrange(year, month)[1]
    book = load_workbook(TEMPLATE_PATH)
    company = ledger.get("company_name") or "틸리언"
    lines = [line for line in (ledger.get("lines") or []) if (line.get("employee_name") or "").strip()]
    by_name = _person_sheets(book)
    prototype = None
    for sheet_name in book.sheetnames:
        if sheet_name not in SKIP_SHEETS:
            prototype = book[sheet_name]
            if _formula(book[sheet_name]["B24"]):
                break
    if prototype is None:
        return render_payroll_xlsx(ledger)
    used = []
    taken = set(book.sheetnames)
    for line in lines:
        name = (line.get("employee_name") or "").strip()
        ws = by_name.get(name)
        if ws is None:
            ws = book.copy_worksheet(prototype)
            title = _safe_sheet_title(line.get("affiliation") or "", name, taken)
            ws.title = title
            taken.add(title)
            by_name[name] = ws
        _fill_person_sheet(ws, line, company)
        used.append(ws.title)
    keep = set(used)
    for sheet_name in list(book.sheetnames):
        if sheet_name in SKIP_SHEETS or sheet_name in keep:
            continue
        del book[sheet_name]
    desired = used + [name for name in ("급여대장", "급여명세서", "2023년 조견표", "급여명세서 수령 확인") if name in book.sheetnames]
    for index, title in enumerate(desired):
        current = book.sheetnames.index(title)
        if current != index:
            book.move_sheet(book[title], offset=index - current)
    summary = book["급여대장"]
    summary["A1"] = datetime(year, month, 1)
    summary["B3"] = ledger.get("period_label") or f"{year}.{month:02d}.01~{year}.{month:02d}.{last:02d}"
    summary["L3"] = company
    _rewrite_summary(summary, used)
    if "급여명세서 수령 확인" in book.sheetnames:
        _fill_receipt_names(book["급여명세서 수령 확인"], [line["employee_name"].strip() for line in lines])
    if "급여명세서" in book.sheetnames:
        _extend_statement_slots(book["급여명세서"], len(used))
    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()
