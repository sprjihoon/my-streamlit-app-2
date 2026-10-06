"""DDP(관세 선납) 예상액. 창고 내부 전산용.

미국 우편은 2,500달러까지 품목 세율로 선납한다. 원화 환산 때 2%만 얹는다.
영국은 부가세 20%에 버퍼 10%와 환율 2%를 얹는다. 최저 금액으로 올리지 않는다.
"""

from __future__ import annotations

import math
import os
import re
from typing import Any

from backend.app.services.ems.us_postal_duty import lookup_us_postal_rate

DDP_COUNTRY_CODES = ("US", "GB")
US_DDP_MAX_USD = 2500
US_GIFT_MAX_USD = 100
US_POSTAL_DDP_MAX_USD = US_DDP_MAX_USD
DEFAULT_USD_KRW = 1400
DUTY_BUFFER_RATE = 0.10


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


def _usd_text(amount: float) -> str:
    return f"USD {amount:,.2f}"


def _formula_lines(
    *,
    country: str,
    path: str,
    usd: float,
    breakdown: dict[str, Any],
    rate: float,
    fx_spread: float,
    deposit: int,
    is_gift: bool = False,
) -> list[dict[str, str]]:
    """선납 원화가 나온 순서를 화면·확인창에 그대로 보여 준다."""
    duty = breakdown["dutyUsd"]
    service = breakdown["serviceFeeUsd"]
    buffer = breakdown["bufferUsd"]
    total = breakdown["totalUsd"]
    raw_krw = _apply_fx(total, rate, fx_spread)
    base = duty + service
    lines: list[dict[str, str]] = [
        {"label": "신고가액", "expr": "상품 USD", "value": _usd_text(usd)},
    ]
    if country == "US" and path == "premium":
        lines.append({"label": "관세", "expr": f"{_usd_text(usd)} × 20%", "value": _usd_text(duty)})
        lines.append({
            "label": "운송사 수수료",
            "expr": f"USD 2.62 + USD 15.00 + 관세 {_usd_text(duty)} × 5%",
            "value": _usd_text(service),
        })
    elif country == "US" and is_gift and duty == 0:
        lines.append({"label": "관세", "expr": "선물 USD 100 이하 면세", "value": _usd_text(0)})
        lines.append({"label": "신고수수료", "expr": "선물 신고수수료", "value": _usd_text(service)})
    elif country == "US":
        duty_note = str(breakdown.get("dutyNote") or "10%")
        duty_expr = f"{_usd_text(usd)} × {duty_note}"
        if is_gift:
            duty_expr += " (선물 USD 100 초과)"
        lines.append({"label": "관세", "expr": duty_expr, "value": _usd_text(duty)})
        lines.append({
            "label": "운송사 수수료",
            "expr": f"USD 1.04 + 관세 {_usd_text(duty)} × 10%",
            "value": _usd_text(service),
        })
    else:
        lines.append({"label": "부가세", "expr": f"{_usd_text(usd)} × 20%", "value": _usd_text(service)})
    if buffer > 0:
        lines.append({
            "label": "버퍼 10%",
            "expr": f"추정액 USD {base:.4f} × 10%",
            "value": f"USD {buffer:.4f}",
        })
    lines.append({
        "label": "선납 달러",
        "expr": "관세 + 수수료" if buffer <= 0 else "추정액 + 버퍼",
        "value": f"USD {total:.4f}",
    })
    fx_label = "버퍼 2%" if country == "US" else "원화 환산"
    lines.append({
        "label": fx_label,
        "expr": f"USD {total:.4f} × {int(round(rate)):,}원 × {1 + fx_spread:.2f}",
        "value": f"{raw_krw:,.2f}원",
    })
    lines.append({
        "label": "1,000원 올림",
        "expr": "선납 예상금액",
        "value": f"{deposit:,}원",
    })
    return lines


def _estimate_us_postal_duty(
    usd: float,
    is_gift: bool = False,
    duty_lines: list[dict[str, Any]] | None = None,
) -> dict[str, float]:
    if is_gift and usd <= US_GIFT_MAX_USD:
        service = 1.04
        return {
            "dutyUsd": 0,
            "serviceFeeUsd": service,
            "bufferUsd": 0.0,
            "totalUsd": service,
            "dutyNote": "면세",
        }
    lines = duty_lines or [{"hs_code": "", "value_usd": usd}]
    duty = 0.0
    notes: list[str] = []
    for line in lines:
        value = max(0.0, float(line.get("value_usd") or 0))
        if value <= 0:
            continue
        rate, label = lookup_us_postal_rate(str(line.get("hs_code") or ""))
        duty += value * rate
        hs = re.sub(r"\D", "", str(line.get("hs_code") or "")) or "HS없음"
        notes.append(f"{label} · {hs} {_usd_text(value)}")
    service = 1.04 + duty * 0.1
    subtotal = duty + service
    return {
        "dutyUsd": duty,
        "serviceFeeUsd": service,
        "bufferUsd": 0.0,
        "totalUsd": subtotal,
        "dutyNote": " + ".join(notes) if notes else "10%",
    }


def _estimate_us_premium_duty(usd: float) -> dict[str, float]:
    duty = usd * 0.2
    service = 2.62 + 15 + duty * 0.05
    subtotal = duty + service
    return {
        "dutyUsd": duty,
        "serviceFeeUsd": service,
        "bufferUsd": 0.0,
        "totalUsd": subtotal,
        "dutyNote": "20%",
    }


def _estimate_gb_duty(usd: float) -> dict[str, float]:
    vat = usd * 0.2
    buffer = vat * DUTY_BUFFER_RATE
    return {"dutyUsd": 0, "serviceFeeUsd": vat, "bufferUsd": buffer, "totalUsd": vat + buffer}


def calculate_duty_deposit(
    *,
    country_code: str,
    customs_value_usd: float,
    duty_prepaid_requested: bool = True,
    shipping_method: str | None = None,
    usd_krw: float | None = None,
    fx_spread: float = 0.02,
    is_gift: bool = False,
    duty_lines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    country = (country_code or "").upper()
    usd = max(0.0, float(customs_value_usd or 0))
    if duty_lines:
        summed = sum(max(0.0, float(line.get("value_usd") or 0)) for line in duty_lines)
        if summed > 0:
            usd = summed
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
                f"미국 USD {US_DDP_MAX_USD:,} 초과는 EMS 프리미엄(FedEx DDP)으로 발송해야 "
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
        breakdown = _estimate_us_postal_duty(usd, is_gift, duty_lines)
    else:
        breakdown = _estimate_gb_duty(usd)
    deposit = _round_up_to(_apply_fx(breakdown["totalUsd"], rate, fx_spread), 1_000)
    buffer_krw = int(round(_apply_fx(breakdown["bufferUsd"], rate, fx_spread)))
    return {
        "eligible": True,
        "dutyPrepaid": True,
        "ddpPath": path,
        "estimateUsd": round(breakdown["totalUsd"] * 100) / 100,
        "depositKrw": deposit,
        "bufferKrw": buffer_krw,
        "breakdown": breakdown,
        "formula": _formula_lines(
            country=country,
            path=path,
            usd=usd,
            breakdown=breakdown,
            rate=rate,
            fx_spread=fx_spread,
            deposit=deposit,
            is_gift=is_gift and country == "US" and path != "premium",
        ),
        "ineligibleReason": None,
        "usdKrwRate": int(rate),
        "customsValueUsd": usd,
    }


def get_ddp_country_label(country_code: str) -> str | None:
    labels = {"US": "미국", "GB": "영국"}
    return labels.get((country_code or "").upper())
