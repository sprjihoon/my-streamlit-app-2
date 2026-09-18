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
    {"nationcd": "MO", "nationnm": "마카오", "nationfn": "MACAO"},
    {"nationcd": "MN", "nationnm": "몽골", "nationfn": "MONGOLIA"},
    {"nationcd": "IN", "nationnm": "인도", "nationfn": "INDIA"},
    {"nationcd": "AE", "nationnm": "아랍에미리트", "nationfn": "UNITED ARAB EMIRATES"},
    {"nationcd": "SA", "nationnm": "사우디아라비아", "nationfn": "SAUDI ARABIA"},
    {"nationcd": "SE", "nationnm": "스웨덴", "nationfn": "SWEDEN"},
    {"nationcd": "CH", "nationnm": "스위스", "nationfn": "SWITZERLAND"},
    {"nationcd": "BR", "nationnm": "브라질", "nationfn": "BRAZIL"},
    {"nationcd": "MX", "nationnm": "멕시코", "nationfn": "MEXICO"},
    {"nationcd": "GR", "nationnm": "그리스", "nationfn": "GREECE"},
    {"nationcd": "NG", "nationnm": "나이지리아", "nationfn": "NIGERIA"},
    {"nationcd": "NP", "nationnm": "네팔", "nationfn": "NEPAL"},
    {"nationcd": "NO", "nationnm": "노르웨이", "nationfn": "NORWAY"},
    {"nationcd": "DK", "nationnm": "덴마크", "nationfn": "DENMARK"},
    {"nationcd": "LA", "nationnm": "라오스", "nationfn": "LAOS"},
    {"nationcd": "RO", "nationnm": "루마니아", "nationfn": "ROMANIA"},
    {"nationcd": "LU", "nationnm": "룩셈부르크", "nationfn": "LUXEMBOURG"},
    {"nationcd": "LT", "nationnm": "리투아니아", "nationfn": "LITHUANIA"},
    {"nationcd": "MM", "nationnm": "미얀마", "nationfn": "MYANMAR"},
    {"nationcd": "BD", "nationnm": "방글라데시", "nationfn": "BANGLADESH"},
    {"nationcd": "BE", "nationnm": "벨기에", "nationfn": "BELGIUM"},
    {"nationcd": "BG", "nationnm": "불가리아", "nationfn": "BULGARIA"},
    {"nationcd": "BN", "nationnm": "브루나이", "nationfn": "BRUNEI"},
    {"nationcd": "LK", "nationnm": "스리랑카", "nationfn": "SRI LANKA"},
    {"nationcd": "SK", "nationnm": "슬로바키아", "nationfn": "SLOVAKIA"},
    {"nationcd": "SI", "nationnm": "슬로베니아", "nationfn": "SLOVENIA"},
    {"nationcd": "AR", "nationnm": "아르헨티나", "nationfn": "ARGENTINA"},
    {"nationcd": "IE", "nationnm": "아일랜드", "nationfn": "IRELAND"},
    {"nationcd": "EE", "nationnm": "에스토니아", "nationfn": "ESTONIA"},
    {"nationcd": "AT", "nationnm": "오스트리아", "nationfn": "AUSTRIA"},
    {"nationcd": "UZ", "nationnm": "우즈베키스탄", "nationfn": "UZBEKISTAN"},
    {"nationcd": "EG", "nationnm": "이집트", "nationfn": "EGYPT"},
    {"nationcd": "CZ", "nationnm": "체코", "nationfn": "CZECH REPUBLIC"},
    {"nationcd": "CL", "nationnm": "칠레", "nationfn": "CHILE"},
    {"nationcd": "KZ", "nationnm": "카자흐스탄", "nationfn": "KAZAKHSTAN"},
    {"nationcd": "KH", "nationnm": "캄보디아", "nationfn": "CAMBODIA"},
    {"nationcd": "TR", "nationnm": "튀르키예", "nationfn": "TURKEY"},
    {"nationcd": "PK", "nationnm": "파키스탄", "nationfn": "PAKISTAN"},
    {"nationcd": "PE", "nationnm": "페루", "nationfn": "PERU"},
    {"nationcd": "PT", "nationnm": "포르투갈", "nationfn": "PORTUGAL"},
    {"nationcd": "PL", "nationnm": "폴란드", "nationfn": "POLAND"},
    {"nationcd": "FI", "nationnm": "핀란드", "nationfn": "FINLAND"},
    {"nationcd": "HU", "nationnm": "헝가리", "nationfn": "HUNGARY"},
]

# K-Packet(14) 은 EMS보다 발송국이 적다. 우체국 API를 못 받을 때만 쓴다.
KPACKET_FALLBACK_CODES = {
    "JP", "US", "CN", "HK", "TW", "SG", "TH", "VN", "MY", "PH",
    "AU", "GB", "DE", "FR", "CA", "NZ", "ID", "IT", "ES", "NL",
    "MO", "MN", "IN", "AE", "SA", "KH", "LA", "MM", "BN", "LK",
    "BD", "NP", "PK", "BR", "MX", "TR", "SE", "CH", "BE", "AT",
    "PL", "CZ", "PT", "HU", "IE", "FI", "DK", "NO", "GR",
}

_NATION_PIN = ["JP", "US", "CN", "HK", "TW", "SG", "AU", "CA", "GB", "DE"]


def sort_nations(items: list[dict[str, str]]) -> list[dict[str, str]]:
    rank = {code: i for i, code in enumerate(_NATION_PIN)}
    return sorted(
        items,
        key=lambda n: (rank.get(str(n.get("nationcd") or ""), 99), str(n.get("nationnm") or n.get("nationcd") or "")),
    )


def fallback_nations(premiumcd: str) -> list[dict[str, str]]:
    code = (premiumcd or "31").strip()
    if code == "14":
        items = [dict(n) for n in FALLBACK_NATIONS if n["nationcd"] in KPACKET_FALLBACK_CODES]
    else:
        items = [dict(n) for n in FALLBACK_NATIONS]
    for item in items:
        item["premiumcd"] = code
    return sort_nations(items)


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


def split_sender_tel(phone: str, fallback: dict[str, str]) -> dict[str, str]:
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return {key: fallback.get(key, "") for key in ("tel1", "tel2", "tel3", "tel4")}
    if digits.startswith("82") and len(digits) >= 10:
        rest = digits[2:]
    elif digits.startswith("0") and len(digits) >= 9:
        rest = digits[1:]
    else:
        rest = digits
    tel2 = rest[:2] or fallback.get("tel2", "10")
    remain = rest[2:]
    tel3 = remain[:4] or fallback.get("tel3", "")
    tel4 = remain[4:] or fallback.get("tel4", "")
    return {"tel1": "82", "tel2": tel2, "tel3": tel3, "tel4": tel4}


def format_sender_tel(sender: dict[str, str]) -> str:
    tel2 = (sender.get("tel2") or "").strip()
    tel3 = (sender.get("tel3") or "").strip()
    tel4 = (sender.get("tel4") or "").strip()
    if tel2 and tel3:
        return f"+82{tel2}{tel3}{tel4}"
    return ""


def apply_sender_override(sender: dict[str, str], patch: dict[str, Any] | str | None = None) -> dict[str, str]:
    if isinstance(patch, str) or patch is None:
        patch = {"sender_name": patch or ""}
    result = dict(sender)
    name = str(patch.get("sender_name") or patch.get("name") or "").strip()
    if name:
        if "@" in name:
            raise ValueError("발송인 이름은 이메일이 아닌 실제 이름이어야 합니다.")
        if len(name) > 50:
            raise ValueError("발송인 이름은 50자 이하여야 합니다.")
        result["name"] = name
    zipcode = re.sub(r"\D", "", str(patch.get("sender_zipcode") or patch.get("zipcode") or ""))[:6]
    if zipcode:
        result["zipcode"] = zipcode
    for src, key in (
        ("sender_addr1", "addr1"),
        ("sender_addr2", "addr2"),
        ("sender_addr3", "addr3"),
        ("addr1", "addr1"),
        ("addr2", "addr2"),
        ("addr3", "addr3"),
    ):
        value = str(patch.get(src) or "").strip()
        if value:
            result[key] = value
    tel = str(patch.get("sender_tel") or patch.get("phone") or "").strip()
    if tel:
        result.update(split_sender_tel(tel, result))
    return result


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
    sender = apply_sender_override(resolve_sender(), data)
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
