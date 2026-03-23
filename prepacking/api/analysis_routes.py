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
