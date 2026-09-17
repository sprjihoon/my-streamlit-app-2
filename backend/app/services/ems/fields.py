"""EMS/K-Packet 접수 필드 정규화. Infront lib/ems 와 동일 계약."""

from __future__ import annotations

import os
import re
from typing import Any

from backend.app.services.ems.dimension_limits import (
    validate_shipping_dimensions,
    validate_weight,
)

SHIPPING_METHODS = [
    {
        "code": "EMS",
        "name": "EMS",
        "desc": "일반 국제우편 · 3-7일",
        "premiumcd": "31",
        "em_ee": "em",
    },
    {
        "code": "EMS_PREMIUM",
        "name": "EMS 프리미엄",
        "desc": "FedEx 특송 · 2-4일 · 최대 70kg",
        "premiumcd": "32",
        "em_ee": "em",
    },
    {
        "code": "KPACKET",
        "name": "K-Packet",
        "desc": "소형 경량 · 7-15일 · 2kg 이하",
        "premiumcd": "14",
        "em_ee": "rl",
    },
]
SHIPPING_METHOD_MAP = {m["code"]: m for m in SHIPPING_METHODS}

FALLBACK_NATIONS = [
    {"nationcd": "JP", "nationnm": "일본", "nationfn": "JAPAN"},
    {"nationcd": "US", "nationnm": "미국", "nationfn": "UNITED STATES"},
    {"nationcd": "CN", "nationnm": "중국", "nationfn": "CHINA"},
    {"nationcd": "HK", "nationnm": "홍콩", "nationfn": "HONG KONG"},
    {"nationcd": "TW", "nationnm": "대만", "nationfn": "TAIWAN"},
    {"nationcd": "SG", "nationnm": "싱가포르", "nationfn": "SINGAPORE"},
    {"nationcd": "TH", "nationnm": "태국", "nationfn": "THAILAND"},
    {"nationcd": "VN", "nationnm": "베트남", "nationfn": "VIETNAM"},
    {"nationcd": "MY", "nationnm": "말레이시아", "nationfn": "MALAYSIA"},
    {"nationcd": "PH", "nationnm": "필리핀", "nationfn": "PHILIPPINES"},
    {"nationcd": "AU", "nationnm": "호주", "nationfn": "AUSTRALIA"},
    {"nationcd": "GB", "nationnm": "영국", "nationfn": "UNITED KINGDOM"},
    {"nationcd": "DE", "nationnm": "독일", "nationfn": "GERMANY"},
    {"nationcd": "FR", "nationnm": "프랑스", "nationfn": "FRANCE"},
    {"nationcd": "CA", "nationnm": "캐나다", "nationfn": "CANADA"},
    {"nationcd": "NZ", "nationnm": "뉴질랜드", "nationfn": "NEW ZEALAND"},
    {"nationcd": "ID", "nationnm": "인도네시아", "nationfn": "INDONESIA"},
    {"nationcd": "IT", "nationnm": "이탈리아", "nationfn": "ITALY"},
    {"nationcd": "ES", "nationnm": "스페인", "nationfn": "SPAIN"},
    {"nationcd": "NL", "nationnm": "네덜란드", "nationfn": "NETHERLANDS"},
]

EMS_APPLY_KEYS = [
    "custno",
    "apprno",
    "premiumcd",
    "em_ee",
    "countrycd",
    "totweight",
    "boxlength",
    "boxwidth",
    "boxheight",
    "boyn",
    "boprc",
    "orderno",
    "sender",
    "senderzipcode",
    "senderaddr1",
    "senderaddr2",
    "senderaddr3",
    "sendertelno1",
    "sendertelno2",
    "sendertelno3",
    "sendertelno4",
    "receivename",
    "receivezipcode",
    "receiveaddr1",
    "receiveaddr2",
    "receiveaddr3",
    "receivetelno",
    "receivemail",
    "EM_gubun",
    "contents",
    "number",
    "weight",
    "value",
    "hs_code",
    "origin",
    "currunitcd",
    "snd_message",
]


def env_clean(key: str, fallback: str = "") -> str:
    return (os.getenv(key) or fallback).replace("\r", "").replace("\n", "").strip() or fallback


def resolve_sender(env: dict[str, str] | None = None) -> dict[str, str]:
    src = env or {}

    def g(name: str, default: str = "") -> str:
        return (src.get(name) or env_clean(name, default)).strip()

    return {
        "name": g("EMS_SENDER_NAME", "스프링풀필먼트"),
        "zipcode": re.sub(r"\D", "", g("EMS_SENDER_ZIPCODE", "41142"))[:6],
        "addr1": g("EMS_SENDER_ADDR1", "1 Dongchon-ro 2F Parcel Room"),
        "addr2": g("EMS_SENDER_ADDR2", "Dong-gu"),
        "addr3": g("EMS_SENDER_ADDR3", "Daegu"),
        "tel1": g("EMS_SENDER_TEL1", "82"),
        "tel2": g("EMS_SENDER_TEL2", "10"),
        "tel3": g("EMS_SENDER_TEL3", "2723"),
        "tel4": g("EMS_SENDER_TEL4", "9490"),
    }


def method_of(code: str) -> dict[str, str]:
    method = SHIPPING_METHOD_MAP.get((code or "").strip().upper())
    if not method:
        raise ValueError(f"지원하지 않는 배송방법: {code}")
    return method


def serialize_invoice_items(items: list[dict[str, Any]], totweight_g: int) -> dict[str, str]:
    if not items:
        raise ValueError("인보이스 물품을 1개 이상 입력해주세요.")
    cleaned: list[dict[str, Any]] = []
    for raw in items:
        name = str(raw.get("name_en") or "").strip()
        if not name:
            raise ValueError("인보이스 품목명(영문)을 입력해주세요.")
        qty = int(raw.get("quantity") or 0)
        if qty < 1:
            raise ValueError("인보이스 수량은 1개 이상이어야 합니다.")
        try:
            price = float(raw.get("unit_price_usd") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("인보이스 단가(USD)를 숫자로 입력해주세요.") from exc
        if price <= 0:
            raise ValueError("인보이스 단가(USD)는 0보다 커야 합니다.")
        hs = re.sub(r"\D", "", str(raw.get("hs_code") or ""))
        origin = (str(raw.get("origin_country") or "KR").strip().upper() or "KR")[:2]
        cleaned.append(
            {
                "name_en": name,
                "quantity": qty,
                "unit_price_usd": price,
                "hs_code": hs,
                "origin_country": origin,
            }
        )

    each = totweight_g // len(cleaned)
    weights = [
        each if i < len(cleaned) - 1 else totweight_g - each * (len(cleaned) - 1)
        for i in range(len(cleaned))
    ]
    weights = [max(1, w) for w in weights]
    return {
        "EM_gubun": ";".join(["Merchandise"] * len(cleaned)),
        "contents": ";".join(it["name_en"] for it in cleaned),
        "number": ";".join(str(it["quantity"]) for it in cleaned),
        "weight": ";".join(str(w) for w in weights),
        "value": ";".join(str(it["unit_price_usd"]) for it in cleaned),
        "hs_code": ";".join(it["hs_code"] for it in cleaned),
        "origin": ";".join(it["origin_country"] for it in cleaned),
        "items": cleaned,  # type: ignore[dict-item]
    }


def _sv(val: Any) -> str:
    if isinstance(val, bool):
        return "Y" if val else "N"
    if isinstance(val, float):
        return str(int(val)) if val.is_integer() else str(val)
    if isinstance(val, int):
        return str(val)
    return str(val)


def build_ems_params(params: dict[str, Any]) -> str:
    pairs: list[str] = []
    used: set[str] = set()
    for key in EMS_APPLY_KEYS:
        if key not in params or params[key] is None:
            continue
        sv = _sv(params[key]).strip() if not isinstance(params[key], (int, float, bool)) else _sv(params[key])
        if sv == "":
            continue
        pairs.append(f"{key}={sv}")
        used.add(key)
    for key, value in params.items():
        if key in used or value is None:
            continue
        sv = _sv(value).strip() if not isinstance(value, (int, float, bool)) else _sv(value)
        if not sv:
            continue
        pairs.append(f"{key}={sv}")
    return "&".join(pairs)


def validate_recipient_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("수취인 이름(영문)을 입력해주세요.")
    if "@" in cleaned:
        raise ValueError("수취인 이름은 이메일이 아닌 실제 이름(영문)이어야 합니다.")
    return cleaned


def validate_countrycd(code: str) -> str:
    cleaned = re.sub(r"[^A-Za-z]", "", code or "").upper()
    if len(cleaned) != 2:
        raise ValueError("국가코드 2자리(예: JP, US)를 입력해주세요.")
    return cleaned


def validate_apply_input(data: dict[str, Any]) -> dict[str, Any]:
    method = method_of(str(data.get("shipping_method") or "EMS"))
    countrycd = validate_countrycd(str(data.get("countrycd") or ""))
    totweight = int(data.get("totweight") or 0)
    boxlength = float(data.get("boxlength") or 0)
    boxwidth = float(data.get("boxwidth") or 0)
    boxheight = float(data.get("boxheight") or 0)
    weight_err = validate_weight(method["premiumcd"], method["em_ee"], totweight)
    if weight_err:
        raise ValueError(weight_err)
    dim_err = validate_shipping_dimensions(
        method["premiumcd"], method["em_ee"], countrycd, boxlength, boxwidth, boxheight
    )
    if dim_err:
        raise ValueError(dim_err)

    receivename = validate_recipient_name(str(data.get("receivename") or ""))
    addr1 = (str(data.get("receiveaddr1") or "")).strip()
    addr2 = (str(data.get("receiveaddr2") or "")).strip()
    addr3 = (str(data.get("receiveaddr3") or "")).strip()
    if len(addr3) < 2:
        raise ValueError("수취인 상세주소(도로명+번지)를 입력해주세요.")
    if not addr1 and not addr2:
        raise ValueError("수취인 주/도 또는 시/군 주소를 입력해주세요.")

    invoice = serialize_invoice_items(list(data.get("items") or []), totweight)
    sender = resolve_sender()
    return {
        "method": method,
        "countrycd": countrycd,
        "totweight": totweight,
        "boxlength": int(boxlength),
        "boxwidth": int(boxwidth),
        "boxheight": int(boxheight),
        "receivename": receivename,
        "receivezipcode": str(data.get("receivezipcode") or "").strip(),
        "receiveaddr1": addr1,
        "receiveaddr2": addr2,
        "receiveaddr3": addr3,
        "receivetelno": re.sub(r"[^\d+]", "", str(data.get("receivetelno") or "")),
        "receivemail": str(data.get("receivemail") or "").strip(),
        "notes": str(data.get("notes") or "").strip(),
        "invoice": invoice,
        "sender": sender,
        "items": invoice["items"],
    }


def build_apply_params(validated: dict[str, Any], *, order_no: str, custno: str, apprno: str) -> dict[str, Any]:
    method = validated["method"]
    sender = validated["sender"]
    invoice = validated["invoice"]
    return {
        "custno": custno,
        "apprno": apprno,
        "premiumcd": method["premiumcd"],
        "em_ee": method["em_ee"],
        "countrycd": validated["countrycd"],
        "totweight": validated["totweight"],
        "boxlength": validated["boxlength"],
        "boxwidth": validated["boxwidth"],
        "boxheight": validated["boxheight"],
        "boyn": "N",
        "boprc": 0,
        "orderno": order_no,
        "sender": sender["name"],
        "senderzipcode": sender["zipcode"],
        "senderaddr1": sender["addr1"],
        "senderaddr2": sender["addr2"],
        "senderaddr3": sender["addr3"],
        "sendertelno1": sender["tel1"],
        "sendertelno2": sender["tel2"],
        "sendertelno3": sender["tel3"],
        "sendertelno4": sender["tel4"],
        "receivename": validated["receivename"],
        "receivezipcode": validated["receivezipcode"],
        "receiveaddr1": validated["receiveaddr1"],
        "receiveaddr2": validated["receiveaddr2"],
        "receiveaddr3": validated["receiveaddr3"],
        "receivetelno": validated["receivetelno"],
        "receivemail": validated["receivemail"],
        "EM_gubun": invoice["EM_gubun"],
        "contents": invoice["contents"],
        "number": invoice["number"],
        "weight": invoice["weight"],
        "value": invoice["value"],
        "hs_code": invoice["hs_code"],
        "origin": invoice["origin"],
        "currunitcd": "USD",
        "snd_message": validated.get("notes") or "",
    }
