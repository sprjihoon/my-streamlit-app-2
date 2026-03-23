"""
predictor — 2단계 예측기 (Classification → Regression)
──────────────────────────────────────────────────────
1단계: 출하 여부 분류 (이 SKU가 오늘 출하되는가?)
2단계: 출하 시 수량 예측 (출하된다면 몇 개?)

이렇게 하면 실제 0인 SKU에 양수를 예측하는 과다예측을 방지.
"""
from __future__ import annotations

import datetime as dt
import logging
import time

import numpy as np
import pandas as pd

from prepacking.services.prediction.pipeline.features import compute_features_for_date, get_feature_names
from prepacking.services.prediction.pipeline.baselines import ShipProbAdjustedMean

logger = logging.getLogger(__name__)

_TRAINED_CACHE: dict[str, dict] = {}
MAX_CACHE = 5

SHIP_PROB_THRESHOLD = 0.3


def predict_for_date(
    supplier_name: str,
    target_date: str,
    weeks_back: int = 8,
    use_gpt: bool = False,
) -> list[dict]:
    from prepacking.common.utils import normalize_sku_name
    from prepacking.services.analysis import repeat_sku_service, repeat_combination_service
    from prepacking.services.analysis import weekday_pattern_service
    from prepacking.services.prediction import confidence_service

    try:
        td = dt.datetime.strptime(target_date[:10], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        td = dt.date.today()

    td_ts = pd.Timestamp(td)
    lookback_days = max(weeks_back * 7 + 45, 120)
    wb = weekday_pattern_service.weekday_basis_for(target_date)

    skus = repeat_sku_service.load_repeat_sku_daily_totals(
        supplier_name, target_date, lookback_days
    )
    combos = repeat_combination_service.load_repeat_combo_daily_totals(
        supplier_name, target_date, lookback_days
    )

    all_rows: list[tuple[str, dict]] = []
    sku_series_map: dict[str, pd.Series] = {}

    for row in skus:
        all_rows.append(("single_sku", row))
        pn = normalize_sku_name(row.get("target_code", ""))
        on = normalize_sku_name(row.get("option_name", ""))
        key = f"{pn}||{on}"
        daily = row.get("daily", {})
        if daily:
            s = pd.Series(
                {pd.Timestamp(k): int(v) for k, v in daily.items()},
                dtype=float,
            ).sort_index()
            sku_series_map[key] = s

    for row in combos:
        all_rows.append(("combination", row))
        ckey = row.get("combination_key", "")
        daily = row.get("daily", {})
        if daily:
            s = pd.Series(
                {pd.Timestamp(k): int(v) for k, v in daily.items()},
                dtype=float,
            ).sort_index()
            sku_series_map[f"combo||{ckey}"] = s

    clf_model, reg_model, model_info = _get_or_train_models(
        supplier_name, target_date, sku_series_map
    )
    feature_names = get_feature_names()
    baseline = ShipProbAdjustedMean()

    out: list[dict] = []

    for target_type, row in all_rows:
        if target_type == "combination":
            ckey = row.get("combination_key", "")
            series_key = f"combo||{ckey}"
        else:
            pn = normalize_sku_name(row.get("target_code", ""))
            on = normalize_sku_name(row.get("option_name", ""))
            series_key = f"{pn}||{on}"

        series = sku_series_map.get(series_key)
        if series is None or series.empty:
            continue

        bl_qty = max(0, int(round(baseline.predict(series, td_ts))))

        feat = compute_features_for_date(series, td_ts)
        X = np.array([[feat.get(f, 0.0) for f in feature_names]], dtype=float)

        ml_qty = 0
        model_used = "statistical"
        ship_prob_ml = feat.get("wd_ship_prob", 0)

        if clf_model is not None and reg_model is not None:
            ship_prob_ml = float(clf_model.predict_proba(X)[0][1])

            if ship_prob_ml >= SHIP_PROB_THRESHOLD:
                raw_qty = float(reg_model.predict(X)[0])
                ml_qty = max(0, int(round(raw_qty)))
                model_used = "ml"
            else:
                ml_qty = 0
                model_used = "ml"

        if model_used == "ml":
            predicted_qty = ml_qty
        else:
            predicted_qty = bl_qty

        daily_dict = {k: int(v) for k, v in row.get("daily", {}).items()}
        data_days = weekday_pattern_service.distinct_active_days(
            daily_dict, target_date, lookback_days
        )
        var = _variability_coeff(series, td_ts)
        base_conf = confidence_service.calculate_confidence(
            row.get("frequency", 0), var, data_days
        )

        cutoff = td_ts - pd.Timedelta(days=1)
        past = series[series.index <= cutoff]
        avg_14 = float(past.tail(14).mean()) if len(past) >= 1 else 0.0
        avg_30 = float(past.tail(30).mean()) if len(past) >= 1 else 0.0

        wd_vals = []
        for w in range(1, weeks_back + 1):
            d = td_ts - pd.Timedelta(weeks=w)
            if d in series.index:
                wd_vals.append(float(series[d]))
        wd_active = [v for v in wd_vals if v > 0]
        wd_avg = np.mean(wd_active) if wd_active else 0.0
        ship_prob_stat = len(wd_active) / max(len(wd_vals), 1) if wd_vals else 0.0

        entry = {
            "target_type": target_type,
            "target_name": row.get("target_name", ""),
            "target_code": row.get("target_code", row.get("combination_key", "")),
            "sku_code": row.get("sku_code", ""),
            "barcode": row.get("barcode", ""),
            "option_name": row.get("option_name", ""),
            "combination_key": row.get("combination_key", ""),
            "items": row.get("items", []),
            "predicted_qty": predicted_qty,
            "stat_qty": bl_qty,
            "ml_qty": ml_qty,
            "ml_model_type": model_used,
            "ml_accuracy": round(model_info.get("train_accuracy", 0), 3),
            "ml_samples": model_info.get("train_samples", 0),
            "confidence_score": round(base_conf, 3),
            "recent_7d_avg": round(avg_14, 1),
            "recent_30d_avg": round(avg_30, 1),
            "recent_same_weekday_avg": round(wd_avg, 1),
            "weekday_basis": wb,
            "frequency": row.get("frequency", 0),
            "model_used": model_used,
            "ship_probability": round(ship_prob_ml if model_used == "ml" else ship_prob_stat, 3),
            "gpt_reason": "",
            "gpt_confidence": "",
        }
        out.append(entry)

    return out


def _get_or_train_models(
    supplier_name: str,
    target_date: str,
    sku_series_map: dict[str, pd.Series],
) -> tuple:
    """
    2단계 모델 학습:
    1) Classifier: 출하 여부 (0/1)
    2) Regressor: 출하 시 수량 (양수만 학습)
    """
    cache_key = f"{supplier_name}||{target_date}"
    if cache_key in _TRAINED_CACHE:
        c = _TRAINED_CACHE[cache_key]
        return c.get("clf"), c.get("reg"), c.get("info", {})

    td = pd.Timestamp(target_date)
    feature_names = get_feature_names()
    train_days = 60

    X_all, y_all = [], []
    t0 = time.time()

    for sku_key, series in sku_series_map.items():
        if series.empty:
            continue
        for offset in range(1, train_days + 1):
            train_date = td - pd.Timedelta(days=offset)
            if train_date < series.index.min():
                continue

            actual = float(series.get(train_date, 0))
            feat = compute_features_for_date(series, train_date)

            has_signal = (
                feat.get("roll_active_mean_14", 0) > 0
                or feat.get("roll_active_mean_30", 0) > 0
                or feat.get("wd_avg", 0) > 0
            )
            if not has_signal and actual == 0:
                continue

            X_all.append([feat.get(f, 0.0) for f in feature_names])
            y_all.append(actual)

            if len(X_all) >= 25000:
                break
        if len(X_all) >= 25000:
            break

    build_time = time.time() - t0

    if len(X_all) < 100:
        logger.info("Insufficient training data (%d) for %s", len(X_all), supplier_name)
        _TRAINED_CACHE[cache_key] = {"clf": None, "reg": None, "info": {}}
        return None, None, {}

    X = np.array(X_all, dtype=float)
    y = np.array(y_all, dtype=float)
    y_cls = (y > 0).astype(int)

    try:
        from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor

        t0 = time.time()

        # === Stage 1: Classification (출하 여부) ===
        clf = GradientBoostingClassifier(
            n_estimators=150,
            max_depth=4,
            learning_rate=0.05,
            min_samples_leaf=10,
            subsample=0.8,
            random_state=42,
        )
        clf.fit(X, y_cls)

        clf_acc = float(np.mean(clf.predict(X) == y_cls))

        # === Stage 2: Regression (출하 시 수량, 양수만) ===
        pos_mask = y > 0
        X_pos = X[pos_mask]
        y_pos = y[pos_mask]

        reg = None
        reg_mae = 0.0
        if len(X_pos) >= 30:
            reg = GradientBoostingRegressor(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                min_samples_leaf=5,
                subsample=0.8,
                random_state=42,
            )
            reg.fit(X_pos, y_pos)
            y_pred_pos = reg.predict(X_pos)
            reg_mae = float(np.mean(np.abs(y_pos - y_pred_pos)))

        train_time = time.time() - t0

        mean_y = float(np.mean(y[y > 0])) if pos_mask.any() else 1.0
        accuracy = max(0.0, 1.0 - reg_mae / max(mean_y, 1.0)) if reg else 0.0

        info = {
            "trained": True,
            "train_samples": len(X),
            "train_accuracy": round(accuracy, 3),
            "clf_accuracy": round(clf_acc, 3),
            "positive_samples": int(pos_mask.sum()),
            "zero_samples": int((~pos_mask).sum()),
            "build_time": round(build_time, 2),
            "train_time": round(train_time, 2),
        }

        logger.info(
            "2-stage model trained: %s | total=%d (pos=%d, zero=%d) | clf_acc=%.1f%% | reg_mae=%.1f | build=%.2fs | train=%.2fs",
            supplier_name, len(X), int(pos_mask.sum()), int((~pos_mask).sum()),
            clf_acc * 100, reg_mae, build_time, train_time,
        )

    except Exception as exc:
        logger.warning("Model training failed for %s: %s", supplier_name, exc)
        _TRAINED_CACHE[cache_key] = {"clf": None, "reg": None, "info": {}}
        return None, None, {}

    _TRAINED_CACHE[cache_key] = {"clf": clf, "reg": reg, "info": info}

    if len(_TRAINED_CACHE) > MAX_CACHE:
        oldest = next(iter(_TRAINED_CACHE))
        del _TRAINED_CACHE[oldest]

    return clf, reg, info


def _variability_coeff(series: pd.Series, td: pd.Timestamp, days: int = 30) -> float:
    cutoff = td - pd.Timedelta(days=1)
    start = cutoff - pd.Timedelta(days=days - 1)
    w = series[(series.index >= start) & (series.index <= cutoff)]
    active = w[w > 0]
    if len(active) < 2:
        return 0.0
    m = float(active.mean())
    if m <= 1e-9:
        return 1.0
    return min(1.0, float(active.std() / m))
