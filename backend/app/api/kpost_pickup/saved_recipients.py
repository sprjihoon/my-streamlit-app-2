"""Saved pickup recipient CRUD. Independent of pickup create."""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel

from backend.app.api.logs import add_log
from backend.app.services.epost.fields import normalize_phone, normalize_zip
from logic.db import get_connection

from .common import KST, _get_user, ensure_pickup_tables
from .router import router


class SavedRecipientRequest(BaseModel):
    label: str
    recipient_name: str
    recipient_phone: str
    zipcode: str
    addr1: str
    addr2: str = ""


@router.get("/saved-recipients")
def list_saved_recipients(token: str):
    user = _get_user(token)
    ensure_pickup_tables()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT id, label, recipient_name, recipient_phone, zipcode, addr1, addr2, created_at
            FROM saved_recipients
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user["user_id"],),
        ).fetchall()
    return {
        "items": [
            {
                "id": row[0],
                "label": row[1],
                "recipient_name": row[2],
                "recipient_phone": row[3],
                "zipcode": row[4],
                "addr1": row[5],
                "addr2": row[6] or "",
                "created_at": row[7],
            }
            for row in rows
        ]
    }


@router.post("/saved-recipients")
def save_recipient(req: SavedRecipientRequest, token: str):
    user = _get_user(token)
    ensure_pickup_tables()
    label = (req.label or "").strip()
    if len(label) < 1:
        raise HTTPException(status_code=400, detail="라벨을 입력해주세요.")
    if len(label) > 50:
        raise HTTPException(status_code=400, detail="라벨은 50자 이하여야 합니다.")
    name = (req.recipient_name or "").strip()
    if len(name) < 1:
        raise HTTPException(status_code=400, detail="수취인 이름을 입력해주세요.")
    phone = normalize_phone(req.recipient_phone)
    if len(phone) < 9:
        raise HTTPException(status_code=400, detail="전화번호를 입력해주세요.")
    zipcode = normalize_zip(req.zipcode)
    if len(zipcode) != 5:
        raise HTTPException(status_code=400, detail="우편번호 5자리가 필요합니다.")
    addr1 = (req.addr1 or "").strip()
    if len(addr1) < 2:
        raise HTTPException(status_code=400, detail="주소를 입력해주세요.")
    addr2 = (req.addr2 or "").strip()
    created_at = datetime.now(KST).isoformat(timespec="seconds")
    with get_connection() as con:
        # 중복 라벨이면 기존 레코드 반환 (1회만 저장)
        existing = con.execute(
            "SELECT id FROM saved_recipients WHERE user_id=? AND label=?",
            (user["user_id"], label),
        ).fetchone()
        if existing:
            return {"success": True, "id": existing[0], "label": label,
                    "recipient_name": name, "recipient_phone": phone,
                    "zipcode": zipcode, "addr1": addr1, "addr2": addr2}
        try:
            cur = con.execute(
                """
                INSERT INTO saved_recipients (user_id, label, recipient_name, recipient_phone, zipcode, addr1, addr2, created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (user["user_id"], label, name, phone, zipcode, addr1, addr2, created_at),
            )
            recipient_id = cur.lastrowid
            con.commit()
        except Exception as exc:
            if "UNIQUE constraint" in str(exc):
                row = con.execute(
                    "SELECT id FROM saved_recipients WHERE user_id=? AND label=?",
                    (user["user_id"], label),
                ).fetchone()
                if row:
                    return {"success": True, "id": row[0], "label": label,
                            "recipient_name": name, "recipient_phone": phone,
                            "zipcode": zipcode, "addr1": addr1, "addr2": addr2}
            raise
    return {
        "success": True,
        "id": recipient_id,
        "label": label,
        "recipient_name": name,
        "recipient_phone": phone,
        "zipcode": zipcode,
        "addr1": addr1,
        "addr2": addr2,
    }


@router.put("/saved-recipients/{recipient_id}")
def update_saved_recipient(recipient_id: int, req: SavedRecipientRequest, token: str):
    user = _get_user(token)
    ensure_pickup_tables()
    label = (req.label or "").strip()
    if len(label) < 1:
        raise HTTPException(status_code=400, detail="라벨을 입력해주세요.")
    if len(label) > 50:
        raise HTTPException(status_code=400, detail="라벨은 50자 이하여야 합니다.")
    name = (req.recipient_name or "").strip()
    if len(name) < 1:
        raise HTTPException(status_code=400, detail="수취인 이름을 입력해주세요.")
    phone = normalize_phone(req.recipient_phone)
    if len(phone) < 9:
        raise HTTPException(status_code=400, detail="전화번호를 입력해주세요.")
    zipcode = normalize_zip(req.zipcode)
    if len(zipcode) != 5:
        raise HTTPException(status_code=400, detail="우편번호 5자리가 필요합니다.")
    addr1 = (req.addr1 or "").strip()
    if len(addr1) < 2:
        raise HTTPException(status_code=400, detail="주소를 입력해주세요.")
    addr2 = (req.addr2 or "").strip()

    with get_connection() as con:
        row = con.execute(
            "SELECT id, user_id FROM saved_recipients WHERE id = ?",
            (recipient_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="저장된 수취인을 찾을 수 없습니다.")
        if row[1] != user["user_id"]:
            raise HTTPException(status_code=403, detail="다른 사용자의 수취인 정보는 수정할 수 없습니다.")

        # Check if new label conflicts with existing (excluding current record)
        existing = con.execute(
            "SELECT id FROM saved_recipients WHERE user_id = ? AND label = ? AND id != ?",
            (user["user_id"], label, recipient_id),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail=f"'{label}' 라벨은 이미 사용 중입니다.")

        con.execute(
            """
            UPDATE saved_recipients
            SET label = ?, recipient_name = ?, recipient_phone = ?,
                zipcode = ?, addr1 = ?, addr2 = ?
            WHERE id = ?
            """,
            (label, name, phone, zipcode, addr1, addr2, recipient_id),
        )
        con.commit()
    add_log(
        action_type="저장된주소지 수정",
        target_type="saved_recipient",
        target_id=str(recipient_id),
        target_name=label,
        user_nickname=user["nickname"],
        details=f"{name} / {zipcode}",
    )
    return {"success": True, "id": recipient_id, "label": label}


@router.delete("/saved-recipients/{recipient_id}")
def delete_saved_recipient(recipient_id: int, token: str):
    user = _get_user(token)
    ensure_pickup_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT id, user_id FROM saved_recipients WHERE id = ?",
            (recipient_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="저장된 수취인을 찾을 수 없습니다.")
        if row[1] != user["user_id"]:
            raise HTTPException(status_code=403, detail="다른 사용자의 수취인 정보는 삭제할 수 없습니다.")
        con.execute("DELETE FROM saved_recipients WHERE id = ?", (recipient_id,))
        con.commit()
    return {"success": True, "id": recipient_id}
