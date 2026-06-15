"""
backend/app/api/certificates.py - 재직/경력 증명서 정보 API
"""
from fastapi import APIRouter, HTTPException
from datetime import date, datetime

from logic.db import get_connection
from backend.app.api.logs import add_log

router = APIRouter(prefix="/certificates", tags=["certificates"])


def _get_user_from_token(token: str) -> dict:
    with get_connection() as con:
        row = con.execute(
            """SELECT u.user_id, u.nickname, u.department, u.position, u.join_date, u.is_admin
               FROM sessions s JOIN users u USING(user_id)
               WHERE s.token = ?""",
            (token,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return {
        "user_id": row[0],
        "nickname": row[1],
        "department": row[2] or "",
        "position": row[3] or "",
        "join_date": row[4] or "",
        "is_admin": bool(row[5]),
    }


def _get_company() -> dict:
    """company_settings 에서 회사 정보 조회"""
    with get_connection() as con:
        row = con.execute(
            """SELECT company_name, business_number, address, representative
               FROM company_settings WHERE id = 1"""
        ).fetchone()
    if row:
        return {
            "company_name": row[0] or "",
            "business_number": row[1] or "",
            "address": row[2] or "",
            "representative": row[3] or "",
        }
    return {"company_name": "", "business_number": "", "address": "", "representative": ""}


def _years_months(join_date_str: str) -> str:
    """입사일 ~ 현재 기간 문자열 (예: 2년 7개월)"""
    if not join_date_str:
        return ""
    try:
        jd = date.fromisoformat(join_date_str)
        today = date.today()
        months = (today.year - jd.year) * 12 + (today.month - jd.month)
        if today.day < jd.day:
            months -= 1
        years, m = divmod(max(months, 0), 12)
        parts = []
        if years:
            parts.append(f"{years}년")
        if m:
            parts.append(f"{m}개월")
        return " ".join(parts) if parts else "1개월 미만"
    except Exception:
        return ""


@router.get("/info")
def get_certificate_info(token: str, target_user_id: int = None):
    """증명서 발급에 필요한 사용자+회사 정보 반환
    - 본인 또는 관리자가 target_user_id 지정 가능
    """
    me = _get_user_from_token(token)
    company = _get_company()

    if target_user_id and target_user_id != me["user_id"]:
        if not me["is_admin"]:
            raise HTTPException(status_code=403, detail="관리자만 타인 증명서를 발급할 수 있습니다.")
        with get_connection() as con:
            row = con.execute(
                "SELECT user_id, nickname, department, position, join_date FROM users WHERE user_id=?",
                (target_user_id,)
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        user = {"user_id": row[0], "nickname": row[1], "department": row[2] or "",
                "position": row[3] or "", "join_date": row[4] or ""}
    else:
        user = me

    today = date.today().isoformat()
    duration = _years_months(user["join_date"])

    return {
        "user": user,
        "company": company,
        "issued_date": today,
        "duration": duration,
    }


@router.post("/log")
def log_certificate(token: str, cert_type: str, purpose: str = ""):
    """증명서 발급 로그 기록"""
    me = _get_user_from_token(token)
    add_log(
        action_type=f"{cert_type} 발급",
        target_type="certificate",
        target_id=str(me["user_id"]),
        target_name=me["nickname"],
        user_nickname=me["nickname"],
        details=f"발급목적: {purpose or '미기재'}",
    )
    return {"success": True}
