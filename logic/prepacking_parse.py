"""
logic/prepacking_parse.py - SKU 파싱 & 배송건 그룹핑
────────────────────────────────────────────────────
배송통계 데이터에서 SKU 아이템을 추출하고,
배송건 단위로 묶어 combo_key를 생성합니다.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .db import get_connection


# ── 안전 변환 유틸 ──────────────────

def _safe_int(val, default: int = 1) -> int:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_str(val) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text).strip())


# ── 컬럼 감지 ───────────────────────

COL_RULES: List[Tuple[str, str]] = [
    ("주문번호",              "order"),
    ("상품명",                "product"),
    ("옵션",                  "option"),
    ("옵션정보",              "option"),
    ("수량",                  "qty"),
    ("내품수량",              "inner_qty"),
    ("상품바코드",            "barcode"),
    ("배송일",                "date"),
    ("송장등록일",            "date"),
    ("출고일자",              "date"),
    ("어드민상품명수량",      "admin_product_qty"),
    ("어드민상품명 수량",     "admin_product_qty"),
]


def detect_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """DataFrame에서 핵심 컬럼명을 자동 감지."""
    col_map: Dict[str, Optional[str]] = {
        "order": None, "product": None, "option": None,
        "qty": None, "inner_qty": None, "barcode": None,
        "date": None, "admin_product_qty": None,
    }
    lookup = {label: key for label, key in COL_RULES}
    for c in df.columns:
        key = lookup.get(c.strip())
        if key and (col_map[key] is None):
            col_map[key] = c
    return col_map


def find_invoice_col(df: pd.DataFrame) -> Optional[str]:
    for key in ("송장번호", "운송장번호"):
        if key in df.columns:
            return key
    return None


# ── 어드민상품명수량 파싱 ────────────

def parse_admin_product_qty(raw: str) -> List[Dict[str, Any]]:
    """
    어드민상품명수량 컬럼 파싱.
    - 줄바꿈(\\n)이 SKU 간 구분자
    - `---` 뒤의 숫자가 수량
    - 줄바꿈이 없으면 콤마 + `---숫자` 패턴으로 split
    """
    if not raw or (isinstance(raw, float) and math.isnan(raw)):
        return []
    raw = str(raw).strip()
    if not raw:
        return []

    lines = _split_admin_lines(raw)
    raw_items = _parse_lines_to_items(lines)
    if not raw_items:
        return []
    return _merge_option_items(raw_items)


def _split_admin_lines(raw: str) -> List[str]:
    if "\n" in raw:
        return [l.strip() for l in raw.split("\n") if l.strip()]

    parts = re.split(r"(---\s*\d+)\s*,\s*", raw)
    if len(parts) <= 1:
        return [raw]

    merged: List[str] = []
    i = 0
    while i < len(parts):
        if i + 1 < len(parts) and re.match(r"^---\s*\d+$", parts[i + 1]):
            merged.append(parts[i] + parts[i + 1])
            i += 2
        else:
            if parts[i].strip():
                merged.append(parts[i])
            i += 1
    return merged


def _parse_lines_to_items(lines: List[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.+?)---+\s*(\d+)\s*$", line)
        if m:
            items.append({"name": _normalize_text(m.group(1)), "qty": int(m.group(2))})
        else:
            items.append({"name": _normalize_text(line), "qty": 1})
    return items


def _merge_option_items(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """[옵션명]만으로 된 항목을 인접 상품에 병합."""
    merged: List[Dict[str, Any]] = []
    pending_options: List[str] = []

    for item in raw_items:
        if re.match(r"^\[.+\]$", item["name"]):
            if merged:
                merged[-1]["name"] = f"{merged[-1]['name']}, {item['name']}"
            else:
                pending_options.append(item["name"])
        else:
            name = item["name"]
            if pending_options:
                name = f"{name}, {', '.join(pending_options)}"
                pending_options.clear()
            merged.append({"name": name, "qty": item["qty"]})

    if pending_options and merged:
        merged[-1]["name"] = f"{merged[-1]['name']}, {', '.join(pending_options)}"
    elif pending_options:
        merged = [{"name": opt, "qty": 1} for opt in pending_options]

    return merged


# ── 행에서 아이템 추출 ──────────────

def extract_items_from_row(
    row: pd.Series,
    col_map: Dict[str, Optional[str]],
) -> List[Dict[str, Any]]:
    """한 행에서 SKU 아이템 리스트 추출."""
    admin_col = col_map.get("admin_product_qty")
    bc_col = col_map.get("barcode")

    if admin_col and admin_col in row.index:
        raw = _safe_str(row.get(admin_col, ""))
        if raw:
            items = parse_admin_product_qty(raw)
            if items:
                barcodes = _split_csv(row.get(bc_col, "")) if bc_col and bc_col in row.index else []
                for i, it in enumerate(items):
                    it["barcode"] = barcodes[i] if i < len(barcodes) else ""
                return items

    product_col = col_map.get("product")
    product = _safe_str(row.get(product_col, "")) if product_col else ""
    if not product:
        return []

    option_col = col_map.get("option")
    option = _safe_str(row.get(option_col, "")) if option_col else ""

    qty = _get_qty(row, col_map)
    name = f"{product} [{option}]" if option else product
    barcode = _safe_str(row.get(bc_col, "")) if bc_col and bc_col in row.index else ""
    return [{"name": name, "qty": qty, "barcode": barcode}]


def _split_csv(val) -> List[str]:
    s = _safe_str(val)
    return [v.strip() for v in s.split(",") if v.strip()] if s else []


def _get_qty(row: pd.Series, col_map: Dict[str, Optional[str]]) -> int:
    inner_col = col_map.get("inner_qty")
    if inner_col and inner_col in row.index:
        qty = _safe_int(row[inner_col], 0)
        if qty > 0:
            return qty
    qty_col = col_map.get("qty")
    if qty_col and qty_col in row.index:
        qty = _safe_int(row[qty_col], 1)
        if qty > 0:
            return qty
    return 1


# ── 배송건 그룹핑 ───────────────────

def group_shipments(
    df: pd.DataFrame,
    col_map: Dict[str, Optional[str]],
) -> List[Tuple[List[Dict[str, Any]], pd.Timestamp]]:
    """
    배송 건 단위로 SKU 아이템 목록을 구성.

    송장번호가 있으면 그룹핑, 없으면 행 단위.
    어드민상품명수량이 있으면 한 행에서 여러 SKU를 추출하므로,
    같은 송장의 여러 행도 하나의 배송건으로 합침.
    """
    date_col = col_map.get("date")
    invoice_col = find_invoice_col(df)

    if invoice_col:
        return _group_by_invoice(df, col_map, date_col, invoice_col)
    return _group_by_row(df, col_map, date_col)


def _group_by_invoice(
    df: pd.DataFrame,
    col_map: Dict[str, Optional[str]],
    date_col: Optional[str],
    invoice_col: str,
) -> List[Tuple[List[Dict[str, Any]], pd.Timestamp]]:
    shipments: List[Tuple[List[Dict[str, Any]], pd.Timestamp]] = []
    for inv_no, group in df.groupby(invoice_col, sort=False):
        if pd.isna(inv_no) or str(inv_no).strip() == "":
            for _, row in group.iterrows():
                items = extract_items_from_row(row, col_map)
                if items:
                    shipments.append((items, _get_date(row, date_col)))
            continue

        all_items: List[Dict[str, Any]] = []
        dt = pd.NaT
        for _, row in group.iterrows():
            all_items.extend(extract_items_from_row(row, col_map))
            if date_col and pd.notna(row.get(date_col)):
                dt = row[date_col]
        if all_items:
            shipments.append((all_items, dt))
    return shipments


def _group_by_row(
    df: pd.DataFrame,
    col_map: Dict[str, Optional[str]],
    date_col: Optional[str],
) -> List[Tuple[List[Dict[str, Any]], pd.Timestamp]]:
    shipments: List[Tuple[List[Dict[str, Any]], pd.Timestamp]] = []
    for _, row in df.iterrows():
        items = extract_items_from_row(row, col_map)
        if items:
            shipments.append((items, _get_date(row, date_col)))
    return shipments


def _get_date(row: pd.Series, date_col: Optional[str]) -> pd.Timestamp:
    if date_col and pd.notna(row.get(date_col)):
        return row[date_col]
    return pd.NaT


# ── combo key 생성 ──────────────────

def build_combo_key(items: List[Dict[str, Any]]) -> str:
    """SKU 목록 → 정렬된 combo_key. 예: "닭:3|오리:5" """
    if not items:
        return ""
    return "|".join(f"{it['name']}:{it['qty']}" for it in sorted(items, key=lambda x: x["name"]))


def build_combo_detail(items: List[Dict[str, Any]]) -> str:
    """combo_detail JSON 생성."""
    details = []
    for it in sorted(items, key=lambda x: x["name"]):
        d: Dict[str, Any] = {"name": it["name"], "qty": it["qty"]}
        if it.get("barcode"):
            d["barcode"] = it["barcode"]
        details.append(d)
    return json.dumps(details, ensure_ascii=False)


# ── 데이터 로드 ─────────────────────

def load_vendor_df(
    vendor: str, d_from, d_to, *, dedup_invoice: bool = False,
) -> Tuple[pd.DataFrame, Dict[str, Optional[str]]]:
    """배송통계 로드 → 공급처·날짜 필터."""
    with get_connection() as con:
        df = pd.read_sql("SELECT * FROM shipping_stats", con)
        df.columns = [c.strip() for c in df.columns]
        alias_df = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor = ? AND file_type = 'shipping_stats'",
            con, params=(vendor,),
        )
    name_list = [vendor] + alias_df["alias"].tolist()
    col_map = detect_columns(df)

    if not col_map["date"]:
        return pd.DataFrame(), col_map

    date_col = col_map["date"]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df[(df[date_col] >= pd.to_datetime(d_from)) & (df[date_col] <= pd.to_datetime(d_to))]

    if "공급처" in df.columns:
        df = df[df["공급처"].isin(name_list)]

    if dedup_invoice:
        inv_col = find_invoice_col(df)
        if inv_col:
            df = df.drop_duplicates(subset=[inv_col])

    return df.reset_index(drop=True), col_map
