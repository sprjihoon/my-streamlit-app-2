"""
predictor — 업체 적응형 예측기
═══════════════════════════════
업체 특성(SKU 수, 평균 수량, 변동성, 출하 빈도)을 자동 분석하여
파라미터를 동적으로 결정한다.

업체 유형:
  A) 소품종 대량 (화장품 등) — SKU 적고 개당 수량 큼, 안정적
  B) 다품종 소량 (의류 등) — SKU 많고 개당 수량 작음, 변동 큼
  C) 중간형 — 그 사이

각 유형에 맞는 출하확률 threshold, 블렌딩 비율, 트렌드 스케일 범위를
자동으로 결정한다.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 업체 프로파일 — 자동 분석 결과
# ──────────────────────────────────────────────
@dataclass
class SupplierProfile:
    total_skus: int
    avg_qty_per_active_day: float
    avg_ship_prob: float       # 전체 SKU의 평균 출하 확률
    volatility: float          # 전체 변동계수 (CV)
    supplier_type: str         # "stable_few", "volatile_many", "mixed"

    # 적응형 파라미터
    prob_threshold: float      # 출하확률 이 미만이면 0 예측
    blend_recent_weight: float # 7일전 값 가중치 (나머지는 중앙값)
    trend_scale_min: float
    trend_scale_max: float
    min_data_days: int         # 최소 데이터 일수


def _analyze_supplier(
    sku_series_map: dict[str, pd.Series],
    td: pd.Timestamp,
    weeks_back: int = 6,
) -> SupplierProfile:
    """업체 데이터를 분석하여 프로파일을 생성한다."""
    if not sku_series_map:
        return _default_profile()

    total_skus = len(sku_series_map)
    cutoff = td - pd.Timedelta(days=1)

    ship_probs: list[float] = []
    avg_qtys: list[float] = []
    cvs: list[float] = []

    for series in sku_series_map.values():
        past = series[series.index <= cutoff]
        if past.empty:
            continue

        # 같은 요일 출하 확률
        wd_vals = []
        for w in range(1, weeks_back + 1):
            d = td - pd.Timedelta(weeks=w)
            if d in past.index:
                wd_vals.append(float(past[d]))
            elif d >= past.index.min():
                wd_vals.append(0.0)

        if wd_vals:
            sp = len([v for v in wd_vals if v > 0]) / len(wd_vals)
            ship_probs.append(sp)

        # 활성일 평균 수량
        active = past[past > 0]
        if len(active) > 0:
            avg_qtys.append(float(active.mean()))
            if len(active) >= 2 and active.mean() > 0:
                cvs.append(float(active.std() / active.mean()))

    avg_ship_prob = float(np.mean(ship_probs)) if ship_probs else 0.0
    avg_qty = float(np.mean(avg_qtys)) if avg_qtys else 0.0
    avg_cv = float(np.mean(cvs)) if cvs else 1.0

    # 업체 유형 결정
    if total_skus <= 50 and avg_qty >= 10 and avg_cv < 0.8:
        stype = "stable_few"
    elif total_skus >= 150 or (avg_qty < 5 and avg_cv > 0.6):
        stype = "volatile_many"
    else:
        stype = "mixed"

    # 유형별 파라미터 결정
    if stype == "stable_few":
        # 소품종 대량: 활성값 중심, 트렌드 적극 반영
        return SupplierProfile(
            total_skus=total_skus,
            avg_qty_per_active_day=avg_qty,
            avg_ship_prob=avg_ship_prob,
            volatility=avg_cv,
            supplier_type=stype,
            prob_threshold=0.20,
            blend_recent_weight=0.5,
            trend_scale_min=0.6,
            trend_scale_max=1.4,
            min_data_days=7,
        )
    elif stype == "volatile_many":
        # 다품종 소량: 보수적, 중앙값 중심, 트렌드 약하게
        return SupplierProfile(
            total_skus=total_skus,
            avg_qty_per_active_day=avg_qty,
            volatility=avg_cv,
            avg_ship_prob=avg_ship_prob,
            supplier_type=stype,
            prob_threshold=0.40,
            blend_recent_weight=0.3,
            trend_scale_min=0.8,
            trend_scale_max=1.2,
            min_data_days=14,
        )
    else:
        return SupplierProfile(
            total_skus=total_skus,
            avg_qty_per_active_day=avg_qty,
            avg_ship_prob=avg_ship_prob,
            volatility=avg_cv,
            supplier_type=stype,
            prob_threshold=0.30,
            blend_recent_weight=0.4,
            trend_scale_min=0.7,
            trend_scale_max=1.3,
            min_data_days=14,
        )


def _default_profile() -> SupplierProfile:
    return SupplierProfile(
        total_skus=0,
        avg_qty_per_active_day=0,
        avg_ship_prob=0,
        volatility=1.0,
        supplier_type="mixed",
        prob_threshold=0.30,
        blend_recent_weight=0.4,
        trend_scale_min=0.7,
        trend_scale_max=1.3,
        min_data_days=14,
    )


# ──────────────────────────────────────────────
# 메인 예측 함수
# ──────────────────────────────────────────────
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

    # 업체 프로파일 자동 분석
    profile = _analyze_supplier(sku_series_map, td_ts)
    logger.info(
        "Supplier profile: %s — type=%s, skus=%d, avgQty=%.1f, cv=%.2f, "
        "probTh=%.2f, blendW=%.2f, trendRange=[%.2f,%.2f]",
        supplier_name, profile.supplier_type, profile.total_skus,
        profile.avg_qty_per_active_day, profile.volatility,
        profile.prob_threshold, profile.blend_recent_weight,
        profile.trend_scale_min, profile.trend_scale_max,
    )

    # 트렌드 스케일링
    trend_scale = _compute_supplier_trend_scale(
        sku_series_map, td_ts,
        scale_min=profile.trend_scale_min,
        scale_max=profile.trend_scale_max,
    )

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

        predicted_qty, ship_prob, method_detail = _adaptive_predict(
            series, td_ts, profile
        )

        if predicted_qty > 0 and trend_scale != 1.0:
            predicted_qty = max(1, int(round(predicted_qty * trend_scale)))
            method_detail += f",scale={trend_scale:.2f}"

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
            "gpt_reason": f"[{profile.supplier_type}] {method_detail}",
            "gpt_confidence": "",
        }
        out.append(entry)

    return out


# ──────────────────────────────────────────────
# 적응형 예측 함수
# ──────────────────────────────────────────────
def _adaptive_predict(
    series: pd.Series,
    td: pd.Timestamp,
    profile: SupplierProfile,
) -> tuple[int, float, str]:
    """
    업체 프로파일에 따라 파라미터가 달라지는 예측.

    stable_few: 7일전 값 비중 높음, 확률 threshold 낮음 → 과소예측 방지
    volatile_many: 중앙값 비중 높음, 확률 threshold 높음 → 과다예측 방지
    """
    cutoff = td - pd.Timedelta(days=1)
    past = series[series.index <= cutoff]

    if past.empty:
        return 0, 0.0, "no_data"

    data_span = (past.index.max() - past.index.min()).days
    if data_span < profile.min_data_days:
        return 0, 0.0, "insufficient_data"

    # 같은 요일 최근 6주 데이터 수집 (0 포함)
    wd_vals: list[float] = []
    for w in range(1, 7):
        d = td - pd.Timedelta(weeks=w)
        if d in past.index:
            wd_vals.append(float(past[d]))
        elif d >= past.index.min():
            wd_vals.append(0.0)

    if not wd_vals:
        return 0, 0.0, "no_weekday_data"

    ship_count = len([v for v in wd_vals if v > 0])
    ship_prob = ship_count / len(wd_vals)

    if ship_prob < profile.prob_threshold:
        return 0, ship_prob, f"low_prob({ship_prob:.0%}<{profile.prob_threshold:.0%})"

    active_vals = [v for v in wd_vals if v > 0]
    median_all = float(np.median(wd_vals))
    median_active = float(np.median(active_vals)) if active_vals else 0.0

    d_7 = td - pd.Timedelta(weeks=1)
    val_7 = float(past[d_7]) if d_7 in past.index else 0.0

    rw = profile.blend_recent_weight  # 7일전 가중치

    if ship_prob >= 0.5:
        # 자주 출하되는 SKU
        if val_7 > 0:
            blended = val_7 * rw + median_active * (1 - rw)
        else:
            blended = median_active * ship_prob
        predicted = max(0, int(round(blended)))
        method = f"freq(7d={val_7:.0f},medA={median_active:.0f},rw={rw:.1f})"
    else:
        # 비정기 SKU — 전체 중앙값 기반
        if median_all > 0:
            predicted = max(0, int(round(median_all)))
            method = f"rare_med({median_all:.0f},p={ship_prob:.0%})"
        elif val_7 > 0:
            predicted = max(0, int(round(val_7 * ship_prob)))
            method = f"rare_7d({val_7:.0f}*{ship_prob:.0%})"
        else:
            predicted = 0
            method = "rare_zero"

    return predicted, ship_prob, method


# ──────────────────────────────────────────────
# 유틸리티 함수들
# ──────────────────────────────────────────────
def _compute_supplier_trend_scale(
    sku_series_map: dict[str, pd.Series],
    td: pd.Timestamp,
    scale_min: float = 0.7,
    scale_max: float = 1.3,
) -> float:
    if not sku_series_map:
        return 1.0

    cutoff = td - pd.Timedelta(days=1)
    recent_start = cutoff - pd.Timedelta(days=6)
    prev_start = recent_start - pd.Timedelta(days=7)
    prev_end = recent_start - pd.Timedelta(days=1)

    recent_total = 0.0
    prev_total = 0.0

    for series in sku_series_map.values():
        recent_window = series[(series.index >= recent_start) & (series.index <= cutoff)]
        prev_window = series[(series.index >= prev_start) & (series.index <= prev_end)]
        recent_total += recent_window.sum()
        prev_total += prev_window.sum()

    if prev_total < 30:
        return 1.0

    raw_scale = recent_total / prev_total
    return max(scale_min, min(scale_max, raw_scale))


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
