from __future__ import annotations

from prepacking.common import date_helper
from prepacking.common.enums import RecommendationStatus, TargetType
from prepacking.database import ensure_pp_tables, get_pp_connection
from prepacking.services.prediction import confidence_service, exclusion_service, forecast_service
from prepacking.services.recommendation import recommendation_repository


def _fetchall_dicts(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def generate_recommendations(
    supplier_name: str,
    target_date: str,
    source_upload_id: int | None = None,
) -> list[dict]:
    ensure_pp_tables()
    preds = forecast_service.predict_for_date(supplier_name, target_date)
    rec_date = date_helper.today_kst().isoformat()
    created: list[dict] = []
    for p in preds:
        code = (p.get("target_code") or "").strip()
        if exclusion_service.is_excluded(supplier_name, code, target_date):
            continue
        freq = int(p.get("frequency", 0))
        conf = float(p.get("confidence_score", 0.0))
        is_new = freq < 4
        risk = confidence_service.calculate_risk(conf, is_new, False)
        tt = p.get("target_type") or TargetType.SINGLE_SKU.value
        if tt not in (TargetType.SINGLE_SKU.value, TargetType.COMBINATION.value):
            tt = TargetType.SINGLE_SKU.value
        row = {
            "recommendation_date": rec_date,
            "target_date": target_date,
            "supplier_name": supplier_name,
            "target_type": tt,
            "target_code": code,
            "target_name": p.get("target_name", ""),
            "option_name": "",
            "combination_key": p.get("combination_key") or "",
            "predicted_qty": int(p.get("predicted_qty", 0)),
            "recommended_pack_unit": 1,
            "confidence_score": conf,
            "risk_score": risk,
            "recommendation_reason": "weighted_moving_average",
            "weekday_basis": p.get("weekday_basis"),
            "recent_7d_avg": float(p.get("recent_7d_avg", 0.0)),
            "recent_30d_avg": float(p.get("recent_30d_avg", 0.0)),
            "recent_same_weekday_avg": float(p.get("recent_same_weekday_avg", 0.0)),
            "source_upload_id": source_upload_id,
            "status": RecommendationStatus.RECOMMENDED.value,
        }
        rid = recommendation_repository.insert_recommendation(row)
        full = recommendation_repository.get_recommendation_by_id(rid)
        if full:
            created.append(full)
    return created


def get_recommendations(
    supplier_name: str,
    target_date: str | None = None,
    status: str | None = None,
) -> list[dict]:
    ensure_pp_tables()
    with get_pp_connection() as con:
        sql = "SELECT * FROM pp_recommendations WHERE supplier_name = ?"
        params: list = [supplier_name]
        if target_date is not None:
            sql += " AND target_date = ?"
            params.append(target_date)
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY recommendation_id DESC"
        cur = con.execute(sql, params)
        return _fetchall_dicts(cur)


def get_recommendation_detail(recommendation_id: int) -> dict | None:
    ensure_pp_tables()
    return recommendation_repository.get_recommendation_by_id(recommendation_id)
