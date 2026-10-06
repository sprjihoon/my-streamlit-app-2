"""EMS/K-Packet 접수 필드 정규화. Infront lib/ems 와 동일 계약."""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any

from anyascii import anyascii

from backend.app.services.ems.dimension_limits import (
    chargeable_weight_g,
    snap_doc_weight_g,
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
    "sendermobile1",
    "sendermobile2",
    "sendermobile3",
    "sendermobile4",
    "receivename",
    "receivezipcode",
    "receiveaddr1",
    "receiveaddr2",
    "receiveaddr3",
    "receivetelno1",
    "receivetelno2",
    "receivetelno3",
    "receivetelno4",
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
    return dict(method)


def normalize_contents_type(raw: Any) -> str:
    text = str(raw or "parcel").strip().lower()
    if text in {"document", "doc", "ee", "서류", "documents"}:
        return "document"
    return "parcel"


def contents_label(contents_type: str, customs_gubun: str = "merchandise") -> str:
    if normalize_contents_type(contents_type) == "document":
        return "서류"
    purpose = normalize_customs_gubun(customs_gubun, contents_type)
    if purpose == "gift":
        return "선물"
    if purpose == "sample":
        return "상품견본"
    return "화물"


def normalize_customs_gubun(raw: Any, contents_type: Any = "parcel") -> str:
    """우체국 EM_gubun. 서류는 Document, 화물은 Merchandise·Gift·Sample."""
    if normalize_contents_type(contents_type) == "document":
        return "document"
    text = str(raw or "merchandise").strip().lower()
    if text in {"gift", "선물"}:
        return "gift"
    if text in {"sample", "상품견본", "견본", "샘플"}:
        return "sample"
    return "merchandise"


def em_gubun_api_value(customs_gubun: str) -> str:
    return {"gift": "Gift", "sample": "Sample", "document": "Document"}.get(
        customs_gubun, "Merchandise"
    )


def resolve_method(shipping_method: str, contents_type: Any = None) -> dict[str, str]:
    method = method_of(shipping_method)
    kind = normalize_contents_type(contents_type)
    if method["premiumcd"] == "14" and kind == "document":
        raise ValueError("K-Packet은 서류 접수가 불가합니다. 화물로 접수하세요.")
    if kind == "document":
        method["em_ee"] = "ee"
    return method


def serialize_invoice_items(
    items: list[dict[str, Any]],
    totweight_g: int,
    *,
    contents_type: str = "parcel",
    customs_gubun: str = "merchandise",
) -> dict[str, str]:
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
        product_name = str(raw.get("product_name") or "").strip()[:80]
        cleaned.append(
            {
                "product_name": product_name,
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
    purpose = normalize_customs_gubun(customs_gubun, contents_type)
    gubun = em_gubun_api_value(purpose)
    return {
        "EM_gubun": ";".join([gubun] * len(cleaned)),
        "contents": ";".join(it["name_en"] for it in cleaned),
        "number": ";".join(str(it["quantity"]) for it in cleaned),
        "weight": ";".join(str(w) for w in weights),
        "value": ";".join(str(it["unit_price_usd"]) for it in cleaned),
        "hs_code": ";".join(it["hs_code"] for it in cleaned),
        "origin": ";".join(it["origin_country"] for it in cleaned),
        "items": cleaned,  # type: ignore[dict-item]
    }


# 우체국 접수 본문은 EUC-KR이다. 분해되지 않는 라틴 문자는 여기서 영문으로 바꾼다.
_EPOST_FOLDS = str.maketrans(
    {
        "ä": "ae",
        "Ä": "Ae",
        "ö": "oe",
        "Ö": "Oe",
        "ü": "ue",
        "Ü": "Ue",
        "ß": "ss",
        "ẞ": "SS",
        "æ": "ae",
        "Æ": "AE",
        "œ": "oe",
        "Œ": "OE",
        "ø": "o",
        "Ø": "O",
        "ł": "l",
        "Ł": "L",
        "đ": "d",
        "Đ": "D",
        "ð": "d",
        "Ð": "D",
        "þ": "th",
        "Þ": "Th",
        "ı": "i",
        "–": "-",
        "—": "-",
        "−": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        "\u00a0": " ",
    }
)


class EpostTextError(ValueError):
    """우체국 문자로 못 바꾼 칸. 화면은 field 로 그 입력칸만 표시한다."""

    def __init__(self, errors: list[dict[str, str]]):
        self.errors = errors
        shown = ", ".join(f"{row['label']}: {row['chars']}" for row in errors)
        super().__init__(
            f"우체국 접수에 넣을 수 없는 문자가 있습니다 ({shown}). 영문·숫자·한글로 바꿔주세요."
        )


def _euc_kr_ok(text: str) -> bool:
    try:
        text.encode("euc-kr")
    except UnicodeEncodeError:
        return False
    return True


def _nfkd_ascii(ch: str) -> str:
    return "".join(
        part
        for part in unicodedata.normalize("NFKD", ch)
        if not unicodedata.combining(part)
    )


def _roman_ok(roman: str) -> bool:
    """한자·태국어 등을 영문 알파벳으로만 받는다. 이모지 별칭(:grinning:)은 거절한다."""
    if not roman or ":" in roman:
        return False
    return all(ch.isascii() and (ch.isalnum() or ch in " -'") for ch in roman)


def _should_romanize(ch: str) -> bool:
    """한글은 우체국이 받는다. 한자·가나·태국어·아랍어는 영문으로 묶어서 바꾼다."""
    o = ord(ch)
    if 0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F:
        return False
    return (
        0x3040 <= o <= 0x30FF
        or 0x3400 <= o <= 0x4DBF
        or 0x4E00 <= o <= 0x9FFF
        or 0xF900 <= o <= 0xFAFF
        or 0x0E00 <= o <= 0x0E7F
        or 0x0600 <= o <= 0x06FF
        or 0x0750 <= o <= 0x077F
        or 0x0590 <= o <= 0x05FF
        or 0x0900 <= o <= 0x097F
    )


def _fold_epost_text(value: str) -> tuple[str, str]:
    """EUC-KR로 들어가는 문자열과, 끝까지 못 바꾼 글자."""
    text = value.translate(_EPOST_FOLDS)
    out: list[str] = []
    bad: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if not _should_romanize(ch) and _euc_kr_ok(ch):
            out.append(ch)
            i += 1
            continue
        if unicodedata.combining(ch):
            i += 1
            continue
        folded = _nfkd_ascii(ch)
        if not _should_romanize(ch) and folded and folded != ch and _euc_kr_ok(folded):
            out.append(folded)
            i += 1
            continue
        j = i + 1
        while j < len(text):
            nxt = text[j]
            if _should_romanize(nxt):
                j += 1
                continue
            if _euc_kr_ok(nxt) or unicodedata.combining(nxt):
                break
            nxt_folded = _nfkd_ascii(nxt)
            if nxt_folded and nxt_folded != nxt and _euc_kr_ok(nxt_folded):
                break
            j += 1
        run = text[i:j]
        roman = anyascii(run).strip()
        if _roman_ok(roman) and _euc_kr_ok(roman):
            out.append(roman)
        else:
            bad.append(run)
        i = j
    return "".join(out), "".join(bad)


def to_euc_kr_text(value: str) -> str:
    """ü, ß 는 ae/oe/ue 로, 한자·태국어는 영문으로 접는다. 한글 음절은 그대로 둔다."""
    converted, bad = _fold_epost_text(value)
    if bad:
        raise ValueError(
            f"우체국 접수에 넣을 수 없는 문자가 있습니다 ({bad}). 영문·숫자·한글로 바꿔주세요."
        )
    return converted


def _fit_epost_text(
    corrections: list[dict[str, str]],
    problems: list[dict[str, str]],
    label: str,
    field: str,
    value: str,
) -> str:
    """우체국에 넣기 전에 고친다. 고친 내용은 확인 창에, 못 고친 글자는 입력칸에 보여 준다."""
    original = value or ""
    if not original:
        return ""
    corrected, bad = _fold_epost_text(original)
    if bad:
        problems.append({"field": field, "label": label, "chars": bad})
        return original
    if corrected != original:
        corrections.append({
            "field": field,
            "label": label,
            "before": original,
            "after": corrected,
        })
    return corrected


def _sv(val: Any) -> str:
    if isinstance(val, bool):
        return "Y" if val else "N"
    if isinstance(val, float):
        return str(int(val)) if val.is_integer() else str(val)
    if isinstance(val, int):
        return str(val)
    return to_euc_kr_text(str(val))


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


_SENDER_NAME_EN = {
    "틸리언": "Tillion",
    "스프링풀필먼트": "Spring Fulfillment",
}


def hs_code_for_epost(code: str, *, document: bool = False) -> str:
    """화면 HS를 우체국 목록에 있는 10자리 세번으로 바꾼다. 서류는 49로 시작하는 코드만 가능하다."""
    from backend.app.services.ems.epost_hs import resolve_epost_hs

    parts = []
    for piece in str(code or "").split(";"):
        digits = re.sub(r"\D", "", piece)
        if not digits and not document:
            continue
        resolved = resolve_epost_hs(digits) if digits else ""
        if document and (len(resolved) != 10 or not resolved.startswith("49")):
            resolved = "4901999000"
        if resolved:
            parts.append(resolved)
    return ";".join(parts)


def epost_sender_name(name: str) -> str:
    """우체국 접수 sender는 영문 35자 이하다. 계약 한글명은 영문으로 바꾼다."""
    raw = (name or "").strip()
    mapped = _SENDER_NAME_EN.get(raw, raw)
    if any(ord(ch) > 127 for ch in mapped):
        raise ValueError("우체국 접수 발송인 이름은 영문 35자 이하여야 합니다.")
    if not mapped or len(mapped) > 35:
        raise ValueError("우체국 접수 발송인 이름은 영문 35자 이하여야 합니다.")
    return mapped


def sender_mobile_parts(sender: dict[str, str]) -> dict[str, str]:
    """계약 EMS 매뉴얼. 발송인 휴대전화는 82 / 10 / 2723 / 9490 처럼 4칸이다."""
    return {
        "sendermobile1": re.sub(r"\D", "", str(sender.get("tel1") or "")) or "82",
        "sendermobile2": re.sub(r"\D", "", str(sender.get("tel2") or "")),
        "sendermobile3": re.sub(r"\D", "", str(sender.get("tel3") or "")),
        "sendermobile4": re.sub(r"\D", "", str(sender.get("tel4") or "")),
    }


_CALLING_CODES = {
    "US": "1", "CA": "1", "JP": "81", "CN": "86", "HK": "852", "TW": "886",
    "GB": "44", "DE": "49", "FR": "33", "AU": "61", "SG": "65", "TH": "66",
    "VN": "84", "MY": "60", "PH": "63", "ID": "62", "NZ": "64", "IT": "39",
    "ES": "34", "NL": "31", "KR": "82",
}


def split_recipient_tel(phone: str, countrycd: str) -> dict[str, str]:
    """수취인 전화. 첫 칸은 도착국 국가번호, 나머지는 4자리씩."""
    digits = re.sub(r"\D", "", phone or "")
    cc = _CALLING_CODES.get((countrycd or "").upper(), "")
    national = digits
    if cc and digits.startswith(cc) and len(digits) > len(cc) + 4:
        national = digits[len(cc):]
    if national.startswith("0"):
        national = national[1:]
    return {
        "receivetelno1": cc,
        "receivetelno2": national[:4],
        "receivetelno3": national[4:8],
        "receivetelno4": national[8:12],
    }


_TRUNK_ZERO_COUNTRIES = {
    "KR", "JP", "GB", "DE", "FR", "AU", "CN", "IT", "ES", "NL",
    "TH", "VN", "MY", "ID", "NZ", "TW",
}


def format_recipient_tel(phone: str, countrycd: str) -> str:
    """수취인 전체 전화번호. 국가번호와 + 없이 010-1234-1234 형식."""
    parts = split_recipient_tel(phone, countrycd)
    national = f"{parts['receivetelno2']}{parts['receivetelno3']}{parts['receivetelno4']}"
    country = (countrycd or "").upper()
    if country in _TRUNK_ZERO_COUNTRIES and national and not national.startswith("0"):
        national = f"0{national}"
    if len(national) == 11:
        return f"{national[:3]}-{national[3:7]}-{national[7:]}"
    if len(national) == 10:
        return f"{national[:3]}-{national[3:6]}-{national[6:]}"
    if len(national) == 9:
        return f"{national[:2]}-{national[2:5]}-{national[5:]}"
    return national


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
    kind = normalize_contents_type(data.get("contents_type"))
    customs_gubun = normalize_customs_gubun(data.get("customs_gubun"), kind)
    method = resolve_method(str(data.get("shipping_method") or "EMS"), kind)
    countrycd = validate_countrycd(str(data.get("countrycd") or ""))
    totweight = int(data.get("totweight") or 0)
    is_doc = method["em_ee"] == "ee"
    weight_err = validate_weight(method["premiumcd"], method["em_ee"], totweight)
    if weight_err:
        raise ValueError(weight_err)
    if is_doc:
        totweight = snap_doc_weight_g(totweight)
    boxlength = float(data.get("boxlength") or 0)
    boxwidth = float(data.get("boxwidth") or 0)
    boxheight = float(data.get("boxheight") or 0)
    volume_weight: int | None = None
    chargeable_weight = totweight
    if not is_doc:
        dim_err = validate_shipping_dimensions(
            method["premiumcd"], method["em_ee"], countrycd, boxlength, boxwidth, boxheight
        )
        if dim_err:
            raise ValueError(dim_err)
        if boxlength < 1 or boxwidth < 1 or boxheight < 1:
            raise ValueError("화물(비서류)은 박스 크기(가로·세로·높이)를 입력해주세요.")
        chargeable_weight, volume_weight = chargeable_weight_g(
            method["premiumcd"],
            method["em_ee"],
            totweight,
            boxlength,
            boxwidth,
            boxheight,
        )
        if chargeable_weight > totweight:
            volume_err = validate_weight(method["premiumcd"], method["em_ee"], chargeable_weight)
            if volume_err:
                raise ValueError(volume_err.replace("중량 초과", "부피중량 초과", 1))

    corrections: list[dict[str, str]] = []
    problems: list[dict[str, str]] = []
    receivename = _fit_epost_text(
        corrections, problems, "수취인", "receivename",
        validate_recipient_name(str(data.get("receivename") or "")),
    )
    addr1 = _fit_epost_text(
        corrections, problems, "주/도", "receiveaddr1", (str(data.get("receiveaddr1") or "")).strip()
    )
    addr2 = _fit_epost_text(
        corrections, problems, "시/군", "receiveaddr2", (str(data.get("receiveaddr2") or "")).strip()
    )
    addr3 = _fit_epost_text(
        corrections, problems, "상세주소", "receiveaddr3", (str(data.get("receiveaddr3") or "")).strip()
    )

    raw_items = []
    for index, raw in enumerate(list(data.get("items") or []), start=1):
        item = dict(raw)
        item["product_name"] = _fit_epost_text(
            corrections, problems, f"{index}행 제품명", f"items.{index - 1}.product_name",
            str(item.get("product_name") or "").strip(),
        )
        item["name_en"] = _fit_epost_text(
            corrections, problems, f"{index}행 품목", f"items.{index - 1}.name_en",
            str(item.get("name_en") or "").strip(),
        )
        raw_items.append(item)
    invoice = serialize_invoice_items(
        raw_items, chargeable_weight, contents_type=kind, customs_gubun=customs_gubun
    )
    notes = _fit_epost_text(corrections, problems, "메모", "notes", str(data.get("notes") or "").strip())
    mail = str(data.get("receivemail") or "").strip()
    if mail and not _euc_kr_ok(mail):
        bad_mail = "".join(ch for ch in mail if not _euc_kr_ok(ch))
        problems.append({"field": "receivemail", "label": "이메일", "chars": bad_mail or mail})

    sender = apply_sender_override(resolve_sender(), data)
    sender = dict(sender)
    for key, label, field in (
        ("addr1", "발송인 시/도", "sender_addr1"),
        ("addr2", "발송인 구/군", "sender_addr2"),
        ("addr3", "발송인 상세주소", "sender_addr3"),
    ):
        sender[key] = _fit_epost_text(corrections, problems, label, field, str(sender.get(key) or ""))
    if problems:
        raise EpostTextError(problems)
    if len(addr3) < 2:
        raise ValueError("수취인 상세주소(도로명+번지)를 입력해주세요.")
    if not addr1 and not addr2:
        raise ValueError("수취인 주/도 또는 시/군 주소를 입력해주세요.")

    posted_name = epost_sender_name(sender["name"])
    if posted_name != sender["name"]:
        corrections.append({
            "field": "sender_name",
            "label": "발송인",
            "before": sender["name"],
            "after": posted_name,
        })
    sender["post_name"] = posted_name
    return {
        "method": method,
        "contents_type": kind,
        "customs_gubun": customs_gubun,
        "contents_label": contents_label(kind, customs_gubun),
        "countrycd": countrycd,
        "totweight": totweight,
        "volume_weight": volume_weight,
        "chargeable_weight": chargeable_weight,
        "boxlength": 0 if is_doc else int(boxlength),
        "boxwidth": 0 if is_doc else int(boxwidth),
        "boxheight": 0 if is_doc else int(boxheight),
        "receivename": receivename,
        "receivezipcode": str(data.get("receivezipcode") or "").strip(),
        "receiveaddr1": addr1,
        "receiveaddr2": addr2,
        "receiveaddr3": addr3,
        "receivetelno": re.sub(r"[^\d+]", "", str(data.get("receivetelno") or "")),
        "receivemail": mail,
        "notes": notes,
        "invoice": invoice,
        "sender": sender,
        "items": invoice["items"],
        "text_corrections": corrections,
    }


def build_apply_params(validated: dict[str, Any], *, order_no: str, custno: str, apprno: str) -> dict[str, Any]:
    method = validated["method"]
    sender = validated["sender"]
    invoice = validated["invoice"]
    is_doc = method["em_ee"] == "ee"
    return {
        "custno": custno,
        "apprno": apprno,
        "premiumcd": method["premiumcd"],
        "em_ee": method["em_ee"],
        "countrycd": validated["countrycd"],
        "totweight": validated.get("chargeable_weight") or validated["totweight"],
        "boxlength": None if is_doc else validated["boxlength"],
        "boxwidth": None if is_doc else validated["boxwidth"],
        "boxheight": None if is_doc else validated["boxheight"],
        "boyn": "N",
        "boprc": 0,
        "orderno": order_no,
        "sender": sender.get("post_name") or epost_sender_name(sender["name"]),
        "senderzipcode": sender["zipcode"],
        "senderaddr1": sender["addr1"],
        "senderaddr2": sender["addr2"],
        "senderaddr3": sender["addr3"],
        "sendertelno1": sender["tel1"],
        "sendertelno2": sender["tel2"],
        "sendertelno3": sender["tel3"],
        "sendertelno4": sender["tel4"],
        **sender_mobile_parts(sender),
        "receivename": validated["receivename"],
        "receivezipcode": validated["receivezipcode"],
        "receiveaddr1": validated["receiveaddr1"],
        "receiveaddr2": validated["receiveaddr2"],
        "receiveaddr3": validated["receiveaddr3"],
        **split_recipient_tel(validated["receivetelno"], validated["countrycd"]),
        "receivetelno": format_recipient_tel(validated["receivetelno"], validated["countrycd"]),
        "receivemail": validated["receivemail"],
        "EM_gubun": invoice["EM_gubun"],
        "contents": invoice["contents"],
        "number": invoice["number"],
        "weight": invoice["weight"],
        "value": invoice["value"],
        "hs_code": hs_code_for_epost(invoice["hs_code"], document=is_doc),
        "origin": invoice["origin"],
        "currunitcd": "USD",
        "snd_message": validated.get("notes") or "",
    }
