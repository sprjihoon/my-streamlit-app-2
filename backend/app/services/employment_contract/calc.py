"""근로계약서 엑셀의 급여 입력칸을 같은 방식으로 계산한다.

실수령액(총액)을 맞추도록 공제를 반복 계산하고, 차량지원·식대는 비과세로
보험료 기준에서 뺀다. 기본급·연장·휴일·야간·식대·차량·직책의 합은 공제 전 월급과 같다.
"""
from __future__ import annotations

import math

PENSION_RATE = 0.0475
HEALTH_RATE = 0.03595
CARE_RATE = 0.1314
EMPLOYMENT_RATE = 0.009


def _down(value: float, unit: int) -> int:
    return int(math.floor((value / unit) + 1e-9)) * unit


def _deductions(taxable: int, income_tax: int) -> dict[str, int]:
    pension_base = _down(taxable, 1000)
    pension = _down(pension_base * PENSION_RATE, 10)
    health = _down(taxable * HEALTH_RATE, 10)
    care = _down(health * CARE_RATE, 10)
    local_tax = _down(income_tax * 0.1, 10)
    employment = _down(taxable * EMPLOYMENT_RATE, 10)
    total = pension + health + care + income_tax + local_tax + employment
    return {
        "pension_base": pension_base,
        "pension": pension,
        "health": health,
        "care": care,
        "income_tax": income_tax,
        "local_tax": local_tax,
        "employment": employment,
        "total": total,
    }


def calculate_contract_pay(data: dict) -> dict:
    net = int(data["net_pay"])
    meal = int(data["meal_allowance"])
    vehicle = int(data["vehicle_allowance"])
    position = int(data["position_allowance"])
    income_tax = int(data["income_tax"])
    base_hours = float(data["base_hours"])
    overtime_hours = float(data["overtime_hours"])
    holiday_hours = float(data["holiday_hours"])
    night_hours = float(data["night_hours"])

    if net <= 0:
        raise ValueError("실수령액을 입력하세요.")
    if base_hours <= 0:
        raise ValueError("기본근로시간은 0보다 커야 합니다.")
    for label, value in (
        ("초과근로시간", overtime_hours),
        ("휴일근로시간", holiday_hours),
        ("야간근로시간", night_hours),
        ("차량지원", vehicle),
        ("식대", meal),
        ("직책수당", position),
        ("소득세", income_tax),
    ):
        if value < 0:
            raise ValueError(f"{label}은 0 이상이어야 합니다.")

    taxable = max(net - meal - vehicle, 0)
    best: tuple | None = None
    for _ in range(60):
        ded = _deductions(taxable, income_tax)
        gross = taxable + meal + vehicle
        actual = gross - ded["total"]
        error = abs(actual - net)
        if best is None or error < best[0]:
            best = (error, taxable, ded, gross, actual)
        nxt = net + ded["total"] - meal - vehicle
        if nxt < 0:
            nxt = 0
        if nxt == taxable:
            break
        taxable = int(nxt)

    assert best is not None
    error, taxable, ded, gross, actual = best
    if error > 20:
        raise ValueError("비과세 수당과 실수령액을 이 계산으로 맞출 수 없습니다.")
    if position > taxable:
        raise ValueError("직책수당이 과세 월급보다 큽니다.")

    weighted = base_hours + overtime_hours * 1.5 + holiday_hours * 1.5 + night_hours * 0.5
    hourly = gross / weighted
    raw_base = hourly * base_hours - meal - vehicle - position
    if raw_base < -1:
        raise ValueError("수당 합계가 월급보다 큽니다.")

    overtime_pay = int(round(hourly * overtime_hours * 1.5))
    holiday_pay = int(round(hourly * holiday_hours * 1.5))
    night_pay = int(round(hourly * night_hours * 0.5))
    base_pay = int(gross) - overtime_pay - holiday_pay - night_pay - meal - vehicle - position

    return {
        "taxable": int(taxable),
        "gross": int(gross),
        "net": int(actual),
        "annual": int(gross) * 12,
        "deduction_total": ded["total"],
        "pension_base": ded["pension_base"],
        "pension": ded["pension"],
        "health": ded["health"],
        "care": ded["care"],
        "income_tax": ded["income_tax"],
        "local_tax": ded["local_tax"],
        "employment": ded["employment"],
        "hourly": int(round(hourly)),
        "base_pay": base_pay,
        "overtime_pay": overtime_pay,
        "holiday_pay": holiday_pay,
        "night_pay": night_pay,
        "meal_allowance": meal,
        "vehicle_allowance": vehicle,
        "position_allowance": position,
        "base_hours": base_hours,
        "overtime_hours": overtime_hours,
        "holiday_hours": holiday_hours,
        "night_hours": night_hours,
    }
