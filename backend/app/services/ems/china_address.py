"""중국 본토 주소 검사.

구글 Address Validation은 중국을 지원하지 않는다. 접수는 우편번호 앞 2자리와
성/직할시가 같은지 보고, 검증 버튼은 같은 구글 키의 Geocoding으로 건물 위치까지
확인한다. 지도가 시/구만 돌려주면 건물을 확인했다고 하지 않는다.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

_SUFFIXES = (
    "autonomousregion",
    "zizhiqu",
    "province",
    "sheng",
    "shi",
    "자치구",
    "성",
    "省",
    "市",
    "시",
)


def _norm(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[\s\-·.'’,，()（）]", "", text)
    changed = True
    while changed and text:
        changed = False
        for suffix in _SUFFIXES:
            if text.endswith(suffix) and len(text) - len(suffix) >= 2:
                text = text[: -len(suffix)]
                changed = True
                break
    return text


def _postal(value: str) -> tuple[str, str]:
    compact = (value or "").strip().translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    compact = re.sub(r"[\s\-]", "", compact)
    if not re.fullmatch(r"\d{6}", compact):
        return "", "중국 우편번호는 6자리 숫자입니다."
    return compact, ""


class _Province:
    def __init__(self, en: str, prefixes: tuple[str, ...], aliases: tuple[str, ...]):
        self.en = en
        self.prefixes = prefixes
        self.aliases = aliases


_PROVINCES = (
    _Province("Beijing", ("10",), ("beijing", "peking", "北京", "北京市", "베이징", "북경", "북경시")),
    _Province("Tianjin", ("30",), ("tianjin", "tientsin", "天津", "天津市", "톈진", "천진", "천진시")),
    _Province("Hebei", ("05", "06", "07"), ("hebei", "河北", "河北省", "허베이", "하북", "하북성")),
    _Province("Shanxi", ("03", "04"), ("shanxi", "山西", "山西省", "산서", "산서성")),
    _Province("Inner Mongolia", ("01", "02"), ("innermongolia", "neimenggu", "内蒙古", "內蒙古", "내몽골", "내몽고", "네이멍구")),
    _Province("Liaoning", ("11", "12"), ("liaoning", "辽宁", "遼寧", "랴오닝", "요녕", "요녕성")),
    _Province("Jilin", ("13",), ("jilin", "吉林", "吉林省", "지린", "길림", "길림성")),
    _Province("Heilongjiang", ("15", "16"), ("heilongjiang", "黑龙江", "黑龍江", "헤이룽장", "흑룡강", "흑룡강성")),
    _Province("Shanghai", ("20",), ("shanghai", "上海", "上海市", "상하이", "상해", "상해시")),
    _Province("Jiangsu", ("21", "22"), ("jiangsu", "江苏", "江蘇", "장쑤", "강소", "강소성")),
    _Province("Zhejiang", ("31", "32"), ("zhejiang", "浙江", "浙江省", "저장", "절강", "절강성")),
    _Province("Anhui", ("23", "24"), ("anhui", "安徽", "安徽省", "안후이", "안휘", "안휘성")),
    _Province("Fujian", ("35", "36"), ("fujian", "福建", "福建省", "푸젠", "복건", "복건성")),
    _Province("Jiangxi", ("33", "34"), ("jiangxi", "江西", "江西省", "장시", "강서", "강서성")),
    _Province("Shandong", ("25", "26", "27"), ("shandong", "山东", "山東", "산둥", "산동", "산동성")),
    _Province("Henan", ("45", "46", "47"), ("henan", "河南", "河南省", "허난", "하남", "하남성")),
    _Province("Hubei", ("43", "44"), ("hubei", "湖北", "湖北省", "후베이", "호북", "호북성")),
    _Province("Hunan", ("41", "42"), ("hunan", "湖南", "湖南省", "후난", "호남", "호남성")),
    _Province("Guangdong", ("51", "52"), ("guangdong", "kwangtung", "广东", "廣東", "광둥", "광동", "광동성")),
    _Province("Guangxi", ("53", "54"), ("guangxi", "guangxizhuang", "guangxizhuangzu", "广西", "廣西", "광시", "광서", "광서성")),
    _Province("Hainan", ("57",), ("hainan", "海南", "海南省", "하이난", "해남", "해남성")),
    _Province("Chongqing", ("40",), ("chongqing", "chungking", "重庆", "重慶", "충칭", "중경", "중경시")),
    _Province("Sichuan", ("61", "62", "63", "64"), ("sichuan", "szechuan", "szechwan", "四川", "四川省", "쓰촨", "사천", "사천성")),
    _Province("Guizhou", ("55", "56"), ("guizhou", "贵州", "貴州", "구이저우", "귀주", "귀주성")),
    _Province("Yunnan", ("65", "66", "67"), ("yunnan", "云南", "雲南", "윈난", "운남", "운남성")),
    _Province("Tibet", ("85", "86"), ("tibet", "xizang", "西藏", "티베트", "서장", "시짱")),
    _Province("Shaanxi", ("71", "72"), ("shaanxi", "陕西", "陝西", "섬서", "섬서성")),
    _Province("Gansu", ("73", "74"), ("gansu", "甘肃", "甘肅", "간쑤", "감숙", "감숙성")),
    _Province("Qinghai", ("81",), ("qinghai", "青海", "青海省", "칭하이", "청해", "청해성")),
    _Province("Ningxia", ("75",), ("ningxia", "ningxiahui", "宁夏", "寧夏", "닝샤", "영하")),
    _Province("Xinjiang", ("83", "84"), ("xinjiang", "xinjianguygur", "xinjianguyghur", "新疆", "신장", "신강")),
)

# 산시 는 산서(Shanxi)와 섬서(Shaanxi)를 모두 가리킨다. 우편번호로만 가른다.
_AMBIGUOUS = {
    "산시": ("Shanxi", "Shaanxi"),
    "산시성": ("Shanxi", "Shaanxi"),
}

_BY_EN = {item.en: item for item in _PROVINCES}
_BY_ALIAS: dict[str, _Province] = {}
_BY_PREFIX: dict[str, _Province] = {}
for _item in _PROVINCES:
    for _alias in _item.aliases:
        _key = _norm(_alias)
        _prev = _BY_ALIAS.get(_key)
        if _prev is not None and _prev is not _item:
            raise RuntimeError(f"중국 성 별칭이 겹칩니다: {_alias}")
        _BY_ALIAS[_key] = _item
    for _prefix in _item.prefixes:
        if _prefix in _BY_PREFIX:
            raise RuntimeError(f"중국 우편번호 권역이 겹칩니다: {_prefix}")
        _BY_PREFIX[_prefix] = _item


def provinces() -> tuple[_Province, ...]:
    return _PROVINCES


def check_china_address(*, addr1: str, addr2: str, zipcode: str) -> dict[str, str | bool]:
    """우편번호 권역과 주/도가 같으면 ok. 다르면 우편번호 기준 영문 성을 제안한다."""
    postal, zip_error = _postal(zipcode)
    if zip_error:
        return {
            "ok": False,
            "message": zip_error,
            "province": "",
            "suggested_addr1": "",
            "zipcode": "",
        }
    zone = _BY_PREFIX.get(postal[:2])
    if zone is None:
        return {
            "ok": False,
            "message": f"중국 우편번호 {postal}의 성/직할시를 확인할 수 없습니다.",
            "province": "",
            "suggested_addr1": "",
            "zipcode": postal,
        }
    names = _candidates(addr1)
    if zone in names:
        if not (addr2 or "").strip():
            return {
                "ok": False,
                "message": "중국 주소는 시/구를 입력해주세요.",
                "province": zone.en,
                "suggested_addr1": "",
                "zipcode": postal,
            }
        return {
            "ok": True,
            "message": f"중국 우편번호와 성이 일치합니다. ({zone.en})",
            "province": zone.en,
            "suggested_addr1": "",
            "zipcode": postal,
        }
    typed = (addr1 or "").strip()
    if typed:
        message = f"중국 우편번호 {postal}의 성은 {zone.en} 입니다. 입력한 주/도({typed})와 다릅니다."
    else:
        message = f"중국 우편번호 {postal}의 성은 {zone.en} 입니다. 주/도를 입력해주세요."
    return {
        "ok": False,
        "message": message,
        "province": zone.en,
        "suggested_addr1": zone.en,
        "zipcode": postal,
    }


def _candidates(addr1: str) -> list[_Province]:
    key = _norm(addr1)
    if not key:
        return []
    ambiguous = _AMBIGUOUS.get(key)
    if ambiguous:
        return [_BY_EN[name] for name in ambiguous]
    found = _BY_ALIAS.get(key)
    return [found] if found else []


def _has_cjk(value: str) -> bool:
    for ch in value or "":
        code = ord(ch)
        if 0x3400 <= code <= 0x9FFF or 0xF900 <= code <= 0xFAFF:
            return True
    return False


def _place_name(value: str) -> str:
    """Guang Dong Sheng, Shen Zhen Shi, Nan Shan Qu 를 Guangdong, Shenzhen, Nanshan 으로."""
    words = [part for part in re.split(r"[\s·]+", (value or "").strip()) if part]
    lower = [part.lower() for part in words]
    drop = {"sheng", "shi", "qu", "xian"}
    if "qu" in lower and "xin" in lower:
        drop = drop | {"xin"}
    kept = [part for part in words if part.lower() not in drop]
    if not kept:
        return (value or "").strip()
    if all(re.fullmatch(r"[A-Za-z]{1,6}", part) for part in kept):
        return "".join(part.capitalize() for part in kept)
    return " ".join(kept)


def _component(components: list[dict], *type_names: str) -> str:
    for item in components:
        types = item.get("types") or []
        if any(name in types for name in type_names):
            return str(item.get("long_name") or "").strip()
    return ""


def _from_geocode(result: dict) -> dict[str, str] | None:
    components = list(result.get("address_components") or [])
    admin = _component(components, "administrative_area_level_1")
    province = ""
    matched = _candidates(admin)
    if len(matched) == 1:
        province = matched[0].en
    elif admin:
        province = _place_name(admin)
    location_type = str((result.get("geometry") or {}).get("location_type") or "")
    if location_type == "ROOFTOP":
        precision = "rooftop"
    elif location_type == "RANGE_INTERPOLATED":
        precision = "range"
    else:
        precision = "area"
    street_number = _component(components, "street_number")
    route = _component(components, "route")
    street = " ".join(part for part in (street_number, route) if part)
    return {
        "precision": precision,
        "province": province,
        "city": _place_name(_component(components, "locality")),
        "district": _place_name(_component(components, "sublocality_level_1")),
        "street": street,
        "zipcode": _component(components, "postal_code"),
    }


def geocode_china(*, addr1: str, addr2: str, addr3: str, zipcode: str, timeout: float = 8) -> dict[str, str] | None:
    """구글 Geocoding. 키가 없거나 결과가 없으면 None."""
    from backend.app.services.ems.google_address import google_maps_api_key

    api_key = google_maps_api_key()
    if not api_key:
        return None
    query = ", ".join(part for part in (addr3, addr2, addr1, zipcode, "China") if str(part).strip())
    params = urllib.parse.urlencode({
        "address": query,
        "components": "country:CN",
        "language": "en",
        "key": api_key,
    })
    request = urllib.request.Request(
        "https://maps.googleapis.com/maps/api/geocode/json?" + params,
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    results = data.get("results") or []
    if data.get("status") != "OK" or not results:
        return None
    return _from_geocode(results[0])


def review_china_address(
    *,
    addr1: str,
    addr2: str,
    addr3: str,
    zipcode: str,
    geocoder=None,
) -> dict[str, str | bool]:
    """우편번호·성을 먼저 보고, 지도가 건물을 찾으면 영문 주소를 제안한다."""
    local = check_china_address(addr1=addr1, addr2=addr2, zipcode=zipcode)
    reviewed: dict[str, str | bool] = {
        **local,
        "suggested_addr2": "",
        "suggested_addr3": "",
        "precision": "postal",
    }
    if not local["ok"]:
        return reviewed
    finder = geocoder if geocoder is not None else geocode_china
    try:
        found = finder(addr1=addr1, addr2=addr2, addr3=addr3, zipcode=str(local["zipcode"]))
    except Exception:
        found = None
    if not found:
        reviewed["message"] = "우편번호와 성은 일치합니다. 지도에서 이 주소를 찾지 못했습니다."
        return reviewed
    precision = str(found.get("precision") or "area")
    reviewed["precision"] = precision
    if precision not in {"rooftop", "range"}:
        reviewed["message"] = (
            "우편번호와 성은 일치합니다. 지도는 시/구까지만 확인했고, 건물 번호는 확인되지 않았습니다."
        )
        return reviewed
    suggestion = _map_suggestion(addr1, addr2, addr3, local, found)
    if suggestion is None:
        reviewed["message"] = "지도에서 건물 위치까지 확인했습니다."
        return reviewed
    reviewed.update(suggestion)
    reviewed["ok"] = False
    return reviewed


def _map_suggestion(addr1: str, addr2: str, addr3: str, local: dict, found: dict) -> dict[str, str | bool] | None:
    province = str(found.get("province") or local["province"])
    city = str(found.get("city") or addr2).strip()
    district = str(found.get("district") or "").strip()
    street = str(found.get("street") or "").strip()
    postal = str(found.get("zipcode") or local["zipcode"])
    province_differs = province != local["province"]
    zip_differs = bool(found.get("zipcode")) and postal != local["zipcode"]
    needs_latin = _has_cjk(addr1) or _has_cjk(addr2) or _has_cjk(addr3)
    if not province_differs and not zip_differs and not needs_latin:
        return None
    if needs_latin and street:
        detail_parts = [street]
        if district and district.lower() != city.lower():
            detail_parts.append(district)
        detail = ", ".join(detail_parts)
    else:
        detail = addr3.strip()
    if not detail:
        detail = addr3.strip()
    if province_differs or zip_differs:
        message = f"지도에서 찾은 주소는 {province} {city} {postal} 입니다."
    else:
        message = "지도에서 건물 위치를 찾았습니다. 영문 주소로 맞출까요?"
    return {
        "message": message,
        "province": province,
        "suggested_addr1": province,
        "suggested_addr2": city,
        "suggested_addr3": detail,
        "zipcode": postal,
        "precision": str(found.get("precision") or "rooftop"),
    }
