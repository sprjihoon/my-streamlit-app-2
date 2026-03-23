from __future__ import annotations

from fastapi import APIRouter

from prepacking.database import get_pp_connection
from prepacking.models.schemas import PPAnalysisRequest
from prepacking.services.analysis.repeat_combination_service import analyze_repeat_combinations
from prepacking.services.analysis.repeat_sku_service import analyze_repeat_skus
from prepacking.services.analysis.weekday_pattern_service import analyze_weekday_patterns

router = APIRouter(prefix="/pp/analysis", tags=["prepacking-analysis"])


def _resolve_dates(supplier_name: str, date_from: str, date_to: str) -> tuple[str, str]:
    """빈 날짜는 해당 공급처의 전체 데이터 범위로 대체."""
    if date_from and date_to:
        return date_from[:10], date_to[:10]
    with get_pp_connection() as con:
        cur = con.execute(
            "SELECT MIN(shipping_date), MAX(shipping_date) FROM pp_shipping_stats "
            "WHERE TRIM(supplier_name) = TRIM(?) AND shipping_date IS NOT NULL AND shipping_date != ''",
            (supplier_name.strip(),),
        )
        row = cur.fetchone()
    mn = (row[0] or "2000-01-01")[:10] if row else "2000-01-01"
    mx = (row[1] or "2099-12-31")[:10] if row else "2099-12-31"
    return date_from[:10] if date_from else mn, date_to[:10] if date_to else mx


@router.post("/repeat-skus")
def post_repeat_skus(body: PPAnalysisRequest) -> list[dict]:
    d_from, d_to = _resolve_dates(body.supplier_name, body.date_from, body.date_to)
    return analyze_repeat_skus(body.supplier_name, d_from, d_to, body.min_count)


@router.post("/repeat-combinations")
def post_repeat_combinations(body: PPAnalysisRequest) -> list[dict]:
    d_from, d_to = _resolve_dates(body.supplier_name, body.date_from, body.date_to)
    return analyze_repeat_combinations(body.supplier_name, d_from, d_to, body.min_count)


@router.post("/weekday-patterns")
def post_weekday_patterns(body: PPAnalysisRequest) -> dict:
    d_from, d_to = _resolve_dates(body.supplier_name, body.date_from, body.date_to)
    return analyze_weekday_patterns(body.supplier_name, d_from, d_to)


@router.get("/debug-data")
def debug_data(supplier: str = ""):
    """임시 디버그: DB 데이터 상태 확인."""
    with get_pp_connection() as con:
        total = con.execute("SELECT COUNT(*) FROM pp_shipping_stats").fetchone()[0]
        with_date = con.execute(
            "SELECT COUNT(*) FROM pp_shipping_stats WHERE shipping_date IS NOT NULL AND shipping_date != ''"
        ).fetchone()[0]
        sample_dates = con.execute(
            "SELECT DISTINCT shipping_date FROM pp_shipping_stats WHERE shipping_date IS NOT NULL AND shipping_date != '' LIMIT 10"
        ).fetchall()
        sample_suppliers = con.execute(
            "SELECT DISTINCT supplier_name FROM pp_shipping_stats LIMIT 10"
        ).fetchall()
        if supplier:
            sup_count = con.execute(
                "SELECT COUNT(*) FROM pp_shipping_stats WHERE TRIM(supplier_name) = TRIM(?)",
                (supplier.strip(),),
            ).fetchone()[0]
            sup_dates = con.execute(
                "SELECT DISTINCT shipping_date FROM pp_shipping_stats "
                "WHERE TRIM(supplier_name) = TRIM(?) AND shipping_date IS NOT NULL AND shipping_date != '' LIMIT 10",
                (supplier.strip(),),
            ).fetchall()
            sup_sample = con.execute(
                "SELECT shipping_date, product_name, option_name, qty FROM pp_shipping_stats "
                "WHERE TRIM(supplier_name) = TRIM(?) LIMIT 5",
                (supplier.strip(),),
            ).fetchall()
        else:
            sup_count = 0
            sup_dates = []
            sup_sample = []
    return {
        "total_rows": total,
        "rows_with_date": with_date,
        "sample_dates": [r[0] for r in sample_dates],
        "sample_suppliers": [r[0] for r in sample_suppliers],
        "supplier_filter": supplier,
        "supplier_row_count": sup_count,
        "supplier_dates": [r[0] for r in sup_dates],
        "supplier_sample_rows": [
            {"shipping_date": r[0], "product_name": r[1], "option_name": r[2], "qty": r[3]}
            for r in sup_sample
        ],
    }
