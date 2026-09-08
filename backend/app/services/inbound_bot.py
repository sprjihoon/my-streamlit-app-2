"""
backend/app/services/inbound_bot.py - 입고모드 봇 흐름
──────────────────────────────────────────────────────
대화 흐름:
  1. 입고 → 화주사 묻기
  2. 화주사 입력 → 배치 생성 → 장끼 사진 요청
  3. 장끼 사진 수신 → OCR + 매칭 → 작업 링크 전송
  4. 후속 명령 처리 (미입고, 마감 등)
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional

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
    """이미지 데이터로 OCR 실행 후 품목 매칭."""
    from pathlib import Path
    from backend.app.api.inbound import (
        UPLOAD_DIR, ensure_inbound_tables, _run_ocr, _match_barcode
    )
    import uuid as _uuid

    ensure_inbound_tables()

    # 파일 저장
    ext = Path(filename).suffix.lower() or ".jpg"
    janggi_filename = f"{_uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / janggi_filename).write_bytes(image_data)

    # OCR
    ocr_result = await _run_ocr(UPLOAD_DIR / janggi_filename)
    receipt_data = (ocr_result or {}).get("receipt", {})
    items_data = (ocr_result or {}).get("items", [])

    wholesale = receipt_data.get("storeName")
    janggi_date = receipt_data.get("orderDate")
    janggi_no = receipt_data.get("receiptNo")

    now = datetime.utcnow().isoformat()
    created_items = []

    with get_connection() as con:
        # 기존 OCR 품목 삭제
        con.execute("DELETE FROM inbound_items WHERE batch_id=? AND memo='OCR'", (batch_id,))

        for i, item in enumerate(items_data):
            item_id = _uuid.uuid4().hex
            item_name = item.get("itemName") or ""
            option_text = item.get("color") or item.get("optionText") or ""
            unit_price = item.get("unitPrice")
            janggi_qty = int(item.get("quantity") or 0)

            match = _match_barcode(vendor, item_name, option_text or None, wholesale)

            con.execute("""
                INSERT INTO inbound_items
                    (id, batch_id, line_no, item_name, option_text, unit_price,
                     janggi_qty, actual_qty, missing_qty, status,
                     matched_barcode, matched_vendor, matched_product, matched_option,
                     match_confidence, needs_matching, memo, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'pending', ?, ?, ?, ?, ?, ?, 'OCR', ?)
            """, (
                item_id, batch_id, i + 1, item_name, option_text or None, unit_price,
                janggi_qty,
                match["matched_barcode"], match["matched_vendor"],
                match["matched_product"], match["matched_option"],
                match["match_confidence"], int(match["needs_matching"]),
                now,
            ))
            created_items.append({**match, "item_name": item_name, "option_text": option_text, "janggi_qty": janggi_qty, "needs_matching": match["needs_matching"]})

        # 배치 업데이트
        totals = con.execute("""
            SELECT COALESCE(SUM(janggi_qty),0) FROM inbound_items WHERE batch_id=?
        """, (batch_id,)).fetchone()
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

    # 취소
    if CANCEL_RE.match(text):
        _clear_pending(user_id, channel_id)
        return "입고 작업을 취소했어요."

    # ── Step 1: 화주사 대기 중 ──
    if step == "wait_vendor":
        vendor = text.strip()
        if not vendor:
            return "화주사 이름을 입력해주세요."
        # 배치 생성
        new_batch_id = _create_batch(vendor, user_name or user_id)
        _set_pending(user_id, channel_id, {
            "step": "wait_janggi",
            "batch_id": new_batch_id,
            "vendor": vendor,
        }, "장끼 사진을 보내주세요.")
        link = _work_link(new_batch_id)
        return (
            f"✅ {vendor} 입고 등록됐어요.\n"
            f"장끼 사진을 이 채팅에 보내주세요.\n\n"
            f"작업 링크 (직원 공유용):\n{link}"
        )

    # ── Step 2: 장끼 이미지 대기 중 (텍스트가 오면 안내) ──
    if step == "wait_janggi":
        return "장끼 사진을 보내주세요. (이미지 파일을 첨부해주세요)"

    # ── 배치 있는 상태에서 후속 명령 처리 ──
    if batch_id:
        batch = _get_batch(batch_id)
        if not batch:
            _clear_pending(user_id, channel_id)
            return "입고 배치를 찾을 수 없어요. `입고`를 다시 입력해 새로 시작해주세요."

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
            f"• 장끼 사진 보내기\n"
            f"• N번 미입고\n"
            f"• 현황\n"
            f"• 입고 마감\n"
            f"• 취소"
        )

    # ── 초기 진입 (화주사 없음) ──
    _set_pending(user_id, channel_id, {"step": "wait_vendor"}, "어느 화주사의 입고인가요?")
    return "입고모드를 시작했어요.\n어느 화주사의 입고인가요?"


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
    """장끼 이미지 수신 → OCR + 매칭 → 결과 응답"""
    pending = _get_pending(user_id, channel_id)
    step = pending.get("step", "")
    batch_id = pending.get("batch_id")
    vendor = pending.get("vendor", "")

    if step != "wait_janggi" or not batch_id:
        return None  # 입고모드지만 장끼 대기 상태가 아님

    try:
        result = await _run_ocr_and_match(batch_id, image_data, filename, vendor)
    except Exception as e:
        logger.exception("OCR failed")
        return f"장끼 OCR 중 오류가 발생했어요: {e}\n작업 링크에서 수동으로 입력해주세요.\n{_work_link(batch_id)}"

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
        f"📄 장끼 분석 완료!",
        f"{'도매처: ' + wholesale if wholesale else ''}",
        f"총 {item_count}개 품목 ({matched}개 자동매칭" + (f", {needs}개 확인필요" if needs else "") + ")",
        "",
        f"🔗 실수량 입력 링크 (직원 공유용):",
        link,
        "",
        "• 미입고는 `N번 미입고` 로 알려주세요",
        "• 작업이 끝나면 `입고 마감`",
    ]
    return "\n".join(l for l in lines if l is not None)


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
