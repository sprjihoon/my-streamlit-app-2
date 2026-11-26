"""알바 주휴와 연도별 최저시급.

주휴시간은 파일에 있던 식 그대로다. 월~일 기본 근무시간을 더해 40으로 나누고 8을 곱한다.
신고 알바만 주휴수당을 받고, 미신고 알바는 주휴시간이 0이다.
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
    if basic_hours <= 0:
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


def weekly_holiday_pay(basic_hours: float, hourly_wage: int, reported: bool) -> tuple[float, int]:
    if not reported:
        return 0.0, 0
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
    """미신고 알바는 사업소득 3%와 지방소득세 0.3%만 원천징수한다."""
    taxable = max(int(taxable or 0), 0)
    income = _down10(taxable * 0.03)
    if income < 1000:
        income = 0
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


def settle_part_time_pay(
    taxable: int,
    work_days: int,
    basic_hours: float,
    reported: bool,
    year: int,
    month: int,
    resident_id: str = "",
) -> dict:
    """알바에게 줄 금액과 회사가 따로 낼 보험료.

    신고는 일용근로소득세다. 3.3%를 또 빼지 않는다.
    고용보험은 신고하면 근로자 0.9%를 빼고, 65세 이상은 빼지 않는다.
    국민연금과 건강보험은 8일, 60시간, 220만 원 중 하나면 뺀다.
    산재는 회사만 부담한다.
    """
    taxable = max(int(taxable or 0), 0)
    work_days = max(int(work_days or 0), 0)
    basic_hours = max(float(basic_hours or 0), 0.0)
    if reported:
        tax = daily_worker_tax(taxable, work_days)
        tax["withholding_kind"] = "daily"
    else:
        tax = business_income_tax(taxable)

    last_day = date(year, month, calendar.monthrange(year, month)[1])
    age = _age_on(resident_id, last_day)
    social = reported and taxable > 0
    employment_on = social and (age is None or age < 65)
    pension_gate = work_days >= 8 or basic_hours >= 60 or taxable >= PENSION_INCOME_GATE
    pension_on = social and pension_gate and (age is None or 18 <= age < 60)
    health_on = social and pension_gate

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
    if social:
        unemployment = _down10(taxable * EMPLOYMENT_EMPLOYER_UNEMPLOYMENT_RATE) if employment_on else 0
        stability = _down10(taxable * EMPLOYMENT_EMPLOYER_STABILITY_RATE)
        employer_employment = unemployment + stability
    industrial = _down10(taxable * INDUSTRIAL_EMPLOYER_RATE) if social else 0
    employer_total = employer_pension + employer_health + employer_care + employer_employment + industrial

    if not reported:
        insurance_note = "미신고는 3.3%만 원천징수하고 4대보험은 빼지 않습니다."
    elif not pension_gate:
        insurance_note = "8일·60시간·220만 원 미만이라 국민연금과 건강보험은 빼지 않습니다."
    elif age is not None and age >= 60:
        insurance_note = "만 60세 이상이라 국민연금은 빼지 않습니다."
    else:
        insurance_note = "국민연금과 건강보험을 급여에서 뺍니다."
    if reported and age is not None and age >= 65:
        insurance_note = "만 65세 이상이라 고용보험 근로자분은 빼지 않습니다. " + insurance_note

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
        "insurance_note": insurance_note,
    }
