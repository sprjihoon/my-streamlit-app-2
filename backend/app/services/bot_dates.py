"""업무 날짜는 Asia/Seoul만 사용한다. 운영 데이터는 일괄 수정하지 않는다."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Optional, Tuple
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")
_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_ISO_TS_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
    r"(Z|[+-]\d{2}:?\d{2})?"
)


def seoul_now() -> datetime:
    return datetime.now(SEOUL)


def seoul_today() -> date:
    return seoul_now().date()


def seoul_today_str() -> str:
    return seoul_today().isoformat()


def seoul_yesterday_str() -> str:
    return (seoul_today() - timedelta(days=1)).isoformat()


def parse_date_string(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    match = _DATE_RE.match(text)
    if not match:
        return None
    try:
        datetime.strptime(match.group(1), "%Y-%m-%d")
    except ValueError:
        return None
    return match.group(1)


def seoul_date_from_timestamp(value: Any) -> Optional[str]:
    """저장시각을 서울 날짜로만 읽는다. 원본 행은 바꾸지 않는다."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=SEOUL)
        return dt.astimezone(SEOUL).date().isoformat()
    text = str(value).strip()
    parsed = parse_date_string(text)
    match = _ISO_TS_RE.match(text)
    if not match:
        return parsed
    body = f"{match.group(1)}T{match.group(2)}"
    suffix = match.group(3) or ""
    try:
        if suffix.upper() == "Z":
            dt = datetime.fromisoformat(body).replace(tzinfo=ZoneInfo("UTC"))
        elif suffix:
            norm = suffix if ":" in suffix[1:] or len(suffix) == 3 else f"{suffix[:3]}:{suffix[3:]}"
            dt = datetime.fromisoformat(body + norm)
        else:
            # timezone 없는 레거시 값은 날짜 컬럼이 있으면 그걸 쓰고,
            # 여기선 읽기 호환만 위해 서울로 해석한다.
            dt = datetime.fromisoformat(body).replace(tzinfo=SEOUL)
        return dt.astimezone(SEOUL).date().isoformat()
    except ValueError:
        return parsed


def business_date(date_value: Any, saved_at: Any = None) -> Optional[str]:
    dated = parse_date_string(date_value)
    if dated:
        return dated
    return seoul_date_from_timestamp(saved_at)


def this_week_range() -> Tuple[str, str]:
    today = seoul_today()
    start = today - timedelta(days=today.weekday())
    return start.isoformat(), today.isoformat()


def this_month_range() -> Tuple[str, str]:
    today = seoul_today()
    return today.replace(day=1).isoformat(), today.isoformat()


def last_month_range() -> Tuple[str, str]:
    today = seoul_today()
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return first_prev.isoformat(), last_prev.isoformat()


def resolve_relative_range(relative: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    key = (relative or "").strip().lower()
    if key in {"today", "오늘"}:
        day = seoul_today_str()
        return day, day
    if key in {"yesterday", "어제"}:
        day = seoul_yesterday_str()
        return day, day
    if key in {"this_week", "이번주"}:
        return this_week_range()
    if key in {"this_month", "이번달"}:
        return this_month_range()
    if key in {"last_month", "지난달", "저번달"}:
        return last_month_range()
    return None, None
