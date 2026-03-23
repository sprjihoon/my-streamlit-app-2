"""
data_loader — 시계열 데이터 로드 및 전처리
──────────────────────────────────────────
pp_shipping_stats에서 SKU별 일별 출하량 시계열을 구축.
날짜 갭을 0으로 채워 연속 시계열로 만든다.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import pandas as pd

from prepacking.common.utils import normalize_sku_name, safe_int, safe_str
from prepacking.database import get_pp_connection


def load_daily_series(
    supplier_name: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> pd.DataFrame:
    """
    SKU별 일별 출하량을 DataFrame으로 반환.
    columns: [date, sku_key, qty]
    date 갭은 0으로 채움.
    """
    with get_pp_connection() as con:
        query = """
            SELECT shipping_date, product_name, option_name, qty
            FROM pp_shipping_stats
            WHERE TRIM(supplier_name) = TRIM(?)
              AND shipping_date IS NOT NULL AND shipping_date != ''
        """
        params: list = [supplier_name.strip()]

        if date_from:
            query += " AND date(shipping_date) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(shipping_date) <= date(?)"
            params.append(date_to)

        rows = con.execute(query, params).fetchall()

    if not rows:
        return pd.DataFrame(columns=["date", "sku_key", "qty"])

    records = []
    for row in rows:
        ds = safe_str(row[0])[:10]
        pn = normalize_sku_name(row[1])
        on = normalize_sku_name(row[2])
        qty = max(0, safe_int(row[3], 0))
        records.append({"date": ds, "sku_key": f"{pn}||{on}", "qty": qty})

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.groupby(["date", "sku_key"], as_index=False)["qty"].sum()

    all_dates = pd.date_range(df["date"].min(), df["date"].max(), freq="D")
    all_skus = df["sku_key"].unique()
    idx = pd.MultiIndex.from_product([all_dates, all_skus], names=["date", "sku_key"])
    full = pd.DataFrame(index=idx).reset_index()
    full = full.merge(df, on=["date", "sku_key"], how="left")
    full["qty"] = full["qty"].fillna(0).astype(int)

    return full.sort_values(["sku_key", "date"]).reset_index(drop=True)


def get_available_date_range(supplier_name: str) -> tuple[str, str]:
    """해당 공급처의 데이터 시작/종료일을 반환."""
    with get_pp_connection() as con:
        row = con.execute(
            """
            SELECT MIN(date(shipping_date)), MAX(date(shipping_date))
            FROM pp_shipping_stats
            WHERE TRIM(supplier_name) = TRIM(?)
              AND shipping_date IS NOT NULL AND shipping_date != ''
            """,
            (supplier_name.strip(),),
        ).fetchone()
    if row and row[0] and row[1]:
        return row[0], row[1]
    return "", ""
