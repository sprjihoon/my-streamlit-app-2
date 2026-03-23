"""
features — 시계열 Feature Engineering (누수 방지)
──────────────────────────────────────────────────
모든 피처는 as_of_date 기준 과거 데이터만 사용.
절대로 미래 정보를 참조하지 않는다.

피처 카테고리:
1. Lag features: 직전값, 7일전, 14일전
2. Rolling features: 7/14/30일 평균, 표준편차, 최대, 중앙값
3. Same-weekday features: 같은 요일 과거 N주 평균/확률
4. Calendar features: 요일, 월, 월초/월말, 주차
5. Shipping probability: 최근 N일 출하 확률
6. Trend: 최근 vs 이전 기간 비율
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

KOREAN_HOLIDAYS_2026 = {
    dt.date(2026, 1, 1), dt.date(2026, 1, 28), dt.date(2026, 1, 29),
    dt.date(2026, 1, 30), dt.date(2026, 3, 1), dt.date(2026, 5, 5),
    dt.date(2026, 5, 24), dt.date(2026, 6, 6), dt.date(2026, 8, 15),
    dt.date(2026, 9, 24), dt.date(2026, 9, 25), dt.date(2026, 9, 26),
    dt.date(2026, 10, 3), dt.date(2026, 10, 9), dt.date(2026, 12, 25),
}


def compute_features_for_date(
    series: pd.Series,
    as_of_date: pd.Timestamp,
    all_dates_index: pd.DatetimeIndex | None = None,
) -> dict[str, float]:
    """
    단일 SKU의 시계열에서 as_of_date 기준 피처를 계산.
    series: index=date(Timestamp), values=qty(int)
    as_of_date: 예측 대상일 (이 날짜의 데이터는 사용하지 않음)

    반환: dict of feature_name -> value
    """
    cutoff = as_of_date - pd.Timedelta(days=1)
    hist = series[series.index <= cutoff].sort_index()

    if hist.empty:
        return _empty_features(as_of_date)

    features: dict[str, float] = {}

    # === 1. Lag features ===
    features["lag_1"] = _safe_lag(hist, 1)
    features["lag_2"] = _safe_lag(hist, 2)
    features["lag_3"] = _safe_lag(hist, 3)
    features["lag_7"] = _safe_lag(hist, 7)
    features["lag_14"] = _safe_lag(hist, 14)

    # === 2. Rolling features (active-day only) ===
    for window in [7, 14, 30]:
        start = cutoff - pd.Timedelta(days=window - 1)
        w = hist[(hist.index >= start) & (hist.index <= cutoff)]
        active = w[w > 0]

        features[f"roll_mean_{window}"] = float(w.mean()) if len(w) > 0 else 0.0
        features[f"roll_active_mean_{window}"] = float(active.mean()) if len(active) > 0 else 0.0
        features[f"roll_std_{window}"] = float(w.std()) if len(w) > 1 else 0.0
        features[f"roll_max_{window}"] = float(w.max()) if len(w) > 0 else 0.0
        features[f"roll_median_{window}"] = float(w.median()) if len(w) > 0 else 0.0
        features[f"roll_active_days_{window}"] = float(len(active))
        features[f"roll_ship_prob_{window}"] = len(active) / max(len(w), 1)

    # === 3. Same-weekday features ===
    target_wd = as_of_date.weekday()
    wd_vals = []
    for wk in range(1, 9):
        past_d = as_of_date - pd.Timedelta(weeks=wk)
        if past_d in hist.index:
            wd_vals.append(float(hist[past_d]))
    wd_active = [v for v in wd_vals if v > 0]

    features["wd_avg"] = np.mean(wd_active) if wd_active else 0.0
    features["wd_ship_prob"] = len(wd_active) / max(len(wd_vals), 1) if wd_vals else 0.0
    features["wd_count"] = float(len(wd_vals))
    features["wd_max"] = max(wd_active) if wd_active else 0.0

    # === 4. Calendar features ===
    d = as_of_date.date() if hasattr(as_of_date, "date") else as_of_date
    features["weekday"] = float(target_wd)
    features["month"] = float(as_of_date.month)
    features["day_of_month"] = float(as_of_date.day)
    features["week_of_year"] = float(as_of_date.isocalendar()[1])
    features["is_monday"] = 1.0 if target_wd == 0 else 0.0
    features["is_friday"] = 1.0 if target_wd == 4 else 0.0
    features["is_weekend"] = 1.0 if target_wd >= 5 else 0.0
    features["is_month_start"] = 1.0 if as_of_date.day <= 3 else 0.0
    features["is_month_end"] = 1.0 if as_of_date.day >= 28 else 0.0
    features["is_holiday"] = 1.0 if d in KOREAN_HOLIDAYS_2026 else 0.0

    # === 5. Trend features ===
    recent_7 = hist.tail(7).mean() if len(hist) >= 7 else hist.mean()
    prev_7 = hist.iloc[-14:-7].mean() if len(hist) >= 14 else 0.0
    features["trend_7d"] = (recent_7 / max(prev_7, 0.1)) if prev_7 > 0 else 1.0

    recent_14 = hist.tail(14).mean() if len(hist) >= 14 else hist.mean()
    prev_14 = hist.iloc[-28:-14].mean() if len(hist) >= 28 else 0.0
    features["trend_14d"] = (recent_14 / max(prev_14, 0.1)) if prev_14 > 0 else 1.0

    # === 6. Last shipment recency ===
    active_hist = hist[hist > 0]
    if not active_hist.empty:
        last_ship_date = active_hist.index[-1]
        features["days_since_last_ship"] = float((as_of_date - last_ship_date).days)
        features["last_ship_qty"] = float(active_hist.iloc[-1])
    else:
        features["days_since_last_ship"] = 999.0
        features["last_ship_qty"] = 0.0

    return features


def _safe_lag(hist: pd.Series, days: int) -> float:
    if hist.empty:
        return 0.0
    target_idx = hist.index[-1] - pd.Timedelta(days=days - 1)
    if target_idx in hist.index:
        return float(hist[target_idx])
    closest = hist.index[hist.index <= target_idx]
    if not closest.empty:
        return float(hist[closest[-1]])
    return 0.0


def _empty_features(as_of_date: pd.Timestamp) -> dict[str, float]:
    features: dict[str, float] = {}
    for lag in [1, 2, 3, 7, 14]:
        features[f"lag_{lag}"] = 0.0
    for window in [7, 14, 30]:
        for suffix in ["mean", "active_mean", "std", "max", "median", "active_days", "ship_prob"]:
            features[f"roll_{suffix}_{window}"] = 0.0
    for k in ["wd_avg", "wd_ship_prob", "wd_count", "wd_max"]:
        features[k] = 0.0
    d = as_of_date.date() if hasattr(as_of_date, "date") else as_of_date
    features["weekday"] = float(as_of_date.weekday())
    features["month"] = float(as_of_date.month)
    features["day_of_month"] = float(as_of_date.day)
    features["week_of_year"] = float(as_of_date.isocalendar()[1])
    features["is_monday"] = 1.0 if as_of_date.weekday() == 0 else 0.0
    features["is_friday"] = 1.0 if as_of_date.weekday() == 4 else 0.0
    features["is_weekend"] = 1.0 if as_of_date.weekday() >= 5 else 0.0
    features["is_month_start"] = 1.0 if as_of_date.day <= 3 else 0.0
    features["is_month_end"] = 1.0 if as_of_date.day >= 28 else 0.0
    features["is_holiday"] = 1.0 if d in KOREAN_HOLIDAYS_2026 else 0.0
    features["trend_7d"] = 1.0
    features["trend_14d"] = 1.0
    features["days_since_last_ship"] = 999.0
    features["last_ship_qty"] = 0.0
    return features


def get_feature_names() -> list[str]:
    """피처 이름 목록 (모델 학습/예측 시 컬럼 순서 보장)."""
    dummy = _empty_features(pd.Timestamp("2026-01-05"))
    return sorted(dummy.keys())
