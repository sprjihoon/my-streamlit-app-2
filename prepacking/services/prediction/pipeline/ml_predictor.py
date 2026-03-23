"""
ml_predictor — ML 기반 SKU별 예측 (분류 + 회귀)
═══════════════════════════════════════════════════
Stage 1: 분류 — "이 SKU가 내일 출하될까?" (LightGBM/GBClassifier)
Stage 2: 회귀 — "출하된다면 몇 개?" (LightGBM/GBRegressor)

통계 예측과 앙상블하여 최종 예측을 생성한다.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor

_LIGHT_FEATURE_NAMES = [
    "lag_7", "lag_14", "wd_avg", "wd_ship_prob", "wd_count",
    "roll_mean_7", "roll_mean_14", "roll_ship_prob_7", "roll_ship_prob_14",
    "weekday", "is_monday", "is_friday", "trend_7d",
    "days_since_last_ship", "last_ship_qty",
]


def _light_features(series: pd.Series, as_of: pd.Timestamp) -> list[float]:
    """경량 피처 — 15개만 빠르게 계산."""
    cutoff = as_of - pd.Timedelta(days=1)
    hist = series[series.index <= cutoff]
    if hist.empty:
        return [0.0] * len(_LIGHT_FEATURE_NAMES)

    feats = {}
    # lag
    for lag in [7, 14]:
        d = as_of - pd.Timedelta(days=lag)
        feats[f"lag_{lag}"] = float(hist[d]) if d in hist.index else 0.0

    # weekday stats
    wd_vals = []
    for w in range(1, 7):
        d = as_of - pd.Timedelta(weeks=w)
        if d in hist.index:
            wd_vals.append(float(hist[d]))
        elif d >= hist.index.min():
            wd_vals.append(0.0)
    wd_active = [v for v in wd_vals if v > 0]
    feats["wd_avg"] = float(np.mean(wd_active)) if wd_active else 0.0
    feats["wd_ship_prob"] = len(wd_active) / max(len(wd_vals), 1) if wd_vals else 0.0
    feats["wd_count"] = float(len(wd_vals))

    # rolling
    for w in [7, 14]:
        window = hist.tail(w)
        feats[f"roll_mean_{w}"] = float(window.mean()) if len(window) > 0 else 0.0
        active = window[window > 0]
        feats[f"roll_ship_prob_{w}"] = len(active) / max(len(window), 1)

    # calendar
    feats["weekday"] = float(as_of.weekday())
    feats["is_monday"] = 1.0 if as_of.weekday() == 0 else 0.0
    feats["is_friday"] = 1.0 if as_of.weekday() == 4 else 0.0

    # trend
    r7 = hist.tail(7).mean() if len(hist) >= 7 else float(hist.mean())
    p7 = hist.iloc[-14:-7].mean() if len(hist) >= 14 else 0.0
    feats["trend_7d"] = (r7 / max(p7, 0.1)) if p7 > 0 else 1.0

    # recency
    active_hist = hist[hist > 0]
    if not active_hist.empty:
        feats["days_since_last_ship"] = float((as_of - active_hist.index[-1]).days)
        feats["last_ship_qty"] = float(active_hist.iloc[-1])
    else:
        feats["days_since_last_ship"] = 999.0
        feats["last_ship_qty"] = 0.0

    return [feats.get(fn, 0.0) for fn in _LIGHT_FEATURE_NAMES]

logger = logging.getLogger(__name__)

try:
    import lightgbm as lgb
    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False


def build_ml_predictions(
    sku_series_map: dict[str, pd.Series],
    td_ts: pd.Timestamp,
    stat_predictions: dict[str, int],
    max_train_skus: int = 30,
) -> dict[str, dict]:
    """
    ML 예측을 생성하여 통계 예측과 앙상블한다.
    속도를 위해 학습 SKU 수를 제한한다.
    """
    import time
    start_time = time.time()

    train_X, train_y_cls, train_y_reg = [], [], []

    # 활성 SKU만 선택 (최근 출하가 있는 것 우선)
    active_keys = sorted(
        sku_series_map.keys(),
        key=lambda k: float(sku_series_map[k].tail(30).sum()),
        reverse=True,
    )[:max_train_skus]

    # 학습 데이터: 최근 3주만 (속도 최적화)
    for series_key in active_keys:
        series = sku_series_map[series_key]
        for w in range(2, 5):
            past_date = td_ts - pd.Timedelta(weeks=w)
            if past_date < series.index.min() + pd.Timedelta(days=14):
                continue

            feat_vec = _light_features(series, past_date)
            actual_val = float(series[past_date]) if past_date in series.index else 0.0
            train_X.append(feat_vec)
            train_y_cls.append(1 if actual_val > 0 else 0)
            train_y_reg.append(actual_val)

        if time.time() - start_time > 8.0:
            logger.warning("ML training data collection timeout, using %d samples", len(train_X))
            break

    if len(train_X) < 20:
        return {}

    X_train = np.array(train_X)
    y_cls = np.array(train_y_cls)
    y_reg = np.array(train_y_reg)

    # Stage 1: 분류기 학습
    clf = _create_classifier()
    try:
        clf.fit(X_train, y_cls)
    except Exception as e:
        logger.warning("Classifier training failed: %s", e)
        return {}

    # Stage 2: 회귀기 학습 (출하가 있는 샘플만)
    ship_mask = y_reg > 0
    reg = None
    if ship_mask.sum() >= 10:
        reg = _create_regressor()
        try:
            reg.fit(X_train[ship_mask], y_reg[ship_mask])
        except Exception as e:
            logger.warning("Regressor training failed: %s", e)
            reg = None

    logger.info("ML trained: clf=%d samples, reg=%d samples, elapsed=%.1fs",
                len(train_X), int(ship_mask.sum()) if reg else 0, time.time() - start_time)

    # 예측 생성 (활성 SKU만)
    results: dict[str, dict] = {}

    for series_key in active_keys:
        series = sku_series_map[series_key]
        feat_vec = np.array([_light_features(series, td_ts)])

        # 분류: 출하 확률
        try:
            ml_ship_prob = float(clf.predict_proba(feat_vec)[0, 1])
        except Exception:
            ml_ship_prob = 0.0

        # 회귀: 수량 예측
        ml_qty = 0
        if ml_ship_prob >= 0.5 and reg is not None:
            try:
                ml_qty = max(0, int(round(reg.predict(feat_vec)[0])))
            except Exception:
                ml_qty = 0

        stat_qty = stat_predictions.get(series_key, 0)

        # 앙상블: 통계와 ML 결합
        final_qty, model_used = _ensemble(stat_qty, ml_qty, ml_ship_prob)

        results[series_key] = {
            "ml_qty": ml_qty,
            "stat_qty": stat_qty,
            "final_qty": final_qty,
            "ml_ship_prob": round(ml_ship_prob, 3),
            "model_used": model_used,
        }

    return results


def _ensemble(stat_qty: int, ml_qty: int, ml_ship_prob: float) -> tuple[int, str]:
    """통계 + ML 앙상블."""
    # ML이 "출하 안 함"이라고 확신하면 (prob < 0.3) → 통계도 0이면 0
    if ml_ship_prob < 0.3 and stat_qty == 0:
        return 0, "both_zero"

    # ML이 "출하 안 함"이라고 하는데 통계는 양수 → 통계 신뢰 (보수적)
    if ml_ship_prob < 0.3 and stat_qty > 0:
        return stat_qty, "stat_override"

    # ML이 "출하 함"이라고 하는데 통계는 0 → ML 신뢰 (새 패턴 감지)
    if ml_ship_prob >= 0.5 and stat_qty == 0 and ml_qty > 0:
        return ml_qty, "ml_detect"

    # 둘 다 양수 → 가중 평균 (통계 60%, ML 40%)
    if stat_qty > 0 and ml_qty > 0:
        blended = int(round(stat_qty * 0.6 + ml_qty * 0.4))
        return max(1, blended), "ensemble"

    # 통계만 양수
    if stat_qty > 0:
        return stat_qty, "stat_only"

    # ML만 양수
    if ml_qty > 0:
        return ml_qty, "ml_only"

    return 0, "zero"


def _create_classifier() -> Any:
    if _HAS_LGB:
        return lgb.LGBMClassifier(
            n_estimators=50,
            max_depth=4,
            learning_rate=0.1,
            min_child_samples=5,
            verbose=-1,
        )
    return GradientBoostingClassifier(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        min_samples_leaf=5,
    )


def _create_regressor() -> Any:
    if _HAS_LGB:
        return lgb.LGBMRegressor(
            n_estimators=50,
            max_depth=4,
            learning_rate=0.1,
            min_child_samples=5,
            verbose=-1,
        )
    return GradientBoostingRegressor(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        min_samples_leaf=5,
    )
