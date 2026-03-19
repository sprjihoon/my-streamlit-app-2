"""
logic/prepacking.py - 프리패킹 예측·관리 로직
───────────────────────────────────────────────
배송통계 데이터에서 SKU 조합을 추출하고,
요일별 패턴 분석 → 가중이동평균 예측 → AI 보정을 통해
프리패킹 추천 목록을 생성합니다.
"""
from __future__ import annotations

import json
import re
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .db import get_connection, now_str


# ─────────────────────────────────────
# 1. 설정 관리
# ─────────────────────────────────────

def get_settings(vendor: str = "_default") -> Dict[str, Any]:
    """공급처별 설정 조회 (없으면 글로벌 기본값)."""
    with get_connection() as con:
        row = con.execute(
            "SELECT min_predicted_qty, min_frequency, min_sku_count, retention_days "
            "FROM prepacking_settings WHERE vendor = ?",
            (vendor,),
        ).fetchone()
        if not row and vendor != "_default":
            row = con.execute(
                "SELECT min_predicted_qty, min_frequency, min_sku_count, retention_days "
                "FROM prepacking_settings WHERE vendor = '_default'",
            ).fetchone()
        if row:
            return {
                "min_predicted_qty": row[0],
                "min_frequency": row[1],
                "min_sku_count": row[2],
                "retention_days": row[3],
            }
    return {"min_predicted_qty": 1, "min_frequency": 1, "min_sku_count": 2, "retention_days": 2}


def save_settings(vendor: str, settings: Dict[str, Any]) -> None:
    """설정 저장 (upsert)."""
    with get_connection() as con:
        con.execute(
            """INSERT INTO prepacking_settings (vendor, min_predicted_qty, min_frequency, min_sku_count, retention_days, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(vendor) DO UPDATE SET
                 min_predicted_qty=excluded.min_predicted_qty,
                 min_frequency=excluded.min_frequency,
                 min_sku_count=excluded.min_sku_count,
                 retention_days=excluded.retention_days,
                 updated_at=excluded.updated_at""",
            (
                vendor,
                settings.get("min_predicted_qty", 3),
                settings.get("min_frequency", 5),
                settings.get("min_sku_count", 2),
                settings.get("retention_days", 2),
                now_str(),
            ),
        )
        con.commit()


def get_all_settings() -> List[Dict[str, Any]]:
    """모든 설정 목록 반환."""
    with get_connection() as con:
        rows = con.execute(
            "SELECT vendor, min_predicted_qty, min_frequency, min_sku_count, retention_days "
            "FROM prepacking_settings ORDER BY vendor"
        ).fetchall()
    return [
        {
            "vendor": r[0],
            "min_predicted_qty": r[1],
            "min_frequency": r[2],
            "min_sku_count": r[3],
            "retention_days": r[4],
        }
        for r in rows
    ]


# ─────────────────────────────────────
# 2. SKU 조합 파싱
# ─────────────────────────────────────

def _normalize_text(text: str) -> str:
    """공백·특수문자 정규화."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text).strip())
    return text


def _safe_int(val, default: int = 1) -> int:
    """안전하게 정수 변환. NaN/None/빈문자열 → default."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_str(val) -> str:
    """안전하게 문자열 변환. NaN/None → 빈문자열."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def _detect_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """DataFrame에서 핵심 컬럼명을 자동 감지."""
    col_map: Dict[str, Optional[str]] = {
        "order": None, "product": None, "option": None,
        "qty": None, "inner_qty": None, "barcode": None,
        "date": None, "admin_product_qty": None,
    }
    for c in df.columns:
        cl = c.strip()
        if cl == "주문번호":
            col_map["order"] = c
        elif cl == "상품명":
            col_map["product"] = c
        elif cl in ("옵션", "옵션정보"):
            col_map["option"] = c
        elif cl == "수량":
            col_map["qty"] = c
        elif cl == "내품수량":
            col_map["inner_qty"] = c
        elif cl == "상품바코드":
            col_map["barcode"] = c
        elif cl in ("배송일", "송장등록일", "출고일자"):
            if col_map["date"] is None:
                col_map["date"] = c
        elif cl in ("어드민상품명수량", "어드민상품명 수량"):
            col_map["admin_product_qty"] = c
    return col_map


def parse_admin_product_qty(raw: str) -> List[Dict[str, Any]]:
    """
    어드민상품명수량 컬럼 파싱.

    구분자 규칙:
    - 줄바꿈(\\n)이 SKU 간 구분자
    - `---` 뒤의 숫자가 수량 (예: `슬로우 피딩 스푼, [옐로우]--- 1`)
    - 줄바꿈이 없으면 콤마를 구분자로 시도하되, `--- 숫자` 패턴이 있는 위치 기준
    """
    if not raw or (isinstance(raw, float) and math.isnan(raw)):
        return []
    raw = str(raw).strip()
    if not raw:
        return []

    # 줄바꿈이 있으면 줄바꿈으로 split
    if "\n" in raw:
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
    else:
        # 줄바꿈 없으면 "---숫자" 뒤의 콤마를 기준으로 split
        # 예: "상품A---1, 상품B---2" → ["상품A---1", "상품B---2"]
        lines = re.split(r"(---\s*\d+)\s*,\s*", raw)
        # re.split with group → ["상품A", "---1", "상품B", "---2", ""]
        # 짝수/홀수 인덱스를 재결합
        if len(lines) > 1:
            merged_lines = []
            i = 0
            while i < len(lines):
                if i + 1 < len(lines) and re.match(r"^---\s*\d+$", lines[i + 1]):
                    merged_lines.append(lines[i] + lines[i + 1])
                    i += 2
                else:
                    if lines[i].strip():
                        merged_lines.append(lines[i])
                    i += 1
            lines = merged_lines

    raw_items: List[Dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.+?)---+\s*(\d+)\s*$", line)
        if m:
            name = _normalize_text(m.group(1))
            qty = int(m.group(2))
            raw_items.append({"name": name, "qty": qty})
        else:
            raw_items.append({"name": _normalize_text(line), "qty": 1})

    if not raw_items:
        return []

    # 옵션 병합: "[옵션명]"만으로 된 항목은 바로 앞 상품의 옵션
    merged: List[Dict[str, Any]] = []
    for item in raw_items:
        if re.match(r"^\[.+\]$", item["name"]):
            if merged:
                merged[-1]["name"] = f"{merged[-1]['name']}, {item['name']}"
            else:
                merged.append(item)
        else:
            merged.append(item)

    return merged


def _split_csv_field(val) -> List[str]:
    """콤마로 구분된 필드를 split. NaN/None → 빈 리스트."""
    s = _safe_str(val)
    if not s:
        return []
    return [v.strip() for v in s.split(",") if v.strip()]


def _extract_items_from_row(
    row: pd.Series,
    col_map: Dict[str, Optional[str]],
) -> List[Dict[str, Any]]:
    """
    한 행에서 SKU 아이템 리스트 추출.

    어드민상품명수량 파싱 후, 같은 행의 상품바코드를
    콤마로 split하여 순서대로 매핑.
    """
    admin_col = col_map.get("admin_product_qty")
    bc_col = col_map.get("barcode")

    # 방법1: 어드민상품명수량 파싱 (우선)
    if admin_col and admin_col in row.index:
        raw = _safe_str(row.get(admin_col, ""))
        if raw:
            items = parse_admin_product_qty(raw)
            if items:
                barcodes = _split_csv_field(row.get(bc_col, "")) if bc_col and bc_col in row.index else []
                for i, it in enumerate(items):
                    it["barcode"] = barcodes[i] if i < len(barcodes) else ""
                return items

    # 방법2: 개별 컬럼 (fallback)
    product_col = col_map.get("product")
    product = _safe_str(row.get(product_col, "")) if product_col else ""
    if not product:
        return []

    option_col = col_map.get("option")
    option = _safe_str(row.get(option_col, "")) if option_col else ""

    qty = 1
    inner_col = col_map.get("inner_qty")
    if inner_col and inner_col in row.index:
        qty = _safe_int(row[inner_col], 0)
    if qty <= 0:
        qty_col = col_map.get("qty")
        if qty_col and qty_col in row.index:
            qty = _safe_int(row[qty_col], 1)
    if qty <= 0:
        qty = 1

    name = f"{product} [{option}]" if option else product
    barcode = _safe_str(row.get(bc_col, "")) if bc_col and bc_col in row.index else ""

    return [{"name": name, "qty": qty, "barcode": barcode}]


def build_combo_key(items: List[Dict[str, Any]]) -> str:
    """
    SKU 목록 → 정렬된 combo_key 생성.
    예: [{"name":"오리","qty":5},{"name":"닭","qty":3}] → "닭:3|오리:5"
    """
    if not items:
        return ""
    sorted_items = sorted(items, key=lambda x: x["name"])
    return "|".join(f"{it['name']}:{it['qty']}" for it in sorted_items)


def build_combo_detail(items: List[Dict[str, Any]]) -> str:
    """combo_detail JSON 생성 (제품명, 바코드, 수량)."""
    details = []
    for it in sorted(items, key=lambda x: x["name"]):
        d: Dict[str, Any] = {"name": it["name"], "qty": it["qty"]}
        if it.get("barcode"):
            d["barcode"] = it["barcode"]
        details.append(d)
    return json.dumps(details, ensure_ascii=False)


# ─────────────────────────────────────
# 3. 조합 분석
# ─────────────────────────────────────

def _load_vendor_df(vendor: str, d_from: date, d_to: date) -> Tuple[pd.DataFrame, Dict[str, Optional[str]]]:
    """
    배송통계 로드 → 공급처 필터 → 날짜 필터 → 송장 중복 제거.
    Returns: (filtered_df, col_map)
    """
    with get_connection() as con:
        df = pd.read_sql("SELECT * FROM shipping_stats", con)
        df.columns = [c.strip() for c in df.columns]
        alias_df = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor = ? AND file_type = 'shipping_stats'",
            con, params=(vendor,),
        )
    name_list = [vendor] + alias_df["alias"].tolist()
    col_map = _detect_columns(df)

    if not col_map["date"]:
        return pd.DataFrame(), col_map

    date_col = col_map["date"]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df[(df[date_col] >= pd.to_datetime(d_from)) & (df[date_col] <= pd.to_datetime(d_to))]

    if "공급처" in df.columns:
        df = df[df["공급처"].isin(name_list)]

    # 송장번호 중복 제거 (한 송장 = 한 배송건)
    for key in ("송장번호", "운송장번호"):
        if key in df.columns:
            df = df.drop_duplicates(subset=[key])
            break

    return df.reset_index(drop=True), col_map


def analyze_combinations(
    vendor: str,
    d_from: date,
    d_to: date,
) -> Dict[str, Any]:
    """
    배송통계에서 공급처별 SKU 조합을 추출·분석.
    각 행의 어드민상품명수량을 파싱하여 합포장 조합 식별.
    어드민상품명수량이 없으면 주문번호 그룹핑으로 fallback.
    """
    df, col_map = _load_vendor_df(vendor, d_from, d_to)
    date_col = col_map["date"]

    if df.empty or not date_col:
        return {"vendor": vendor, "total_orders": 0, "multi_item_orders": 0, "combos": [], "data_weeks": 0}

    total_orders = len(df)

    combo_counter: Counter = Counter()
    combo_day_counter: Dict[str, Counter] = defaultdict(Counter)
    combo_detail_cache: Dict[str, str] = {}
    multi_item_count = 0

    for _, row in df.iterrows():
        items = _extract_items_from_row(row, col_map)
        if len(items) < 2:
            continue
        multi_item_count += 1
        key = build_combo_key(items)
        combo_counter[key] += 1
        dow = row[date_col].weekday() if pd.notna(row[date_col]) else 0
        combo_day_counter[key][dow] += 1
        if key not in combo_detail_cache:
            combo_detail_cache[key] = build_combo_detail(items)

    # 데이터 기간 (주 수)
    valid_dates = df[date_col].dropna()
    if len(valid_dates) > 0:
        data_weeks = max(1, (valid_dates.max() - valid_dates.min()).days // 7)
    else:
        data_weeks = 0

    combos = []
    for key, count in combo_counter.most_common():
        day_counts = {str(d): combo_day_counter[key].get(d, 0) for d in range(7)}
        combos.append({
            "combo_key": key,
            "combo_detail": combo_detail_cache.get(key, "[]"),
            "count": count,
            "day_counts": day_counts,
        })

    return {
        "vendor": vendor,
        "total_orders": total_orders,
        "multi_item_orders": multi_item_count,
        "combos": combos,
        "data_weeks": data_weeks,
    }


# ─────────────────────────────────────
# 4. 가중이동평균 예측
# ─────────────────────────────────────

def _weighted_moving_average(values: List[int], weights: Optional[List[float]] = None) -> float:
    """가중이동평균 계산. 최근 데이터에 더 높은 가중치."""
    if not values:
        return 0.0
    n = len(values)
    if weights is None:
        weights = list(range(1, n + 1))
    w = weights[-n:]
    total_w = sum(w)
    if total_w == 0:
        return 0.0
    return sum(v * wt for v, wt in zip(values, w)) / total_w


def predict_for_date(
    vendor: str,
    target_date: date,
    weeks_back: int = 8,
) -> List[Dict[str, Any]]:
    """
    특정 날짜의 프리패킹 추천 목록 생성 (통계 기반).
    어드민상품명수량 파싱으로 각 행의 SKU 조합을 추출.
    같은 요일 데이터가 2주 미만이면 전체 요일 일평균으로 폴백.
    """
    settings = get_settings(vendor)
    target_dow = target_date.weekday()

    d_to = target_date - timedelta(days=1)
    d_from = target_date - timedelta(weeks=weeks_back)

    df, col_map = _load_vendor_df(vendor, d_from, d_to)
    date_col = col_map["date"]

    if df.empty or not date_col:
        return []

    def _extract_combos(work_df: pd.DataFrame) -> Tuple[Counter, Dict[str, str]]:
        freq: Counter = Counter()
        detail_cache: Dict[str, str] = {}
        for _, row in work_df.iterrows():
            items = _extract_items_from_row(row, col_map)
            if len(items) < settings["min_sku_count"]:
                continue
            key = build_combo_key(items)
            freq[key] += 1
            if key not in detail_cache:
                detail_cache[key] = build_combo_detail(items)
        return freq, detail_cache

    # 1차 시도: 같은 요일만
    dow_df = df[df[date_col].dt.weekday == target_dow]
    dow_weeks = dow_df[date_col].dt.isocalendar().week.nunique() if not dow_df.empty else 0
    use_all_days = dow_weeks < 2

    if use_all_days:
        total_days = df[date_col].dt.date.nunique()
        if total_days == 0:
            return []
        combo_freq, combo_detail_cache = _extract_combos(df)

        predictions = []
        for key, freq in combo_freq.items():
            if freq < settings["min_frequency"]:
                continue
            daily_avg = freq / total_days
            pred_qty = max(1, round(daily_avg))
            if pred_qty < settings["min_predicted_qty"]:
                continue
            predictions.append({
                "combo_key": key,
                "combo_detail": combo_detail_cache.get(key, "[]"),
                "predicted_qty": pred_qty,
                "frequency": freq,
                "weekly_history": [],
            })
    else:
        # 같은 요일 주별 가중이동평균
        dow_df = dow_df.copy()
        dow_df["_week"] = dow_df[date_col].dt.isocalendar().week.astype(int)
        weeks_sorted = sorted(dow_df["_week"].unique())

        combo_weekly: Dict[str, List[int]] = defaultdict(lambda: [0] * len(weeks_sorted))
        combo_total_freq: Counter = Counter()
        combo_detail_cache: Dict[str, str] = {}

        for week_idx, week_num in enumerate(weeks_sorted):
            week_df = dow_df[dow_df["_week"] == week_num]
            for _, row in week_df.iterrows():
                items = _extract_items_from_row(row, col_map)
                if len(items) < settings["min_sku_count"]:
                    continue
                key = build_combo_key(items)
                combo_weekly[key][week_idx] += 1
                combo_total_freq[key] += 1
                if key not in combo_detail_cache:
                    combo_detail_cache[key] = build_combo_detail(items)

        predictions = []
        for key, weekly_vals in combo_weekly.items():
            freq = combo_total_freq[key]
            if freq < settings["min_frequency"]:
                continue
            pred = _weighted_moving_average(weekly_vals)
            pred_qty = max(1, round(pred))
            if pred_qty < settings["min_predicted_qty"]:
                continue
            predictions.append({
                "combo_key": key,
                "combo_detail": combo_detail_cache.get(key, "[]"),
                "predicted_qty": pred_qty,
                "frequency": freq,
                "weekly_history": weekly_vals,
            })

    predictions.sort(key=lambda x: x["predicted_qty"], reverse=True)
    return predictions


# ─────────────────────────────────────
# 5. 예측 저장·조회
# ─────────────────────────────────────

def save_predictions(vendor: str, target_date: date, predictions: List[Dict]) -> int:
    """예측 결과를 DB에 저장."""
    dow = target_date.weekday()
    with get_connection() as con:
        # 기존 예측 삭제 (같은 vendor+date)
        con.execute(
            "DELETE FROM prepacking_predictions WHERE vendor=? AND target_date=?",
            (vendor, target_date.isoformat()),
        )
        for p in predictions:
            con.execute(
                """INSERT INTO prepacking_predictions
                   (vendor, target_date, day_of_week, combo_key, combo_detail, predicted_qty, ai_adjusted_qty, ai_reasoning, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    vendor,
                    target_date.isoformat(),
                    dow,
                    p["combo_key"],
                    p.get("combo_detail", "[]"),
                    p["predicted_qty"],
                    p.get("ai_adjusted_qty"),
                    p.get("ai_reasoning"),
                    now_str(),
                ),
            )
        con.commit()
    return len(predictions)


def get_predictions(vendor: str, target_date: date) -> List[Dict]:
    """저장된 예측 조회."""
    with get_connection() as con:
        rows = con.execute(
            """SELECT id, combo_key, combo_detail, predicted_qty, ai_adjusted_qty, ai_reasoning, actual_qty, mape
               FROM prepacking_predictions WHERE vendor=? AND target_date=?
               ORDER BY COALESCE(ai_adjusted_qty, predicted_qty) DESC""",
            (vendor, target_date.isoformat()),
        ).fetchall()
    return [
        {
            "id": r[0], "combo_key": r[1], "combo_detail": r[2],
            "predicted_qty": r[3], "ai_adjusted_qty": r[4], "ai_reasoning": r[5],
            "actual_qty": r[6], "mape": r[7],
        }
        for r in rows
    ]


# ─────────────────────────────────────
# 6. 제작 기록 (productions)
# ─────────────────────────────────────

def create_production(
    vendor: str,
    target_date: date,
    combo_key: str,
    combo_detail: str,
    predicted_qty: int,
    produced_qty: int,
    location: str = "",
) -> int:
    """프리패킹 제작 기록 생성."""
    ts = now_str()
    with get_connection() as con:
        cur = con.execute(
            """INSERT INTO prepacking_productions
               (vendor, target_date, combo_key, combo_detail, predicted_qty, produced_qty, remaining_qty, location, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (vendor, target_date.isoformat(), combo_key, combo_detail, predicted_qty, produced_qty, produced_qty, location, ts, ts),
        )
        prod_id = cur.lastrowid
        # 이력 기록
        con.execute(
            "INSERT INTO prepacking_logs (production_id, action, new_value, created_at) VALUES (?, 'create', ?, ?)",
            (prod_id, json.dumps({"produced_qty": produced_qty, "location": location}, ensure_ascii=False), ts),
        )
        con.commit()
    return prod_id


def use_production(production_id: int, use_qty: int, changed_by: str = "") -> Dict[str, Any]:
    """프리패킹 사용 (수동 차감)."""
    ts = now_str()
    with get_connection() as con:
        row = con.execute(
            "SELECT remaining_qty, status FROM prepacking_productions WHERE id=?",
            (production_id,),
        ).fetchone()
        if not row:
            return {"success": False, "error": "제작 기록을 찾을 수 없습니다."}
        remaining, status = row
        if status not in ("active", "carried", "held"):
            return {"success": False, "error": f"현재 상태({status})에서는 사용할 수 없습니다."}
        if use_qty > remaining:
            return {"success": False, "error": f"잔여 수량({remaining})보다 많이 사용할 수 없습니다."}

        new_remaining = remaining - use_qty
        new_status = "depleted" if new_remaining == 0 else status
        con.execute(
            "UPDATE prepacking_productions SET remaining_qty=?, status=?, updated_at=? WHERE id=?",
            (new_remaining, new_status, ts, production_id),
        )
        con.execute(
            "INSERT INTO prepacking_logs (production_id, action, field_changed, old_value, new_value, changed_by, created_at) VALUES (?, 'use', 'remaining_qty', ?, ?, ?, ?)",
            (production_id, str(remaining), str(new_remaining), changed_by, ts),
        )
        con.commit()
    return {"success": True, "remaining_qty": new_remaining, "status": new_status}


def update_production_status(production_id: int, new_status: str, changed_by: str = "") -> Dict[str, Any]:
    """프리패킹 상태 변경."""
    valid = {"active", "carried", "held", "disassemble", "disassembled", "depleted"}
    if new_status not in valid:
        return {"success": False, "error": f"유효하지 않은 상태: {new_status}"}
    ts = now_str()
    with get_connection() as con:
        row = con.execute("SELECT status FROM prepacking_productions WHERE id=?", (production_id,)).fetchone()
        if not row:
            return {"success": False, "error": "제작 기록을 찾을 수 없습니다."}
        old_status = row[0]
        con.execute(
            "UPDATE prepacking_productions SET status=?, updated_at=? WHERE id=?",
            (new_status, ts, production_id),
        )
        con.execute(
            "INSERT INTO prepacking_logs (production_id, action, field_changed, old_value, new_value, changed_by, created_at) VALUES (?, 'status_change', 'status', ?, ?, ?, ?)",
            (production_id, old_status, new_status, changed_by, ts),
        )
        con.commit()
    return {"success": True, "old_status": old_status, "new_status": new_status}


def update_production_location(production_id: int, new_location: str, changed_by: str = "") -> Dict[str, Any]:
    """로케이션 변경."""
    ts = now_str()
    with get_connection() as con:
        row = con.execute("SELECT location FROM prepacking_productions WHERE id=?", (production_id,)).fetchone()
        if not row:
            return {"success": False, "error": "제작 기록을 찾을 수 없습니다."}
        old_loc = row[0]
        con.execute(
            "UPDATE prepacking_productions SET location=?, updated_at=? WHERE id=?",
            (new_location, ts, production_id),
        )
        con.execute(
            "INSERT INTO prepacking_logs (production_id, action, field_changed, old_value, new_value, changed_by, created_at) VALUES (?, 'location_change', 'location', ?, ?, ?, ?)",
            (production_id, old_loc, new_location, changed_by, ts),
        )
        con.commit()
    return {"success": True, "old_location": old_loc, "new_location": new_location}


def get_active_productions(vendor: Optional[str] = None) -> List[Dict]:
    """활성 프리패킹 재고 조회."""
    with get_connection() as con:
        if vendor:
            rows = con.execute(
                """SELECT id, vendor, target_date, combo_key, combo_detail,
                          predicted_qty, produced_qty, remaining_qty, location, status, created_at
                   FROM prepacking_productions
                   WHERE vendor=? AND status IN ('active','carried','held')
                   ORDER BY target_date DESC, combo_key""",
                (vendor,),
            ).fetchall()
        else:
            rows = con.execute(
                """SELECT id, vendor, target_date, combo_key, combo_detail,
                          predicted_qty, produced_qty, remaining_qty, location, status, created_at
                   FROM prepacking_productions
                   WHERE status IN ('active','carried','held')
                   ORDER BY vendor, target_date DESC, combo_key"""
            ).fetchall()
    return [
        {
            "id": r[0], "vendor": r[1], "target_date": r[2], "combo_key": r[3],
            "combo_detail": r[4], "predicted_qty": r[5], "produced_qty": r[6],
            "remaining_qty": r[7], "location": r[8], "status": r[9], "created_at": r[10],
        }
        for r in rows
    ]


def get_productions_by_date(vendor: str, target_date: date) -> List[Dict]:
    """특정 날짜의 제작 기록 조회."""
    with get_connection() as con:
        rows = con.execute(
            """SELECT id, combo_key, combo_detail, predicted_qty, produced_qty,
                      remaining_qty, location, status, created_at
               FROM prepacking_productions
               WHERE vendor=? AND target_date=?
               ORDER BY combo_key""",
            (vendor, target_date.isoformat()),
        ).fetchall()
    return [
        {
            "id": r[0], "combo_key": r[1], "combo_detail": r[2], "predicted_qty": r[3],
            "produced_qty": r[4], "remaining_qty": r[5], "location": r[6], "status": r[7],
            "created_at": r[8],
        }
        for r in rows
    ]


# ─────────────────────────────────────
# 7. 미사용분 판정 (오늘의 지시)
# ─────────────────────────────────────

def generate_daily_instructions(vendor: str, today: Optional[date] = None) -> Dict[str, Any]:
    """
    오늘의 프리패킹 지시 생성.
    - 유지 안내 (내일도 필요한 조합)
    - 해체 지시 (유지기간 초과)
    - 신규 제작 추천 (유지분 차감)
    """
    if today is None:
        today = date.today()
    tomorrow = today + timedelta(days=1)
    settings = get_settings(vendor)
    retention_days = settings["retention_days"]

    # 1) 현재 활성 재고
    active = get_active_productions(vendor)

    # 2) 내일 예측
    tomorrow_preds = predict_for_date(vendor, tomorrow)
    tomorrow_keys = {p["combo_key"]: p for p in tomorrow_preds}

    carry_list = []
    disassemble_list = []
    hold_list = []

    for prod in active:
        if prod["remaining_qty"] <= 0:
            continue
        key = prod["combo_key"]
        prod_date = datetime.strptime(prod["target_date"], "%Y-%m-%d").date() if isinstance(prod["target_date"], str) else prod["target_date"]
        age_days = (today - prod_date).days

        if key in tomorrow_keys:
            carry_list.append({**prod, "tomorrow_predicted": tomorrow_keys[key]["predicted_qty"]})
        elif age_days >= retention_days:
            disassemble_list.append({**prod, "age_days": age_days})
        else:
            hold_list.append({**prod, "age_days": age_days, "expires_in": retention_days - age_days})

    # 3) 신규 제작 추천 (유지분 차감)
    carry_remaining: Dict[str, int] = {}
    for c in carry_list:
        carry_remaining[c["combo_key"]] = carry_remaining.get(c["combo_key"], 0) + c["remaining_qty"]

    new_production = []
    for pred in tomorrow_preds:
        existing = carry_remaining.get(pred["combo_key"], 0)
        needed = max(0, pred["predicted_qty"] - existing)
        if needed > 0:
            new_production.append({
                "combo_key": pred["combo_key"],
                "combo_detail": pred["combo_detail"],
                "predicted_qty": pred["predicted_qty"],
                "existing_qty": existing,
                "new_qty": needed,
            })

    return {
        "vendor": vendor,
        "date": today.isoformat(),
        "tomorrow": tomorrow.isoformat(),
        "carry": carry_list,
        "hold": hold_list,
        "disassemble": disassemble_list,
        "new_production": new_production,
    }


# ─────────────────────────────────────
# 8. 정확도 비교
# ─────────────────────────────────────

def update_actual_qty(vendor: str, target_date: date) -> Dict[str, Any]:
    """
    예측 대비 실제 출고 수량 업데이트 + MAPE 계산.
    배송통계에서 해당 날짜의 실제 조합 수량을 추출하여 비교.
    """
    analysis = analyze_combinations(vendor, target_date, target_date)
    actual_map: Dict[str, int] = {}
    for combo in analysis.get("combos", []):
        actual_map[combo["combo_key"]] = combo["count"]

    with get_connection() as con:
        preds = con.execute(
            "SELECT id, combo_key, predicted_qty, ai_adjusted_qty FROM prepacking_predictions WHERE vendor=? AND target_date=?",
            (vendor, target_date.isoformat()),
        ).fetchall()

        updated = 0
        total_mape = 0.0
        count_mape = 0

        for pid, key, pred_qty, ai_qty in preds:
            actual = actual_map.get(key, 0)
            effective_pred = ai_qty if ai_qty is not None else pred_qty
            mape = abs(effective_pred - actual) / max(actual, 1) * 100 if actual > 0 else None
            con.execute(
                "UPDATE prepacking_predictions SET actual_qty=?, mape=? WHERE id=?",
                (actual, mape, pid),
            )
            updated += 1
            if mape is not None:
                total_mape += mape
                count_mape += 1

        con.commit()

    avg_mape = total_mape / count_mape if count_mape > 0 else None
    return {
        "vendor": vendor,
        "target_date": target_date.isoformat(),
        "predictions_updated": updated,
        "avg_mape": round(avg_mape, 2) if avg_mape is not None else None,
    }


def get_accuracy_history(vendor: str, limit: int = 30) -> List[Dict]:
    """정확도 이력 조회."""
    with get_connection() as con:
        rows = con.execute(
            """SELECT target_date,
                      COUNT(*) as combo_count,
                      AVG(mape) as avg_mape,
                      SUM(predicted_qty) as total_predicted,
                      SUM(COALESCE(ai_adjusted_qty, predicted_qty)) as total_ai_predicted,
                      SUM(actual_qty) as total_actual
               FROM prepacking_predictions
               WHERE vendor=? AND actual_qty IS NOT NULL
               GROUP BY target_date
               ORDER BY target_date DESC
               LIMIT ?""",
            (vendor, limit),
        ).fetchall()
    return [
        {
            "target_date": r[0], "combo_count": r[1],
            "avg_mape": round(r[2], 2) if r[2] is not None else None,
            "total_predicted": r[3], "total_ai_predicted": r[4], "total_actual": r[5],
        }
        for r in rows
    ]


# ─────────────────────────────────────
# 9. 효율 지표
# ─────────────────────────────────────

def get_efficiency_stats(vendor: str, days: int = 30) -> Dict[str, Any]:
    """프리패킹 효율 지표."""
    d_from = (date.today() - timedelta(days=days)).isoformat()
    with get_connection() as con:
        row = con.execute(
            """SELECT
                 COUNT(*) as total,
                 SUM(produced_qty) as total_produced,
                 SUM(produced_qty - remaining_qty) as total_used,
                 SUM(CASE WHEN status='depleted' THEN 1 ELSE 0 END) as depleted_count,
                 SUM(CASE WHEN status='disassembled' THEN 1 ELSE 0 END) as disassembled_count
               FROM prepacking_productions
               WHERE vendor=? AND target_date >= ?""",
            (vendor, d_from),
        ).fetchone()

    if not row or row[0] == 0:
        return {"total": 0, "utilization_rate": 0, "waste_rate": 0}

    total, total_produced, total_used, depleted, disassembled = row
    total_produced = total_produced or 0
    total_used = total_used or 0

    utilization = (total_used / total_produced * 100) if total_produced > 0 else 0
    waste = (disassembled / total * 100) if total > 0 else 0

    return {
        "total": total,
        "total_produced": total_produced,
        "total_used": total_used,
        "depleted_count": depleted or 0,
        "disassembled_count": disassembled or 0,
        "utilization_rate": round(utilization, 1),
        "waste_rate": round(waste, 1),
    }


# ─────────────────────────────────────
# 10. 로케이션 자동완성
# ─────────────────────────────────────

def suggest_locations(vendor: str, prefix: str = "", limit: int = 10) -> List[str]:
    """공급처별 최근 사용 로케이션 제안."""
    with get_connection() as con:
        if prefix:
            rows = con.execute(
                """SELECT DISTINCT location FROM prepacking_productions
                   WHERE vendor=? AND location LIKE ? AND location != ''
                   ORDER BY updated_at DESC LIMIT ?""",
                (vendor, f"{prefix}%", limit),
            ).fetchall()
        else:
            rows = con.execute(
                """SELECT DISTINCT location FROM prepacking_productions
                   WHERE vendor=? AND location != ''
                   ORDER BY updated_at DESC LIMIT ?""",
                (vendor, limit),
            ).fetchall()
    return [r[0] for r in rows]


# ─────────────────────────────────────
# 11. 공급처 목록 (프리패킹용)
# ─────────────────────────────────────

def get_vendors_with_data() -> List[str]:
    """배송통계에 데이터가 있는 공급처 목록."""
    with get_connection() as con:
        rows = con.execute(
            "SELECT DISTINCT 공급처 FROM shipping_stats WHERE 공급처 IS NOT NULL AND 공급처 != '' ORDER BY 공급처"
        ).fetchall()
    return [r[0] for r in rows]
