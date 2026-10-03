"""Inbound item CRUD and normal-qty updates."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import Header, HTTPException

from logic.db import get_connection

from .barcode import _update_barcode_master
from .router import router
from .schemas import InboundItemCreate, InboundItemUpdate, NormalQtyUpdate
from .utils import (
    ITEM_STATUS_VALUES,
    UPLOAD_DIR,
    _PHOTO_DECISION_VALUES,
    _check_link_expiry,
    _get_user,
    _recalc_batch_totals,
)

# ── 품목 수동 추가 ──────────────────────

@router.post("/batches/{batch_id}/items", status_code=201)
def add_item(
    batch_id: str,
    body: InboundItemCreate,
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    with get_connection() as con:
        if not con.execute("SELECT 1 FROM inbound_batches WHERE id=?", (batch_id,)).fetchone():
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")
        item_id = uuid.uuid4().hex
        max_line = con.execute(
            "SELECT COALESCE(MAX(line_no),0) FROM inbound_items WHERE batch_id=?", (batch_id,)
        ).fetchone()[0]
        con.execute("""
            INSERT INTO inbound_items
                (id, batch_id, line_no, item_name, option_text, unit_price,
                 janggi_qty, actual_qty, missing_qty, status,
                 matched_barcode, matched_vendor, matched_product, matched_option,
                 match_confidence, needs_matching, memo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id, batch_id, max_line + 1, body.item_name, body.option_text, body.unit_price,
            body.janggi_qty, body.actual_qty, body.missing_qty,
            body.matched_barcode, body.matched_vendor, body.matched_product, body.matched_option,
            1.0 if body.matched_barcode else 0.0,
            0 if body.matched_barcode else 1,
            body.memo,
        ))
        _recalc_batch_totals(con, batch_id)
        con.commit()
    return {"id": item_id}


# ── 품목 수정 ───────────────────────────

@router.patch("/items/{item_id}")
def update_item(
    item_id: str,
    body: InboundItemUpdate,
    authorization: Optional[str] = Header(None),
):
    # 실수량 입력은 로그인 없이도 가능 — confirmed_by로 입력자 이름 기록
    # 비로그인 공개 접근: 당일 자정 이후 만료
    if not authorization:
        with get_connection() as con:
            batch_info = con.execute(
                """SELECT b.inbound_date FROM inbound_items i
                   JOIN inbound_batches b ON i.batch_id = b.id
                   WHERE i.id=?""",
                (item_id,)
            ).fetchone()
        if batch_info:
            _check_link_expiry(batch_info[0])

    fields, params = [], []

    if body.actual_qty is not None:
        fields.append("actual_qty=?"); params.append(body.actual_qty)
        # 직원이 수량을 명시적으로 입력했으면 확인 완료 처리
        fields.append("actual_qty_confirmed=1")
    if body.missing_qty is not None:
        fields.append("missing_qty=?"); params.append(body.missing_qty)
    if body.status is not None:
        if body.status not in ITEM_STATUS_VALUES:
            raise HTTPException(status_code=400, detail=f"유효하지 않은 품목 상태: {body.status}")
        fields.append("status=?"); params.append(body.status)
    if body.memo is not None:
        fields.append("memo=?"); params.append(body.memo)
    if body.item_name is not None:
        name_val = body.item_name.strip()
        fields.append("item_name=?"); params.append(name_val if name_val else None)
    if body.option_text is not None:
        opt_val = body.option_text.strip()
        fields.append("option_text=?"); params.append(opt_val if opt_val else None)
    if body.item_wholesale is not None:
        ws_val = body.item_wholesale.strip()
        fields.append("item_wholesale=?"); params.append(ws_val if ws_val else None)
    if body.confirmed_by is not None:
        name = body.confirmed_by.strip()[:50]  # 최대 50자, 앞뒤 공백 제거
        fields.append("confirmed_by=?"); params.append(name if name else None)
    if body.photo_decision is not None:
        if body.photo_decision not in _PHOTO_DECISION_VALUES:
            raise HTTPException(status_code=400, detail=f"photo_decision 허용값: {_PHOTO_DECISION_VALUES}")
        fields.append("photo_decision=?"); params.append(body.photo_decision)
    if body.matched_barcode is not None:
        fields.append("matched_barcode=?"); params.append(body.matched_barcode)
        fields.append("needs_matching=0")
        # 바코드 연결 시 사진 처리결정도 자동 설정 (명시 입력 없을 때)
        if body.photo_decision is None:
            fields.append("photo_decision=COALESCE(photo_decision,'existing')")
    if body.matched_vendor is not None:
        fields.append("matched_vendor=?"); params.append(body.matched_vendor)
    if body.matched_product is not None:
        fields.append("matched_product=?"); params.append(body.matched_product)
    if body.matched_option is not None:
        fields.append("matched_option=?"); params.append(body.matched_option)
    if body.supplier_location is not None:
        fields.append("supplier_location=?"); params.append(body.supplier_location)
    if body.supplier_contact is not None:
        fields.append("supplier_contact=?"); params.append(body.supplier_contact)

    if not fields:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")

    fields.append("updated_at=CURRENT_TIMESTAMP")
    params.append(item_id)
    with get_connection() as con:
        con.execute(f"UPDATE inbound_items SET {', '.join(fields)} WHERE id=?", params)
        batch_row = con.execute("SELECT batch_id FROM inbound_items WHERE id=?", (item_id,)).fetchone()
        if batch_row:
            _recalc_batch_totals(con, batch_row[0])

        # ── 바코드 마스터 자동 갱신 ──────────────────────────────────────
        # matched_barcode / supplier / 상품명·옵션 중 하나라도 변경될 때
        # repair_barcode 의 해당 바코드 레코드를 최신 상태로 갱신한다.
        should_update_master = any([
            body.matched_barcode, body.supplier_location, body.supplier_contact,
            body.matched_product, body.matched_option,
        ])
        if should_update_master:
            # 업데이트 후 품목 전체 상태 조회
            item_state = con.execute(
                """SELECT i.matched_barcode,
                          COALESCE(i.item_wholesale, b.wholesale) AS wholesale,
                          i.supplier_location,
                          i.supplier_contact,
                          i.matched_product,
                          i.matched_option
                   FROM inbound_items i
                   JOIN inbound_batches b ON i.batch_id = b.id
                   WHERE i.id=?""",
                (item_id,)
            ).fetchone()
            if item_state and item_state[0]:  # matched_barcode 있을 때만
                _update_barcode_master(
                    con,
                    barcode=item_state[0],
                    wholesale=item_state[1] or "",
                    supplier_location=item_state[2] or "",
                    supplier_contact=item_state[3] or "",
                    matched_product=item_state[4] or "",
                    matched_option=item_state[5] or "",
                )

        con.commit()

    # ── 사진 사전 자동 등록 ──────────────────────────────────
    # matched_barcode 가 새로 설정된 경우, inbox 사진 중 이 품목에 연결된 항목을
    # product_photo_dict 에 등록한다 (호출되지 않는 서비스 연결).
    if body.matched_barcode:
        try:
            from backend.app.services.inbound_photo_dict import confirm_photo_link
            with get_connection() as _pd_con:
                inbox_rows = _pd_con.execute(
                    "SELECT id, stored_filename FROM inbound_product_photo_inbox "
                    "WHERE item_id=? AND is_deleted=0",
                    (item_id,)
                ).fetchall()
                item_meta = _pd_con.execute(
                    """SELECT i.matched_barcode, i.matched_vendor,
                              COALESCE(i.item_wholesale, b.wholesale) AS wholesale,
                              i.matched_product
                       FROM inbound_items i
                       JOIN inbound_batches b ON i.batch_id = b.id
                       WHERE i.id=?""",
                    (item_id,)
                ).fetchone()
            if item_meta and inbox_rows:
                for inbox_row in inbox_rows:
                    try:
                        confirm_photo_link(
                            photo_filename=inbox_row[1] or inbox_row[0],
                            item_id=item_id,
                            barcode=item_meta[0] or body.matched_barcode,
                            vendor=item_meta[1] or "",
                            wholesale=item_meta[2] or "",
                            sales_product=item_meta[3] or "",
                        )
                    except Exception:
                        pass  # 사진 사전 등록 실패는 품목 저장에 영향 없음
        except Exception:
            pass  # 서비스 불가 시 무시

    return {"ok": True}


# ── 품목 삭제 ───────────────────────────

@router.delete("/items/{item_id}")
def delete_item(
    item_id: str,
    authorization: Optional[str] = Header(None),
):
    user = _get_user(authorization)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 삭제할 수 있습니다.")
    with get_connection() as con:
        batch_row = con.execute("SELECT batch_id FROM inbound_items WHERE id=?", (item_id,)).fetchone()
        # 사진 파일 삭제
        photos = con.execute("SELECT filename FROM inbound_item_photos WHERE item_id=?", (item_id,)).fetchall()
        for p in photos:
            try: (UPLOAD_DIR / p[0]).unlink(missing_ok=True)
            except Exception: pass
        con.execute("DELETE FROM inbound_item_photos WHERE item_id=?", (item_id,))
        con.execute("DELETE FROM inbound_items WHERE id=?", (item_id,))
        if batch_row:
            _recalc_batch_totals(con, batch_row[0])
        con.commit()
    return {"ok": True}


@router.patch("/items/{item_id}/normal-qty")
def update_normal_qty(
    item_id: str,
    body: NormalQtyUpdate,
    authorization: Optional[str] = Header(None),
):
    """
    정상처리 수량 입력·정정 (인증 불필요 — 작업자 직접 입력).

    - normal_qty < 0  → 거부
    - normal_qty > actual_qty  → 거부 (실입고수량 초과 불가)
    - normal_qty == actual_qty → status 자동 'confirmed'
    - normal_qty < actual_qty, 현재 confirmed → status 'pending' 으로 복귀
    """
    if body.normal_qty < 0:
        raise HTTPException(status_code=400, detail="수량은 0 이상이어야 합니다.")

    with get_connection() as con:
        item_row = con.execute(
            "SELECT id, batch_id, actual_qty, status FROM inbound_items WHERE id=?",
            (item_id,)
        ).fetchone()
        if not item_row:
            raise HTTPException(status_code=404, detail="품목을 찾을 수 없습니다.")

        actual_qty = item_row[2] or 0
        current_status = item_row[3] or "pending"

        if body.normal_qty > actual_qty:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"정상처리 수량({body.normal_qty})이 "
                    f"실입고수량({actual_qty})을 초과할 수 없습니다."
                ),
            )

        # 자동 상태 전환 (중복 집계 방지: pending/confirmed 사이만 자동 전환)
        if body.normal_qty == actual_qty and actual_qty > 0:
            new_status = "confirmed"
        elif body.normal_qty < actual_qty and current_status == "confirmed":
            new_status = "pending"
        else:
            new_status = current_status  # 다른 상태(defect/repair 등)는 유지

        fields = ["normal_qty=?", "status=?", "updated_at=CURRENT_TIMESTAMP"]
        params: list = [body.normal_qty, new_status]
        if body.confirmed_by is not None:
            name = body.confirmed_by.strip()[:50]
            fields.append("confirmed_by=?")
            params.append(name if name else None)
        params.append(item_id)

        con.execute(f"UPDATE inbound_items SET {', '.join(fields)} WHERE id=?", params)
        _recalc_batch_totals(con, item_row[1])
        con.commit()

    return {"ok": True, "normal_qty": body.normal_qty, "status": new_status}
