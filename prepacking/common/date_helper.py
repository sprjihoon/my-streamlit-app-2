"""
prepacking/common/date_helper.py - 날짜 유틸
"""
from __future__ import annotations

import datetime as dt


def now_kst() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Asia/Seoul"))
    except ImportError:
        import pytz
        return dt.datetime.now(pytz.timezone("Asia/Seoul"))


def today_kst() -> dt.date:
    return now_kst().date()


def now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return now_kst().strftime(fmt)


def date_range(start: dt.date, end: dt.date) -> list[dt.date]:
    days = (end - start).days
    return [start + dt.timedelta(days=i) for i in range(days + 1)]


def weekday_ko(d: dt.date) -> str:
    names = ["월", "화", "수", "목", "금", "토", "일"]
    return names[d.weekday()]
