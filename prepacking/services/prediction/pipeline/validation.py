"""
validation — Walk-Forward Validation (시간순 검증)
──────────────────────────────────────────────────
절대 랜덤 split을 사용하지 않는다.
시간순으로 과거 → 미래 방향으로 검증.

Walk-forward:
  for each test_date in test_dates:
    train on data < test_date
    predict test_date
    record (actual, predicted)
"""
from __future__ import annotations

import datetime as dt
import logging
import time

import numpy as np
import pandas as pd

from prepacking.services.prediction.pipeline.features import compute_features_for_date, get_feature_names
from prepacking.services.prediction.pipeline.metrics import compute_all_metrics, segment_analysis
from prepacking.services.prediction.pipeline.baselines import get_all_baselines

logger = logging.getLogger(__name__)


def walk_forward_validate(
    daily_df: pd.DataFrame,
    test_start: str,
    test_end: str,
    model_factory=None,
    train_min_days: int = 30,
    max_skus: int = 200,
) -> dict:
    """
    Walk-forward validation.

    daily_df: columns [date, sku_key, qty] — 전체 데이터
    test_start/end: 테스트 기간
    model_factory: callable() -> model with .fit(X, y) and .predict(X)
    train_min_days: 최소 학습 기간
    max_skus: 성능을 위한 SKU 수 제한 (출하 빈도 상위)

    반환: {
        "model_metrics": {...},
        "baseline_metrics": {name: {...}},
        "segment_analysis": {...},
        "per_date_results": [...],
        "summary": str,
    }
    """
    t_start_dt = pd.Timestamp(test_start)
    t_end_dt = pd.Timestamp(test_end)

    top_skus = (
        daily_df[daily_df["qty"] > 0]
        .groupby("sku_key")["qty"]
        .count()
        .nlargest(max_skus)
        .index.tolist()
    )
    df = daily_df[daily_df["sku_key"].isin(top_skus)].copy()

    test_dates = pd.date_range(t_start_dt, t_end_dt, freq="D")
    feature_names = get_feature_names()
    baselines = get_all_baselines()

    all_actual = []
    all_pred_model = []
    all_pred_baselines = {b.name: [] for b in baselines}
    per_date_results = []

    t0 = time.time()

    for test_date in test_dates:
        train_cutoff = test_date - pd.Timedelta(days=1)
        train_start = train_cutoff - pd.Timedelta(days=train_min_days)

        if df[df["date"] <= train_cutoff]["date"].nunique() < train_min_days:
            continue

        X_train_rows = []
        y_train_rows = []
        X_test_rows = []
        y_test_rows = []
        test_sku_keys = []

        for sku_key in top_skus:
            sku_data = df[df["sku_key"] == sku_key].set_index("date")["qty"]
            if sku_data.empty:
                continue

            actual_val = float(sku_data.get(test_date, 0))

            test_features = compute_features_for_date(sku_data, test_date)
            X_test_rows.append([test_features.get(f, 0.0) for f in feature_names])
            y_test_rows.append(actual_val)
            test_sku_keys.append(sku_key)

            for bl in baselines:
                pred = bl.predict(sku_data, test_date)
                all_pred_baselines[bl.name].append(max(0, pred))

            all_actual.append(actual_val)

            train_dates_for_sku = sku_data[
                (sku_data.index >= train_start) & (sku_data.index <= train_cutoff)
            ]
            for td_train in train_dates_for_sku.index:
                feat = compute_features_for_date(sku_data, td_train)
                X_train_rows.append([feat.get(f, 0.0) for f in feature_names])
                y_train_rows.append(float(sku_data.get(td_train, 0)))

        if not X_train_rows or not X_test_rows:
            continue

        X_train = np.array(X_train_rows, dtype=float)
        y_train = np.array(y_train_rows, dtype=float)
        X_test = np.array(X_test_rows, dtype=float)
        y_test = np.array(y_test_rows, dtype=float)

        if model_factory is not None:
            model = model_factory()
            model.fit(X_train, y_train)
            y_pred = np.maximum(0, model.predict(X_test))
        else:
            y_pred = np.zeros(len(y_test))

        all_pred_model.extend(y_pred.tolist())

        date_actual_sum = float(y_test.sum())
        date_pred_sum = float(y_pred.sum())
        per_date_results.append({
            "date": test_date.strftime("%Y-%m-%d"),
            "actual_total": date_actual_sum,
            "predicted_total": date_pred_sum,
            "error": abs(date_actual_sum - date_pred_sum),
        })

    elapsed = time.time() - t0

    y_true = np.array(all_actual)
    y_pred_m = np.array(all_pred_model)

    model_metrics = compute_all_metrics(y_true, y_pred_m) if len(y_true) > 0 else {}
    baseline_results = {}
    for bl in baselines:
        y_bl = np.array(all_pred_baselines[bl.name])
        if len(y_bl) == len(y_true):
            baseline_results[bl.name] = compute_all_metrics(y_true, y_bl)

    seg = segment_analysis(y_true, y_pred_m) if len(y_true) > 0 else {}

    best_baseline_name = ""
    best_baseline_mae = float("inf")
    for name, m in baseline_results.items():
        if m["MAE"] < best_baseline_mae:
            best_baseline_mae = m["MAE"]
            best_baseline_name = name

    model_beats_baseline = (
        model_metrics.get("MAE", float("inf")) < best_baseline_mae
        if model_metrics
        else False
    )

    summary_lines = [
        f"Walk-forward validation: {test_start} ~ {test_end}",
        f"SKUs tested: {len(top_skus)}, Test dates: {len(per_date_results)}",
        f"Elapsed: {elapsed:.1f}s",
        "",
        "=== Model ===",
        f"  {model_metrics}" if model_metrics else "  (no model)",
        "",
        "=== Baselines ===",
    ]
    for name, m in baseline_results.items():
        marker = " ★ BEST" if name == best_baseline_name else ""
        summary_lines.append(f"  {name}: {m}{marker}")

    summary_lines.append("")
    if model_beats_baseline:
        summary_lines.append(f"✓ Model beats best baseline ({best_baseline_name})")
    else:
        summary_lines.append(f"✗ Model DOES NOT beat best baseline ({best_baseline_name}, MAE={best_baseline_mae:.2f})")

    return {
        "model_metrics": model_metrics,
        "baseline_metrics": baseline_results,
        "best_baseline": best_baseline_name,
        "model_beats_baseline": model_beats_baseline,
        "segment_analysis": seg,
        "per_date_results": per_date_results,
        "summary": "\n".join(summary_lines),
        "elapsed_seconds": round(elapsed, 1),
    }
