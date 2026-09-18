"""DDP(관세 선납). Infront lib/duty-deposit.ts 와 동일 산출.

우체국 postal DDP(미국 $800 이하, 영국) + EMS 프리미엄 FedEx DDP(미국 $800 초과).
창고 접수는 고객 결제가 없지만, 후납·정산용 예상액을 미리 보여 준다.
"""

from __future__ import annotations

import math
import os
from typing import Any

DDP_COUNTRY_CODES = ("US", "GB")
US_DDP_MAX_USD = 800
US_GIFT_MAX_USD = 100
US_POSTAL_DDP_MAX_USD = US_DDP_MAX_USD
DEFAULT_USD_KRW = 1400


def usd_krw_rate() -> int:
    raw = (os.getenv("EMS_USD_KRW_RATE") or "").replace(",", "").strip()
    try:
        rate = float(raw) if raw else 0
    except ValueError:
        rate = 0
    if rate > 0:
        return int(round(rate))
    return DEFAULT_USD_KRW


def is_ddp_country(country_code: str) -> bool:
    return (country_code or "").upper() in DDP_COUNTRY_CODES


def requires_us_ems_premium(country_code: str, customs_value_usd: float) -> bool:
    return (country_code or "").upper() == "US" and customs_value_usd > US_DDP_MAX_USD


def is_postal_ddp_eligible(country_code: str, customs_value_usd: float) -> bool:
    if not is_ddp_country(country_code):
        return False
    if (country_code or "").upper() == "US" and customs_value_usd > US_DDP_MAX_USD:
        return False
    return True


def is_premium_ddp_eligible(
    country_code: str,
    customs_value_usd: float,
    shipping_method: str | None = None,
) -> bool:
    if shipping_method != "EMS_PREMIUM":
        return False
    if (country_code or "").upper() != "US":
        return False
    return customs_value_usd > US_DDP_MAX_USD


def is_ddp_eligible_for_shipment(
    country_code: str,
    customs_value_usd: float,
    shipping_method: str | None = None,
) -> bool:
    return is_postal_ddp_eligible(country_code, customs_value_usd) or is_premium_ddp_eligible(
        country_code, customs_value_usd, shipping_method
    )


def resolve_ddp_path(
    country_code: str,
    customs_value_usd: float,
    shipping_method: str | None = None,
) -> str | None:
    if is_premium_ddp_eligible(country_code, customs_value_usd, shipping_method):
        return "premium"
    if is_postal_ddp_eligible(country_code, customs_value_usd):
        return "postal"
    return None


def _round_up_to(n: float, unit: int) -> int:
    return int(math.ceil(n / unit) * unit)


def _apply_fx(usd: float, rate: float, spread: float) -> float:
    return usd * rate * (1 + spread)


def _estimate_us_postal_duty(usd: float, is_gift: bool = False) -> dict[str, float]:
    if is_gift and usd <= US_GIFT_MAX_USD:
        service = 1.04
        buffer = service * 0.15
        return {"dutyUsd": 0, "serviceFeeUsd": service, "bufferUsd": buffer, "totalUsd": service + buffer}
    duty = usd * 0.17
    service = 1.04 + duty * 0.1
    subtotal = duty + service
    buffer = subtotal * 0.15
    return {"dutyUsd": duty, "serviceFeeUsd": service, "bufferUsd": buffer, "totalUsd": subtotal + buffer}


def _estimate_us_premium_duty(usd: float) -> dict[str, float]:
    duty = usd * 0.2
    service = 2.62 + 15 + duty * 0.05
    subtotal = duty + service
    buffer = subtotal * 0.2
    return {"dutyUsd": duty, "serviceFeeUsd": service, "bufferUsd": buffer, "totalUsd": subtotal + buffer}


def _estimate_gb_duty(usd: float) -> dict[str, float]:
    vat = usd * 0.2
    buffer = vat * 0.1
    return {"dutyUsd": 0, "serviceFeeUsd": vat, "bufferUsd": buffer, "totalUsd": vat + buffer}


def calculate_duty_deposit(
    *,
    country_code: str,
    customs_value_usd: float,
    duty_prepaid_requested: bool = True,
    shipping_method: str | None = None,
    usd_krw: float | None = None,
    fx_spread: float = 0.02,
) -> dict[str, Any]:
    country = (country_code or "").upper()
    usd = max(0.0, float(customs_value_usd or 0))
    rate = float(usd_krw if usd_krw is not None else usd_krw_rate())
    path = resolve_ddp_path(country, usd, shipping_method)
    empty = {
        "eligible": is_ddp_country(country),
        "dutyPrepaid": False,
        "ddpPath": None,
        "estimateUsd": 0.0,
        "depositKrw": 0,
        "breakdown": None,
        "ineligibleReason": None,
        "usdKrwRate": int(rate),
        "customsValueUsd": usd,
    }
    if not duty_prepaid_requested:
        return empty
    if not is_ddp_country(country):
        return {
            **empty,
            "eligible": False,
            "ineligibleReason": "해당 국가는 관세 선납(DDP)을 지원하지 않습니다.",
        }
    if country == "US" and usd > US_DDP_MAX_USD and shipping_method != "EMS_PREMIUM":
        return {
            **empty,
            "eligible": False,
            "ineligibleReason": (
                f"미국 USD {US_DDP_MAX_USD} 초과는 EMS 프리미엄(FedEx DDP)으로 발송해야 "
                "관세 선납이 가능합니다."
            ),
        }
    if not path:
        return {
            **empty,
            "eligible": False,
            "ineligibleReason": "관세 선납(DDP) 조건을 충족하지 않습니다.",
        }
    if usd <= 0:
        return {
            **empty,
            "eligible": True,
            "dutyPrepaid": True,
            "ddpPath": path,
        }
    if country == "US" and path == "premium":
        breakdown = _estimate_us_premium_duty(usd)
    elif country == "US":
        breakdown = _estimate_us_postal_duty(usd, False)
    else:
        breakdown = _estimate_gb_duty(usd)
    min_krw = 25_000 if path == "premium" else (15_000 if country == "US" else 10_000)
    deposit = max(min_krw, _round_up_to(_apply_fx(breakdown["totalUsd"], rate, fx_spread), 1_000))
    return {
        "eligible": True,
        "dutyPrepaid": True,
        "ddpPath": path,
        "estimateUsd": round(breakdown["totalUsd"] * 100) / 100,
        "depositKrw": deposit,
        "breakdown": breakdown,
        "ineligibleReason": None,
        "usdKrwRate": int(rate),
        "customsValueUsd": usd,
    }


def get_ddp_country_label(country_code: str) -> str | None:
    labels = {"US": "미국", "GB": "영국"}
    return labels.get((country_code or "").upper())
