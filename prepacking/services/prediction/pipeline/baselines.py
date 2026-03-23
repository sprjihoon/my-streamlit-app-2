"""
baselines — Baseline 예측 모델
──────────────────────────────
모든 baseline은 as_of_date 기준 과거 데이터만 사용.
ML 모델은 이 baseline들을 이겨야만 의미가 있다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class NaiveLastValue:
    """직전 출하일의 수량을 그대로 예측."""
    name = "naive_last"

    def predict(self, hist: pd.Series, as_of_date: pd.Timestamp) -> float:
        cutoff = as_of_date - pd.Timedelta(days=1)
        past = hist[hist.index <= cutoff]
        active = past[past > 0]
        if active.empty:
            return 0.0
        return float(active.iloc[-1])


class SeasonalNaive:
    """7일 전 (같은 요일) 값을 예측."""
    name = "seasonal_naive_7d"

    def predict(self, hist: pd.Series, as_of_date: pd.Timestamp) -> float:
        target = as_of_date - pd.Timedelta(days=7)
        if target in hist.index:
            return float(hist[target])
        return 0.0


class RollingMean7:
    """최근 7일 평균."""
    name = "rolling_mean_7d"

    def predict(self, hist: pd.Series, as_of_date: pd.Timestamp) -> float:
        cutoff = as_of_date - pd.Timedelta(days=1)
        start = cutoff - pd.Timedelta(days=6)
        w = hist[(hist.index >= start) & (hist.index <= cutoff)]
        return float(w.mean()) if len(w) > 0 else 0.0


class SameWeekdayMean:
    """같은 요일 최근 4주 평균."""
    name = "same_weekday_mean_4w"

    def predict(self, hist: pd.Series, as_of_date: pd.Timestamp) -> float:
        vals = []
        for w in range(1, 5):
            d = as_of_date - pd.Timedelta(weeks=w)
            if d in hist.index:
                vals.append(float(hist[d]))
        return np.mean(vals) if vals else 0.0


class ShipProbAdjustedMean:
    """
    출하 확률 반영 평균 — 가장 강력한 baseline.
    같은 요일 출하 확률 × 출하일 평균 수량.
    """
    name = "ship_prob_adjusted"

    def predict(self, hist: pd.Series, as_of_date: pd.Timestamp) -> float:
        cutoff = as_of_date - pd.Timedelta(days=1)
        past = hist[hist.index <= cutoff]

        wd_vals = []
        for w in range(1, 9):
            d = as_of_date - pd.Timedelta(weeks=w)
            if d in past.index:
                wd_vals.append(float(past[d]))

        if not wd_vals:
            return 0.0

        ship_prob = len([v for v in wd_vals if v > 0]) / len(wd_vals)
        active_vals = [v for v in wd_vals if v > 0]
        active_mean = np.mean(active_vals) if active_vals else 0.0

        return float(active_mean * ship_prob)


def get_all_baselines() -> list:
    return [
        NaiveLastValue(),
        SeasonalNaive(),
        RollingMean7(),
        SameWeekdayMean(),
        ShipProbAdjustedMean(),
    ]
