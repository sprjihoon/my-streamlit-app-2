"""
calibration — 업체별 예측 파라미터 자동 튜닝 (경량 버전)
═══════════════════════════════════════════════════════
백테스트 실행 시 이미 로드된 데이터를 재활용하여
추가 DB 쿼리 없이 그리드서치를 수행한다.

흐름:
  1) 백테스트가 predict_for_date를 호출 → 데이터 로드됨
  2) 백테스트 결과에서 실제값 확보
  3) calibrate_from_backtest()로 현재 날짜 기준 최적 파라미터 탐색
  4) DB에 저장 (기존 결과와 가중 평균)
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 그리드 — 48 조합 (빠름)
PROB_THRESHOLDS = [0.17, 0.33, 0.50]
BLEND_WEIGHTS = [0.3, 0.5]
FALLBACK_PROBS = [0.40, 0.60]
FALLBACK_RATIOS = [0.3, 0.7]
TREND_RANGES = [(0.85, 1.15), (1.0, 1.0)]


def calibrate_from_backtest(
    supplier_name: str,
    target_date: str,
    sku_series_map: dict[str, pd.Series],
    all_rows: list[tuple[str, dict]],
    actual_map: dict[str, int],
    td_ts: pd.Timestamp,
) -> dict | None:
    """
    백테스트 데이터를 재활용하여 최적 파라미터를 찾는다.
    추가 DB 쿼리 없이 순수 계산만 수행.
    """
    from prepacking.common.utils import normalize_sku_name

    if not actual_map or not sku_series_map:
        return None

    total_actual = sum(actual_map.values())
    if total_actual <= 0:
        return None

    best_accuracy = -1.0
    best_params = None

    for pt in PROB_THRESHOLDS:
        for brw in BLEND_WEIGHTS:
            for fp in FALLBACK_PROBS:
                for fr in FALLBACK_RATIOS:
                    for ts_min, ts_max in TREND_RANGES:
                        total_pred = _simulate_total(
                            sku_series_map, all_rows, td_ts,
                            pt, brw, fp, fr, ts_min, ts_max,
                        )
                        error_rate = abs(total_pred - total_actual) / total_actual * 100
                        acc = max(0.0, 100.0 - error_rate)

                        if acc > best_accuracy:
                            best_accuracy = acc
                            best_params = {
                                "prob_threshold": pt,
                                "blend_recent_weight": brw,
                                "fallback_prob": fp,
                                "fallback_ratio": fr,
                                "trend_scale_min": ts_min,
                                "trend_scale_max": ts_max,
                            }

    if best_params is None:
        return None

    # 정확도가 60% 미만이면 저장하지 않음 (노이즈 방지)
    if best_accuracy < 60.0:
        logger.info(
            "Skipping calibration for %s on %s: best_acc=%.1f%% < 60%%",
            supplier_name, target_date, best_accuracy,
        )
        return {"accuracy": round(best_accuracy, 1), "skipped": True, **best_params}

    _update_params_in_db(supplier_name, target_date, best_params, best_accuracy, sku_series_map, td_ts)

    logger.info(
        "Calibrated %s on %s: acc=%.1f%%, pt=%.2f, brw=%.1f, fp=%.2f, fr=%.1f, ts=[%.2f,%.2f]",
        supplier_name, target_date, best_accuracy,
        best_params["prob_threshold"], best_params["blend_recent_weight"],
        best_params["fallback_prob"], best_params["fallback_ratio"],
        best_params["trend_scale_min"], best_params["trend_scale_max"],
    )

    return {
        "accuracy": round(best_accuracy, 1),
        **best_params,
    }


def _simulate_total(
    sku_series_map: dict[str, pd.Series],
    all_rows: list[tuple[str, dict]],
    td: pd.Timestamp,
    prob_threshold: float,
    blend_recent_weight: float,
    fallback_prob: float,
    fallback_ratio: float,
    trend_scale_min: float,
    trend_scale_max: float,
) -> int:
    """특정 파라미터로 전체 예측 총합을 계산."""
    from prepacking.common.utils import normalize_sku_name
    from prepacking.services.prediction.pipeline.predictor import _compute_supplier_trend_scale

    trend_scale = _compute_supplier_trend_scale(
        sku_series_map, td,
        scale_min=trend_scale_min,
        scale_max=trend_scale_max,
    )

    total = 0
    for target_type, row in all_rows:
        if target_type == "combination":
            series_key = f"combo||{row.get('combination_key', '')}"
        else:
            pn = normalize_sku_name(row.get("target_code", ""))
            on = normalize_sku_name(row.get("option_name", ""))
            series_key = f"{pn}||{on}"

        series = sku_series_map.get(series_key)
        if series is None or series.empty:
            continue

        pred = _fast_predict(series, td, prob_threshold, blend_recent_weight, fallback_prob, fallback_ratio)

        if pred > 0 and trend_scale != 1.0:
            pred = max(1, int(round(pred * trend_scale)))

        total += pred

    return total


def _fast_predict(
    series: pd.Series,
    td: pd.Timestamp,
    prob_threshold: float,
    blend_recent_weight: float,
    fallback_prob: float,
    fallback_ratio: float,
) -> int:
    """최소한의 계산으로 예측값 반환."""
    cutoff = td - pd.Timedelta(days=1)
    past = series[series.index <= cutoff]

    if past.empty or (past.index.max() - past.index.min()).days < 7:
        return 0

    wd_vals = []
    for w in range(1, 7):
        d = td - pd.Timedelta(weeks=w)
        if d in past.index:
            wd_vals.append(float(past[d]))
        elif d >= past.index.min():
            wd_vals.append(0.0)

    if not wd_vals:
        return 0

    ship_prob = len([v for v in wd_vals if v > 0]) / len(wd_vals)
    if ship_prob < prob_threshold:
        return 0

    active_vals = [v for v in wd_vals if v > 0]
    median_active = float(np.median(active_vals)) if active_vals else 0.0

    d_7 = td - pd.Timedelta(weeks=1)
    val_7 = float(past[d_7]) if d_7 in past.index else 0.0

    if val_7 > 0:
        return max(1, int(round(val_7 * blend_recent_weight + median_active * (1 - blend_recent_weight))))

    if ship_prob >= fallback_prob and median_active > 0:
        return max(1, int(round(median_active * fallback_ratio)))

    return 0


def _update_params_in_db(
    supplier_name: str,
    target_date: str,
    new_params: dict,
    new_accuracy: float,
    sku_series_map: dict[str, pd.Series],
    td_ts: pd.Timestamp,
) -> None:
    """DB에 파라미터 저장. 기존 결과가 있으면 가중 평균으로 블렌딩."""
    from prepacking.database import get_pp_connection
    from prepacking.services.prediction.pipeline.predictor import _analyze_supplier

    existing = load_supplier_params(supplier_name)
    profile = _analyze_supplier(sku_series_map, td_ts)

    if existing and existing.get("calibration_accuracy", 0) > 0:
        old_acc = existing["calibration_accuracy"]

        # 새 결과가 기존보다 20% 이상 나쁘면 저장하지 않음
        if new_accuracy < old_acc - 20:
            logger.info(
                "Skipping update for %s: new_acc=%.1f%% < old_acc=%.1f%% - 20",
                supplier_name, new_accuracy, old_acc,
            )
            return

        old_weight = 0.6
        new_weight = 0.4

        params = {}
        for key in ["prob_threshold", "blend_recent_weight", "fallback_prob",
                     "fallback_ratio", "trend_scale_min", "trend_scale_max"]:
            old_val = existing.get(key, new_params[key])
            params[key] = old_val * old_weight + new_params[key] * new_weight

        # 이산값으로 스냅 (가장 가까운 그리드 값)
        params["prob_threshold"] = _snap_to_grid(params["prob_threshold"], PROB_THRESHOLDS)
        params["blend_recent_weight"] = _snap_to_grid(params["blend_recent_weight"], BLEND_WEIGHTS)
        params["fallback_prob"] = _snap_to_grid(params["fallback_prob"], FALLBACK_PROBS)
        params["fallback_ratio"] = _snap_to_grid(params["fallback_ratio"], FALLBACK_RATIOS)

        blended_acc = old_acc * old_weight + new_accuracy * new_weight
    else:
        params = new_params
        blended_acc = new_accuracy

    dates_json = json.dumps([target_date])
    if existing:
        try:
            old_dates = json.loads(existing.get("calibration_dates", "[]") or "[]")
            if target_date not in old_dates:
                old_dates.append(target_date)
            dates_json = json.dumps(old_dates[-5:])
        except (json.JSONDecodeError, TypeError):
            dates_json = json.dumps([target_date])

    with get_pp_connection() as con:
        con.execute(
            """
            INSERT INTO pp_supplier_params (
                supplier_name, supplier_type,
                prob_threshold, blend_recent_weight,
                trend_scale_min, trend_scale_max,
                min_data_days, fallback_prob, fallback_ratio,
                calibration_accuracy, calibration_dates,
                total_skus, avg_qty, volatility,
                calibrated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(supplier_name) DO UPDATE SET
                supplier_type = excluded.supplier_type,
                prob_threshold = excluded.prob_threshold,
                blend_recent_weight = excluded.blend_recent_weight,
                trend_scale_min = excluded.trend_scale_min,
                trend_scale_max = excluded.trend_scale_max,
                min_data_days = excluded.min_data_days,
                fallback_prob = excluded.fallback_prob,
                fallback_ratio = excluded.fallback_ratio,
                calibration_accuracy = excluded.calibration_accuracy,
                calibration_dates = excluded.calibration_dates,
                total_skus = excluded.total_skus,
                avg_qty = excluded.avg_qty,
                volatility = excluded.volatility,
                calibrated_at = CURRENT_TIMESTAMP
            """,
            (
                supplier_name,
                profile.supplier_type,
                params["prob_threshold"],
                params["blend_recent_weight"],
                params["trend_scale_min"],
                params["trend_scale_max"],
                14,
                params["fallback_prob"],
                params["fallback_ratio"],
                round(blended_acc, 1),
                dates_json,
                profile.total_skus,
                round(profile.avg_qty_per_active_day, 1),
                round(profile.volatility, 2),
            ),
        )
        con.commit()


def _snap_to_grid(value: float, grid: list[float]) -> float:
    """가장 가까운 그리드 값으로 스냅."""
    return min(grid, key=lambda g: abs(g - value))


def load_supplier_params(supplier_name: str) -> dict | None:
    """DB에서 업체별 저장된 파라미터를 로드."""
    from prepacking.database import get_pp_connection

    try:
        with get_pp_connection() as con:
            row = con.execute(
                """
                SELECT supplier_type, prob_threshold, blend_recent_weight,
                       trend_scale_min, trend_scale_max, min_data_days,
                       fallback_prob, fallback_ratio, calibration_accuracy,
                       calibration_dates
                FROM pp_supplier_params
                WHERE supplier_name = ?
                """,
                (supplier_name,),
            ).fetchone()
    except Exception:
        return None

    if row is None:
        return None

    return {
        "supplier_type": row[0],
        "prob_threshold": row[1],
        "blend_recent_weight": row[2],
        "trend_scale_min": row[3],
        "trend_scale_max": row[4],
        "min_data_days": row[5],
        "fallback_prob": row[6],
        "fallback_ratio": row[7],
        "calibration_accuracy": row[8],
        "calibration_dates": row[9],
    }
