"""
calibration — 업체별 예측 파라미터 자동 튜닝
═══════════════════════════════════════════════
과거 데이터를 사용하여 그리드서치로 최적 파라미터 조합을 찾고
DB에 저장한다.

사용 시점:
  1) 백테스트 실행 시 자동 트리거
  2) 수동 캘리브레이션 API 호출
  3) 새 데이터 업로드 후 자동 실행
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 그리드서치 파라미터 공간
PARAM_GRID = {
    "prob_threshold": [0.17, 0.25, 0.33, 0.40, 0.50],
    "blend_recent_weight": [0.2, 0.3, 0.4, 0.5, 0.6],
    "fallback_prob": [0.40, 0.50, 0.60, 0.67],
    "fallback_ratio": [0.3, 0.5, 0.7, 0.9],
    "trend_scale_range": [
        (0.85, 1.15),
        (0.7, 1.3),
        (0.6, 1.4),
        (1.0, 1.0),  # 트렌드 비활성화
    ],
}


def calibrate_supplier(
    supplier_name: str,
    test_dates: list[str] | None = None,
    max_dates: int = 8,
) -> dict:
    """
    업체의 최적 예측 파라미터를 찾아 DB에 저장한다.

    1. 과거 테스트 날짜들을 자동 선택 (최근 N주 같은 요일)
    2. 각 파라미터 조합으로 시뮬레이션
    3. 평균 정확도가 가장 높은 조합을 저장
    """
    from prepacking.services.prediction.pipeline.predictor import (
        _daily_to_filled_series,
        _analyze_supplier,
    )
    from prepacking.common.utils import normalize_sku_name
    from prepacking.services.analysis import repeat_sku_service, repeat_combination_service

    if test_dates is None:
        test_dates = _auto_select_test_dates(supplier_name, max_dates)

    if not test_dates:
        return {"error": "no_test_dates", "supplier_name": supplier_name}

    logger.info("Calibrating %s with %d test dates: %s", supplier_name, len(test_dates), test_dates)

    # 각 테스트 날짜별 실제 데이터 로드
    date_contexts: list[dict] = []
    for td_str in test_dates:
        ctx = _load_date_context(supplier_name, td_str)
        if ctx:
            date_contexts.append(ctx)

    if not date_contexts:
        return {"error": "no_data", "supplier_name": supplier_name}

    # 프로파일 분석 (첫 번째 날짜 기준)
    first_ctx = date_contexts[0]
    profile = _analyze_supplier(first_ctx["sku_series_map"], first_ctx["td_ts"])

    # 그리드서치
    best_accuracy = -1.0
    best_params = None
    all_results = []

    combos = list(itertools.product(
        PARAM_GRID["prob_threshold"],
        PARAM_GRID["blend_recent_weight"],
        PARAM_GRID["fallback_prob"],
        PARAM_GRID["fallback_ratio"],
        PARAM_GRID["trend_scale_range"],
    ))

    logger.info("Grid search: %d combinations x %d dates", len(combos), len(date_contexts))

    for pt, brw, fp, fr, (ts_min, ts_max) in combos:
        accuracies = []
        for ctx in date_contexts:
            acc = _simulate_accuracy(ctx, pt, brw, fp, fr, ts_min, ts_max)
            accuracies.append(acc)

        avg_acc = float(np.mean(accuracies))
        min_acc = float(np.min(accuracies))

        if avg_acc > best_accuracy:
            best_accuracy = avg_acc
            best_params = {
                "prob_threshold": pt,
                "blend_recent_weight": brw,
                "fallback_prob": fp,
                "fallback_ratio": fr,
                "trend_scale_min": ts_min,
                "trend_scale_max": ts_max,
                "avg_accuracy": round(avg_acc, 1),
                "min_accuracy": round(min_acc, 1),
                "per_date_accuracy": [round(a, 1) for a in accuracies],
            }

    if best_params is None:
        return {"error": "no_valid_params", "supplier_name": supplier_name}

    # DB 저장
    _save_params_to_db(supplier_name, best_params, profile, test_dates)

    result = {
        "supplier_name": supplier_name,
        "supplier_type": profile.supplier_type,
        "best_params": best_params,
        "test_dates": test_dates,
        "total_combinations_tested": len(combos),
        "profile": {
            "total_skus": profile.total_skus,
            "avg_qty": round(profile.avg_qty_per_active_day, 1),
            "volatility": round(profile.volatility, 2),
            "avg_ship_prob": round(profile.avg_ship_prob, 2),
        },
    }

    logger.info(
        "Calibration complete for %s: accuracy=%.1f%%, params=%s",
        supplier_name, best_accuracy, best_params,
    )

    return result


def _auto_select_test_dates(supplier_name: str, max_dates: int = 8) -> list[str]:
    """업체의 출하 데이터가 있는 최근 날짜들을 자동 선택."""
    from prepacking.database import get_pp_connection

    with get_pp_connection() as con:
        rows = con.execute(
            """
            SELECT DISTINCT shipping_date
            FROM pp_shipping_stats
            WHERE supplier_name = ?
              AND shipping_date IS NOT NULL
            ORDER BY shipping_date DESC
            LIMIT 60
            """,
            (supplier_name,),
        ).fetchall()

    if not rows:
        return []

    all_dates = [r[0] for r in rows if r[0]]
    if len(all_dates) <= 2:
        return []

    # 최근 날짜는 제외 (예측 대상이므로), 그 다음부터 선택
    # 최소 7일 간격으로 분산 선택
    selected = []
    last_selected = None
    for d_str in all_dates[1:]:
        try:
            d = dt.datetime.strptime(d_str[:10], "%Y-%m-%d").date()
        except ValueError:
            continue

        if last_selected is None or (last_selected - d).days >= 5:
            selected.append(d_str[:10])
            last_selected = d
            if len(selected) >= max_dates:
                break

    return selected


def _load_date_context(supplier_name: str, target_date: str) -> dict | None:
    """특정 날짜의 예측에 필요한 컨텍스트를 로드."""
    from prepacking.services.prediction.pipeline.predictor import _daily_to_filled_series
    from prepacking.common.utils import normalize_sku_name
    from prepacking.services.analysis import repeat_sku_service, repeat_combination_service

    try:
        td = dt.datetime.strptime(target_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

    td_ts = pd.Timestamp(td)
    lookback_days = 120

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
        s = _daily_to_filled_series(daily, td_ts, lookback_days)
        if s is not None:
            sku_series_map[key] = s

    for row in combos:
        all_rows.append(("combination", row))
        ckey = row.get("combination_key", "")
        daily = row.get("daily", {})
        s = _daily_to_filled_series(daily, td_ts, lookback_days)
        if s is not None:
            sku_series_map[f"combo||{ckey}"] = s

    # 실제 출하 데이터 로드
    actual_map = _load_actual_for_date(supplier_name, target_date)

    if not all_rows:
        return None

    return {
        "supplier_name": supplier_name,
        "target_date": target_date,
        "td_ts": td_ts,
        "all_rows": all_rows,
        "sku_series_map": sku_series_map,
        "actual_map": actual_map,
    }


def _load_actual_for_date(supplier_name: str, target_date: str) -> dict[str, int]:
    """특정 날짜의 실제 출하 데이터를 로드."""
    from prepacking.common.utils import normalize_sku_name
    from prepacking.database import get_pp_connection

    actual: dict[str, int] = {}
    with get_pp_connection() as con:
        rows = con.execute(
            """
            SELECT product_name, option_name, SUM(qty) as total_qty
            FROM pp_shipping_stats
            WHERE supplier_name = ? AND shipping_date = ?
            GROUP BY product_name, option_name
            """,
            (supplier_name, target_date),
        ).fetchall()

    for pn, on, qty in rows:
        key = f"{normalize_sku_name(pn or '')}||{normalize_sku_name(on or '')}"
        actual[key] = actual.get(key, 0) + int(qty or 0)

    return actual


def _simulate_accuracy(
    ctx: dict,
    prob_threshold: float,
    blend_recent_weight: float,
    fallback_prob: float,
    fallback_ratio: float,
    trend_scale_min: float,
    trend_scale_max: float,
) -> float:
    """특정 파라미터 조합으로 예측하고 총합 기준 정확도를 계산."""
    from prepacking.common.utils import normalize_sku_name
    from prepacking.services.prediction.pipeline.predictor import _compute_supplier_trend_scale

    td_ts = ctx["td_ts"]
    sku_series_map = ctx["sku_series_map"]
    actual_map = ctx["actual_map"]

    trend_scale = _compute_supplier_trend_scale(
        sku_series_map, td_ts,
        scale_min=trend_scale_min,
        scale_max=trend_scale_max,
    )

    total_predicted = 0
    total_actual = sum(actual_map.values())

    for target_type, row in ctx["all_rows"]:
        if target_type == "combination":
            series_key = f"combo||{row.get('combination_key', '')}"
        else:
            pn = normalize_sku_name(row.get("target_code", ""))
            on = normalize_sku_name(row.get("option_name", ""))
            series_key = f"{pn}||{on}"

        series = sku_series_map.get(series_key)
        if series is None or series.empty:
            continue

        pred = _sim_predict(
            series, td_ts,
            prob_threshold, blend_recent_weight,
            fallback_prob, fallback_ratio,
        )

        if pred > 0 and trend_scale != 1.0:
            pred = max(1, int(round(pred * trend_scale)))

        total_predicted += pred

    if total_actual <= 0:
        return 100.0 if total_predicted == 0 else 0.0

    error_rate = abs(total_predicted - total_actual) / total_actual * 100
    return max(0.0, 100.0 - error_rate)


def _sim_predict(
    series: pd.Series,
    td: pd.Timestamp,
    prob_threshold: float,
    blend_recent_weight: float,
    fallback_prob: float,
    fallback_ratio: float,
) -> int:
    """단순화된 예측 — 캘리브레이션용."""
    cutoff = td - pd.Timedelta(days=1)
    past = series[series.index <= cutoff]

    if past.empty:
        return 0

    data_span = (past.index.max() - past.index.min()).days
    if data_span < 7:
        return 0

    wd_vals: list[float] = []
    for w in range(1, 7):
        d = td - pd.Timedelta(weeks=w)
        if d in past.index:
            wd_vals.append(float(past[d]))
        elif d >= past.index.min():
            wd_vals.append(0.0)

    if not wd_vals:
        return 0

    ship_count = len([v for v in wd_vals if v > 0])
    ship_prob = ship_count / len(wd_vals)

    if ship_prob < prob_threshold:
        return 0

    active_vals = [v for v in wd_vals if v > 0]
    median_active = float(np.median(active_vals)) if active_vals else 0.0

    d_7 = td - pd.Timedelta(weeks=1)
    val_7 = float(past[d_7]) if d_7 in past.index else 0.0

    rw = blend_recent_weight

    if val_7 > 0:
        blended = val_7 * rw + median_active * (1 - rw)
        return max(1, int(round(blended)))
    elif ship_prob >= fallback_prob and median_active > 0:
        return max(1, int(round(median_active * fallback_ratio)))
    else:
        return 0


def _save_params_to_db(
    supplier_name: str,
    params: dict,
    profile,
    test_dates: list[str],
) -> None:
    """최적 파라미터를 DB에 저장 (UPSERT)."""
    from prepacking.database import get_pp_connection

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
                params["avg_accuracy"],
                json.dumps(test_dates),
                profile.total_skus,
                round(profile.avg_qty_per_active_day, 1),
                round(profile.volatility, 2),
            ),
        )
        con.commit()


def load_supplier_params(supplier_name: str) -> dict | None:
    """DB에서 업체별 저장된 파라미터를 로드."""
    from prepacking.database import get_pp_connection

    with get_pp_connection() as con:
        row = con.execute(
            """
            SELECT supplier_type, prob_threshold, blend_recent_weight,
                   trend_scale_min, trend_scale_max, min_data_days,
                   fallback_prob, fallback_ratio, calibration_accuracy
            FROM pp_supplier_params
            WHERE supplier_name = ?
            """,
            (supplier_name,),
        ).fetchone()

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
    }
