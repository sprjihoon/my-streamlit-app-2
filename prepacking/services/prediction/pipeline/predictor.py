"""
predictor — SeasonalNaive 기반 예측기
──────────────────────────────────────
핵심: 7일 전 같은 요일 값을 그대로 예측.
7일 전에 출하 0이면 → 0, 20이면 → 20.

이것이 가장 정확한 baseline이며, ML이 이를 이기기 전까지는
이 방식을 사용한다.

보조 로직:
- 7일 전 데이터가 없으면 14일 전, 21일 전 순서로 폴백
- 최근 4주 같은 요일 중앙값으로 이상치 보정
"""
from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


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

        predicted_qty, ship_prob, method_detail = _seasonal_naive_predict(
            series, td_ts
        )

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
            else:
                wd_vals.append(0.0)
        wd_active = [v for v in wd_vals if v > 0]
        wd_avg = np.mean(wd_active) if wd_active else 0.0

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
            "stat_qty": predicted_qty,
            "ml_qty": 0,
            "ml_model_type": "statistical",
            "ml_accuracy": 0,
            "ml_samples": 0,
            "confidence_score": round(base_conf, 3),
            "recent_7d_avg": round(avg_14, 1),
            "recent_30d_avg": round(avg_30, 1),
            "recent_same_weekday_avg": round(wd_avg, 1),
            "weekday_basis": wb,
            "frequency": row.get("frequency", 0),
            "model_used": "statistical",
            "ship_probability": round(ship_prob, 3),
            "gpt_reason": method_detail,
            "gpt_confidence": "",
        }
        out.append(entry)

    return out


def _daily_to_filled_series(
    daily: dict, td_ts: pd.Timestamp, lookback_days: int
) -> pd.Series | None:
    """daily dict를 연속 날짜 시계열로 변환. 0인 날도 포함."""
    if not daily:
        return None

    raw = {pd.Timestamp(k): int(v) for k, v in daily.items()}
    if not raw:
        return None

    start = td_ts - pd.Timedelta(days=lookback_days)
    end = td_ts - pd.Timedelta(days=1)
    date_range = pd.date_range(start, end, freq="D")

    filled = pd.Series(0.0, index=date_range)
    for d, v in raw.items():
        if d in filled.index:
            filled[d] = float(v)

    return filled


def _seasonal_naive_predict(
    series: pd.Series,
    td: pd.Timestamp,
) -> tuple[int, float, str]:
    """
    SeasonalNaive 예측 — 같은 요일 최근 값 기반.

    1차: 7일 전 값 사용
    2차: 7일 전이 0이면, 최근 4주 같은 요일 중앙값 사용
    3차: 4주 모두 0이면 → 0

    이상치 보정: 7일 전 값이 4주 중앙값의 3배 이상이면 중앙값 사용.
    """
    cutoff = td - pd.Timedelta(days=1)
    past = series[series.index <= cutoff]

    if past.empty:
        return 0, 0.0, "no_data"

    # 같은 요일 최근 4주 데이터 수집 (0 포함)
    wd_vals: list[float] = []
    for w in range(1, 5):
        d = td - pd.Timedelta(weeks=w)
        if d in past.index:
            wd_vals.append(float(past[d]))
        elif d >= past.index.min():
            wd_vals.append(0.0)

    if not wd_vals:
        return 0, 0.0, "no_weekday_data"

    # 출하 확률
    ship_count = len([v for v in wd_vals if v > 0])
    ship_prob = ship_count / len(wd_vals)

    # 7일 전 값 (primary)
    d_7 = td - pd.Timedelta(weeks=1)
    val_7 = float(past[d_7]) if d_7 in past.index else 0.0

    # 4주 중앙값
    median_4w = float(np.median(wd_vals))

    # 예측 결정
    if val_7 > 0:
        # 이상치 보정: 7일 전 값이 중앙값의 3배 이상이면 중앙값 사용
        if median_4w > 0 and val_7 > median_4w * 3:
            predicted = int(round(median_4w))
            method = f"seasonal_capped(7d={val_7:.0f},med={median_4w:.0f})"
        else:
            predicted = int(round(val_7))
            method = f"seasonal_7d({val_7:.0f})"
    elif median_4w > 0:
        # 7일 전이 0이지만 다른 주에 출하가 있었음
        predicted = int(round(median_4w))
        method = f"median_4w({median_4w:.0f},prob={ship_prob:.0%})"
    else:
        predicted = 0
        method = "zero_all_weeks"

    return predicted, ship_prob, method


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
