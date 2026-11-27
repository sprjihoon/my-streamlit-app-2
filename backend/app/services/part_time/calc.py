"""알바 주휴, 세금, 회사 부담 보험.

주휴시간은 월~일 기본 근무시간을 더해 40으로 나누고 8을 곱한다.
그 주 근무가 14시간 미만이면 주휴는 없다.
세금과 보험은 신고 구분이 아니라 근무 기간과 한 주 시간으로 정한다.
"""
from __future__ import annotations

import calendar
import re
from datetime import date

# 고용노동부 최저임금 고시. 시간급.
# 2026년: 고시 제2025-47호, 10,320원.
# 2027년: 고시 제2026-60호, 10,700원.
MINIMUM_WAGES = {
    2024: 9860,
    2025: 10030,
    2026: 10320,
    2027: 10700,
}


def minimum_wage(year: int) -> int:
    if year in MINIMUM_WAGES:
        return MINIMUM_WAGES[year]
    known = sorted(MINIMUM_WAGES)
    if year < known[0]:
        return MINIMUM_WAGES[known[0]]
    return MINIMUM_WAGES[known[-1]]


def weekly_holiday_hours(basic_hours: float) -> float:
    if basic_hours < 14:
        return 0.0
    return basic_hours / 40 * 8


def _down10(value: float) -> int:
    return int(value // 10) * 10


def daily_worker_tax(taxable: int, work_days: int) -> dict:
    """일용근로소득 원천징수.

    일용근로대장은 총지급액, 비과세소득, 소득세, 지방소득세를 적는다.
    소득세는 (과세지급액 - 15만 원 × 근로일수)의 6%에서 그 55%를 세액공제하고,
    10원 미만은 버리고 1,000원 미만은 징수하지 않는다. 지방소득세는 소득세의 10%다.
    """
    taxable = max(int(taxable or 0), 0)
    work_days = max(int(work_days or 0), 0)
    deduction = 150_000 * work_days
    tax_base = max(taxable - deduction, 0)
    calculated = _down10(tax_base * 0.06)
    credit = _down10(calculated * 0.55)
    income = calculated - credit
    if income < 1000:
        income = 0
    local = _down10(income * 0.1) if income else 0
    return {
        "earned_income_deduction": deduction,
        "tax_base": tax_base,
        "calculated_tax": calculated,
        "tax_credit": credit,
        "income_tax": income,
        "local_tax": local,
        "deduction_total": income + local,
    }


def weekly_holiday_pay(basic_hours: float, hourly_wage: int, reported: bool = True) -> tuple[float, int]:
    """주휴는 그 주 시간으로만 정한다. reported 는 예전 호출이 깨지지 않게 남겨 둔다."""
    del reported
    hours = weekly_holiday_hours(basic_hours)
    return hours, int(round(hours * int(hourly_wage or 0)))


# 2026년 근로자 부담. 정규직 급여명세서와 같은 요율이다.
# 국민연금 4.75%, 건강보험 3.595%, 장기요양 건강보험료의 13.14%, 고용보험 0.9%.
# 산재 0.8%는 도소매·소비자용품수리업 회사 부담이라 알바 실지급에서 빼지 않는다.
PENSION_EMPLOYEE_RATE = 0.0475
HEALTH_EMPLOYEE_RATE = 0.03595
CARE_OF_HEALTH_RATE = 0.1314
EMPLOYMENT_EMPLOYEE_RATE = 0.009
EMPLOYMENT_EMPLOYER_UNEMPLOYMENT_RATE = 0.009
EMPLOYMENT_EMPLOYER_STABILITY_RATE = 0.0025
INDUSTRIAL_EMPLOYER_RATE = 0.008
PENSION_INCOME_GATE = 2_200_000


def _pension_bounds(year: int, month: int) -> tuple[int, int]:
    if (year, month) >= (2026, 7):
        return 410_000, 6_590_000
    if (year, month) >= (2025, 7):
        return 400_000, 6_370_000
    return 390_000, 6_170_000


def _birth_date(resident_id: str) -> date | None:
    digits = re.sub(r"\D", "", resident_id or "")
    if len(digits) < 7:
        return None
    century = {
        "1": 1900, "2": 1900, "5": 1900, "6": 1900,
        "3": 2000, "4": 2000, "7": 2000, "8": 2000,
        "9": 1800, "0": 1800,
    }.get(digits[6])
    if century is None:
        return None
    try:
        return date(century + int(digits[0:2]), int(digits[2:4]), int(digits[4:6]))
    except ValueError:
        return None


def _age_on(resident_id: str, on: date) -> int | None:
    born = _birth_date(resident_id)
    if born is None:
        return None
    age = on.year - born.year
    if (on.month, on.day) < (born.month, born.day):
        age -= 1
    return age


def business_income_tax(taxable: int) -> dict:
    """인적용역 사업소득은 지급액의 3%와 그 10%인 지방소득세를 원천징수한다.

    10원 미만은 버린다. 2024년 7월 1일 이후 지급하는 인적용역 사업소득은
    소득세가 1,000원 미만이어도 소액부징수 없이 원천징수한다.
    """
    taxable = max(int(taxable or 0), 0)
    income = _down10(taxable * 0.03)
    local = _down10(income * 0.1) if income else 0
    return {
        "withholding_kind": "business_3_3",
        "earned_income_deduction": 0,
        "tax_base": taxable,
        "calculated_tax": income,
        "tax_credit": 0,
        "income_tax": income,
        "local_tax": local,
    }


def continued_three_months(first_day: date, month_end: date) -> bool:
    """같은 곳에서 3개월 이상 계속 일하면 일용근로가 아니다."""
    month = first_day.month + 3
    year = first_day.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(first_day.day, calendar.monthrange(year, month)[1])
    return month_end >= date(year, month, day)


def choose_pay_regime(first_day: date | None, month_end: date, weekly_max: float, month_hours: float) -> str:
    """회사 총비용이 낮으면서 근로자에게 맞는 신고를 고른다.

    주 15시간 미만은 초단시간이다. 3개월 미만이면 산재만, 3개월 이상이면 고용보험이 붙는다.
    주 15시간 이상이고 3개월 미만이면 일용근로, 그 이후에는 일반 근로다.
    3.3% 인적용역은 현장 알바의 선택지가 아니다.
    """
    short_hours = weekly_max < 15 and month_hours < 60
    long_term = first_day is not None and continued_three_months(first_day, month_end)
    if short_hours:
        return "short_long" if long_term else "short"
    return "regular" if long_term else "daily"


def _wage_income_tax(taxable: int) -> dict:
    """이 시급대의 근로소득 간이세액은 0원이다."""
    taxable = max(int(taxable or 0), 0)
    return {
        "withholding_kind": "wage",
        "earned_income_deduction": 0,
        "tax_base": taxable,
        "calculated_tax": 0,
        "tax_credit": 0,
        "income_tax": 0,
        "local_tax": 0,
    }


def settle_part_time_pay(
    taxable: int,
    work_days: int,
    basic_hours: float,
    reported: bool,
    year: int,
    month: int,
    resident_id: str = "",
    regime: str | None = None,
) -> dict:
    """알바에게 줄 금액과 회사가 따로 낼 보험료.

    regime 가 없으면 기존 신고 구분을 따른다. 명세서 계산은 기간과 시간으로 regime 을 넘긴다.
    """
    taxable = max(int(taxable or 0), 0)
    work_days = max(int(work_days or 0), 0)
    basic_hours = max(float(basic_hours or 0), 0.0)
    if regime is None:
        regime = "daily" if reported else "business"
    if regime == "daily":
        tax = daily_worker_tax(taxable, work_days)
        tax["withholding_kind"] = "daily"
    elif regime == "business":
        tax = business_income_tax(taxable)
    else:
        tax = _wage_income_tax(taxable)
        tax["withholding_kind"] = regime

    last_day = date(year, month, calendar.monthrange(year, month)[1])
    age = _age_on(resident_id, last_day)
    pension_gate = False
    employment_on = False
    industrial_on = regime != "business" and taxable > 0
    if regime == "daily":
        employment_on = taxable > 0 and (age is None or age < 65)
        pension_gate = taxable > 0 and (work_days >= 8 or basic_hours >= 60 or taxable >= PENSION_INCOME_GATE)
    elif regime == "short":
        pension_gate = taxable >= PENSION_INCOME_GATE
    elif regime in {"short_long", "regular"}:
        employment_on = taxable > 0 and (age is None or age < 65)
        pension_gate = taxable > 0 and (basic_hours >= 60 or taxable >= PENSION_INCOME_GATE)
    pension_on = pension_gate and (age is None or 18 <= age < 60)
    health_on = pension_gate

    low, high = _pension_bounds(year, month)
    pension_base = 0
    pension = 0
    if pension_on:
        pension_base = min(max((taxable // 1000) * 1000, low), high)
        pension = _down10(pension_base * (PENSION_EMPLOYEE_RATE if year >= 2026 else 0.045))
    health = _down10(taxable * HEALTH_EMPLOYEE_RATE) if health_on else 0
    care = _down10(health * CARE_OF_HEALTH_RATE) if health else 0
    employment = _down10(taxable * EMPLOYMENT_EMPLOYEE_RATE) if employment_on else 0
    employee_insurance = pension + health + care + employment
    deduction_total = tax["income_tax"] + tax["local_tax"] + employee_insurance

    employer_pension = pension if pension_on else 0
    employer_health = health if health_on else 0
    employer_care = care if health_on else 0
    employer_employment = 0
    if regime in {"daily", "short_long", "regular"} and taxable > 0:
        unemployment = _down10(taxable * EMPLOYMENT_EMPLOYER_UNEMPLOYMENT_RATE) if employment_on else 0
        stability = _down10(taxable * EMPLOYMENT_EMPLOYER_STABILITY_RATE) if employment_on or (age is not None and age >= 65) else 0
        employer_employment = unemployment + stability
    industrial = _down10(taxable * INDUSTRIAL_EMPLOYER_RATE) if industrial_on else 0
    employer_total = employer_pension + employer_health + employer_care + employer_employment + industrial

    notes = {
        "business": "인적용역이면 3.3%를 떼고 4대보험은 없습니다. 현장에서 지시받아 일하는 알바에게는 쓰지 않습니다.",
        "short": "주 15시간 미만이고 3개월 미만입니다. 회사는 산재보험만 냅니다.",
        "short_long": "3개월 이상 이어서 일했고 주 15시간 미만입니다. 회사는 산재와 고용보험을 냅니다.",
        "daily": "주 15시간 이상이고 3개월 미만이라 일용근로로 계산합니다.",
        "regular": "3개월 이상이고 주 15시간 이상이라 일반 근로로 계산합니다.",
    }
    insurance_note = notes.get(regime, "")
    if regime == "daily" and not pension_gate:
        insurance_note += " 8일·60시간·220만 원 미만이라 국민연금과 건강보험은 없습니다."
    elif regime == "regular" and not pension_gate:
        insurance_note += " 60시간·220만 원 미만이라 국민연금과 건강보험은 없습니다."
    elif pension_on and age is not None and age >= 60:
        insurance_note += " 만 60세 이상이라 국민연금은 빼지 않습니다."
    if employment_on and age is not None and age >= 65:
        insurance_note += " 만 65세 이상이라 고용보험 근로자분은 빼지 않습니다."

    return {
        **tax,
        "employment_insurance": employment,
        "pension": pension,
        "pension_base": pension_base,
        "health": health,
        "care": care,
        "employee_insurance": employee_insurance,
        "deduction_total": deduction_total,
        "net_pay": taxable - deduction_total,
        "employer_employment": employer_employment,
        "employer_pension": employer_pension,
        "employer_health": employer_health,
        "employer_care": employer_care,
        "employer_industrial": industrial,
        "employer_total": employer_total,
        "company_cost": taxable + employer_total,
        "pay_regime": regime,
        "insurance_note": insurance_note,
    }
