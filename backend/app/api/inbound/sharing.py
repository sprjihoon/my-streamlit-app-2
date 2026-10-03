"""Share links and the public overview served by them."""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException
from fastapi.responses import FileResponse

from backend.app.config import settings
from logic.db import get_connection

from .overview import _compute_batch_overview
from .router import router
from .schemas import ShareLinkCreate
from .utils import UPLOAD_DIR, _get_user, _hash_password, _verify_password


@router.post("/batches/{batch_id}/share")
def create_share_link(
    batch_id: str,
    body: ShareLinkCreate,
    authorization: Optional[str] = Header(None),
):
    """
    공유 링크 생성.
    비밀번호가 있으면 SHA-256+salt 해시로 변환해 저장.
    원문 비밀번호는 응답에 한 번만 포함 — 이후 API·로그·DB 어디에도 원문 없음.
    """
    user = _get_user(authorization)
    plain_password = (body.password or "").strip() or None  # None = 비번 없는 링크

    # 해시 변환 (원문 즉시 폐기)
    stored_password = _hash_password(plain_password) if plain_password else None

    with get_connection() as con:
        if not con.execute("SELECT 1 FROM inbound_batches WHERE id=?", (batch_id,)).fetchone():
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")
        from datetime import timedelta
        token = uuid.uuid4().hex
        expires_at = (datetime.utcnow() + timedelta(days=body.expires_days)).strftime("%Y-%m-%d")
        con.execute("""
            INSERT INTO inbound_share_links (token, batch_id, password, expires_at, allow_excel, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (token, batch_id, stored_password, expires_at, int(body.allow_excel), user["nickname"]))
        con.commit()

    link = f"{settings.FRONTEND_URL}/share/{token}"
    # plain_password 는 생성 응답에만 포함. 이 이후로는 서버 어디에도 원문이 없음.
    return {
        "token": token,
        "link": link,
        "expires_at": expires_at,
        "has_password": plain_password is not None,
        "password_once": plain_password,  # 프론트가 1회 표시 후 즉시 소멸해야 함
    }


@router.get("/share/{token}")
def get_share_data(
    token: str,
    password: Optional[str] = None,
):
    """공유 링크 데이터 (인증 불필요, 비밀번호 확인만)"""
    with get_connection() as con:
        row = con.execute(
            "SELECT batch_id, password, expires_at, allow_excel, revoked_at FROM inbound_share_links WHERE token=?",
            (token,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="링크를 찾을 수 없습니다.")
        batch_id, stored_pw, expires_at, allow_excel, revoked_at = row

        # 폐기 확인
        if revoked_at:
            raise HTTPException(status_code=410, detail="폐기된 링크입니다.")

        # 만료 확인
        if expires_at and datetime.utcnow().strftime("%Y-%m-%d") > expires_at:
            raise HTTPException(status_code=410, detail="링크가 만료되었습니다.")

        # 비밀번호 확인 (해시 비교 — 원문 절대 반환하지 않음)
        if stored_pw:
            if not password:
                return {"needs_password": True}
            if not _verify_password(password, stored_pw):
                raise HTTPException(status_code=403, detail="비밀번호가 틀렸습니다.")

        # 배치 + 품목 조회
        batch_row = con.execute("""
            SELECT id, vendor, inbound_date, status, wholesale, janggi_date, janggi_no,
                   total_janggi_qty, total_actual_qty, total_missing_qty, created_by, closed_at
            FROM inbound_batches WHERE id=?
        """, (batch_id,)).fetchone()
        if not batch_row:
            raise HTTPException(status_code=404, detail="입고 데이터를 찾을 수 없습니다.")

        items = con.execute("""
            SELECT id, line_no, item_name, option_text, janggi_qty, actual_qty, missing_qty,
                   status, matched_barcode, matched_vendor, matched_product, matched_option
            FROM inbound_items WHERE batch_id=? ORDER BY line_no
        """, (batch_id,)).fetchall()

        photos_map: dict = {}
        if items:
            ids_ph = [r[0] for r in items]
            ph_rows = con.execute(
                f"SELECT item_id, id, filename FROM inbound_item_photos WHERE item_id IN ({','.join('?' for _ in ids_ph)})",
                ids_ph
            ).fetchall()
            for ph in ph_rows:
                photos_map.setdefault(ph[0], []).append({"id": ph[1], "filename": ph[2]})

    STATUS_LABEL_MAP = {
        "ocr_pending": "장끼 확인 중", "confirming": "수량 확인 중",
        "inbound_done": "입고접수 완료", "grading": "양품화 중",
        "repairing": "수선 중", "done": "최종완료", "cancelled": "취소",
    }
    ITEM_LABEL_MAP = {
        "pending": "확인 전", "confirmed": "정상", "missing": "미입고",
        "defect": "불량", "repair": "수선대기", "unrecoverable": "회생불가", "done": "완료",
    }

    return {
        "batch": {
            "id": batch_row[0], "vendor": batch_row[1], "inbound_date": batch_row[2],
            "status": batch_row[3], "status_label": STATUS_LABEL_MAP.get(batch_row[3], batch_row[3]),
            "wholesale": batch_row[4], "janggi_date": batch_row[5], "janggi_no": batch_row[6],
            "total_janggi_qty": batch_row[7], "total_actual_qty": batch_row[8],
            "total_missing_qty": batch_row[9], "created_by": batch_row[10], "closed_at": batch_row[11],
        },
        "items": [{
            "id": r[0], "line_no": r[1], "item_name": r[2], "option_text": r[3],
            "janggi_qty": r[4], "actual_qty": r[5], "missing_qty": r[6],
            "status": r[7], "status_label": ITEM_LABEL_MAP.get(r[7], r[7]),
            "matched_barcode": r[8], "matched_vendor": r[9],
            "matched_product": r[10], "matched_option": r[11],
            "photos": [
                {"id": p["id"], "url": f"/inbound/share-photo/{p['filename']}"}
                for p in photos_map.get(r[0], [])
            ],
        } for r in items],
        "allow_excel": bool(allow_excel),
        "expires_at": expires_at,
    }


@router.get("/share-photo/{filename}")
def serve_share_photo(filename: str):
    """공유 링크용 사진 (인증 불필요)"""
    safe_name = Path(filename).name
    path = UPLOAD_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="사진을 찾을 수 없습니다.")
    return FileResponse(path)

# ── 공유 링크 폐기 ──────────────────────────────────────────────

@router.delete("/share/{token}")
def revoke_share_link(
    token: str,
    authorization: Optional[str] = Header(None),
):
    """공유 링크 폐기 (인증 필요). 이후 해당 링크 접근 불가."""
    _get_user(authorization)

    with get_connection() as con:
        row = con.execute(
            "SELECT token, revoked_at FROM inbound_share_links WHERE token=?",
            (token,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="링크를 찾을 수 없습니다.")
        if row[1]:
            return {"ok": True, "already_revoked": True, "revoked_at": row[1]}

        con.execute(
            "UPDATE inbound_share_links SET revoked_at=CURRENT_TIMESTAMP WHERE token=?",
            (token,)
        )
        con.commit()

    return {"ok": True, "revoked": True}


# ── 공유 통합현황 (화주사용, 인증 불필요) ──────────────────────

@router.get("/share/{token}/overview")
def get_share_overview(
    token: str,
    password: Optional[str] = None,
):
    """
    공유 링크 토큰으로 통합현황 조회 (화주사용, 인증 불필요).

    보안:
    - 토큰에 연결된 화주사·batch만 조회 가능
    - 비밀번호, 만료, 폐기 검증
    - 다른 batch·화주사 접근 불가
    - 내부 필드(원가·직원명·인증정보) 제외한 공유 전용 DTO 반환
    """
    with get_connection() as con:
        link_row = con.execute(
            "SELECT batch_id, password, expires_at, revoked_at FROM inbound_share_links WHERE token=?",
            (token,)
        ).fetchone()
        if not link_row:
            raise HTTPException(status_code=404, detail="링크를 찾을 수 없습니다.")

        batch_id, stored_pw, expires_at, revoked_at = link_row

        # 폐기 확인
        if revoked_at:
            raise HTTPException(status_code=410, detail="폐기된 링크입니다.")

        # 만료 확인
        if expires_at and datetime.utcnow().strftime("%Y-%m-%d") > expires_at:
            raise HTTPException(status_code=410, detail="링크가 만료되었습니다.")

        # 비밀번호 확인
        if stored_pw:
            if not password:
                return {"needs_password": True}
            if not _verify_password(password, stored_pw):
                raise HTTPException(status_code=403, detail="비밀번호가 틀렸습니다.")

        # 공유 DTO 생성 (public=True → 내부 필드 제외)
        overview = _compute_batch_overview(batch_id, con, public=True)

    if overview is None:
        raise HTTPException(status_code=404, detail="입고 데이터를 찾을 수 없습니다.")

    overview["expires_at"] = expires_at
    overview["updated_at"] = overview["batch"].get("closed_at") or overview["batch"].get("inbound_date")
    return overview
