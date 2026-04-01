"""
backend/app/api/invoice_analytics.py - 청구금액 분석 API
───────────────────────────────────────────────────
월별 청구금액 추이, 항목(카테고리)별 월별 추이, 거래처별 월별 추이
"""

from fastapi import APIRouter
from typing import Optional
import pandas as pd

from logic.db import get_connection

router = APIRouter(prefix="/invoice-analytics", tags=["invoice-analytics"])


def _categorize(name: str) -> str:
    n = (name or "").lower()
    if "보관료" in n or "보관" in n:
        return "보관료"
    if "택배" in n:
        return "택배요금"
    if "기본" in n and ("출고" in n or "출고비" in n):
        return "기본출고비"
    if "박스" in n or "봉투" in n:
        return "박스/봉투"
    if "입고" in n and "검수" in n:
        return "입고검수"
    if "도서산간" in n:
        return "도서산간"
    if "합포장" in n:
        return "합포장"
    if "바코드" in n:
        return "바코드"
    if "완충" in n:
        return "완충작업"
    if "반품" in n:
        return "반품"
    if "영상" in n or "촬영" in n:
        return "영상촬영"
    return "기타"


@router.get("/monthly-trend")
async def monthly_trend():
    """월별 청구금액 추이 (총액 + 인보이스 건수)"""
    with get_connection() as con:
        df = pd.read_sql("""
            SELECT
                strftime('%Y-%m', i.period_from) AS period,
                COUNT(*)                         AS invoice_count,
                SUM(i.total_amount)              AS total_amount
            FROM invoices i
            WHERE i.period_from IS NOT NULL
            GROUP BY period
            ORDER BY period
        """, con)

    if df.empty:
        return []

    df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").fillna(0).astype(int)
    df["growth"] = df["total_amount"].pct_change() * 100

    result = []
    for _, r in df.iterrows():
        result.append({
            "period": r["period"],
            "invoice_count": int(r["invoice_count"]),
            "total_amount": int(r["total_amount"]),
            "growth": round(r["growth"], 1) if pd.notna(r["growth"]) else None,
        })
    return result


@router.get("/monthly-by-category")
async def monthly_by_category():
    """항목(카테고리)별 월별 청구금액"""
    with get_connection() as con:
        df = pd.read_sql("""
            SELECT
                strftime('%Y-%m', i.period_from) AS period,
                ii.item_name,
                SUM(ii.amount)  AS amount,
                SUM(ii.qty)     AS qty
            FROM invoice_items ii
            JOIN invoices i ON ii.invoice_id = i.invoice_id
            WHERE i.period_from IS NOT NULL
            GROUP BY period, ii.item_name
        """, con)

    if df.empty:
        return {"periods": [], "categories": [], "data": []}

    df["category"] = df["item_name"].apply(_categorize)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

    pivot = df.groupby(["period", "category"])["amount"].sum().reset_index()
    periods = sorted(pivot["period"].unique().tolist())
    categories = sorted(pivot["category"].unique().tolist())

    data = []
    for p in periods:
        row = {"period": p}
        sub = pivot[pivot["period"] == p]
        for _, r in sub.iterrows():
            row[r["category"]] = int(r["amount"])
        for cat in categories:
            row.setdefault(cat, 0)
        data.append(row)

    return {"periods": periods, "categories": categories, "data": data}


@router.get("/monthly-by-vendor")
async def monthly_by_vendor():
    """거래처별 월별 청구금액"""
    with get_connection() as con:
        df = pd.read_sql("""
            SELECT
                strftime('%Y-%m', i.period_from) AS period,
                COALESCE(v.name, v.vendor, i.vendor_id) AS vendor_name,
                SUM(i.total_amount) AS total_amount
            FROM invoices i
            LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
            WHERE i.period_from IS NOT NULL
            GROUP BY period, vendor_name
            ORDER BY period
        """, con)

    if df.empty:
        return {"periods": [], "vendors": [], "data": []}

    df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").fillna(0)

    periods = sorted(df["period"].unique().tolist())
    vendors = sorted(df["vendor_name"].dropna().unique().tolist())

    data = []
    for p in periods:
        row = {"period": p}
        sub = df[df["period"] == p]
        for _, r in sub.iterrows():
            row[str(r["vendor_name"])] = int(r["total_amount"])
        for v in vendors:
            row.setdefault(v, 0)
        data.append(row)

    vendor_totals = df.groupby("vendor_name")["total_amount"].sum().sort_values(ascending=False)
    vendors_sorted = vendor_totals.index.tolist()

    return {"periods": periods, "vendors": vendors_sorted, "data": data}


@router.get("/summary")
async def analytics_summary():
    """전체 분석 요약 (총 기간, 총 금액, 평균 월 청구액 등)"""
    with get_connection() as con:
        row = con.execute("""
            SELECT
                COUNT(*)                         AS total_invoices,
                COALESCE(SUM(total_amount), 0)   AS total_amount,
                COUNT(DISTINCT strftime('%Y-%m', period_from)) AS total_months,
                MIN(period_from) AS first_period,
                MAX(period_from) AS last_period
            FROM invoices
            WHERE period_from IS NOT NULL
        """).fetchone()

    total_invoices = row[0] or 0
    total_amount = int(row[1] or 0)
    total_months = row[2] or 1
    avg_monthly = int(total_amount / total_months) if total_months > 0 else 0

    return {
        "total_invoices": total_invoices,
        "total_amount": total_amount,
        "total_months": total_months,
        "avg_monthly_amount": avg_monthly,
        "first_period": str(row[3])[:7] if row[3] else None,
        "last_period": str(row[4])[:7] if row[4] else None,
    }
