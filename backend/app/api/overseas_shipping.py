"""창고 직원용 EMS/K-Packet 해외배송 접수. 결제 없이 우체국 즉시 접수."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.kpost_pickup import _get_user
from backend.app.api.logs import add_log
from backend.app.services.ems.client import (
    EmsApiError,
    apply_ems,
    cancel_ems,
    get_available_nations,
    get_shipping_quote,
    has_ems_credentials,
    mock_apply_ems,
    mock_quote_fee,
)
from backend.app.services.ems.fields import (
    FALLBACK_NATIONS,
    SHIPPING_METHODS,
    build_apply_params,
    env_clean,
    resolve_sender,
    validate_apply_input,
)
from logic.db import get_connection

router = APIRouter(prefix="/overseas-shipping", tags=["overseas-shipping"])
KST = ZoneInfo("Asia/Seoul")


class InvoiceItem(BaseModel):
    name_en: str
    quantity: int = 1
    unit_price_usd: float
    hs_code: str = ""
    origin_country: str = "KR"


class OverseasSubmitRequest(BaseModel):
    shipping_method: str = "EMS"
    countrycd: str
    receivename: str
    receivetelno: str = ""
    receivemail: str = ""
    receivezipcode: str = ""
    receiveaddr1: str = ""
    receiveaddr2: str = ""
    receiveaddr3: str
    totweight: int
    boxlength: int
    boxwidth: int
    boxheight: int
    items: list[InvoiceItem] = Field(default_factory=list)
    notes: str = ""
    confirm: bool = False
    test_mode: bool = False


def ensure_overseas_tables() -> None:
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS overseas_shipping_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT NOT NULL,
                shipping_method TEXT NOT NULL,
                premiumcd TEXT,
                countrycd TEXT NOT NULL,
                recipient_name TEXT NOT NULL,
                recipient_phone TEXT,
                recipient_email TEXT,
                recipient_zip TEXT,
                recipient_addr1 TEXT,
                recipient_addr2 TEXT,
                recipient_addr3 TEXT,
                totweight INTEGER,
                boxlength INTEGER,
                boxwidth INTEGER,
                boxheight INTEGER,
                item_list TEXT,
                tracking_no TEXT,
                req_no TEXT,
                receive_seq TEXT,
                ems_fee TEXT,
                post_office TEXT,
                status TEXT NOT NULL DEFAULT 'requested',
                is_test INTEGER NOT NULL DEFAULT 0,
                apply_snapshot TEXT,
                notes TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                canceled_at TEXT,
                canceled_by TEXT
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_overseas_shipping_created "
            "ON overseas_shipping_requests(created_at DESC)"
        )
        con.commit()


def _http_error(exc: Exception, status: int = 400) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, EmsApiError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=status, detail=str(exc))


def _req_dict(req: OverseasSubmitRequest) -> dict[str, Any]:
    return {
        "shipping_method": req.shipping_method,
        "countrycd": req.countrycd,
        "receivename": req.receivename,
        "receivetelno": req.receivetelno,
        "receivemail": req.receivemail,
        "receivezipcode": req.receivezipcode,
        "receiveaddr1": req.receiveaddr1,
        "receiveaddr2": req.receiveaddr2,
        "receiveaddr3": req.receiveaddr3,
        "totweight": req.totweight,
        "boxlength": req.boxlength,
        "boxwidth": req.boxwidth,
        "boxheight": req.boxheight,
        "items": [item.model_dump() for item in req.items],
        "notes": req.notes,
    }


def _quote_fee(validated: dict[str, Any], *, live: bool) -> int | None:
    method = validated["method"]
    if not live:
        return mock_quote_fee(validated["totweight"], method["premiumcd"])
    try:
        quoted = get_shipping_quote(
            method["premiumcd"],
            method["em_ee"],
            validated["countrycd"],
            validated["totweight"],
            boxlength=validated["boxlength"],
            boxwidth=validated["boxwidth"],
            boxheight=validated["boxheight"],
        )
        return int(quoted["totalFee"])
    except Exception:
        return None


def _preview_payload(validated: dict[str, Any], *, is_test: bool, fee: int | None) -> dict[str, Any]:
    sender = validated["sender"]
    method = validated["method"]
    return {
        "shipping_method": method["code"],
        "shipping_method_name": method["name"],
        "countrycd": validated["countrycd"],
        "recipient_name": validated["receivename"],
        "recipient_phone": validated["receivetelno"],
        "recipient_email": validated["receivemail"],
        "recipient_zip": validated["receivezipcode"],
        "recipient_addr": " ".join(
            p for p in (
                validated["receiveaddr1"],
                validated["receiveaddr2"],
                validated["receiveaddr3"],
            ) if p
        ),
        "totweight": validated["totweight"],
        "boxlength": validated["boxlength"],
        "boxwidth": validated["boxwidth"],
        "boxheight": validated["boxheight"],
        "items": validated["items"],
        "sender_name": sender["name"],
        "sender_addr": f"{sender['addr1']}, {sender['addr2']}, {sender['addr3']} {sender['zipcode']}",
        "expected_fee": fee,
        "is_test": is_test,
        "notes": validated.get("notes") or "",
    }


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    keys = [
        "id",
        "order_no",
        "shipping_method",
        "premiumcd",
        "countrycd",
        "recipient_name",
        "recipient_phone",
        "recipient_email",
        "recipient_zip",
        "recipient_addr1",
        "recipient_addr2",
        "recipient_addr3",
        "totweight",
        "boxlength",
        "boxwidth",
        "boxheight",
        "item_list",
        "tracking_no",
        "req_no",
        "receive_seq",
        "ems_fee",
        "post_office",
        "status",
        "is_test",
        "notes",
        "created_by",
        "created_at",
        "canceled_at",
        "canceled_by",
    ]
    data = dict(zip(keys, row))
    data["is_test"] = bool(data["is_test"])
    try:
        data["items"] = json.loads(data.pop("item_list") or "[]")
    except json.JSONDecodeError:
        data["items"] = []
    return data


@router.get("/meta")
def overseas_meta(token: str):
    _get_user(token)
    ensure_overseas_tables()
    sender = resolve_sender()
    return {
        "live_ready": has_ems_credentials(),
        "methods": SHIPPING_METHODS,
        "sender": {
            "name": sender["name"],
            "addr": f"{sender['addr1']}, {sender['addr2']}, {sender['addr3']}",
            "zip": sender["zipcode"],
        },
    }


@router.get("/nations")
def overseas_nations(token: str, premiumcd: str = "31"):
    _get_user(token)
    code = (premiumcd or "31").strip()
    if code not in {"31", "32", "14"}:
        raise HTTPException(status_code=400, detail="잘못된 배송방법 코드입니다.")
    if not has_ems_credentials():
        return {"items": [{**n, "premiumcd": code} for n in FALLBACK_NATIONS], "fallback": True}
    try:
        return {"items": get_available_nations(code), "fallback": False}
    except Exception:
        return {"items": [{**n, "premiumcd": code} for n in FALLBACK_NATIONS], "fallback": True}


@router.post("/preview")
def preview_overseas(req: OverseasSubmitRequest, token: str):
    _get_user(token)
    live = has_ems_credentials() and not req.test_mode
    try:
        validated = validate_apply_input(_req_dict(req))
    except ValueError as exc:
        raise _http_error(exc) from exc
    fee = _quote_fee(validated, live=live)
    return {"ok": True, "preview": _preview_payload(validated, is_test=not live, fee=fee)}


@router.get("")
def list_overseas(token: str, limit: int = 500):
    _get_user(token)
    ensure_overseas_tables()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT id, order_no, shipping_method, premiumcd, countrycd,
                   recipient_name, recipient_phone, recipient_email, recipient_zip,
                   recipient_addr1, recipient_addr2, recipient_addr3,
                   totweight, boxlength, boxwidth, boxheight, item_list,
                   tracking_no, req_no, receive_seq, ems_fee, post_office,
                   status, is_test, notes, created_by, created_at, canceled_at, canceled_by
            FROM overseas_shipping_requests
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 2000)),),
        ).fetchall()
    return {"items": [_row_to_dict(row) for row in rows]}


@router.post("")
def create_overseas(req: OverseasSubmitRequest, token: str):
    user = _get_user(token)
    ensure_overseas_tables()
    if not req.confirm:
        raise HTTPException(status_code=400, detail="접수 확인이 필요합니다. 다시 시도해주세요.")

    live = has_ems_credentials() and not req.test_mode
    try:
        validated = validate_apply_input(_req_dict(req))
    except ValueError as exc:
        raise _http_error(exc) from exc

    today = datetime.now(KST).date().isoformat()
    with get_connection() as con:
        existing = con.execute(
            """
            SELECT id, tracking_no FROM overseas_shipping_requests
            WHERE created_by=? AND recipient_phone=? AND countrycd=?
              AND status='requested' AND created_at LIKE ?
            ORDER BY id DESC LIMIT 1
            """,
            (user["nickname"], validated["receivetelno"], validated["countrycd"], f"{today}%"),
        ).fetchone()
    if existing and validated["receivetelno"]:
        return {
            "duplicate_guard": True,
            "success": True,
            "id": existing[0],
            "tracking_no": existing[1],
        }

    order_no = f"TIL-{int(time.time() * 1000)}"
    params = build_apply_params(
        validated,
        order_no=order_no,
        custno=env_clean("EMS_CUSTOMER_NO") or "TEST",
        apprno=env_clean("EMS_APPROVAL_NO") or "0000000000",
    )
    try:
        result = (
            apply_ems(params)
            if live
            else mock_apply_ems(
                validated["method"]["premiumcd"],
                validated["method"]["em_ee"],
                validated["countrycd"],
            )
        )
    except EmsApiError as exc:
        raise _http_error(exc) from exc

    tracking = (result.get("regino") or "").strip()
    if live and len(tracking) < 10:
        raise HTTPException(status_code=502, detail="우체국이 등기번호를 반환하지 않았습니다.")

    fee = result.get("prerecevprc") or "0"
    created_at = datetime.now(KST).isoformat(timespec="seconds")
    with get_connection() as con:
        cur = con.execute(
            """
            INSERT INTO overseas_shipping_requests (
                order_no, shipping_method, premiumcd, countrycd,
                recipient_name, recipient_phone, recipient_email, recipient_zip,
                recipient_addr1, recipient_addr2, recipient_addr3,
                totweight, boxlength, boxwidth, boxheight, item_list,
                tracking_no, req_no, receive_seq, ems_fee, post_office,
                status, is_test, apply_snapshot, notes, created_by, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                order_no,
                validated["method"]["code"],
                validated["method"]["premiumcd"],
                validated["countrycd"],
                validated["receivename"],
                validated["receivetelno"],
                validated["receivemail"],
                validated["receivezipcode"],
                validated["receiveaddr1"],
                validated["receiveaddr2"],
                validated["receiveaddr3"],
                validated["totweight"],
                validated["boxlength"],
                validated["boxwidth"],
                validated["boxheight"],
                json.dumps(validated["items"], ensure_ascii=False),
                tracking,
                result.get("reqno") or "",
                result.get("receiveseq") or "",
                str(fee),
                result.get("treatporegipoengnm") or "",
                "requested",
                0 if live else 1,
                json.dumps({k: v for k, v in params.items() if k not in {"custno", "apprno"}}, ensure_ascii=False),
                validated.get("notes") or "",
                user["nickname"],
                created_at,
            ),
        )
        row_id = cur.lastrowid
        con.commit()

    add_log(
        action_type="해외배송접수",
        target_type="overseas_shipping",
        target_id=str(row_id),
        target_name=tracking or order_no,
        user_nickname=user["nickname"],
        details=f"{validated['receivename']} / {validated['countrycd']} / {validated['method']['code']}",
    )
    return {
        "success": True,
        "id": row_id,
        "order_no": order_no,
        "tracking_no": tracking,
        "ems_fee": str(fee),
        "is_test": not live,
        "preview": _preview_payload(validated, is_test=not live, fee=int(fee) if str(fee).isdigit() else None),
    }


@router.post("/{shipment_id}/cancel")
def cancel_overseas(shipment_id: int, token: str, confirm: bool = False):
    user = _get_user(token)
    if not confirm:
        raise HTTPException(status_code=400, detail="확인 후에만 취소할 수 있습니다.")
    ensure_overseas_tables()
    with get_connection() as con:
        row = con.execute(
            """
            SELECT id, status, is_test, req_no, tracking_no
            FROM overseas_shipping_requests WHERE id = ?
            """,
            (shipment_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="접수 내역을 찾을 수 없습니다.")
    if row[1] == "canceled":
        return {"success": True, "already": True, "message": "이미 취소된 접수입니다."}

    if not row[2]:
        req_no = row[3] or ""
        tracking = row[4] or ""
        if req_no and tracking:
            try:
                canceled = cancel_ems(req_no, tracking)
                if canceled.get("canceledyn") == "N" and canceled.get("notcancelreason"):
                    raise HTTPException(
                        status_code=502,
                        detail=f"우체국 취소 불가: {canceled['notcancelreason']}",
                    )
            except HTTPException:
                raise
            except Exception as exc:
                msg = str(exc)
                if "ERR-" in msg or "없" in msg:
                    pass
                else:
                    raise HTTPException(status_code=502, detail=msg) from exc

    canceled_at = datetime.now(KST).isoformat(timespec="seconds")
    with get_connection() as con:
        con.execute(
            """
            UPDATE overseas_shipping_requests
            SET status='canceled', canceled_at=?, canceled_by=?
            WHERE id=?
            """,
            (canceled_at, user["nickname"], shipment_id),
        )
        con.commit()
    return {"success": True, "message": "해외배송 접수를 취소했습니다."}
