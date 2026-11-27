"""급여명세서는 근로자 본인 것만 확인하고, 관리자는 전체를 확인한다."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.app.api.employment_contracts import _company
from backend.app.api.payroll_ledgers import _load, _mask_rrn, _public_line, ensure_payroll_tables
from backend.app.services.payroll_ledger.slip import render_bundle_pdf, render_slip_pdf, slip_preview_pages
from logic.db import get_connection

router = APIRouter(prefix="/payroll-slips", tags=["payroll-slips"])


def _session(token: str) -> dict:
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
    return {"user_id": row[0], "nickname": row[1] or "", "is_admin": bool(row[2])}


def _owns(line: dict, actor: dict) -> bool:
    """계정이 있으면 그 계정만, 계정이 없을 때만 빈 이름이 아닌 본인 성함으로 맞춘다."""
    owner = int(line.get("user_id") or 0)
    if owner:
        return owner == int(actor["user_id"])
    name = (line.get("employee_name") or "").strip()
    nickname = (actor.get("nickname") or "").strip()
    return bool(name) and name == nickname


def _visible_ledger(year: int, month: int, actor: dict) -> dict:
    ledger = _load(year, month)
    if not ledger:
        raise HTTPException(status_code=404, detail="이 달 급여명세서가 없습니다.")
    if not actor["is_admin"] and not ledger.get("released_at"):
        raise HTTPException(status_code=404, detail="아직 제공된 급여명세서가 없습니다.")
    return ledger


def _reject_other_person(actor: dict, user_id: int | None, employee_name: str | None) -> None:
    if actor["is_admin"]:
        return
    asked_name = (employee_name or "").strip()
    if user_id and int(user_id) != int(actor["user_id"]):
        raise HTTPException(status_code=403, detail="본인 급여명세서만 확인할 수 있습니다.")
    if asked_name and asked_name != (actor.get("nickname") or "").strip():
        raise HTTPException(status_code=403, detail="본인 급여명세서만 확인할 수 있습니다.")


def _pick_line(ledger: dict, actor: dict, user_id: int | None, employee_name: str | None) -> dict:
    _reject_other_person(actor, user_id, employee_name)
    if actor["is_admin"]:
        name = (employee_name or "").strip()
        if user_id:
            for line in ledger["lines"]:
                if int(line.get("user_id") or 0) == user_id:
                    return line
        if name:
            for line in ledger["lines"]:
                if (line.get("employee_name") or "").strip() == name:
                    return line
        if not user_id and not name:
            raise HTTPException(status_code=400, detail="직원을 지정하세요.")
        raise HTTPException(status_code=404, detail="그 직원의 급여명세서가 없습니다.")
    for line in ledger["lines"]:
        if _owns(line, actor):
            return line
    raise HTTPException(status_code=404, detail="이 달 본인 급여명세서가 없습니다.")


def _pdf_response(content: bytes, filename: str) -> Response:
    encoded = quote(filename)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded}"},
    )


def _list_where(actor: dict, year: int | None, month: int | None) -> tuple[str, list]:
    where = ["1 = 1"]
    args: list = []
    if not actor["is_admin"]:
        where.append("l.released_at IS NOT NULL")
        where.append(
            """(
                p.user_id = ?
                OR (
                    COALESCE(p.user_id, 0) = 0
                    AND TRIM(p.employee_name) = ?
                    AND TRIM(?) != ''
                )
            )"""
        )
        nickname = (actor.get("nickname") or "").strip()
        args.extend([actor["user_id"], nickname, nickname])
    if year:
        where.append("l.year = ?")
        args.append(year)
    if month:
        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="월은 1부터 12까지입니다.")
        where.append("l.month = ?")
        args.append(month)
    return " AND ".join(where), args


@router.get("")
def list_slips(token: str, year: int | None = None, month: int | None = None, page: int = 1, page_size: int = 20):
    actor = _session(token)
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 20), 1), 100)
    where, args = _list_where(actor, year, month)
    month_where, month_args = _list_where(actor, None, None)
    with get_connection() as con:
        months = con.execute(
            f"""
            SELECT l.year, l.month, l.period_label, COUNT(*)
            FROM payroll_ledgers l
            JOIN payroll_lines p ON p.ledger_id = l.id
            WHERE {month_where}
            GROUP BY l.year, l.month, l.period_label
            ORDER BY l.year DESC, l.month DESC
            """,
            month_args,
        ).fetchall()
        total = con.execute(
            f"""
            SELECT COUNT(*)
            FROM payroll_ledgers l
            JOIN payroll_lines p ON p.ledger_id = l.id
            WHERE {where}
            """,
            args,
        ).fetchone()[0]
        rows = con.execute(
            f"""
            SELECT l.year, l.month, l.period_label, l.released_at,
                   p.user_id, p.employee_name, p.affiliation, p.net_pay, p.seq
            FROM payroll_ledgers l
            JOIN payroll_lines p ON p.ledger_id = l.id
            WHERE {where}
            ORDER BY l.year DESC, l.month DESC, p.seq, p.id
            LIMIT ? OFFSET ?
            """,
            [*args, page_size, (page - 1) * page_size],
        ).fetchall()
    items = [
        {
            "year": row[0],
            "month": row[1],
            "period_label": row[2],
            "released_at": row[3],
            "user_id": row[4],
            "employee_name": row[5],
            "affiliation": row[6] or "",
            "net_pay": row[7],
            "seq": row[8],
            "mine": _owns({"user_id": row[4], "employee_name": row[5]}, actor),
        }
        for row in rows
        if actor["is_admin"] or _owns({"user_id": row[4], "employee_name": row[5]}, actor)
    ]
    return {
        "is_admin": actor["is_admin"],
        "company_name": _company().get("company_name") or "틸리언",
        "slips": items,
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "months": [
            {"year": row[0], "month": row[1], "period_label": row[2] or "", "count": row[3]}
            for row in months
        ],
    }


@router.get("/{year}/{month}")
def get_slip(year: int, month: int, token: str, user_id: int | None = None, employee_name: str | None = None):
    actor = _session(token)
    _reject_other_person(actor, user_id, employee_name)
    ledger = _visible_ledger(year, month, actor)
    line = _pick_line(ledger, actor, user_id if actor["is_admin"] else None, employee_name if actor["is_admin"] else None)
    shown = _public_line(line)
    return {
        "year": year,
        "month": month,
        "company_name": ledger.get("company_name") or _company().get("company_name") or "틸리언",
        "period_label": ledger.get("period_label") or "",
        "released_at": ledger.get("released_at"),
        "line": shown,
    }


@router.get("/{year}/{month}/pdf")
def download_slip(year: int, month: int, token: str, user_id: int | None = None, employee_name: str | None = None):
    actor = _session(token)
    _reject_other_person(actor, user_id, employee_name)
    ledger = _visible_ledger(year, month, actor)
    line = _pick_line(ledger, actor, user_id if actor["is_admin"] else None, employee_name if actor["is_admin"] else None)
    pdf = render_slip_pdf(ledger, line, masked_rrn=_mask_rrn(str(line.get("resident_id") or "")))
    name = line.get("employee_name") or "직원"
    return _pdf_response(pdf, f"급여명세서 {year}년 {month:02d}월 {name}.pdf")


@router.get("/{year}/{month}/pages")
def preview_slip(year: int, month: int, token: str, user_id: int | None = None, employee_name: str | None = None):
    actor = _session(token)
    _reject_other_person(actor, user_id, employee_name)
    ledger = _visible_ledger(year, month, actor)
    line = _pick_line(ledger, actor, user_id if actor["is_admin"] else None, employee_name if actor["is_admin"] else None)
    pdf = render_slip_pdf(ledger, line, masked_rrn=_mask_rrn(str(line.get("resident_id") or "")))
    return {"pages": slip_preview_pages(pdf)}


@router.get("/{year}/{month}/bundle.pdf")
def download_bundle(year: int, month: int, token: str):
    actor = _session(token)
    if not actor["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 전체 명세서를 받을 수 있습니다.")
    ledger = _load(year, month)
    if not ledger:
        raise HTTPException(status_code=404, detail="이 달 급여대장이 없습니다.")
    pdf = render_bundle_pdf(ledger, ledger["lines"], _mask_rrn)
    return _pdf_response(pdf, f"급여명세서 {year}년 {month:02d}월.pdf")
