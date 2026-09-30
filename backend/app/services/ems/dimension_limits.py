"""우체국 EMS / EMS 프리미엄(FedEx) / K-Packet 박스 크기 검증.

Infront apps/web/lib/ems/dimension-limits.ts 와 동일 계약.
3변은 최장·중간·최단으로 정렬 후 규격을 적용한다.
"""

from __future__ import annotations

import math
from typing import Any


EMS_PREMIUM_DIMENSION_RULES = {
    "label": "EMS 프리미엄",
    "maxLongestCm": 274,
    "maxMiddleCm": 105,
    "maxShortestCm": 76,
    "maxLengthPlusGirthCm": 330,
    "maxSumCm": None,
}

EMS_PARCEL_DEFAULT_RULES = {
    "label": "EMS",
    "maxLongestCm": 150,
    "maxLengthPlusGirthCm": 300,
    "maxMiddleCm": None,
    "maxShortestCm": None,
    "maxSumCm": None,
}

EMS_PARCEL_COUNTRY_OVERRIDES = {
    "US": {
        "label": "EMS (미국)",
        "maxLongestCm": 152,
        "maxLengthPlusGirthCm": 275,
        "maxMiddleCm": None,
        "maxShortestCm": None,
        "maxSumCm": None,
    },
    "AU": {
        "label": "EMS (호주)",
        "maxLongestCm": 105,
        "maxLengthPlusGirthCm": 245,
        "maxMiddleCm": None,
        "maxShortestCm": None,
        "maxSumCm": None,
    },
    "BR": {
        "label": "EMS (브라질)",
        "maxLongestCm": 105,
        "maxLengthPlusGirthCm": 200,
        "maxMiddleCm": None,
        "maxShortestCm": None,
        "maxSumCm": None,
    },
}

KPACKET_DIMENSION_RULES = {
    "label": "K-Packet",
    "maxLongestCm": 60,
    "maxSumCm": 90,
    "maxLengthPlusGirthCm": None,
    "maxMiddleCm": None,
    "maxShortestCm": None,
}

EMS_PREMIUM_NONDOC_MAX_WEIGHT_G = 70_000
EMS_PREMIUM_DOC_MAX_WEIGHT_G = 500
EMS_DOC_WEIGHT_TIERS_G = (300, 500, 750, 1000, 1250, 1500, 1750, 2000)


def snap_doc_weight_g(totweight_g: int) -> int:
    """실중량을 EMS 서류 요금 구간으로 올림. Infront snapDocWeightG 와 동일."""
    weight = int(totweight_g or 0)
    for tier in EMS_DOC_WEIGHT_TIERS_G:
        if weight <= tier:
            return tier
    return 2000


def sort_box_dimensions(a: float, b: float, c: float) -> tuple[float, float, float]:
    longest, middle, shortest = sorted([a, b, c], reverse=True)
    return longest, middle, shortest


def calc_length_plus_girth_cm(length_cm: float, width_cm: float, height_cm: float) -> float:
    longest, middle, shortest = sort_box_dimensions(length_cm, width_cm, height_cm)
    return longest + 2 * (middle + shortest)


def get_ems_premium_max_weight_g(em_ee: str | None = None) -> int:
    return EMS_PREMIUM_DOC_MAX_WEIGHT_G if em_ee == "ee" else EMS_PREMIUM_NONDOC_MAX_WEIGHT_G


def get_max_weight_g(premiumcd: str, em_ee: str | None = None) -> int:
    if premiumcd == "14":
        return 2000
    if premiumcd == "32":
        return get_ems_premium_max_weight_g(em_ee)
    if em_ee == "ee":
        return 2000
    return 30000


def get_ems_parcel_dimension_rules(country_code: str | None = None) -> dict[str, Any]:
    cc = (country_code or "").upper()
    if cc in EMS_PARCEL_COUNTRY_OVERRIDES:
        return EMS_PARCEL_COUNTRY_OVERRIDES[cc]
    return EMS_PARCEL_DEFAULT_RULES


def get_dimension_rules_for_service(
    premiumcd: str,
    em_ee: str | None = None,
    country_code: str | None = None,
) -> dict[str, Any] | None:
    if em_ee == "ee":
        return None
    if premiumcd == "32":
        return EMS_PREMIUM_DIMENSION_RULES
    if premiumcd == "14":
        return KPACKET_DIMENSION_RULES
    if premiumcd == "31":
        return get_ems_parcel_dimension_rules(country_code)
    return None


def validate_box_dimensions(
    rules: dict[str, Any],
    length_cm: float,
    width_cm: float,
    height_cm: float,
) -> str | None:
    dims = [length_cm, width_cm, height_cm]
    if any(not isinstance(d, (int, float)) or d <= 0 for d in dims):
        return f"{rules['label']}: 박스 크기(가로·세로·높이)를 올바르게 입력해주세요."

    longest, middle, shortest = sort_box_dimensions(length_cm, width_cm, height_cm)
    total = length_cm + width_cm + height_cm
    length_plus_girth = longest + 2 * (middle + shortest)
    label = rules["label"]

    if longest > rules["maxLongestCm"]:
        return f"{label} 크기 초과: 최장변 {longest:.0f}cm (최대 {rules['maxLongestCm']}cm)"
    if rules.get("maxMiddleCm") is not None and middle > rules["maxMiddleCm"]:
        return f"{label} 크기 초과: 2번째 긴 변 {middle:.0f}cm (최대 {rules['maxMiddleCm']}cm)"
    if rules.get("maxShortestCm") is not None and shortest > rules["maxShortestCm"]:
        return f"{label} 크기 초과: 최단변 {shortest:.0f}cm (최대 {rules['maxShortestCm']}cm)"
    if rules.get("maxSumCm") is not None and total > rules["maxSumCm"]:
        return f"{label} 크기 초과: 가로+세로+높이 {total:.0f}cm (최대 {rules['maxSumCm']}cm)"
    if (
        rules.get("maxLengthPlusGirthCm") is not None
        and length_plus_girth > rules["maxLengthPlusGirthCm"]
    ):
        return (
            f"{label} 크기 초과: 길이+둘레 {length_plus_girth:.0f}cm "
            f"(최대 {rules['maxLengthPlusGirthCm']}cm)"
        )
    return None


def validate_shipping_dimensions(
    premiumcd: str,
    em_ee: str | None,
    countrycd: str | None,
    boxlength: float | None,
    boxwidth: float | None,
    boxheight: float | None,
) -> str | None:
    if boxlength is None or boxwidth is None or boxheight is None:
        return None
    rules = get_dimension_rules_for_service(premiumcd, em_ee, countrycd)
    if not rules:
        return None
    return validate_box_dimensions(rules, boxlength, boxwidth, boxheight)


def volumetric_weight_g(
    premiumcd: str,
    length_cm: float,
    width_cm: float,
    height_cm: float,
) -> int | None:
    """부피중량(g). EMS는 cm³/6000kg, EMS 프리미엄은 cm³/5000kg.

    K-Packet은 우체국 규정상 실중량만 받는다.
    """
    if str(premiumcd or "") == "14":
        return None
    if length_cm <= 0 or width_cm <= 0 or height_cm <= 0:
        return None
    grams_per_cm3 = 5 if str(premiumcd) == "32" else 6
    return math.ceil((length_cm * width_cm * height_cm) / grams_per_cm3)


def chargeable_weight_g(
    premiumcd: str,
    em_ee: str | None,
    actual_g: int,
    length_cm: float = 0,
    width_cm: float = 0,
    height_cm: float = 0,
) -> tuple[int, int | None]:
    """실중량과 부피중량 중 큰 값을 운임 중량으로 쓴다. 서류는 실중량만."""
    actual = int(actual_g or 0)
    if em_ee == "ee":
        return actual, None
    volume = volumetric_weight_g(premiumcd, length_cm, width_cm, height_cm)
    if volume is None:
        return actual, None
    return max(actual, volume), volume


def validate_weight(premiumcd: str, em_ee: str | None, totweight_g: int) -> str | None:
    max_g = get_max_weight_g(premiumcd, em_ee)
    is_doc = em_ee == "ee"
    if premiumcd == "14":
        name = "K-Packet"
    elif is_doc:
        name = "EMS 서류"
    elif premiumcd == "32":
        name = "EMS 프리미엄"
    else:
        name = "EMS"
    if totweight_g > max_g:
        return f"중량 초과: {name} 최대 {max_g / 1000:g}kg (입력: {totweight_g / 1000:.1f}kg)"
    if totweight_g < 1:
        return "총중량(g)을 입력해주세요."
    return None
