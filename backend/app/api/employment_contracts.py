"""근로계약서 작성, 완료 보관, 다시 활성화."""
from __future__ import annotations

import json
import re
from datetime import datetime
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
from backend.app.services.employment_contract.pdf import render_contract_pdf
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


def _admin(token: str) -> dict:
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
    if not row[2]:
        raise HTTPException(status_code=403, detail="관리자만 근로계약서를 다룰 수 있습니다.")
    return {"user_id": row[0], "nickname": row[1]}


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
    for label, amount in (
        ("차량지원", data.vehicle_allowance),
        ("식대", data.meal_allowance),
        ("직책수당", data.position_allowance),
        ("소득세", data.income_tax),
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
                       c.id, c.employee_name, c.updated_at
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
    _admin(token)
    with get_connection() as con:
        user = _user_or_404(con, user_id)
        latest = _latest(con, user_id)
        if latest and latest[1] == "completed":
            raise HTTPException(status_code=400, detail="완료된 계약입니다. 수정하려면 다시 활성화하세요.")
        draft = _load_contract(con, latest[0]) if latest else None
    if draft:
        shown = dict(draft["input"])
        return {"user": user, "input": shown, "calc": draft["calc"], "draft_id": draft["id"]}
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
