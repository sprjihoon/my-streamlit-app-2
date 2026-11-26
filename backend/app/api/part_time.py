"""알바 등록과 달력 근무시간. 주휴수당은 신고 알바만 계산한다."""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.logs import add_log
from backend.app.services.part_time.calc import minimum_wage, weekly_holiday_pay
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
                updated_at TEXT,
                PRIMARY KEY (worker_id, work_date)
            )
            """
        )
        con.commit()


class WorkerIn(BaseModel):
    name: str
    resident_id: str
    reported: bool = True
    hourly_wage: int | None = None


class WorkerPatch(BaseModel):
    name: str | None = None
    resident_id: str | None = None
    reported: bool | None = None
    hourly_wage: int | None = None
    active: bool | None = None


class HourIn(BaseModel):
    worker_id: int
    hours: float = Field(ge=0, le=24)


class DayIn(BaseModel):
    work_date: str
    entries: list[HourIn]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _admin(token: str) -> dict:
    ensure_part_time_tables()
    with get_connection() as con:
        row = con.execute(
            """
            SELECT u.user_id, u.nickname, u.is_admin
            FROM sessions s
            JOIN users u ON u.user_id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    if not row[2]:
        raise HTTPException(status_code=403, detail="관리자만 아르바이트 관리대장을 다룰 수 있습니다.")
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


def _public_worker(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "resident_id": _mask_rrn(row[2]),
        "reported": bool(row[3]),
        "hourly_wage": int(row[4]),
        "active": bool(row[5]),
    }


def _load_workers() -> list[dict]:
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT id, name, resident_id, reported, hourly_wage, active
            FROM part_time_workers
            ORDER BY active DESC, name, id
            """
        ).fetchall()
    return [_public_worker(row) for row in rows]


def _worker_row(worker_id: int):
    with get_connection() as con:
        return con.execute(
            "SELECT id, name, resident_id, reported, hourly_wage, active FROM part_time_workers WHERE id = ?",
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
                (name, resident_id, reported, hourly_wage, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (name, resident_id, 1 if body.reported else 0, wage, stamp, stamp),
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
            SET name = ?, resident_id = ?, reported = ?, hourly_wage = ?, active = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, resident_id, reported, wage, active, stamp, worker_id),
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
            SELECT worker_id, work_date, hours
            FROM part_time_hours
            WHERE work_date >= ? AND work_date <= ?
            """,
            (range_start.isoformat(), range_end.isoformat()),
        ).fetchall()
    hours: dict[tuple[int, str], float] = {}
    days: dict[str, list[dict]] = {}
    for worker_id, work_date, amount in rows:
        if worker_id not in by_id:
            continue
        amount = round(float(amount), 2)
        hours[(worker_id, work_date)] = amount
        work_day = _parse_day(work_date)
        if first <= work_day <= last:
            worker = by_id[worker_id]
            days.setdefault(work_date, []).append({
                "worker_id": worker_id,
                "name": worker["name"],
                "hours": amount,
                "reported": worker["reported"],
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
            "weekly_holiday_hours": round(holiday_hours, 2),
            "weekly_holiday_pay": holiday_pay,
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
    with get_connection() as con:
        for entry in body.entries:
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
            con.execute(
                """
                INSERT INTO part_time_hours (worker_id, work_date, hours, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(worker_id, work_date) DO UPDATE SET hours = excluded.hours, updated_at = excluded.updated_at
                """,
                (entry.worker_id, work_day.isoformat(), hours, stamp),
            )
            saved.append(f"{worker[0]} {hours:g}시간")
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
