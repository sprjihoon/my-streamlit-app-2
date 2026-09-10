"""
backend/app/services/inbound_bot.py - 입고모드 봇 흐름
──────────────────────────────────────────────────────
대화 흐름:
  1. 입고 → 진행중 입고 충돌 확인 → 화주사 묻기
  2. 화주사 입력 → 후보 매칭 → 선택 → 배치 생성 → 장끼 사진 요청
  3. 장끼 사진 수신 → OCR + 매칭 → 제품사진 inbox 수집
  4. 사진 끝 → 링크 제공
  5. 후속 명령 처리 (미입고, 마감, 현황 등)
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.config import settings
from backend.app.services.conversation_state import get_conversation_manager
from logic.db import get_connection

logger = logging.getLogger(__name__)

# ─────────────────────────────────────
# 상수
# ─────────────────────────────────────

YES_RE = re.compile(r"^(네|넵|예|응|어|맞아|맞아요|그래|좋아|ㅇㅇ|ㅇ)$")
CLOSE_RE = re.compile(r"(입고\s*마감|마감\s*해|마감\s*할게|완료\s*해|작업\s*끝)")
MISSING_RE = re.compile(r"(\d+)\s*번\s*(미입고|안왔어|없어|못받았어)")
CANCEL_RE = re.compile(r"^(취소|그만|아니야|아니)$")
PHOTO_END_RE = re.compile(r"^(사진\s*끝|사진\s*완료|사진\s*다\s*보냈어|사진\s*다\s*올렸어)$")
# "1" or "1번" 선택 응답
SELECT_RE = re.compile(r"^(\d+)번?$")

EXPIRED_MSG = "입고 작업이 만료됐어요. `입고`를 다시 입력해 새로 시작해주세요."


# ─────────────────────────────────────
# Conversation state helpers
# ─────────────────────────────────────

def _get_pending(user_id: str, channel_id: Optional[str]) -> Dict[str, Any]:
    state = get_conversation_manager().get_state(user_id, channel_id)
    if not state or state.get("expired"):
        return {}
    data = state.get("pending_data") or {}
    if data.get("entry_type") != "inbound":
        return {}
    return data


def _set_pending(user_id: str, channel_id: str, data: Dict[str, Any], question: str = "") -> None:
    data = {**data, "entry_type": "inbound"}
    get_conversation_manager().set_state(
        user_id=user_id,
        channel_id=channel_id or "",
        pending_data=data,
        missing=[],
        last_question=question,
    )


def _clear_pending(user_id: str, channel_id: Optional[str]) -> None:
    get_conversation_manager().clear_state(user_id, channel_id)


def pending_is_inbound(user_id: str, channel_id: Optional[str]) -> bool:
    state = get_conversation_manager().get_state(user_id, channel_id)
    return bool(
        state
        and not state.get("expired")
        and (state.get("pending_data") or {}).get("entry_type") == "inbound"
    )


# ─────────────────────────────────────
# 화주사 후보 검색
# ─────────────────────────────────────

def _find_vendor_candidates(text: str) -> List[Dict]:
    """입력 텍스트와 유사한 화주사 후보 최대 5개를 반환한다."""
    norm = text.strip().lower()
    with get_connection() as con:
        rows = con.execute(
            "SELECT vendor, name FROM vendors WHERE active IS NULL OR active != 'N' ORDER BY vendor"
        ).fetchall()
        # 별칭도 포함
        alias_rows = con.execute(
            "SELECT alias, vendor FROM aliases WHERE file_type='work_log'"
        ).fetchall()

    alias_map: Dict[str, str] = {}
    for alias, vendor in alias_rows:
        alias_map[alias.lower()] = vendor

    candidates = []
    for (vendor, name) in rows:
        v_lower = (vendor or "").lower()
        n_lower = (name or "").lower()
        # 완전 일치 우선
        if norm in (v_lower, n_lower):
            candidates.insert(0, {"vendor": vendor, "name": name or vendor, "match": "exact"})
        elif norm in v_lower or v_lower in norm or norm in n_lower or n_lower in norm:
            candidates.append({"vendor": vendor, "name": name or vendor, "match": "partial"})

    # 별칭 일치
    matched_alias = alias_map.get(norm)
    if matched_alias:
        for c in candidates:
            if c["vendor"] == matched_alias:
                c["match"] = "alias"
                break
        else:
            # vendor 테이블에서 찾기
            with get_connection() as con:
                row = con.execute("SELECT vendor, name FROM vendors WHERE vendor=?", (matched_alias,)).fetchone()
            if row:
                candidates.insert(0, {"vendor": row[0], "name": row[1] or row[0], "match": "alias"})

    return candidates[:5]


def _exact_vendor_match(text: str) -> Optional[str]:
    """완전 일치 화주사 1개 반환 (별칭 포함). 없으면 None."""
    norm = text.strip().lower()
    with get_connection() as con:
        rows = con.execute(
            "SELECT vendor FROM vendors WHERE LOWER(vendor)=? OR LOWER(name)=?",
            (norm, norm)
        ).fetchall()
        if rows:
            return rows[0][0]
        # 별칭 확인
        alias_row = con.execute(
            "SELECT vendor FROM aliases WHERE LOWER(alias)=? AND file_type='work_log' LIMIT 1",
            (norm,)
        ).fetchone()
        if alias_row:
            return alias_row[0]
    return None


# ─────────────────────────────────────
# 진행중 입고 충돌 감지
# ─────────────────────────────────────

def _active_batch_for_user(user_id: str, channel_id: Optional[str]) -> Optional[Dict]:
    """현재 사용자·채팅방에서 진행 중인 입고 배치를 반환한다."""
    pending = _get_pending(user_id, channel_id)
    batch_id = pending.get("batch_id")
    if not batch_id:
        return None
    batch = _get_batch(batch_id)
    if not batch:
        return None
    # 완료/마감된 배치는 진행 중으로 보지 않음
    if batch["status"] in ("done", "inbound_done") and pending.get("step") == "active":
        return None
    return batch


# ─────────────────────────────────────
# 제품사진 inbox (SHA-256 기반 중복 체크)
# ─────────────────────────────────────

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inbox_photo_count(batch_id: str) -> int:
    """입고 전용 제품사진 inbox의 현재 장수."""
    with get_connection() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM inbound_product_photo_inbox WHERE batch_id=? AND is_deleted=0",
            (batch_id,)
        ).fetchone()
    return row[0] if row else 0


def _add_inbox_photo(
    batch_id: str,
    user_id: str,
    channel_id: str,
    image_data: bytes,
    filename: str,
) -> Dict:
    """
    제품사진 inbox에 사진을 추가한다.
    - SHA-256 중복이면 {'duplicate': True, 'count': N} 반환
    - 성공이면 {'added': True, 'count': N} 반환
    """
    from backend.app.api.inbound import UPLOAD_DIR, ensure_inbound_tables
    ensure_inbound_tables()
    _ensure_inbox_table()

    sha = _sha256(image_data)

    with get_connection() as con:
        existing = con.execute(
            "SELECT id FROM inbound_product_photo_inbox WHERE batch_id=? AND sha256=? AND is_deleted=0",
            (batch_id, sha)
        ).fetchone()
        if existing:
            count = con.execute(
                "SELECT COUNT(*) FROM inbound_product_photo_inbox WHERE batch_id=? AND is_deleted=0",
                (batch_id,)
            ).fetchone()[0]
            return {"duplicate": True, "count": count}

        # 파일 저장
        ext = (filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg")[:4]
        photo_id = uuid.uuid4().hex
        stored_name = f"inbound_product_{batch_id}_{photo_id}.{ext}"
        dest = UPLOAD_DIR / stored_name
        dest.write_bytes(image_data)

        now = datetime.utcnow().isoformat()
        con.execute("""
            INSERT INTO inbound_product_photo_inbox
                (id, batch_id, user_id, channel_id, sha256, filename, stored_filename, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (photo_id, batch_id, user_id, channel_id, sha, filename, stored_name, now))
        con.commit()

        count = con.execute(
            "SELECT COUNT(*) FROM inbound_product_photo_inbox WHERE batch_id=? AND is_deleted=0",
            (batch_id,)
        ).fetchone()[0]

    return {"added": True, "count": count, "id": photo_id}


def _ensure_inbox_table() -> None:
    """inbound_product_photo_inbox 테이블 생성 (없을 경우)."""
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_product_photo_inbox (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                filename TEXT,
                stored_filename TEXT,
                item_id TEXT,
                is_deleted INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()


# ─────────────────────────────────────
# 배치/품목 DB 조회
# ─────────────────────────────────────

def _get_batch(batch_id: str) -> Optional[Dict]:
    with get_connection() as con:
        row = con.execute(
            "SELECT id, vendor, inbound_date, status, total_janggi_qty, total_actual_qty, total_missing_qty, wholesale FROM inbound_batches WHERE id=?",
            (batch_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "vendor": row[1], "inbound_date": row[2], "status": row[3],
        "total_janggi_qty": row[4], "total_actual_qty": row[5],
        "total_missing_qty": row[6], "wholesale": row[7],
    }


def _get_items(batch_id: str) -> List[Dict]:
    with get_connection() as con:
        rows = con.execute(
            "SELECT id, line_no, item_name, option_text, janggi_qty, actual_qty, missing_qty, status, needs_matching FROM inbound_items WHERE batch_id=? ORDER BY line_no",
            (batch_id,)
        ).fetchall()
    return [{"id": r[0], "line_no": r[1], "item_name": r[2], "option_text": r[3],
             "janggi_qty": r[4], "actual_qty": r[5], "missing_qty": r[6],
             "status": r[7], "needs_matching": bool(r[8])} for r in rows]


def _create_batch(vendor: str, created_by: str) -> str:
    batch_id = uuid.uuid4().hex
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.utcnow().isoformat()
    with get_connection() as con:
        con.execute("""
            INSERT INTO inbound_batches
                (id, vendor, inbound_date, status, created_by, created_at, updated_at)
            VALUES (?, ?, ?, 'ocr_pending', ?, ?, ?)
        """, (batch_id, vendor, today, created_by, now, now))
        con.commit()
    return batch_id


def _update_item_status(item_id: str, missing_qty: int) -> None:
    with get_connection() as con:
        con.execute(
            "UPDATE inbound_items SET missing_qty=?, status='missing' WHERE id=?",
            (missing_qty, item_id)
        )
        # 배치 집계 갱신
        row = con.execute("SELECT batch_id FROM inbound_items WHERE id=?", (item_id,)).fetchone()
        if row:
            totals = con.execute("""
                SELECT COALESCE(SUM(janggi_qty),0), COALESCE(SUM(actual_qty),0), COALESCE(SUM(missing_qty),0)
                FROM inbound_items WHERE batch_id=?
            """, (row[0],)).fetchone()
            con.execute(
                "UPDATE inbound_batches SET total_janggi_qty=?, total_actual_qty=?, total_missing_qty=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (totals[0], totals[1], totals[2], row[0])
            )
        con.commit()


# ─────────────────────────────────────
# 링크 생성
# ─────────────────────────────────────

def _work_link(batch_id: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/inbound/{batch_id}"


# ─────────────────────────────────────
# OCR + 매칭 (비동기, inbound.py 로직 호출)
# ─────────────────────────────────────

async def _run_ocr_and_match(batch_id: str, image_data: bytes, filename: str, vendor: str) -> Dict:
    """이미지 데이터로 이미지 정규화 → OCR 실행 → 품목 매칭 → DB 저장.

    실패 시 OcrError 또는 ValueError를 re-raise. DB는 성공 시에만 변경.
    """
    from backend.app.api.inbound import (
        UPLOAD_DIR, ensure_inbound_tables,
        _normalize_image, _run_ocr, OcrError, _match_barcode,
    )
    import uuid as _uuid

    ensure_inbound_tables()

    # 이미지 정규화 (ValueError → 호출자가 처리)
    norm_bytes, mime = _normalize_image(image_data)

    # OCR 실행 (OcrError → 호출자가 처리, DB 미변경)
    ocr_result = await _run_ocr(norm_bytes, mime)

    # OCR 성공 → 파일 저장 후 DB 업데이트
    janggi_filename = f"{_uuid.uuid4().hex}.jpg"
    (UPLOAD_DIR / janggi_filename).write_bytes(norm_bytes)

    receipt_data = ocr_result.get("receipt", {})
    items_data = ocr_result.get("items", [])

    wholesale = receipt_data.get("storeName")
    janggi_date = receipt_data.get("orderDate")
    janggi_no = receipt_data.get("receiptNo")

    now = datetime.utcnow().isoformat()
    created_items = []

    with get_connection() as con:
        # 기존 OCR 품목 삭제 (재시도 교체)
        con.execute(
            "DELETE FROM inbound_items WHERE batch_id=? AND (memo LIKE '%OCR%' OR memo IS NULL)",
            (batch_id,),
        )

        for i, item in enumerate(items_data):
            item_id = _uuid.uuid4().hex
            item_name = item.get("itemName") or ""
            color = item.get("color") or ""
            size_str = item.get("size") or ""
            option_text = item.get("optionText") or ""
            combined_option = " ".join(filter(None, [color, size_str, option_text])) or None
            unit_price = item.get("unitPrice")
            janggi_qty = int(item.get("quantity") or 0)

            match = _match_barcode(vendor, item_name, combined_option, wholesale)
            needs_review = bool(item.get("needsReview", False))
            needs_matching = match["needs_matching"] or needs_review

            con.execute("""
                INSERT INTO inbound_items
                    (id, batch_id, line_no, item_name, option_text, unit_price,
                     janggi_qty, actual_qty, missing_qty, status,
                     matched_barcode, matched_vendor, matched_product, matched_option,
                     match_confidence, needs_matching, memo, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'pending', ?, ?, ?, ?, ?, ?, 'OCR', ?)
            """, (
                item_id, batch_id, i + 1, item_name, combined_option, unit_price,
                janggi_qty,
                match["matched_barcode"], match["matched_vendor"],
                match["matched_product"], match["matched_option"],
                match["match_confidence"], int(needs_matching),
                now,
            ))
            created_items.append({
                **match,
                "item_name": item_name,
                "option_text": combined_option,
                "janggi_qty": janggi_qty,
                "needs_matching": needs_matching,
            })

        totals = con.execute(
            "SELECT COALESCE(SUM(janggi_qty),0) FROM inbound_items WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        con.execute("""
            UPDATE inbound_batches
            SET janggi_filename=?, janggi_date=?, janggi_no=?, wholesale=?,
                total_janggi_qty=?, status='confirming', updated_at=?
            WHERE id=?
        """, (janggi_filename, janggi_date, janggi_no, wholesale, totals[0], now, batch_id))
        con.commit()

    matched = sum(1 for it in created_items if not it["needs_matching"])
    return {
        "item_count": len(created_items),
        "matched_count": matched,
        "needs_count": len(created_items) - matched,
        "wholesale": wholesale,
        "janggi_date": janggi_date,
    }


# ─────────────────────────────────────
# 텍스트 메시지 핸들러
# ─────────────────────────────────────

async def handle_user_text(
    user_id: str,
    channel_id: str,
    text: str,
    user_name: Optional[str] = None,
) -> Optional[str]:
    """
    입고모드 텍스트 처리.
    반환값: 봇 응답 문자열 (None이면 응답 없음)
    """
    text = (text or "").strip()
    pending = _get_pending(user_id, channel_id)
    step = pending.get("step", "")
    batch_id = pending.get("batch_id")

    # ── 취소 ──
    if CANCEL_RE.match(text):
        _clear_pending(user_id, channel_id)
        return "입고 작업을 취소했어요."

    # ── Step: 진행중 입고 충돌 — 기존 계속 / 새 입고 선택 대기 ──
    if step == "wait_conflict_choice":
        sel = SELECT_RE.match(text)
        active_batch_id = pending.get("active_batch_id")
        if sel:
            choice = int(sel.group(1))
            if choice == 1 and active_batch_id:
                # 기존 계속
                batch = _get_batch(active_batch_id)
                _set_pending(user_id, channel_id, {
                    "step": "active",
                    "batch_id": active_batch_id,
                    "vendor": batch["vendor"] if batch else "",
                }, "")
                return f"기존 입고를 계속 진행합니다.\n작업 링크:\n{_work_link(active_batch_id)}"
            elif choice == 2:
                # 새 입고 시작 — 기존 pending 초기화 후 화주사 대기
                _set_pending(user_id, channel_id, {"step": "wait_vendor"}, "어느 화주사의 입고인가요?")
                return "새 입고를 시작합니다.\n어느 화주사의 입고인가요?"
        return "1 또는 2로 선택해주세요.\n1. 기존 입고 계속\n2. 새 입고 시작"

    # ── Step: 화주사 후보 선택 대기 ──
    if step == "wait_vendor_choice":
        candidates = pending.get("vendor_candidates", [])
        sel = SELECT_RE.match(text)
        if sel:
            idx = int(sel.group(1)) - 1
            if 0 <= idx < len(candidates):
                vendor = candidates[idx]["vendor"]
                new_batch_id = _create_batch(vendor, user_name or user_id)
                _set_pending(user_id, channel_id, {
                    "step": "wait_janggi",
                    "batch_id": new_batch_id,
                    "vendor": vendor,
                }, "장끼 사진을 보내주세요.")
                return (
                    f"✅ {vendor} 입고를 시작했어요.\n"
                    f"장끼(납품서) 사진을 보내주세요."
                )
            return f"1~{len(candidates)} 중에서 선택해주세요."
        # 새 입력으로 다시 검색
        return await _handle_vendor_input(user_id, channel_id, text, user_name)

    # ── Step 1: 화주사 대기 중 ──
    if step == "wait_vendor":
        return await _handle_vendor_input(user_id, channel_id, text, user_name)

    # ── Step 2: 장끼 이미지 대기 중 (텍스트가 오면 안내) ──
    if step == "wait_janggi":
        return "장끼(납품서) 사진을 보내주세요. (이미지 파일을 첨부해주세요)"

    # ── 배치 있는 상태에서 후속 명령 처리 ──
    if batch_id:
        batch = _get_batch(batch_id)
        if not batch:
            _clear_pending(user_id, channel_id)
            return "입고 배치를 찾을 수 없어요. `입고`를 다시 입력해 새로 시작해주세요."

        # 사진 끝 → 매칭 링크 제공
        if PHOTO_END_RE.match(text):
            return _handle_photo_end(batch_id, user_id, channel_id)

        # 미입고 처리: "3번 미입고", "2번 안왔어"
        m = MISSING_RE.search(text)
        if m:
            line_no = int(m.group(1))
            items = _get_items(batch_id)
            matched_item = next((it for it in items if it["line_no"] == line_no), None)
            if matched_item:
                _update_item_status(matched_item["id"], matched_item["janggi_qty"])
                return f"{line_no}번 품목을 미입고로 처리했어요. ({matched_item['item_name'] or '품목'})"
            return f"{line_no}번 품목을 찾을 수 없어요."

        # 마감
        if CLOSE_RE.search(text):
            return await _try_close(batch_id, user_name or user_id)

        # 현황 보기
        if any(kw in text for kw in ("현황", "상태", "어떻게", "몇개", "몇 개", "요약")):
            return _summary_text(batch_id)

        # 링크 재요청
        if any(kw in text for kw in ("링크", "주소", "url", "URL")):
            return f"작업 링크:\n{_work_link(batch_id)}"

        return (
            f"입고모드 진행 중이에요. ({batch['vendor']} / {batch['status']})\n"
            f"• 제품사진 보내기 (순서 무관)\n"
            f"• `사진 끝` — 매칭 링크 받기\n"
            f"• N번 미입고\n"
            f"• 현황\n"
            f"• 입고 마감\n"
            f"• 취소"
        )

    # ── 초기 진입: 진행 중인 입고 충돌 확인 ──
    # (이미 pending이 없는 경우 — apply_mode_command에서 설정된 wait_vendor와 다름)
    _set_pending(user_id, channel_id, {"step": "wait_vendor"}, "어느 화주사의 입고인가요?")
    return "입고모드를 시작했어요.\n어느 화주사의 입고인가요?"


async def _handle_vendor_input(
    user_id: str,
    channel_id: str,
    text: str,
    user_name: Optional[str],
) -> str:
    """화주사 입력 처리 — 완전 일치 시 즉시 생성, 불명확 시 후보 제시."""
    vendor = text.strip()
    if not vendor:
        return "화주사 이름을 입력해주세요."

    # 완전 일치 확인
    exact = _exact_vendor_match(vendor)
    if exact:
        new_batch_id = _create_batch(exact, user_name or user_id)
        _set_pending(user_id, channel_id, {
            "step": "wait_janggi",
            "batch_id": new_batch_id,
            "vendor": exact,
        }, "장끼 사진을 보내주세요.")
        return (
            f"✅ {exact} 입고를 시작했어요.\n"
            f"장끼(납품서) 사진을 보내주세요."
        )

    # 부분 일치 후보
    candidates = _find_vendor_candidates(vendor)
    if candidates:
        lines = ["어느 화주사인가요? 번호로 선택해주세요."]
        for i, c in enumerate(candidates, 1):
            lines.append(f"{i}. {c['name']} ({c['vendor']})")
        lines.append(f"\n다른 화주사라면 이름을 다시 입력해주세요.")
        _set_pending(user_id, channel_id, {
            "step": "wait_vendor_choice",
            "vendor_candidates": candidates,
        }, "화주사를 선택해주세요.")
        return "\n".join(lines)

    # 후보도 없으면 그냥 이름 그대로 생성
    new_batch_id = _create_batch(vendor, user_name or user_id)
    _set_pending(user_id, channel_id, {
        "step": "wait_janggi",
        "batch_id": new_batch_id,
        "vendor": vendor,
    }, "장끼 사진을 보내주세요.")
    return (
        f"✅ {vendor} 입고를 시작했어요.\n"
        f"장끼(납품서) 사진을 보내주세요."
    )


def _handle_photo_end(batch_id: str, user_id: str, channel_id: str) -> str:
    """사진 끝 명령 처리 — 장끼 판독 상태 확인 후 매칭 링크 제공."""
    batch = _get_batch(batch_id)
    if not batch:
        return "입고 배치를 찾을 수 없어요."

    if batch["status"] == "ocr_pending":
        return "아직 장끼 판독이 완료되지 않았어요. 장끼(납품서) 사진을 먼저 보내주세요."

    _ensure_inbox_table()
    count = _inbox_photo_count(batch_id)

    if count == 0:
        return (
            f"아직 제품사진을 받지 못했어요.\n"
            f"사진을 보내거나 매칭 링크에서 직접 작업해주세요.\n"
            f"매칭 링크:\n{_work_link(batch_id)}"
        )

    link = _work_link(batch_id)
    return (
        f"📸 제품사진 {count}장 접수 완료!\n\n"
        f"아래 링크에서 사진을 품목에 연결해주세요.\n"
        f"🔗 {link}"
    )


# ─────────────────────────────────────
# 이미지 수신 핸들러
# ─────────────────────────────────────

async def handle_image(
    user_id: str,
    channel_id: str,
    image_data: bytes,
    filename: str,
    user_name: Optional[str] = None,
) -> Optional[str]:
    """
    입고모드 이미지 수신 핸들러.
    - wait_janggi 단계: 장끼(납품서) OCR + 매칭
    - active 단계: 제품사진 inbox 수집 (SHA-256 중복 체크)
    """
    pending = _get_pending(user_id, channel_id)
    step = pending.get("step", "")
    batch_id = pending.get("batch_id")
    vendor = pending.get("vendor", "")

    # 화주사 대기 중
    if step in ("wait_vendor", "wait_vendor_choice", "wait_conflict_choice"):
        return "먼저 화주사를 선택해주세요."

    # 장끼 대기 단계
    if step == "wait_janggi":
        if not batch_id:
            return "입고 배치가 없어요. `입고`를 다시 입력해주세요."
        return await _handle_janggi_image(user_id, channel_id, batch_id, vendor, image_data, filename, user_name)

    # active 단계 — 제품사진 수집
    if step == "active" and batch_id:
        return await _handle_product_photo(user_id, channel_id, batch_id, image_data, filename)

    return None


async def _handle_janggi_image(
    user_id: str,
    channel_id: str,
    batch_id: str,
    vendor: str,
    image_data: bytes,
    filename: str,
    user_name: Optional[str],
) -> str:
    """장끼(납품서) 사진 OCR 처리."""
    try:
        result = await _run_ocr_and_match(batch_id, image_data, filename, vendor)
    except Exception as e:
        from backend.app.api.inbound import OcrError
        if isinstance(e, OcrError):
            return (
                f"장끼 판독 실패: {e.user_msg}\n"
                f"다시 촬영해 보내주세요.\n"
                f"또는 작업 링크에서 직접 입력해주세요:\n{_work_link(batch_id)}"
            )
        if isinstance(e, ValueError):
            return (
                f"이미지 오류: {e}\n"
                f"다시 촬영해 보내주세요."
            )
        logger.exception("OCR unexpected error")
        return (
            f"장끼 OCR 중 오류가 발생했어요.\n"
            f"작업 링크에서 수동으로 입력해주세요.\n{_work_link(batch_id)}"
        )

    if result.get("item_count", 0) == 0:
        return (
            "품목을 찾지 못했어요. 다시 촬영해 보내주세요.\n"
            f"또는 작업 링크에서 직접 입력해주세요:\n{_work_link(batch_id)}"
        )

    _set_pending(user_id, channel_id, {
        "step": "active",
        "batch_id": batch_id,
        "vendor": vendor,
    }, "")

    link = _work_link(batch_id)
    item_count = result["item_count"]
    matched = result["matched_count"]
    needs = result["needs_count"]
    wholesale = result.get("wholesale") or ""

    lines = [
        "📄 장끼 분석 완료!",
        (f"도매처: {wholesale}" if wholesale else ""),
        f"총 {item_count}개 품목 ({matched}개 자동매칭" + (f", {needs}개 확인필요" if needs else "") + ")",
        "",
        "이제 제품사진을 순서 무관하게 보내주세요.",
        "다 보내셨으면 `사진 끝` 을 입력해주세요.",
        "",
        f"🔗 직접 작업 링크:\n{link}",
    ]
    return "\n".join(l for l in lines if l is not None)


async def _handle_product_photo(
    user_id: str,
    channel_id: str,
    batch_id: str,
    image_data: bytes,
    filename: str,
) -> str:
    """제품사진 inbox에 사진을 추가한다. 중복이면 조용히 무시."""
    result = _add_inbox_photo(batch_id, user_id, channel_id, image_data, filename)
    if result.get("duplicate"):
        return None  # 중복 사진은 조용히 무시
    count = result.get("count", 0)
    return f"현재 제품사진 {count}장 접수"


# ─────────────────────────────────────
# 마감 처리
# ─────────────────────────────────────

async def _try_close(batch_id: str, user_name: str) -> str:
    with get_connection() as con:
        row = con.execute("SELECT status, total_janggi_qty, total_actual_qty, total_missing_qty FROM inbound_batches WHERE id=?", (batch_id,)).fetchone()
        if not row:
            return "입고 배치를 찾을 수 없어요."
        status, janggi_qty, actual_qty, missing_qty = row

        if status == "confirming":
            pending_cnt = con.execute("SELECT COUNT(*) FROM inbound_items WHERE batch_id=? AND status='pending'", (batch_id,)).fetchone()[0]
            if pending_cnt > 0:
                return f"아직 확인 전 품목이 {pending_cnt}개 있어요. 실수량을 모두 입력한 후 마감해주세요."
            next_status = "inbound_done"
        elif status == "inbound_done":
            next_status = "grading"
        elif status in ("grading", "repairing"):
            next_status = "done"
        else:
            return f"현재 상태({status})에서는 마감할 수 없어요."

        now = datetime.utcnow().isoformat()
        con.execute(
            "UPDATE inbound_batches SET status=?, closed_by=?, closed_at=?, updated_at=? WHERE id=?",
            (next_status, user_name, now if next_status == "done" else None, now, batch_id)
        )
        con.commit()

    labels = {
        "inbound_done": "입고접수 완료",
        "grading": "양품화 중",
        "done": "최종완료",
    }
    return f"✅ {labels.get(next_status, next_status)}로 처리됐어요.\n장끼 {janggi_qty}개 / 실입고 {actual_qty}개 / 미입고 {missing_qty}개"


# ─────────────────────────────────────
# 현황 요약
# ─────────────────────────────────────

def _summary_text(batch_id: str) -> str:
    batch = _get_batch(batch_id)
    if not batch:
        return "입고 정보를 찾을 수 없어요."
    items = _get_items(batch_id)
    pending = sum(1 for it in items if it["status"] == "pending")
    confirmed = sum(1 for it in items if it["status"] == "confirmed")
    missing = sum(1 for it in items if it["status"] == "missing")
    defect = sum(1 for it in items if it["status"] in ("defect", "repair", "unrecoverable"))

    lines = [
        f"📦 {batch['vendor']} 입고 현황",
        f"장끼수량: {batch['total_janggi_qty']}개",
        f"실입고:   {batch['total_actual_qty']}개",
        f"미입고:   {batch['total_missing_qty']}개",
        f"품목별 — 확인전 {pending} / 정상 {confirmed} / 미입고 {missing} / 불량 {defect}",
        f"작업 링크: {_work_link(batch_id)}",
    ]
    return "\n".join(lines)
