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


def _is_option_only(name: str) -> bool:
    """[블랙], [화이트] 등 대괄호로만 감싸진 옵션명인지 판별."""
    return bool(re.match(r"^\[.+\]$", name.strip()))


def parse_admin_product_qty(raw: str) -> List[Dict[str, Any]]:
    """
    어드민상품명수량 컬럼 파싱.
    예: "닭가슴살---5, 오리안심---5" → [{"name": "닭가슴살", "qty": 5}, ...]
    
    옵션 처리:
    - "[블랙]---1, 허밍 레이스 티셔츠---1" 같은 경우
      [블랙]은 옵션이므로 다음 상품명에 붙여서 "허밍 레이스 티셔츠 [블랙]"으로 합침.
    - 옵션이 상품명 뒤에 오는 경우도 처리.
    """
    if not raw or pd.isna(raw):
        return []
    raw = str(raw).strip()
    raw_items: List[Dict[str, Any]] = []
    for part in re.split(r"[,\n]", raw):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(.+?)---+(\d+)$", part)
        if m:
            raw_items.append({"name": _normalize_text(m.group(1)), "qty": int(m.group(2))})
            continue
        m = re.match(r"^(.+?)\s*[x×\*]\s*(\d+)$", part, re.IGNORECASE)
        if m:
            raw_items.append({"name": _normalize_text(m.group(1)), "qty": int(m.group(2))})
            continue
        raw_items.append({"name": _normalize_text(part), "qty": 1})

    # 옵션 병합: [대괄호] 항목을 인접 상품명에 합침
    if not raw_items:
        return []

    merged: List[Dict[str, Any]] = []
    pending_options: List[str] = []

    for item in raw_items:
        if _is_option_only(item["name"]):
            pending_options.append(item["name"])
        else:
            name = item["name"]
            # 앞에 대기 중인 옵션이 있으면 현재 상품명에 붙임
            if pending_options:
                name = f"{name} {' '.join(pending_options)}"
                pending_options.clear()
            merged.append({"name": name, "qty": item["qty"]})

    # 끝에 남은 옵션이 있으면 마지막 상품에 붙임
    if pending_options and merged:
        merged[-1]["name"] = f"{merged[-1]['name']} {' '.join(pending_options)}"
    elif pending_options:
        for opt in pending_options:
            merged.append({"name": opt, "qty": 1})

    return merged


def build_combo_key(items: List[Dict[str, Any]]) -> str:
    """
    SKU 목록 → 정렬된 combo_key 생성.
    예: [{"name":"오리","qty":5},{"name":"닭","qty":3}] → "닭:3|오리:5"
    """
    if not items:
        return ""
    sorted_items = sorted(items, key=lambda x: x["name"])
    return "|".join(f"{it['name']}:{it['qty']}" for it in sorted_items)


def build_combo_detail(
    items: List[Dict[str, Any]],
    barcode_map: Optional[Dict[str, str]] = None,
    code_map: Optional[Dict[str, str]] = None,
) -> str:
    """combo_detail JSON 생성 (제품명, 바코드, 코드, 수량)."""
    details = []
    for it in sorted(items, key=lambda x: x["name"]):
        d: Dict[str, Any] = {"name": it["name"], "qty": it["qty"]}
        if barcode_map and it["name"] in barcode_map:
            d["barcode"] = barcode_map[it["name"]]
        if code_map and it["name"] in code_map:
            d["code"] = code_map[it["name"]]
        details.append(d)
    return json.dumps(details, ensure_ascii=False)


# ─────────────────────────────────────
# 3. 조합 분석
# ─────────────────────────────────────

def analyze_combinations(
    vendor: str,
    d_from: date,
    d_to: date,
) -> Dict[str, Any]:
    """
    배송통계에서 공급처별 SKU 조합을 추출·분석.
    Returns:
        {
            "vendor": str,
            "total_orders": int,
            "multi_item_orders": int,
            "combos": [{"combo_key", "combo_detail", "count", "day_counts": {0..6: int}}],
            "data_weeks": int,
        }
    """
    with get_connection() as con:
        df = pd.read_sql("SELECT * FROM shipping_stats", con)
        df.columns = [c.strip() for c in df.columns]

        alias_df = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor = ? AND file_type = 'shipping_stats'",
            con, params=(vendor,),
        )
    name_list = [vendor] + alias_df["alias"].tolist()

    # 날짜 컬럼 감지
    date_col = None
    for c in ["배송일", "송장등록일", "출고일자"]:
        if c in df.columns:
            date_col = c
            break
    if not date_col:
        return {"vendor": vendor, "total_orders": 0, "multi_item_orders": 0, "combos": [], "data_weeks": 0}

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df[(df[date_col] >= pd.to_datetime(d_from)) & (df[date_col] <= pd.to_datetime(d_to))]

    if "공급처" in df.columns:
        df = df[df["공급처"].isin(name_list)]

    # 중복 제거
    for key in ("송장번호", "운송장번호"):
        if key in df.columns:
            df = df.drop_duplicates(subset=[key])
            break

    total_orders = len(df)

    # 어드민상품명수량 파싱
    admin_col = None
    for c in ["어드민상품명수량", "어드민상품명 수량"]:
        if c in df.columns:
            admin_col = c
            break

    if not admin_col:
        return {"vendor": vendor, "total_orders": total_orders, "multi_item_orders": 0, "combos": [], "data_weeks": 0}

    # 바코드·코드 매핑 구축
    barcode_map: Dict[str, str] = {}
    code_map: Dict[str, str] = {}
    if "상품바코드" in df.columns and "상품명" in df.columns:
        for _, row in df[["상품명", "상품바코드"]].dropna().drop_duplicates().iterrows():
            barcode_map[_normalize_text(str(row["상품명"]))] = str(row["상품바코드"])
    if "어드민상품코드" in df.columns and "상품명" in df.columns:
        for _, row in df[["상품명", "어드민상품코드"]].dropna().drop_duplicates().iterrows():
            code_map[_normalize_text(str(row["상품명"]))] = str(row["어드민상품코드"])

    # 조합 추출
    combo_counter: Counter = Counter()
    combo_day_counter: Dict[str, Counter] = defaultdict(Counter)
    combo_detail_cache: Dict[str, str] = {}
    multi_item_count = 0

    for _, row in df.iterrows():
        items = parse_admin_product_qty(row.get(admin_col, ""))
        if len(items) < 2:
            continue
        multi_item_count += 1
        key = build_combo_key(items)
        combo_counter[key] += 1
        dow = row[date_col].weekday() if pd.notna(row[date_col]) else 0
        combo_day_counter[key][dow] += 1
        if key not in combo_detail_cache:
            combo_detail_cache[key] = build_combo_detail(items, barcode_map, code_map)

    # 데이터 기간 (주 수)
    if len(df) > 0 and pd.notna(df[date_col]).any():
        min_d = df[date_col].min()
        max_d = df[date_col].max()
        data_weeks = max(1, (max_d - min_d).days // 7)
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


def _load_filtered_df(vendor: str, d_from: date, d_to: date):
    """배송통계 로드 + 공급처 필터 + 중복 제거. (date_col, admin_col, df) 반환."""
    with get_connection() as con:
        df = pd.read_sql("SELECT * FROM shipping_stats", con)
        df.columns = [c.strip() for c in df.columns]
        alias_df = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor = ? AND file_type = 'shipping_stats'",
            con, params=(vendor,),
        )
    name_list = [vendor] + alias_df["alias"].tolist()

    date_col = None
    for c in ["배송일", "송장등록일", "출고일자"]:
        if c in df.columns:
            date_col = c
            break
    if not date_col:
        return None, None, pd.DataFrame()

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df[(df[date_col] >= pd.to_datetime(d_from)) & (df[date_col] <= pd.to_datetime(d_to))]
    if "공급처" in df.columns:
        df = df[df["공급처"].isin(name_list)]
    for key in ("송장번호", "운송장번호"):
        if key in df.columns:
            df = df.drop_duplicates(subset=[key])
            break

    admin_col = None
    for c in ["어드민상품명수량", "어드민상품명 수량"]:
        if c in df.columns:
            admin_col = c
            break

    return date_col, admin_col, df


def predict_for_date(
    vendor: str,
    target_date: date,
    weeks_back: int = 8,
) -> List[Dict[str, Any]]:
    """
    특정 날짜의 프리패킹 추천 목록 생성 (통계 기반).
    같은 요일 데이터가 2주 미만이면 전체 요일 일평균으로 폴백.
    """
    settings = get_settings(vendor)
    target_dow = target_date.weekday()

    d_to = target_date - timedelta(days=1)
    d_from = target_date - timedelta(weeks=weeks_back)

    date_col, admin_col, df = _load_filtered_df(vendor, d_from, d_to)
    if date_col is None or admin_col is None or df.empty:
        return []

    # 1차 시도: 같은 요일만
    dow_df = df[df[date_col].dt.weekday == target_dow]
    dow_weeks = dow_df[date_col].dt.isocalendar().week.nunique() if not dow_df.empty else 0
    use_all_days = dow_weeks < 2

    if use_all_days:
        # 전체 요일 사용, 일평균으로 계산
        work_df = df.copy()
        total_days = work_df[date_col].dt.date.nunique()
        if total_days == 0:
            return []
    else:
        work_df = dow_df
        total_days = 0  # 주별 그룹핑 사용

    combo_total_freq: Counter = Counter()
    combo_detail_cache: Dict[str, str] = {}

    if use_all_days:
        # 전체 기간 빈도 → 일평균으로 예측
        for _, row in work_df.iterrows():
            items = parse_admin_product_qty(row.get(admin_col, ""))
            if len(items) < settings["min_sku_count"]:
                continue
            key = build_combo_key(items)
            combo_total_freq[key] += 1
            if key not in combo_detail_cache:
                combo_detail_cache[key] = build_combo_detail(items)

        predictions = []
        for key, freq in combo_total_freq.items():
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
        work_df = work_df.copy()
        work_df["_week"] = work_df[date_col].dt.isocalendar().week.astype(int)
        weeks_sorted = sorted(work_df["_week"].unique())
        combo_weekly: Dict[str, List[int]] = defaultdict(lambda: [0] * len(weeks_sorted))

        for week_idx, week_num in enumerate(weeks_sorted):
            week_df = work_df[work_df["_week"] == week_num]
            for _, row in week_df.iterrows():
                items = parse_admin_product_qty(row.get(admin_col, ""))
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
