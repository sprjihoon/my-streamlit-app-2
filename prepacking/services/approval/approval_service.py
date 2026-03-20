from __future__ import annotations

from prepacking.common import date_helper
from prepacking.common.enums import RecommendationStatus
from prepacking.database import ensure_pp_tables, get_pp_connection
from prepacking.services.approval import approval_repository
from prepacking.services.recommendation import recommendation_repository


def _approval_row(approval_id: int) -> dict | None:
    ensure_pp_tables()
    with get_pp_connection() as con:
        cur = con.execute(
            "SELECT * FROM pp_approvals WHERE approval_id = ?",
            (int(approval_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


def approve_recommendation(
    recommendation_id: int,
    approved_by: str = "",
    memo: str = "",
) -> dict:
    ensure_pp_tables()
    rec = recommendation_repository.get_recommendation_by_id(recommendation_id)
    if not rec:
        raise ValueError("recommendation not found")
    oq = int(rec.get("predicted_qty", 0))
    aid = approval_repository.insert_approval(
        {
            "recommendation_id": recommendation_id,
            "action_type": RecommendationStatus.APPROVED.value,
            "original_qty": oq,
            "adjusted_qty": oq,
            "action_reason": "",
            "approved_by": approved_by,
            "memo": memo,
        }
    )
    recommendation_repository.update_recommendation_status(
        recommendation_id, RecommendationStatus.APPROVED.value
    )
    row = _approval_row(aid)
    if not row:
        raise RuntimeError("approval insert failed")
    return row


def modify_recommendation(
    recommendation_id: int,
    adjusted_qty: int,
    reason: str = "",
    modified_by: str = "",
    memo: str = "",
) -> dict:
    ensure_pp_tables()
    rec = recommendation_repository.get_recommendation_by_id(recommendation_id)
    if not rec:
        raise ValueError("recommendation not found")
    oq = int(rec.get("predicted_qty", 0))
    aid = approval_repository.insert_approval(
        {
            "recommendation_id": recommendation_id,
            "action_type": RecommendationStatus.MODIFIED.value,
            "original_qty": oq,
            "adjusted_qty": int(adjusted_qty),
            "action_reason": reason,
            "approved_by": modified_by,
            "memo": memo,
        }
    )
    with get_pp_connection() as con:
        con.execute(
            """
            UPDATE pp_recommendations
            SET predicted_qty = ?, status = ?, updated_at = ?
            WHERE recommendation_id = ?
            """,
            (
                int(adjusted_qty),
                RecommendationStatus.MODIFIED.value,
                date_helper.now_str(),
                int(recommendation_id),
            ),
        )
        con.commit()
    row = _approval_row(aid)
    if not row:
        raise RuntimeError("approval insert failed")
    return row


def hold_recommendation(
    recommendation_id: int,
    reason: str = "",
    held_by: str = "",
    memo: str = "",
) -> dict:
    ensure_pp_tables()
    rec = recommendation_repository.get_recommendation_by_id(recommendation_id)
    if not rec:
        raise ValueError("recommendation not found")
    oq = int(rec.get("predicted_qty", 0))
    aid = approval_repository.insert_approval(
        {
            "recommendation_id": recommendation_id,
            "action_type": RecommendationStatus.HELD.value,
            "original_qty": oq,
            "adjusted_qty": oq,
            "action_reason": reason,
            "approved_by": held_by,
            "memo": memo,
        }
    )
    recommendation_repository.update_recommendation_status(
        recommendation_id, RecommendationStatus.HELD.value
    )
    row = _approval_row(aid)
    if not row:
        raise RuntimeError("approval insert failed")
    return row


def reject_recommendation(
    recommendation_id: int,
    reason: str = "",
    rejected_by: str = "",
    memo: str = "",
) -> dict:
    ensure_pp_tables()
    rec = recommendation_repository.get_recommendation_by_id(recommendation_id)
    if not rec:
        raise ValueError("recommendation not found")
    oq = int(rec.get("predicted_qty", 0))
    aid = approval_repository.insert_approval(
        {
            "recommendation_id": recommendation_id,
            "action_type": RecommendationStatus.REJECTED.value,
            "original_qty": oq,
            "adjusted_qty": oq,
            "action_reason": reason,
            "approved_by": rejected_by,
            "memo": memo,
        }
    )
    recommendation_repository.update_recommendation_status(
        recommendation_id, RecommendationStatus.REJECTED.value
    )
    row = _approval_row(aid)
    if not row:
        raise RuntimeError("approval insert failed")
    return row


def get_approval_history(recommendation_id: int) -> list[dict]:
    return approval_repository.get_approvals_by_recommendation(recommendation_id)
