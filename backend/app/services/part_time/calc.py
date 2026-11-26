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


def weekly_holiday_pay(basic_hours: float, hourly_wage: int, reported: bool) -> tuple[float, int]:
    if not reported:
        return 0.0, 0
    hours = weekly_holiday_hours(basic_hours)
    return hours, int(round(hours * int(hourly_wage or 0)))
