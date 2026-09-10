"""Infront 우체국 회수신청(반품소포) 접수 API."""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.api.logs import add_log
from backend.app.services.epost.client import (
    EpostError,
    cancel_order,
    get_res_info,
    get_res_info_with_dates,
    has_epost_credentials,
    lookup_req_ymds,
    track_regi_no,
    insert_order,
    is_ambiguous_insert_error,
    mock_insert_order,
)
from backend.app.services.epost.fields import (
    FINAL_TREAT_STATUSES,
    PICKUP_BOX_SIZES,
    TREAT_STATUS_ORDER,
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
    resolve_cancel_req_ymd,
    resolve_infront_center,
    resolve_office_ser,
    split_pickup_address,
    today_kst,
    treat_status_code,
    treat_status_label,
    validate_pickup_address_detail,
)
from logic.db import get_connection

router = APIRouter(prefix="/kpost-pickup", tags=["kpost-pickup"])
KST = ZoneInfo("Asia/Seoul")


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


class SavedRecipientRequest(BaseModel):
    label: str
    recipient_name: str
    recipient_phone: str
    zipcode: str
    addr1: str
    addr2: str = ""


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


def ensure_pickup_tables() -> None:
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS kpost_pickup_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor TEXT NOT NULL DEFAULT 'infront',
                order_no TEXT NOT NULL,
                recipient_name TEXT NOT NULL,
                recipient_phone TEXT NOT NULL,
                zipcode TEXT NOT NULL,
                addr1 TEXT NOT NULL,
                addr2 TEXT NOT NULL,
                pickup_date TEXT NOT NULL,
                goods_name TEXT,
                box_size TEXT,
                box_quantity INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                tracking_no TEXT,
                req_no TEXT,
                res_no TEXT,
                res_date TEXT,
                price TEXT,
                post_office TEXT,
                treat_status TEXT,
                treat_status_name TEXT,
                status TEXT NOT NULL DEFAULT 'requested',
                is_test INTEGER NOT NULL DEFAULT 0,
                insert_snapshot TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                canceled_at TEXT,
                canceled_by TEXT
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_kpost_pickup_created ON kpost_pickup_requests(created_at DESC)"
        )
        
        # Migration: Add box_quantity column if it doesn't exist
        try:
            con.execute("SELECT box_quantity FROM kpost_pickup_requests LIMIT 1")
        except Exception:
            con.execute("ALTER TABLE kpost_pickup_requests ADD COLUMN box_quantity INTEGER NOT NULL DEFAULT 1")

        # Migration: 숫자코드 treat_status → Korean text (1회성, 이미 변환된 행은 영향 없음)
        from backend.app.services.epost.fields import TREAT_STATUS_LABELS
        for code, label in TREAT_STATUS_LABELS.items():
            con.execute(
                "UPDATE kpost_pickup_requests SET treat_status=?, treat_status_name=? "
                "WHERE treat_status=?",
                (label, label, code),
            )
        
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                recipient_name TEXT NOT NULL,
                recipient_phone TEXT NOT NULL,
                zipcode TEXT NOT NULL,
                addr1 TEXT NOT NULL,
                addr2 TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, label)
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_saved_recipients_user ON saved_recipients(user_id, created_at DESC)"
        )
        con.commit()


def _get_user(token: str) -> dict[str, Any]:
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        row = con.execute(
            """
            SELECT u.user_id, u.nickname, u.department, u.is_admin
            FROM sessions s JOIN users u USING(user_id)
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return {
        "user_id": row[0],
        "nickname": row[1] or "",
        "department": row[2] or "",
        "is_admin": bool(row[3]),
    }


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


def _row_to_dict(row: Any) -> dict[str, Any]:
    keys = [
        "id",
        "vendor",
        "order_no",
        "recipient_name",
        "recipient_phone",
        "zipcode",
        "addr1",
        "addr2",
        "pickup_date",
        "goods_name",
        "box_size",
        "box_quantity",
        "notes",
        "tracking_no",
        "req_no",
        "res_no",
        "res_date",
        "price",
        "post_office",
        "treat_status",
        "treat_status_name",
        "status",
        "is_test",
        "created_by",
        "created_at",
        "canceled_at",
        "canceled_by",
    ]
    data = dict(zip(keys, row))
    data["is_test"] = bool(data["is_test"])
    if data.get("status") == "canceled":
        data["treat_status_name"] = "취소"
    else:
        data["treat_status_name"] = treat_status_label(
            data.get("treat_status"), data.get("treat_status_name")
        )
    return data


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


@router.get("/saved-recipients")
def list_saved_recipients(token: str):
    user = _get_user(token)
    ensure_pickup_tables()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT id, label, recipient_name, recipient_phone, zipcode, addr1, addr2, created_at
            FROM saved_recipients
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user["user_id"],),
        ).fetchall()
    return {
        "items": [
            {
                "id": row[0],
                "label": row[1],
                "recipient_name": row[2],
                "recipient_phone": row[3],
                "zipcode": row[4],
                "addr1": row[5],
                "addr2": row[6] or "",
                "created_at": row[7],
            }
            for row in rows
        ]
    }


@router.post("/saved-recipients")
def save_recipient(req: SavedRecipientRequest, token: str):
    user = _get_user(token)
    ensure_pickup_tables()
    label = (req.label or "").strip()
    if len(label) < 1:
        raise HTTPException(status_code=400, detail="라벨을 입력해주세요.")
    if len(label) > 50:
        raise HTTPException(status_code=400, detail="라벨은 50자 이하여야 합니다.")
    name = (req.recipient_name or "").strip()
    if len(name) < 1:
        raise HTTPException(status_code=400, detail="수취인 이름을 입력해주세요.")
    phone = normalize_phone(req.recipient_phone)
    if len(phone) < 9:
        raise HTTPException(status_code=400, detail="전화번호를 입력해주세요.")
    zipcode = normalize_zip(req.zipcode)
    if len(zipcode) != 5:
        raise HTTPException(status_code=400, detail="우편번호 5자리가 필요합니다.")
    addr1 = (req.addr1 or "").strip()
    if len(addr1) < 2:
        raise HTTPException(status_code=400, detail="주소를 입력해주세요.")
    addr2 = (req.addr2 or "").strip()
    created_at = datetime.now(KST).isoformat(timespec="seconds")
    with get_connection() as con:
        # 중복 라벨이면 기존 레코드 반환 (1회만 저장)
        existing = con.execute(
            "SELECT id FROM saved_recipients WHERE user_id=? AND label=?",
            (user["user_id"], label),
        ).fetchone()
        if existing:
            return {"success": True, "id": existing[0], "label": label,
                    "recipient_name": name, "recipient_phone": phone,
                    "zipcode": zipcode, "addr1": addr1, "addr2": addr2}
        try:
            cur = con.execute(
                """
                INSERT INTO saved_recipients (user_id, label, recipient_name, recipient_phone, zipcode, addr1, addr2, created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (user["user_id"], label, name, phone, zipcode, addr1, addr2, created_at),
            )
            recipient_id = cur.lastrowid
            con.commit()
        except Exception as exc:
            if "UNIQUE constraint" in str(exc):
                row = con.execute(
                    "SELECT id FROM saved_recipients WHERE user_id=? AND label=?",
                    (user["user_id"], label),
                ).fetchone()
                if row:
                    return {"success": True, "id": row[0], "label": label,
                            "recipient_name": name, "recipient_phone": phone,
                            "zipcode": zipcode, "addr1": addr1, "addr2": addr2}
            raise
    return {
        "success": True,
        "id": recipient_id,
        "label": label,
        "recipient_name": name,
        "recipient_phone": phone,
        "zipcode": zipcode,
        "addr1": addr1,
        "addr2": addr2,
    }


@router.put("/saved-recipients/{recipient_id}")
def update_saved_recipient(recipient_id: int, req: SavedRecipientRequest, token: str):
    user = _get_user(token)
    ensure_pickup_tables()
    label = (req.label or "").strip()
    if len(label) < 1:
        raise HTTPException(status_code=400, detail="라벨을 입력해주세요.")
    if len(label) > 50:
        raise HTTPException(status_code=400, detail="라벨은 50자 이하여야 합니다.")
    name = (req.recipient_name or "").strip()
    if len(name) < 1:
        raise HTTPException(status_code=400, detail="수취인 이름을 입력해주세요.")
    phone = normalize_phone(req.recipient_phone)
    if len(phone) < 9:
        raise HTTPException(status_code=400, detail="전화번호를 입력해주세요.")
    zipcode = normalize_zip(req.zipcode)
    if len(zipcode) != 5:
        raise HTTPException(status_code=400, detail="우편번호 5자리가 필요합니다.")
    addr1 = (req.addr1 or "").strip()
    if len(addr1) < 2:
        raise HTTPException(status_code=400, detail="주소를 입력해주세요.")
    addr2 = (req.addr2 or "").strip()

    with get_connection() as con:
        row = con.execute(
            "SELECT id, user_id FROM saved_recipients WHERE id = ?",
            (recipient_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="저장된 수취인을 찾을 수 없습니다.")
        if row[1] != user["user_id"]:
            raise HTTPException(status_code=403, detail="다른 사용자의 수취인 정보는 수정할 수 없습니다.")

        # Check if new label conflicts with existing (excluding current record)
        existing = con.execute(
            "SELECT id FROM saved_recipients WHERE user_id = ? AND label = ? AND id != ?",
            (user["user_id"], label, recipient_id),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail=f"'{label}' 라벨은 이미 사용 중입니다.")

        con.execute(
            """
            UPDATE saved_recipients
            SET label = ?, recipient_name = ?, recipient_phone = ?,
                zipcode = ?, addr1 = ?, addr2 = ?
            WHERE id = ?
            """,
            (label, name, phone, zipcode, addr1, addr2, recipient_id),
        )
        con.commit()
    add_log(
        action_type="저장된주소지 수정",
        target_type="saved_recipient",
        target_id=str(recipient_id),
        target_name=label,
        user_nickname=user["nickname"],
        details=f"{name} / {zipcode}",
    )
    return {"success": True, "id": recipient_id, "label": label}


@router.delete("/saved-recipients/{recipient_id}")
def delete_saved_recipient(recipient_id: int, token: str):
    user = _get_user(token)
    ensure_pickup_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT id, user_id FROM saved_recipients WHERE id = ?",
            (recipient_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="저장된 수취인을 찾을 수 없습니다.")
        if row[1] != user["user_id"]:
            raise HTTPException(status_code=403, detail="다른 사용자의 수취인 정보는 삭제할 수 없습니다.")
        con.execute("DELETE FROM saved_recipients WHERE id = ?", (recipient_id,))
        con.commit()
    return {"success": True, "id": recipient_id}


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


@router.get("/debug-track/{regi_no}")
def debug_track(regi_no: str, token: str):
    """특정 송장번호의 종적조회 결과 + DB 상태를 반환 (관리자 전용 디버그)."""
    user = _get_user(token)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자만 사용할 수 있습니다.")
    from backend.app.services.epost.client import (
        _track_via_epost_trace,
        _track_via_tracker_delivery,
        _track_via_vercel_relay,
        VERCEL_APP_URL,
        EPOST_RELAY_SECRET,
    )
    results: dict[str, Any] = {}

    # 1) DB에서 해당 송장번호 레코드 조회
    ensure_pickup_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT id, order_no, tracking_no, treat_status, treat_status_name, status, res_date, created_at, pickup_date FROM kpost_pickup_requests WHERE tracking_no=? ORDER BY id DESC LIMIT 1",
            (regi_no,),
        ).fetchone()
    if row:
        cols = ["id","order_no","tracking_no","treat_status","treat_status_name","status","res_date","created_at","pickup_date"]
        results["db_record"] = dict(zip(cols, row))
        order_no = row[1]
        # 2) GetResInfo (계약 API) 테스트
        if order_no:
            ymds = lookup_req_ymds(row[6], row[7], row[8])
            try:
                info = get_res_info_with_dates(order_no, ymds)
                results["get_res_info"] = info
            except Exception as e:
                results["get_res_info_error"] = str(e)
    else:
        results["db_record"] = f"송장번호 {regi_no} 없음"

    # 3) tracker.delivery (외부 GraphQL API) 테스트
    try:
        r = _track_via_tracker_delivery(regi_no)
        results["tracker_delivery"] = r or "None (자격증명 없음 또는 매핑 실패)"
    except Exception as e:
        results["tracker_delivery_error"] = str(e)

    # 3-B) Vercel ICN 릴레이 테스트
    results["vercel_relay_config"] = {
        "VERCEL_APP_URL": VERCEL_APP_URL or "(미설정)",
        "EPOST_RELAY_SECRET": "설정됨" if EPOST_RELAY_SECRET else "(미설정)",
    }
    try:
        rv = _track_via_vercel_relay(regi_no)
        results["vercel_relay"] = rv or "None (릴레이 응답 없음 또는 텍스트 매핑 실패)"
    except Exception as e:
        results["vercel_relay_error"] = str(e)

    # 4) epost HTML 스크래핑 (service.epost.go.kr - Railway에서 차단될 수 있음)
    try:
        r2 = _track_via_epost_trace(regi_no)
        results["epost_trace"] = r2 or "None (텍스트 매핑 실패)"
    except Exception as e:
        results["epost_trace_error"] = str(e)

    # 5) ntrack.epost.go.kr (신형 서버) 접근 가능성 테스트
    try:
        import httpx as _httpx
        nr = _httpx.get(
            "https://ntrack.epost.go.kr/trace/traceDelivery.comm",
            params={"barCode": regi_no, "displayHeader": "N"},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"},
            follow_redirects=True,
        )
        results["ntrack_status"] = nr.status_code
        if nr.status_code < 400:
            raw_n = nr.content
            try:
                html_n = raw_n.decode("euc-kr")
            except Exception:
                html_n = raw_n.decode("utf-8", errors="replace")
            from backend.app.services.epost.fields import treat_status_from_tracking_text
            treat_n = treat_status_from_tracking_text(html_n)
            results["ntrack_treat"] = treat_n
            results["ntrack_sample"] = html_n[:300]
        else:
            results["ntrack_sample"] = f"HTTP {nr.status_code}"
    except Exception as e:
        results["ntrack_error"] = str(e)

    return results


@router.get("/maintenance/inspect")
def maintenance_inspect(secret: str, tracking_no: str):
    """유지보수 전용: 특정 송장의 DB 레코드 + insert_snapshot 조회."""
    relay_secret = os.getenv("EPOST_RELAY_SECRET", "").strip()
    if not relay_secret or secret != relay_secret:
        raise HTTPException(status_code=403, detail="인증 실패")
    ensure_pickup_tables()
    with get_connection() as con:
        row = con.execute(
            """SELECT id, order_no, tracking_no, treat_status, treat_status_name,
                      box_size, box_quantity, status, created_at, recipient_name,
                      insert_snapshot
               FROM kpost_pickup_requests
               WHERE tracking_no=? ORDER BY id DESC LIMIT 1""",
            (tracking_no,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="해당 송장 없음")
    cols = ["id","order_no","tracking_no","treat_status","treat_status_name",
            "box_size","box_quantity","status","created_at","recipient_name","insert_snapshot"]
    d = dict(zip(cols, row))
    snap = {}
    if d.get("insert_snapshot"):
        import json as _json
        try:
            snap = _json.loads(d["insert_snapshot"])
        except Exception:
            snap = {"raw": d["insert_snapshot"]}
    return {
        "db": {k: v for k, v in d.items() if k != "insert_snapshot"},
        "insert_snapshot": snap,
    }


@router.post("/maintenance/reset-status")
def maintenance_reset_status(secret: str, body: dict):
    """유지보수 전용: EPOST_RELAY_SECRET 인증으로 특정 송장 상태를 직접 수정.

    body: {"tracking_nos": ["...", ...], "treat_status": "수거준비"} (또는 숫자코드 "05"도 허용)
    secret: EPOST_RELAY_SECRET 값
    """
    relay_secret = os.getenv("EPOST_RELAY_SECRET", "").strip()
    if not relay_secret or secret != relay_secret:
        raise HTTPException(status_code=403, detail="인증 실패: secret이 올바르지 않습니다.")

    tracking_nos: list[str] = body.get("tracking_nos") or []
    raw_status: str = (body.get("treat_status") or "").strip()
    if not tracking_nos:
        raise HTTPException(status_code=400, detail="tracking_nos가 비어 있습니다.")
    # 숫자코드('05') 또는 Korean text('수거준비') 모두 허용
    new_name = treat_status_code(raw_status)
    if new_name not in TREAT_STATUS_ORDER:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 상태. 허용: {list(TREAT_STATUS_ORDER.keys())}")

    ensure_pickup_tables()
    updated = []
    not_found = []
    with get_connection() as con:
        for tno in tracking_nos:
            row = con.execute(
                "SELECT id, treat_status FROM kpost_pickup_requests WHERE tracking_no=? ORDER BY id DESC LIMIT 1",
                (tno,),
            ).fetchone()
            if not row:
                not_found.append(tno)
                continue
            con.execute(
                "UPDATE kpost_pickup_requests SET treat_status=?, treat_status_name=? WHERE id=?",
                (new_name, new_name, row[0]),
            )
            updated.append({"id": row[0], "tracking_no": tno, "prev": row[1], "now": new_name})
        con.commit()
    return {
        "success": True,
        "updated": updated,
        "not_found": not_found,
        "treat_status": new_name,
        "treat_status_name": new_name,
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
