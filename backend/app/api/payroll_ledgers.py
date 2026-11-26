"""근로계약 급여로 월별 급여대장을 만든다."""
from __future__ import annotations

import calendar
import re
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.app.api.employment_contracts import _company, apply_payroll_contract_fields, ensure_contract_tables
from backend.app.api.logs import add_log
from backend.app.services.employment_contract.calc import calculate_contract_pay
from backend.app.services.payroll_ledger.excel import fill_official_xlsx, parse_payroll_xlsx, render_payroll_xlsx
from backend.app.services.payroll_ledger.october_2026 import october_2026_lines
from logic.db import get_connection

router = APIRouter(prefix="/payroll-ledgers", tags=["payroll-ledgers"])

LINE_FIELDS = (
    "user_id",
    "contract_id",
    "seq",
    "employee_name",
    "affiliation",
    "hire_date",
    "resident_id",
    "work_days",
    "base_hours",
    "overtime_hours",
    "holiday_hours",
    "night_hours",
    "extra_hours",
    "hourly",
    "base_pay",
    "overtime_pay",
    "holiday_pay",
    "night_pay",
    "position_allowance",
    "vehicle_allowance",
    "meal_allowance",
    "annual_leave_pay",
    "special_pay",
    "incentive_pay",
    "attendance_deduction",
    "settlement_pay",
    "bonus_pay",
    "income_tax",
    "local_tax",
    "pension",
    "health",
    "care",
    "employment",
    "year_end_tax",
    "insurance_adjust",
    "prepaid",
    "gross_pay",
    "deduction_total",
    "net_pay",
)

MONEY_TOTALS = (
    "base_pay",
    "overtime_pay",
    "holiday_pay",
    "night_pay",
    "position_allowance",
    "vehicle_allowance",
    "meal_allowance",
    "annual_leave_pay",
    "special_pay",
    "incentive_pay",
    "attendance_deduction",
    "settlement_pay",
    "bonus_pay",
    "income_tax",
    "local_tax",
    "pension",
    "health",
    "care",
    "employment",
    "year_end_tax",
    "insurance_adjust",
    "prepaid",
    "gross_pay",
    "deduction_total",
    "net_pay",
)


def ensure_payroll_tables() -> None:
    ensure_contract_tables()
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS payroll_ledgers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                company_name TEXT,
                period_label TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                origin TEXT DEFAULT 'contract',
                UNIQUE(year, month)
            )
            """
        )
        columns = [row[1] for row in con.execute("PRAGMA table_info(payroll_ledgers)")]
        if "origin" not in columns:
            con.execute("ALTER TABLE payroll_ledgers ADD COLUMN origin TEXT DEFAULT 'contract'")
        if "released_at" not in columns:
            con.execute("ALTER TABLE payroll_ledgers ADD COLUMN released_at TEXT")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS payroll_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                contract_id INTEGER,
                seq INTEGER NOT NULL,
                employee_name TEXT,
                affiliation TEXT,
                hire_date TEXT,
                resident_id TEXT,
                work_days TEXT,
                base_hours REAL,
                overtime_hours REAL,
                holiday_hours REAL,
                night_hours REAL,
                extra_hours REAL,
                hourly INTEGER,
                base_pay INTEGER,
                overtime_pay INTEGER,
                holiday_pay INTEGER,
                night_pay INTEGER,
                position_allowance INTEGER,
                vehicle_allowance INTEGER,
                meal_allowance INTEGER,
                annual_leave_pay INTEGER DEFAULT 0,
                special_pay INTEGER DEFAULT 0,
                incentive_pay INTEGER DEFAULT 0,
                attendance_deduction INTEGER DEFAULT 0,
                settlement_pay INTEGER DEFAULT 0,
                bonus_pay INTEGER DEFAULT 0,
                income_tax INTEGER,
                local_tax INTEGER,
                pension INTEGER,
                health INTEGER,
                care INTEGER,
                employment INTEGER,
                year_end_tax INTEGER DEFAULT 0,
                insurance_adjust INTEGER DEFAULT 0,
                prepaid INTEGER DEFAULT 0,
                gross_pay INTEGER,
                deduction_total INTEGER,
                net_pay INTEGER
            )
            """
        )
        con.commit()
        _seed_october_2026(con)
        con.commit()


def _seed_october_2026(con) -> None:
    existing = con.execute(
        "SELECT id FROM payroll_ledgers WHERE year = 2026 AND month = 10"
    ).fetchone()
    if existing:
        return
    lines = october_2026_lines()
    _match_users(lines)
    apply_payroll_contract_fields(lines)
    cur = con.execute(
        """
        INSERT INTO payroll_ledgers (year, month, company_name, period_label, origin, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (2026, 10, "틸리언", "2026.10.01~2026.10.31", "excel", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    ledger_id = cur.lastrowid
    placeholders = ", ".join("?" for _ in LINE_FIELDS)
    columns = ", ".join(LINE_FIELDS)
    for line in lines:
        con.execute(
            f"INSERT INTO payroll_lines (ledger_id, {columns}) VALUES (?, {placeholders})",
            (ledger_id, *[line[name] for name in LINE_FIELDS]),
        )


class LedgerCreate(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    replace: bool = False


class LineChange(BaseModel):
    seq: int
    work_days: str | None = None
    base_hours: float | None = None
    overtime_hours: float | None = None
    holiday_hours: float | None = None
    night_hours: float | None = None
    net_pay: int | None = None
    vehicle_allowance: int | None = None
    meal_allowance: int | None = None
    position_allowance: int | None = None
    annual_leave_pay: int | None = None
    special_pay: int | None = None
    incentive_pay: int | None = None
    attendance_deduction: int | None = None
    bonus_pay: int | None = None
    settlement_pay: int | None = None
    keep: bool = True


class LedgerChanges(BaseModel):
    lines: list[LineChange]


def _admin(token: str) -> dict:
    ensure_payroll_tables()
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
        raise HTTPException(status_code=403, detail="관리자만 급여대장을 다룰 수 있습니다.")
    return {"user_id": row[0], "nickname": row[1] or ""}


def _mask_rrn(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 7:
        return ""
    return f"{digits[:6]}-{digits[6]}******"


def _period(year: int, month: int) -> tuple[str, str, str]:
    last_day = calendar.monthrange(year, month)[1]
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year:04d}-{month:02d}-{last_day:02d}"
    label = f"{year}.{month:02d}.01~{year}.{month:02d}.{last_day:02d}"
    return start, end, label


def _covers(start: str, end: str, contract_start: str, contract_end: str) -> bool:
    if contract_start and contract_start > end:
        return False
    if contract_end and contract_end < start:
        return False
    return True


def _lines_from_contracts(year: int, month: int) -> tuple[list[dict], list[str]]:
    start, end, _label = _period(year, month)
    ensure_contract_tables()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT u.user_id, u.department, u.nickname,
                   c.id, c.employee_name, c.job_title, c.rank_title, c.resident_id,
                   c.hire_date, c.contract_start, c.contract_end,
                   c.base_hours, c.overtime_hours, c.holiday_hours, c.night_hours,
                   c.net_pay, c.vehicle_allowance, c.meal_allowance,
                   c.position_allowance, c.dependents
            FROM users u
            JOIN employment_contracts c ON c.id = (
                SELECT id FROM employment_contracts
                WHERE user_id = u.user_id AND COALESCE(net_pay, 0) > 0
                ORDER BY id DESC
                LIMIT 1
            )
            ORDER BY COALESCE(u.department, ''), COALESCE(c.employee_name, u.nickname, '')
            """
        ).fetchall()
    lines: list[dict] = []
    skipped: list[str] = []
    for row in rows:
        contract_start = row[9] or ""
        contract_end = row[10] or ""
        name = (row[4] or row[2] or "").strip()
        if not _covers(start, end, contract_start, contract_end):
            continue
        payload = {
            "net_pay": row[15] or 0,
            "meal_allowance": row[17] or 0,
            "vehicle_allowance": row[16] or 0,
            "position_allowance": row[18] or 0,
            "dependents": row[19] or 1,
            "base_hours": row[11] or 0,
            "overtime_hours": row[12] or 0,
            "holiday_hours": row[13] or 0,
            "night_hours": row[14] or 0,
        }
        try:
            calc = calculate_contract_pay(payload)
        except ValueError:
            skipped.append(name or str(row[0]))
            continue
        affiliation = (row[5] or row[6] or row[1] or "").strip()
        lines.append({
            "user_id": row[0],
            "contract_id": row[3],
            "employee_name": name,
            "affiliation": affiliation,
            "hire_date": row[8] or "",
            "resident_id": row[7] or "",
            "work_days": "만근",
            "base_hours": calc["base_hours"],
            "overtime_hours": calc["overtime_hours"],
            "holiday_hours": calc["holiday_hours"],
            "night_hours": calc["night_hours"],
            "extra_hours": float(calc["overtime_hours"]) * 0.5,
            "hourly": calc["hourly"],
            "base_pay": calc["base_pay"],
            "overtime_pay": calc["overtime_pay"],
            "holiday_pay": calc["holiday_pay"],
            "night_pay": calc["night_pay"],
            "position_allowance": calc["position_allowance"],
            "vehicle_allowance": calc["vehicle_allowance"],
            "meal_allowance": calc["meal_allowance"],
            "annual_leave_pay": 0,
            "special_pay": 0,
            "incentive_pay": 0,
            "attendance_deduction": 0,
            "settlement_pay": 0,
            "bonus_pay": 0,
            "income_tax": calc["income_tax"],
            "local_tax": calc["local_tax"],
            "pension": calc["pension"],
            "health": calc["health"],
            "care": calc["care"],
            "employment": calc["employment"],
            "year_end_tax": 0,
            "insurance_adjust": 0,
            "prepaid": 0,
            "gross_pay": calc["gross"],
            "deduction_total": calc["deduction_total"],
            "net_pay": calc["net"],
        })
    for seq, line in enumerate(lines, start=1):
        line["seq"] = seq
    return lines, skipped


def _previous_ledger(year: int, month: int) -> dict | None:
    if month > 1:
        return _load(year, month - 1)
    return _load(year - 1, 12)


def _inactive_names(year: int, month: int) -> set[str]:
    start, end, _label = _period(year, month)
    ensure_contract_tables()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT COALESCE(c.employee_name, u.nickname, ''),
                   c.contract_start, c.contract_end
            FROM users u
            JOIN employment_contracts c ON c.id = (
                SELECT id FROM employment_contracts
                WHERE user_id = u.user_id
                ORDER BY id DESC
                LIMIT 1
            )
            """
        ).fetchall()
    ended = set()
    for row in rows:
        name = (row[0] or "").strip()
        if name and not _covers(start, end, row[1] or "", row[2] or ""):
            ended.add(name)
    return ended


def _lines_for_month(year: int, month: int) -> tuple[list[dict], list[str], bool]:
    contract_lines, skipped = _lines_from_contracts(year, month)
    previous = _previous_ledger(year, month)
    if not previous:
        return contract_lines, skipped, False
    by_name = {(line.get("employee_name") or "").strip(): line for line in contract_lines}
    ended = _inactive_names(year, month)
    merged: list[dict] = []
    seen: set[str] = set()
    for line in previous["lines"]:
        name = (line.get("employee_name") or "").strip()
        if not name or name in ended:
            continue
        seen.add(name)
        merged.append(dict(by_name.get(name) or line))
    for line in contract_lines:
        name = (line.get("employee_name") or "").strip()
        if name and name not in seen:
            merged.append(dict(line))
            seen.add(name)
    for seq, line in enumerate(merged, start=1):
        line["seq"] = seq
    return merged, skipped, True


def _dependents_for(line: dict) -> int:
    with get_connection() as con:
        row = None
        if line.get("contract_id"):
            row = con.execute(
                "SELECT dependents FROM employment_contracts WHERE id = ?",
                (line["contract_id"],),
            ).fetchone()
        if row is None and line.get("user_id"):
            row = con.execute(
                """
                SELECT dependents FROM employment_contracts
                WHERE user_id = ? ORDER BY id DESC LIMIT 1
                """,
                (line["user_id"],),
            ).fetchone()
    value = int(row[0] or 1) if row else 1
    return value if 1 <= value <= 10 else 1


def _recalc_line(line: dict) -> dict:
    payload = {
        "net_pay": int(line.get("net_pay") or 0),
        "meal_allowance": int(line.get("meal_allowance") or 0),
        "vehicle_allowance": int(line.get("vehicle_allowance") or 0),
        "position_allowance": int(line.get("position_allowance") or 0),
        "dependents": _dependents_for(line),
        "base_hours": line.get("base_hours") or 209,
        "overtime_hours": line.get("overtime_hours") or 0,
        "holiday_hours": line.get("holiday_hours") or 0,
        "night_hours": line.get("night_hours") or 0,
    }
    calc = calculate_contract_pay(payload)
    extras = (
        int(line.get("annual_leave_pay") or 0)
        + int(line.get("special_pay") or 0)
        + int(line.get("incentive_pay") or 0)
        + int(line.get("bonus_pay") or 0)
        + int(line.get("settlement_pay") or 0)
        - int(line.get("attendance_deduction") or 0)
    )
    updated = dict(line)
    updated.update({
        "base_hours": calc["base_hours"],
        "overtime_hours": calc["overtime_hours"],
        "holiday_hours": calc["holiday_hours"],
        "night_hours": calc["night_hours"],
        "extra_hours": float(calc["overtime_hours"]) * 0.5,
        "hourly": calc["hourly"],
        "base_pay": calc["base_pay"],
        "overtime_pay": calc["overtime_pay"],
        "holiday_pay": calc["holiday_pay"],
        "night_pay": calc["night_pay"],
        "position_allowance": calc["position_allowance"],
        "vehicle_allowance": calc["vehicle_allowance"],
        "meal_allowance": calc["meal_allowance"],
        "income_tax": calc["income_tax"],
        "local_tax": calc["local_tax"],
        "pension": calc["pension"],
        "health": calc["health"],
        "care": calc["care"],
        "employment": calc["employment"],
        "gross_pay": calc["gross"] + extras,
        "deduction_total": calc["deduction_total"],
        "net_pay": calc["net"],
    })
    return updated


def _totals(lines: list[dict]) -> dict:
    return {name: sum(int(line.get(name) or 0) for line in lines) for name in MONEY_TOTALS}


def _public_line(line: dict) -> dict:
    shown = dict(line)
    shown["resident_id"] = _mask_rrn(str(line.get("resident_id") or ""))
    return shown


def _load(year: int, month: int) -> dict | None:
    with get_connection() as con:
        header = con.execute(
            "SELECT id, year, month, company_name, period_label, created_at, origin, released_at FROM payroll_ledgers WHERE year = ? AND month = ?",
            (year, month),
        ).fetchone()
        if not header:
            return None
        columns = ", ".join(LINE_FIELDS)
        rows = con.execute(
            f"SELECT {columns} FROM payroll_lines WHERE ledger_id = ? ORDER BY seq, id",
            (header[0],),
        ).fetchall()
    lines = [dict(zip(LINE_FIELDS, row)) for row in rows]
    return {
        "id": header[0],
        "year": header[1],
        "month": header[2],
        "company_name": header[3] or "",
        "period_label": header[4] or "",
        "created_at": header[5],
        "origin": header[6] or "contract",
        "released_at": header[7],
        "lines": lines,
        "totals": _totals(lines),
    }


def _match_users(lines: list[dict]) -> None:
    with get_connection() as con:
        rows = con.execute("SELECT user_id, nickname FROM users").fetchall()
    by_name = {(row[1] or "").strip(): row[0] for row in rows if (row[1] or "").strip()}
    for line in lines:
        line["user_id"] = by_name.get(line["employee_name"], 0)
        line["contract_id"] = None


def _store(year: int, month: int, company: str, label: str, lines: list[dict], origin: str, replace: bool) -> dict:
    with get_connection() as con:
        existing = con.execute(
            "SELECT id, released_at FROM payroll_ledgers WHERE year = ? AND month = ?",
            (year, month),
        ).fetchone()
        if existing and not replace:
            pass
        else:
            released_at = existing[1] if existing else None
            if existing and replace:
                con.execute("DELETE FROM payroll_lines WHERE ledger_id = ?", (existing[0],))
                con.execute("DELETE FROM payroll_ledgers WHERE id = ?", (existing[0],))
            cur = con.execute(
                """
                INSERT INTO payroll_ledgers (year, month, company_name, period_label, origin, created_at, released_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (year, month, company, label, origin, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), released_at),
            )
            ledger_id = cur.lastrowid
            placeholders = ", ".join("?" for _ in LINE_FIELDS)
            columns = ", ".join(LINE_FIELDS)
            for line in lines:
                con.execute(
                    f"INSERT INTO payroll_lines (ledger_id, {columns}) VALUES (?, {placeholders})",
                    (ledger_id, *[line[name] for name in LINE_FIELDS]),
                )
        con.commit()
    saved = _load(year, month)
    assert saved is not None
    saved["replaced"] = bool(existing and replace)
    saved["existed"] = bool(existing and not replace)
    return saved


def _save(year: int, month: int, replace: bool) -> dict:
    current = _load(year, month)
    if current and current.get("origin") == "excel" and not replace:
        current["skipped"] = []
        current["replaced"] = False
        current["existed"] = True
        return current
    lines, skipped, from_previous = _lines_for_month(year, month)
    if not lines:
        raise HTTPException(status_code=400, detail="이 달에 적용할 근로계약 급여가 없습니다.")
    _start, _end, label = _period(year, month)
    company = _company().get("company_name") or "틸리언"
    saved = _store(year, month, company, label, lines, "contract", replace)
    saved["skipped"] = skipped
    saved["from_previous"] = from_previous
    return saved


@router.get("")
def list_ledgers(token: str):
    _admin(token)
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT year, month, period_label, created_at, released_at,
                   (SELECT COUNT(*) FROM payroll_lines WHERE ledger_id = payroll_ledgers.id)
            FROM payroll_ledgers
            ORDER BY year DESC, month DESC
            """
        ).fetchall()
    return {
        "ledgers": [
            {
                "year": row[0],
                "month": row[1],
                "period_label": row[2],
                "created_at": row[3],
                "released_at": row[4],
                "headcount": row[5],
            }
            for row in rows
        ]
    }


@router.post("/import")
async def import_ledger_file(token: str, file: UploadFile = File(...)):
    """급여대장 엑셀의 계산된 값을 그 달 대장으로 그대로 저장한다."""
    actor = _admin(token)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="파일이 비어 있습니다.")
    try:
        parsed = parse_payroll_xlsx(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _match_users(parsed["lines"])
    contracts = apply_payroll_contract_fields(parsed["lines"])
    saved = _store(
        parsed["year"],
        parsed["month"],
        parsed["company_name"],
        parsed["period_label"],
        parsed["lines"],
        "excel",
        True,
    )
    add_log(
        action_type="급여대장 파일 반영",
        target_type="payroll_ledger",
        target_id=f"{parsed['year']}-{parsed['month']:02d}",
        target_name=parsed["period_label"],
        user_nickname=actor["nickname"],
        details=f"대장 {len(parsed['lines'])}명, 계약 {len(contracts['updated'])}명",
    )
    shown = dict(saved)
    shown["lines"] = [_public_line(line) for line in saved["lines"]]
    shown["contracts"] = contracts
    return shown


@router.get("/{year}/{month}")
def get_ledger(year: int, month: int, token: str):
    _admin(token)
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="월은 1부터 12까지입니다.")
    ledger = _load(year, month)
    if not ledger:
        raise HTTPException(status_code=404, detail="이 달 급여대장이 없습니다.")
    shown = dict(ledger)
    shown["lines"] = [_public_line(line) for line in ledger["lines"]]
    return shown


@router.post("")
def create_ledger(body: LedgerCreate, token: str):
    actor = _admin(token)
    saved = _save(body.year, body.month, body.replace)
    if not saved["existed"]:
        add_log(
            action_type="급여대장 작성",
            target_type="payroll_ledger",
            target_id=f"{body.year}-{body.month:02d}",
            target_name=saved["period_label"],
            user_nickname=actor["nickname"],
            details=f"{len(saved['lines'])}명",
        )
    shown = dict(saved)
    shown["lines"] = [_public_line(line) for line in saved["lines"]]
    return shown


@router.put("/{year}/{month}/lines")
def update_ledger_lines(year: int, month: int, body: LedgerChanges, token: str):
    actor = _admin(token)
    ledger = _load(year, month)
    if not ledger:
        raise HTTPException(status_code=404, detail="이 달 급여대장이 없습니다.")
    current = {int(line["seq"]): line for line in ledger["lines"]}
    updated: list[dict] = []
    for change in body.lines:
        if not change.keep:
            continue
        line = current.get(change.seq)
        if not line:
            raise HTTPException(status_code=400, detail=f"{change.seq}번 직원을 찾지 못했습니다.")
        next_line = dict(line)
        for name in (
            "work_days",
            "base_hours",
            "overtime_hours",
            "holiday_hours",
            "night_hours",
            "net_pay",
            "vehicle_allowance",
            "meal_allowance",
            "position_allowance",
            "annual_leave_pay",
            "special_pay",
            "incentive_pay",
            "attendance_deduction",
            "bonus_pay",
            "settlement_pay",
        ):
            value = getattr(change, name)
            if value is not None:
                next_line[name] = value
        try:
            updated.append(_recalc_line(next_line))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{line.get('employee_name')}: {exc}") from exc
    if not updated:
        raise HTTPException(status_code=400, detail="급여대장에 남을 직원이 없습니다.")
    for seq, line in enumerate(updated, start=1):
        line["seq"] = seq
    saved = _store(year, month, ledger["company_name"], ledger["period_label"], updated, ledger.get("origin") or "contract", True)
    add_log(
        action_type="급여대장 변동",
        target_type="payroll_ledger",
        target_id=f"{year}-{month:02d}",
        target_name=saved["period_label"],
        user_nickname=actor["nickname"],
        details=f"{len(saved['lines'])}명",
    )
    shown = dict(saved)
    shown["lines"] = [_public_line(line) for line in saved["lines"]]
    return shown


@router.get("/{year}/{month}/xlsx")
def download_ledger(year: int, month: int, token: str):
    _admin(token)
    ledger = _load(year, month)
    if not ledger:
        raise HTTPException(status_code=404, detail="이 달 급여대장이 없습니다.")
    content = fill_official_xlsx(ledger)
    filename = quote(f"틸리언 급여대장 {year}년 {month:02d}월.xlsx")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/{year}/{month}/release")
def release_slips(year: int, month: int, token: str):
    actor = _admin(token)
    ledger = _load(year, month)
    if not ledger:
        raise HTTPException(status_code=404, detail="이 달 급여대장이 없습니다.")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as con:
        con.execute(
            "UPDATE payroll_ledgers SET released_at = ? WHERE year = ? AND month = ?",
            (stamp, year, month),
        )
        con.commit()
    add_log(
        action_type="급여명세서 제공",
        target_type="payroll_ledger",
        target_id=f"{year}-{month:02d}",
        target_name=ledger["period_label"],
        user_nickname=actor["nickname"],
        details=f"{len(ledger['lines'])}명",
    )
    saved = _load(year, month)
    shown = dict(saved)
    shown["lines"] = [_public_line(line) for line in saved["lines"]]
    return shown
