"""근로계약서 작성, 완료 보관, 다시 활성화."""
from __future__ import annotations

import base64
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.app.api.auth import ensure_users_table
from backend.app.api.certificates import certificate_company_name
from backend.app.api.logs import add_log
from backend.app.api.settings import _ensure_settings_table
from backend.app.config import settings
from backend.app.services.employment_contract.calc import calculate_contract_pay
from backend.app.services.employment_contract.pdf import render_contract_pdf, render_page_pngs
from logic.db import get_connection

router = APIRouter(prefix="/employment-contracts", tags=["employment-contracts"])

INPUT_FIELDS = (
    "employee_name",
    "job_title",
    "rank_title",
    "resident_id",
    "address",
    "phone",
    "hire_date",
    "contract_start",
    "contract_end",
    "base_hours",
    "overtime_hours",
    "holiday_hours",
    "night_hours",
    "net_pay",
    "vehicle_allowance",
    "meal_allowance",
    "position_allowance",
    "income_tax",
    "pension",
    "weekday_hours",
    "break_time",
    "work_days",
    "pay_day",
)


class ContractInput(BaseModel):
    employee_name: str = ""
    job_title: str = ""
    rank_title: str = ""
    resident_id: str = ""
    address: str = ""
    phone: str = ""
    hire_date: str = ""
    contract_start: str = ""
    contract_end: str = ""
    base_hours: float = 209
    overtime_hours: float = 0
    holiday_hours: float = 0
    night_hours: float = 0
    net_pay: int = 0
    vehicle_allowance: int = 0
    meal_allowance: int = 0
    position_allowance: int = 0
    income_tax: int = 0
    pension: int | None = None
    weekday_hours: str = "09:00~18:00"
    break_time: str = "1시간 (12~13)"
    work_days: str = "주중 평균 5일 근무"
    pay_day: int = Field(default=15, ge=1, le=31)


def ensure_contract_tables() -> None:
    ensure_users_table()
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS employment_contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                employee_name TEXT,
                job_title TEXT,
                rank_title TEXT,
                resident_id TEXT,
                address TEXT,
                phone TEXT,
                hire_date TEXT,
                contract_start TEXT,
                contract_end TEXT,
                base_hours REAL DEFAULT 209,
                overtime_hours REAL DEFAULT 0,
                holiday_hours REAL DEFAULT 0,
                night_hours REAL DEFAULT 0,
                net_pay INTEGER DEFAULT 0,
                vehicle_allowance INTEGER DEFAULT 0,
                meal_allowance INTEGER DEFAULT 0,
                position_allowance INTEGER DEFAULT 0,
                income_tax INTEGER DEFAULT 0,
                pension INTEGER,
                weekday_hours TEXT,
                break_time TEXT,
                work_days TEXT,
                pay_day INTEGER DEFAULT 15,
                gross_pay INTEGER,
                calc_json TEXT,
                pdf_filename TEXT,
                completed_at TEXT,
                completed_by INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = [row[1] for row in con.execute("PRAGMA table_info(employment_contracts)")]
        if "pension" not in columns:
            con.execute("ALTER TABLE employment_contracts ADD COLUMN pension INTEGER")
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_employment_contracts_user
            ON employment_contracts(user_id, id)
            """
        )
        con.commit()


def _contract_dir() -> Path:
    path = Path(settings.UPLOAD_DIR) / "employment-contracts"
    path.mkdir(parents=True, exist_ok=True)
    return path


class WorkerInput(BaseModel):
    """근로자가 계약서에 직접 적는 항목."""
    employee_name: str = ""
    resident_id: str = ""
    address: str = ""
    phone: str = ""


def _session(token: str) -> dict:
    ensure_contract_tables()
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
    return {"user_id": row[0], "nickname": row[1], "is_admin": bool(row[2])}


def _admin(token: str) -> dict:
    actor = _session(token)
    if not actor["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 근로계약서를 다룰 수 있습니다.")
    return actor


def _own_or_admin(token: str, user_id: int) -> dict:
    actor = _session(token)
    if not actor["is_admin"] and actor["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="본인 계약서만 적을 수 있습니다.")
    return actor


def _company() -> dict:
    _ensure_settings_table()
    with get_connection() as con:
        row = con.execute(
            """
            SELECT company_name, address, representative
            FROM company_settings WHERE id = 1
            """
        ).fetchone()
    if not row:
        return {"company_name": "틸리언", "address": "", "representative": ""}
    return {
        "company_name": certificate_company_name(row[0] or "") or "틸리언",
        "address": row[1] or "",
        "representative": row[2] or "",
    }


def _normalize_rrn(value: str, required: bool) -> str:
    raw = (value or "").strip()
    if not raw:
        if required:
            raise HTTPException(status_code=400, detail="주민등록번호를 입력하세요.")
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 13:
        raise HTTPException(status_code=400, detail="주민등록번호는 13자리입니다.")
    return f"{digits[:6]}-{digits[6:]}"


def _values(data: ContractInput, *, required: bool) -> dict:
    name = data.employee_name.strip()
    if required and not name:
        raise HTTPException(status_code=400, detail="성명을 입력하세요.")
    if required and not data.address.strip():
        raise HTTPException(status_code=400, detail="주소를 입력하세요.")
    if required and not data.phone.strip():
        raise HTTPException(status_code=400, detail="연락처를 입력하세요.")
    for label, amount in (
        ("차량지원", data.vehicle_allowance),
        ("식대", data.meal_allowance),
        ("직책수당", data.position_allowance),
        ("소득세", data.income_tax),
        ("국민연금", data.pension or 0),
    ):
        if amount < 0:
            raise HTTPException(status_code=400, detail=f"{label}은 0 이상이어야 합니다.")
    payload = data.model_dump()
    payload["employee_name"] = name[:40]
    payload["job_title"] = data.job_title.strip()[:40]
    payload["rank_title"] = data.rank_title.strip()[:40]
    if required:
        payload["resident_id"] = _normalize_rrn(data.resident_id, True)
    else:
        digits = re.sub(r"\D", "", data.resident_id or "")
        payload["resident_id"] = f"{digits[:6]}-{digits[6:]}" if len(digits) == 13 else (data.resident_id or "").strip()[:20]
    payload["address"] = data.address.strip()[:120]
    payload["phone"] = data.phone.strip()[:30]
    payload["hire_date"] = data.hire_date.strip()[:10]
    payload["contract_start"] = data.contract_start.strip()[:10]
    payload["contract_end"] = data.contract_end.strip()[:10]
    payload["weekday_hours"] = (data.weekday_hours or "09:00~18:00").strip()[:40]
    payload["break_time"] = (data.break_time or "1시간 (12~13)").strip()[:40]
    payload["work_days"] = (data.work_days or "주중 평균 5일 근무").strip()[:40]
    payload["pension"] = None if data.pension in (None, 0) else int(data.pension)
    return payload


def _calculate(payload: dict) -> dict:
    try:
        return calculate_contract_pay(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _user_or_404(con, user_id: int):
    row = con.execute(
        """
        SELECT user_id, nickname, department, position, join_date
        FROM users WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다.")
    return {
        "user_id": row[0],
        "nickname": row[1],
        "department": row[2] or "",
        "position": row[3] or "",
        "join_date": row[4] or "",
    }


def _latest(con, user_id: int):
    return con.execute(
        """
        SELECT id, status FROM employment_contracts
        WHERE user_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (user_id,),
    ).fetchone()


def _require_open(con, user_id: int) -> None:
    latest = _latest(con, user_id)
    if latest and latest[1] == "completed":
        raise HTTPException(status_code=400, detail="완료된 계약입니다. 수정하려면 다시 활성화하세요.")


def _public_input(payload: dict) -> dict:
    shown = dict(payload)
    shown.pop("resident_id", None)
    return shown


def _insert_contract(con, user_id: int, payload: dict, calc: dict | None, status: str) -> int:
    columns = ["user_id", "status", *INPUT_FIELDS, "gross_pay", "calc_json"]
    values = [user_id, status, *[payload[name] for name in INPUT_FIELDS]]
    values.append(calc["gross"] if calc else None)
    values.append(json.dumps(calc, ensure_ascii=False) if calc else None)
    placeholders = ", ".join("?" for _ in columns)
    con.execute(
        f"INSERT INTO employment_contracts ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )
    return con.execute("SELECT last_insert_rowid()").fetchone()[0]


def _one_year_term(start: str) -> str:
    year, month, day = [int(part) for part in start[:10].split("-")]
    try:
        ended = date(year + 1, month, day)
    except ValueError:
        ended = date(year + 1, month, 28)
    return (ended - timedelta(days=1)).isoformat()


def _contract_defaults(existing: dict | None, position: str, join_date: str) -> dict:
    current = dict(existing or {})
    return {
        "employee_name": current.get("employee_name") or "",
        "job_title": current.get("job_title") or "",
        "rank_title": current.get("rank_title") or position or "",
        "resident_id": current.get("resident_id") or "",
        "address": current.get("address") or "",
        "phone": current.get("phone") or "",
        "hire_date": current.get("hire_date") or join_date or "",
        "contract_start": current.get("contract_start") or "",
        "contract_end": current.get("contract_end") or "",
        "base_hours": current.get("base_hours") if current.get("base_hours") not in (None, "") else 209,
        "overtime_hours": current.get("overtime_hours") or 0,
        "holiday_hours": current.get("holiday_hours") or 0,
        "night_hours": current.get("night_hours") or 0,
        "net_pay": current.get("net_pay") or 0,
        "vehicle_allowance": current.get("vehicle_allowance") or 0,
        "meal_allowance": current.get("meal_allowance") or 0,
        "position_allowance": current.get("position_allowance") or 0,
        "income_tax": current.get("income_tax") or 0,
        "pension": current.get("pension"),
        "weekday_hours": current.get("weekday_hours") or "09:00~18:00",
        "break_time": current.get("break_time") or "1시간 (12~13)",
        "work_days": current.get("work_days") or "주중 평균 5일 근무",
        "pay_day": current.get("pay_day") or 15,
    }


def apply_payroll_contract_fields(lines: list[dict]) -> dict:
    """급여대장에서 계약 조건이 되는 항목만 근로계약 초안에 반영한다.

    연차수당, 근태공제, 상여처럼 그 달에만 있는 금액은 계약서에 넣지 않는다.
    주소와 연락처, 근무요일 문장은 이미 적힌 값을 유지한다.
    """
    updated: list[dict] = []
    missing: list[str] = []
    with get_connection() as con:
        users = con.execute("SELECT user_id, nickname, position, join_date FROM users").fetchall()
        by_name: dict[str, tuple] = {}
        for user_id, nickname, position, join_date in users:
            key = (nickname or "").strip()
            if key and key not in by_name:
                by_name[key] = (user_id, position or "", join_date or "")
        for line in lines:
            name = (line.get("employee_name") or "").strip()
            found = by_name.get(name)
            if not found:
                missing.append(name)
                continue
            user_id, position, join_date = found
            latest = _latest(con, user_id)
            existing = None
            if latest and latest[1] == "draft":
                existing = _load_contract(con, latest[0])["input"]
            elif latest and latest[1] == "completed":
                existing = _load_contract(con, latest[0])["input"]
            payload = _contract_defaults(existing, position, join_date)
            payload["employee_name"] = name
            if line.get("affiliation"):
                payload["job_title"] = str(line["affiliation"]).strip()
            if not payload["rank_title"]:
                payload["rank_title"] = position
            if line.get("resident_id"):
                try:
                    payload["resident_id"] = _normalize_rrn(str(line["resident_id"]), True)
                except HTTPException:
                    pass
            if line.get("hire_date"):
                payload["hire_date"] = str(line["hire_date"])[:10]
            if payload["hire_date"] and not payload["contract_start"]:
                payload["contract_start"] = payload["hire_date"]
            if payload["contract_start"] and not payload["contract_end"]:
                payload["contract_end"] = _one_year_term(payload["contract_start"])
            payload["base_hours"] = float(line.get("base_hours") or 0) or 209
            payload["overtime_hours"] = float(line.get("overtime_hours") or 0)
            payload["holiday_hours"] = float(line.get("holiday_hours") or 0)
            payload["night_hours"] = float(line.get("night_hours") or 0)
            payload["net_pay"] = int(line.get("net_pay") or 0)
            payload["vehicle_allowance"] = int(line.get("vehicle_allowance") or 0)
            payload["meal_allowance"] = int(line.get("meal_allowance") or 0)
            payload["position_allowance"] = int(line.get("position_allowance") or 0)
            payload["income_tax"] = int(line.get("income_tax") or 0)
            payload["pension"] = int(line.get("pension") or 0) or None
            calc = calculate_contract_pay(payload) if payload["net_pay"] > 0 and payload["base_hours"] > 0 else None
            if latest and latest[1] == "draft":
                assignments = ", ".join(f"{field} = ?" for field in INPUT_FIELDS)
                con.execute(
                    f"""
                    UPDATE employment_contracts
                    SET {assignments}, gross_pay = ?, calc_json = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        *[payload[field] for field in INPUT_FIELDS],
                        calc["gross"] if calc else None,
                        json.dumps(calc, ensure_ascii=False) if calc else None,
                        latest[0],
                    ),
                )
            else:
                _insert_contract(con, user_id, payload, calc, "draft")
            if payload["hire_date"] and not join_date:
                con.execute(
                    "UPDATE users SET join_date = ? WHERE user_id = ? AND (join_date IS NULL OR join_date = '')",
                    (payload["hire_date"], user_id),
                )
            updated.append({"user_id": user_id, "employee_name": name})
        con.commit()
    return {"updated": updated, "missing": missing}


def _load_contract(con, contract_id: int):
    row = con.execute(
        f"SELECT id, user_id, status, {', '.join(INPUT_FIELDS)}, gross_pay, calc_json, pdf_filename, completed_at FROM employment_contracts WHERE id = ?",
        (contract_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다.")
    payload = {name: row[index + 3] for index, name in enumerate(INPUT_FIELDS)}
    return {
        "id": row[0],
        "user_id": row[1],
        "status": row[2],
        "input": payload,
        "gross_pay": row[3 + len(INPUT_FIELDS)],
        "calc": json.loads(row[4 + len(INPUT_FIELDS)]) if row[4 + len(INPUT_FIELDS)] else None,
        "pdf_filename": row[5 + len(INPUT_FIELDS)],
        "completed_at": row[6 + len(INPUT_FIELDS)],
    }


@router.get("")
def list_contracts(token: str, view: str = "open"):
    """작성 대상은 완료되지 않은 직원만, 완료 보관은 저장된 PDF만 보여 준다."""
    _admin(token)
    if view not in {"open", "completed"}:
        raise HTTPException(status_code=400, detail="목록 종류가 올바르지 않습니다.")
    with get_connection() as con:
        if view == "open":
            rows = con.execute(
                """
                SELECT u.user_id, u.nickname, u.department, u.position, u.join_date,
                       c.id, c.employee_name, c.updated_at, c.address, c.phone, c.resident_id
                FROM users u
                LEFT JOIN employment_contracts c
                  ON c.id = (
                    SELECT id FROM employment_contracts
                    WHERE user_id = u.user_id
                    ORDER BY id DESC LIMIT 1
                  )
                WHERE c.id IS NULL OR c.status = 'draft'
                ORDER BY COALESCE(u.department, ''), u.nickname
                """
            ).fetchall()
            return {
                "employees": [
                    {
                        "user_id": row[0],
                        "nickname": row[1],
                        "department": row[2] or "",
                        "position": row[3] or "",
                        "join_date": row[4] or "",
                        "state": "draft" if row[5] else "new",
                        "draft_id": row[5],
                        "employee_name": row[6] or row[1],
                        "updated_at": row[7],
                        "worker_filled": bool((row[8] or "").strip() and (row[9] or "").strip() and (row[10] or "").strip()),
                    }
                    for row in rows
                ]
            }
        rows = con.execute(
            """
            SELECT c.id, c.user_id, c.employee_name, c.completed_at, c.net_pay, c.gross_pay,
                   u.department, u.nickname,
                   CASE WHEN c.id = (
                     SELECT id FROM employment_contracts
                     WHERE user_id = c.user_id
                     ORDER BY id DESC LIMIT 1
                   ) THEN 1 ELSE 0 END
            FROM employment_contracts c
            JOIN users u ON u.user_id = c.user_id
            WHERE c.status = 'completed'
            ORDER BY c.completed_at DESC, c.id DESC
            """
        ).fetchall()
    return {
        "contracts": [
            {
                "id": row[0],
                "user_id": row[1],
                "employee_name": row[2],
                "completed_at": row[3],
                "net_pay": row[4],
                "gross_pay": row[5],
                "department": row[6] or "",
                "nickname": row[7],
                "can_reactivate": bool(row[8]),
            }
            for row in rows
        ]
    }


@router.get("/users/{user_id}")
def get_contract_draft(user_id: int, token: str):
    actor = _own_or_admin(token, user_id)
    with get_connection() as con:
        user = _user_or_404(con, user_id)
        latest = _latest(con, user_id)
        if latest and latest[1] == "completed":
            raise HTTPException(status_code=400, detail="완료된 계약입니다. 수정하려면 다시 활성화하세요.")
        draft = _load_contract(con, latest[0]) if latest else None
    if draft:
        shown = dict(draft["input"])
        if not actor["is_admin"]:
            shown = {key: shown.get(key, "") for key in ("employee_name", "resident_id", "address", "phone")}
        return {
            "user": user,
            "input": shown,
            "calc": None if not actor["is_admin"] else draft["calc"],
            "draft_id": draft["id"],
        }
    return {
        "user": user,
        "input": {
            "employee_name": user["nickname"],
            "job_title": "",
            "rank_title": user["position"],
            "resident_id": "",
            "address": "",
            "phone": "",
            "hire_date": user["join_date"],
            "contract_start": user["join_date"],
            "contract_end": "",
            "base_hours": 209,
            "overtime_hours": 0,
            "holiday_hours": 0,
            "night_hours": 0,
            "net_pay": 0,
            "vehicle_allowance": 0,
            "meal_allowance": 0,
            "position_allowance": 0,
            "income_tax": 0,
            "pension": None,
            "weekday_hours": "09:00~18:00",
            "break_time": "1시간 (12~13)",
            "work_days": "주중 평균 5일 근무",
            "pay_day": 15,
        },
        "calc": None,
        "draft_id": None,
    }


@router.post("/preview")
def preview_contract(body: ContractInput, token: str):
    _admin(token)
    payload = _values(body, required=False)
    return {"calc": _calculate(payload)}


def _preview_calc(payload: dict) -> dict:
    if int(payload.get("net_pay") or 0) > 0:
        return _calculate(payload)
    return {
        "taxable": 0,
        "gross": 0,
        "net": 0,
        "annual": 0,
        "deduction_total": 0,
        "pension_base": 0,
        "pension": payload.get("pension") or 0,
        "health": 0,
        "care": 0,
        "income_tax": 0,
        "local_tax": 0,
        "employment": 0,
        "hourly": 0,
        "base_pay": 0,
        "overtime_pay": 0,
        "holiday_pay": 0,
        "night_pay": 0,
        "meal_allowance": int(payload.get("meal_allowance") or 0),
        "vehicle_allowance": int(payload.get("vehicle_allowance") or 0),
        "position_allowance": int(payload.get("position_allowance") or 0),
        "base_hours": payload.get("base_hours") or 0,
        "overtime_hours": payload.get("overtime_hours") or 0,
        "holiday_hours": payload.get("holiday_hours") or 0,
        "night_hours": payload.get("night_hours") or 0,
    }


def _pages_from_pdf(pdf: bytes) -> dict:
    return {"pages": [base64.b64encode(png).decode("ascii") for png in render_page_pngs(pdf)]}


@router.post("/preview-pages")
def preview_contract_pages(body: ContractInput, token: str):
    """입력 중인 계약을 A4 페이지 이미지로 보여 준다. 보관하지 않는다."""
    _admin(token)
    payload = _values(body, required=False)
    calc = _preview_calc(payload)
    pdf = render_contract_pdf(
        0,
        _company(),
        payload,
        calc,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        preview=True,
    )
    return _pages_from_pdf(pdf)


def _worker_values(data: WorkerInput) -> dict:
    name = data.employee_name.strip()
    address = data.address.strip()
    phone = data.phone.strip()
    if not name:
        raise HTTPException(status_code=400, detail="성명을 입력하세요.")
    if not address:
        raise HTTPException(status_code=400, detail="주소를 입력하세요.")
    if not phone:
        raise HTTPException(status_code=400, detail="연락처를 입력하세요.")
    return {
        "employee_name": name[:40],
        "resident_id": _normalize_rrn(data.resident_id, True),
        "address": address[:120],
        "phone": phone[:30],
    }


@router.put("/users/{user_id}/worker")
def save_worker_fields(user_id: int, body: WorkerInput, token: str):
    """근로자가 성명, 주민등록번호, 주소, 연락처를 적는다."""
    _own_or_admin(token, user_id)
    worker = _worker_values(body)
    with get_connection() as con:
        user = _user_or_404(con, user_id)
        _require_open(con, user_id)
        latest = _latest(con, user_id)
        if latest and latest[1] == "draft":
            con.execute(
                """
                UPDATE employment_contracts
                SET employee_name = ?, resident_id = ?, address = ?, phone = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (worker["employee_name"], worker["resident_id"], worker["address"], worker["phone"], latest[0]),
            )
            draft_id = latest[0]
        else:
            payload = _values(
                ContractInput(
                    employee_name=worker["employee_name"],
                    resident_id=worker["resident_id"],
                    address=worker["address"],
                    phone=worker["phone"],
                    rank_title=user["position"],
                    hire_date=user["join_date"],
                    contract_start=user["join_date"],
                ),
                required=False,
            )
            payload.update(worker)
            draft_id = _insert_contract(con, user_id, payload, None, "draft")
        con.commit()
    return {"draft_id": draft_id}


@router.put("/users/{user_id}")
def save_contract_draft(user_id: int, body: ContractInput, token: str):
    actor = _admin(token)
    payload = _values(body, required=False)
    calc = _calculate(payload) if payload["net_pay"] > 0 and payload["base_hours"] > 0 else None
    with get_connection() as con:
        _user_or_404(con, user_id)
        _require_open(con, user_id)
        latest = _latest(con, user_id)
        if latest and latest[1] == "draft":
            assignments = ", ".join(f"{name} = ?" for name in INPUT_FIELDS)
            con.execute(
                f"""
                UPDATE employment_contracts
                SET {assignments}, gross_pay = ?, calc_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                [
                    *[payload[name] for name in INPUT_FIELDS],
                    calc["gross"] if calc else None,
                    json.dumps(calc, ensure_ascii=False) if calc else None,
                    latest[0],
                ],
            )
            draft_id = latest[0]
        else:
            draft_id = _insert_contract(con, user_id, payload, calc, "draft")
        con.commit()
    return {"draft_id": draft_id, "calc": calc, "saved_by": actor["nickname"]}


@router.post("/users/{user_id}/complete")
def complete_contract(user_id: int, body: ContractInput, token: str):
    """완료하면 PDF를 저장하고 작성 목록에서 숨긴다."""
    actor = _admin(token)
    payload = _values(body, required=True)
    calc = _calculate(payload)
    company = _company()
    completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as con:
        user = _user_or_404(con, user_id)
        _require_open(con, user_id)
        latest = _latest(con, user_id)
        if latest and latest[1] == "draft":
            con.execute("DELETE FROM employment_contracts WHERE id = ?", (latest[0],))
        contract_id = _insert_contract(con, user_id, payload, calc, "completed")
        con.execute(
            """
            UPDATE employment_contracts
            SET completed_at = ?, completed_by = ?, pdf_filename = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (completed_at, actor["user_id"], f"{contract_id}.pdf", contract_id),
        )
        try:
            pdf = render_contract_pdf(contract_id, company, payload, calc, completed_at)
            (_contract_dir() / f"{contract_id}.pdf").write_bytes(pdf)
        except Exception:
            con.rollback()
            raise
        con.commit()
    add_log(
        action_type="근로계약 날인",
        target_type="employment_contract",
        target_id=str(contract_id),
        target_name=payload["employee_name"] or user["nickname"],
        user_nickname=actor["nickname"],
        details="직인 날인 후 PDF 보관",
    )
    return {"id": contract_id, "calc": calc, "completed_at": completed_at}


@router.post("/users/{user_id}/reactivate")
def reactivate_contract(user_id: int, token: str):
    """갱신이 필요하면 작성 목록에 다시 나타낸다. 기존 PDF는 남긴다."""
    actor = _admin(token)
    with get_connection() as con:
        user = _user_or_404(con, user_id)
        latest = _latest(con, user_id)
        if not latest or latest[1] != "completed":
            raise HTTPException(status_code=400, detail="완료된 계약이 없습니다.")
        stored = _load_contract(con, latest[0])
        payload = stored["input"]
        draft_id = _insert_contract(con, user_id, payload, stored["calc"], "draft")
        con.commit()
    add_log(
        action_type="근로계약 다시 활성화",
        target_type="employment_contract",
        target_id=str(draft_id),
        target_name=payload.get("employee_name") or user["nickname"],
        user_nickname=actor["nickname"],
        details="작성 목록으로 되돌림",
    )
    return {"draft_id": draft_id, "user_id": user_id}


@router.get("/{contract_id}/pages")
def contract_preview_pages(contract_id: int, token: str):
    """보관된 계약서를 A4 페이지 이미지로 보여 준다."""
    _admin(token)
    with get_connection() as con:
        row = con.execute(
            "SELECT pdf_filename, status FROM employment_contracts WHERE id = ?",
            (contract_id,),
        ).fetchone()
    if not row or row[1] != "completed" or not row[0]:
        raise HTTPException(status_code=404, detail="저장된 계약서 PDF가 없습니다.")
    root = _contract_dir().resolve()
    path = (root / row[0]).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="저장된 계약서 PDF가 없습니다.")
    return _pages_from_pdf(path.read_bytes())


@router.get("/{contract_id}/pdf")
def download_contract_pdf(contract_id: int, token: str):
    _admin(token)
    with get_connection() as con:
        row = con.execute(
            """
            SELECT pdf_filename, employee_name, status
            FROM employment_contracts WHERE id = ?
            """,
            (contract_id,),
        ).fetchone()
    if not row or row[2] != "completed" or not row[0]:
        raise HTTPException(status_code=404, detail="저장된 계약서 PDF가 없습니다.")
    root = _contract_dir().resolve()
    path = (root / row[0]).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="저장된 계약서 PDF가 없습니다.")
    filename = quote(f"근로계약서_{row[1] or contract_id}.pdf")
    return Response(
        content=path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"},
    )
