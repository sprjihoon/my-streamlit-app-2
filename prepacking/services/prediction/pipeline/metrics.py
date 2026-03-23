"""
metrics — 시계열 예측 평가 메트릭
─────────────────────────────────
MAE, RMSE, WAPE, sMAPE + 구간별 오차 분석.
"""
from __future__ import annotations

import numpy as np


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Weighted Absolute Percentage Error — 총합 기준."""
    total = np.sum(np.abs(y_true))
    if total == 0:
        return 0.0
    return float(np.sum(np.abs(y_true - y_pred)) / total * 100)


def smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Symmetric Mean Absolute Percentage Error."""
    denom = np.abs(y_true) + np.abs(y_pred)
    mask = denom > 0
    if not mask.any():
        return 0.0
    return float(np.mean(2 * np.abs(y_true[mask] - y_pred[mask]) / denom[mask]) * 100)


def compute_all_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    return {
        "MAE": round(mae(y_true, y_pred), 2),
        "RMSE": round(rmse(y_true, y_pred), 2),
        "WAPE": round(wape(y_true, y_pred), 1),
        "sMAPE": round(smape(y_true, y_pred), 1),
    }


def segment_analysis(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    segments: dict[str, tuple[float, float]] | None = None,
) -> dict[str, dict]:
    """
    구간별 오차 분석.
    segments: {"zero": (0, 0), "low": (1, 10), "mid": (11, 50), "high": (51, inf)}
    """
    if segments is None:
        segments = {
            "zero (actual=0)": (0, 0),
            "low (1-10)": (1, 10),
            "mid (11-50)": (11, 50),
            "high (51+)": (51, float("inf")),
        }

    result = {}
    for name, (lo, hi) in segments.items():
        if hi == 0:
            mask = y_true == 0
        elif hi == float("inf"):
            mask = y_true >= lo
        else:
            mask = (y_true >= lo) & (y_true <= hi)

        n = int(mask.sum())
        if n == 0:
            result[name] = {"count": 0, "MAE": 0, "RMSE": 0}
            continue

        result[name] = {
            "count": n,
            **compute_all_metrics(y_true[mask], y_pred[mask]),
        }

    return result
