"""국내 출고 송장. 계약은 하나이고, 박스 1개당 송장 1장이다.

우체국 API에는 업체에 저장된 보내는 사람과 공급지번호를 보낸다.
송장에는 접수 화면에서 입력한 보내는 사람을 찍는다.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.app.api.kpost_pickup import _get_user
from backend.app.api.kpost_pickup.tracking import _apply_tracking_info
from backend.app.api.logs import add_log
from backend.app.services.epost.client import (
    EpostError,
    cancel_order,
    get_res_info,
    has_epost_credentials,
    insert_order,
    lookup_req_ymds,
    mock_insert_order,
    track_regi_no,
)
from backend.app.services.epost.domestic_label import (
    build_domestic_label_pdf,
    build_domestic_labels_pdf,
)
from backend.app.services.epost.fields import (
    EPOST_CONTRACT_COMP_NM,
    FINAL_TREAT_STATUSES,
    PICKUP_BOX_SIZES,
    normalize_addr1,
    normalize_phone,
    normalize_zip,
    require_phone,
    resolve_box_spec,
    resolve_cancel_req_ymd,
    resolve_infront_center,
    resolve_office_ser,
    sanitize_plain_field,
    truncate_utf8_bytes,
)
from logic.db import get_connection

router = APIRouter(prefix="/domestic-shipping", tags=["domestic-shipping"])
KST = ZoneInfo("Asia/Seoul")
_DUP_WINDOW = timedelta(seconds=20)
# 계약소포 출고. 1=일반, 선불.
_REQ_TYPE = "1"
_PAY_TYPE = "1"
_CONT_CD = "025"


class DomesticVendorRequest(BaseModel):
    name: str
    office_ser: str
    sender_name: str
    sender_phone: str
    sender_zip: str
    sender_addr1: str
    sender_addr2: str = ""


class DomesticSubmitRequest(BaseModel):
    vendor_id: int
    print_sender_name: str = ""
    print_sender_phone: str = ""
    print_sender_zip: str = ""
    print_sender_addr1: str = ""
    print_sender_addr2: str = ""
    recipient_name: str
    recipient_phone: str
    recipient_zip: str
    recipient_addr1: str
    recipient_addr2: str = ""
    goods_name: str
    goods_qty: int = 1
    box_size: str = "MICRO"
    label_count: int = 1
    notes: str = ""
    confirm: bool = False
    test_mode: bool = False


def ensure_domestic_tables() -> None:
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS domestic_vendors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                office_ser TEXT NOT NULL,
                sender_name TEXT NOT NULL,
                sender_phone TEXT NOT NULL,
                sender_zip TEXT NOT NULL,
                sender_addr1 TEXT NOT NULL,
                sender_addr2 TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS domestic_shipments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_id INTEGER,
                vendor_name TEXT,
                office_ser TEXT,
                api_sender_name TEXT,
                api_sender_phone TEXT,
                api_sender_zip TEXT,
                api_sender_addr1 TEXT,
                api_sender_addr2 TEXT,
                print_sender_name TEXT,
                print_sender_phone TEXT,
                print_sender_zip TEXT,
                print_sender_addr1 TEXT,
                print_sender_addr2 TEXT,
                recipient_name TEXT,
                recipient_phone TEXT,
                recipient_zip TEXT,
                recipient_addr1 TEXT,
                recipient_addr2 TEXT,
                goods_name TEXT,
                box_size TEXT,
                weight INTEGER,
                volume INTEGER,
                notes TEXT,
                order_no TEXT,
                tracking_no TEXT,
                req_no TEXT,
                res_no TEXT,
                res_date TEXT,
                price TEXT,
                post_office TEXT,
                status TEXT NOT NULL DEFAULT 'requested',
                is_test INTEGER NOT NULL DEFAULT 0,
                created_by TEXT,
                created_at TEXT NOT NULL,
                canceled_at TEXT,
                canceled_by TEXT
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_domestic_shipments_created ON domestic_shipments(created_at DESC)"
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS domestic_saved_recipients (
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
            "CREATE INDEX IF NOT EXISTS idx_domestic_saved_recipients_user "
            "ON domestic_saved_recipients(user_id, created_at DESC)"
        )
        columns = {row[1] for row in con.execute("PRAGMA table_info(domestic_shipments)")}
        if "v_tel_no" not in columns:
            con.execute("ALTER TABLE domestic_shipments ADD COLUMN v_tel_no TEXT NOT NULL DEFAULT ''")
        columns = {row[1] for row in con.execute("PRAGMA table_info(domestic_shipments)")}
        if "goods_qty" not in columns:
            con.execute("ALTER TABLE domestic_shipments ADD COLUMN goods_qty INTEGER NOT NULL DEFAULT 1")
        columns = {row[1] for row in con.execute("PRAGMA table_info(domestic_shipments)")}
        if "treat_status" not in columns:
            con.execute("ALTER TABLE domestic_shipments ADD COLUMN treat_status TEXT")
        if "treat_status_name" not in columns:
            con.execute("ALTER TABLE domestic_shipments ADD COLUMN treat_status_name TEXT")
        _seed_spring_vendor(con)
        con.commit()


def _seed_spring_vendor(con) -> None:
    """회수접수 센터 정보로 스프링풀필먼트 출고 업체를 한 번만 넣는다."""
    name = EPOST_CONTRACT_COMP_NM
    exists = con.execute("SELECT 1 FROM domestic_vendors WHERE name=?", (name,)).fetchone()
    if exists:
        return
    from backend.app.api.kpost_pickup.pickup import _env
    from backend.app.config import settings

    env = _env()
    center = resolve_infront_center(env)
    phone = center.get("phone") or f"0{settings.EMS_SENDER_TEL2}{settings.EMS_SENDER_TEL3}{settings.EMS_SENDER_TEL4}"
    now = datetime.now(KST).isoformat(timespec="seconds")
    con.execute(
        """
        INSERT INTO domestic_vendors (
            name, office_ser, sender_name, sender_phone, sender_zip,
            sender_addr1, sender_addr2, created_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            resolve_office_ser(env),
            name,
            phone,
            center["zip"],
            center["addr1"],
            center["addr2"],
            "시스템",
            now,
        ),
    )


def _clean(value: Any, *, max_bytes: int = 100) -> str:
    return truncate_utf8_bytes(sanitize_plain_field(str(value or "")), max_bytes)


def _office_ser(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        raise ValueError("공급지번호를 입력해주세요.")
    return digits


def _vendor_row(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "office_ser": row[2],
        "sender_name": row[3],
        "sender_phone": row[4],
        "sender_zip": row[5],
        "sender_addr1": row[6],
        "sender_addr2": row[7] or "",
        "created_by": row[8] or "",
        "created_at": row[9],
    }


def _load_vendor(vendor_id: int) -> dict[str, Any]:
    with get_connection() as con:
        row = con.execute(
            """
            SELECT id, name, office_ser, sender_name, sender_phone, sender_zip,
                   sender_addr1, sender_addr2, created_by, created_at
            FROM domestic_vendors WHERE id=?
            """,
            (vendor_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="출고 업체를 찾을 수 없습니다.")
    return _vendor_row(row)


def _party(name: str, phone: str, zipcode: str, addr1: str, addr2: str, who: str) -> dict[str, str]:
    shown_name = _clean(name, max_bytes=40)
    if len(shown_name) < 1:
        raise ValueError(f"{who} 이름을 입력해주세요.")
    shown_phone = require_phone(phone, f"{who} 전화")
    shown_zip = normalize_zip(zipcode)
    if len(shown_zip) != 5:
        raise ValueError(f"{who} 우편번호 5자리를 입력해주세요.")
    road = normalize_addr1(_clean(addr1))
    if len(road) < 2:
        raise ValueError(f"{who} 주소를 입력해주세요.")
    detail = _clean(addr2)
    return {
        "name": shown_name,
        "phone": shown_phone,
        "zip": shown_zip,
        "addr1": road,
        "addr2": detail,
    }


def _print_sender(req: DomesticSubmitRequest, saved: dict[str, str]) -> dict[str, str]:
    """출력용. 이름을 비우면 업체 저장값을 그대로 쓴다."""
    if not str(req.print_sender_name or "").strip():
        return saved
    return _party(
        req.print_sender_name,
        req.print_sender_phone or saved["phone"],
        req.print_sender_zip or saved["zip"],
        req.print_sender_addr1 or saved["addr1"],
        req.print_sender_addr2,
        "보내는 사람",
    )


def _saved_sender(vendor: dict[str, Any]) -> dict[str, str]:
    return _party(
        vendor["sender_name"],
        vendor["sender_phone"],
        vendor["sender_zip"],
        vendor["sender_addr1"],
        vendor["sender_addr2"],
        "업체 보내는 사람",
    )


def _validate(req: DomesticSubmitRequest) -> dict[str, Any]:
    vendor = _load_vendor(req.vendor_id)
    if not str(vendor["office_ser"] or "").strip():
        raise ValueError("공급지번호가 없는 업체는 접수할 수 없습니다.")
    saved = _saved_sender(vendor)
    printed = _print_sender(req, saved)
    recipient = _party(
        req.recipient_name,
        req.recipient_phone,
        req.recipient_zip,
        req.recipient_addr1,
        req.recipient_addr2,
        "받는 사람",
    )
    goods = _clean(req.goods_name, max_bytes=40)
    if not goods:
        raise ValueError("상품명을 입력해주세요.")
    spec = resolve_box_spec(req.box_size)
    return {
        "vendor": vendor,
        "saved": saved,
        "printed": printed,
        "recipient": recipient,
        "goods": goods,
        "goods_qty": _bounded_count(req.goods_qty, "상품수량"),
        "label_count": _bounded_count(req.label_count, "송장 갯수"),
        "spec": spec,
        "notes": _clean(req.notes, max_bytes=50),
    }


def _bounded_count(value: int, name: str) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name}는 1에서 99 사이여야 합니다.") from None
    if count < 1 or count > 99:
        raise ValueError(f"{name}는 1에서 99 사이여야 합니다.")
    return count


def _api_params(data: dict[str, Any], order_no: str, *, test_yn: str) -> dict[str, str]:
    saved = data["saved"]
    recipient = data["recipient"]
    spec = data["spec"]
    body = {
        "payType": _PAY_TYPE,
        "reqType": _REQ_TYPE,
        "officeSer": data["vendor"]["office_ser"],
        "orderNo": order_no,
        "ordCompNm": EPOST_CONTRACT_COMP_NM,
        "ordNm": saved["name"],
        "inqTelCn": saved["phone"],
        "ordZip": saved["zip"],
        "ordAddr1": saved["addr1"],
        "ordAddr2": saved["addr2"] or "-",
        "ordTel": saved["phone"],
        "ordMob": saved["phone"],
        "recNm": recipient["name"],
        "recZip": recipient["zip"],
        "recAddr1": recipient["addr1"],
        "recAddr2": recipient["addr2"] or "-",
        "recTel": recipient["phone"],
        "recMob": recipient["phone"],
        "contCd": _CONT_CD,
        "goodsNm": data["goods"],
        "weight": int(spec["weight"]),
        "volume": int(spec["volume"]),
        "qty": data["goods_qty"],
        "microYn": "Y" if spec.get("micro") else "N",
        "printYn": "Y",
        "testYn": test_yn,
    }
    if data["notes"]:
        body["delivMsg"] = data["notes"]
    return body


def _preview(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "vendor_name": data["vendor"]["name"],
        "office_ser": data["vendor"]["office_ser"],
        "api_sender": data["saved"],
        "print_sender": data["printed"],
        "recipient": data["recipient"],
        "goods_name": data["goods"],
        "goods_qty": data["goods_qty"],
        "label_count": data["label_count"],
        "box_size": data["spec"]["code"],
        "box_label": data["spec"]["label"],
        "weight": data["spec"]["weight"],
        "volume": data["spec"]["volume"],
    }


def _shipment_dict(row: tuple) -> dict[str, Any]:
    keys = (
        "id", "vendor_id", "vendor_name", "office_ser",
        "api_sender_name", "api_sender_phone", "api_sender_zip", "api_sender_addr1", "api_sender_addr2",
        "print_sender_name", "print_sender_phone", "print_sender_zip", "print_sender_addr1", "print_sender_addr2",
        "recipient_name", "recipient_phone", "recipient_zip", "recipient_addr1", "recipient_addr2",
        "goods_name", "box_size", "weight", "volume", "notes",
        "order_no", "tracking_no", "req_no", "res_no", "res_date", "price", "post_office",
        "status", "is_test", "created_by", "created_at", "canceled_at", "canceled_by",
        "v_tel_no", "goods_qty", "treat_status", "treat_status_name",
    )
    item = dict(zip(keys, row))
    item["is_test"] = bool(item["is_test"])
    return item


def _load_shipment(shipment_id: int) -> dict[str, Any]:
    with get_connection() as con:
        row = con.execute("SELECT * FROM domestic_shipments WHERE id=?", (shipment_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="접수 내역을 찾을 수 없습니다.")
    return _shipment_dict(row)


def _http_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/meta")
def domestic_meta(token: str):
    _get_user(token)
    ensure_domestic_tables()
    return {
        "live_ready": has_epost_credentials(),
        "box_sizes": PICKUP_BOX_SIZES,
        "contract": "one",
    }


@router.get("/vendors")
def list_vendors(token: str):
    _get_user(token)
    ensure_domestic_tables()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT id, name, office_ser, sender_name, sender_phone, sender_zip,
                   sender_addr1, sender_addr2, created_by, created_at
            FROM domestic_vendors ORDER BY id DESC
            """
        ).fetchall()
    return {"items": [_vendor_row(row) for row in rows]}


@router.post("/vendors")
def create_vendor(req: DomesticVendorRequest, token: str):
    user = _get_user(token)
    ensure_domestic_tables()
    try:
        name = _clean(req.name, max_bytes=40)
        if not name:
            raise ValueError("업체명을 입력해주세요.")
        office = _office_ser(req.office_ser)
        sender = _party(req.sender_name, req.sender_phone, req.sender_zip, req.sender_addr1, req.sender_addr2, "보내는 사람")
    except ValueError as exc:
        raise _http_error(exc) from exc
    now = datetime.now(KST).isoformat(timespec="seconds")
    with get_connection() as con:
        cur = con.execute(
            """
            INSERT INTO domestic_vendors (
                name, office_ser, sender_name, sender_phone, sender_zip,
                sender_addr1, sender_addr2, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name, office, sender["name"], sender["phone"], sender["zip"],
                sender["addr1"], sender["addr2"], user["nickname"], now,
            ),
        )
        con.commit()
        vendor_id = int(cur.lastrowid)
    return {"success": True, "id": vendor_id}


@router.put("/vendors/{vendor_id}")
def update_vendor(vendor_id: int, req: DomesticVendorRequest, token: str):
    user = _get_user(token)
    ensure_domestic_tables()
    _load_vendor(vendor_id)
    try:
        name = _clean(req.name, max_bytes=40)
        if not name:
            raise ValueError("업체명을 입력해주세요.")
        office = _office_ser(req.office_ser)
        sender = _party(req.sender_name, req.sender_phone, req.sender_zip, req.sender_addr1, req.sender_addr2, "보내는 사람")
    except ValueError as exc:
        raise _http_error(exc) from exc
    with get_connection() as con:
        con.execute(
            """
            UPDATE domestic_vendors
            SET name=?, office_ser=?, sender_name=?, sender_phone=?, sender_zip=?,
                sender_addr1=?, sender_addr2=?
            WHERE id=?
            """,
            (name, office, sender["name"], sender["phone"], sender["zip"], sender["addr1"], sender["addr2"], vendor_id),
        )
        con.commit()
    add_log(
        action_type="국내출고업체수정",
        target_type="domestic_vendor",
        target_id=str(vendor_id),
        target_name=name,
        user_nickname=user["nickname"],
    )
    return {"success": True, "id": vendor_id}


@router.delete("/vendors/{vendor_id}")
def delete_vendor(vendor_id: int, token: str):
    user = _get_user(token)
    ensure_domestic_tables()
    vendor = _load_vendor(vendor_id)
    with get_connection() as con:
        con.execute("DELETE FROM domestic_vendors WHERE id=?", (vendor_id,))
        con.commit()
    add_log(
        action_type="국내출고업체삭제",
        target_type="domestic_vendor",
        target_id=str(vendor_id),
        target_name=vendor["name"],
        user_nickname=user["nickname"],
    )
    return {"success": True}


@router.post("/preview")
def preview_domestic(req: DomesticSubmitRequest, token: str):
    _get_user(token)
    ensure_domestic_tables()
    try:
        data = _validate(req)
    except ValueError as exc:
        raise _http_error(exc) from exc
    return {"ok": True, "preview": _preview(data), "live_ready": has_epost_credentials()}


@router.get("")
def list_domestic(token: str):
    _get_user(token)
    ensure_domestic_tables()
    with get_connection() as con:
        rows = con.execute(
            "SELECT * FROM domestic_shipments ORDER BY id DESC LIMIT 500"
        ).fetchall()
    return {"items": [_shipment_dict(row) for row in rows]}


def _sync_domestic_tracking(item: dict[str, Any]) -> dict[str, Any]:
    """출고는 일반 계약소포(reqType 1)다. 접수조회 다음 종적조회로 배송상태를 받는다."""
    if item.get("order_no"):
        for req_ymd in lookup_req_ymds(item.get("res_date"), item.get("created_at")):
            try:
                info = get_res_info(item["order_no"], req_ymd, "1")
            except Exception:
                continue
            _apply_tracking_info(item, info)
            break
    if item.get("treat_status") not in FINAL_TREAT_STATUSES and item.get("tracking_no"):
        try:
            _apply_tracking_info(item, track_regi_no(item["tracking_no"]))
        except Exception:
            pass
    return item


@router.post("/refresh-status")
def refresh_domestic_statuses(token: str):
    """접수 목록의 실접수 송장을 우체국에 물어 배송상태를 저장한다."""
    _get_user(token)
    ensure_domestic_tables()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT * FROM domestic_shipments
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
    items = [_shipment_dict(row) for row in rows]
    checked = 0
    delivered = 0
    failed = 0

    def _process(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if item.get("treat_status") in FINAL_TREAT_STATUSES:
            return "skip", item
        try:
            _sync_domestic_tracking(item)
            return "checked", item
        except Exception:
            return "failed", item

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_process, item) for item in items]
        for future in as_completed(futures):
            status, item = future.result()
            if status == "checked":
                with get_connection() as con:
                    con.execute(
                        """
                        UPDATE domestic_shipments
                        SET treat_status=?, treat_status_name=?, tracking_no=?
                        WHERE id=?
                        """,
                        (item.get("treat_status"), item.get("treat_status_name"), item.get("tracking_no"), item["id"]),
                    )
                    con.commit()
                checked += 1
                if item.get("treat_status") == "배달완료":
                    delivered += 1
            elif status == "failed":
                failed += 1
    return {
        "success": True,
        "checked": checked,
        "delivered": delivered,
        "failed": failed,
        "message": (
            f"송장 {checked}건 조회. 배달완료 {delivered}건"
            + (f" / 조회실패 {failed}건" if failed else "")
        ),
    }


def _parse_label_ids(raw: str) -> list[int]:
    parts = [part.strip() for part in (raw or "").split(",") if part.strip()]
    if not parts or len(parts) > 99:
        raise HTTPException(status_code=400, detail="송장은 1장에서 99장까지 지정해주세요.")
    ids: list[int] = []
    for part in parts:
        if not part.isdigit():
            raise HTTPException(status_code=400, detail="송장 번호가 올바르지 않습니다.")
        ids.append(int(part))
    return ids


class DomesticSavedRecipientRequest(BaseModel):
    label: str
    recipient_name: str
    recipient_phone: str
    zipcode: str
    addr1: str
    addr2: str = ""


def _saved_recipient_fields(req: DomesticSavedRecipientRequest) -> dict[str, str]:
    label = (req.label or "").strip()
    if len(label) < 1:
        raise HTTPException(status_code=400, detail="라벨을 입력해주세요.")
    if len(label) > 50:
        raise HTTPException(status_code=400, detail="라벨은 50자 이하여야 합니다.")
    name = (req.recipient_name or "").strip()
    if len(name) < 1:
        raise HTTPException(status_code=400, detail="받는 사람 이름을 입력해주세요.")
    phone = normalize_phone(req.recipient_phone)
    if len(phone) < 9:
        raise HTTPException(status_code=400, detail="전화번호를 입력해주세요.")
    zipcode = normalize_zip(req.zipcode)
    if len(zipcode) != 5:
        raise HTTPException(status_code=400, detail="우편번호 5자리가 필요합니다.")
    addr1 = (req.addr1 or "").strip()
    if len(addr1) < 2:
        raise HTTPException(status_code=400, detail="주소를 입력해주세요.")
    return {
        "label": label,
        "recipient_name": name,
        "recipient_phone": phone,
        "zipcode": zipcode,
        "addr1": addr1,
        "addr2": (req.addr2 or "").strip(),
    }


def _saved_recipient_item(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "label": row[1],
        "recipient_name": row[2],
        "recipient_phone": row[3],
        "zipcode": row[4],
        "addr1": row[5],
        "addr2": row[6] or "",
        "created_at": row[7],
    }


@router.get("/saved-recipients")
def list_domestic_saved_recipients(token: str):
    user = _get_user(token)
    ensure_domestic_tables()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT id, label, recipient_name, recipient_phone, zipcode, addr1, addr2, created_at
            FROM domestic_saved_recipients
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user["user_id"],),
        ).fetchall()
    return {"items": [_saved_recipient_item(row) for row in rows]}


@router.post("/saved-recipients")
def save_domestic_recipient(req: DomesticSavedRecipientRequest, token: str):
    user = _get_user(token)
    ensure_domestic_tables()
    fields = _saved_recipient_fields(req)
    created_at = datetime.now(KST).isoformat(timespec="seconds")
    with get_connection() as con:
        existing = con.execute(
            "SELECT id, label, recipient_name, recipient_phone, zipcode, addr1, addr2, created_at "
            "FROM domestic_saved_recipients WHERE user_id=? AND label=?",
            (user["user_id"], fields["label"]),
        ).fetchone()
        if existing:
            item = _saved_recipient_item(existing)
            return {"success": True, **item}
        try:
            cur = con.execute(
                """
                INSERT INTO domestic_saved_recipients (
                    user_id, label, recipient_name, recipient_phone, zipcode, addr1, addr2, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["user_id"], fields["label"], fields["recipient_name"], fields["recipient_phone"],
                    fields["zipcode"], fields["addr1"], fields["addr2"], created_at,
                ),
            )
            con.commit()
            recipient_id = int(cur.lastrowid)
        except Exception as exc:
            if "UNIQUE constraint" not in str(exc):
                raise
            row = con.execute(
                "SELECT id, label, recipient_name, recipient_phone, zipcode, addr1, addr2, created_at "
                "FROM domestic_saved_recipients WHERE user_id=? AND label=?",
                (user["user_id"], fields["label"]),
            ).fetchone()
            if not row:
                raise
            return {"success": True, **_saved_recipient_item(row)}
    return {"success": True, "id": recipient_id, "created_at": created_at, **fields}


@router.put("/saved-recipients/{recipient_id}")
def update_domestic_saved_recipient(recipient_id: int, req: DomesticSavedRecipientRequest, token: str):
    user = _get_user(token)
    ensure_domestic_tables()
    fields = _saved_recipient_fields(req)
    with get_connection() as con:
        row = con.execute(
            "SELECT id, user_id FROM domestic_saved_recipients WHERE id=?",
            (recipient_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="저장된 주소지를 찾을 수 없습니다.")
        if row[1] != user["user_id"]:
            raise HTTPException(status_code=403, detail="다른 사용자의 주소지는 수정할 수 없습니다.")
        conflict = con.execute(
            "SELECT id FROM domestic_saved_recipients WHERE user_id=? AND label=? AND id!=?",
            (user["user_id"], fields["label"], recipient_id),
        ).fetchone()
        if conflict:
            raise HTTPException(status_code=400, detail=f"'{fields['label']}' 라벨은 이미 사용 중입니다.")
        con.execute(
            """
            UPDATE domestic_saved_recipients
            SET label=?, recipient_name=?, recipient_phone=?, zipcode=?, addr1=?, addr2=?
            WHERE id=?
            """,
            (
                fields["label"], fields["recipient_name"], fields["recipient_phone"],
                fields["zipcode"], fields["addr1"], fields["addr2"], recipient_id,
            ),
        )
        con.commit()
    add_log(
        action_type="국내출고주소지수정",
        target_type="domestic_saved_recipient",
        target_id=str(recipient_id),
        target_name=fields["label"],
        user_nickname=user["nickname"],
        details=f"{fields['recipient_name']} / {fields['zipcode']}",
    )
    return {"success": True, "id": recipient_id, "label": fields["label"]}


@router.delete("/saved-recipients/{recipient_id}")
def delete_domestic_saved_recipient(recipient_id: int, token: str):
    user = _get_user(token)
    ensure_domestic_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT id, user_id, label FROM domestic_saved_recipients WHERE id=?",
            (recipient_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="저장된 주소지를 찾을 수 없습니다.")
        if row[1] != user["user_id"]:
            raise HTTPException(status_code=403, detail="다른 사용자의 주소지는 삭제할 수 없습니다.")
        con.execute("DELETE FROM domestic_saved_recipients WHERE id=?", (recipient_id,))
        con.commit()
    return {"success": True, "id": recipient_id}


@router.get("/labels")
def domestic_labels(token: str, ids: str = "", format: str = "pdf"):
    _get_user(token)
    ensure_domestic_tables()
    wanted = _parse_label_ids(ids)
    items = [_load_shipment(shipment_id) for shipment_id in wanted]
    if format != "pdf":
        return {"ok": True, "items": items}
    pdf = build_domestic_labels_pdf(items)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="domestic-labels.pdf"'},
    )


@router.get("/{shipment_id}")
def get_domestic(shipment_id: int, token: str):
    _get_user(token)
    ensure_domestic_tables()
    return _load_shipment(shipment_id)


def _store_shipment(
    data: dict[str, Any],
    order_no: str,
    result: dict[str, Any],
    *,
    live: bool,
    user_name: str,
    created_at: str,
) -> int:
    saved = data["saved"]
    printed = data["printed"]
    recipient = data["recipient"]
    with get_connection() as con:
        cur = con.execute(
            """
            INSERT INTO domestic_shipments (
                vendor_id, vendor_name, office_ser,
                api_sender_name, api_sender_phone, api_sender_zip, api_sender_addr1, api_sender_addr2,
                print_sender_name, print_sender_phone, print_sender_zip, print_sender_addr1, print_sender_addr2,
                recipient_name, recipient_phone, recipient_zip, recipient_addr1, recipient_addr2,
                goods_name, box_size, weight, volume, notes,
                order_no, tracking_no, req_no, res_no, res_date, price, post_office,
                status, is_test, created_by, created_at, v_tel_no, goods_qty,
                treat_status, treat_status_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'requested', ?, ?, ?, ?, ?, '신청접수', '신청접수')
            """,
            (
                data["vendor"]["id"], data["vendor"]["name"], data["vendor"]["office_ser"],
                saved["name"], saved["phone"], saved["zip"], saved["addr1"], saved["addr2"],
                printed["name"], printed["phone"], printed["zip"], printed["addr1"], printed["addr2"],
                recipient["name"], recipient["phone"], recipient["zip"], recipient["addr1"], recipient["addr2"],
                data["goods"], data["spec"]["code"], int(data["spec"]["weight"]), int(data["spec"]["volume"]),
                data["notes"],
                order_no, result.get("regiNo") or "", result.get("reqNo") or "", result.get("resNo") or "",
                result.get("resDate") or "", result.get("price") or "", result.get("regiPoNm") or "",
                0 if live else 1, user_name, created_at, result.get("vTelNo") or "", data["goods_qty"],
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def _created_payload(rows: list[tuple], *, requested: int, live: bool, data: dict[str, Any], duplicate: bool) -> dict[str, Any]:
    ids = [int(row[0]) for row in rows]
    trackings = [row[1] or "" for row in rows]
    return {
        "duplicate_guard": duplicate,
        "success": True,
        "id": ids[0],
        "ids": ids,
        "order_no": rows[0][2] or "",
        "tracking_no": trackings[0],
        "tracking_nos": trackings,
        "price": rows[0][3] or "",
        "partial": len(ids) < requested,
        "is_test": not live,
        "preview": _preview(data),
    }


@router.post("")
def create_domestic(req: DomesticSubmitRequest, token: str):
    user = _get_user(token)
    ensure_domestic_tables()
    if not req.confirm:
        raise HTTPException(status_code=400, detail="접수 확인이 필요합니다. 다시 시도해주세요.")
    try:
        data = _validate(req)
    except ValueError as exc:
        raise _http_error(exc) from exc

    requested = data["label_count"]
    recent = (datetime.now(KST) - _DUP_WINDOW).isoformat(timespec="seconds")
    with get_connection() as con:
        existing = con.execute(
            """
            SELECT id, tracking_no, order_no, price FROM domestic_shipments
            WHERE created_by=? AND vendor_id=? AND recipient_phone=? AND status='requested'
              AND created_at>=?
            ORDER BY id ASC
            """,
            (user["nickname"], data["vendor"]["id"], data["recipient"]["phone"], recent),
        ).fetchall()
    if len(existing) >= requested:
        return _created_payload(existing[-requested:], requested=requested, live=not req.test_mode and has_epost_credentials(), data=data, duplicate=True)
    remaining = requested - len(existing)

    live = has_epost_credentials() and not req.test_mode
    now = datetime.now(KST).isoformat(timespec="seconds")
    created: list[tuple] = []
    for offset in range(remaining):
        index = len(existing) + offset + 1
        order_no = truncate_utf8_bytes(
            re.sub(r"[^A-Za-z0-9]", "", f"DOM{int(datetime.now(KST).timestamp() * 1000)}{index:02d}").upper(),
            30,
        )
        params = _api_params(data, order_no, test_yn="N" if live else "Y")
        if not live:
            result = mock_insert_order()
        else:
            try:
                result = insert_order(params)
            except EpostError as exc:
                if created or existing:
                    break
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        shipment_id = _store_shipment(data, order_no, result, live=live, user_name=user["nickname"], created_at=now)
        created.append((shipment_id, result.get("regiNo") or "", order_no, result.get("price") or ""))
        add_log(
            action_type="국내출고접수",
            target_type="domestic_shipment",
            target_id=str(shipment_id),
            target_name=result.get("regiNo") or order_no,
            user_nickname=user["nickname"],
        )

    rows = list(existing) + created
    if not rows:
        raise HTTPException(status_code=502, detail="접수에 실패했습니다.")
    return _created_payload(rows, requested=requested, live=live, data=data, duplicate=False)


def _label_pdf(item: dict[str, Any]) -> bytes:
    return build_domestic_label_pdf(item)


@router.get("/{shipment_id}/label")
def domestic_label(shipment_id: int, token: str, format: str = "json"):
    _get_user(token)
    ensure_domestic_tables()
    item = _load_shipment(shipment_id)
    if format == "pdf":
        filename = f"domestic-{item.get('tracking_no') or item['id']}.pdf"
        return Response(
            content=_label_pdf(item),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )
    return {"ok": True, "label": item}


@router.post("/{shipment_id}/cancel")
def cancel_domestic(shipment_id: int, token: str, confirm: bool = False):
    user = _get_user(token)
    ensure_domestic_tables()
    if not confirm:
        raise HTTPException(status_code=400, detail="확인 후에만 취소할 수 있습니다.")
    item = _load_shipment(shipment_id)
    if item["status"] == "canceled":
        return {"success": True, "already": True, "message": "이미 취소된 접수입니다."}
    if not item["is_test"]:
        try:
            cancel_order(
                req_no=item.get("req_no") or "",
                res_no=item.get("res_no") or "",
                regi_no=item.get("tracking_no") or "",
                req_ymd=resolve_cancel_req_ymd(item.get("res_date"), item.get("created_at")),
                req_type=_REQ_TYPE,
                pay_type=_PAY_TYPE,
            )
        except EpostError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    now = datetime.now(KST).isoformat(timespec="seconds")
    with get_connection() as con:
        con.execute(
            "UPDATE domestic_shipments SET status='canceled', canceled_at=?, canceled_by=? WHERE id=?",
            (now, user["nickname"], shipment_id),
        )
        con.commit()
    return {"success": True, "message": "국내 출고 접수를 취소했습니다."}


@router.delete("/{shipment_id}")
def delete_domestic(shipment_id: int, token: str):
    user = _get_user(token)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자만 접수 내역을 삭제할 수 있습니다.")
    ensure_domestic_tables()
    item = _load_shipment(shipment_id)
    if item["status"] != "canceled" and not item["is_test"]:
        cancel_domestic(shipment_id, token, confirm=True)
    with get_connection() as con:
        con.execute("DELETE FROM domestic_shipments WHERE id=?", (shipment_id,))
        con.commit()
    add_log(
        action_type="국내출고삭제",
        target_type="domestic_shipment",
        target_id=str(shipment_id),
        target_name=str(item.get("tracking_no") or item.get("order_no") or ""),
        user_nickname=user["nickname"],
    )
    return {"success": True, "message": "목록에서 삭제했습니다."}
