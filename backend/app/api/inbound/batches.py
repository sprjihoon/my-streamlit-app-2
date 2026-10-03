"""Inbound batch CRUD, close, grade, and stats."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import Header, HTTPException, Query

from backend.app.api.logs import add_log
from logic.db import get_connection

from .barcode import _resolve_vendor_names
from .photos import _cleanup_unmatched_inbox_photos
from .router import router
from .schemas import CloseRequest, InboundBatchCreate, InboundBatchUpdate
from .utils import (
    STATUS_LABELS,
    STATUS_VALUES,
    UPLOAD_DIR,
    _check_link_expiry,
    _get_item_photos,
    _get_user,
    _recalc_batch_totals,
    _serialize_batch,
    _serialize_item,
)

# ── 입고 배치 목록 ──────────────────────

@router.get("/batches")
def list_batches(
    vendor: Optional[str] = Query(None),
    wholesale: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    where = ["1=1"]
    params: list = []
    if vendor:
        # 별칭 포함 업체명 목록으로 확장 (alias → canonical 포함) + 부분일치
        vendor_names = _resolve_vendor_names(vendor)
        ph = ",".join("?" * len(vendor_names))
        where.append(f"(vendor IN ({ph}) OR vendor LIKE ? OR vendor_canonical IN ({ph}) OR vendor_canonical LIKE ?)")
        params += vendor_names + [f"%{vendor}%"] + vendor_names + [f"%{vendor}%"]
    if wholesale:
        where.append("wholesale LIKE ?"); params.append(f"%{wholesale}%")
    if status:
        where.append("status=?"); params.append(status)
    if date_from:
        where.append("inbound_date>=?"); params.append(date_from)
    if date_to:
        where.append("inbound_date<=?"); params.append(date_to)

    sql = f"""
        SELECT id, vendor, inbound_date, status, memo, receipt_id,
               janggi_filename, janggi_date, janggi_no, wholesale,
               total_janggi_qty, total_actual_qty, total_missing_qty,
               created_by, closed_by, closed_at, created_at, updated_at
        FROM inbound_batches
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    params += [limit, offset]
    with get_connection() as con:
        rows = con.execute(sql, params).fetchall()
        total = con.execute(
            f"SELECT COUNT(*) FROM inbound_batches WHERE {' AND '.join(where)}",
            params[:-2]
        ).fetchone()[0]
    return {"items": [_serialize_batch(r) for r in rows], "total": total}


# ── 입고 배치 생성 ──────────────────────

@router.post("/batches", status_code=201)
def create_batch(
    body: InboundBatchCreate,
    authorization: Optional[str] = Header(None),
):
    user = _get_user(authorization)
    batch_id = uuid.uuid4().hex
    now = datetime.utcnow().isoformat()
    with get_connection() as con:
        con.execute("""
            INSERT INTO inbound_batches
                (id, vendor, vendor_canonical, inbound_date, status, memo, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'ocr_pending', ?, ?, ?, ?)
        """, (batch_id, body.vendor, body.vendor_canonical or body.vendor,
              body.inbound_date, body.memo,
              body.created_by or user["nickname"], now, now))
        con.commit()
    add_log("inbound", "create_batch", f"입고 배치 생성: {body.vendor} {body.inbound_date}", user["user_id"])
    return {"id": batch_id, "status": "ocr_pending"}


# ── 입고 배치 상세 ──────────────────────

@router.get("/batches/{batch_id}")
def get_batch(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    # 실수량 입력 링크는 로그인 없이 접근 가능 (배치 ID가 비밀 토큰 역할)
    with get_connection() as con:
        row = con.execute("""
            SELECT id, vendor, inbound_date, status, memo, receipt_id,
                   janggi_filename, janggi_date, janggi_no, wholesale,
                   total_janggi_qty, total_actual_qty, total_missing_qty,
                   created_by, closed_by, closed_at, created_at, updated_at
            FROM inbound_batches WHERE id=?
        """, (batch_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")
        # 비로그인 공개 접근: 당일 자정 이후 만료
        if not authorization:
            _check_link_expiry(row[2])  # row[2] = inbound_date
        batch = _serialize_batch(row)

        items = con.execute("""
            SELECT id, batch_id, line_no, item_name, option_text, unit_price,
                   janggi_qty, actual_qty, missing_qty, status,
                   matched_barcode, matched_vendor, matched_product, matched_option,
                   match_confidence, needs_matching, memo,
                   supplier_location, supplier_contact, created_at, updated_at,
                   confirmed_by, item_wholesale,
                   actual_qty_confirmed, photo_decision
            FROM inbound_items WHERE batch_id=? ORDER BY line_no, created_at
        """, (batch_id,)).fetchall()
        item_list = []
        for item_row in items:
            item = _serialize_item(item_row)
            item["photos"] = _get_item_photos(con, item_row[0])
            item_list.append(item)

    batch["items"] = item_list
    return batch


# ── 입고 배치 수정 ──────────────────────

@router.patch("/batches/{batch_id}")
def update_batch(
    batch_id: str,
    body: InboundBatchUpdate,
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    fields, params = [], []
    if body.status is not None:
        if body.status not in STATUS_VALUES:
            raise HTTPException(status_code=400, detail=f"유효하지 않은 상태: {body.status}")
        fields.append("status=?"); params.append(body.status)
    if body.memo is not None:
        fields.append("memo=?"); params.append(body.memo)
    if body.vendor is not None:
        fields.append("vendor=?"); params.append(body.vendor)
    if body.inbound_date is not None:
        fields.append("inbound_date=?"); params.append(body.inbound_date)
    if not fields:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")
    fields.append("updated_at=CURRENT_TIMESTAMP")
    params.append(batch_id)
    with get_connection() as con:
        con.execute(f"UPDATE inbound_batches SET {', '.join(fields)} WHERE id=?", params)
        con.commit()
    return {"ok": True}


@router.post("/batches/{batch_id}/close")
def close_batch(
    batch_id: str,
    body: CloseRequest = CloseRequest(),
    authorization: Optional[str] = Header(None),
):
    """
    오전(am): confirming → inbound_done (양품화 중 시작, 확인 전 품목 없어야 함)
    오후(pm): inbound_done / grading / repairing → done
              장끼수량 = 미입고 + 일반정상 + 수선중 + 수선후정상 + 회생불가 검증 포함
    """
    close_type = body.close_type.lower().strip()
    if close_type not in ("am", "pm"):
        raise HTTPException(status_code=400, detail="close_type은 'am' 또는 'pm'이어야 합니다.")

    user = _get_user(authorization)
    with get_connection() as con:
        batch_row = con.execute(
            "SELECT status, total_janggi_qty, total_actual_qty, total_missing_qty FROM inbound_batches WHERE id=?",
            (batch_id,)
        ).fetchone()
        if not batch_row:
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")

        current_status = batch_row[0]
        total_janggi = batch_row[1] or 0

        # ── 오전 마감: confirming / ocr_pending → inbound_done ──────────────
        # 입고 확인 완료: 수량만 확정, 품목 status는 그대로 둠 (검품·양품화 미실행)
        if close_type == "am":
            if current_status not in ("confirming", "ocr_pending"):
                return {"ok": False, "warning": f"입고처리 완료는 '수량 확인 중' 또는 '장끼 등록 완료' 상태에서만 가능합니다. (현재: {STATUS_LABELS.get(current_status, current_status)})"}

            # ── 수량 미확인 품목 차단 ────────────────────────────────────────
            # actual_qty_confirmed=0 인 품목: 직원이 한 번도 수량을 확인하지 않은 상태
            unconfirmed_rows = con.execute(
                """SELECT id, line_no, item_name, janggi_qty
                   FROM inbound_items
                   WHERE batch_id=? AND actual_qty_confirmed=0
                   ORDER BY line_no""",
                (batch_id,)
            ).fetchall()
            if unconfirmed_rows:
                return {
                    "ok": False,
                    "warning": (
                        f"수량 미확인 품목이 {len(unconfirmed_rows)}개 있습니다. "
                        "각 품목의 실입고수량을 입력하거나 '수량 전부 장끼와 동일' 버튼을 사용해주세요."
                    ),
                    "unconfirmed_count": len(unconfirmed_rows),
                    "unconfirmed_items": [
                        {"id": r[0], "line_no": r[1], "item_name": r[2], "janggi_qty": r[3]}
                        for r in unconfirmed_rows
                    ],
                }

            # ── 사진 처리결정 미완료 차단 ─────────────────────────────────────
            # actual_qty >= 1 이면서 photo_decision 이 NULL 인 품목
            undecided_photo_rows = con.execute(
                """SELECT id, line_no, item_name, actual_qty
                   FROM inbound_items
                   WHERE batch_id=? AND actual_qty >= 1 AND photo_decision IS NULL
                   ORDER BY line_no""",
                (batch_id,)
            ).fetchall()
            if undecided_photo_rows:
                return {
                    "ok": False,
                    "warning": (
                        f"사진 처리결정이 없는 품목이 {len(undecided_photo_rows)}개 있습니다. "
                        "각 품목에 사진 연결·신상품·사진없음 중 하나를 선택해주세요."
                    ),
                    "undecided_photo_count": len(undecided_photo_rows),
                    "undecided_photo_items": [
                        {"id": r[0], "line_no": r[1], "item_name": r[2], "actual_qty": r[3]}
                        for r in undecided_photo_rows
                    ],
                }

            # ── photo_decision 실제 연결관계 검증 ─────────────────────────────
            # 'photo': 실제 연결된 사진이 최소 1장 있어야 함
            photo_no_file_rows = con.execute(
                """SELECT i.id, i.line_no, i.item_name
                   FROM inbound_items i
                   WHERE i.batch_id=? AND i.photo_decision='photo' AND i.actual_qty >= 1
                     AND NOT EXISTS (
                         SELECT 1 FROM inbound_item_photos p WHERE p.item_id = i.id
                     )
                   ORDER BY i.line_no""",
                (batch_id,)
            ).fetchall()
            if photo_no_file_rows:
                return {
                    "ok": False,
                    "warning": (
                        f"사진 연결로 표시됐지만 실제 사진이 없는 품목이 {len(photo_no_file_rows)}개 있습니다. "
                        "사진을 업로드하거나 처리결정을 변경해주세요."
                    ),
                    "photo_no_file_count": len(photo_no_file_rows),
                    "photo_no_file_items": [
                        {"id": r[0], "line_no": r[1], "item_name": r[2]}
                        for r in photo_no_file_rows
                    ],
                }

            # 'existing': 실제 상품마스터(repair_barcode) 연결이 있어야 함
            # matched_barcode 가 없거나 repair_barcode 에 존재하지 않으면 차단
            existing_no_product_rows = con.execute(
                """SELECT i.id, i.line_no, i.item_name
                   FROM inbound_items i
                   WHERE i.batch_id=? AND i.photo_decision='existing' AND i.actual_qty >= 1
                     AND (
                       i.matched_barcode IS NULL
                       OR i.matched_barcode = ''
                       OR NOT EXISTS (
                           SELECT 1 FROM repair_barcode rb WHERE rb.바코드 = i.matched_barcode
                       )
                     )
                   ORDER BY i.line_no""",
                (batch_id,)
            ).fetchall()
            if existing_no_product_rows:
                return {
                    "ok": False,
                    "warning": (
                        f"기존상품 연결로 표시됐지만 상품마스터에 없는 품목이 {len(existing_no_product_rows)}개 있습니다. "
                        "바코드를 연결하거나 처리결정을 변경해주세요."
                    ),
                    "existing_no_product_count": len(existing_no_product_rows),
                    "existing_no_product_items": [
                        {"id": r[0], "line_no": r[1], "item_name": r[2]}
                        for r in existing_no_product_rows
                    ],
                }

            next_status = "inbound_done"
            now = datetime.utcnow().isoformat()
            con.execute(
                "UPDATE inbound_batches SET status=?, updated_at=? WHERE id=?",
                (next_status, now, batch_id)
            )
            con.commit()

            # ── 미매칭 inbox 사진 정리 (입고완료 시 자동 삭제) ──────────────
            deleted_files = _cleanup_unmatched_inbox_photos(batch_id)

            add_log("inbound", "am_close",
                    f"오전 입고접수 완료: {batch_id} | 미매칭사진 {deleted_files}장 삭제",
                    user["user_id"])
            return {
                "ok": True,
                "close_type": "am",
                "status": next_status,
                "status_label": STATUS_LABELS[next_status],
                "message": "오전 입고접수 완료 — 양품화를 진행해주세요",
                "zero_qty_count": 0,  # 수량 미확인 품목은 이미 위에서 차단됨
                "deleted_inbox_photos": deleted_files,
            }

        # ── 오후 마감: inbound_done / grading / repairing → done ──
        # close_type == "pm"
        if current_status == "done":
            return {"ok": False, "warning": "이미 최종 마감된 입고건입니다."}
        if current_status not in ("inbound_done", "grading", "repairing"):
            return {"ok": False, "warning": f"오후 최종 마감은 '양품화 중' 또는 '수선 중' 상태에서만 가능합니다. (현재: {STATUS_LABELS.get(current_status, current_status)})"}

        # ── 미해결 부분수량 차단: qty 컬럼 기준 (통합현황과 동일 source) ──────
        defect_count = con.execute(
            "SELECT COALESCE(SUM(defect_pending_qty), 0) FROM inbound_items WHERE batch_id=?",
            (batch_id,)
        ).fetchone()[0]
        repair_count = con.execute(
            "SELECT COALESCE(SUM(repairing_qty), 0) FROM inbound_items WHERE batch_id=?",
            (batch_id,)
        ).fetchone()[0]
        if defect_count > 0 or repair_count > 0:
            return {
                "ok": False,
                "warning": (
                    f"미해결 수량이 있어 최종 마감할 수 없습니다. "
                    f"불량판정중 {defect_count}개, 수선중 {repair_count}개를 처리해주세요."
                ),
                "defect_qty": defect_count,
                "repair_qty": repair_count,
            }

        # ── 검품·양품화 완료 + 수량 정산 + 배치 종결 ─ 단일 transaction ──
        now = datetime.utcnow().isoformat()
        # 미처리(pending) 품목 → 정상처리(confirmed) 자동 이동 (idempotent)
        moved_count = con.execute(
            "SELECT COUNT(*) FROM inbound_items WHERE batch_id=? AND status='pending'",
            (batch_id,)
        ).fetchone()[0]
        if moved_count > 0:
            con.execute(
                """UPDATE inbound_items
                   SET status='confirmed', confirmed_by=COALESCE(confirmed_by, ?), updated_at=?
                   WHERE batch_id=? AND status='pending'""",
                (user["nickname"], now, batch_id)
            )
            _recalc_batch_totals(con, batch_id)

        # ── 수량 정산 ──
        # 공식: 장끼수량 = 미입고 + 일반정상 + 수선중 + 수선후정상 + 회생불가
        rows = con.execute("""
            SELECT status,
                   COALESCE(SUM(actual_qty),  0) AS actual_sum,
                   COALESCE(SUM(missing_qty), 0) AS missing_sum,
                   COALESCE(SUM(janggi_qty),  0) AS janggi_sum
            FROM inbound_items WHERE batch_id=? GROUP BY status
        """, (batch_id,)).fetchall()
        sd: dict[str, dict] = {r[0]: {"actual": r[1], "missing": r[2], "janggi": r[3]} for r in rows}

        # 각 카테고리 수량 (개수 기준) — moved_count 반영 후이므로 repair=0, defect=0 보장
        정상_qty     = sd.get("confirmed",     {}).get("actual", 0)
        수선중_qty    = sd.get("repair",        {}).get("actual", 0)   # 위에서 차단됐으므로 0
        수선후정상_qty = sd.get("done",          {}).get("actual", 0)
        회생불가_qty  = sd.get("unrecoverable", {}).get("actual", 0)
        미입고_qty = sum(v["missing"] for v in sd.values())

        formula_total = 미입고_qty + 정상_qty + 수선중_qty + 수선후정상_qty + 회생불가_qty
        discrepancy = total_janggi - formula_total

        # 배치 상태 변경을 같은 transaction 안에서 처리
        con.execute("""
            UPDATE inbound_batches
            SET status='done', closed_by=?, closed_at=?, updated_at=?
            WHERE id=?
        """, (user["nickname"], now, now, batch_id))
        con.commit()  # ← 여기서 단일 commit: item UPDATE + batch UPDATE 모두 포함

    add_log("inbound", "pm_close",
            f"오후 최종 마감: {batch_id} | 정상{정상_qty}/수선중{수선중_qty}/수선후{수선후정상_qty}/회생불가{회생불가_qty}/미입고{미입고_qty} (자동정상처리:{moved_count})",
            user["user_id"])

    result = {
        "ok": True,
        "close_type": "pm",
        "status": "done",
        "status_label": STATUS_LABELS["done"],
        "message": "오후 최종 마감 완료",
        "graded_count": moved_count,  # 자동으로 정상처리된 품목 수
        # ── 수량 정산 (공식 기준) ──
        "total_janggi_qty":    total_janggi,
        "정상_qty":            정상_qty,
        "수선중_qty":           수선중_qty,
        "수선후정상_qty":       수선후정상_qty,
        "회생불가_qty":         회생불가_qty,
        "미입고_qty":           미입고_qty,
        "formula_total":       formula_total,
        "discrepancy":         discrepancy,
        "formula_ok":          discrepancy == 0,
        "formula_str": (
            f"장끼{total_janggi} = 미입고{미입고_qty} + 정상{정상_qty} "
            f"+ 수선중{수선중_qty} + 수선후정상{수선후정상_qty} + 회생불가{회생불가_qty}"
            f" ({'✓ 일치' if discrepancy == 0 else f'⚠️ 차이 {discrepancy:+d}'})"
        ),
    }
    return result


# ── 검품·양품화 완료 (단독 실행) ─────────────────────────
# PM 최종 마감과 달리 배치 status를 done으로 바꾸지 않는다.
# 미처리(pending) 품목만 정상처리(confirmed)로 이동하고 나머지 상태는 건드리지 않는다.
# idempotent: 이미 confirmed 인 품목은 다시 변경하지 않는다.

@router.post("/batches/{batch_id}/grade-complete")
def grade_complete(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    검품·양품화 완료.
    - 남은 미처리(pending) 품목 → 정상처리(confirmed) 자동 이동
    - defect/repair/done/unrecoverable 품목은 그대로
    - 배치 status는 변경하지 않음 (최종 마감은 pm close 별도 실행)
    - 이 API를 여러 번 호출해도 수량이 중복 증가하지 않음 (idempotent)
    """
    user = _get_user(authorization)
    with get_connection() as con:
        batch_row = con.execute(
            "SELECT status FROM inbound_batches WHERE id=?", (batch_id,)
        ).fetchone()
        if not batch_row:
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")

        if batch_row[0] == "done":
            return {"ok": True, "moved": 0, "message": "이미 최종 마감된 배치입니다."}

        # 부분수량 모델: pending_qty > 0 인 품목 조회
        # pending_qty = actual - normal - defect - repairing - repair_done - unrecov
        pending_items = con.execute(
            """SELECT id, actual_qty,
                      COALESCE(normal_qty,0), COALESCE(defect_pending_qty,0),
                      COALESCE(repairing_qty,0), COALESCE(repair_done_qty,0),
                      COALESCE(unrecoverable_qty,0)
               FROM inbound_items
               WHERE batch_id=?
                 AND (actual_qty
                      - COALESCE(normal_qty,0) - COALESCE(defect_pending_qty,0)
                      - COALESCE(repairing_qty,0) - COALESCE(repair_done_qty,0)
                      - COALESCE(unrecoverable_qty,0)) > 0""",
            (batch_id,)
        ).fetchall()

        if not pending_items:
            return {"ok": True, "moved": 0, "message": "미처리 수량이 없습니다. 이미 완료 상태입니다."}

        now = datetime.utcnow().isoformat()
        # pending_qty 를 normal_qty 로 이동 (qty 컬럼 기반)
        # 최종 normal_qty = actual_qty - defect_pending - repairing - repair_done - unrecov
        con.execute(
            """UPDATE inbound_items
               SET normal_qty = actual_qty - COALESCE(defect_pending_qty,0)
                                           - COALESCE(repairing_qty,0)
                                           - COALESCE(repair_done_qty,0)
                                           - COALESCE(unrecoverable_qty,0),
                   actual_qty_confirmed = 1,
                   confirmed_by = COALESCE(confirmed_by, ?),
                   updated_at   = ?
               WHERE batch_id=?
                 AND (actual_qty
                      - COALESCE(normal_qty,0) - COALESCE(defect_pending_qty,0)
                      - COALESCE(repairing_qty,0) - COALESCE(repair_done_qty,0)
                      - COALESCE(unrecoverable_qty,0)) > 0""",
            (user["nickname"], now, batch_id)
        )
        _recalc_batch_totals(con, batch_id)
        con.commit()

    moved = len(pending_items)
    add_log("inbound", "grade_complete",
            f"검품·양품화 완료: {batch_id} | 자동정상처리 {moved}건", user["user_id"])
    return {
        "ok": True,
        "moved": moved,
        "message": f"미처리 {moved}건을 정상처리로 이동했습니다.",
    }


# ── 배치 삭제 (관리자) ──────────────────

@router.delete("/batches/{batch_id}")
def delete_batch(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    user = _get_user(authorization)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 삭제할 수 있습니다.")
    with get_connection() as con:
        # 사진 파일 삭제
        photos = con.execute(
            "SELECT filename FROM inbound_item_photos WHERE batch_id=?", (batch_id,)
        ).fetchall()
        for p in photos:
            try: (UPLOAD_DIR / p[0]).unlink(missing_ok=True)
            except Exception: pass
        # 장끼 이미지 삭제
        janggi = con.execute("SELECT janggi_filename FROM inbound_batches WHERE id=?", (batch_id,)).fetchone()
        if janggi and janggi[0]:
            try: (UPLOAD_DIR / janggi[0]).unlink(missing_ok=True)
            except Exception: pass
        con.execute("DELETE FROM inbound_item_photos WHERE batch_id=?", (batch_id,))
        con.execute("DELETE FROM inbound_items WHERE batch_id=?", (batch_id,))
        con.execute("DELETE FROM inbound_batches WHERE id=?", (batch_id,))
        con.commit()
    return {"ok": True}

# ── 입고 통계 ───────────────────────────

@router.get("/stats")
def get_stats(
    year_month: Optional[str] = Query(None, description="YYYY-MM"),
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    where = "1=1"
    params: list = []
    if year_month:
        where = "inbound_date LIKE ?"
        params.append(f"{year_month}%")
    with get_connection() as con:
        rows = con.execute(f"""
            SELECT status, COUNT(*), SUM(total_janggi_qty), SUM(total_actual_qty), SUM(total_missing_qty)
            FROM inbound_batches WHERE {where}
            GROUP BY status
        """, params).fetchall()
    return {
        "by_status": [
            {"status": r[0], "status_label": STATUS_LABELS.get(r[0], r[0]),
             "count": r[1], "janggi_qty": r[2] or 0,
             "actual_qty": r[3] or 0, "missing_qty": r[4] or 0}
            for r in rows
        ]
    }
