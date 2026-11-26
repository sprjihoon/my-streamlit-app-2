"""근로계약서 엑셀의 급여 입력칸을 같은 방식으로 계산한다.

회사는 실수령액, 세전(과세월급), 연봉 중 하나만 넣는다. 차량지원·식대는 비과세라
보험료 기준에서 빠지고, 기본급·연장·휴일·야간·식대·차량·직책의 합은 공제 전 월급과 같다.
"""
from __future__ import annotations

import math

from backend.app.services.employment_contract.tax_table import lookup_simple_tax

PENSION_RATE = 0.0475
HEALTH_RATE = 0.03595
CARE_RATE = 0.1314
EMPLOYMENT_RATE = 0.009
INDUSTRIAL_RATE = 0.008  # 도소매·소비자용품수리업. 산재는 회사 전액, 근로자 공제 아님.


def _down(value: float, unit: int) -> int:
    return int(math.floor((value / unit) + 1e-9)) * unit


def _deductions(taxable: int, dependents: int = 1) -> dict[str, int]:
    pension_base = _down(taxable, 1000)
    pension = _down(pension_base * PENSION_RATE, 10)
    health = _down(taxable * HEALTH_RATE, 10)
    care = _down(health * CARE_RATE, 10)
    income_tax = lookup_simple_tax(taxable, dependents)
    local_tax = _down(income_tax * 0.1, 10)
    employment = _down(taxable * EMPLOYMENT_RATE, 10)
    industrial = _down(taxable * INDUSTRIAL_RATE, 10)
    total = pension + health + care + income_tax + local_tax + employment
    return {
        "pension_base": pension_base,
        "pension": pension,
        "health": health,
        "care": care,
        "income_tax": income_tax,
        "local_tax": local_tax,
        "employment": employment,
        "industrial": industrial,
        "total": total,
    }


def industrial_insurance(line_or_taxable) -> int:
    """산재보험(회사부담). 실수령 공제에는 넣지 않는다."""
    if isinstance(line_or_taxable, dict):
        stored = int(line_or_taxable.get("industrial") or 0)
        if stored:
            return stored
        taxable = int(line_or_taxable.get("taxable_pay") or line_or_taxable.get("taxable") or 0)
        if not taxable:
            taxable = max(
                int(line_or_taxable.get("gross_pay") or line_or_taxable.get("gross") or 0)
                - int(line_or_taxable.get("vehicle_allowance") or 0)
                - int(line_or_taxable.get("meal_allowance") or 0),
                0,
            )
        return _down(taxable * INDUSTRIAL_RATE, 10)
    return _down(max(int(line_or_taxable or 0), 0) * INDUSTRIAL_RATE, 10)


def _int(data: dict, key: str) -> int:
    value = data.get(key)
    if value in ("", None):
        return 0
    return int(value)


def _from_net(net: int, meal: int, vehicle: int, dependents: int):
    taxable = max(net - meal - vehicle, 0)
    best: tuple | None = None
    for _ in range(60):
        ded = _deductions(taxable, dependents)
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
    return best


def calculate_contract_pay(data: dict) -> dict:
    net = _int(data, "net_pay")
    taxable_in = _int(data, "taxable_pay")
    annual_in = _int(data, "annual_pay")
    meal = _int(data, "meal_allowance")
    vehicle = _int(data, "vehicle_allowance")
    position = _int(data, "position_allowance")
    dependents = _int(data, "dependents") or 1
    if dependents < 1 or dependents > 10:
        raise ValueError("공제대상 가족 수는 1명부터 10명까지입니다.")
    base_hours = float(data.get("base_hours") or 209)
    overtime_hours = float(data["overtime_hours"])
    holiday_hours = float(data["holiday_hours"])
    night_hours = float(data["night_hours"])

    filled = [name for name, value in (("실수령액", net), ("세전금액", taxable_in), ("연봉", annual_in)) if value > 0]
    if len(filled) > 1:
        raise ValueError("실수령액, 세전금액, 연봉 중 하나만 입력하세요.")
    if not filled:
        raise ValueError("실수령액, 세전금액, 연봉 중 하나를 입력하세요.")
    if base_hours <= 0:
        raise ValueError("기본근로시간은 0보다 커야 합니다.")
    for label, value in (
        ("초과근로시간", overtime_hours),
        ("휴일근로시간", holiday_hours),
        ("야간근로시간", night_hours),
        ("차량지원", vehicle),
        ("식대", meal),
        ("직책수당", position),
    ):
        if value < 0:
            raise ValueError(f"{label}은 0 이상이어야 합니다.")

    if net > 0:
        error, taxable, ded, gross, actual = _from_net(net, meal, vehicle, dependents)
        if error > 20:
            raise ValueError("비과세 수당과 실수령액을 이 계산으로 맞출 수 없습니다.")
    else:
        if annual_in > 0:
            if annual_in % 12:
                raise ValueError("연봉은 12로 나누어 떨어지는 금액이어야 합니다.")
            gross = annual_in // 12
            taxable = max(gross - meal - vehicle, 0)
        else:
            taxable = taxable_in
            gross = taxable + meal + vehicle
        ded = _deductions(taxable, dependents)
        actual = gross - ded["total"]
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
        "industrial": ded["industrial"],
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
        "dependents": dependents,
    }
