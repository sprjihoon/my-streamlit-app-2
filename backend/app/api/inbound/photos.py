"""Item photos and inbox photo matching."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from logic.db import get_connection

from .router import router
from .schemas import InboxPhotoLink
from .utils import (
    UPLOAD_DIR,
    _check_link_expiry,
    _get_user,
    _image_url,
    _save_upload,
    logger,
)

# ── 제품 사진 업로드 ──────────────────

@router.post("/items/{item_id}/photos", status_code=201)
async def upload_item_photo(
    item_id: str,
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    # 작업자도 사진 업로드 가능 (인증 불필요)
    # 비로그인 공개 접근: 당일 자정 이후 만료
    with get_connection() as con:
        item_row = con.execute("SELECT batch_id FROM inbound_items WHERE id=?", (item_id,)).fetchone()
        if not item_row:
            raise HTTPException(status_code=404, detail="품목을 찾을 수 없습니다.")
        batch_id = item_row[0]
        if not authorization:
            date_row = con.execute(
                "SELECT inbound_date FROM inbound_batches WHERE id=?", (batch_id,)
            ).fetchone()
            if date_row:
                _check_link_expiry(date_row[0])

    filename = await _save_upload(file)
    photo_id = uuid.uuid4().hex
    with get_connection() as con:
        con.execute(
            "INSERT INTO inbound_item_photos (id, item_id, batch_id, filename) VALUES (?, ?, ?, ?)",
            (photo_id, item_id, batch_id, filename)
        )
        # 사진 업로드 시 photo_decision을 'photo'로 자동 설정 (이미 결정됐으면 유지)
        con.execute(
            "UPDATE inbound_items SET photo_decision=COALESCE(photo_decision,'photo') WHERE id=?",
            (item_id,)
        )
        con.commit()
    return {"id": photo_id, "url": _image_url(filename)}


# ── 제품 사진 삭제 ─────────────────────

@router.delete("/items/{item_id}/photos/{photo_id}")
def delete_item_photo(
    item_id: str,
    photo_id: str,
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    with get_connection() as con:
        row = con.execute(
            "SELECT filename FROM inbound_item_photos WHERE id=? AND item_id=?",
            (photo_id, item_id)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="사진을 찾을 수 없습니다.")
        try: (UPLOAD_DIR / row[0]).unlink(missing_ok=True)
        except Exception: pass
        con.execute("DELETE FROM inbound_item_photos WHERE id=?", (photo_id,))
        con.commit()
    return {"ok": True}


# ── 사진 파일 서빙 ─────────────────────

@router.get("/photos/{filename}")
def serve_photo(
    filename: str,
    authorization: Optional[str] = Header(None),
):
    # 작업자도 사진 조회 가능 (인증 불필요)
    # 경로 탈출 방지
    safe_name = Path(filename).name
    path = UPLOAD_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="사진을 찾을 수 없습니다.")
    return FileResponse(path)


# ── 미매칭 inbox 사진 정리 ────────────────────────────────────

def _cleanup_unmatched_inbox_photos(batch_id: str) -> int:
    """
    입고완료(am close) 시 item_id가 NULL인 미매칭 inbox 사진을
    파일 삭제 + DB soft-delete 처리한다.
    반환: 삭제된 사진 수
    """
    with get_connection() as con:
        rows = con.execute(
            """SELECT id, stored_filename
               FROM inbound_product_photo_inbox
               WHERE batch_id=? AND item_id IS NULL AND is_deleted=0""",
            (batch_id,)
        ).fetchall()

        if not rows:
            return 0

        deleted = 0
        for photo_id, stored_filename in rows:
            # 파일 삭제
            if stored_filename:
                try:
                    file_path = UPLOAD_DIR / Path(stored_filename).name
                    if file_path.exists():
                        file_path.unlink()
                except Exception as e:
                    logger.warning(f"inbox 사진 파일 삭제 실패 ({stored_filename}): {e}")
            # DB soft-delete
            con.execute(
                "UPDATE inbound_product_photo_inbox SET is_deleted=1 WHERE id=?",
                (photo_id,)
            )
            deleted += 1

        con.commit()
    return deleted


# ── 제품사진 inbox 조회 (봇이 수집한 미분류 사진) ──────────

@router.get("/batches/{batch_id}/inbox")
def list_inbox_photos(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    봇 채팅에서 수집된 미분류 제품사진 목록 반환.
    item_id가 NULL인 항목이 매칭 대상.
    """
    _get_user(authorization)
    with get_connection() as con:
        batch_row = con.execute(
            "SELECT id FROM inbound_batches WHERE id=?", (batch_id,)
        ).fetchone()
        if not batch_row:
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")
        rows = con.execute(
            """SELECT id, sha256, filename, stored_filename, item_id, is_deleted, created_at
               FROM inbound_product_photo_inbox
               WHERE batch_id=? AND is_deleted=0
               ORDER BY created_at ASC""",
            (batch_id,)
        ).fetchall()
    return {
        "batch_id": batch_id,
        "photos": [
            {
                "id":               r[0],
                "sha256":           r[1],
                "filename":         r[2],
                "stored_filename":  r[3],              # 멀티아이템 링크 비교용
                "url":              _image_url(r[3]) if r[3] else None,
                "item_id":          r[4],
                "matched":          r[4] is not None,  # 어느 품목이든 연결됐으면 True
                "created_at":       r[6],
            }
            for r in rows
        ],
        "total": len(rows),
        "unmatched": sum(1 for r in rows if r[4] is None),
    }


@router.post("/items/{item_id}/photos/from-inbox", status_code=201)
def link_inbox_photo_to_item(
    item_id: str,
    body: InboxPhotoLink,
    authorization: Optional[str] = Header(None),
):
    """
    봇 inbox 사진을 특정 품목에 연결한다.

    ◆ 파일 복제 없음: stored_filename 을 inbound_item_photos 에서 공유
    ◆ 같은 inbox 사진을 여러 품목(옵션 등)에 연결 가능
    ◆ 같은 (item_id, stored_filename) 중복은 기존 ID 반환 (idempotent)
    ◆ 연결 성공 후에만 photo_decision='photo' 설정
    ◆ inbox 사진과 품목이 다른 배치이면 거부
    """
    _get_user(authorization)
    with get_connection() as con:
        # inbox 사진 조회
        inbox = con.execute(
            "SELECT id, batch_id, stored_filename, is_deleted FROM inbound_product_photo_inbox WHERE id=?",
            (body.inbox_photo_id,)
        ).fetchone()
        if not inbox:
            raise HTTPException(status_code=404, detail="inbox 사진을 찾을 수 없습니다.")
        if inbox[3]:
            raise HTTPException(status_code=400, detail="삭제된 사진입니다.")
        inbox_batch_id = inbox[1]
        stored_filename = inbox[2]
        if not stored_filename:
            raise HTTPException(status_code=400, detail="저장된 파일 경로가 없는 사진입니다.")

        # 품목 조회
        item = con.execute(
            "SELECT id, batch_id FROM inbound_items WHERE id=?", (item_id,)
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="품목을 찾을 수 없습니다.")

        # 다른 배치 사진 연결 차단
        if inbox_batch_id != item[1]:
            raise HTTPException(status_code=400, detail="다른 입고건의 사진은 연결할 수 없습니다.")

        # 중복 연결 방지 (같은 품목 + 같은 파일)
        existing = con.execute(
            "SELECT id FROM inbound_item_photos WHERE item_id=? AND filename=?",
            (item_id, stored_filename)
        ).fetchone()
        if existing:
            return {
                "ok": True,
                "id": existing[0],
                "url": _image_url(stored_filename),
                "duplicated": True,
            }

        # 관계 생성 (파일 복사 없음)
        photo_id = uuid.uuid4().hex
        con.execute(
            "INSERT INTO inbound_item_photos (id, item_id, batch_id, filename, created_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (photo_id, item_id, item[1], stored_filename)
        )
        # inbox 사진에 item_id 기록 (최종 연결 항목 추적용)
        con.execute(
            "UPDATE inbound_product_photo_inbox SET item_id=? WHERE id=?",
            (item_id, body.inbox_photo_id)
        )
        # 연결 성공 후에만 photo_decision='photo'
        con.execute(
            "UPDATE inbound_items SET photo_decision=COALESCE(photo_decision,'photo'), updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (item_id,)
        )
        con.commit()

    return {
        "ok": True,
        "id": photo_id,
        "url": _image_url(stored_filename),
        "duplicated": False,
    }


# ── inbox 사진-품목 연결 해제 ─────────────────────────────────────

@router.delete("/items/{item_id}/photos/from-inbox/{inbox_photo_id}", status_code=200)
def unlink_inbox_photo_from_item(
    item_id: str,
    inbox_photo_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    from-inbox 으로 연결된 inbox 사진을 품목에서 해제한다.

    ◆ inbound_item_photos 에서 해당 관계 행만 삭제 (파일·inbox 행은 유지)
    ◆ 해당 inbox 사진을 이 품목 외 다른 품목도 쓰지 않으면 inbox 행의 item_id → NULL
    ◆ 해제 후 다른 inbox 사진 연결 또는 업로드 사진 사용 가능
    """
    _get_user(authorization)
    with get_connection() as con:
        inbox = con.execute(
            "SELECT stored_filename FROM inbound_product_photo_inbox WHERE id=?",
            (inbox_photo_id,)
        ).fetchone()
        if not inbox:
            raise HTTPException(status_code=404, detail="inbox 사진을 찾을 수 없습니다.")
        stored_fn = inbox[0]

        # inbound_item_photos 에서 해당 관계 삭제
        con.execute(
            "DELETE FROM inbound_item_photos WHERE item_id=? AND filename=?",
            (item_id, stored_fn)
        )

        # 이 파일이 다른 품목에도 연결되어 있는지 확인
        other_links = con.execute(
            "SELECT COUNT(*) FROM inbound_item_photos WHERE filename=?",
            (stored_fn,)
        ).fetchone()[0]

        # 다른 품목에도 연결이 없으면 inbox 행의 item_id → NULL (다시 미매칭 상태)
        if other_links == 0:
            con.execute(
                "UPDATE inbound_product_photo_inbox SET item_id=NULL WHERE id=?",
                (inbox_photo_id,)
            )

        con.commit()

    return {"ok": True, "unlinked": True, "inbox_photo_id": inbox_photo_id, "item_id": item_id}
