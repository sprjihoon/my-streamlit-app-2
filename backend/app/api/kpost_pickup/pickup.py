"""Pickup validation, preview, list, and create."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from backend.app.api.logs import add_log
from backend.app.services.epost.client import (
    EpostError,
    get_res_info,
    has_epost_credentials,
    insert_order,
    is_ambiguous_insert_error,
    mock_insert_order,
)
from backend.app.services.epost.fields import (
    PICKUP_BOX_SIZES,
    build_return_pickup_params,
    default_ret_visit_iso,
    format_pickup_order_no,
    iso_today_kst,
    normalize_addr1,
    normalize_phone,
    normalize_ret_visit_ymd,
    normalize_zip,
    require_phone,
    resolve_box_spec,
    resolve_infront_center,
    resolve_office_ser,
    split_pickup_address,
    today_kst,
    validate_pickup_address_detail,
)
from logic.db import get_connection

from .common import KST, _get_user, _row_to_dict, ensure_pickup_tables
from .router import router


class PickupSubmitRequest(BaseModel):
    recipient_name: str
    recipient_phone: str
    zipcode: str
    addr1: str
    addr2: str
    pickup_date: str
    goods_name: str = "해외배송 물품"
    box_size: str = "DEFAULT"
    box_quantity: int = 1
    notes: str = ""
    confirm: bool = False
    test_mode: bool = False


def _env() -> dict[str, str]:
    keys = (
        "INFRONT_CENTER_ORD_NM",
        "INFRONT_CENTER_NAME",
        "INFRONT_CENTER_ZIPCODE",
        "INFRONT_CENTER_ADDR1",
        "INFRONT_CENTER_ADDR2",
        "INFRONT_CENTER_PHONE",
        "EPOST_CUSTOMER_ID",
        "EPOST_APPROVAL_NO",
        "EPOST_OFFICE_SER",
    )
    return {key: (os.getenv(key) or "").strip() for key in keys}


def _http_error(exc: Exception, status: int = 400) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, EpostError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=status, detail=str(exc))


def _build_validated(req: PickupSubmitRequest, *, live: bool) -> dict[str, Any]:
    name = (req.recipient_name or "").strip()
    if len(name) < 1:
        raise ValueError("수취인 이름을 입력해주세요.")
    zipcode = normalize_zip(req.zipcode) or extract_if_needed(req.addr1)
    if len(zipcode) != 5:
        raise ValueError("우편번호 5자리가 필요합니다. 주소 검색으로 다시 선택해주세요.")
    addr1, addr2 = split_pickup_address(req.addr1, req.addr2)
    detail_error = validate_pickup_address_detail(addr2)
    if live and detail_error:
        raise ValueError(detail_error)
    if len(addr1) < 2:
        raise ValueError("수거지 도로명 주소가 없습니다.")
    center = resolve_infront_center(_env())
    if live:
        phone = require_phone(req.recipient_phone, "수거 연락처")
        center_phone = require_phone(center.get("phone") or os.getenv("INFRONT_CENTER_PHONE"), "센터 연락처")
    else:
        phone = normalize_phone(req.recipient_phone) or "01000000000"
        center_phone = center.get("phone") or "01000000000"
    if live and zipcode == center["zip"] and normalize_addr1(addr1) == center["addr1"]:
        raise ValueError("수거 주소는 물류센터 주소와 달라야 합니다. 고객 주소를 입력해주세요.")
    spec = resolve_box_spec(req.box_size)
    visit_ymd = normalize_ret_visit_ymd(req.pickup_date)
    goods = (req.goods_name or "").strip() or "해외배송 물품"
    notes = (req.notes or "").strip()
    qty = max(1, min(99, int(req.box_quantity or 1)))
    return {
        "name": name,
        "phone": phone,
        "zipcode": zipcode,
        "addr1": addr1,
        "addr2": addr2,
        "center": {**center, "phone": center_phone},
        "spec": spec,
        "visit_ymd": visit_ymd,
        "goods": goods,
        "qty": qty,
        "notes": notes,
    }


def extract_if_needed(addr1: str) -> str:
    from backend.app.services.epost.fields import extract_zip_from_address

    return extract_zip_from_address(addr1)


def _preview_payload(validated: dict[str, Any], is_test: bool) -> dict[str, Any]:
    visit = validated["visit_ymd"]
    return {
        "vendor": "spring",
        "recipient_name": validated["name"],
        "recipient_phone": validated["phone"],
        "zipcode": validated["zipcode"],
        "addr1": validated["addr1"],
        "addr2": validated["addr2"],
        "pickup_date": f"{visit[:4]}-{visit[4:6]}-{visit[6:8]}",
        "goods_name": validated["goods"],
        "box_size": validated["spec"]["code"],
        "box_quantity": validated["qty"],
        "box_label": f"{validated['spec']['label']} · {validated['spec']['weight']}kg · {validated['spec']['volume']}cm · {validated['qty']}개",
        "notes": validated["notes"],
        "center_name": validated["center"].get("display_name") or validated["center"]["ord_nm"],
        "center_addr": f"{validated['center']['addr1']} {validated['center']['addr2']}".strip(),
        "office_ser": resolve_office_ser(_env()),
        "is_test": is_test,
    }


@router.get("/filter-options")
def pickup_filter_options(token: str):
    """목록 필터용 고유값 목록 반환 (접수자 전체, 수취인 최근 200명)."""
    _get_user(token)
    ensure_pickup_tables()
    with get_connection() as con:
        cb_rows = con.execute(
            "SELECT DISTINCT created_by FROM kpost_pickup_requests "
            "WHERE created_by IS NOT NULL AND created_by != '' "
            "ORDER BY created_by"
        ).fetchall()
        rn_rows = con.execute(
            "SELECT DISTINCT recipient_name FROM kpost_pickup_requests "
            "WHERE recipient_name IS NOT NULL AND recipient_name != '' "
            "ORDER BY recipient_name LIMIT 200"
        ).fetchall()
    return {
        "created_by": [r[0] for r in cb_rows],
        "recipient_names": [r[0] for r in rn_rows],
    }


@router.get("/meta")
def pickup_meta(token: str):
    _get_user(token)
    ensure_pickup_tables()
    live = has_epost_credentials()
    return {
        "vendor": "spring",
        "default_pickup_date": default_ret_visit_iso(),
        "max_pickup_date": (today_kst() + timedelta(days=21)).isoformat(),
        "today": iso_today_kst(),
        "box_sizes": PICKUP_BOX_SIZES,
        "live_ready": live,
        "office_ser": resolve_office_ser(_env()),
        "center": {
            "name": resolve_infront_center(_env()).get("display_name") or "스프링풀필먼트",
            "addr": f"{resolve_infront_center(_env())['addr1']} {resolve_infront_center(_env())['addr2']}".strip(),
        },
    }


@router.post("/preview")
def preview_pickup(req: PickupSubmitRequest, token: str):
    _get_user(token)
    live = has_epost_credentials() and not req.test_mode
    try:
        validated = _build_validated(req, live=live)
    except ValueError as exc:
        raise _http_error(exc) from exc
    return {"ok": True, "preview": _preview_payload(validated, is_test=not live)}


@router.get("")
def list_pickups(
    token: str,
    limit: int = 2000,
    date_from: str | None = None,
    date_to: str | None = None,
    recipient_name: str | None = None,
    created_by: str | None = None,
    treat_status: str | None = None,
):
    _get_user(token)
    ensure_pickup_tables()
    conditions = []
    params: list[Any] = []
    
    if date_from:
        conditions.append("pickup_date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("pickup_date <= ?")
        params.append(date_to)
    if recipient_name and recipient_name.strip():
        conditions.append("recipient_name LIKE ?")
        params.append(f"%{recipient_name.strip()}%")
    if created_by and created_by.strip():
        conditions.append("created_by LIKE ?")
        params.append(f"%{created_by.strip()}%")
    if treat_status and treat_status.strip():
        # "canceled" 는 status 컬럼으로 필터, 나머지는 treat_status 컬럼으로 필터
        if treat_status.strip() == "canceled":
            conditions.append("status = 'canceled'")
        else:
            conditions.append("treat_status = ?")
            params.append(treat_status.strip())
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(max(1, min(limit, 5000)))
    
    with get_connection() as con:
        rows = con.execute(
            f"""
            SELECT id, vendor, order_no, recipient_name, recipient_phone, zipcode, addr1, addr2,
                   pickup_date, goods_name, box_size, box_quantity, notes, tracking_no, req_no, res_no, res_date,
                   price, post_office, treat_status, treat_status_name, status, is_test,
                   created_by, created_at, canceled_at, canceled_by
            FROM kpost_pickup_requests
            {where_clause}
            ORDER BY id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
    return {"items": [_row_to_dict(row) for row in rows]}


def _do_one_insert(
    box_order_no: str,
    validated: dict,
    env: dict,
    live: bool,
    _log: Any,
) -> tuple[dict, dict]:
    """박스 1개분 InsertOrder 호출. (params, result) 반환."""
    params = build_return_pickup_params(
        {
            "cust_no": env.get("EPOST_CUSTOMER_ID") or "TEST",
            "appr_no": env.get("EPOST_APPROVAL_NO") or "0000000000",
            "office_ser": resolve_office_ser(env),
            "order_no": box_order_no,
            "center": {
                "ord_nm": validated["center"]["ord_nm"],
                "zip": validated["center"]["zip"],
                "addr1": validated["center"]["addr1"],
                "addr2": validated["center"]["addr2"],
                "phone": validated["center"]["phone"],
            },
            "pickup": {
                "name": validated["name"],
                "zip": validated["zipcode"],
                "addr1": validated["addr1"],
                "addr2": validated["addr2"],
                "phone": validated["phone"],
            },
            "goods_nm": validated["goods"],
            "weight": validated["spec"]["weight"],
            "volume": validated["spec"]["volume"],
            "micro": validated["spec"].get("micro", False),
            "qty": 1,  # 박스 1개씩 InsertOrder → 송장번호 1개
            "deliv_msg": validated["notes"],
            "ret_visit_ymd": validated["visit_ymd"],
            "test_yn": "Y" if not live else "N",
        }
    )
    if not live:
        return params, mock_insert_order()
    try:
        result = insert_order({**params, "orderNo": box_order_no})
    except Exception as first_err:
        _log.error("[InsertOrder ERR] %s | orderNo=%s", first_err, box_order_no)
        recovered = None
        if not is_ambiguous_insert_error(first_err):
            try:
                recovered = get_res_info(
                    box_order_no, validated["visit_ymd"],
                    timeout=3.0, max_attempts=1,
                )
                if not (recovered.get("regiNo") or "").strip():
                    recovered = None
            except Exception:
                recovered = None
        if recovered and len(recovered.get("regiNo") or "") >= 10:
            return params, recovered
        raise
    return params, result


@router.post("")
def create_pickup(req: PickupSubmitRequest, token: str):
    import logging as _logging
    _log = _logging.getLogger("epost")
    user = _get_user(token)
    ensure_pickup_tables()
    if not req.confirm:
        raise HTTPException(status_code=400, detail="접수 확인이 필요합니다. 다시 시도해주세요.")

    live = has_epost_credentials() and not req.test_mode
    try:
        validated = _build_validated(req, live=live)
    except ValueError as exc:
        raise _http_error(exc) from exc

    pickup_iso = (
        f"{validated['visit_ymd'][:4]}-"
        f"{validated['visit_ymd'][4:6]}-"
        f"{validated['visit_ymd'][6:8]}"
    )

    # 중복 방지: 같은 사용자·수령인 전화번호·수거일에 이미 접수된 건 확인
    with get_connection() as _dup_con:
        _existing_rows = _dup_con.execute(
            """SELECT id, tracking_no FROM kpost_pickup_requests
               WHERE created_by=? AND recipient_phone=? AND pickup_date=?
                 AND status='requested'
               ORDER BY id ASC""",
            (user["nickname"], validated["phone"], pickup_iso),
        ).fetchall()

    qty = validated["qty"]
    already = len(_existing_rows)

    if already >= qty:
        # 요청 수량만큼 이미 모두 접수됨 → guard 반환
        all_tnos = [r[1] for r in _existing_rows[:qty]]
        return {
            "duplicate_guard": True,
            "id": _existing_rows[0][0],
            "tracking_no": all_tnos[0],
            "tracking_nos": all_tnos,
            "success": True,
        }
    elif already > 0:
        # 일부만 접수됨(부분 실패 후 재시도) → 남은 개수만 추가 접수
        qty = qty - already

    env = _env()
    created_at = datetime.now(KST).isoformat(timespec="seconds")

    # qty박스 각각 InsertOrder 1회 → 송장번호 qty개 발급
    created: list[dict] = []
    for box_idx in range(qty):
        box_order_no = format_pickup_order_no()
        try:
            params, result = _do_one_insert(box_order_no, validated, env, live, _log)
        except Exception as err:
            if created:
                # 일부 성공 → 부분 성공으로 처리
                _log.warning(
                    "[InsertOrder PARTIAL] %d/%d 접수 완료 후 실패: %s",
                    len(created), qty, err,
                )
                break
            hint = ""
            msg = str(err)
            if is_ambiguous_insert_error(err):
                hint = " 우체국에 이미 접수되었을 수 있습니다. 목록을 확인한 뒤 다시 누르지 마세요."
            elif "recAddr2" in msg:
                hint = " 상세주소(동·호수·층)를 2글자 이상 입력했는지 확인해주세요."
            elif "recAddr1" in msg or "recZip" in msg:
                hint = " 주소 검색으로 도로명 주소와 우편번호를 다시 선택해주세요."
            raise HTTPException(status_code=502, detail=msg + hint)

        tracking = (result.get("regiNo") or "").strip()
        if live and len(tracking) < 10:
            if created:
                break
            raise HTTPException(
                status_code=502,
                detail="우체국이 수거송장번호를 반환하지 않았습니다. 접수가 완료되지 않았습니다.",
            )
        _log.info(
            "[InsertOrder OK] regiNo=%s reqNo=%s orderNo=%s box=%d/%d user=%s",
            tracking, result.get("reqNo"), box_order_no,
            box_idx + 1, qty, user["nickname"],
        )

        snapshot = {k: v for k, v in params.items() if k != "testYn"}
        with get_connection() as con:
            cur = con.execute(
                """INSERT INTO kpost_pickup_requests (
                    vendor, order_no, recipient_name, recipient_phone, zipcode, addr1, addr2,
                    pickup_date, goods_name, box_size, box_quantity, notes, tracking_no,
                    req_no, res_no, res_date, price, post_office,
                    treat_status, treat_status_name, status, is_test,
                    insert_snapshot, created_by, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "spring",
                    box_order_no,
                    validated["name"],
                    validated["phone"],
                    validated["zipcode"],
                    validated["addr1"],
                    validated["addr2"],
                    pickup_iso,
                    validated["goods"],
                    validated["spec"]["code"],
                    1,  # 박스 1개씩 저장
                    validated["notes"],
                    tracking,
                    result.get("reqNo") or "",
                    result.get("resNo") or "",
                    result.get("resDate") or "",
                    result.get("price") or "0",
                    result.get("regiPoNm") or "",
                    "00" if live else "TEST",
                    "신청접수" if live else "테스트접수",
                    "requested",
                    0 if live else 1,
                    json.dumps(snapshot, ensure_ascii=False),
                    user["nickname"],
                    created_at,
                ),
            )
            box_id = cur.lastrowid
            con.commit()
        created.append({"id": box_id, "order_no": box_order_no, "tracking": tracking, "result": result})

    if not created:
        raise HTTPException(status_code=502, detail="접수에 실패했습니다.")

    for c in created:
        add_log(
            action_type="우체국회수접수",
            target_type="kpost_pickup",
            target_id=str(c["id"]),
            target_name=c["tracking"] or c["order_no"],
            user_nickname=user["nickname"],
            details=f"{validated['name']} / {pickup_iso}",
        )

    all_tnos = [c["tracking"] for c in created]
    first = created[0]
    return {
        "success": True,
        "id": first["id"],
        "order_no": first["order_no"],
        "tracking_no": first["tracking"],
        "tracking_nos": all_tnos,
        "req_no": first["result"].get("reqNo") or "",
        "res_no": first["result"].get("resNo") or "",
        "price": first["result"].get("price") or "0",
        "post_office": first["result"].get("regiPoNm") or "",
        "pickup_date": pickup_iso,
        "is_test": not live,
        "partial": len(created) < qty,
        "preview": _preview_payload(validated, is_test=not live),
    }
