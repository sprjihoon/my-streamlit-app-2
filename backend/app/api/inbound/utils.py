"""Shared inbound helpers. Behavior matches the former inbound module."""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import logging
import secrets
import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

from backend.app.config import settings
from logic.db import get_connection

logger = logging.getLogger("backend.app.api.inbound")

UPLOAD_DIR = Path(settings.UPLOAD_DIR) / "inbound"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────
# 비밀번호 해시 헬퍼
# ─────────────────────────────────────

def _hash_password(plain: str) -> str:
    """SHA-256 + random 16-byte hex salt.
    저장 형식: sha256:{salt}:{hex_digest}
    원문 비밀번호는 이 함수 호출 후 즉시 폐기해야 합니다.
    """
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{plain}".encode("utf-8")).hexdigest()
    return f"sha256:{salt}:{digest}"


def _verify_password(plain: str, stored: str) -> bool:
    """해시 비교 (타이밍 공격 방지 compare_digest 사용).
    stored 가 sha256:… 형식이 아닌 경우(레거시 플레인텍스트) 도 처리.
    """
    if not stored:
        return not plain  # 저장 비번 없음 → 빈 값만 통과
    if stored.startswith("sha256:"):
        parts = stored.split(":", 2)
        if len(parts) != 3:
            return False
        _, salt, h = parts
        candidate = hashlib.sha256(f"{salt}:{plain}".encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate, h)
    # 레거시: 플레인텍스트로 저장된 경우 (해시 마이그레이션 전 데이터)
    return hmac.compare_digest(plain, stored)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}

# ─────────────────────────────────────
# 상태 정의
# ─────────────────────────────────────

STATUS_VALUES = ("ocr_pending", "confirming", "inbound_done", "grading", "repairing", "done", "cancelled")
STATUS_LABELS = {
    "ocr_pending": "장끼 확인 중",
    "confirming":  "수량 확인 중",
    "inbound_done": "양품화 중",          # 오전 입고접수 완료 후 상태
    "grading":     "양품화 중(수선처리)",  # 수선 품목 있을 때
    "repairing":   "수선 중",
    "done":        "최종완료",
    "cancelled":   "취소",
}

ITEM_STATUS_VALUES = ("pending", "confirmed", "missing", "defect", "repair", "unrecoverable", "done", "etc")
ITEM_STATUS_LABELS = {
    "pending": "확인 전",
    "confirmed": "정상",
    "missing": "미입고",
    "defect": "불량",
    "repair": "수선대기",
    "unrecoverable": "회생불가",
    "done": "완료",
    "etc": "기타",
}

_PHOTO_DECISION_VALUES = {'photo', 'existing', 'new', 'none'}

# ── 부분수량 상태 컬럼 매핑 ────────────────────────────────────
# 각 상태 이름 → inbound_items 컬럼명 (pending 은 computed 이므로 None)
_QTY_STATE_COL: dict = {
    "pending":       None,
    "normal":        "normal_qty",
    "defect":        "defect_pending_qty",
    "repairing":     "repairing_qty",
    "repair_done":   "repair_done_qty",
    "unrecoverable": "unrecoverable_qty",
}


def _item_pending_qty(actual: int, normal: int, defect: int, repairing: int,
                      repair_done: int, unrecov: int) -> int:
    """품목의 현재 미처리(pending) 수량 = actual - 모든 확정 수량."""
    return max(0, actual - normal - defect - repairing - repair_done - unrecov)


def move_item_qty(
    con,
    item_id: str,
    from_state: str,
    to_state: str,
    qty: int,
    *,
    actor: str = "system",
    ref_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict:
    """
    단일 transaction 안에서 품목의 부분수량을 from_state → to_state 로 이동한다.

    ◆ 불변식 보장
      - qty > 0
      - from_state 의 현재 수량 >= qty
      - 이동 후 모든 부분수량 합 == actual_qty
    ◆ ref_id 로 idempotency: 같은 ref_id+item_id 조합이 이미 이력에 있으면 skip
    ◆ caller 가 commit 책임 (이 함수는 commit 하지 않음)
    """
    if qty <= 0:
        raise ValueError(f"이동수량은 1 이상이어야 합니다. qty={qty}")
    if from_state not in _QTY_STATE_COL or to_state not in _QTY_STATE_COL:
        raise ValueError(f"유효하지 않은 상태값. from={from_state}, to={to_state}")
    if from_state == to_state:
        raise ValueError(f"출발·도착 상태가 동일합니다: {from_state}")

    # idempotency
    if ref_id:
        if con.execute(
            "SELECT 1 FROM inbound_item_qty_transitions WHERE ref_id=? AND item_id=? LIMIT 1",
            (ref_id, item_id)
        ).fetchone():
            return {"skipped": True, "reason": "already_moved", "ref_id": ref_id}

    # 현재 수량 조회
    row = con.execute(
        """SELECT actual_qty, normal_qty, defect_pending_qty,
                  repairing_qty, repair_done_qty, unrecoverable_qty
           FROM inbound_items WHERE id=?""",
        (item_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"품목을 찾을 수 없습니다: {item_id}")

    actual, normal, defect, repairing, repair_done, unrecov = [v or 0 for v in row]
    pending = _item_pending_qty(actual, normal, defect, repairing, repair_done, unrecov)

    cur = {
        "pending":       pending,
        "normal":        normal,
        "defect":        defect,
        "repairing":     repairing,
        "repair_done":   repair_done,
        "unrecoverable": unrecov,
    }

    if cur[from_state] < qty:
        raise ValueError(
            f"이동수량({qty})이 현재 {from_state} 수량({cur[from_state]})을 초과합니다."
        )

    # atomic UPDATE (pending 은 computed 이므로 컬럼 없음 → 차이로 표현)
    set_parts = ["updated_at=CURRENT_TIMESTAMP"]
    from_col = _QTY_STATE_COL[from_state]
    to_col   = _QTY_STATE_COL[to_state]
    if from_col:
        set_parts.append(f"{from_col}={from_col}-{qty}")
    if to_col:
        set_parts.append(f"{to_col}={to_col}+{qty}")

    con.execute(f"UPDATE inbound_items SET {','.join(set_parts)} WHERE id=?", (item_id,))

    # 이력 기록
    hist_id = uuid.uuid4().hex
    con.execute(
        """INSERT INTO inbound_item_qty_transitions
               (id, item_id, from_state, to_state, qty, actor, ref_id, reason, moved_at)
           VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
        (hist_id, item_id, from_state, to_state, qty, actor, ref_id, reason)
    )

    return {
        "moved": True,
        "from": from_state,
        "to": to_state,
        "qty": qty,
        "after": {k: (cur[k] - qty if k == from_state else cur[k] + qty if k == to_state else cur[k])
                  for k in cur},
    }

# ─────────────────────────────────────
# 인증 헬퍼
# ─────────────────────────────────────

def _get_user(token: Optional[str]) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    tok = token.replace("Bearer ", "").strip()
    with get_connection() as con:
        row = con.execute(
            """SELECT u.user_id, u.nickname, u.is_admin
               FROM sessions s JOIN users u ON s.user_id = u.user_id
               WHERE s.token = ?""",
            (tok,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    return {"user_id": row[0], "nickname": row[1], "is_admin": bool(row[2])}


_KST = _dt.timezone(_dt.timedelta(hours=9))

def _check_link_expiry(inbound_date_str: str) -> None:
    """비로그인 공개 링크 만료 확인 — 당일(KST) 자정 이후이면 410 반환."""
    try:
        batch_date = _dt.date.fromisoformat(inbound_date_str)
        today_kst  = _dt.datetime.now(_KST).date()
        if today_kst > batch_date:
            raise HTTPException(
                status_code=410,
                detail=f"링크가 만료되었습니다. (유효일: {inbound_date_str})"
            )
    except HTTPException:
        raise
    except Exception:
        pass  # 날짜 파싱 실패 시 허용


# ─────────────────────────────────────
# 내부 유틸
# ─────────────────────────────────────

async def _save_upload(file: UploadFile) -> str:
    ext = Path(file.filename or "img.jpg").suffix.lower() or ".jpg"
    if ext not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식: {ext}")
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / filename).write_bytes(await file.read())
    return filename


def _image_url(filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    return f"/inbound/photos/{filename}"


def _recalc_batch_totals(con, batch_id: str):
    """품목 수량 집계를 배치에 반영"""
    row = con.execute("""
        SELECT
            COALESCE(SUM(janggi_qty), 0),
            COALESCE(SUM(actual_qty), 0),
            COALESCE(SUM(missing_qty), 0)
        FROM inbound_items WHERE batch_id = ?
    """, (batch_id,)).fetchone()
    if row:
        con.execute("""
            UPDATE inbound_batches
            SET total_janggi_qty=?, total_actual_qty=?, total_missing_qty=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (row[0], row[1], row[2], batch_id))


def _serialize_batch(row) -> dict:
    return {
        "id": row[0],
        "vendor": row[1],
        "inbound_date": row[2],
        "status": row[3],
        "status_label": STATUS_LABELS.get(row[3], row[3]),
        "memo": row[4],
        "receipt_id": row[5],
        "janggi_filename": row[6],
        "janggi_date": row[7],
        "janggi_no": row[8],
        "wholesale": row[9],
        "total_janggi_qty": row[10],
        "total_actual_qty": row[11],
        "total_missing_qty": row[12],
        "created_by": row[13],
        "closed_by": row[14],
        "closed_at": row[15],
        "created_at": row[16],
        "updated_at": row[17],
    }


def _serialize_item(row) -> dict:
    return {
        "id": row[0],
        "batch_id": row[1],
        "line_no": row[2],
        "item_name": row[3],
        "option_text": row[4],
        "unit_price": row[5],
        "janggi_qty": row[6],
        "actual_qty": row[7],
        "missing_qty": row[8],
        "status": row[9],
        "status_label": ITEM_STATUS_LABELS.get(row[9], row[9]),
        "matched_barcode": row[10],
        "matched_vendor": row[11],
        "matched_product": row[12],
        "matched_option": row[13],
        "match_confidence": row[14],
        "needs_matching": bool(row[15]),
        "memo": row[16],
        "supplier_location": row[17],
        "supplier_contact": row[18],
        "created_at": row[19],
        "updated_at": row[20],
        "confirmed_by": row[21] if len(row) > 21 else None,
        "item_wholesale": row[22] if len(row) > 22 else None,
        "actual_qty_confirmed": bool(row[23]) if len(row) > 23 and row[23] is not None else False,
        "photo_decision": row[24] if len(row) > 24 else None,
    }


def _get_item_photos(con, item_id: str) -> list:
    rows = con.execute(
        "SELECT id, filename, created_at FROM inbound_item_photos WHERE item_id=? ORDER BY created_at",
        (item_id,)
    ).fetchall()
    return [{"id": r[0], "url": _image_url(r[1]), "filename": r[1], "created_at": r[2]} for r in rows]

# ── 이미지 URL 헬퍼 (수선/불량일지용) ──────────────────────────

def _image_url_repair(filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    return f"/repair-log/image/{filename}"


def _image_url_defect(filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    return f"/defect-log/image/{filename}"
