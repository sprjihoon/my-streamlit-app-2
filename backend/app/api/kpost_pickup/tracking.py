"""Pickup status sync, refresh, detail, cancel, and delete."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from backend.app.api.logs import add_log
from backend.app.services.epost.client import (
    cancel_order,
    get_res_info_with_dates,
    lookup_req_ymds,
    track_regi_no,
)
from backend.app.services.epost.fields import (
    FINAL_TREAT_STATUSES,
    TREAT_STATUS_ORDER,
    resolve_cancel_req_ymd,
    treat_status_code,
)
from logic.db import get_connection

from .common import KST, _get_user, _row_to_dict, ensure_pickup_tables
from .router import router


def _pickup_req_ymd(item: dict[str, Any]) -> str:
    ymds = lookup_req_ymds(item.get("res_date"), item.get("created_at"), item.get("pickup_date"))
    return ymds[0] if ymds else resolve_cancel_req_ymd(item.get("res_date"), item.get("created_at"))


def _apply_tracking_info(item: dict[str, Any], info: dict[str, str]) -> dict[str, Any]:
    """API 응답을 item dict에 반영한다.
    
    상태는 앞으로만 진행한다(no-downgrade).
    GetResInfo가 수거완료(01)를 반환해도 이미 배달준비(06)인 항목을 덮어쓰지 않는다.
    """
    # treat_status_code()로 숫자코드·Korean text 모두 Korean text로 정규화
    new_name = treat_status_code(info.get("treatStusCd") or "")
    if new_name and new_name != "신청접수":
        cur_name = treat_status_code(item.get("treat_status") or "신청접수")
        cur_order = TREAT_STATUS_ORDER.get(cur_name, 0)
        new_order = TREAT_STATUS_ORDER.get(new_name, 0)
        if new_order >= cur_order:  # 더 진행된 상태이거나 같은 상태일 때만 업데이트
            item["treat_status"] = new_name
            item["treat_status_name"] = new_name
    if info.get("regiNo"):
        item["tracking_no"] = info["regiNo"]
    return item


def _sync_pickup_like_infront(item: dict[str, Any]) -> dict[str, Any]:
    """Infront inbound-sync: GetResInfo 먼저, 송장이 있으면 종적조회로 보완."""
    if item.get("order_no"):
        ymds = lookup_req_ymds(item.get("res_date"), item.get("created_at"), item.get("pickup_date"))
        try:
            info = get_res_info_with_dates(item["order_no"], ymds)
            _apply_tracking_info(item, info)
        except Exception:
            pass
    # '배달완료'만 최종 상태 — 수거완료 이후에도 이동중·배달중·배달완료 추적을 계속한다.
    # track_regi_no 실패는 조용히 무시: GetResInfo 결과만으로도 DB를 갱신해야 하기 때문.
    if item.get("treat_status") not in FINAL_TREAT_STATUSES and item.get("tracking_no"):
        try:
            tracked = track_regi_no(item["tracking_no"])
            _apply_tracking_info(item, tracked)
        except Exception:
            pass  # 공개 종적조회 실패 시 GetResInfo 결과 그대로 유지
    return item


@router.post("/refresh-status")
def refresh_pickup_statuses(token: str):
    _get_user(token)
    ensure_pickup_tables()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT id, vendor, order_no, recipient_name, recipient_phone, zipcode, addr1, addr2,
                   pickup_date, goods_name, box_size, box_quantity, notes, tracking_no, req_no, res_no, res_date,
                   price, post_office, treat_status, treat_status_name, status, is_test,
                   created_by, created_at, canceled_at, canceled_by
            FROM kpost_pickup_requests
            WHERE status = 'requested' AND is_test = 0
              AND (treat_status IS NULL OR treat_status NOT IN ('배달완료'))
              AND (
                (order_no IS NOT NULL AND order_no != '')
                OR (tracking_no IS NOT NULL AND tracking_no != '')
              )
            ORDER BY id DESC
            LIMIT 200
            """
        ).fetchall()
    items = [_row_to_dict(row) for row in rows]
    today_ymd = datetime.now(KST).strftime("%Y%m%d")
    checked = 0
    completed = 0
    failed = 0

    def _process(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """단일 항목 API 조회 (스레드에서 실행). DB 쓰기는 호출자가 처리."""
        pickup_ymd = re.sub(r"\D", "", item.get("pickup_date") or "")[:8]
        if pickup_ymd and pickup_ymd > today_ymd:
            if item.get("treat_status") == "수거완료":
                return "reset", item
            return "skip", item
        if item.get("treat_status") in FINAL_TREAT_STATUSES:
            return "skip", item
        try:
            _sync_pickup_like_infront(item)
            return "checked", item
        except Exception:
            return "failed", item

    # HTTP 호출은 병렬(최대 8 스레드), DB 쓰기는 메인 스레드에서 직렬 처리
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {executor.submit(_process, item): item for item in items}
        for future in as_completed(future_map):
            status, item = future.result()
            if status == "reset":
                with get_connection() as con:
                    con.execute(
                        "UPDATE kpost_pickup_requests SET treat_status='신청접수', treat_status_name='신청접수' WHERE id=?",
                        (item["id"],),
                    )
                    con.commit()
            elif status == "checked":
                with get_connection() as con:
                    con.execute(
                        """
                        UPDATE kpost_pickup_requests
                        SET treat_status=?, treat_status_name=?, tracking_no=?
                        WHERE id=?
                        """,
                        (item["treat_status"], item["treat_status_name"], item["tracking_no"], item["id"]),
                    )
                    con.commit()
                checked += 1
                if item.get("treat_status") == "수거완료":
                    completed += 1
            elif status == "failed":
                failed += 1
    return {
        "success": True,
        "checked": checked,
        "completed": completed,
        "failed": failed,
        "message": (
            f"송장 {checked}건 조회. 수거완료 {completed}건"
            + (f" / 조회실패 {failed}건" if failed else "")
        ),
    }


@router.patch("/{pickup_id}/treat-status")
def patch_treat_status(pickup_id: int, token: str, treat_status: str):
    """관리자 전용: 특정 항목의 처리상태를 수동으로 수정."""
    user = _get_user(token)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자만 사용할 수 있습니다.")
    # treat_status는 Korean text (예: '수거준비') — 숫자코드면 변환
    new_name = treat_status_code(treat_status)
    if new_name not in TREAT_STATUS_ORDER:
        allowed = list(TREAT_STATUS_ORDER.keys())
        raise HTTPException(status_code=400, detail=f"유효하지 않은 상태. 허용: {allowed}")
    ensure_pickup_tables()
    with get_connection() as con:
        row = con.execute("SELECT id FROM kpost_pickup_requests WHERE id=?", (pickup_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
        con.execute(
            "UPDATE kpost_pickup_requests SET treat_status=?, treat_status_name=? WHERE id=?",
            (new_name, new_name, pickup_id),
        )
        con.commit()
    add_log(
        action_type="수동상태수정",
        target_type="kpost_pickup",
        target_id=str(pickup_id),
        target_name=str(pickup_id),
        user_nickname=user["nickname"],
        details=f"treat_status → {new_name}",
    )
    return {"success": True, "id": pickup_id, "treat_status": new_name, "treat_status_name": new_name}


@router.get("/{pickup_id}")
def get_pickup(pickup_id: int, token: str, refresh: bool = False):
    _get_user(token)
    ensure_pickup_tables()
    with get_connection() as con:
        row = con.execute(
            """
            SELECT id, vendor, order_no, recipient_name, recipient_phone, zipcode, addr1, addr2,
                   pickup_date, goods_name, box_size, box_quantity, notes, tracking_no, req_no, res_no, res_date,
                   price, post_office, treat_status, treat_status_name, status, is_test,
                   created_by, created_at, canceled_at, canceled_by
            FROM kpost_pickup_requests WHERE id = ?
            """,
            (pickup_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="접수 내역을 찾을 수 없습니다.")
    item = _row_to_dict(row)
    if refresh and not item["is_test"] and item["status"] == "requested":
        try:
            _sync_pickup_like_infront(item)
            with get_connection() as con:
                con.execute(
                    """
                    UPDATE kpost_pickup_requests
                    SET treat_status=?, treat_status_name=?, tracking_no=?
                    WHERE id=?
                    """,
                    (item["treat_status"], item["treat_status_name"], item["tracking_no"], pickup_id),
                )
                con.commit()
        except Exception:
            pass
    return item


@router.post("/bulk-delete")
def bulk_delete_pickups(token: str, tracking_nos: list[str]):
    """송장번호 목록으로 접수 내역 일괄 삭제 (관리자 전용)."""
    user = _get_user(token)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자만 삭제할 수 있습니다.")
    if not tracking_nos:
        raise HTTPException(status_code=400, detail="송장번호 목록이 비어 있습니다.")
    ensure_pickup_tables()
    with get_connection() as con:
        placeholders = ",".join(["?"] * len(tracking_nos))
        rows = con.execute(
            f"SELECT id, tracking_no FROM kpost_pickup_requests WHERE tracking_no IN ({placeholders})",
            tracking_nos,
        ).fetchall()
        if not rows:
            return {"success": True, "deleted": 0, "message": "해당 송장번호가 없습니다."}
        ids = [r[0] for r in rows]
        id_placeholders = ",".join(["?"] * len(ids))
        con.execute(f"DELETE FROM kpost_pickup_requests WHERE id IN ({id_placeholders})", ids)
        con.commit()
    for r in rows:
        add_log(
            action_type="우체국회수일괄삭제",
            target_type="kpost_pickup",
            target_id=str(r[0]),
            target_name=r[1],
            user_nickname=user["nickname"],
            details="일괄 삭제",
        )
    return {"success": True, "deleted": len(ids), "ids": ids}


@router.delete("/{pickup_id}")
def delete_pickup(pickup_id: int, token: str):
    """접수 내역을 DB에서 완전 삭제합니다 (관리자 전용)."""
    user = _get_user(token)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자만 삭제할 수 있습니다.")
    ensure_pickup_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT id, tracking_no, order_no, status FROM kpost_pickup_requests WHERE id = ?",
            (pickup_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="접수 내역을 찾을 수 없습니다.")
        tracking = row[1] or row[2] or str(pickup_id)
        con.execute("DELETE FROM kpost_pickup_requests WHERE id = ?", (pickup_id,))
        con.commit()
    add_log(
        action_type="우체국회수삭제",
        target_type="kpost_pickup",
        target_id=str(pickup_id),
        target_name=tracking,
        user_nickname=user["nickname"],
        details=f"수동 삭제 (id={pickup_id})",
    )
    return {"success": True, "id": pickup_id, "tracking_no": tracking}


@router.post("/{pickup_id}/cancel")
def cancel_pickup(pickup_id: int, token: str, confirm: bool = False):
    user = _get_user(token)
    if not confirm:
        raise HTTPException(status_code=400, detail="확인 후에만 취소할 수 있습니다.")
    ensure_pickup_tables()
    with get_connection() as con:
        row = con.execute(
            """
            SELECT id, status, is_test, req_no, res_no, tracking_no, pickup_date, insert_snapshot,
                   res_date, created_at
            FROM kpost_pickup_requests WHERE id = ?
            """,
            (pickup_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="접수 내역을 찾을 수 없습니다.")
    if row[1] == "canceled":
        return {"success": True, "already": True, "message": "이미 취소된 접수입니다."}
    if not row[2]:
        # reqYmd: res_date(우체국 접수일) → created_at(DB 생성일) → 오늘 순서로 사용
        req_no  = row[3] or ""
        res_no  = row[4] or ""
        regi_no = row[5] or ""
        req_ymd = resolve_cancel_req_ymd(row[8] or "", row[9] or "")  # res_date, created_at
        if req_no and res_no and regi_no:
            snapshot = json.loads(row[7] or "{}")
            try:
                cancel_order(
                    req_no=req_no,
                    res_no=res_no,
                    regi_no=regi_no,
                    req_ymd=req_ymd,
                    insert_snapshot=snapshot,
                )
            except Exception as exc:
                msg = str(exc)
                import logging as _logging
                _logging.getLogger("epost").warning("[Cancel WARN] %s | regiNo=%s", msg, regi_no)
                if (
                    "ERR-123" in msg
                    or "예약된 정보가 없" in msg
                    or "필수값 누락" in msg
                    or "취소 미완료" in msg       # canceledYn=N: 우체국이 취소 불가 반환
                    or "canceledYn=N" in msg
                ):
                    pass  # 우체국 취소 실패해도 DB는 취소 처리
                else:
                    raise HTTPException(status_code=502, detail=msg) from exc
    canceled_at = datetime.now(KST).isoformat(timespec="seconds")
    with get_connection() as con:
        con.execute(
            """
            UPDATE kpost_pickup_requests
            SET status='canceled', canceled_at=?, canceled_by=?, treat_status_name='취소'
            WHERE id=?
            """,
            (canceled_at, user["nickname"], pickup_id),
        )
        con.commit()
    add_log(
        action_type="우체국회수취소",
        target_type="kpost_pickup",
        target_id=str(pickup_id),
        target_name=row[5] or str(pickup_id),
        user_nickname=user["nickname"],
    )
    return {"success": True, "id": pickup_id, "status": "canceled"}
