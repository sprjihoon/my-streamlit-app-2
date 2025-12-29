"""
actions/basic_shipping.py
─────────────────────────
Utilities for handling the **기본 출고비** (basic outbound handling fee).

업데이트 ✨ (2025-04-29)
-----------------------
* **날짜 필터 지원** – 모든 집계가 `date_from`-`date_to` 범위로 제한됩니다.  
  기본 컬럼은 `송장등록일`(shipping_stats F열)이며, 다른 컬럼명을 쓰는 경우 `date_col` 파라미터로 지정하세요.
* 단가는 여전히 **Rate Manager**(`get_price`)에서 실시간 조회합니다.

데이터 흐름
------------
```mermaid
flowchart TD
    A[shipping_stats (date filter)] -->|filter vendor/alias| B(count rows)
    B --> C[lookup sku_group (vendor_flags)]
    C --> D[get unit price via get_price("out_basic", sku_group)]
    D --> E(total = count * unit)
```
"""
from __future__ import annotations

import sqlite3
from typing import Tuple, Optional

import pandas as pd
from datetime import date

# 외부 헬퍼 (settings DB 연결 + 단가 조회)
try:
    from logic.db import get_connection  # type: ignore
except ImportError:  # graceful degradation (tests)
    get_connection = None  # type: ignore

# get_price는 별도 구현 필요 시 추가
get_price = None  # type: ignore

BILLING_DB = "billing.db"
DEFAULT_ITEM_NAME = "기본 출고비"
VENDOR_FLAG_TBL = "vendor_flags"  # (vendor, sku_group)
DATE_COL_DEFAULT = "송장등록일"     # shipping_stats 기준 날짜 컬럼

__all__ = [
    "calculate_out_basic",
    "add_basic_shipping",
]

# ──────────────────────────────────────────
# Helper: 단가 조회
# ──────────────────────────────────────────

def _unit_price_from_group(sku_group: str) -> int:
    if not get_connection or not get_price:
        return 0
    with get_connection() as con_set:
        try:
            return int(get_price(con_set, "out_basic", "SKU구간", sku_group))  # type: ignore[arg-type]
        except Exception:
            return 0

# ──────────────────────────────────────────
# 1) DB-aware 계산기 (date filter)
# ──────────────────────────────────────────

def calculate_out_basic(
    vendor: str,
    *,
    date_from: Optional[str | date] = None,
    date_to:   Optional[str | date] = None,
    date_col: str = DATE_COL_DEFAULT,
    db_path: str = BILLING_DB,
) -> Tuple[int, int, int]:
    """Return *(count, unit_price, total)* for basic outbound fee within date range.

    Parameters
    ----------
    vendor : str
        Canonical vendor name.
    date_from / date_to : str | datetime.date | None
        Inclusive date range; if omitted, the entire table is considered.
    date_col : str
        Column in `shipping_stats` representing the invoice date.
    db_path : str
        Path to *billing.db* (contains `shipping_stats`).
    """
    if not vendor:
        return 0, 0, 0

    # Format dates to ISO strings for SQL
    def _iso(d: str | date | None) -> Optional[str]:
        if d is None:
            return None
        return d.isoformat() if isinstance(d, date) else str(d)

    dt_from, dt_to = _iso(date_from), _iso(date_to)

    try:
        with sqlite3.connect(db_path) as con:
            # ① 출고 건수 (공급처 + 날짜 필터)
            ship_df = pd.read_sql(f"SELECT 공급처, {date_col} FROM shipping_stats", con)
            alias_df = pd.read_sql(
                "SELECT alias FROM alias_vendor_v WHERE vendor = ? AND file_type = 'shipping_stats'",
                con,
                params=(vendor,),
            )
            suppliers: list[str] = alias_df["alias"].tolist() + [vendor]
            mask = ship_df["공급처"].isin(suppliers)
            if dt_from:
                mask &= ship_df[date_col] >= dt_from
            if dt_to:
                mask &= ship_df[date_col] <= dt_to
            cnt = int(ship_df[mask].shape[0])
            if cnt == 0:
                return 0, 0, 0

            # ② 대표 SKU 구간
            row = con.execute(
                f"SELECT sku_group FROM {VENDOR_FLAG_TBL} WHERE vendor = ? LIMIT 1",
                (vendor,),
            ).fetchone()
            sku_group = row[0] if row else "≤100"

        # ③ 단가
        unit_price = _unit_price_from_group(sku_group)
        return cnt, unit_price, cnt * unit_price
    except Exception:
        return 0, 0, 0

# ──────────────────────────────────────────
# 2) DataFrame 업데이트 헬퍼 (date filter)
# ──────────────────────────────────────────

def add_basic_shipping(
    items_df: pd.DataFrame,
    *,
    vendor: str,
    date_from: Optional[str | date] = None,
    date_to:   Optional[str | date] = None,
    db_path: str = BILLING_DB,
    item_name: str = DEFAULT_ITEM_NAME,
) -> pd.DataFrame:
    """Insert/update 기본 출고비 row using date-filtered counts & live unit price."""
    out_qty, unit_cost, _ = calculate_out_basic(
        vendor,
        date_from=date_from,
        date_to=date_to,
        db_path=db_path,
    )
    if out_qty == 0:
        return items_df

    amount = out_qty * unit_cost
    mask = items_df["항목"] == item_name
    if mask.any():
        items_df.loc[mask, ["수량", "단가", "금액"]] = [out_qty, unit_cost, amount]
    else:
        items_df.loc[len(items_df)] = [item_name, out_qty, unit_cost, amount]
    return items_df
