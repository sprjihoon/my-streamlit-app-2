"""노무사 전달 일용근로대장. 제출 서식과 같은 칸에 신고 알바만 적는다."""
from __future__ import annotations

from copy import copy
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "assets" / "part_time_ledger_template.xlsx"
_BLOCK_HEIGHT = 19
_FIRST_BLOCK = 7
_GONG_SLOTS = (
    {"name": "O", "days": ("O", "S", "T", "Y", "AA"), "avg": "V"},
    {"name": "AE", "days": ("AE", "AF", "AH", "AM", "AP"), "avg": "AI"},
    {"name": "AT", "days": ("AT", "AU", "AZ", "BF", "BH"), "avg": "BB"},
    {"name": "BM", "days": ("BM", "BQ", "BW", "CB", "CF"), "avg": "BY"},
)


def _won(amount: int) -> str:
    return f"{int(amount):,} 원 "


def _hours_label(value: float) -> str:
    rounded = round(float(value), 2)
    text = str(int(rounded)) if rounded == int(rounded) else f"{rounded:g}"
    return f"{text}시간"


def _slot_count(needed: int) -> int:
    count = 8
    while count < needed:
        count += 2
    return count


def _copy_block(ws, src_start: int, dst_start: int) -> None:
    for offset in range(_BLOCK_HEIGHT):
        src_row = src_start + offset
        dst_row = dst_start + offset
        for col in range(1, 13):
            src = ws.cell(src_row, col)
            dst = ws.cell(dst_row, col)
            dst.value = src.value
            if src.has_style:
                dst.font = copy(src.font)
                dst.border = copy(src.border)
                dst.fill = copy(src.fill)
                dst.number_format = src.number_format
                dst.alignment = copy(src.alignment)
        if ws.row_dimensions[src_row].height:
            ws.row_dimensions[dst_row].height = ws.row_dimensions[src_row].height
    for origin in (2, 8):
        for offset in range(5):
            ws.merge_cells(
                start_row=dst_start + offset,
                start_column=origin,
                end_row=dst_start + offset,
                end_column=origin + 4,
            )
    for col in (1, 7):
        ws.merge_cells(
            start_row=dst_start + 5,
            start_column=col,
            end_row=dst_start + 18,
            end_column=col,
        )


def _ensure_slots(ws, needed: int) -> list[tuple[int, int]]:
    blocks = _slot_count(needed) // 2
    last_ready = 4
    src_start = _FIRST_BLOCK + (last_ready - 1) * _BLOCK_HEIGHT
    for index in range(last_ready, blocks):
        _copy_block(ws, src_start, _FIRST_BLOCK + index * _BLOCK_HEIGHT)
    slots = []
    for index in range(blocks):
        start = _FIRST_BLOCK + index * _BLOCK_HEIGHT
        slots.append((start, 2))
        slots.append((start, 8))
    return slots


def _write_hours(ws, start: int, origin: int, hours_by_day: dict) -> None:
    for day, hours in hours_by_day.items():
        if not hours:
            continue
        group = (int(day) - 1) // 5
        index = (int(day) - 1) % 5
        cell = ws.cell(start + 6 + group * 2, origin + index, hours)
        cell.number_format = "0.##"


def _write_ledger_person(ws, start: int, origin: int, person: dict) -> None:
    ws.cell(start, origin, person["name"])
    ws.cell(start + 1, origin, person["resident_id"])
    ws.cell(start + 2, origin, f"{person['work_days']}일")
    if person["average_hours"]:
        ws.cell(start + 3, origin, _hours_label(person["average_hours"]))
    pay = ws.cell(start + 4, origin, int(person["taxable_pay"]))
    pay.number_format = '_-* #,##0_-;\\-* #,##0_-;_-* "-"_-;_-@_-'
    _write_hours(ws, start, origin, person.get("hours_by_day") or {})


def _mark_days(ws, slot: dict, hours_by_day: dict) -> None:
    for day, hours in hours_by_day.items():
        if not hours:
            continue
        group = (int(day) - 1) // 5
        index = (int(day) - 1) % 5
        ws[f"{slot['days'][index]}{26 + group * 2 + 1}"] = "o"


def _write_gong_person(ws, slot: dict, person: dict, month: int) -> None:
    column = slot["name"]
    ws[f"{column}21"] = person["name"]
    ws[f"{column}22"] = person["resident_id"]
    ws[f"{column}23"] = "한국"
    ws[f"{column}25"] = "029"
    ws[f"{column}40"] = f"{person['work_days']} 일 "
    average = _hours_label(person["average_hours"]).removesuffix("시간")
    ws[f"{slot['avg']}40"] = f"{average} 시간 "
    ws[f"{column}41"] = f"{person['work_days']} 일 "
    ws[f"{column}42"] = _won(person["taxable_pay"])
    ws[f"{column}43"] = _won(person["taxable_pay"] + person["nontaxable_pay"])
    ws[f"{column}44"] = 1
    ws[f"{column}47"] = f"{month}월 "
    ws[f"{column}48"] = _won(person["taxable_pay"])
    ws[f"{column}49"] = _won(person["nontaxable_pay"])
    ws[f"{column}50"] = _won(person["income_tax"])
    ws[f"{column}51"] = _won(person["local_tax"])
    _mark_days(ws, slot, person.get("hours_by_day") or {})


def _usable_business_number(value: str) -> str:
    text = (value or "").strip()
    digits = text.replace("-", "")
    if not digits or set(digits) <= {"0"}:
        return ""
    return text


def render_part_time_xlsx(year: int, month: int, company: dict, people: list[dict]) -> bytes:
    book = load_workbook(TEMPLATE_PATH)
    sheet = book["양식"]
    sheet.title = f"{month}월"
    sheet["A1"] = f"{year}년 {month}월 일용근로대장"
    if company.get("company_name"):
        sheet["B3"] = company["company_name"]
    business_number = _usable_business_number(company.get("business_number") or "")
    if business_number:
        sheet["B4"] = business_number

    ordered = sorted(people, key=lambda person: (person.get("name") or "", person.get("worker_id") or 0))
    slots = _ensure_slots(sheet, len(ordered))
    for slot, person in zip(slots, ordered):
        _write_ledger_person(sheet, slot[0], slot[1], person)

    gong = book["공단"]
    pages = [gong]
    page_count = max(1, (len(ordered) + 3) // 4)
    for index in range(1, page_count):
        copied = book.copy_worksheet(gong)
        copied.title = f"공단{index + 1}"
        pages.append(copied)
    for index, person in enumerate(ordered):
        _write_gong_person(pages[index // 4], _GONG_SLOTS[index % 4], person, month)

    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()
