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

from prepacking.services.prediction.pipeline.features import (
    compute_features_for_date,
    get_feature_names,
)

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
) -> dict[str, dict]:
    """
    ML 예측을 생성하여 통계 예측과 앙상블한다.

    Returns: {series_key: {"ml_qty": int, "stat_qty": int, "final_qty": int,
                           "ml_ship_prob": float, "model_used": str}}
    """
    feature_names = get_feature_names()
    train_X, train_y_cls, train_y_reg = [], [], []

    cutoff = td_ts - pd.Timedelta(days=1)

    # 학습 데이터 수집: 과거 8주의 같은 요일 데이터
    for series_key, series in sku_series_map.items():
        for w in range(2, 10):
            past_date = td_ts - pd.Timedelta(weeks=w)
            if past_date < series.index.min() + pd.Timedelta(days=14):
                continue

            feats = compute_features_for_date(series, past_date)
            feat_vec = [feats.get(fn, 0.0) for fn in feature_names]

            actual_val = float(series[past_date]) if past_date in series.index else 0.0
            train_X.append(feat_vec)
            train_y_cls.append(1 if actual_val > 0 else 0)
            train_y_reg.append(actual_val)

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

    # 예측 생성
    results: dict[str, dict] = {}

    for series_key, series in sku_series_map.items():
        feats = compute_features_for_date(series, td_ts)
        feat_vec = np.array([[feats.get(fn, 0.0) for fn in feature_names]])

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
