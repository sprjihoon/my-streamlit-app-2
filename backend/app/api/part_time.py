"""알바 등록과 달력 근무시간. 세금은 근무 기간과 한 주 시간으로 계산한다."""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.app.api.logs import add_log
from backend.app.services.part_time.calc import choose_pay_regime, minimum_wage, settle_part_time_pay, weekly_holiday_pay
from backend.app.services.part_time.calendar_actions import normalize_clock, shift_times
from backend.app.services.part_time.excel import render_part_time_xlsx
from backend.app.services.part_time.slip_pdf import render_part_time_slips_pdf
from backend.app.services.part_time.october_2026 import OCTOBER_2026_START, october_2026_people
from logic.db import get_connection

router = APIRouter(prefix="/part-time", tags=["part-time"])


def ensure_part_time_tables() -> None:
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS part_time_workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                resident_id TEXT NOT NULL,
                reported INTEGER NOT NULL DEFAULT 1,
                hourly_wage INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS part_time_hours (
                worker_id INTEGER NOT NULL,
                work_date TEXT NOT NULL,
                hours REAL NOT NULL,
                start_time TEXT,
                updated_at TEXT,
                PRIMARY KEY (worker_id, work_date)
            )
            """
        )
        columns = [row[1] for row in con.execute("PRAGMA table_info(part_time_hours)").fetchall()]
        if "start_time" not in columns:
            con.execute("ALTER TABLE part_time_hours ADD COLUMN start_time TEXT")
        worker_columns = [row[1] for row in con.execute("PRAGMA table_info(part_time_workers)").fetchall()]
        if "phone" not in worker_columns:
            con.execute("ALTER TABLE part_time_workers ADD COLUMN phone TEXT")
        if "bank_name" not in worker_columns:
            con.execute("ALTER TABLE part_time_workers ADD COLUMN bank_name TEXT")
        if "account_number" not in worker_columns:
            con.execute("ALTER TABLE part_time_workers ADD COLUMN account_number TEXT")
        if "exclude_from_excel" not in worker_columns:
            con.execute("ALTER TABLE part_time_workers ADD COLUMN exclude_from_excel INTEGER NOT NULL DEFAULT 0")
        _seed_october_2026(con)
        _fill_worker_profiles(con)
        con.commit()


def _seed_october_2026(con) -> None:
    taken = con.execute(
        """
        SELECT 1 FROM part_time_hours
        WHERE work_date >= '2026-10-01' AND work_date <= '2026-10-31'
        LIMIT 1
        """
    ).fetchone()
    if taken:
        return
    stamp = _now()
    wage = minimum_wage(2026)
    for person in october_2026_people():
        resident_id = _normalize_rrn(person["resident_id"])
        row = con.execute(
            "SELECT id FROM part_time_workers WHERE resident_id = ? ORDER BY active DESC, id LIMIT 1",
            (resident_id,),
        ).fetchone()
        if row:
            worker_id = row[0]
        else:
            cur = con.execute(
                """
                INSERT INTO part_time_workers
                    (name, resident_id, reported, hourly_wage, active, phone, bank_name, account_number, created_at, updated_at)
                VALUES (?, ?, 1, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    person["name"],
                    resident_id,
                    wage,
                    _phone(person.get("phone") or ""),
                    (person.get("bank_name") or "").strip(),
                    str(person.get("account_number") or "").strip(),
                    stamp,
                    stamp,
                ),
            )
            worker_id = cur.lastrowid
        for day, hours in person["days"].items():
            con.execute(
                """
                INSERT INTO part_time_hours (worker_id, work_date, hours, start_time, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(worker_id, work_date) DO UPDATE SET
                    hours = excluded.hours,
                    start_time = excluded.start_time,
                    updated_at = excluded.updated_at
                """,
                (worker_id, f"2026-10-{int(day):02d}", float(hours), OCTOBER_2026_START, stamp),
            )


def _fill_worker_profiles(con) -> None:
    """엑셀에 있는 알바는 만들고, 주민번호·연락처·은행·계좌가 비어 있으면 채운다. 적어 둔 값은 덮지 않는다."""
    stamp = _now()
    wage = minimum_wage(2026)
    for person in october_2026_people():
        try:
            resident_id = _normalize_rrn(person["resident_id"])
        except HTTPException:
            continue
        name = (person.get("name") or "").strip()
        phone = _phone(person.get("phone") or "")
        bank_name = (person.get("bank_name") or "").strip()
        account_number = str(person.get("account_number") or "").strip()
        row = con.execute(
            """
            SELECT id, name, resident_id, phone, bank_name, account_number
            FROM part_time_workers
            WHERE resident_id = ?
            ORDER BY active DESC, id LIMIT 1
            """,
            (resident_id,),
        ).fetchone()
        matched_name = False
        if not row and name:
            row = con.execute(
                """
                SELECT id, name, resident_id, phone, bank_name, account_number
                FROM part_time_workers
                WHERE TRIM(name) = ?
                ORDER BY active DESC, id LIMIT 1
                """,
                (name,),
            ).fetchone()
            matched_name = bool(row)
        if not row:
            con.execute(
                """
                INSERT INTO part_time_workers
                    (name, resident_id, reported, hourly_wage, active, phone, bank_name, account_number, created_at, updated_at)
                VALUES (?, ?, 1, ?, 1, ?, ?, ?, ?, ?)
                """,
                (name, resident_id, wage, phone, bank_name, account_number, stamp, stamp),
            )
            continue
        new_name = (row[1] or "").strip() or name
        current_digits = re.sub(r"\D", "", row[2] or "")
        new_resident = row[2]
        if len(current_digits) != 13:
            new_resident = resident_id
        elif matched_name and (row[2] or "") != resident_id:
            taken = con.execute(
                "SELECT id FROM part_time_workers WHERE resident_id = ? AND id != ?",
                (resident_id, row[0]),
            ).fetchone()
            if not taken:
                new_resident = resident_id
        new_phone = (row[3] or "").strip() or phone
        new_bank = (row[4] or "").strip() or bank_name
        new_account = (row[5] or "").strip() or account_number
        if (
            new_name == (row[1] or "").strip()
            and new_resident == (row[2] or "")
            and new_phone == (row[3] or "").strip()
            and new_bank == (row[4] or "").strip()
            and new_account == (row[5] or "").strip()
        ):
            continue
        con.execute(
            """
            UPDATE part_time_workers
            SET name = ?, resident_id = ?, phone = ?, bank_name = ?, account_number = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_name, new_resident, new_phone, new_bank, new_account, stamp, row[0]),
        )


class WorkerIn(BaseModel):
    name: str
    resident_id: str
    reported: bool = True
    hourly_wage: int | None = None
    phone: str = ""
    bank_name: str = ""
    account_number: str = ""
    exclude_from_excel: bool = False


class WorkerPatch(BaseModel):
    name: str | None = None
    resident_id: str | None = None
    reported: bool | None = None
    hourly_wage: int | None = None
    active: bool | None = None
    phone: str | None = None
    bank_name: str | None = None
    account_number: str | None = None
    exclude_from_excel: bool | None = None


class HourIn(BaseModel):
    worker_id: int
    hours: float = Field(ge=0, le=24)
    start_time: str = ""


class DayIn(BaseModel):
    work_date: str
    entries: list[HourIn]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _admin(token: str) -> dict:
    from backend.app.api.auth import ensure_users_table

    ensure_users_table()
    ensure_part_time_tables()
    with get_connection() as con:
        row = con.execute(
            """
            SELECT u.user_id, u.nickname, u.is_admin, u.can_manage_part_time
            FROM sessions s
            JOIN users u ON u.user_id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    if not row[2] and not row[3]:
        raise HTTPException(status_code=403, detail="아르바이트 관리 권한이 필요합니다.")
    return {"user_id": row[0], "nickname": row[1] or ""}


def _mask_rrn(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 7:
        return ""
    return f"{digits[:6]}-{digits[6]}******"


def _normalize_rrn(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 13:
        raise HTTPException(status_code=400, detail="주민번호는 13자리입니다.")
    return f"{digits[:6]}-{digits[6:]}"


def _wage(value: int | None, year: int) -> int:
    amount = minimum_wage(year) if value is None else int(value)
    if amount < 1:
        raise HTTPException(status_code=400, detail="시급은 1원 이상이어야 합니다.")
    return amount


def _parse_day(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="날짜는 YYYY-MM-DD 형식입니다.") from exc


def _phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return ""
    if not 9 <= len(digits) <= 11:
        raise HTTPException(status_code=400, detail="전화번호는 9자리에서 11자리입니다.")
    if digits.startswith("02"):
        middle = 5 if len(digits) == 9 else 6
        return f"02-{digits[2:middle]}-{digits[middle:]}"
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"


def _bank_name(value: str | None) -> str:
    return (value or "").strip()[:40]


def _account_number(value: str | None) -> str:
    text = str(value or "").strip().replace(" ", "")
    if not text:
        return ""
    cleaned = re.sub(r"[^\d\-]", "", text)
    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        raise HTTPException(status_code=400, detail="계좌번호를 확인해 주세요.")
    if len(digits) > 20:
        raise HTTPException(status_code=400, detail="계좌번호가 너무 깁니다.")
    return cleaned[:40]


_WORKER_COLS = "id, name, resident_id, reported, hourly_wage, active, phone, bank_name, account_number, exclude_from_excel"


def _public_worker(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "resident_id": _mask_rrn(row[2]),
        "reported": bool(row[3]),
        "hourly_wage": int(row[4]),
        "active": bool(row[5]),
        "phone": row[6] or "",
        "bank_name": row[7] or "",
        "account_number": row[8] or "",
        "exclude_from_excel": bool(row[9]),
    }


def _load_workers() -> list[dict]:
    with get_connection() as con:
        rows = con.execute(
            f"""
            SELECT {_WORKER_COLS}
            FROM part_time_workers
            ORDER BY active DESC, name, id
            """
        ).fetchall()
    return [_public_worker(row) for row in rows]


def _worker_row(worker_id: int):
    with get_connection() as con:
        return con.execute(
            f"SELECT {_WORKER_COLS} FROM part_time_workers WHERE id = ?",
            (worker_id,),
        ).fetchone()


@router.get("/wage-default")
def wage_default(year: int, token: str):
    _admin(token)
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="연도를 확인해 주세요.")
    return {"year": year, "hourly_wage": minimum_wage(year)}


@router.get("/workers")
def list_workers(token: str):
    _admin(token)
    return {"workers": _load_workers()}


@router.post("/workers")
def create_worker(body: WorkerIn, token: str):
    actor = _admin(token)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력하세요.")
    resident_id = _normalize_rrn(body.resident_id)
    wage = _wage(body.hourly_wage, date.today().year)
    stamp = _now()
    with get_connection() as con:
        taken = con.execute(
            "SELECT id FROM part_time_workers WHERE resident_id = ? AND active = 1",
            (resident_id,),
        ).fetchone()
        if taken:
            raise HTTPException(status_code=400, detail="같은 주민번호의 알바가 이미 등록되어 있습니다.")
        cur = con.execute(
            """
            INSERT INTO part_time_workers
                (name, resident_id, reported, hourly_wage, active, phone, bank_name, account_number, exclude_from_excel, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                resident_id,
                1 if body.reported else 0,
                wage,
                _phone(body.phone),
                _bank_name(body.bank_name),
                _account_number(body.account_number),
                1 if body.exclude_from_excel else 0,
                stamp,
                stamp,
            ),
        )
        con.commit()
        worker_id = cur.lastrowid
    add_log(
        action_type="알바 등록",
        target_type="part_time_worker",
        target_id=str(worker_id),
        target_name=name,
        user_nickname=actor["nickname"],
        details="신고" if body.reported else "미신고",
    )
    row = _worker_row(worker_id)
    return _public_worker(row)


@router.put("/workers/{worker_id}")
def update_worker(worker_id: int, body: WorkerPatch, token: str):
    actor = _admin(token)
    current = _worker_row(worker_id)
    if not current:
        raise HTTPException(status_code=404, detail="알바를 찾지 못했습니다.")
    name = body.name.strip() if body.name is not None else current[1]
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력하세요.")
    resident_id = _normalize_rrn(body.resident_id) if body.resident_id else current[2]
    reported = current[3] if body.reported is None else (1 if body.reported else 0)
    wage = _wage(body.hourly_wage, date.today().year) if body.hourly_wage is not None else int(current[4])
    active = current[5] if body.active is None else (1 if body.active else 0)
    phone = current[6] or "" if body.phone is None else _phone(body.phone)
    bank_name = current[7] or "" if body.bank_name is None else _bank_name(body.bank_name)
    account_number = current[8] or "" if body.account_number is None else _account_number(body.account_number)
    exclude_from_excel = current[9] if body.exclude_from_excel is None else (1 if body.exclude_from_excel else 0)
    if active:
        with get_connection() as con:
            taken = con.execute(
                "SELECT id FROM part_time_workers WHERE resident_id = ? AND active = 1 AND id != ?",
                (resident_id, worker_id),
            ).fetchone()
        if taken:
            raise HTTPException(status_code=400, detail="같은 주민번호의 알바가 이미 등록되어 있습니다.")
    stamp = _now()
    with get_connection() as con:
        con.execute(
            """
            UPDATE part_time_workers
            SET name = ?, resident_id = ?, reported = ?, hourly_wage = ?, active = ?, phone = ?, bank_name = ?, account_number = ?, exclude_from_excel = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, resident_id, reported, wage, active, phone, bank_name, account_number, exclude_from_excel, stamp, worker_id),
        )
        con.commit()
    add_log(
        action_type="알바 수정",
        target_type="part_time_worker",
        target_id=str(worker_id),
        target_name=name,
        user_nickname=actor["nickname"],
        details="근무" if active else "그만둠",
    )
    return _public_worker(_worker_row(worker_id))


def _month_bounds(year: int, month: int) -> tuple[date, date, date, date]:
    if month < 1 or month > 12 or year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="연월을 확인해 주세요.")
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    range_start = first - timedelta(days=(first.weekday()))
    range_end = last + timedelta(days=(6 - last.weekday()))
    return first, last, range_start, range_end


@router.get("/calendar")
def month_calendar(year: int, month: int, token: str):
    _admin(token)
    first, last, range_start, range_end = _month_bounds(year, month)
    workers = _load_workers()
    by_id = {worker["id"]: worker for worker in workers}
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT worker_id, work_date, hours, start_time
            FROM part_time_hours
            WHERE work_date >= ? AND work_date <= ?
            """,
            (range_start.isoformat(), range_end.isoformat()),
        ).fetchall()
    hours: dict[tuple[int, str], float] = {}
    days: dict[str, list[dict]] = {}
    for worker_id, work_date, amount, start_time in rows:
        if worker_id not in by_id:
            continue
        amount = round(float(amount), 2)
        hours[(worker_id, work_date)] = amount
        work_day = _parse_day(work_date)
        if first <= work_day <= last:
            worker = by_id[worker_id]
            shift = {}
            if start_time:
                try:
                    shift = shift_times(str(start_time), amount)
                except ValueError:
                    shift = {"start_time": str(start_time), "end_time": "", "next_day": False, "label": str(start_time)}
            days.setdefault(work_date, []).append({
                "worker_id": worker_id,
                "name": worker["name"],
                "hours": amount,
                "start_time": shift.get("start_time") or (str(start_time) if start_time else ""),
                "end_time": shift.get("end_time") or "",
                "next_day": bool(shift.get("next_day")),
                "shift_label": shift.get("label") or "",
                "reported": worker["reported"],
                "hourly_wage": worker["hourly_wage"],
                "pay": int(round(amount * worker["hourly_wage"])),
            })
    for items in days.values():
        items.sort(key=lambda item: item["name"])

    weeks = []
    sunday = first + timedelta(days=(6 - first.weekday()) % 7)
    while sunday <= last:
        monday = sunday - timedelta(days=6)
        people = []
        for worker in workers:
            basic = 0.0
            day = monday
            while day <= sunday:
                basic += hours.get((worker["id"], day.isoformat()), 0.0)
                day += timedelta(days=1)
            holiday_hours, holiday_pay = weekly_holiday_pay(basic, worker["hourly_wage"], worker["reported"])
            if basic <= 0 and holiday_pay <= 0:
                continue
            people.append({
                "worker_id": worker["id"],
                "name": worker["name"],
                "reported": worker["reported"],
                "basic_hours": round(basic, 2),
                "weekly_holiday_hours": round(holiday_hours, 2),
                "weekly_holiday_pay": holiday_pay,
            })
        weeks.append({
            "monday": monday.isoformat(),
            "sunday": sunday.isoformat(),
            "workers": people,
        })
        sunday += timedelta(days=7)

    totals = []
    for worker in workers:
        basic = 0.0
        holiday_hours = 0.0
        holiday_pay = 0
        day = first
        while day <= last:
            basic += hours.get((worker["id"], day.isoformat()), 0.0)
            day += timedelta(days=1)
        for week in weeks:
            matched = next((item for item in week["workers"] if item["worker_id"] == worker["id"]), None)
            if matched:
                holiday_hours += matched["weekly_holiday_hours"]
                holiday_pay += matched["weekly_holiday_pay"]
        if basic <= 0 and holiday_pay <= 0:
            continue
        totals.append({
            "worker_id": worker["id"],
            "name": worker["name"],
            "reported": worker["reported"],
            "hourly_wage": worker["hourly_wage"],
            "active": worker["active"],
            "basic_hours": round(basic, 2),
            "base_pay": int(round(basic * worker["hourly_wage"])),
            "weekly_holiday_hours": round(holiday_hours, 2),
            "weekly_holiday_pay": holiday_pay,
            "total_pay": int(round(basic * worker["hourly_wage"])) + holiday_pay,
        })
    return {
        "year": year,
        "month": month,
        "minimum_wage": minimum_wage(year),
        "workers": workers,
        "days": days,
        "weeks": weeks,
        "totals": totals,
    }


@router.put("/days")
def save_day(body: DayIn, token: str):
    actor = _admin(token)
    work_day = _parse_day(body.work_date)
    stamp = _now()
    saved = []
    seen: set[int] = set()
    entries = []
    for entry in body.entries:
        if entry.worker_id in seen:
            continue
        seen.add(entry.worker_id)
        entries.append(entry)
    with get_connection() as con:
        for entry in entries:
            worker = con.execute(
                "SELECT name FROM part_time_workers WHERE id = ?",
                (entry.worker_id,),
            ).fetchone()
            if not worker:
                raise HTTPException(status_code=400, detail="알바를 찾지 못했습니다.")
            hours = round(float(entry.hours), 2)
            if hours <= 0:
                con.execute(
                    "DELETE FROM part_time_hours WHERE worker_id = ? AND work_date = ?",
                    (entry.worker_id, work_day.isoformat()),
                )
                continue
            if not (entry.start_time or "").strip():
                raise HTTPException(status_code=400, detail="시작시간을 입력하세요.")
            try:
                start_time = normalize_clock(entry.start_time)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            shift = shift_times(start_time, hours)
            con.execute(
                """
                INSERT INTO part_time_hours (worker_id, work_date, hours, start_time, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(worker_id, work_date) DO UPDATE SET
                    hours = excluded.hours,
                    start_time = excluded.start_time,
                    updated_at = excluded.updated_at
                """,
                (entry.worker_id, work_day.isoformat(), hours, start_time, stamp),
            )
            saved.append(f"{worker[0]} {shift['label']} {hours:g}시간")
        con.commit()
    add_log(
        action_type="알바 근무시간",
        target_type="part_time_day",
        target_id=work_day.isoformat(),
        target_name=work_day.isoformat(),
        user_nickname=actor["nickname"],
        details=", ".join(saved) if saved else "기록 없음",
    )
    return month_calendar(work_day.year, work_day.month, token)


def _first_work_days() -> dict[int, date]:
    with get_connection() as con:
        rows = con.execute(
            "SELECT worker_id, MIN(work_date) FROM part_time_hours GROUP BY worker_id"
        ).fetchall()
    found: dict[int, date] = {}
    for worker_id, work_date in rows:
        if work_date:
            found[int(worker_id)] = date.fromisoformat(str(work_date))
    return found


def _weekly_max(worker_id: int, data: dict, lines: list[dict]) -> float:
    buckets: dict[date, float] = {}
    for line in lines:
        day = date.fromisoformat(line["work_date"])
        sunday = day + timedelta(days=(6 - day.weekday()) % 7)
        buckets[sunday] = buckets.get(sunday, 0.0) + float(line["hours"])
    peak = max(buckets.values(), default=0.0)
    for week in data["weeks"]:
        matched = next((item for item in week["workers"] if item["worker_id"] == worker_id), None)
        if matched:
            peak = max(peak, float(matched["basic_hours"]))
    return peak


def _slips(data: dict) -> list[dict]:
    with get_connection() as con:
        resident_rows = con.execute("SELECT id, resident_id FROM part_time_workers").fetchall()
    residents = {row[0]: row[1] for row in resident_rows}
    first_days = _first_work_days()
    year = int(data["year"])
    month = int(data["month"])
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    slips = []
    for total in data["totals"]:
        lines = []
        for work_date in sorted(data["days"]):
            for entry in data["days"][work_date]:
                if entry["worker_id"] != total["worker_id"]:
                    continue
                lines.append({
                    "work_date": work_date,
                    "hours": entry["hours"],
                    "start_time": entry.get("start_time") or "",
                    "end_time": entry.get("end_time") or "",
                    "shift_label": entry.get("shift_label") or "",
                    "pay": entry["pay"],
                })
        regime = choose_pay_regime(
            first_days.get(total["worker_id"]),
            month_end,
            _weekly_max(total["worker_id"], data, lines),
            float(total["basic_hours"]),
        )
        taxable = int(total["total_pay"])
        pay = settle_part_time_pay(
            taxable,
            len(lines),
            total["basic_hours"],
            bool(total["reported"]),
            year,
            month,
            residents.get(total["worker_id"]) or "",
            regime,
        )
        average = round(total["basic_hours"] / len(lines), 2) if lines else 0
        slips.append({
            **total,
            "work_days": len(lines),
            "average_hours": average,
            "taxable_pay": taxable,
            "nontaxable_pay": 0,
            "lines": lines,
            **pay,
        })
    return slips


@router.get("/slips")
def list_slips(year: int, month: int, token: str):
    data = month_calendar(year, month, token)
    return {"year": year, "month": month, "slips": _slips(data)}


@router.get("/slips/pdf")
def download_slip_pdf(year: int, month: int, token: str, worker_id: int | None = None):
    _admin(token)
    data = month_calendar(year, month, token)
    slips = _slips(data)
    with get_connection() as con:
        rows = con.execute("SELECT id, resident_id FROM part_time_workers").fetchall()
    resident = {row[0]: row[1] for row in rows}
    if worker_id is not None:
        slips = [slip for slip in slips if slip["worker_id"] == worker_id]
        if not slips:
            raise HTTPException(status_code=404, detail="이 달 그 알바의 급여명세서가 없습니다.")
    elif not slips:
        raise HTTPException(status_code=404, detail="이 달 급여명세서가 없습니다.")
    for slip in slips:
        slip["resident_id"] = resident.get(slip["worker_id"]) or ""
    company = _company_for_excel()["company_name"]
    content = render_part_time_slips_pdf(company, year, month, slips)
    if worker_id is not None:
        filename = quote(f"급여명세서 {year}년 {month:02d}월 {slips[0]['name']}.pdf")
    else:
        filename = quote(f"알바 급여명세서 {year}년 {month:02d}월.pdf")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


def _company_for_excel() -> dict:
    try:
        with get_connection() as con:
            row = con.execute(
                "SELECT company_name, business_number FROM company_settings WHERE id = 1"
            ).fetchone()
    except Exception:
        return {"company_name": "틸리언", "business_number": ""}
    if not row:
        return {"company_name": "틸리언", "business_number": ""}
    return {"company_name": row[0] or "틸리언", "business_number": row[1] or ""}


@router.get("/xlsx")
def download_xlsx(year: int, month: int, token: str):
    _admin(token)
    data = month_calendar(year, month, token)
    slips = [slip for slip in _slips(data) if slip.get("pay_regime") == "daily"]
    with get_connection() as con:
        rows = con.execute("SELECT id, resident_id FROM part_time_workers").fetchall()
    resident = {row[0]: row[1] for row in rows}
    excluded = {worker["id"] for worker in data["workers"] if worker.get("exclude_from_excel")}
    people = []
    for slip in slips:
        if slip["worker_id"] in excluded:
            continue
        hours_by_day = {}
        for line in slip["lines"]:
            hours_by_day[int(line["work_date"][8:10])] = line["hours"]
        people.append({
            **slip,
            "resident_id": resident.get(slip["worker_id"]) or "",
            "hours_by_day": hours_by_day,
        })
    content = render_part_time_xlsx(year, month, _company_for_excel(), people)
    filename = quote(f"틸리언 일용근로대장 {year}년 {month:02d}월.xlsx")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
