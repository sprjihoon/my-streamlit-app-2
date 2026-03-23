from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException

from prepacking.database import get_pp_connection
from prepacking.models.schemas import PPApprovalRequest, PPRecommendationRequest, PPWorkOrderRequest
from prepacking.services.approval.approval_service import (
    approve_recommendation,
    get_approval_history,
    hold_recommendation,
    modify_recommendation,
    reject_recommendation,
)
from prepacking.services.prediction import forecast_service
from prepacking.services.recommendation.recommendation_service import (
    generate_recommendations,
    get_recommendation_detail,
    get_recommendations,
)

router = APIRouter(prefix="/pp/recommendations", tags=["prepacking-recommendations"])

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


@router.post("/work-order")
def post_work_order(body: PPWorkOrderRequest) -> dict:
    """내일(또는 지정일) 프리패킹 작업 지시서를 생성. DB 저장 없이 바로 반환."""
    import logging
    logger = logging.getLogger(__name__)

    target = body.target_date
    try:
        td = dt.datetime.strptime(target[:10], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        td = dt.date.today() + dt.timedelta(days=1)
        target = td.isoformat()

    weekday_idx = td.weekday()
    weekday_name = WEEKDAY_KR[weekday_idx]

    if body.supplier_name:
        suppliers = [body.supplier_name.strip()]
    else:
        with get_pp_connection() as con:
            cur = con.execute(
                "SELECT DISTINCT TRIM(supplier_name) FROM pp_shipping_stats "
                "WHERE supplier_name IS NOT NULL AND TRIM(supplier_name) != '' "
                "ORDER BY supplier_name"
            )
            suppliers = [r[0] for r in cur.fetchall()]

    all_items: list[dict] = []
    debug_stats: dict = {"suppliers_total": len(suppliers), "preds_total": 0, "preds_positive": 0, "errors": 0}
    for sup in suppliers:
        try:
            preds = forecast_service.predict_for_date(sup, target)
        except Exception as exc:
            logger.warning("forecast failed for supplier=%s: %s", sup, exc)
            debug_stats["errors"] += 1
            continue
        debug_stats["preds_total"] += len(preds)
        for p in preds:
            qty = int(p.get("predicted_qty", 0))
            if qty <= 0:
                continue
            debug_stats["preds_positive"] += 1
            all_items.append({
                "supplier_name": sup,
                "target_type": p.get("target_type", "single_sku"),
                "target_name": p.get("target_name", ""),
                "target_code": p.get("target_code", ""),
                "combination_key": p.get("combination_key", ""),
                "predicted_qty": qty,
                "confidence_score": round(float(p.get("confidence_score", 0)), 3),
                "recent_7d_avg": round(float(p.get("recent_7d_avg", 0)), 1),
                "recent_30d_avg": round(float(p.get("recent_30d_avg", 0)), 1),
                "recent_same_weekday_avg": round(float(p.get("recent_same_weekday_avg", 0)), 1),
                "weekday_basis": weekday_idx,
                "frequency": int(p.get("frequency", 0)),
            })
    logger.warning("work-order debug: %s", debug_stats)

    all_items.sort(key=lambda x: (-x["predicted_qty"], -x["confidence_score"]))

    total_qty = sum(i["predicted_qty"] for i in all_items)
    combo_items = [i for i in all_items if i["target_type"] == "combination"]
    sku_items = [i for i in all_items if i["target_type"] != "combination"]

    return {
        "target_date": target,
        "weekday_name": weekday_name,
        "weekday_index": weekday_idx,
        "supplier_filter": body.supplier_name or "",
        "total_items": len(all_items),
        "total_predicted_qty": total_qty,
        "combination_count": len(combo_items),
        "single_sku_count": len(sku_items),
        "items": all_items,
        "_debug": debug_stats,
    }


@router.post("/generate")
def post_generate(body: PPRecommendationRequest) -> list[dict]:
    return generate_recommendations(
        body.supplier_name,
        body.target_date,
        body.source_upload_id,
    )


@router.get("/")
def list_recommendations(
    supplier_name: str,
    target_date: str | None = None,
    status: str | None = None,
) -> list[dict]:
    return get_recommendations(supplier_name, target_date, status)


@router.get("/{recommendation_id}")
def get_recommendation(recommendation_id: int) -> dict:
    row = get_recommendation_detail(recommendation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="recommendation_not_found")
    return row


@router.post("/{recommendation_id}/approve")
def post_approve(recommendation_id: int, body: PPApprovalRequest) -> dict:
    action = (body.action_type or "").strip().lower()
    try:
        if action == "approve":
            return approve_recommendation(recommendation_id, approved_by=body.by, memo=body.memo)
        if action == "modify":
            if body.adjusted_qty is None:
                raise ValueError("adjusted_qty_required")
            return modify_recommendation(
                recommendation_id,
                body.adjusted_qty,
                reason=body.reason,
                modified_by=body.by,
                memo=body.memo,
            )
        if action == "hold":
            return hold_recommendation(
                recommendation_id,
                reason=body.reason,
                held_by=body.by,
                memo=body.memo,
            )
        if action == "reject":
            return reject_recommendation(
                recommendation_id,
                reason=body.reason,
                rejected_by=body.by,
                memo=body.memo,
            )
    except ValueError as e:
        if str(e) == "recommendation not found":
            raise HTTPException(status_code=404, detail="recommendation_not_found") from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    raise HTTPException(status_code=400, detail="invalid_action_type")


@router.get("/{recommendation_id}/history")
def get_history(recommendation_id: int) -> list[dict]:
    return get_approval_history(recommendation_id)
