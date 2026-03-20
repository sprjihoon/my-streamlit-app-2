"""
logic/prepacking_analysis.py - 조합 분석 & 예측
───────────────────────────────────────────────
출고 데이터에서 합포장 조합 빈도를 세고,
요일별로 분류한 뒤 가중이동평균으로 예측합니다.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .prepacking_parse import (
    build_combo_detail,
    build_combo_key,
    extract_items_from_row,
    find_invoice_col,
    group_shipments,
    load_vendor_df,
    _safe_str,
)
from .prepacking_settings import get_settings


# ── 조합 분석 ───────────────────────

def analyze_combinations(
    vendor: str,
    d_from: date,
    d_to: date,
) -> Dict[str, Any]:
    """
    출고 데이터에서 합포장 조합 빈도를 세고 요일별로 분류.

    핵심 흐름:
      shipping_stats → 배송건 그룹핑 → combo_key 카운트 → 요일별 분류 → 순위 정렬
    """
    df, col_map = load_vendor_df(vendor, d_from, d_to, dedup_invoice=False)
    date_col = col_map["date"]

    if df.empty or not date_col:
        return {"vendor": vendor, "total_orders": 0, "multi_item_orders": 0, "combos": [], "data_weeks": 0}

    min_sku = get_settings(vendor).get("min_sku_count", 2)
    shipments = group_shipments(df, col_map)

    combo_counter: Counter = Counter()
    combo_day_counter: Dict[str, Counter] = defaultdict(Counter)
    combo_detail_cache: Dict[str, str] = {}
    combo_sku_count: Dict[str, int] = {}
    multi_item_count = 0
    single_item_count = 0

    for items, dt in shipments:
        if len(items) < min_sku:
            single_item_count += 1
            continue
        multi_item_count += 1
        key = build_combo_key(items)
        combo_counter[key] += 1
        combo_day_counter[key][dt.weekday() if pd.notna(dt) else 0] += 1
        if key not in combo_detail_cache:
            combo_detail_cache[key] = build_combo_detail(items)
            combo_sku_count[key] = len(items)

    valid_dates = df[date_col].dropna()
    data_weeks = max(1, (valid_dates.max() - valid_dates.min()).days // 7) if len(valid_dates) > 0 else 0

    combos = [
        {
            "combo_key": key,
            "combo_detail": combo_detail_cache.get(key, "[]"),
            "count": count,
            "day_counts": {str(d): combo_day_counter[key].get(d, 0) for d in range(7)},
            "sku_count": combo_sku_count.get(key, 0),
        }
        for key, count in combo_counter.most_common()
    ]

    invoice_col = find_invoice_col(df)

    result: Dict[str, Any] = {
        "vendor": vendor,
        "total_orders": len(shipments),
        "multi_item_orders": multi_item_count,
        "single_item_orders": single_item_count,
        "combos": combos,
        "data_weeks": data_weeks,
        "min_sku_count": min_sku,
        "has_admin_col": col_map.get("admin_product_qty") is not None,
        "has_barcode_col": col_map.get("barcode") is not None,
        "has_invoice_col": invoice_col is not None,
        "invoice_col": invoice_col,
        "detected_columns": {k: v for k, v in col_map.items() if v is not None},
    }

    # 합포장 0건일 때 진단 정보 추가
    if multi_item_count == 0 and len(shipments) > 0:
        diag_samples = []
        admin_col = col_map.get("admin_product_qty")
        for _, row in df.head(5).iterrows():
            raw = _safe_str(row.get(admin_col, "")) if admin_col else ""
            items = extract_items_from_row(row, col_map)
            diag_samples.append({
                "admin_raw": raw[:300] if raw else "(empty)",
                "items": items,
                "item_count": len(items),
            })
        item_counts = [len(items) for items, _ in shipments[:200]]
        result["diagnostic"] = {
            "sample_rows": diag_samples,
            "item_count_distribution": {str(c): item_counts.count(c) for c in set(item_counts)},
            "all_columns": list(df.columns[:30]),
        }

    return result


# ── 가중이동평균 ────────────────────

def _weighted_moving_average(values: List[int], weights: Optional[List[float]] = None) -> float:
    if not values:
        return 0.0
    n = len(values)
    if weights is None:
        weights = list(range(1, n + 1))
    w = weights[-n:]
    total_w = sum(w)
    return sum(v * wt for v, wt in zip(values, w)) / total_w if total_w else 0.0


# ── 예측 ────────────────────────────

def predict_for_date(
    vendor: str,
    target_date: date,
    weeks_back: int = 8,
) -> List[Dict[str, Any]]:
    """
    특정 날짜의 프리패킹 추천 목록 생성.
    같은 요일 데이터가 2주 미만이면 전체 일평균으로 폴백.
    """
    settings = get_settings(vendor)
    target_dow = target_date.weekday()
    d_from = target_date - timedelta(weeks=weeks_back)
    d_to = target_date - timedelta(days=1)

    df, col_map = load_vendor_df(vendor, d_from, d_to, dedup_invoice=False)
    if df.empty or not col_map["date"]:
        return []

    all_shipments = group_shipments(df, col_map)
    if not all_shipments:
        return []

    dow_shipments = [(items, dt) for items, dt in all_shipments if pd.notna(dt) and dt.weekday() == target_dow]
    dow_weeks = len(set(dt.isocalendar()[1] for _, dt in dow_shipments if pd.notna(dt)))

    if dow_weeks < 2:
        return _predict_from_all_days(all_shipments, settings)
    return _predict_from_weekday(dow_shipments, settings)


def _extract_combos(
    shipments: List[Tuple[List[Dict[str, Any]], pd.Timestamp]],
    min_sku: int,
) -> Tuple[Counter, Dict[str, str]]:
    freq: Counter = Counter()
    detail_cache: Dict[str, str] = {}
    for items, _ in shipments:
        if len(items) < min_sku:
            continue
        key = build_combo_key(items)
        freq[key] += 1
        if key not in detail_cache:
            detail_cache[key] = build_combo_detail(items)
    return freq, detail_cache


def _predict_from_all_days(
    shipments: List[Tuple[List[Dict[str, Any]], pd.Timestamp]],
    settings: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """같은 요일 데이터 부족 시 전체 일평균으로 폴백."""
    unique_dates = set(dt.date() for _, dt in shipments if pd.notna(dt))
    if not unique_dates:
        return []

    total_days = len(unique_dates)
    combo_freq, detail_cache = _extract_combos(shipments, settings["min_sku_count"])

    predictions = []
    for key, freq in combo_freq.items():
        if freq < settings["min_frequency"]:
            continue
        pred_qty = max(1, round(freq / total_days))
        if pred_qty < settings["min_predicted_qty"]:
            continue
        predictions.append({
            "combo_key": key,
            "combo_detail": detail_cache.get(key, "[]"),
            "predicted_qty": pred_qty,
            "frequency": freq,
            "weekly_history": [],
        })
    predictions.sort(key=lambda x: x["predicted_qty"], reverse=True)
    return predictions


def _predict_from_weekday(
    dow_shipments: List[Tuple[List[Dict[str, Any]], pd.Timestamp]],
    settings: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """같은 요일 데이터로 주간 가중이동평균 예측."""
    week_map: Dict[int, List[Tuple[List[Dict[str, Any]], pd.Timestamp]]] = defaultdict(list)
    for items, dt in dow_shipments:
        if pd.notna(dt):
            week_map[dt.isocalendar()[1]].append((items, dt))
    weeks_sorted = sorted(week_map.keys())

    combo_weekly: Dict[str, List[int]] = defaultdict(lambda: [0] * len(weeks_sorted))
    combo_total_freq: Counter = Counter()
    detail_cache: Dict[str, str] = {}

    for week_idx, week_num in enumerate(weeks_sorted):
        for items, _ in week_map[week_num]:
            if len(items) < settings["min_sku_count"]:
                continue
            key = build_combo_key(items)
            combo_weekly[key][week_idx] += 1
            combo_total_freq[key] += 1
            if key not in detail_cache:
                detail_cache[key] = build_combo_detail(items)

    predictions = []
    for key, weekly_vals in combo_weekly.items():
        freq = combo_total_freq[key]
        if freq < settings["min_frequency"]:
            continue
        pred_qty = max(1, round(_weighted_moving_average(weekly_vals)))
        if pred_qty < settings["min_predicted_qty"]:
            continue
        predictions.append({
            "combo_key": key,
            "combo_detail": detail_cache.get(key, "[]"),
            "predicted_qty": pred_qty,
            "frequency": freq,
            "weekly_history": weekly_vals,
        })
    predictions.sort(key=lambda x: x["predicted_qty"], reverse=True)
    return predictions
