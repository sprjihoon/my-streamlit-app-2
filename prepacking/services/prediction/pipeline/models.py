"""
models — ML 모델 (LightGBM → GBR 폴백)
──────────────────────────────────────────
1. LightGBM 우선 시도 (설치되어 있으면)
2. 없으면 sklearn GradientBoostingRegressor 폴백
3. 모든 모델은 walk-forward validation에서 baseline을 이겨야만 사용

Stacking은 out-of-fold 기반으로만 구현.
"""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


def _try_lightgbm():
    try:
        import lightgbm as lgb
        return lgb
    except ImportError:
        return None


def create_gbr_model():
    """sklearn GradientBoostingRegressor — LightGBM 없을 때 폴백."""
    from sklearn.ensemble import GradientBoostingRegressor
    return GradientBoostingRegressor(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        min_samples_leaf=5,
        subsample=0.8,
        random_state=42,
    )


def create_lgbm_model():
    """LightGBM Regressor — 가능하면 우선 사용."""
    lgb = _try_lightgbm()
    if lgb is None:
        logger.info("LightGBM not available, falling back to GBR")
        return create_gbr_model()
    return lgb.LGBMRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        min_child_samples=10,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        random_state=42,
        verbose=-1,
    )


def create_best_model():
    """사용 가능한 최선의 단일 모델을 반환."""
    lgb = _try_lightgbm()
    if lgb is not None:
        return create_lgbm_model()
    return create_gbr_model()


class OutOfFoldStacker:
    """
    Out-of-fold 기반 스태킹.
    base_models: list of model factories
    meta_model: model factory for 2nd level

    반드시 walk-forward 내에서 사용.
    base 모델이 각각 baseline을 이긴 후에만 사용할 것.
    """

    def __init__(self, base_factories: list, meta_factory=None):
        self.base_factories = base_factories
        self.meta_factory = meta_factory or (lambda: create_gbr_model())
        self.base_models = []
        self.meta_model = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        n = len(X)
        n_bases = len(self.base_factories)
        oof_preds = np.zeros((n, n_bases))

        from sklearn.model_selection import TimeSeriesSplit
        tscv = TimeSeriesSplit(n_splits=3)

        self.base_models = []
        for i, factory in enumerate(self.base_factories):
            model = factory()
            for train_idx, val_idx in tscv.split(X):
                fold_model = factory()
                fold_model.fit(X[train_idx], y[train_idx])
                oof_preds[val_idx, i] = np.maximum(0, fold_model.predict(X[val_idx]))
            model.fit(X, y)
            self.base_models.append(model)

        self.meta_model = self.meta_factory()
        self.meta_model.fit(oof_preds, y)

    def predict(self, X: np.ndarray) -> np.ndarray:
        base_preds = np.column_stack([
            np.maximum(0, m.predict(X)) for m in self.base_models
        ])
        return np.maximum(0, self.meta_model.predict(base_preds))
