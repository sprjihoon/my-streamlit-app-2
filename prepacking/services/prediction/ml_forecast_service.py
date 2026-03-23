"""
ml_forecast_service — 답안지 기반 통합 ML 모델
───────────────────────────────────────────────
핵심: 전체 SKU/조합의 과거 출하 데이터를 답안지로 사용하여
하나의 GradientBoostingRegressor 모델을 학습.

- SKU별 개별 모델 X → 전체 통합 모델 1개
- 학습 데이터: 과거 60일 × 전체 SKU = 수만 건
- 학습 시간: 1~2초 (모델 1개)
- 캐싱: supplier+날짜 기준으로 캐시하여 재학습 방지
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from collections import defaultdict

import numpy as np

from prepacking.common.utils import normalize_sku_name, safe_int, safe_str
from prepacking.database import get_pp_connection

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, dict] = {}
TRAIN_DAYS = 60
MIN_SAMPLES = 30
FEATURE_NAMES = [
    "active_avg_14", "active_avg_30", "active_avg_60",
    "active_days_14", "active_days_30",
    "same_wd_avg", "same_wd_count",
    "last_qty", "max_14", "median_14",
    "frequency_ratio",
    "wd_0", "wd_1", "wd_2", "wd_3", "wd_4", "wd_5", "wd_6",
]


def _load_all_sku_daily(supplier_name: str, date_from: str, date_to: str) -> dict[str, dict[str, int]]:
    """
    supplier의 전체 SKU별 일별 출하량을 로드.
    반환: { "상품명||옵션명": { "2026-01-05": 10, ... }, ... }
    """
    with get_pp_connection() as con:
        rows = con.execute(
            """
            SELECT shipping_date, product_name, option_name, qty
            FROM pp_shipping_stats
            WHERE TRIM(supplier_name) = TRIM(?)
              AND shipping_date IS NOT NULL AND shipping_date != ''
              AND date(shipping_date) >= date(?)
              AND date(shipping_date) <= date(?)
            """,
            (supplier_name.strip(), date_from, date_to),
        ).fetchall()

    result: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        ds = safe_str(row[0])[:10]
        pn = normalize_sku_name(row[1])
        on = normalize_sku_name(row[2])
        qty = max(1, safe_int(row[3], 1))
        key = f"{pn}||{on}"
        result[key][ds] += qty

    return dict(result)


def _compute_features(daily: dict[str, int], td: dt.date) -> dict[str, float]:
    """하나의 SKU에 대해 td 시점의 피처를 계산."""

    def _active_avg(days: int) -> tuple[float, int]:
        vals = []
        for i in range(1, days + 1):
            d = td - dt.timedelta(days=i)
            v = daily.get(d.isoformat(), 0)
            if v > 0:
                vals.append(float(v))
        return (sum(vals) / len(vals) if vals else 0.0), len(vals)

    def _same_wd() -> tuple[float, int]:
        nonzero = []
        for w in range(1, 9):
            past_d = td - dt.timedelta(weeks=w)
            v = daily.get(past_d.isoformat(), 0)
            if v > 0:
                nonzero.append(float(v))
        avg = sum(nonzero) / len(nonzero) if nonzero else 0.0
        return avg, len(nonzero)

    avg_14, active_14 = _active_avg(14)
    avg_30, active_30 = _active_avg(30)
    avg_60, _ = _active_avg(60)
    wd_avg, wd_count = _same_wd()

    recent_14_vals = []
    for i in range(1, 15):
        d = td - dt.timedelta(days=i)
        v = daily.get(d.isoformat(), 0)
        if v > 0:
            recent_14_vals.append(float(v))

    last_qty = 0.0
    for i in range(1, 31):
        d = td - dt.timedelta(days=i)
        v = daily.get(d.isoformat(), 0)
        if v > 0:
            last_qty = float(v)
            break

    max_14 = max(recent_14_vals) if recent_14_vals else 0.0
    median_14 = float(np.median(recent_14_vals)) if recent_14_vals else 0.0

    total_days_in_range = len(daily)
    active_total = len([v for v in daily.values() if v > 0])
    freq_ratio = active_total / max(total_days_in_range, 1)

    wd = td.weekday()
    wd_onehot = [1.0 if j == wd else 0.0 for j in range(7)]

    features = {
        "active_avg_14": avg_14,
        "active_avg_30": avg_30,
        "active_avg_60": avg_60,
        "active_days_14": float(active_14),
        "active_days_30": float(active_30),
        "same_wd_avg": wd_avg,
        "same_wd_count": float(wd_count),
        "last_qty": last_qty,
        "max_14": max_14,
        "median_14": median_14,
        "frequency_ratio": freq_ratio,
    }
    for j, v in enumerate(wd_onehot):
        features[f"wd_{j}"] = v

    return features


def _build_training_data(
    all_sku_daily: dict[str, dict[str, int]],
    target_date: str,
    train_days: int = TRAIN_DAYS,
) -> tuple[np.ndarray, np.ndarray]:
    """
    과거 train_days일에 대해 전체 SKU의 (피처, 실제출하량) 쌍을 생성.
    답안지 = 각 날짜의 실제 출하량.
    """
    td = dt.datetime.strptime(target_date[:10], "%Y-%m-%d").date()

    X_rows = []
    y_rows = []
    max_samples = 10000

    for day_offset in range(1, train_days + 1):
        train_date = td - dt.timedelta(days=day_offset)

        for sku_key, daily in all_sku_daily.items():
            actual_qty = daily.get(train_date.isoformat(), 0)
            if actual_qty <= 0:
                continue

            features = _compute_features(daily, train_date)
            if features["active_avg_14"] <= 0 and features["active_avg_30"] <= 0 and features["same_wd_avg"] <= 0:
                continue

            row = [features.get(n, 0.0) for n in FEATURE_NAMES]
            X_rows.append(row)
            y_rows.append(float(actual_qty))

            if len(X_rows) >= max_samples:
                break
        if len(X_rows) >= max_samples:
            break

    if not X_rows:
        return np.array([]), np.array([])

    return np.array(X_rows, dtype=float), np.array(y_rows, dtype=float)


def train_and_predict(
    supplier_name: str,
    target_date: str,
    sku_daily_map: dict[str, dict[str, int]],
) -> dict[str, int]:
    """
    통합 모델을 학습하고, 각 SKU에 대해 예측값을 반환.
    반환: { "상품명||옵션명": predicted_qty, ... }
    캐시 키: supplier + target_date
    """
    cache_key = f"{supplier_name}||{target_date}"

    cached = _MODEL_CACHE.get(cache_key)
    if cached and cached.get("predictions"):
        return cached["predictions"]

    td = dt.datetime.strptime(target_date[:10], "%Y-%m-%d").date()

    if sku_daily_map:
        all_sku_daily = {k: v for k, v in sku_daily_map.items()}
    else:
        data_end = (td - dt.timedelta(days=1)).isoformat()
        data_start = (td - dt.timedelta(days=120)).isoformat()
        all_sku_daily = _load_all_sku_daily(supplier_name, data_start, data_end)

    if not all_sku_daily:
        return {}

    t_start = time.time()
    MAX_TOTAL_SECONDS = 15

    X_train, y_train = _build_training_data(all_sku_daily, target_date, TRAIN_DAYS)
    t_build = time.time() - t_start

    if t_build > MAX_TOTAL_SECONDS:
        logger.warning("ML: build took %.1fs, skipping for %s", t_build, supplier_name)
        return {}

    if len(X_train) < MIN_SAMPLES:
        logger.info("ML: insufficient training data (%d samples) for %s", len(X_train), supplier_name)
        return {}

    try:
        from sklearn.ensemble import GradientBoostingRegressor

        t0 = time.time()
        model = GradientBoostingRegressor(
            n_estimators=80,
            max_depth=3,
            learning_rate=0.1,
            min_samples_leaf=3,
            subsample=0.8,
            random_state=42,
        )
        model.fit(X_train, y_train)
        t_train = time.time() - t0

        y_pred_train = model.predict(X_train)
        mae = float(np.mean(np.abs(y_train - y_pred_train)))
        mean_y = float(np.mean(y_train))
        train_accuracy = max(0.0, 1.0 - mae / max(mean_y, 1.0))

        logger.info(
            "ML trained: %s | samples=%d | accuracy=%.1f%% | build=%.2fs | train=%.2fs",
            supplier_name, len(X_train), train_accuracy * 100, t_build, t_train,
        )

    except Exception as exc:
        logger.warning("ML training failed for %s: %s", supplier_name, exc)
        return {}

    predictions: dict[str, int] = {}
    for sku_key, daily in sku_daily_map.items():
        features = _compute_features(daily, td)
        row = np.array([[features.get(n, 0.0) for n in FEATURE_NAMES]], dtype=float)
        pred_val = float(model.predict(row)[0])
        predictions[sku_key] = max(0, int(round(pred_val)))

    _MODEL_CACHE[cache_key] = {
        "predictions": predictions,
        "train_samples": len(X_train),
        "train_accuracy": round(train_accuracy, 3),
    }

    if len(_MODEL_CACHE) > 10:
        oldest = next(iter(_MODEL_CACHE))
        del _MODEL_CACHE[oldest]

    return predictions


def get_model_info(supplier_name: str, target_date: str) -> dict:
    cache_key = f"{supplier_name}||{target_date}"
    cached = _MODEL_CACHE.get(cache_key, {})
    return {
        "trained": bool(cached),
        "train_samples": cached.get("train_samples", 0),
        "train_accuracy": cached.get("train_accuracy", 0),
    }
