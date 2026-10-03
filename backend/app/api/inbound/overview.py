"""Batch overview calculation for internal and public views."""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from logic.db import get_connection

from .router import router
from .utils import (
    ITEM_STATUS_LABELS,
    STATUS_LABELS,
    _get_user,
    _image_url,
    _image_url_defect,
    _image_url_repair,
    _item_pending_qty,
)

# ═══════════════════════════════════════════════════════════════
#  입고 건별 통합 처리현황 (feat/inbound-unified-overview)
# ═══════════════════════════════════════════════════════════════


# ── 처리 단계 추론 ──────────────────────────────────────────────

def _infer_phase(
    *,
    status: str,
    pending_qty: int,
    defect_qty: int,
    repairing_qty: int,
    received_qty: int,
) -> str:
    """batch 상태 + 수량 현황 → 한국어 처리 단계."""
    if status in ("ocr_pending", "confirming"):
        return "입고 확인 중"
    if status == "done":
        return "최종 마감 완료"
    if status == "cancelled":
        return "취소"
    # 진행 중
    if repairing_qty > 0:
        return "수선 진행 중"
    if defect_qty > 0:
        return "불량 확인 중"
    if pending_qty > 0:
        return "양품화 진행 중"
    if received_qty > 0:
        return "양품화 진행 중"
    return "입고 확인 중"


# ── 배치 통합현황 계산 헬퍼 ─────────────────────────────────────

def _compute_batch_overview(batch_id: str, con, *, public: bool = False) -> Optional[dict]:
    """
    batch_id 기준 통합현황 dict 반환.

    public=True 이면 내부 전용 필드(원가, 직원명, 인증정보)를 제외한 공유 DTO 반환.
    반환값이 None 이면 배치가 존재하지 않음.

    수량 계산 원칙 (부분수량 모델, v2)
    ────────────────────────────────
    각 inbound_item 은 동일 품목 안에서 여러 상태의 수량을 동시에 가질 수 있다.

    source of truth: qty 컬럼 (status 는 화면용 대표상태)
      actual_qty       = 실총입고수량
      normal_qty       = 정상처리 부분수량
      defect_pending_qty = 불량판정중 부분수량
      repairing_qty    = 수선중 부분수량
      repair_done_qty  = 수선후정상 부분수량
      unrecoverable_qty= 회생불가 부분수량
      pending_qty (computed) = actual_qty - 위 모든 합

    불변식: actual_qty == pending + normal + defect + repairing + repair_done + unrecov
    """
    batch_row = con.execute("""
        SELECT id, vendor, inbound_date, status, memo,
               janggi_filename, janggi_date, janggi_no, wholesale,
               total_janggi_qty, total_actual_qty, total_missing_qty,
               created_by, closed_by, closed_at, created_at, updated_at, vendor_canonical
        FROM inbound_batches WHERE id=?
    """, (batch_id,)).fetchone()

    if not batch_row:
        return None

    # 품목 조회 (모든 부분수량 컬럼 포함, named alias 로 안전한 접근)
    _items_cur = con.execute("""
        SELECT id, batch_id, line_no, item_name, option_text, unit_price,
               janggi_qty, actual_qty, missing_qty, status,
               matched_barcode, matched_vendor, matched_product, matched_option,
               match_confidence, needs_matching, memo,
               supplier_location, supplier_contact, created_at, updated_at,
               confirmed_by, item_wholesale,
               COALESCE(normal_qty,        0) AS col_normal,
               inbound_item_id, defect_case_id,
               COALESCE(defect_pending_qty, 0) AS col_defect,
               COALESCE(repairing_qty,      0) AS col_repairing,
               COALESCE(repair_done_qty,    0) AS col_repair_done,
               COALESCE(unrecoverable_qty,  0) AS col_unrecov,
               COALESCE(actual_qty_confirmed, 0) AS col_qty_confirmed,
               photo_decision
        FROM inbound_items WHERE batch_id=? ORDER BY line_no, created_at
    """, (batch_id,))
    # dict 변환: 컬럼명으로 안전하게 접근
    _cols = [d[0] for d in _items_cur.description]
    items_raw = [dict(zip(_cols, row)) for row in _items_cur.fetchall()]

    item_ids = [r["id"] for r in items_raw]

    # 품목 사진
    photos_map: dict = {}
    if item_ids:
        ph_rows = con.execute(
            f"SELECT item_id, id, filename FROM inbound_item_photos "
            f"WHERE item_id IN ({','.join('?'*len(item_ids))})",
            item_ids
        ).fetchall()
        for ph in ph_rows:
            photos_map.setdefault(ph[0], []).append({
                "id": ph[1],
                "url": _image_url(ph[2]),
                "filename": ph[2],
            })

    # 불량일지 (inbound_item_id 연결)
    defect_map: dict = {}
    if item_ids:
        try:
            d_rows = con.execute(
                f"SELECT inbound_item_id, id, 날짜, 불량명, 수량, 비고, 처리결과, "
                f"before_image, after_image, extra_images "
                f"FROM defect_log WHERE inbound_item_id IN ({','.join('?'*len(item_ids))})"
                f" ORDER BY COALESCE(저장시간, 날짜) ASC",
                item_ids
            ).fetchall()
            for dr in d_rows:
                entry = {
                    "id": dr[1], "날짜": dr[2], "불량명": dr[3],
                    "수량": dr[4], "비고": dr[5], "처리결과": dr[6],
                    "before_image": _image_url_defect(dr[7]),
                    "after_image": _image_url_defect(dr[8]),
                }
                if not public:
                    entry["extra_images"] = dr[9]
                defect_map.setdefault(dr[0], []).append(entry)
        except Exception:
            pass  # 테이블 없으면 빈 맵

    # 수선일지 (inbound_item_id 연결)
    repair_map: dict = {}
    if item_ids:
        try:
            r_rows = con.execute(
                f"SELECT inbound_item_id, id, 날짜, 작업, 불량명, 수량, 비용, 비고, "
                f"before_image, after_image "
                f"FROM repair_work_log WHERE inbound_item_id IN ({','.join('?'*len(item_ids))})"
                f" ORDER BY COALESCE(저장시간, 날짜) ASC",
                item_ids
            ).fetchall()
            for rr in r_rows:
                entry = {
                    "id": rr[1], "날짜": rr[2], "작업": rr[3], "불량명": rr[4],
                    "수량": rr[5], "비고": rr[7],
                    "before_image": _image_url_repair(rr[8]),
                    "after_image": _image_url_repair(rr[9]),
                }
                if not public:
                    entry["비용"] = rr[6]
                repair_map.setdefault(rr[0], []).append(entry)
        except Exception:
            pass

    # ── 수량 집계 ──────────────────────────────────────────
    total_janggi = 0
    total_actual = 0
    total_missing = 0
    agg_pending = 0
    agg_normal = 0
    agg_defect = 0
    agg_repairing = 0
    agg_repaired_good = 0
    agg_unrecoverable = 0

    item_list = []
    for r in items_raw:
        # ── named dict 접근 (tuple magic index 사용 금지) ──────────
        item_id     = r["id"]
        janggi_qty  = r["janggi_qty"] or 0
        actual_qty  = r["actual_qty"] or 0
        missing_qty = r["missing_qty"] or 0
        status      = r["status"] or "pending"

        # ── 부분수량 source of truth: qty 컬럼 named 접근 ────────────
        i_normal    = r["col_normal"]
        i_defect    = r["col_defect"]
        i_repairing = r["col_repairing"]
        i_repaired  = r["col_repair_done"]
        i_unrecov   = r["col_unrecov"]
        i_pending   = _item_pending_qty(actual_qty, i_normal, i_defect, i_repairing, i_repaired, i_unrecov)

        total_janggi    += janggi_qty
        total_actual    += actual_qty
        total_missing   += missing_qty
        agg_pending     += i_pending
        agg_normal      += i_normal
        agg_defect      += i_defect
        agg_repairing   += i_repairing
        agg_repaired_good += i_repaired
        agg_unrecoverable += i_unrecov

        item_data: dict = {
            "id":          item_id,
            "line_no":     r["line_no"],
            "item_name":   r["item_name"],
            "option_text": r["option_text"],
            "janggi_qty":  janggi_qty,
            "actual_qty":  actual_qty,
            "missing_qty": missing_qty,
            "status":      status,
            "status_label": ITEM_STATUS_LABELS.get(status, status),
            "matched_barcode": r["matched_barcode"],
            "matched_vendor":  r["matched_vendor"],
            "matched_product": r["matched_product"],
            "matched_option":  r["matched_option"],
            "breakdown": {
                "normal":        i_normal,
                "pending":       i_pending,
                "defect":        i_defect,
                "repairing":     i_repairing,
                "repaired_good": i_repaired,
                "unrecoverable": i_unrecov,
            },
            "photos":      photos_map.get(item_id, []),
            "defect_logs": defect_map.get(item_id, []),
            "repair_logs": repair_map.get(item_id, []),
        }

        if not public:
            item_data["unit_price"]        = r["unit_price"]
            item_data["item_wholesale"]    = r["item_wholesale"]
            item_data["normal_qty_input"]  = i_normal
            item_data["needs_matching"]    = bool(r["needs_matching"])
            item_data["match_confidence"]  = r["match_confidence"]
            item_data["supplier_location"] = r["supplier_location"]
            item_data["supplier_contact"]  = r["supplier_contact"]
            item_data["confirmed_by"]      = r["confirmed_by"]
            item_data["memo"]              = r["memo"]
            item_data["defect_case_id"]    = r["defect_case_id"]
            item_data["inbound_item_id"]   = r["inbound_item_id"]
            item_data["actual_qty_confirmed"] = bool(r["col_qty_confirmed"])
            item_data["photo_decision"]    = r["photo_decision"]

        item_list.append(item_data)

    # ── 진행률 (0 나누기 안전 처리) ─────────────────────────
    final_good_qty   = agg_normal + agg_repaired_good
    received_qty     = total_actual
    expected_qty     = total_janggi

    inbound_progress = (
        round((received_qty + total_missing) / expected_qty * 100, 1)
        if expected_qty > 0 else 0.0
    )
    processing_progress = (
        round((agg_normal + agg_repaired_good + agg_unrecoverable) / received_qty * 100, 1)
        if received_qty > 0 else 0.0
    )

    phase = _infer_phase(
        status=batch_row[3],
        pending_qty=agg_pending,
        defect_qty=agg_defect,
        repairing_qty=agg_repairing,
        received_qty=received_qty,
    )

    # ── 처리 이력 타임라인 ─────────────────────────────────
    timeline: list = []
    for item_data in item_list:
        for d in item_data["defect_logs"]:
            timeline.append({
                "type": "defect",
                "date": d.get("날짜"),
                "item_name": item_data["item_name"],
                "detail": d.get("불량명"),
                "qty": d.get("수량"),
                "result": d.get("처리결과"),
                "id": d.get("id"),
            })
        for rr in item_data["repair_logs"]:
            timeline.append({
                "type": "repair",
                "date": rr.get("날짜"),
                "item_name": item_data["item_name"],
                "detail": rr.get("작업"),
                "qty": rr.get("수량"),
                "id": rr.get("id"),
            })
    timeline.sort(key=lambda e: (e.get("date") or ""), reverse=True)

    janggi_url = _image_url(batch_row[5]) if batch_row[5] else None

    batch_info: dict = {
        "id":            batch_row[0],
        "vendor":        batch_row[1],
        "inbound_date":  batch_row[2],
        "status":        batch_row[3],
        "status_label":  STATUS_LABELS.get(batch_row[3], batch_row[3]),
        "wholesale":     batch_row[8],
        "janggi_date":   batch_row[6],
        "janggi_no":     batch_row[7],
        "janggi_url":    janggi_url,
        "phase":         phase,
        "closed_at":     batch_row[14],
    }
    if not public:
        batch_info["memo"]       = batch_row[4]
        batch_info["created_by"] = batch_row[12]
        batch_info["closed_by"]  = batch_row[13]

    return {
        "batch": batch_info,
        "summary": {
            "expected_qty":      expected_qty,
            "received_qty":      received_qty,
            "missing_qty":       total_missing,
            "pending_qty":       agg_pending,
            "normal_qty":        agg_normal,
            "defect_pending_qty": agg_defect,
            "repairing_qty":     agg_repairing,
            "repaired_good_qty": agg_repaired_good,
            "unrecoverable_qty": agg_unrecoverable,
            "final_good_qty":    final_good_qty,
            "inbound_progress":  inbound_progress,
            "processing_progress": processing_progress,
        },
        "items":    item_list,
        "timeline": timeline[:50],
        "photos":   {"janggi": janggi_url},
    }


# ── 통합현황 조회 (내부, 인증 필요) ────────────────────────────

@router.get("/batches/{batch_id}/overview")
def get_batch_overview(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    """입고 건별 통합 처리현황 (내부 직원용, 로그인 필요)."""
    _get_user(authorization)
    with get_connection() as con:
        overview = _compute_batch_overview(batch_id, con, public=False)
    if overview is None:
        raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")
    return overview
