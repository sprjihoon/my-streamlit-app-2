"""
backend/app/api/prepacking.py - 프리패킹 API
─────────────────────────────────────────────
프리패킹 예측·제작·관리 엔드포인트.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.models.schemas import (
    PrepackingAnalyzeRequest,
    PrepackingPredictRequest,
    PrepackingProductionCreate,
    PrepackingProductionUse,
    PrepackingStatusUpdate,
    PrepackingLocationUpdate,
    PrepackingSettingsUpdate,
    PrepackingAccuracyRequest,
)
from logic.prepacking import (
    analyze_combinations,
    predict_for_date,
    save_predictions,
    get_predictions,
    create_production,
    use_production,
    update_production_status,
    update_production_location,
    get_active_productions,
    get_productions_by_date,
    generate_daily_instructions,
    update_actual_qty,
    get_accuracy_history,
    get_efficiency_stats,
    get_settings,
    save_settings,
    get_all_settings,
    suggest_locations,
    get_vendors_with_data,
    parse_admin_product_qty,
    _detect_columns,
    _safe_str,
    _extract_items_from_row,
    _find_invoice_col,
    _group_shipments,
)

router = APIRouter(prefix="/prepacking", tags=["prepacking"])


# ─────────────────────────────────────
# 공급처 목록
# ─────────────────────────────────────
@router.get("/vendors")
async def list_vendors():
    """배송통계에 데이터가 있는 공급처 목록."""
    return get_vendors_with_data()


# ─────────────────────────────────────
# 조합 분석
# ─────────────────────────────────────
@router.post("/analyze")
async def analyze(req: PrepackingAnalyzeRequest):
    """공급처별 SKU 조합 분석."""
    try:
        result = analyze_combinations(req.vendor, req.date_from, req.date_to)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────
# 예측
# ─────────────────────────────────────
@router.post("/predict")
async def predict(req: PrepackingPredictRequest):
    """프리패킹 추천 목록 생성."""
    try:
        predictions = predict_for_date(req.vendor, req.target_date, req.weeks_back)
        if req.save and predictions:
            save_predictions(req.vendor, req.target_date, predictions)
        return {"vendor": req.vendor, "target_date": req.target_date.isoformat(), "predictions": predictions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions")
async def get_saved_predictions(
    vendor: str = Query(...),
    target_date: date = Query(...),
):
    """저장된 예측 조회."""
    return get_predictions(vendor, target_date)


# ─────────────────────────────────────
# 오늘의 지시
# ─────────────────────────────────────
@router.get("/daily-instructions")
async def daily_instructions(
    vendor: str = Query(...),
    today: Optional[date] = Query(default=None),
):
    """오늘의 프리패킹 지시 (유지/해체/신규제작)."""
    try:
        return generate_daily_instructions(vendor, today)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────
# 제작 기록
# ─────────────────────────────────────
@router.post("/productions")
async def create_prod(req: PrepackingProductionCreate):
    """프리패킹 제작 기록 생성."""
    try:
        prod_id = create_production(
            vendor=req.vendor,
            target_date=req.target_date,
            combo_key=req.combo_key,
            combo_detail=req.combo_detail,
            predicted_qty=req.predicted_qty,
            produced_qty=req.produced_qty,
            location=req.location,
        )
        return {"success": True, "id": prod_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/productions/active")
async def active_productions(vendor: Optional[str] = Query(default=None)):
    """활성 프리패킹 재고 현황."""
    return get_active_productions(vendor)


@router.get("/productions/by-date")
async def productions_by_date(
    vendor: str = Query(...),
    target_date: date = Query(...),
):
    """특정 날짜의 제작 기록."""
    return get_productions_by_date(vendor, target_date)


@router.patch("/productions/{production_id}/use")
async def use_prod(production_id: int, req: PrepackingProductionUse):
    """프리패킹 수동 차감."""
    result = use_production(production_id, req.use_qty, req.changed_by)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.patch("/productions/{production_id}/status")
async def update_status(production_id: int, req: PrepackingStatusUpdate):
    """프리패킹 상태 변경."""
    result = update_production_status(production_id, req.status, req.changed_by)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.patch("/productions/{production_id}/location")
async def update_location(production_id: int, req: PrepackingLocationUpdate):
    """로케이션 변경."""
    result = update_production_location(production_id, req.location, req.changed_by)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ─────────────────────────────────────
# 정확도
# ─────────────────────────────────────
@router.post("/accuracy/update")
async def update_accuracy(req: PrepackingAccuracyRequest):
    """예측 vs 실제 정확도 업데이트."""
    try:
        return update_actual_qty(req.vendor, req.target_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accuracy/history")
async def accuracy_history(
    vendor: str = Query(...),
    limit: int = Query(default=30, ge=1, le=100),
):
    """정확도 이력."""
    return get_accuracy_history(vendor, limit)


@router.get("/efficiency")
async def efficiency(
    vendor: str = Query(...),
    days: int = Query(default=30, ge=1, le=365),
):
    """프리패킹 효율 지표."""
    return get_efficiency_stats(vendor, days)


# ─────────────────────────────────────
# 설정
# ─────────────────────────────────────
@router.get("/settings")
async def get_all_prepacking_settings():
    """모든 설정 조회."""
    return get_all_settings()


@router.get("/settings/{vendor}")
async def get_vendor_settings(vendor: str):
    """공급처별 설정 조회."""
    return get_settings(vendor)


@router.put("/settings")
async def update_settings(req: PrepackingSettingsUpdate):
    """설정 저장."""
    save_settings(req.vendor, req.model_dump(exclude={"vendor"}))
    return {"success": True, "vendor": req.vendor}


# ─────────────────────────────────────
# 로케이션 자동완성
# ─────────────────────────────────────
@router.get("/locations/suggest")
async def location_suggest(
    vendor: str = Query(...),
    prefix: str = Query(default=""),
    limit: int = Query(default=10, ge=1, le=50),
):
    """로케이션 자동완성 제안."""
    return suggest_locations(vendor, prefix, limit)


# ─────────────────────────────────────
# 디버그
# ─────────────────────────────────────
@router.get("/debug/sample-rows")
async def debug_sample_rows(
    vendor: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
):
    """샘플 데이터 + 파싱 결과 확인 (경량 버전)."""
    import pandas as pd
    from logic.db import get_connection

    with get_connection() as con:
        # 전체 로드 대신 컬럼 정보만 먼저 확인
        col_info = con.execute("PRAGMA table_info(shipping_stats)").fetchall()
        all_columns = [c[1].strip() for c in col_info]

        alias_df = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor = ? AND file_type = 'shipping_stats'",
            con, params=(vendor,),
        )
        name_list = [vendor] + alias_df["alias"].tolist()

        # 공급처 필터가 있으면 적용, LIMIT으로 가볍게
        if "공급처" in all_columns:
            placeholders = ",".join(["?"] * len(name_list))
            sample_df = pd.read_sql(
                f"SELECT * FROM shipping_stats WHERE [공급처] IN ({placeholders}) LIMIT ?",
                con, params=(*name_list, limit * 5),
            )
        else:
            sample_df = pd.read_sql(
                f"SELECT * FROM shipping_stats LIMIT ?",
                con, params=(limit * 5,),
            )

        # 전체 건수 (가볍게)
        if "공급처" in all_columns:
            total_row = con.execute(
                f"SELECT COUNT(*) FROM shipping_stats WHERE [공급처] IN ({placeholders})",
                name_list,
            ).fetchone()
        else:
            total_row = con.execute("SELECT COUNT(*) FROM shipping_stats").fetchone()
        total_rows = total_row[0] if total_row else 0

    sample_df.columns = [c.strip() for c in sample_df.columns]
    col_map = _detect_columns(sample_df)

    admin_col = col_map.get("admin_product_qty")
    invoice_col = _find_invoice_col(sample_df)

    # 샘플 행 파싱
    samples = []
    for idx, row in sample_df.head(limit).iterrows():
        raw_val = _safe_str(row.get(admin_col, "")) if admin_col else ""
        parsed = parse_admin_product_qty(raw_val) if raw_val else []
        items = _extract_items_from_row(row, col_map)
        samples.append({
            "row_idx": int(idx),
            "admin_product_qty_raw": raw_val[:500],
            "parsed_skus": parsed,
            "extracted_items": items,
            "item_count": len(items),
        })

    # 샘플 범위 내 합포장 감지
    shipments = _group_shipments(sample_df, col_map)
    multi_shipments = [(items, dt) for items, dt in shipments if len(items) >= 2]

    multi_samples = []
    for items, dt in multi_shipments[:limit]:
        multi_samples.append({
            "item_count": len(items),
            "items": items,
            "date": str(dt) if pd.notna(dt) else None,
        })

    return {
        "vendor": vendor,
        "total_rows": total_rows,
        "sample_rows": len(sample_df),
        "total_shipments": len(shipments),
        "multi_item_shipments": len(multi_shipments),
        "detected_columns": {k: v for k, v in col_map.items() if v is not None},
        "admin_col": admin_col,
        "invoice_col": invoice_col,
        "all_columns": all_columns[:40],
        "first_rows": samples,
        "multi_shipment_samples": multi_samples,
    }
