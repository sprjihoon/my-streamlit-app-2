from __future__ import annotations

from fastapi import APIRouter, HTTPException

from prepacking.models.schemas import PPApprovalRequest, PPRecommendationRequest
from prepacking.services.approval.approval_service import (
    approve_recommendation,
    get_approval_history,
    hold_recommendation,
    modify_recommendation,
    reject_recommendation,
)
from prepacking.services.recommendation.recommendation_service import (
    generate_recommendations,
    get_recommendation_detail,
    get_recommendations,
)

router = APIRouter(prefix="/pp/recommendations", tags=["prepacking-recommendations"])


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
