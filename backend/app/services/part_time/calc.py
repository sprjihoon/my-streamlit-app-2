"""알바 주휴와 연도별 최저시급.

주휴시간은 파일에 있던 식 그대로다. 월~일 기본 근무시간을 더해 40으로 나누고 8을 곱한다.
신고 알바만 주휴수당을 받고, 미신고 알바는 주휴시간이 0이다.
"""
from __future__ import annotations

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
