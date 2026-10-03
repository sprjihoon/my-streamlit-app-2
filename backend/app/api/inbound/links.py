"""Defect-log and repair-log links on inbound items."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import Header, HTTPException

from logic.db import get_connection

from .router import router
from .schemas import DefectLogLink, RepairLogLink
from .utils import _QTY_STATE_COL, _get_user, _item_pending_qty, move_item_qty


# ── 수선일지 연결: 허용된 업무액션 → 수량전환 매핑 ──────────────
# 입고품목 연결 수선일지는 서버가 결정하는 (from, to) 전환을 사용한다.
_REPAIR_ACTION_TRANSITIONS: dict = {
    "수선접수":   ("defect", "repairing"),      # 불량판정중 → 수선중
    "수선완료":   ("repairing", "repair_done"),  # 수선중 → 수선후정상
    "회생불가":   ("repairing", "unrecoverable"),# 수선중 → 회생불가
    "재판정정상": ("defect", "normal"),           # 불량판정중 → 정상 (재판정)
}


@router.post("/items/{item_id}/defect-log", status_code=201)
def link_defect_log(
    item_id: str,
    body: DefectLogLink,
    authorization: Optional[str] = Header(None),
):
    """
    입고 품목에서 불량일지 생성 (원자 트랜잭션).

    ◆ pending_qty 확인 → defect_log INSERT → pending→defect 수량이동 → commit
    ◆ 어느 단계든 실패하면 전체 rollback (불량로그·수량이력 모두 저장 안 됨)
    ◆ pending 부족 시 409 (INSUFFICIENT_PENDING) 반환
    """
    from backend.app.api.defect_log import ensure_defect_tables
    ensure_defect_tables()
    user = _get_user(authorization)

    if body.수량 < 1:
        raise HTTPException(status_code=400, detail="수량은 1 이상이어야 합니다.")

    with get_connection() as con:
        # 1. 품목 + 부분수량 조회
        item = con.execute(
            """SELECT id, batch_id, item_name, option_text,
                      matched_barcode, matched_vendor, matched_product, matched_option,
                      actual_qty,
                      COALESCE(normal_qty,0), COALESCE(defect_pending_qty,0),
                      COALESCE(repairing_qty,0), COALESCE(repair_done_qty,0),
                      COALESCE(unrecoverable_qty,0)
               FROM inbound_items WHERE id=?""",
            (item_id,)
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="품목을 찾을 수 없습니다.")

        batch = con.execute(
            "SELECT inbound_date, vendor FROM inbound_batches WHERE id=?", (item[1],)
        ).fetchone()

        # 2. pending_qty 검증 (409 → 전체 미저장)
        actual, normal, defect, repairing, repair_done, unrecov = (item[8] or 0), (item[9] or 0), (item[10] or 0), (item[11] or 0), (item[12] or 0), (item[13] or 0)
        pending = _item_pending_qty(actual, normal, defect, repairing, repair_done, unrecov)

        if pending < body.수량:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "INSUFFICIENT_PENDING",
                    "message": f"미처리 수량({pending})이 불량 등록 수량({body.수량})보다 적습니다.",
                    "pending_qty": pending,
                    "requested_qty": body.수량,
                },
            )

        # 3. defect_log INSERT (같은 connection, 아직 commit 안 함)
        inbound_date = (batch[0] if batch else None) or datetime.utcnow().strftime("%Y-%m-%d")
        vendor  = item[5] or (batch[1] if batch else "") or ""
        product = item[6] or item[2] or ""
        option  = item[7] or item[3]
        barcode = item[4]
        now_str = datetime.utcnow().isoformat()
        actor   = body.작성자 or user["nickname"]

        cur = con.execute(
            """INSERT INTO defect_log
               (날짜, 업체명, 제품명, 옵션, 바코드, 불량명, 수량, 비고,
                작성자, 저장시간, 출처, inbound_item_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'inbound', ?)""",
            (inbound_date, vendor, product, option, barcode,
             body.불량명, body.수량, body.비고, actor, now_str, item_id),
        )
        defect_log_id = cur.lastrowid

        # 4. pending → defect 수량 이동 (같은 connection)
        move_item_qty(
            con, item_id, "pending", "defect", body.수량,
            actor=actor,
            ref_id=f"defect:{defect_log_id}",
            reason=body.불량명,
        )

        # 5. defect_case_id 기록
        con.execute(
            "UPDATE inbound_items SET defect_case_id=? WHERE id=?",
            (str(defect_log_id), item_id)
        )

        # 6. 단일 commit (모두 성공해야 저장됨)
        con.commit()

    return {
        "id": defect_log_id,
        "defect_log_id": defect_log_id,
        "inbound_item_id": item_id,
        "qty_moved": {"from": "pending", "to": "defect", "qty": body.수량},
    }


@router.post("/items/{item_id}/repair-log", status_code=201)
def link_repair_log(
    item_id: str,
    body: RepairLogLink,
    authorization: Optional[str] = Header(None),
):
    """
    입고 품목에서 수선일지 생성 (원자 트랜잭션).

    ◆ repair_action ('수선접수'|'수선완료'|'회생불가'|'재판정정상') 으로 수량전환 결정
    ◆ repair_action 이 없으면 qty_from + qty_to 명시 필요 (둘 다 있어야 함)
    ◆ repair_action 이 없고 qty_from/qty_to 도 없으면 400 반환
    ◆ 수량 부족 시 409 → 수선로그·수량이력 모두 rollback
    ◆ 입고품목 미연결(item_id 없음) 수선일지는 독립 기록 — 이 엔드포인트는 항상 연결
    """
    from backend.app.api.repair_log import ensure_repair_tables
    ensure_repair_tables()
    user = _get_user(authorization)

    if body.수량 < 1:
        raise HTTPException(status_code=400, detail="수량은 1 이상이어야 합니다.")

    # ── 수량 전환 결정 ──────────────────────────────────────────────
    # repair_action 우선, 없으면 명시적 qty_from/qty_to, 없으면 오류
    qty_transition: Optional[tuple] = None
    if body.repair_action:
        if body.repair_action not in _REPAIR_ACTION_TRANSITIONS:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_REPAIR_ACTION",
                    "message": f"허용되지 않은 repair_action: '{body.repair_action}'. "
                               f"허용값: {list(_REPAIR_ACTION_TRANSITIONS.keys())}",
                },
            )
        qty_transition = _REPAIR_ACTION_TRANSITIONS[body.repair_action]
    elif body.qty_from and body.qty_to:
        if body.qty_from not in _QTY_STATE_COL or body.qty_to not in _QTY_STATE_COL:
            raise HTTPException(status_code=400, detail="유효하지 않은 qty_from / qty_to 상태값.")
        qty_transition = (body.qty_from, body.qty_to)
    else:
        # 입고품목 연결 수선일지인데 전환 정보 없음 → 명확한 오류
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MISSING_QTY_TRANSITION",
                "message": (
                    "입고품목 연결 수선일지는 repair_action 또는 qty_from+qty_to 가 필요합니다. "
                    f"허용 repair_action: {list(_REPAIR_ACTION_TRANSITIONS.keys())}"
                ),
            },
        )

    from_state, to_state = qty_transition

    with get_connection() as con:
        # 1. 품목 + 부분수량 조회
        item = con.execute(
            """SELECT id, batch_id, item_name, option_text,
                      matched_barcode, matched_vendor, matched_product, matched_option,
                      actual_qty,
                      COALESCE(normal_qty,0), COALESCE(defect_pending_qty,0),
                      COALESCE(repairing_qty,0), COALESCE(repair_done_qty,0),
                      COALESCE(unrecoverable_qty,0)
               FROM inbound_items WHERE id=?""",
            (item_id,)
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="품목을 찾을 수 없습니다.")

        batch = con.execute(
            "SELECT inbound_date, vendor FROM inbound_batches WHERE id=?", (item[1],)
        ).fetchone()

        # 2. 출발 상태 수량 검증 (409 → 전체 미저장)
        actual, normal, defect, repairing, repair_done, unrecov = \
            (item[8] or 0), (item[9] or 0), (item[10] or 0), (item[11] or 0), (item[12] or 0), (item[13] or 0)
        pending = _item_pending_qty(actual, normal, defect, repairing, repair_done, unrecov)
        cur_qty = {
            "pending": pending, "normal": normal, "defect": defect,
            "repairing": repairing, "repair_done": repair_done, "unrecoverable": unrecov,
        }

        if cur_qty[from_state] < body.수량:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "INSUFFICIENT_QTY",
                    "message": f"{from_state} 수량({cur_qty[from_state]})이 이동 수량({body.수량})보다 적습니다.",
                    "from_state": from_state,
                    "available_qty": cur_qty[from_state],
                    "requested_qty": body.수량,
                },
            )

        # 3. repair_work_log INSERT (같은 connection, 아직 commit 안 함)
        inbound_date = (batch[0] if batch else None) or datetime.utcnow().strftime("%Y-%m-%d")
        vendor  = item[5] or (batch[1] if batch else "") or ""
        product = item[6] or item[2] or ""
        option  = item[7] or item[3]
        barcode = item[4]
        now_str = datetime.utcnow().isoformat()
        actor   = body.작성자 or user["nickname"]

        cur = con.execute(
            """INSERT INTO repair_work_log
               (날짜, 업체명, 제품명, 옵션, 바코드, 불량명, 작업, 수량, 비용, 비고,
                작성자, 저장시간, 출처, inbound_item_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'inbound', ?)""",
            (inbound_date, vendor, product, option, barcode,
             body.불량명, body.작업, body.수량, body.비용, body.비고,
             actor, now_str, item_id),
        )
        repair_log_id = cur.lastrowid

        # 4. 수량 이동 (같은 connection)
        move_item_qty(
            con, item_id, from_state, to_state, body.수량,
            actor=actor,
            ref_id=f"repair:{repair_log_id}",
            reason=body.작업,
        )

        # 5. defect_case_id 기록
        con.execute(
            "UPDATE inbound_items SET defect_case_id=? WHERE id=?",
            (f"repair:{repair_log_id}", item_id)
        )

        # 6. 단일 commit
        con.commit()

    return {
        "id": repair_log_id,
        "repair_log_id": repair_log_id,
        "inbound_item_id": item_id,
        "qty_moved": {"from": from_state, "to": to_state, "qty": body.수량},
    }
