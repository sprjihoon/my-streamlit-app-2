"""근로계약서 작성, 완료 PDF 보관, 재계약. 완료 파일은 관리자만 다룬다."""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timedelta
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
from backend.app.services.employment_contract.seal import make_seal, prepare_mark
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
    "taxable_pay",
    "annual_pay",
    "pay_basis",
    "vehicle_allowance",
    "meal_allowance",
    "position_allowance",
    "income_tax",
    "pension",
    "dependents",
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
    taxable_pay: int = 0
    annual_pay: int = 0
    pay_basis: str = "net"
    vehicle_allowance: int = 0
    meal_allowance: int = 0
    position_allowance: int = 0
    income_tax: int = 0
    pension: int | None = None
    dependents: int = Field(default=1, ge=1, le=10)
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
                taxable_pay INTEGER DEFAULT 0,
                annual_pay INTEGER DEFAULT 0,
                pay_basis TEXT DEFAULT 'net',
                vehicle_allowance INTEGER DEFAULT 0,
                meal_allowance INTEGER DEFAULT 0,
                position_allowance INTEGER DEFAULT 0,
                income_tax INTEGER DEFAULT 0,
                pension INTEGER,
                dependents INTEGER DEFAULT 1,
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
        if "taxable_pay" not in columns:
            con.execute("ALTER TABLE employment_contracts ADD COLUMN taxable_pay INTEGER DEFAULT 0")
        if "annual_pay" not in columns:
            con.execute("ALTER TABLE employment_contracts ADD COLUMN annual_pay INTEGER DEFAULT 0")
        if "pay_basis" not in columns:
            con.execute("ALTER TABLE employment_contracts ADD COLUMN pay_basis TEXT DEFAULT 'net'")
        if "dependents" not in columns:
            con.execute("ALTER TABLE employment_contracts ADD COLUMN dependents INTEGER DEFAULT 1")
        if "worker_sealed_at" not in columns:
            con.execute("ALTER TABLE employment_contracts ADD COLUMN worker_sealed_at TEXT")
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_employment_contracts_user
            ON employment_contracts(user_id, id)
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS employment_marks (
                user_id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                image BLOB NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
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


class MarkInput(BaseModel):
    """근로자가 저장하는 도장 또는 싸인."""
    kind: str = ""
    name: str = ""
    image_base64: str = ""


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
        raise HTTPException(status_code=403, detail="관리자만 근로계약서를 확인하고 관리할 수 있습니다.")
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
    ):
        if amount < 0:
            raise HTTPException(status_code=400, detail=f"{label}은 0 이상이어야 합니다.")
    basis = (data.pay_basis or "net").strip()
    if basis not in {"net", "taxable", "annual"}:
        raise HTTPException(status_code=400, detail="급여 기준은 실수령액, 세전금액, 연봉 중 하나입니다.")
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
    payload["pension"] = None
    payload["dependents"] = int(data.dependents or 1)
    payload["income_tax"] = int(data.income_tax or 0)
    payload["pay_basis"] = basis
    payload["taxable_pay"] = int(data.taxable_pay or 0)
    payload["annual_pay"] = int(data.annual_pay or 0)
    if basis == "net":
        payload["taxable_pay"] = 0
        payload["annual_pay"] = 0
    elif basis == "taxable":
        payload["net_pay"] = 0
        payload["annual_pay"] = 0
    else:
        payload["net_pay"] = 0
        payload["taxable_pay"] = 0
    return payload


def _apply_calc(payload: dict, calc: dict) -> dict:
    payload["net_pay"] = calc["net"]
    payload["taxable_pay"] = calc["taxable"]
    payload["annual_pay"] = calc["annual"]
    payload["income_tax"] = calc["income_tax"]
    payload["pension"] = calc["pension"]
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


def _personal_filled(payload: dict) -> bool:
    return all(str(payload.get(name) or "").strip() for name in ("employee_name", "resident_id", "address", "phone"))


def _mask_stored_rrn(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 7:
        return ""
    return f"{digits[:6]}-{digits[6]}******"


def _locked_resident_id(con, user_id: int) -> str:
    """한 번 날인한 주민번호는 재계약에서도 그대로 둔다."""
    row = con.execute(
        """
        SELECT resident_id FROM employment_contracts
        WHERE user_id = ? AND status = 'completed'
          AND resident_id IS NOT NULL AND TRIM(resident_id) != ''
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    return str(row[0]).strip() if row else ""


def _parse_stamp(value: str) -> datetime | None:
    text = (value or "").strip()
    if len(text) < 19:
        return None
    try:
        return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _within_download_hour(completed_at: str, now: datetime | None = None) -> bool:
    stamp = _parse_stamp(completed_at)
    if not stamp:
        return False
    current = now or datetime.now()
    return timedelta(0) <= current - stamp <= timedelta(hours=1)


def _worker_download_offer(con, user_id: int) -> dict | None:
    row = con.execute(
        """
        SELECT id, status, completed_at
        FROM employment_contracts
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if not row or row[1] != "completed" or not _within_download_hour(row[2] or ""):
        return None
    stamp = _parse_stamp(row[2])
    until = stamp + timedelta(hours=1) if stamp else None
    return {
        "contract_id": row[0],
        "completed_at": row[2],
        "until": until.strftime("%Y-%m-%d %H:%M:%S") if until else "",
    }


def _is_system_admin_username(username: str | None) -> bool:
    """시스템 계정 admin만 근로계약 날인 대상이 아니다. 장명찬처럼 관리자이면서 직원인 계정은 대상이다."""
    return (username or "").strip().lower() == "admin"


def worker_needs_contract(user_id: int, is_admin: bool = False) -> bool:
    """작성 중이거나, 날인 후 1시간 안에는 근로계약 메뉴가 필요하다.

    관리자라도 시스템 계정(admin)이 아니면 본인 기재·근로자 날인 대상이다.
    입사일이 비어 있어도 같다.
    """
    ensure_contract_tables()
    with get_connection() as con:
        latest = _latest(con, user_id)
        if latest:
            if latest[1] == "draft":
                return True
            return _worker_download_offer(con, user_id) is not None
        if not is_admin:
            return True
        row = con.execute("SELECT username FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row) and not _is_system_admin_username(row[0])


def _require_open(con, user_id: int) -> None:
    latest = _latest(con, user_id)
    if latest and latest[1] == "completed":
        raise HTTPException(status_code=400, detail="완료된 계약입니다. 수정하려면 재계약하세요.")


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
        "taxable_pay": current.get("taxable_pay") or 0,
        "annual_pay": current.get("annual_pay") or 0,
        "pay_basis": current.get("pay_basis") or "net",
        "vehicle_allowance": current.get("vehicle_allowance") or 0,
        "meal_allowance": current.get("meal_allowance") or 0,
        "position_allowance": current.get("position_allowance") or 0,
        "income_tax": current.get("income_tax") or 0,
        "pension": current.get("pension"),
        "dependents": current.get("dependents") or 1,
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
            payload["base_hours"] = float(line.get("base_hours") or 0) or 209
            payload["overtime_hours"] = float(line.get("overtime_hours") or 0)
            payload["holiday_hours"] = float(line.get("holiday_hours") or 0)
            payload["night_hours"] = float(line.get("night_hours") or 0)
            payload["net_pay"] = int(line.get("net_pay") or 0)
            payload["taxable_pay"] = 0
            payload["annual_pay"] = 0
            payload["pay_basis"] = "net"
            payload["vehicle_allowance"] = int(line.get("vehicle_allowance") or 0)
            payload["meal_allowance"] = int(line.get("meal_allowance") or 0)
            payload["position_allowance"] = int(line.get("position_allowance") or 0)
            payload["income_tax"] = 0
            payload["pension"] = None
            payload["dependents"] = int(line.get("dependents") or payload.get("dependents") or 1)
            calc = calculate_contract_pay(payload) if payload["base_hours"] > 0 and (payload["net_pay"] or payload["taxable_pay"] or payload["annual_pay"]) else None
            if calc:
                payload = _apply_calc(payload, calc)
            if latest and latest[1] == "draft":
                assignments = ", ".join(f"{field} = ?" for field in INPUT_FIELDS)
                con.execute(
                    f"""
                    UPDATE employment_contracts
                    SET {assignments}, gross_pay = ?, calc_json = ?, worker_sealed_at = NULL, updated_at = CURRENT_TIMESTAMP
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


def _pay_ready(net_pay, taxable_pay, annual_pay) -> bool:
    return bool(int(net_pay or 0) or int(taxable_pay or 0) or int(annual_pay or 0))


def _notice(notice_id: str, title: str, message: str, count: int) -> dict:
    return {
        "id": notice_id,
        "title": title,
        "message": message,
        "href": "/employment-contracts",
        "count": count,
    }


def _worker_profile_notices(user_id: int, is_admin: bool = False) -> list[dict]:
    """근로자에게 남은 작성, 확인, 다운로드만 알린다. 날인 후 회사 차례는 알리지 않는다."""
    if not worker_needs_contract(user_id, is_admin):
        return []
    with get_connection() as con:
        offer = _worker_download_offer(con, user_id)
        if offer:
            return [_notice("contract-download", "근로계약", "회사 날인이 끝난 계약서를 받을 수 있습니다.", 1)]
        latest = _latest(con, user_id)
        if not latest:
            return [_notice("contract-write", "근로계약", "근로계약에 적을 내용이 있습니다.", 1)]
        if latest[1] != "draft":
            return []
        row = con.execute(
            """
            SELECT worker_sealed_at, net_pay, taxable_pay, annual_pay
            FROM employment_contracts
            WHERE id = ?
            """,
            (latest[0],),
        ).fetchone()
    if not row or row[0]:
        return []
    if _pay_ready(row[1], row[2], row[3]):
        return [_notice("contract-confirm", "확인사항", "근로계약서를 확인하고 날인하세요.", 1)]
    return [_notice("contract-write", "근로계약", "근로계약에 적을 내용이 있습니다.", 1)]


def _admin_profile_notices(exclude_user_id: int | None = None) -> list[dict]:
    """관리자에게는 급여가 비어 있는 작성과, 근로자가 날인한 확인만 모아서 알린다.

    시스템 계정 admin만 빼고, 관리자이면서 직원인 사람도 대상이다. 본인 건은 근로자 알림으로 따로 보여 준다.
    """
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT c.worker_sealed_at, c.net_pay, c.taxable_pay, c.annual_pay
            FROM users u
            LEFT JOIN employment_contracts c
              ON c.id = (
                SELECT id FROM employment_contracts
                WHERE user_id = u.user_id
                ORDER BY id DESC LIMIT 1
              )
            WHERE (c.id IS NULL OR c.status = 'draft')
              AND (? IS NULL OR u.user_id != ?)
              AND LOWER(TRIM(COALESCE(u.username, ''))) != 'admin'
            """,
            (exclude_user_id, exclude_user_id),
        ).fetchall()
    write = 0
    confirm = 0
    for sealed_at, net_pay, taxable_pay, annual_pay in rows:
        if sealed_at:
            confirm += 1
        elif not _pay_ready(net_pay, taxable_pay, annual_pay):
            write += 1
    items: list[dict] = []
    if write:
        items.append(_notice("contract-write", "근로계약", f"작성할 근로계약이 {write}건 있습니다.", write))
    if confirm:
        items.append(_notice("contract-confirm", "확인사항", f"근로자 {confirm}명이 계약서를 확인하고 날인했습니다.", confirm))
    return items


@router.get("/notices")
def list_profile_notices(token: str):
    """프로필 옆 알림. 로그인한 사람이 처리할 근로계약과 확인만 돌려준다."""
    actor = _session(token)
    items: list[dict] = []
    if actor["is_admin"]:
        items.extend(_admin_profile_notices(exclude_user_id=actor["user_id"]))
    items.extend(_worker_profile_notices(actor["user_id"], actor["is_admin"]))
    return {"items": items}


@router.get("")
def list_contracts(token: str, view: str = "open"):
    """작성 대상은 완료되지 않은 직원만, 완료 보관은 저장된 PDF를 모두 보여 준다."""
    _admin(token)
    if view not in {"open", "completed"}:
        raise HTTPException(status_code=400, detail="목록 종류가 올바르지 않습니다.")
    with get_connection() as con:
        if view == "open":
            rows = con.execute(
                """
                SELECT u.user_id, u.nickname, u.department, u.position, u.join_date,
                       c.id, c.employee_name, c.updated_at, c.address, c.phone, c.resident_id,
                       c.worker_sealed_at
                FROM users u
                LEFT JOIN employment_contracts c
                  ON c.id = (
                    SELECT id FROM employment_contracts
                    WHERE user_id = u.user_id
                    ORDER BY id DESC LIMIT 1
                  )
                WHERE (c.id IS NULL OR c.status = 'draft')
                  AND LOWER(TRIM(COALESCE(u.username, ''))) != 'admin'
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
                        "worker_sealed": bool(row[11]),
                    }
                    for row in rows
                ]
            }
        rows = con.execute(
            """
            SELECT c.id, c.user_id, c.employee_name, c.completed_at, c.net_pay, c.gross_pay,
                   u.department, u.nickname, c.resident_id, c.pdf_filename,
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
    stored = []
    root = _contract_dir().resolve()
    for row in rows:
        filename = row[9] or f"{row[0]}.pdf"
        path = (root / filename).resolve()
        stored.append(
            {
                "id": row[0],
                "user_id": row[1],
                "employee_name": row[2],
                "completed_at": row[3],
                "net_pay": row[4],
                "gross_pay": row[5],
                "department": row[6] or "",
                "nickname": row[7],
                "resident_id": _mask_stored_rrn(row[8]),
                "has_pdf": path.parent == root and path.is_file(),
                "pdf_filename": filename if row[9] else "",
                "can_reactivate": bool(row[10]),
            }
        )
    return {"contracts": stored}


@router.get("/users/{user_id}")
def get_contract_draft(user_id: int, token: str):
    actor = _own_or_admin(token, user_id)
    with get_connection() as con:
        user = _user_or_404(con, user_id)
        latest = _latest(con, user_id)
        own = actor["user_id"] == user_id
        if own:
            offer = _worker_download_offer(con, user_id)
            if offer:
                return {
                    "user": user,
                    "input": {},
                    "calc": None,
                    "draft_id": None,
                    "status": "completed",
                    "completed_at": offer["completed_at"],
                    "rrn_locked": False,
                    "renewal": False,
                    "worker_sealed": False,
                    "download": offer,
                }
        if not actor["is_admin"]:
            if not worker_needs_contract(user_id, False):
                raise HTTPException(status_code=400, detail="작성할 근로계약이 없습니다.")
        locked = _locked_resident_id(con, user_id)
        draft = _load_contract(con, latest[0]) if latest else None
        sealed_at = ""
        if latest:
            sealed_row = con.execute(
                "SELECT worker_sealed_at FROM employment_contracts WHERE id = ?",
                (latest[0],),
            ).fetchone()
            sealed_at = (sealed_row[0] or "") if sealed_row else ""
    if draft:
        shown = dict(draft["input"])
        if locked:
            shown["resident_id"] = locked
        if not actor["is_admin"]:
            shown = {key: shown.get(key, "") for key in ("employee_name", "resident_id", "address", "phone")}
        return {
            "user": user,
            "input": shown,
            "calc": None if not actor["is_admin"] else draft["calc"],
            "draft_id": draft["id"],
            "status": draft["status"],
            "completed_at": draft.get("completed_at"),
            "rrn_locked": bool(locked),
            "renewal": bool(locked and draft["status"] == "draft"),
            "worker_sealed": bool(sealed_at) and draft["status"] == "draft",
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
            "taxable_pay": 0,
            "annual_pay": 0,
            "pay_basis": "net",
            "vehicle_allowance": 0,
            "meal_allowance": 0,
            "position_allowance": 0,
            "income_tax": 0,
            "pension": None,
            "dependents": 1,
            "weekday_hours": "09:00~18:00",
            "break_time": "1시간 (12~13)",
            "work_days": "주중 평균 5일 근무",
            "pay_day": 15,
        },
        "calc": None,
        "draft_id": None,
        "status": "new",
        "completed_at": None,
        "rrn_locked": False,
        "renewal": False,
        "worker_sealed": False,
    }


@router.post("/preview")
def preview_contract(body: ContractInput, token: str):
    _admin(token)
    payload = _values(body, required=False)
    return {"calc": _calculate(payload)}


def _preview_calc(payload: dict) -> dict:
    if int(payload.get("net_pay") or 0) > 0 or int(payload.get("taxable_pay") or 0) > 0 or int(payload.get("annual_pay") or 0) > 0:
        return _calculate(payload)
    return {
        "taxable": 0,
        "gross": 0,
        "net": 0,
        "annual": 0,
        "deduction_total": 0,
        "pension_base": 0,
        "pension": 0,
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
def preview_contract_pages(body: ContractInput, token: str, user_id: int | None = None):
    """입력 중인 계약을 A4 페이지 이미지로 보여 준다. 보관하지 않는다."""
    _admin(token)
    if user_id:
        with get_connection() as con:
            _user_or_404(con, user_id)
    payload = _values(body, required=False)
    calc = _preview_calc(payload)
    pdf = render_contract_pdf(
        0,
        _company(),
        payload,
        calc,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        preview=True,
        employee_mark=_employee_mark(user_id),
    )
    return _pages_from_pdf(pdf)


@router.post("/users/{user_id}/preview-own")
def preview_own_contract(user_id: int, token: str):
    """저장된 초안을 근로자가 확인하고 날인하기 전에 본다."""
    actor = _own_or_admin(token, user_id)
    if not actor["is_admin"] and not worker_needs_contract(user_id, False):
        raise HTTPException(status_code=400, detail="작성할 근로계약이 없습니다.")
    with get_connection() as con:
        _user_or_404(con, user_id)
        latest = _latest(con, user_id)
        if not latest or latest[1] != "draft":
            raise HTTPException(status_code=400, detail="회사에서 계약 내용을 저장한 뒤 확인할 수 있습니다.")
        draft = _load_contract(con, latest[0])
    payload = draft["input"]
    calc = draft["calc"] or _preview_calc(payload)
    pdf = render_contract_pdf(
        0,
        _company(),
        payload,
        calc,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        preview=True,
        employee_mark=_employee_mark(user_id),
    )
    return _pages_from_pdf(pdf)


@router.post("/users/{user_id}/worker-seal")
def worker_seal_contract(user_id: int, token: str):
    """근로자가 계약서를 확인한 뒤 본인 도장으로 날인한다."""
    actor = _session(token)
    if actor["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="본인 계약서만 날인할 수 있습니다.")
    if not _employee_mark(user_id):
        raise HTTPException(status_code=400, detail="도장이나 싸인을 먼저 저장하세요.")
    with get_connection() as con:
        _user_or_404(con, user_id)
        _require_open(con, user_id)
        latest = _latest(con, user_id)
        if not latest or latest[1] != "draft":
            raise HTTPException(status_code=400, detail="회사에서 계약 내용을 저장한 뒤 날인할 수 있습니다.")
        payload = _load_contract(con, latest[0])["input"]
        if not _personal_filled(payload):
            raise HTTPException(status_code=400, detail="성명, 주민등록번호, 주소, 연락처를 저장한 뒤 날인하세요.")
        if not (int(payload.get("net_pay") or 0) or int(payload.get("taxable_pay") or 0) or int(payload.get("annual_pay") or 0)):
            raise HTTPException(status_code=400, detail="회사에서 급여를 저장한 뒤 날인할 수 있습니다.")
        sealed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute(
            """
            UPDATE employment_contracts
            SET worker_sealed_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (sealed_at, latest[0]),
        )
        con.commit()
    add_log(
        action_type="근로계약 근로자 날인",
        target_type="employment_contract",
        target_id=str(latest[0]),
        target_name=payload.get("employee_name") or actor["nickname"],
        user_nickname=actor["nickname"],
        details="근로자가 계약서를 확인하고 날인",
    )
    return {"worker_sealed_at": sealed_at}


def _worker_values(data: WorkerInput, locked_rrn: str = "") -> dict:
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
        "resident_id": locked_rrn or _normalize_rrn(data.resident_id, True),
        "address": address[:120],
        "phone": phone[:30],
    }


@router.put("/users/{user_id}/worker")
def save_worker_fields(user_id: int, body: WorkerInput, token: str):
    """근로자가 성명, 주소, 연락처를 적는다. 재계약이면 주민번호는 고정이다."""
    actor = _own_or_admin(token, user_id)
    if not actor["is_admin"] and not worker_needs_contract(user_id, False):
        raise HTTPException(status_code=400, detail="작성할 근로계약이 없습니다.")
    with get_connection() as con:
        user = _user_or_404(con, user_id)
        _require_open(con, user_id)
        worker = _worker_values(body, _locked_resident_id(con, user_id))
        latest = _latest(con, user_id)
        if latest and latest[1] == "draft":
            con.execute(
                """
                UPDATE employment_contracts
                SET employee_name = ?, resident_id = ?, address = ?, phone = ?, worker_sealed_at = NULL, updated_at = CURRENT_TIMESTAMP
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


def _own_name(con, user_id: int) -> str:
    """도장에 넣는 이름은 그 사람의 저장된 성명이다. 없으면 계정 이름이다."""
    user = _user_or_404(con, user_id)
    latest = _latest(con, user_id)
    if latest:
        row = con.execute(
            "SELECT employee_name FROM employment_contracts WHERE id = ?",
            (latest[0],),
        ).fetchone()
        stored = (row[0] or "").strip() if row else ""
        if stored:
            return stored
    nickname = (user["nickname"] or "").strip()
    if nickname:
        return nickname
    raise HTTPException(status_code=400, detail="성명을 먼저 저장하세요.")


def _lookup_own_name(user_id: int) -> str:
    with get_connection() as con:
        return _own_name(con, user_id)


def _employee_mark(user_id: int | None) -> bytes | None:
    if not user_id:
        return None
    with get_connection() as con:
        row = con.execute("SELECT image FROM employment_marks WHERE user_id = ?", (user_id,)).fetchone()
    if not row or not row[0]:
        return None
    return bytes(row[0])


def _mark_payload(user_id: int) -> dict:
    with get_connection() as con:
        row = con.execute(
            "SELECT kind, image FROM employment_marks WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row or not row[1]:
        return {"kind": "", "image": ""}
    return {"kind": row[0] or "", "image": base64.b64encode(bytes(row[1])).decode("ascii")}


@router.get("/users/{user_id}/mark-samples")
def mark_samples(user_id: int, token: str):
    """그 사람 이름으로 도장 두 가지를 보여 준다. 저장하지 않는다."""
    _own_or_admin(token, user_id)
    own_name = _lookup_own_name(user_id)
    try:
        return {
            "name": own_name,
            "grid": base64.b64encode(make_seal(own_name, "grid")).decode("ascii"),
            "ring": base64.b64encode(make_seal(own_name, "ring")).decode("ascii"),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/users/{user_id}/mark")
def get_worker_mark(user_id: int, token: str):
    _own_or_admin(token, user_id)
    with get_connection() as con:
        _user_or_404(con, user_id)
    return _mark_payload(user_id)


@router.put("/users/{user_id}/mark")
def save_worker_mark(user_id: int, body: MarkInput, token: str):
    """도장 만들기, 도장 파일, 싸인 중 하나를 저장한다. 날인할 때 을 서명란에 찍힌다."""
    _own_or_admin(token, user_id)
    kind = (body.kind or "").strip()
    if kind not in {"grid", "ring", "upload", "signature"}:
        raise HTTPException(status_code=400, detail="도장 또는 싸인 종류를 고르세요.")
    own_name = ""
    try:
        if kind in {"grid", "ring"}:
            own_name = _lookup_own_name(user_id)
            image = make_seal(own_name, kind)
        else:
            encoded = (body.image_base64 or "").strip()
            if "," in encoded and encoded.lower().startswith("data:"):
                encoded = encoded.split(",", 1)[1]
            try:
                raw = base64.b64decode(encoded, validate=False)
            except Exception as exc:
                raise ValueError("도장 이미지를 읽을 수 없습니다.") from exc
            image = prepare_mark(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with get_connection() as con:
        _user_or_404(con, user_id)
        con.execute(
            """
            INSERT INTO employment_marks (user_id, kind, image, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                kind = excluded.kind,
                image = excluded.image,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, kind, image),
        )
        con.commit()
    return {"kind": kind, "name": own_name, "image": base64.b64encode(image).decode("ascii")}


@router.put("/users/{user_id}")
def save_contract_draft(user_id: int, body: ContractInput, token: str):
    actor = _admin(token)
    payload = _values(body, required=False)
    calc = _calculate(payload) if payload["base_hours"] > 0 and (payload["net_pay"] or payload["taxable_pay"] or payload["annual_pay"]) else None
    if calc:
        payload = _apply_calc(payload, calc)
    with get_connection() as con:
        _user_or_404(con, user_id)
        _require_open(con, user_id)
        locked = _locked_resident_id(con, user_id)
        if locked:
            payload["resident_id"] = locked
        latest = _latest(con, user_id)
        if latest and latest[1] == "draft":
            assignments = ", ".join(f"{name} = ?" for name in INPUT_FIELDS)
            con.execute(
                f"""
                UPDATE employment_contracts
                SET {assignments}, gross_pay = ?, calc_json = ?, worker_sealed_at = NULL, updated_at = CURRENT_TIMESTAMP
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
    """완료하면 PDF를 저장하고 작성 목록에서 숨긴다. 이전 완료 파일은 지우지 않는다."""
    actor = _admin(token)
    payload = _values(body, required=True)
    calc = _calculate(payload)
    payload = _apply_calc(payload, calc)
    company = _company()
    completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as con:
        user = _user_or_404(con, user_id)
        _require_open(con, user_id)
        latest = _latest(con, user_id)
        locked = _locked_resident_id(con, user_id)
        if not latest or latest[1] != "draft":
            raise HTTPException(status_code=400, detail="근로자가 계약서를 확인하고 날인한 뒤 회사 날인을 할 수 있습니다.")
        sealed_row = con.execute(
            "SELECT worker_sealed_at FROM employment_contracts WHERE id = ?",
            (latest[0],),
        ).fetchone()
        if not sealed_row or not (sealed_row[0] or "").strip():
            raise HTTPException(status_code=400, detail="근로자가 계약서를 확인하고 날인한 뒤 회사 날인을 할 수 있습니다.")
        if latest and latest[1] == "draft":
            previous = _load_contract(con, latest[0])["input"]
            for key in ("employee_name", "resident_id", "address", "phone"):
                if not str(payload.get(key) or "").strip() and previous.get(key):
                    payload[key] = previous[key]
            if locked:
                payload["resident_id"] = locked
            else:
                payload["resident_id"] = _normalize_rrn(str(payload.get("resident_id") or ""), True)
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
            pdf = render_contract_pdf(
                contract_id,
                company,
                payload,
                calc,
                completed_at,
                employee_mark=_employee_mark(user_id),
            )
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
    """연봉 인상 등으로 재계약한다. 주민번호와 이전 계약 내용을 복사하고 기존 PDF는 남긴다."""
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
        action_type="근로계약 재계약",
        target_type="employment_contract",
        target_id=str(draft_id),
        target_name=payload.get("employee_name") or user["nickname"],
        user_nickname=actor["nickname"],
        details="이전 계약 내용을 복사해 재계약 초안을 만듦",
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
    actor = _session(token)
    with get_connection() as con:
        row = con.execute(
            """
            SELECT pdf_filename, employee_name, status, user_id, completed_at
            FROM employment_contracts WHERE id = ?
            """,
            (contract_id,),
        ).fetchone()
    if not row or row[2] != "completed" or not row[0]:
        raise HTTPException(status_code=404, detail="저장된 계약서 PDF가 없습니다.")
    owner = actor["user_id"] == row[3]
    if actor["is_admin"]:
        disposition = "inline"
    elif owner and _within_download_hour(row[4] or ""):
        disposition = "attachment"
    else:
        if owner:
            raise HTTPException(status_code=403, detail="날인 후 1시간이 지나 계약서를 받을 수 없습니다.")
        raise HTTPException(status_code=403, detail="본인 계약서만 받을 수 있습니다.")
    root = _contract_dir().resolve()
    path = (root / row[0]).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="저장된 계약서 PDF가 없습니다.")
    filename = quote(f"근로계약서_{row[1] or contract_id}.pdf")
    return Response(
        content=path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{filename}"},
    )
