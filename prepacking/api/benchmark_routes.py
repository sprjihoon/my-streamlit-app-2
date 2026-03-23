"""
benchmark_routes — 전체 업체 × N일 백테스트 일괄 실행
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from prepacking.database import get_pp_connection
from prepacking.services.prediction.backtest_service import run_backtest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pp/benchmark", tags=["benchmark"])


@router.get("/top-suppliers")
def get_top_suppliers(limit: int = 10) -> list[dict]:
    """출고량 기준 상위 업체 목록."""
    with get_pp_connection() as con:
        cur = con.execute(
            "SELECT TRIM(supplier_name) AS name, SUM(qty) AS total_qty, "
            "COUNT(DISTINCT shipping_date) AS active_days, "
            "COUNT(DISTINCT product_name || '||' || COALESCE(option_name,'')) AS sku_count "
            "FROM pp_shipping_stats "
            "WHERE supplier_name IS NOT NULL AND TRIM(supplier_name) != '' "
            "GROUP BY TRIM(supplier_name) "
            "ORDER BY total_qty DESC LIMIT ?",
            (limit,),
        )
        return [
            {"rank": i + 1, "supplier": r[0], "total_qty": r[1],
             "active_days": r[2], "sku_count": r[3]}
            for i, r in enumerate(cur.fetchall())
        ]


@router.post("/run")
def run_benchmark(body: dict | None = None) -> dict:
    """
    전체 업체 × 지정 날짜들에 대해 백테스트를 실행하고 결과를 반환.
    body: {"dates": ["2026-02-02", ...], "suppliers": ["아바마", ...] (optional)}
    """
    dates = (body or {}).get("dates", [
        "2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06",
    ])
    requested_suppliers = (body or {}).get("suppliers", [])

    top_n = (body or {}).get("top_n", 0)

    if requested_suppliers:
        suppliers = requested_suppliers
    else:
        with get_pp_connection() as con:
            cur = con.execute(
                "SELECT TRIM(supplier_name) AS name, SUM(qty) AS total "
                "FROM pp_shipping_stats "
                "WHERE supplier_name IS NOT NULL AND TRIM(supplier_name) != '' "
                "GROUP BY TRIM(supplier_name) "
                "ORDER BY total DESC"
            )
            rows = cur.fetchall()
            suppliers = [r[0] for r in rows]
            if top_n > 0:
                suppliers = suppliers[:top_n]

    results = []
    supplier_avgs = {}

    for sup in suppliers:
        sup_results = []
        for d in dates:
            try:
                r = run_backtest(sup, d)
                if "error" in r:
                    continue
                s = r["summary"]
                sup_results.append({
                    "date": d,
                    "accuracy": s["accuracy"],
                    "acc_volume": s["acc_volume"],
                    "acc_sku_match": s["acc_sku_match"],
                    "acc_qty_close": s["acc_qty_close"],
                    "total_predicted": s["total_predicted"],
                    "total_actual": s["total_actual"],
                    "matched": s["matched"],
                    "item_count": s["item_count"],
                })
            except Exception as exc:
                logger.warning("Benchmark %s %s failed: %s", sup, d, exc)

        if sup_results:
            avg_acc = sum(r["accuracy"] for r in sup_results) / len(sup_results)
            avg_vol = sum(r["acc_volume"] for r in sup_results) / len(sup_results)
            avg_sku = sum(r["acc_sku_match"] for r in sup_results) / len(sup_results)
            avg_qty = sum(r["acc_qty_close"] for r in sup_results) / len(sup_results)
            supplier_avgs[sup] = {
                "avg_accuracy": round(avg_acc, 1),
                "avg_volume": round(avg_vol, 1),
                "avg_sku_match": round(avg_sku, 1),
                "avg_qty_close": round(avg_qty, 1),
                "test_days": len(sup_results),
                "details": sup_results,
            }
            results.append({
                "supplier": sup,
                "avg_accuracy": round(avg_acc, 1),
                "test_days": len(sup_results),
            })

    all_accs = [v["avg_accuracy"] for v in supplier_avgs.values()]
    overall_avg = round(sum(all_accs) / len(all_accs), 1) if all_accs else 0.0

    return {
        "overall_avg_accuracy": overall_avg,
        "supplier_count": len(supplier_avgs),
        "total_tests": sum(v["test_days"] for v in supplier_avgs.values()),
        "target": 70.0,
        "gap": round(70.0 - overall_avg, 1),
        "ranking": sorted(results, key=lambda x: x["avg_accuracy"], reverse=True),
        "details": supplier_avgs,
    }
