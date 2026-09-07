"""우체국 반품소포 필드 정규화. Infront pickup-order / client 와 동일 계약."""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
EPOST_PICKUP_DETAIL_MIN_LEN = 2
EPOST_DISPLAY_CENTER_NM = "스프링풀필먼트"
# 공급지관리의 스프링풀필먼트 공급지코드.
EPOST_OFFICE_SER = "260940699"
EPOST_LEGACY_INFOCUS_OFFICE_SER = "260537802"
EPOST_CONTRACT_COMP_NM = "스프링풀필먼트"
EPOST_ORD_COMP_NM = EPOST_CONTRACT_COMP_NM
LEGACY_CENTER_NAME_MARKERS = ("인프론트", "infront")
EPOST_ORD_COMP_NM_MAX_BYTES = 24
EPOST_ADDR_MAX_BYTES = 100
EPOST_ORDER_NO_MAX_BYTES = 30
EPOST_GOODS_NM_MAX_BYTES = 40
EPOST_DELIV_MSG_MAX_BYTES = 50
EPOST_PHONE_RE = re.compile(r"^\d{9,12}$")

EPOST_PICKUP_KR_HOLIDAYS = {
    "2026-01-01",
    "2026-02-16",
    "2026-02-17",
    "2026-02-18",
    "2026-03-01",
    "2026-05-05",
    "2026-05-24",
    "2026-06-06",
    "2026-08-15",
    "2026-08-16",
    "2026-09-24",
    "2026-09-25",
    "2026-09-26",
    "2026-10-03",
    "2026-10-09",
    "2026-12-25",
}

EPOST_CENTER_DEFAULTS = {
    "ord_nm": EPOST_DISPLAY_CENTER_NM,
    "zip": "41142",
    "addr1": "대구광역시 동구 동촌로 1",
    "addr2": "동대구우체국 2층 소포실",
}

TREAT_STATUS_LABELS = {
    "00": "신청접수",
    "01": "수거완료",
    "02": "수거중",
    "03": "배달완료",
}


def treat_status_code(code: str | None) -> str:
    raw = (code or "").strip()
    if raw.isdigit():
        return raw.zfill(2)
    return raw


def treat_status_from_tracking_text(text: str | None) -> str | None:
    blob = text or ""
    if any(token in blob for token in ("배달완료", "배달 완료")):
        return "03"
    if any(token in blob for token in ("집하완료", "집하 완료", "수거완료", "수거 완료", "집하")):
        return "01"
    if any(token in blob for token in ("수거중", "배달준비", "발송")):
        return "02"
    return None


def treat_status_label(code: str | None, fallback: str | None = None) -> str:
    cd = treat_status_code(code)
    if cd == "01" or (fallback or "").strip() == "집하완료":
        return "수거완료"
    if cd in TREAT_STATUS_LABELS:
        return TREAT_STATUS_LABELS[cd]
    name = (fallback or "").strip()
    return name or "신청접수"


PICKUP_BOX_SIZES = [
    {"code": "DEFAULT", "label": "극소형", "desc": "2kg · 60cm", "weight": 2, "volume": 60},
    {"code": "SMALL", "label": "소형", "desc": "5kg · 80cm", "weight": 5, "volume": 80},
    {"code": "MEDIUM", "label": "중형", "desc": "10kg · 100cm", "weight": 10, "volume": 100},
    {"code": "LARGE", "label": "대형", "desc": "20kg · 120cm", "weight": 20, "volume": 120},
    {"code": "XL", "label": "특대형", "desc": "30kg · 160cm", "weight": 30, "volume": 160},
]
PICKUP_BOX_SIZE_MAP = {s["code"]: s for s in PICKUP_BOX_SIZES}

INSERT_ORDER_KEYS = [
    "custNo",
    "apprNo",
    "payType",
    "reqType",
    "officeSer",
    "weight",
    "volume",
    "microYn",
    "packngMtrCd",
    "orderNo",
    "insuYn",
    "insuAmt",
    "ordCompNm",
    "inqTelCn",
    "ordNm",
    "ordZip",
    "ordAddr1",
    "ordAddr2",
    "ordTel",
    "ordMob",
    "recNm",
    "recZip",
    "recAddr1",
    "recAddr2",
    "recTel",
    "recMob",
    "contCd",
    "goodsNm",
    "goodsCd",
    "goodsMdl",
    "goodsSize",
    "goodsColor",
    "qty",
    "delivMsg",
    "smsOrdCd",
    "retReason",
    "retVisitYmd",
    "retOrigRegiNo",
    "printYn",
    "printAreaCdYn",
]


def today_kst() -> date:
    return datetime.now(KST).date()


def iso_today_kst() -> str:
    return today_kst().isoformat()


def sanitize_plain_field(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[&=\r\n]", " ", value)).strip()


def truncate_utf8_bytes(text: str, max_bytes: int) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    end = max_bytes
    while end > 0 and (raw[end] & 0xC0) == 0x80:
        end -= 1
    return raw[:end].decode("utf-8")


def normalize_zip(zip_code: str | int | None) -> str:
    if zip_code is None or zip_code == "":
        return ""
    return re.sub(r"\D", "", str(zip_code))[:5]


def extract_zip_from_address(addr: str | None) -> str:
    m = re.search(r"(?:^|\s|\[)(\d{5})(?:\s|\]|$)", addr or "")
    return m.group(1) if m else ""


def expand_metro_short_name(addr: str) -> str:
    pairs = [
        (r"^대구\s+(?!광역시)", "대구광역시 "),
        (r"^부산\s+(?!광역시)", "부산광역시 "),
        (r"^인천\s+(?!광역시)", "인천광역시 "),
        (r"^광주\s+(?!광역시)", "광주광역시 "),
        (r"^대전\s+(?!광역시)", "대전광역시 "),
        (r"^울산\s+(?!광역시)", "울산광역시 "),
        (r"^세종\s+(?!특별자치시)", "세종특별자치시 "),
    ]
    for pattern, prefix in pairs:
        if re.search(pattern, addr):
            return re.sub(pattern, prefix, addr, count=1)
    return addr


def normalize_addr1(addr: str | None) -> str:
    trimmed = (addr or "").strip()
    return expand_metro_short_name(trimmed) if trimmed else ""


def resolve_center_addr2(detail: str | None) -> str:
    trimmed = (detail or "").strip()
    return trimmed if len(trimmed) >= 2 else "없음"


def normalize_pickup_addr2(detail: str) -> str:
    text = sanitize_plain_field(detail.strip())
    if not text:
        return text
    compact = re.sub(r"\s+", "", text)
    if re.fullmatch(r"\d+층", compact):
        return f"제{compact}"
    return text


def infer_pickup_address_detail(addr1: str | None, detail: str | None) -> str:
    from_column = (detail or "").strip()
    if len(from_column) >= 2:
        return from_column
    full = (addr1 or "").strip()
    if len(full) < 5:
        return ""
    road_tail = re.search(r"(?:로|길|대로)\s*(\d+(?:-\d+)?)\s+(.+)$", full)
    if road_tail and len(road_tail.group(2).strip()) >= 2:
        return road_tail.group(2).strip()
    comma_parts = [s.strip() for s in re.split(r"[,，]", full) if s.strip()]
    if len(comma_parts) >= 2:
        last = comma_parts[-1]
        if 2 <= len(last) <= 50 and not re.fullmatch(r"\d{5}", last):
            return last
    floor = re.search(r"(\d+\s*층(?:\s*\d+)?[^\s,)]*|\d+\s*호|\d+동\s*\d+[^\s,)]*)", full)
    if floor and len(floor.group(1).strip()) >= 2:
        return floor.group(1).strip()
    paren = re.search(r"\(([^)]+)\)\s*$", full)
    if paren and len(paren.group(1).strip()) >= 2:
        return paren.group(1).strip()
    return ""


def split_pickup_address(addr1: str | None, detail: str | None) -> tuple[str, str]:
    full = normalize_addr1(addr1)
    explicit = (detail or "").strip()
    inferred = infer_pickup_address_detail(full, explicit)
    if len(full) >= 2 and len(explicit) >= 2:
        return full, explicit
    if inferred and inferred != full:
        leftover = full
        if leftover.endswith(inferred):
            leftover = leftover[: -len(inferred)].rstrip(" ,")
        if len(leftover) >= 2:
            return leftover, inferred
        return full, inferred
    return full, inferred


def validate_pickup_address_detail(detail: str | None) -> str | None:
    """
    상세주소 검증. 우체국은 실제로는 빈 값만 아니면 대부분 허용함.
    너무 엄격한 검증은 오히려 정상 입력을 막을 수 있음.
    """
    trimmed = (detail or "").strip()
    if not trimmed:
        return "상세주소(동·호수, 층)를 입력해주세요. 우체국 수거에 필요합니다."
    # 1글자만 있는 경우만 경고 (예: "3" 단독)
    if len(trimmed) == 1 and trimmed.isdigit():
        return f'"{trimmed}"만으로는 부족합니다. 예: {trimmed}층, 302호'
    # 그 외에는 모두 허용 (2층, 3층, 201호, 제3층 등)
    return None


def normalize_phone(phone: str | None, max_len: int = 12) -> str:
    if not phone:
        return ""
    digits = "".join(ch for ch in str(phone) if "0" <= ch <= "9")
    if digits.startswith("82") and len(digits) >= 11:
        digits = f"0{digits[2:]}"
    return digits[:max_len]


def require_phone(phone: str | None, field_label: str) -> str:
    digits = normalize_phone(phone)
    if not EPOST_PHONE_RE.fullmatch(digits):
        current = (phone or "").strip() or "(비어 있음)"
        raise ValueError(
            f"{field_label}는 숫자 9~12자리여야 합니다. (현재: \"{current}\") "
            "01012345678 형식으로 입력해주세요."
        )
    return digits


def is_pickup_date_unavailable(iso_date: str) -> bool:
    d = date.fromisoformat(iso_date)
    if d.weekday() >= 5:
        return True
    return iso_date in EPOST_PICKUP_KR_HOLIDAYS


def default_ret_visit_iso() -> str:
    d = today_kst() + timedelta(days=1)
    while is_pickup_date_unavailable(d.isoformat()):
        d += timedelta(days=1)
    return d.isoformat()


def normalize_ret_visit_ymd(pickup_date: str) -> str:
    ymd = re.sub(r"\D", "", pickup_date)[:8]
    if len(ymd) != 8:
        raise ValueError("수거 희망일 형식이 올바르지 않습니다.")
    iso = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
    if is_pickup_date_unavailable(iso):
        raise ValueError("토·일·공휴일은 수거 희망일로 선택할 수 없습니다.")
    today = today_kst().strftime("%Y%m%d")
    if ymd <= today:
        raise ValueError("수거 희망일은 오늘 이후 날짜를 선택해주세요.")
    max_ymd = (today_kst() + timedelta(days=21)).strftime("%Y%m%d")
    if ymd > max_ymd:
        raise ValueError("수거 희망일은 3주 이내로 선택해주세요.")
    return ymd


def resolve_box_spec(box_size: str | None) -> dict[str, Any]:
    code = (box_size or "DEFAULT").upper()
    spec = PICKUP_BOX_SIZE_MAP.get(code)
    if not spec:
        raise ValueError(f"잘못된 박스 규격: {box_size}")
    return spec


def format_pickup_order_no(seq: int = 1) -> str:
    raw = re.sub(r"[^A-Za-z0-9]", "", f"SPB{int(datetime.now(KST).timestamp() * 1000)}{seq}").upper()
    return truncate_utf8_bytes(raw, EPOST_ORDER_NO_MAX_BYTES)


def sanitize_center_addr(addr: str, default: str) -> str:
    text = addr.strip()
    if len(text) < 2 or not re.search(r"[가-힣]", text) or text.count("?") >= 3:
        return default
    return text


def resolve_office_ser(env: dict[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    raw = re.sub(r"\D", "", (source.get("EPOST_OFFICE_SER") or EPOST_OFFICE_SER).strip())
    if not raw or raw == EPOST_LEGACY_INFOCUS_OFFICE_SER:
        return EPOST_OFFICE_SER
    return raw


def _is_legacy_center_name(value: str | None) -> bool:
    name = (value or "").strip().lower()
    if not name:
        return True
    return any(marker.lower() in name for marker in LEGACY_CENTER_NAME_MARKERS)


def _spring_center_name(value: str | None) -> str:
    if _is_legacy_center_name(value):
        return EPOST_DISPLAY_CENTER_NM
    return (value or "").strip()


def resolve_infront_center(env: dict[str, str]) -> dict[str, str]:
    raw_addr1 = (env.get("INFRONT_CENTER_ADDR1") or EPOST_CENTER_DEFAULTS["addr1"]).strip()
    display_name = _spring_center_name(env.get("INFRONT_CENTER_NAME"))
    return {
        "ord_nm": _spring_center_name(env.get("INFRONT_CENTER_ORD_NM") or EPOST_CENTER_DEFAULTS["ord_nm"]),
        "zip": re.sub(r"\D", "", env.get("INFRONT_CENTER_ZIPCODE") or EPOST_CENTER_DEFAULTS["zip"]),
        "addr1": sanitize_center_addr(raw_addr1, EPOST_CENTER_DEFAULTS["addr1"]),
        "addr2": sanitize_center_addr(
            sanitize_plain_field((env.get("INFRONT_CENTER_ADDR2") or EPOST_CENTER_DEFAULTS["addr2"]).strip()),
            EPOST_CENTER_DEFAULTS["addr2"],
        ),
        "phone": normalize_phone(env.get("INFRONT_CENTER_PHONE") or ""),
        "display_name": display_name,
    }


def _sv(val: Any) -> str:
    if isinstance(val, bool):
        return "Y" if val else "N"
    if isinstance(val, (int, float)):
        return str(int(val))
    return str(val)


def build_epost_params(params: dict[str, Any], endpoint: str = "") -> str:
    if "GetResInfo" in endpoint:
        required = {"custNo", "reqType", "orderNo", "reqYmd"}
        pairs = []
        for key in ["custNo", "reqType", "orderNo", "reqYmd"]:
            if key not in params:
                continue
            val = params[key]
            if val is None:
                raise ValueError(f"[EPost] 필수 파라미터 '{key}'가 누락되었습니다.")
            sv = _sv(val)
            if key in required and not sv.strip():
                raise ValueError(f"[EPost] 필수 파라미터 '{key}'가 비어 있습니다.")
            pairs.append(f"{key}={sv}")
        return "&".join(pairs)

    is_insert = (not endpoint) or ("InsertOrder" in endpoint)
    required = {"custNo", "apprNo", "recNm", "recZip", "recAddr1", "recAddr2", "recTel", "orderNo"}
    pairs: list[str] = []
    for key in INSERT_ORDER_KEYS:
        if key not in params:
            continue
        val = params[key]
        if val is None:
            continue
        sv = _sv(val)
        is_req = key in required
        if not is_req and sv == "":
            continue
        if is_insert and is_req and not sv.strip():
            is_return = str(params.get("reqType")) == "2"
            if key == "ordAddr2" or (key == "recAddr2" and not is_return):
                sv = "없음"
            elif is_return and key == "recAddr2":
                raise ValueError("반품인 상세주소(recAddr2)가 비어 있습니다. 수거지 동·호수·층을 입력해주세요.")
            else:
                raise ValueError(f"필수 파라미터 '{key}'가 비어 있습니다. 주소/연락처를 다시 확인해주세요.")
        elif (not is_insert) and is_req and not sv.strip():
            continue
        if is_insert and is_req and str(params.get("reqType")) == "2" and key == "recAddr2" and sv.strip() == "없음":
            raise ValueError('반품인 상세주소(recAddr2)에 "없음"은 사용할 수 없습니다.')
        pairs.append(f"{key}={sv}")

    for key, value in params.items():
        if key in INSERT_ORDER_KEYS or value is None:
            continue
        sv = _sv(value).strip() if not isinstance(value, (int, float, bool)) else _sv(value)
        if not sv:
            continue
        pairs.append(f"{key}={sv}")
    return "&".join(pairs)


def build_return_pickup_params(input_data: dict[str, Any]) -> dict[str, Any]:
    pickup = input_data["pickup"]
    center = input_data["center"]
    pickup_phone = require_phone(pickup.get("phone"), "수거 연락처(recTel)")
    center_phone = require_phone(center.get("phone"), "센터 연락처(ordMob)")
    addr1, addr2 = split_pickup_address(pickup.get("addr1"), pickup.get("addr2"))
    if len(addr1) < 2:
        raise ValueError("수거지 도로명 주소(recAddr1)가 없습니다.")
    if len(addr2) < EPOST_PICKUP_DETAIL_MIN_LEN:
        raise ValueError("수거지 상세주소(recAddr2)가 없습니다. 동·호수·층을 2글자 이상 입력해주세요.")
    qty = int(input_data.get("qty") or 1)
    if qty < 1:
        raise ValueError("박스 수량은 1개 이상이어야 합니다.")
    if qty > 99:
        raise ValueError("박스 수량은 99개 이하여야 합니다.")
    return {
        "custNo": input_data["cust_no"],
        "apprNo": input_data["appr_no"],
        "payType": "2",
        "reqType": "2",
        "officeSer": resolve_office_ser({"EPOST_OFFICE_SER": str(input_data.get("office_ser") or "")}),
        "orderNo": input_data["order_no"],
        "ordCompNm": EPOST_CONTRACT_COMP_NM,
        "ordNm": truncate_utf8_bytes(EPOST_CONTRACT_COMP_NM, 40),
        "inqTelCn": center_phone,
        "ordZip": normalize_zip(center.get("zip")),
        "ordAddr1": normalize_addr1(center.get("addr1")),
        "ordAddr2": resolve_center_addr2(center.get("addr2")),
        "ordMob": center_phone,
        "recNm": truncate_utf8_bytes(sanitize_plain_field((pickup.get("name") or "고객").strip()), 40),
        "recZip": normalize_zip(pickup.get("zip")),
        "recAddr1": addr1,
        "recAddr2": normalize_pickup_addr2(addr2),
        "contCd": "025",
        "goodsNm": input_data.get("goods_nm") or "해외배송 물품",
        "weight": int(input_data.get("weight") or 2),
        "volume": int(input_data.get("volume") or 60),
        "qty": qty,
        "microYn": "N",
        "delivMsg": input_data.get("deliv_msg") or None,
        "retVisitYmd": normalize_ret_visit_ymd(input_data["ret_visit_ymd"]),
        "testYn": input_data.get("test_yn") or "N",
        "printYn": "Y",
        "recTel": pickup_phone,
    }


def sanitize_insert_order_body(body: dict[str, Any]) -> dict[str, Any]:
    allowed = set(INSERT_ORDER_KEYS)
    cleaned = {k: v for k, v in body.items() if k in allowed}
    for key in ("ordMob", "ordTel", "recMob", "recTel", "inqTelCn"):
        if cleaned.get(key) not in (None, ""):
            cleaned[key] = normalize_phone(str(cleaned[key]))
    if str(cleaned.get("reqType", "")) == "2":
        cleaned.pop("recMob", None)
        if "ordMob" in cleaned:
            cleaned["ordMob"] = require_phone(str(cleaned.get("ordMob") or ""), "주문자 휴대폰(ordMob)")
        if "recTel" in cleaned:
            cleaned["recTel"] = require_phone(str(cleaned.get("recTel") or ""), "수취인 연락처(recTel)")
        if cleaned.get("inqTelCn") not in (None, ""):
            cleaned["inqTelCn"] = require_phone(str(cleaned["inqTelCn"]), "문의전화(inqTelCn)")
    if str(cleaned.get("reqType", "")) == "2":
        cleaned["ordCompNm"] = EPOST_CONTRACT_COMP_NM
        cleaned["ordNm"] = truncate_utf8_bytes(EPOST_CONTRACT_COMP_NM, 40)
        cleaned["officeSer"] = resolve_office_ser(
            {"EPOST_OFFICE_SER": str(cleaned.get("officeSer") or "")}
        )
    if isinstance(cleaned.get("ordCompNm"), str):
        cleaned["ordCompNm"] = truncate_utf8_bytes(
            sanitize_plain_field(cleaned["ordCompNm"]), EPOST_ORD_COMP_NM_MAX_BYTES
        )
    if isinstance(cleaned.get("ordNm"), str):
        cleaned["ordNm"] = truncate_utf8_bytes(sanitize_plain_field(cleaned["ordNm"]), 40)
    if isinstance(cleaned.get("recNm"), str):
        cleaned["recNm"] = truncate_utf8_bytes(sanitize_plain_field(cleaned["recNm"]), 40)
    for key in ("ordAddr1", "ordAddr2", "recAddr1", "recAddr2"):
        if isinstance(cleaned.get(key), str):
            cleaned[key] = truncate_utf8_bytes(sanitize_plain_field(cleaned[key]), EPOST_ADDR_MAX_BYTES)
    if isinstance(cleaned.get("goodsNm"), str):
        cleaned["goodsNm"] = truncate_utf8_bytes(
            sanitize_plain_field(cleaned["goodsNm"]), EPOST_GOODS_NM_MAX_BYTES
        )
    if isinstance(cleaned.get("delivMsg"), str) and cleaned["delivMsg"]:
        cleaned["delivMsg"] = truncate_utf8_bytes(
            sanitize_plain_field(cleaned["delivMsg"]), EPOST_DELIV_MSG_MAX_BYTES
        )
    return cleaned


def resolve_cancel_req_ymd(epost_pickup_date: str | None = None, requested_at: str | None = None) -> str:
    from_res = re.sub(r"\D", "", epost_pickup_date or "")[:8]
    if len(from_res) == 8:
        return from_res
    if requested_at:
        try:
            dt = datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
            return dt.astimezone(KST).strftime("%Y%m%d")
        except ValueError:
            pass
    return today_kst().strftime("%Y%m%d")
