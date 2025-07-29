"""utils/clean.py – 공통 정규화 헬퍼
---------------------------------------------------
• TRACK_COLS: 운송장/등기 번호 컬럼 이름 모음
• normalize_tracking(): 과학표기·소수 포함 문자열을 순수 숫자ㆍ영문 문자열로 변환
"""
from __future__ import annotations
import re
import pandas as pd

# 운송장·등기번호 관련 컬럼 공통 정의
TRACK_COLS = (
    "등기번호",
    "송장번호",
    "운송장번호",
    "TrackingNo",
    "tracking_no",
)

_num_re = re.compile(r"[^0-9A-Za-z]")


def _to_int_str(val: str) -> str:
    """과학표기 또는 소수점이 포함된 문자열을 정수 문자열로 변환."""
    try:
        if any(ch in val for ch in ("e", "E", ".")):
            return str(int(float(val)))
    except Exception:
        pass
    return val


def normalize_tracking(series: pd.Series) -> pd.Series:  # type: ignore[name-defined]
    """송장번호 계열 Series 정규화.

    1) dtype → str 강제
    2) 과학표기·소수 → 정수 문자열
    3) 숫자·영문 외 문자 제거
    """
    def _clean(x):
        if pd.isna(x):  # type: ignore[attr-defined]
            return ""
        s = str(x).strip()
        s = _to_int_str(s)
        s = _num_re.sub("", s)
        return s

    return series.astype("string").apply(_clean) 