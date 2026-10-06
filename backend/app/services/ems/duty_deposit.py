"""DDP 청구액. 창고 내부 전산용.

미국 우편은 품목 일반세율에 수수료와 수수료 부가세를 더한다.
2,500달러 초과 프리미엄은 한국산 12.5% 하한, 정식통관 수수료, 대납수수료를 쓴다.
영국은 접수 때 걷지 않으므로 지출은 0원이고, 현지 세금은 예비로만 보여 준다.
환율 2%와 1,000원 올림은 청구액 밖이다.
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
DEFAULT_USD_PER_GBP = 1.35
US_KR_DUTY_FLOOR = 0.125
US_POSTAL_BASE_FEE = 1.04
US_POSTAL_DUTY_FEE = 0.10
US_FEE_VAT = 0.10
US_MPF_RATE = 0.003464
US_MPF_MIN = 34.58
US_MPF_MAX = 670.86
US_DISBURSE_MIN = 17.50
US_DISBURSE_RATE = 0.025
GB_VAT = 0.20
GB_DUTY_THRESHOLD = 135
GB_GIFT_THRESHOLD = 39
_COMPANY_MARKERS = ("풀필먼트", "fulfillment", "틸리언", "tillion", "주식회사", "(주)", "㈜")


def usd_krw_rate() -> int:
    raw = (os.getenv("EMS_USD_KRW_RATE") or "").replace(",", "").strip()
    try:
        rate = float(raw) if raw else 0
    except ValueError:
        rate = 0
    if rate > 0:
        return int(round(rate))
    return DEFAULT_USD_KRW


def usd_per_gbp() -> float:
    raw = (os.getenv("EMS_USD_PER_GBP") or "").replace(",", "").strip()
    try:
        rate = float(raw) if raw else 0
    except ValueError:
        rate = 0
    if rate > 0:
        return rate
    return DEFAULT_USD_PER_GBP


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


def private_gift_allowed(is_gift: bool, sender_name: str | None) -> bool:
    """개인 발송인이 개인에게 보내는 선물만 100달러 면세를 쓴다."""
    if not is_gift:
        return False
    folded = re.sub(r"\s+", "", sender_name or "").lower()
    if not folded:
        return False
    return not any(re.sub(r"\s+", "", marker).lower() in folded for marker in _COMPANY_MARKERS)


def _round_up_to(n: float, unit: int) -> int:
    return int(math.ceil(n / unit) * unit)


def _won(usd: float, rate: float) -> int:
    return int(math.floor(usd * rate + 0.5))


def _fx_reserve(invoice_krw: int, spread: float) -> int:
    if invoice_krw <= 0 or spread <= 0:
        return 0
    raised = _round_up_to(invoice_krw * (1 + spread), 1_000)
    return max(0, raised - invoice_krw)


def _usd_text(amount: float) -> str:
    return f"USD {amount:,.2f}"


def _krw_text(amount: int) -> str:
    return f"{amount:,}원"


def _hs_digits(raw: str) -> str:
    return re.sub(r"\D", "", raw or "") or "HS없음"


def _append_reserve(lines: list[dict[str, str]], reserve: int) -> None:
    if reserve <= 0:
        return
    lines.append({
        "label": "환율 여유",
        "expr": "청구액의 2%를 1,000원으로 올린 차액, 합계 제외",
        "value": _krw_text(reserve),
    })


def _postal_formula(
    *,
    usd: float,
    breakdown: dict[str, Any],
    rate: float,
    deposit: int,
    reserve: int,
    private_gift: bool,
) -> list[dict[str, str]]:
    duty = float(breakdown["dutyUsd"])
    fee_ex = float(breakdown["feeExVatUsd"])
    vat = float(breakdown["feeVatUsd"])
    total = float(breakdown["totalUsd"])
    lines: list[dict[str, str]] = [
        {"label": "신고가액", "expr": "상품 USD", "value": _usd_text(usd)},
    ]
    if private_gift and duty == 0:
        lines.append({"label": "관세", "expr": "개인 선물 USD 100 이하 면세", "value": _usd_text(0)})
        lines.append({"label": "신고수수료", "expr": "USD 1.04", "value": _usd_text(US_POSTAL_BASE_FEE)})
    else:
        duty_note = str(breakdown.get("dutyNote") or "")
        duty_expr = f"{_usd_text(usd)} × {duty_note}" if duty_note else _usd_text(usd)
        if private_gift:
            duty_expr += " (선물 USD 100 초과)"
        elif breakdown.get("companyGift"):
            duty_expr += " (회사 발송, 선물 면세 없음)"
        lines.append({"label": "관세", "expr": duty_expr, "value": _usd_text(duty)})
        lines.append({
            "label": "운송사 수수료",
            "expr": f"USD 1.04 + 관세 {_usd_text(duty)} × 10%",
            "value": _usd_text(fee_ex),
        })
    lines.append({"label": "수수료 부가세", "expr": f"{_usd_text(fee_ex)} × 10%", "value": _usd_text(vat)})
    lines.append({"label": "선납 달러", "expr": "관세 + 수수료 + 부가세", "value": f"USD {total:.4f}"})
    lines.append({
        "label": "청구액",
        "expr": f"USD {total:.4f} × {int(round(rate)):,}원",
        "value": _krw_text(deposit),
    })
    _append_reserve(lines, reserve)
    return lines


def _premium_formula(
    *,
    usd: float,
    breakdown: dict[str, Any],
    rate: float,
    deposit: int,
    reserve: int,
) -> list[dict[str, str]]:
    duty = float(breakdown["dutyUsd"])
    mpf = float(breakdown["mpfUsd"])
    disburse = float(breakdown["serviceFeeUsd"])
    total = float(breakdown["totalUsd"])
    lines = [
        {"label": "신고가액", "expr": "상품 USD", "value": _usd_text(usd)},
        {
            "label": "관세",
            "expr": f"{_usd_text(usd)} × {breakdown.get('dutyNote') or ''}",
            "value": _usd_text(duty),
        },
        {
            "label": "수입처리수수료",
            "expr": f"max(USD {US_MPF_MIN:.2f}, 가액 × 0.3464%)",
            "value": _usd_text(mpf),
        },
        {
            "label": "대납수수료",
            "expr": f"max(USD {US_DISBURSE_MIN:.2f}, (관세+수입처리수수료) × 2.5%)",
            "value": _usd_text(disburse),
        },
        {"label": "선납 달러", "expr": "관세 + 수입처리수수료 + 대납수수료", "value": f"USD {total:.4f}"},
        {
            "label": "청구액",
            "expr": f"USD {total:.4f} × {int(round(rate)):,}원",
            "value": _krw_text(deposit),
        },
    ]
    _append_reserve(lines, reserve)
    return lines


def _unknown_codes(duty_lines: list[dict[str, Any]] | None, usd: float) -> list[str]:
    lines = duty_lines or [{"hs_code": "", "value_usd": usd}]
    missing: list[str] = []
    seen_value = False
    for line in lines:
        value = max(0.0, float(line.get("value_usd") or 0))
        if value <= 0:
            continue
        seen_value = True
        rate, _label = lookup_us_postal_rate(str(line.get("hs_code") or ""))
        if rate is None:
            missing.append(_hs_digits(str(line.get("hs_code") or "")))
    if not seen_value:
        missing.append("HS없음")
    return missing


def _duty_from_lines(
    usd: float,
    duty_lines: list[dict[str, Any]] | None,
    *,
    floor: float,
) -> dict[str, Any]:
    lines = duty_lines or [{"hs_code": "", "value_usd": usd}]
    duty = 0.0
    notes: list[str] = []
    for line in lines:
        value = max(0.0, float(line.get("value_usd") or 0))
        if value <= 0:
            continue
        column1, label = lookup_us_postal_rate(str(line.get("hs_code") or ""))
        if column1 is None:
            continue
        rate = column1
        note = label
        if floor > 0 and column1 < floor:
            rate = floor
            note = f"{label} → 한국산 12.5%"
        duty += value * rate
        notes.append(f"{note} · {_hs_digits(str(line.get('hs_code') or ''))} {_usd_text(value)}")
    return {"dutyUsd": duty, "dutyNote": " + ".join(notes)}


def _estimate_us_postal_duty(
    usd: float,
    *,
    private_gift: bool,
    company_gift: bool,
    duty_lines: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if private_gift and usd <= US_GIFT_MAX_USD:
        fee_ex = US_POSTAL_BASE_FEE
        vat = round(fee_ex * US_FEE_VAT, 4)
        fee = round(fee_ex + vat, 4)
        return {
            "dutyUsd": 0.0,
            "feeExVatUsd": fee_ex,
            "feeVatUsd": vat,
            "serviceFeeUsd": fee,
            "bufferUsd": 0.0,
            "totalUsd": fee,
            "dutyNote": "면세",
            "companyGift": False,
        }
    priced = _duty_from_lines(usd, duty_lines, floor=0)
    duty = float(priced["dutyUsd"])
    fee_ex = round(US_POSTAL_BASE_FEE + duty * US_POSTAL_DUTY_FEE, 4)
    vat = round(fee_ex * US_FEE_VAT, 4)
    fee = round(fee_ex + vat, 4)
    return {
        "dutyUsd": duty,
        "feeExVatUsd": fee_ex,
        "feeVatUsd": vat,
        "serviceFeeUsd": fee,
        "bufferUsd": 0.0,
        "totalUsd": round(duty + fee, 4),
        "dutyNote": priced["dutyNote"],
        "companyGift": company_gift,
    }


def _estimate_us_premium_duty(
    usd: float,
    duty_lines: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    priced = _duty_from_lines(usd, duty_lines, floor=US_KR_DUTY_FLOOR)
    duty = float(priced["dutyUsd"])
    mpf = min(US_MPF_MAX, max(US_MPF_MIN, usd * US_MPF_RATE))
    disburse = max(US_DISBURSE_MIN, (duty + mpf) * US_DISBURSE_RATE)
    return {
        "dutyUsd": duty,
        "mpfUsd": mpf,
        "feeExVatUsd": 0.0,
        "feeVatUsd": 0.0,
        "serviceFeeUsd": disburse,
        "bufferUsd": 0.0,
        "totalUsd": duty + mpf + disburse,
        "dutyNote": priced["dutyNote"],
    }


def _gb_reserve(usd: float, freight_usd: float, private_gift: bool) -> dict[str, Any]:
    per_gbp = usd_per_gbp()
    goods_gbp = usd / per_gbp
    base_usd = usd + max(0.0, freight_usd)
    if private_gift and goods_gbp <= GB_GIFT_THRESHOLD:
        return {
            "estimateUsd": 0.0,
            "goodsGbp": goods_gbp,
            "overThreshold": False,
            "note": "개인 선물 39파운드 이하는 현지 관세·부가세 예비를 두지 않습니다.",
        }
    vat = base_usd * GB_VAT
    over = goods_gbp > GB_DUTY_THRESHOLD
    note = "영국은 접수 때 관세를 걷지 않습니다. 이 금액은 현지 부가세 예비이고 지출에 넣지 않습니다."
    if over:
        note += " 135파운드를 넘어 품목 관세가 따로 붙을 수 있으며, 그 관세는 예비에 없습니다."
    elif freight_usd <= 0:
        note += " 운임이 없으면 물품 가액만으로 계산합니다."
    return {"estimateUsd": vat, "goodsGbp": goods_gbp, "overThreshold": over, "note": note}


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
    sender_name: str | None = None,
    freight_krw: float = 0,
    is_document: bool = False,
) -> dict[str, Any]:
    country = (country_code or "").upper()
    usd = max(0.0, float(customs_value_usd or 0))
    if duty_lines:
        summed = sum(max(0.0, float(line.get("value_usd") or 0)) for line in duty_lines)
        if summed > 0:
            usd = summed
    rate = float(usd_krw if usd_krw is not None else usd_krw_rate())
    path = resolve_ddp_path(country, usd, shipping_method)
    private_gift = private_gift_allowed(is_gift, sender_name)
    empty = {
        "eligible": is_ddp_country(country),
        "dutyPrepaid": False,
        "ddpPath": None,
        "estimateUsd": 0.0,
        "depositKrw": 0,
        "reserveKrw": 0,
        "localEstimateKrw": None,
        "showsLocalEstimate": False,
        "rateConfirmed": True,
        "breakdown": None,
        "ineligibleReason": None,
        "collectionNote": None,
        "usdKrwRate": int(rate),
        "customsValueUsd": usd,
    }
    if is_document:
        return {**empty, "collectionNote": "서류는 관세가 없습니다."}
    if not duty_prepaid_requested:
        return empty
    if not is_ddp_country(country):
        return {
            **empty,
            "eligible": False,
            "ineligibleReason": "해당 국가는 관세 선납(DDP)을 지원하지 않습니다.",
        }
    if country == "GB":
        freight_usd = max(0.0, float(freight_krw or 0)) / rate if rate else 0.0
        reserve = _gb_reserve(usd, freight_usd, private_gift)
        local = _won(float(reserve["estimateUsd"]), rate) if usd > 0 else 0
        return {
            **empty,
            "eligible": True,
            "ddpPath": None,
            "estimateUsd": round(float(reserve["estimateUsd"]) * 100) / 100,
            "localEstimateKrw": local,
            "showsLocalEstimate": usd > 0,
            "collectionNote": reserve["note"] if usd > 0 else "신고가액을 입력하면 현지 세금 예비가 나옵니다.",
            "formula": [
                {"label": "신고가액", "expr": "상품 USD", "value": _usd_text(usd)},
                {
                    "label": "현지 예비",
                    "expr": "부가세 20%, 지출 제외",
                    "value": _krw_text(local),
                },
            ] if usd > 0 else None,
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
        return {**empty, "eligible": True, "dutyPrepaid": True, "ddpPath": path}
    needs_rate = not (path != "premium" and private_gift and usd <= US_GIFT_MAX_USD)
    if needs_rate:
        missing = _unknown_codes(duty_lines, usd)
        if missing:
            shown = ", ".join(missing)
            return {
                **empty,
                "eligible": True,
                "ddpPath": path,
                "rateConfirmed": False,
                "ineligibleReason": f"세율표에 없는 HS({shown})가 있어 선납액을 비웠습니다.",
            }
    if path == "premium":
        breakdown = _estimate_us_premium_duty(usd, duty_lines)
    else:
        breakdown = _estimate_us_postal_duty(
            usd,
            private_gift=private_gift,
            company_gift=is_gift and not private_gift,
            duty_lines=duty_lines,
        )
    deposit = _won(float(breakdown["totalUsd"]), rate)
    reserve = _fx_reserve(deposit, fx_spread)
    formula = (
        _premium_formula(usd=usd, breakdown=breakdown, rate=rate, deposit=deposit, reserve=reserve)
        if path == "premium"
        else _postal_formula(
            usd=usd,
            breakdown=breakdown,
            rate=rate,
            deposit=deposit,
            reserve=reserve,
            private_gift=private_gift,
        )
    )
    return {
        "eligible": True,
        "dutyPrepaid": True,
        "ddpPath": path,
        "estimateUsd": round(float(breakdown["totalUsd"]) * 100) / 100,
        "depositKrw": deposit,
        "reserveKrw": reserve,
        "localEstimateKrw": None,
        "showsLocalEstimate": False,
        "rateConfirmed": True,
        "bufferKrw": 0,
        "breakdown": breakdown,
        "formula": formula,
        "ineligibleReason": None,
        "collectionNote": None,
        "usdKrwRate": int(rate),
        "customsValueUsd": usd,
    }


def get_ddp_country_label(country_code: str) -> str | None:
    labels = {"US": "미국", "GB": "영국"}
    return labels.get((country_code or "").upper())
