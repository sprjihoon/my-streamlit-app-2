"""
ML 기반 예측 서비스
─────────────────
GradientBoostingRegressor를 사용하여 SKU/조합별 수요를 예측.
특성(feature):
  - 같은 요일 과거 N주 출하량
  - 최근 7/14/30일 이동평균
  - 요일 원핫
  - 추세(선형 기울기)
  - 변동성(CV)
통계 폴백: ML 학습 데이터가 부족하면 기존 가중이동평균으로 폴백.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
from collections import defaultdict

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, object] = {}

WEEKS_BACK = 12
MIN_TRAIN_POINTS = 4


def _parse_date(s: str) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _build_daily_series(daily: dict[str, int], end_date: dt.date, lookback: int) -> list[tuple[dt.date, int]]:
    """날짜순 (date, qty) 리스트 생성."""
    start = end_date - dt.timedelta(days=lookback)
    series = []
    d = start
    while d < end_date:
        series.append((d, daily.get(d.isoformat(), 0)))
        d += dt.timedelta(days=1)
    return series


def _extract_features(series: list[tuple[dt.date, int]], target_date: dt.date) -> list[dict]:
    """학습/예측용 feature 행 생성. 각 날짜에 대해 feature dict를 만든다."""
    if not series:
        return []

    daily_map: dict[str, int] = {d.isoformat(): q for d, q in series}
    rows = []

    for i, (d, qty) in enumerate(series):
        if i < 14:
            continue

        wd = d.weekday()
        wd_onehot = [1.0 if j == wd else 0.0 for j in range(7)]

        same_wd_vals = []
        for w in range(1, WEEKS_BACK + 1):
            past_d = d - dt.timedelta(weeks=w)
            same_wd_vals.append(float(daily_map.get(past_d.isoformat(), 0)))

        recent_7 = [float(daily_map.get((d - dt.timedelta(days=k)).isoformat(), 0)) for k in range(1, 8)]
        recent_14 = [float(daily_map.get((d - dt.timedelta(days=k)).isoformat(), 0)) for k in range(1, 15)]
        recent_30 = [float(daily_map.get((d - dt.timedelta(days=k)).isoformat(), 0)) for k in range(1, min(31, i + 1))]

        avg_7 = sum(recent_7) / 7.0
        avg_14 = sum(recent_14) / 14.0
        avg_30 = sum(recent_30) / max(1, len(recent_30))

        avg_same_wd = sum(same_wd_vals) / max(1, len([v for v in same_wd_vals if v > 0])) if any(v > 0 for v in same_wd_vals) else 0.0

        if len(recent_7) > 1 and avg_7 > 0:
            cv_7 = float(np.std(recent_7)) / avg_7
        else:
            cv_7 = 0.0

        trend_vals = recent_14[::-1]
        if len(trend_vals) >= 3:
            x = np.arange(len(trend_vals), dtype=float)
            y = np.array(trend_vals, dtype=float)
            if np.std(x) > 0:
                slope = float(np.polyfit(x, y, 1)[0])
            else:
                slope = 0.0
        else:
            slope = 0.0

        features = {
            "avg_7": avg_7,
            "avg_14": avg_14,
            "avg_30": avg_30,
            "avg_same_wd": avg_same_wd,
            "cv_7": min(cv_7, 3.0),
            "trend_slope": slope,
            "same_wd_1w": same_wd_vals[0] if same_wd_vals else 0.0,
            "same_wd_2w": same_wd_vals[1] if len(same_wd_vals) > 1 else 0.0,
            "same_wd_3w": same_wd_vals[2] if len(same_wd_vals) > 2 else 0.0,
            "same_wd_4w": same_wd_vals[3] if len(same_wd_vals) > 3 else 0.0,
        }
        for j, v in enumerate(wd_onehot):
            features[f"wd_{j}"] = v

        rows.append({"date": d, "qty": qty, "features": features})

    return rows


def _feature_names() -> list[str]:
    return [
        "avg_7", "avg_14", "avg_30", "avg_same_wd",
        "cv_7", "trend_slope",
        "same_wd_1w", "same_wd_2w", "same_wd_3w", "same_wd_4w",
        "wd_0", "wd_1", "wd_2", "wd_3", "wd_4", "wd_5", "wd_6",
    ]


def _rows_to_xy(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    names = _feature_names()
    X = np.array([[r["features"].get(n, 0.0) for n in names] for r in rows], dtype=float)
    y = np.array([r["qty"] for r in rows], dtype=float)
    return X, y


def predict_ml(
    daily: dict[str, int],
    target_date: str,
    frequency: int,
    cache_key: str = "",
) -> dict:
    """
    ML 예측. 반환:
      {"predicted_qty": int, "model_type": str, "confidence_boost": float}
    model_type: "ml" | "statistical" (폴백)
    """
    td = _parse_date(target_date)
    if td is None:
        return {"predicted_qty": 0, "model_type": "error", "confidence_boost": 0.0}

    lookback = max(WEEKS_BACK * 7 + 45, 120)
    series = _build_daily_series(daily, td, lookback)

    feature_rows = _extract_features(series, td)

    if len(feature_rows) < MIN_TRAIN_POINTS:
        return _fallback_statistical(daily, td, frequency)

    train_rows = feature_rows
    X_train, y_train = _rows_to_xy(train_rows)

    nonzero_count = int(np.count_nonzero(y_train))
    if nonzero_count < MIN_TRAIN_POINTS:
        return _fallback_statistical(daily, td, frequency)

    try:
        from sklearn.ensemble import GradientBoostingRegressor

        model = GradientBoostingRegressor(
            n_estimators=80,
            max_depth=3,
            learning_rate=0.1,
            min_samples_leaf=2,
            subsample=0.8,
            random_state=42,
        )
        model.fit(X_train, y_train)

        target_row = _build_target_features(daily, td)
        if target_row is None:
            return _fallback_statistical(daily, td, frequency)

        names = _feature_names()
        X_pred = np.array([[target_row.get(n, 0.0) for n in names]], dtype=float)
        pred_val = float(model.predict(X_pred)[0])

        y_pred_train = model.predict(X_train)
        residuals = y_train - y_pred_train
        mae = float(np.mean(np.abs(residuals)))
        mean_y = float(np.mean(y_train)) if len(y_train) > 0 else 1.0
        mape = mae / max(mean_y, 1.0)
        accuracy = max(0.0, 1.0 - mape)

        pred_qty = max(0, int(round(pred_val)))

        confidence_boost = min(0.2, accuracy * 0.25)

        return {
            "predicted_qty": pred_qty,
            "model_type": "ml",
            "confidence_boost": round(confidence_boost, 3),
            "train_accuracy": round(accuracy, 3),
            "train_mae": round(mae, 2),
            "train_samples": len(y_train),
        }

    except Exception as exc:
        logger.warning("ML prediction failed, falling back: %s", exc)
        return _fallback_statistical(daily, td, frequency)


def _build_target_features(daily: dict[str, int], td: dt.date) -> dict | None:
    """예측 대상 날짜의 feature dict 생성."""
    daily_map = daily
    wd = td.weekday()
    wd_onehot = [1.0 if j == wd else 0.0 for j in range(7)]

    same_wd_vals = []
    for w in range(1, WEEKS_BACK + 1):
        past_d = td - dt.timedelta(weeks=w)
        same_wd_vals.append(float(daily_map.get(past_d.isoformat(), 0)))

    recent_7 = [float(daily_map.get((td - dt.timedelta(days=k)).isoformat(), 0)) for k in range(1, 8)]
    recent_14 = [float(daily_map.get((td - dt.timedelta(days=k)).isoformat(), 0)) for k in range(1, 15)]
    recent_30 = [float(daily_map.get((td - dt.timedelta(days=k)).isoformat(), 0)) for k in range(1, 31)]

    avg_7 = sum(recent_7) / 7.0
    avg_14 = sum(recent_14) / 14.0
    avg_30 = sum(recent_30) / max(1, len(recent_30))
    avg_same_wd = sum(same_wd_vals) / max(1, len([v for v in same_wd_vals if v > 0])) if any(v > 0 for v in same_wd_vals) else 0.0

    cv_7 = (float(np.std(recent_7)) / avg_7) if avg_7 > 0 else 0.0

    trend_vals = recent_14[::-1]
    if len(trend_vals) >= 3:
        x = np.arange(len(trend_vals), dtype=float)
        y = np.array(trend_vals, dtype=float)
        slope = float(np.polyfit(x, y, 1)[0]) if np.std(x) > 0 else 0.0
    else:
        slope = 0.0

    features = {
        "avg_7": avg_7,
        "avg_14": avg_14,
        "avg_30": avg_30,
        "avg_same_wd": avg_same_wd,
        "cv_7": min(cv_7, 3.0),
        "trend_slope": slope,
        "same_wd_1w": same_wd_vals[0] if same_wd_vals else 0.0,
        "same_wd_2w": same_wd_vals[1] if len(same_wd_vals) > 1 else 0.0,
        "same_wd_3w": same_wd_vals[2] if len(same_wd_vals) > 2 else 0.0,
        "same_wd_4w": same_wd_vals[3] if len(same_wd_vals) > 3 else 0.0,
    }
    for j, v in enumerate(wd_onehot):
        features[f"wd_{j}"] = v

    return features


def _fallback_statistical(daily: dict[str, int], td: dt.date, frequency: int) -> dict:
    """일평균 기반 폴백 (같은 요일만 보지 않고 전체 최근 데이터 활용)."""
    avg_7 = sum(daily.get((td - dt.timedelta(days=i)).isoformat(), 0) for i in range(1, 8)) / 7.0
    avg_14 = sum(daily.get((td - dt.timedelta(days=i)).isoformat(), 0) for i in range(1, 15)) / 14.0

    same_wd_vals = []
    for w in range(1, 9):
        past_d = td - dt.timedelta(weeks=w)
        same_wd_vals.append(float(daily.get(past_d.isoformat(), 0)))
    same_wd_nonzero = [v for v in same_wd_vals if v > 0]
    avg_same_wd = sum(same_wd_vals) / len(same_wd_vals) if same_wd_vals else 0.0

    signals: list[tuple[float, float]] = []
    if avg_7 > 0:
        signals.append((avg_7, 3.0))
    if avg_14 > 0:
        signals.append((avg_14, 2.0))
    if avg_same_wd > 0:
        signals.append((avg_same_wd, 2.0))

    if not signals:
        total_qty = sum(daily.values())
        active = len([v for v in daily.values() if v > 0])
        if active > 0:
            pred = total_qty / active
        else:
            pred = 0.0
        return {
            "predicted_qty": max(0, int(round(pred))),
            "model_type": "statistical",
            "confidence_boost": 0.0,
        }

    total_w = sum(w for _, w in signals)
    pred = sum(v * w for v, w in signals) / total_w

    return {
        "predicted_qty": max(0, int(round(pred))),
        "model_type": "statistical",
        "confidence_boost": 0.0,
    }
