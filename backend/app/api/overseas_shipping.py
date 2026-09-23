"""창고 직원용 EMS/K-Packet 해외배송 접수. 결제 없이 우체국 즉시 접수."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from backend.app.api.kpost_pickup import _get_user
from backend.app.api.logs import add_log
from backend.app.services.ems.client import (
    EmsApiError,
    apply_ems,
    approval_no_for,
    cancel_ems,
    get_available_nations,
    get_shipping_quote,
    has_ems_credentials,
    mock_apply_ems,
    mock_quote_fee,
)
from backend.app.services.ems.fields import (
    SHIPPING_METHODS,
    apply_sender_override,
    build_apply_params,
    contents_label,
    env_clean,
    fallback_nations,
    format_sender_tel,
    normalize_contents_type,
    resolve_method,
    resolve_sender,
    sort_nations,
    validate_apply_input,
    validate_countrycd,
)
from backend.app.services.ems.dimension_limits import snap_doc_weight_g, validate_weight
from backend.app.services.ems.duty_deposit import calculate_duty_deposit
from backend.app.services.ems.hs_catalog import search_hs_catalog
from backend.app.services.ems.item_categories import ITEM_CATEGORIES
from backend.app.services.ems.label import build_shipment_label, render_label_html
from backend.app.services.ems.order_excel import parse_order_workbook
from logic.db import get_connection

router = APIRouter(prefix="/overseas-shipping", tags=["overseas-shipping"])
KST = ZoneInfo("Asia/Seoul")
_NATION_CACHE: dict[str, tuple[float, list[dict[str, str]]]] = {}
_NATION_CACHE_TTL = 600.0


def clear_nation_cache() -> None:
    _NATION_CACHE.clear()


def _nations_payload(premiumcd: str) -> dict[str, Any]:
    code = (premiumcd or "31").strip()
    now = time.time()
    if not has_ems_credentials():
        items = fallback_nations(code)
        return {"items": items, "fallback": True, "source": "fallback", "count": len(items)}
    cached = _NATION_CACHE.get(code)
    if cached and now - cached[0] < _NATION_CACHE_TTL:
        return {"items": cached[1], "fallback": False, "source": "epost-cache", "count": len(cached[1])}
    try:
        items = sort_nations(get_available_nations(code))
        if items:
            _NATION_CACHE[code] = (now, items)
            return {"items": items, "fallback": False, "source": "epost", "count": len(items)}
    except Exception:
        if cached:
            return {"items": cached[1], "fallback": False, "source": "epost-cache", "count": len(cached[1])}
    items = fallback_nations(code)
    return {"items": items, "fallback": True, "source": "fallback", "count": len(items)}


class InvoiceItem(BaseModel):
    product_name: str = ""
    name_en: str
    quantity: int = 1
    unit_price_usd: float
    hs_code: str = ""
    origin_country: str = "KR"


class OverseasSubmitRequest(BaseModel):
    shipping_method: str = "EMS"
    contents_type: str = "parcel"
    countrycd: str
    sender_name: str = ""
    sender_zipcode: str = ""
    sender_addr1: str = ""
    sender_addr2: str = ""
    sender_addr3: str = ""
    sender_tel: str = ""
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
    save_address: bool = False
    save_address_label: str = ""
    save_address_default: bool = False
    save_sender: bool = False
    save_sender_label: str = ""
    save_sender_default: bool = False


class SavedOverseasAddressRequest(BaseModel):
    label: str
    recipient_name: str
    recipient_phone: str = ""
    recipient_email: str = ""
    countrycd: str
    zipcode: str = ""
    addr1: str = ""
    addr2: str = ""
    addr3: str
    is_default: bool = False


class SavedOverseasSenderRequest(BaseModel):
    label: str
    name: str
    phone: str = ""
    zipcode: str = ""
    addr1: str = ""
    addr2: str = ""
    addr3: str = ""
    is_default: bool = False


class SavedOverseasHsRequest(BaseModel):
    label: str = ""
    name_ko: str = ""
    name_en: str
    hs_code: str
    origin_country: str = "KR"
    group_name: str = "저장품목"


def ensure_overseas_tables() -> None:
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS overseas_shipping_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT NOT NULL,
                shipping_method TEXT NOT NULL,
                contents_type TEXT NOT NULL DEFAULT 'parcel',
                premiumcd TEXT,
                countrycd TEXT NOT NULL,
                sender_name TEXT,
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
        try:
            con.execute("SELECT sender_name FROM overseas_shipping_requests LIMIT 1")
        except Exception:
            con.execute("ALTER TABLE overseas_shipping_requests ADD COLUMN sender_name TEXT")
        try:
            con.execute("SELECT contents_type FROM overseas_shipping_requests LIMIT 1")
        except Exception:
            con.execute(
                "ALTER TABLE overseas_shipping_requests ADD COLUMN contents_type TEXT DEFAULT 'parcel'"
            )
        try:
            con.execute("SELECT ddp_krw FROM overseas_shipping_requests LIMIT 1")
        except Exception:
            con.execute("ALTER TABLE overseas_shipping_requests ADD COLUMN ddp_krw INTEGER")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS overseas_saved_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                recipient_name TEXT NOT NULL,
                recipient_phone TEXT,
                recipient_email TEXT,
                countrycd TEXT NOT NULL,
                zipcode TEXT,
                addr1 TEXT,
                addr2 TEXT,
                addr3 TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, label)
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_overseas_saved_addresses_user "
            "ON overseas_saved_addresses(user_id, is_default DESC, created_at DESC)"
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS overseas_saved_senders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                phone TEXT,
                zipcode TEXT,
                addr1 TEXT,
                addr2 TEXT,
                addr3 TEXT,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_by TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS overseas_saved_hs_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL UNIQUE,
                name_ko TEXT,
                name_en TEXT NOT NULL,
                hs_code TEXT NOT NULL,
                origin_country TEXT NOT NULL DEFAULT 'KR',
                group_name TEXT NOT NULL DEFAULT '저장품목',
                created_by TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_overseas_saved_hs_code "
            "ON overseas_saved_hs_codes(hs_code, name_en)"
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
        "contents_type": req.contents_type,
        "countrycd": req.countrycd,
        "sender_name": req.sender_name,
        "sender_zipcode": req.sender_zipcode,
        "sender_addr1": req.sender_addr1,
        "sender_addr2": req.sender_addr2,
        "sender_addr3": req.sender_addr3,
        "sender_tel": req.sender_tel,
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


def _normalize_saved_address(req: SavedOverseasAddressRequest) -> dict[str, Any]:
    label = (req.label or "").strip()
    if len(label) < 1:
        raise HTTPException(status_code=400, detail="별칭을 입력해주세요.")
    if len(label) > 50:
        raise HTTPException(status_code=400, detail="별칭은 50자 이하여야 합니다.")
    name = (req.recipient_name or "").strip()
    if len(name) < 1:
        raise HTTPException(status_code=400, detail="수취인 이름을 입력해주세요.")
    countrycd = re.sub(r"[^A-Za-z]", "", req.countrycd or "").upper()
    if len(countrycd) != 2:
        raise HTTPException(status_code=400, detail="국가코드 2자리(예: JP, US)를 입력해주세요.")
    addr3 = (req.addr3 or "").strip()
    if len(addr3) < 2:
        raise HTTPException(status_code=400, detail="수취인 상세주소를 입력해주세요.")
    addr1 = (req.addr1 or "").strip()
    addr2 = (req.addr2 or "").strip()
    if not addr1 and not addr2:
        raise HTTPException(status_code=400, detail="수취인 주/도 또는 시/군 주소를 입력해주세요.")
    return {
        "label": label,
        "recipient_name": name,
        "recipient_phone": re.sub(r"[^\d+]", "", req.recipient_phone or ""),
        "recipient_email": (req.recipient_email or "").strip(),
        "countrycd": countrycd,
        "zipcode": (req.zipcode or "").strip(),
        "addr1": addr1,
        "addr2": addr2,
        "addr3": addr3,
        "is_default": 1 if req.is_default else 0,
    }


def _saved_address_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "label": row[1],
        "recipient_name": row[2],
        "recipient_phone": row[3] or "",
        "recipient_email": row[4] or "",
        "countrycd": row[5],
        "zipcode": row[6] or "",
        "addr1": row[7] or "",
        "addr2": row[8] or "",
        "addr3": row[9] or "",
        "is_default": bool(row[10]),
        "created_at": row[11],
    }


def _insert_saved_address(user_id: int, req: SavedOverseasAddressRequest) -> dict[str, Any]:
    data = _normalize_saved_address(req)
    created_at = datetime.now(KST).isoformat(timespec="seconds")
    with get_connection() as con:
        existing = con.execute(
            "SELECT id FROM overseas_saved_addresses WHERE user_id=? AND label=?",
            (user_id, data["label"]),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail=f"'{data['label']}' 별칭은 이미 사용 중입니다.")
        if data["is_default"]:
            con.execute(
                "UPDATE overseas_saved_addresses SET is_default=0 WHERE user_id=?",
                (user_id,),
            )
        cur = con.execute(
            """
            INSERT INTO overseas_saved_addresses (
                user_id, label, recipient_name, recipient_phone, recipient_email,
                countrycd, zipcode, addr1, addr2, addr3, is_default, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user_id,
                data["label"],
                data["recipient_name"],
                data["recipient_phone"],
                data["recipient_email"],
                data["countrycd"],
                data["zipcode"],
                data["addr1"],
                data["addr2"],
                data["addr3"],
                data["is_default"],
                created_at,
            ),
        )
        address_id = cur.lastrowid
        con.commit()
    return {"success": True, "id": address_id, **data, "is_default": bool(data["is_default"])}


def _normalize_saved_sender(req: SavedOverseasSenderRequest) -> dict[str, Any]:
    label = (req.label or "").strip()
    if len(label) < 1:
        raise HTTPException(status_code=400, detail="발송인 별칭을 입력해주세요.")
    if len(label) > 50:
        raise HTTPException(status_code=400, detail="발송인 별칭은 50자 이하여야 합니다.")
    name = (req.name or "").strip()
    if len(name) < 1:
        raise HTTPException(status_code=400, detail="발송인 이름을 입력해주세요.")
    if "@" in name:
        raise HTTPException(status_code=400, detail="발송인 이름은 이메일이 아닌 실제 이름이어야 합니다.")
    addr1 = (req.addr1 or "").strip()
    addr2 = (req.addr2 or "").strip()
    addr3 = (req.addr3 or "").strip()
    if not addr1 and not addr3:
        raise HTTPException(status_code=400, detail="발송인 주소를 입력해주세요.")
    return {
        "label": label,
        "name": name,
        "phone": re.sub(r"[^\d+]", "", req.phone or ""),
        "zipcode": re.sub(r"\D", "", req.zipcode or "")[:6],
        "addr1": addr1,
        "addr2": addr2,
        "addr3": addr3,
        "is_default": 1 if req.is_default else 0,
    }


def _saved_sender_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "label": row[1],
        "name": row[2],
        "phone": row[3] or "",
        "zipcode": row[4] or "",
        "addr1": row[5] or "",
        "addr2": row[6] or "",
        "addr3": row[7] or "",
        "is_default": bool(row[8]),
        "created_at": row[9],
    }


def _insert_saved_sender(nickname: str, req: SavedOverseasSenderRequest) -> dict[str, Any]:
    data = _normalize_saved_sender(req)
    created_at = datetime.now(KST).isoformat(timespec="seconds")
    with get_connection() as con:
        existing = con.execute(
            "SELECT id FROM overseas_saved_senders WHERE label=?",
            (data["label"],),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail=f"'{data['label']}' 별칭은 이미 사용 중입니다.")
        if data["is_default"]:
            con.execute("UPDATE overseas_saved_senders SET is_default=0")
        cur = con.execute(
            """
            INSERT INTO overseas_saved_senders (
                label, name, phone, zipcode, addr1, addr2, addr3, is_default, created_by, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                data["label"],
                data["name"],
                data["phone"],
                data["zipcode"],
                data["addr1"],
                data["addr2"],
                data["addr3"],
                data["is_default"],
                nickname,
                created_at,
            ),
        )
        sender_id = cur.lastrowid
        con.commit()
    return {"success": True, "id": sender_id, **data, "is_default": bool(data["is_default"])}


def _normalize_saved_hs(req: SavedOverseasHsRequest) -> dict[str, Any]:
    hs = re.sub(r"\D", "", req.hs_code or "")
    if len(hs) != 6:
        raise HTTPException(status_code=400, detail="HS코드는 6자리 숫자여야 합니다.")
    name_en = (req.name_en or "").strip()
    if len(name_en) < 1:
        raise HTTPException(status_code=400, detail="영문 품목명을 입력해주세요.")
    if len(name_en) > 80:
        raise HTTPException(status_code=400, detail="영문 품목명은 80자 이하여야 합니다.")
    name_ko = (req.name_ko or "").strip()
    label = (req.label or "").strip() or name_ko or name_en
    if len(label) < 1:
        raise HTTPException(status_code=400, detail="HS 별칭을 입력해주세요.")
    if len(label) > 50:
        label = label[:50]
    origin = re.sub(r"[^A-Za-z]", "", req.origin_country or "KR").upper()[:2] or "KR"
    group_name = (req.group_name or "저장품목").strip()[:30] or "저장품목"
    return {
        "label": label,
        "name_ko": name_ko or label,
        "name_en": name_en,
        "hs_code": hs,
        "origin_country": origin,
        "group_name": group_name,
    }


def _saved_hs_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "label": row[1],
        "name_ko": row[2] or row[1],
        "name_en": row[3],
        "hs_code": row[4],
        "origin_country": row[5] or "KR",
        "group_name": row[6] or "저장품목",
        "created_at": row[7],
    }


def _saved_hs_as_category(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"saved-{row['id']}",
        "name_ko": row["name_ko"],
        "name_en": row["name_en"],
        "hs_code": row["hs_code"],
        "group": row["group_name"],
        "origin_country": row["origin_country"],
        "saved": True,
        "saved_id": row["id"],
        "label": row["label"],
    }


def _insert_saved_hs(nickname: str, req: SavedOverseasHsRequest, *, upsert: bool = False) -> dict[str, Any]:
    data = _normalize_saved_hs(req)
    created_at = datetime.now(KST).isoformat(timespec="seconds")
    with get_connection() as con:
        same = con.execute(
            "SELECT id FROM overseas_saved_hs_codes WHERE hs_code=? AND LOWER(name_en)=LOWER(?)",
            (data["hs_code"], data["name_en"]),
        ).fetchone()
        if same:
            if not upsert:
                raise HTTPException(status_code=400, detail="같은 영문 품목명과 HS코드가 이미 저장되어 있습니다.")
            return {"success": True, "id": same[0], **data, "updated": True}
        label_dup = con.execute(
            "SELECT id FROM overseas_saved_hs_codes WHERE label=?",
            (data["label"],),
        ).fetchone()
        if label_dup:
            if not upsert:
                raise HTTPException(status_code=400, detail=f"'{data['label']}' 별칭은 이미 사용 중입니다.")
            data["label"] = f"{data['label']}-{data['hs_code']}"[:50]
        cur = con.execute(
            """
            INSERT INTO overseas_saved_hs_codes (
                label, name_ko, name_en, hs_code, origin_country, group_name, created_by, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                data["label"],
                data["name_ko"],
                data["name_en"],
                data["hs_code"],
                data["origin_country"],
                data["group_name"],
                nickname,
                created_at,
            ),
        )
        hs_id = cur.lastrowid
        con.commit()
    return {"success": True, "id": hs_id, **data, "updated": False}


def _list_saved_hs_rows() -> list[dict[str, Any]]:
    ensure_overseas_tables()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT id, label, name_ko, name_en, hs_code, origin_country, group_name, created_at
            FROM overseas_saved_hs_codes
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [_saved_hs_dict(row) for row in rows]


def _match_saved_hs(query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    q = (query or "").strip().lower().replace(" ", "")
    items = []
    for row in rows:
        hay = f"{row['label']}{row['name_ko']}{row['name_en']}{row['hs_code']}".lower().replace(" ", "")
        if not q or q in hay or str(row["hs_code"]).startswith(q):
            items.append(_saved_hs_as_category(row))
    return items


def _autosave_invoice_hs(nickname: str, items: list[dict[str, Any]]) -> None:
    seen: set[tuple[str, str]] = set()
    for item in items:
        hs = re.sub(r"\D", "", str(item.get("hs_code") or ""))
        name_en = str(item.get("name_en") or "").strip()
        if len(hs) != 6 or not name_en:
            continue
        key = (hs, name_en.lower())
        if key in seen:
            continue
        seen.add(key)
        try:
            _insert_saved_hs(
                nickname,
                SavedOverseasHsRequest(
                    label=name_en,
                    name_ko=name_en,
                    name_en=name_en,
                    hs_code=hs,
                    origin_country=str(item.get("origin_country") or "KR"),
                    group_name="저장품목",
                ),
                upsert=True,
            )
        except HTTPException:
            pass


def _quote_shipping(
    premiumcd: str,
    em_ee: str,
    countrycd: str,
    totweight: int,
    *,
    boxlength: int = 0,
    boxwidth: int = 0,
    boxheight: int = 0,
    live: bool,
) -> dict[str, Any]:
    is_doc = em_ee == "ee"
    quote_weight = snap_doc_weight_g(totweight) if is_doc else totweight
    try:
        if live:
            quoted = get_shipping_quote(
                premiumcd,
                em_ee,
                countrycd,
                totweight,
                boxlength=None if is_doc else (boxlength or None),
                boxwidth=None if is_doc else (boxwidth or None),
                boxheight=None if is_doc else (boxheight or None),
            )
            fee = int(quoted["totalFee"])
        else:
            weight_err = validate_weight(premiumcd, em_ee, totweight)
            if weight_err:
                raise ValueError(weight_err)
            fee = mock_quote_fee(quote_weight, premiumcd, em_ee)
        return {
            "ok": True,
            "totalFee": fee,
            "totweight": quote_weight,
            "em_ee": em_ee,
            "error": None,
        }
    except (EmsApiError, ValueError) as exc:
        return {
            "ok": False,
            "totalFee": None,
            "totweight": quote_weight,
            "em_ee": em_ee,
            "error": str(exc),
        }


def _quote_fee(validated: dict[str, Any], *, live: bool) -> int | None:
    method = validated["method"]
    quoted = _quote_shipping(
        method["premiumcd"],
        method["em_ee"],
        validated["countrycd"],
        validated["totweight"],
        boxlength=validated["boxlength"],
        boxwidth=validated["boxwidth"],
        boxheight=validated["boxheight"],
        live=live,
    )
    return int(quoted["totalFee"]) if quoted.get("ok") and quoted.get("totalFee") is not None else None


def _preview_payload(validated: dict[str, Any], *, is_test: bool, fee: int | None) -> dict[str, Any]:
    sender = validated["sender"]
    method = validated["method"]
    return {
        "shipping_method": method["code"],
        "shipping_method_name": method["name"],
        "contents_type": validated.get("contents_type") or "parcel",
        "contents_label": validated.get("contents_label") or contents_label(
            validated.get("contents_type") or "parcel"
        ),
        "em_ee": method["em_ee"],
        "countrycd": validated["countrycd"],
        "sender_name": sender["name"],
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
        "duty": calculate_duty_deposit(
            country_code=validated["countrycd"],
            customs_value_usd=sum(
                float(i.get("unit_price_usd") or 0) * int(i.get("quantity") or 1)
                for i in (validated.get("items") or [])
            ),
            duty_prepaid_requested=True,
            shipping_method=method["code"],
        ),
        "is_test": is_test,
        "notes": validated.get("notes") or "",
    }


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    keys = [
        "id",
        "order_no",
        "shipping_method",
        "contents_type",
        "premiumcd",
        "countrycd",
        "sender_name",
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
        "ddp_krw",
    ]
    data = dict(zip(keys, row))
    data["is_test"] = bool(data["is_test"])
    data["contents_type"] = data.get("contents_type") or "parcel"
    data["contents_label"] = contents_label(str(data["contents_type"]))
    try:
        data["items"] = json.loads(data.pop("item_list") or "[]")
    except json.JSONDecodeError:
        data["items"] = []
    _attach_spend(data)
    return data


def _customs_value_usd(items: list[dict[str, Any]]) -> float:
    total = 0.0
    for item in items or []:
        try:
            price = float(item.get("unit_price_usd") or 0)
            qty = int(item.get("quantity") or 1)
        except (TypeError, ValueError):
            continue
        total += price * qty
    return total


def _ddp_krw_for(countrycd: str, shipping_method: str, items: list[dict[str, Any]]) -> int:
    duty = calculate_duty_deposit(
        country_code=countrycd,
        customs_value_usd=_customs_value_usd(items),
        duty_prepaid_requested=True,
        shipping_method=shipping_method,
    )
    if not duty.get("dutyPrepaid"):
        return 0
    return int(duty.get("depositKrw") or 0)


def _attach_spend(data: dict[str, Any]) -> None:
    stored = data.get("ddp_krw")
    if stored is None or stored == "":
        ddp = _ddp_krw_for(
            str(data.get("countrycd") or ""),
            str(data.get("shipping_method") or ""),
            list(data.get("items") or []),
        )
    else:
        ddp = int(stored or 0)
    fee_raw = str(data.get("ems_fee") or "").strip()
    try:
        fee = int(float(fee_raw)) if fee_raw else 0
    except ValueError:
        fee = 0
    data["ddp_krw"] = ddp
    data["spent_total"] = fee + ddp


@router.get("/meta")
def overseas_meta(token: str):
    _get_user(token)
    ensure_overseas_tables()
    sender = resolve_sender()
    with get_connection() as con:
        default_sender = con.execute(
            """
            SELECT name, phone, zipcode, addr1, addr2, addr3
            FROM overseas_saved_senders
            WHERE is_default=1
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
    if default_sender:
        sender = apply_sender_override(
            sender,
            {
                "name": default_sender[0],
                "phone": default_sender[1] or "",
                "zipcode": default_sender[2] or "",
                "addr1": default_sender[3] or "",
                "addr2": default_sender[4] or "",
                "addr3": default_sender[5] or "",
            },
        )
    return {
        "live_ready": has_ems_credentials(),
        "methods": SHIPPING_METHODS,
        "sender": {
            "name": sender["name"],
            "addr": f"{sender['addr1']}, {sender['addr2']}, {sender['addr3']}",
            "zip": sender["zipcode"],
            "addr1": sender["addr1"],
            "addr2": sender["addr2"],
            "addr3": sender["addr3"],
            "tel": format_sender_tel(sender),
        },
        "item_categories": ITEM_CATEGORIES,
        "saved_hs": [_saved_hs_as_category(row) for row in _list_saved_hs_rows()],
    }


@router.get("/nations")
def overseas_nations(token: str, premiumcd: str = "31"):
    _get_user(token)
    code = (premiumcd or "31").strip()
    if code not in {"31", "32", "14"}:
        raise HTTPException(status_code=400, detail="잘못된 배송방법 코드입니다.")
    return _nations_payload(code)


@router.get("/quote")
def overseas_quote(
    token: str,
    shipping_method: str = "EMS",
    contents_type: str = "parcel",
    countrycd: str = "JP",
    totweight: int = 0,
    boxlength: int = 0,
    boxwidth: int = 0,
    boxheight: int = 0,
    customs_value_usd: float = 0,
):
    """우체국 예상요금 + 미국/영국 DDP. 결제가 아니라 후납 참고 금액."""
    _get_user(token)
    kind = normalize_contents_type(contents_type)
    try:
        parcel_method = resolve_method(shipping_method, "parcel")
        country = validate_countrycd(countrycd)
        selected_method = resolve_method(shipping_method, kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if totweight < 1:
        raise HTTPException(status_code=400, detail="중량(g)을 입력해주세요.")
    live = has_ems_credentials()
    duty = calculate_duty_deposit(
        country_code=country,
        customs_value_usd=customs_value_usd,
        duty_prepaid_requested=True,
        shipping_method=selected_method["code"],
    )
    parcel = _quote_shipping(
        parcel_method["premiumcd"],
        parcel_method["em_ee"],
        country,
        totweight,
        boxlength=boxlength,
        boxwidth=boxwidth,
        boxheight=boxheight,
        live=live,
    )
    document = None
    if parcel_method["premiumcd"] != "14":
        document = _quote_shipping(
            selected_method["premiumcd"] if kind == "document" else parcel_method["premiumcd"],
            "ee",
            country,
            totweight,
            live=live,
        )
    selected = document if kind == "document" and document is not None else parcel
    shipping = int(selected.get("totalFee") or 0) if selected.get("ok") else 0
    ddp = int(duty.get("depositKrw") or 0) if duty.get("dutyPrepaid") else 0
    return {
        "ok": bool(selected.get("ok")),
        "totalFee": selected.get("totalFee") if selected.get("ok") else None,
        "live": live,
        "source": "epost" if live else "mock",
        "shipping_method": selected_method["code"],
        "shipping_method_name": selected_method["name"],
        "contents_type": kind,
        "contents_label": contents_label(kind),
        "em_ee": selected_method["em_ee"],
        "countrycd": country,
        "totweight": selected.get("totweight") or totweight,
        "error": selected.get("error"),
        "duty": duty,
        "payableTotal": (shipping + ddp) if selected.get("ok") else None,
        "parcel": parcel,
        "document": document,
    }


@router.get("/item-categories")
def overseas_item_categories(token: str, q: str = ""):
    _get_user(token)
    saved = _match_saved_hs(q, _list_saved_hs_rows())
    catalog = search_hs_catalog(q, limit=30)
    seen = {(c.get("hs_code") or "", (c.get("name_en") or "").lower()) for c in saved}
    merged = list(saved)
    for cat in catalog:
        key = (cat.get("hs_code") or "", (cat.get("name_en") or "").lower())
        if key in seen:
            continue
        merged.append(cat)
        seen.add(key)
    return {"items": merged[:40], "source": "saved+catalog+hs6"}


@router.get("/saved-addresses")
def list_saved_overseas_addresses(token: str):
    user = _get_user(token)
    ensure_overseas_tables()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT id, label, recipient_name, recipient_phone, recipient_email,
                   countrycd, zipcode, addr1, addr2, addr3, is_default, created_at
            FROM overseas_saved_addresses
            WHERE user_id=?
            ORDER BY is_default DESC, created_at DESC
            """,
            (user["user_id"],),
        ).fetchall()
    return {"items": [_saved_address_dict(row) for row in rows]}


@router.post("/saved-addresses")
def save_overseas_address(req: SavedOverseasAddressRequest, token: str):
    user = _get_user(token)
    ensure_overseas_tables()
    return _insert_saved_address(user["user_id"], req)


@router.put("/saved-addresses/{address_id}")
def update_saved_overseas_address(address_id: int, req: SavedOverseasAddressRequest, token: str):
    user = _get_user(token)
    ensure_overseas_tables()
    data = _normalize_saved_address(req)
    with get_connection() as con:
        row = con.execute(
            "SELECT id, user_id FROM overseas_saved_addresses WHERE id=?",
            (address_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="저장된 주소를 찾을 수 없습니다.")
        if row[1] != user["user_id"]:
            raise HTTPException(status_code=403, detail="다른 사용자의 주소는 수정할 수 없습니다.")
        dup = con.execute(
            "SELECT id FROM overseas_saved_addresses WHERE user_id=? AND label=? AND id!=?",
            (user["user_id"], data["label"], address_id),
        ).fetchone()
        if dup:
            raise HTTPException(status_code=400, detail=f"'{data['label']}' 별칭은 이미 사용 중입니다.")
        if data["is_default"]:
            con.execute(
                "UPDATE overseas_saved_addresses SET is_default=0 WHERE user_id=?",
                (user["user_id"],),
            )
        con.execute(
            """
            UPDATE overseas_saved_addresses
            SET label=?, recipient_name=?, recipient_phone=?, recipient_email=?,
                countrycd=?, zipcode=?, addr1=?, addr2=?, addr3=?, is_default=?
            WHERE id=?
            """,
            (
                data["label"],
                data["recipient_name"],
                data["recipient_phone"],
                data["recipient_email"],
                data["countrycd"],
                data["zipcode"],
                data["addr1"],
                data["addr2"],
                data["addr3"],
                data["is_default"],
                address_id,
            ),
        )
        con.commit()
    return {"success": True, "id": address_id, "label": data["label"]}


@router.delete("/saved-addresses/{address_id}")
def delete_saved_overseas_address(address_id: int, token: str):
    user = _get_user(token)
    ensure_overseas_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT id, user_id FROM overseas_saved_addresses WHERE id=?",
            (address_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="저장된 주소를 찾을 수 없습니다.")
        if row[1] != user["user_id"]:
            raise HTTPException(status_code=403, detail="다른 사용자의 주소는 삭제할 수 없습니다.")
        con.execute("DELETE FROM overseas_saved_addresses WHERE id=?", (address_id,))
        con.commit()
    return {"success": True, "id": address_id}


@router.get("/saved-senders")
def list_saved_overseas_senders(token: str):
    _get_user(token)
    ensure_overseas_tables()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT id, label, name, phone, zipcode, addr1, addr2, addr3, is_default, created_at
            FROM overseas_saved_senders
            ORDER BY is_default DESC, created_at DESC
            """
        ).fetchall()
    return {"items": [_saved_sender_dict(row) for row in rows]}


@router.post("/saved-senders")
def save_overseas_sender(req: SavedOverseasSenderRequest, token: str):
    user = _get_user(token)
    ensure_overseas_tables()
    return _insert_saved_sender(user["nickname"], req)


@router.put("/saved-senders/{sender_id}")
def update_saved_overseas_sender(sender_id: int, req: SavedOverseasSenderRequest, token: str):
    _get_user(token)
    ensure_overseas_tables()
    data = _normalize_saved_sender(req)
    with get_connection() as con:
        row = con.execute("SELECT id FROM overseas_saved_senders WHERE id=?", (sender_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="저장된 발송인을 찾을 수 없습니다.")
        dup = con.execute(
            "SELECT id FROM overseas_saved_senders WHERE label=? AND id!=?",
            (data["label"], sender_id),
        ).fetchone()
        if dup:
            raise HTTPException(status_code=400, detail=f"'{data['label']}' 별칭은 이미 사용 중입니다.")
        if data["is_default"]:
            con.execute("UPDATE overseas_saved_senders SET is_default=0")
        con.execute(
            """
            UPDATE overseas_saved_senders
            SET label=?, name=?, phone=?, zipcode=?, addr1=?, addr2=?, addr3=?, is_default=?
            WHERE id=?
            """,
            (
                data["label"],
                data["name"],
                data["phone"],
                data["zipcode"],
                data["addr1"],
                data["addr2"],
                data["addr3"],
                data["is_default"],
                sender_id,
            ),
        )
        con.commit()
    return {"success": True, "id": sender_id, "label": data["label"]}


@router.delete("/saved-senders/{sender_id}")
def delete_saved_overseas_sender(sender_id: int, token: str):
    _get_user(token)
    ensure_overseas_tables()
    with get_connection() as con:
        row = con.execute("SELECT id FROM overseas_saved_senders WHERE id=?", (sender_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="저장된 발송인을 찾을 수 없습니다.")
        con.execute("DELETE FROM overseas_saved_senders WHERE id=?", (sender_id,))
        con.commit()
    return {"success": True, "id": sender_id}


@router.get("/saved-hs")
def list_saved_overseas_hs(token: str, q: str = ""):
    _get_user(token)
    rows = _list_saved_hs_rows()
    if (q or "").strip():
        matched_ids = {item["saved_id"] for item in _match_saved_hs(q, rows)}
        rows = [row for row in rows if row["id"] in matched_ids]
    return {"items": rows}


@router.post("/saved-hs")
def save_overseas_hs(req: SavedOverseasHsRequest, token: str):
    user = _get_user(token)
    ensure_overseas_tables()
    return _insert_saved_hs(user["nickname"], req)


@router.put("/saved-hs/{hs_id}")
def update_saved_overseas_hs(hs_id: int, req: SavedOverseasHsRequest, token: str):
    _get_user(token)
    ensure_overseas_tables()
    data = _normalize_saved_hs(req)
    with get_connection() as con:
        row = con.execute("SELECT id FROM overseas_saved_hs_codes WHERE id=?", (hs_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="저장된 HS코드를 찾을 수 없습니다.")
        dup_label = con.execute(
            "SELECT id FROM overseas_saved_hs_codes WHERE label=? AND id!=?",
            (data["label"], hs_id),
        ).fetchone()
        if dup_label:
            raise HTTPException(status_code=400, detail=f"'{data['label']}' 별칭은 이미 사용 중입니다.")
        dup_hs = con.execute(
            """
            SELECT id FROM overseas_saved_hs_codes
            WHERE hs_code=? AND LOWER(name_en)=LOWER(?) AND id!=?
            """,
            (data["hs_code"], data["name_en"], hs_id),
        ).fetchone()
        if dup_hs:
            raise HTTPException(status_code=400, detail="같은 영문 품목명과 HS코드가 이미 저장되어 있습니다.")
        con.execute(
            """
            UPDATE overseas_saved_hs_codes
            SET label=?, name_ko=?, name_en=?, hs_code=?, origin_country=?, group_name=?
            WHERE id=?
            """,
            (
                data["label"],
                data["name_ko"],
                data["name_en"],
                data["hs_code"],
                data["origin_country"],
                data["group_name"],
                hs_id,
            ),
        )
        con.commit()
    return {"success": True, "id": hs_id, "label": data["label"]}


@router.delete("/saved-hs/{hs_id}")
def delete_saved_overseas_hs(hs_id: int, token: str):
    _get_user(token)
    ensure_overseas_tables()
    with get_connection() as con:
        row = con.execute("SELECT id FROM overseas_saved_hs_codes WHERE id=?", (hs_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="저장된 HS코드를 찾을 수 없습니다.")
        con.execute("DELETE FROM overseas_saved_hs_codes WHERE id=?", (hs_id,))
        con.commit()
    return {"success": True, "id": hs_id}


@router.post("/import-excel")
async def import_overseas_excel(token: str, file: UploadFile = File(...)):
    """주문 엑셀 1건(합포)을 접수 입력값으로 바꾼다. 없는 항목은 비워 둔다."""
    _get_user(token)
    raw = await file.read()
    try:
        groups = parse_order_workbook(raw, filename=file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"groups": groups}


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
            SELECT id, order_no, shipping_method, contents_type, premiumcd, countrycd, sender_name,
                   recipient_name, recipient_phone, recipient_email, recipient_zip,
                   recipient_addr1, recipient_addr2, recipient_addr3,
                   totweight, boxlength, boxwidth, boxheight, item_list,
                   tracking_no, req_no, receive_seq, ems_fee, post_office,
                   status, is_test, notes, created_by, created_at, canceled_at, canceled_by,
                   ddp_krw
            FROM overseas_shipping_requests
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 2000)),),
        ).fetchall()
    return {"items": [_row_to_dict(row) for row in rows]}


def _load_shipment(shipment_id: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
    ensure_overseas_tables()
    with get_connection() as con:
        row = con.execute(
            """
            SELECT id, order_no, shipping_method, contents_type, premiumcd, countrycd, sender_name,
                   recipient_name, recipient_phone, recipient_email, recipient_zip,
                   recipient_addr1, recipient_addr2, recipient_addr3,
                   totweight, boxlength, boxwidth, boxheight, item_list,
                   tracking_no, req_no, receive_seq, ems_fee, post_office,
                   status, is_test, notes, created_by, created_at, canceled_at, canceled_by,
                   ddp_krw, apply_snapshot
            FROM overseas_shipping_requests
            WHERE id = ?
            """,
            (shipment_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="접수 내역을 찾을 수 없습니다.")
    snapshot_raw = row[-1]
    data = _row_to_dict(row[:-1])
    snapshot: dict[str, Any] | None = None
    if snapshot_raw:
        try:
            parsed = json.loads(snapshot_raw)
            if isinstance(parsed, dict):
                snapshot = parsed
        except json.JSONDecodeError:
            snapshot = None
    snap = snapshot or {}
    data["sender_zipcode"] = str(snap.get("senderzipcode") or "")
    data["sender_addr1"] = str(snap.get("senderaddr1") or "")
    data["sender_addr2"] = str(snap.get("senderaddr2") or "")
    data["sender_addr3"] = str(snap.get("senderaddr3") or "")
    data["sender_tel"] = format_sender_tel(
        {
            "tel2": str(snap.get("sendertelno2") or ""),
            "tel3": str(snap.get("sendertelno3") or ""),
            "tel4": str(snap.get("sendertelno4") or ""),
        }
    )
    return data, snapshot


@router.get("/{shipment_id}")
def get_overseas(shipment_id: int, token: str):
    """접수 1건을 입력 당시 값 그대로 돌려준다."""
    _get_user(token)
    data, _snapshot = _load_shipment(shipment_id)
    return data


@router.get("/{shipment_id}/label")
def overseas_label(shipment_id: int, token: str, format: str = "json"):
    """접수 저장본으로 CN22 출력서류를 내려준다. 우체국 PDF API는 없다."""
    _get_user(token)
    data, snapshot = _load_shipment(shipment_id)
    label = build_shipment_label(data, snapshot=snapshot)
    if (format or "json").lower() == "html":
        return HTMLResponse(render_label_html(label))
    return {"ok": True, "label": label}


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
        apprno=approval_no_for(validated["method"]["premiumcd"]) or "0000000000",
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
    ddp_krw = _ddp_krw_for(
        validated["countrycd"],
        validated["method"]["code"],
        list(validated.get("items") or []),
    )
    created_at = datetime.now(KST).isoformat(timespec="seconds")
    with get_connection() as con:
        cur = con.execute(
            """
            INSERT INTO overseas_shipping_requests (
                order_no, shipping_method, contents_type, premiumcd, countrycd, sender_name,
                recipient_name, recipient_phone, recipient_email, recipient_zip,
                recipient_addr1, recipient_addr2, recipient_addr3,
                totweight, boxlength, boxwidth, boxheight, item_list,
                tracking_no, req_no, receive_seq, ems_fee, post_office,
                status, is_test, apply_snapshot, notes, created_by, created_at, ddp_krw
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                order_no,
                validated["method"]["code"],
                validated.get("contents_type") or "parcel",
                validated["method"]["premiumcd"],
                validated["countrycd"],
                validated["sender"]["name"],
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
                ddp_krw,
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
        details=f"{validated['sender']['name']} → {validated['receivename']} / {validated['countrycd']} / {validated['method']['code']} {validated.get('contents_label') or '화물'}",
    )
    if req.save_address:
        try:
            _insert_saved_address(
                user["user_id"],
                SavedOverseasAddressRequest(
                    label=(req.save_address_label or "").strip() or validated["receivename"],
                    recipient_name=validated["receivename"],
                    recipient_phone=validated["receivetelno"],
                    recipient_email=validated["receivemail"],
                    countrycd=validated["countrycd"],
                    zipcode=validated["receivezipcode"],
                    addr1=validated["receiveaddr1"],
                    addr2=validated["receiveaddr2"],
                    addr3=validated["receiveaddr3"],
                    is_default=req.save_address_default,
                ),
            )
        except HTTPException:
            pass
    if req.save_sender:
        try:
            sender = validated["sender"]
            _insert_saved_sender(
                user["nickname"],
                SavedOverseasSenderRequest(
                    label=(req.save_sender_label or "").strip() or sender["name"],
                    name=sender["name"],
                    phone=format_sender_tel(sender) or req.sender_tel,
                    zipcode=sender["zipcode"],
                    addr1=sender["addr1"],
                    addr2=sender["addr2"],
                    addr3=sender["addr3"],
                    is_default=req.save_sender_default,
                ),
            )
        except HTTPException:
            pass
    _autosave_invoice_hs(user["nickname"], validated["items"])
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
            SELECT id, status, is_test, req_no, tracking_no, premiumcd
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
                canceled = cancel_ems(req_no, tracking, approval_no_for(row[5] or ""))
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


@router.delete("/{shipment_id}")
def delete_overseas(shipment_id: int, token: str):
    """관리자만 접수 행을 목록에서 지운다. 실접수는 우체국 취소 후에 삭제한다."""
    user = _get_user(token)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자만 접수 내역을 삭제할 수 있습니다.")
    data, _snapshot = _load_shipment(shipment_id)
    if data["status"] != "canceled" and not data["is_test"]:
        cancel_overseas(shipment_id, token, confirm=True)
    with get_connection() as con:
        con.execute("DELETE FROM overseas_shipping_requests WHERE id=?", (shipment_id,))
        con.commit()
    add_log(
        action_type="해외배송삭제",
        target_type="overseas_shipping",
        target_id=str(shipment_id),
        target_name=str(data.get("tracking_no") or data.get("order_no") or ""),
        user_nickname=user["nickname"],
        details=f"{data.get('recipient_name') or ''} / {data.get('countrycd') or ''} 삭제",
    )
    return {"success": True, "message": "접수 내역을 삭제했습니다."}
