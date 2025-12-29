"""
backend/app/api/calculate.py - 계산 API 엔드포인트
───────────────────────────────────────────────────
logic/ 모듈의 계산 함수를 호출하는 얇은 API 레이어.
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
import pandas as pd

from logic.db import get_connection
from backend.app.api.logs import add_log

# logic 모듈에서 계산 함수 import
from logic import (
    # 인보이스 계산
    add_basic_shipping,
    add_worklog_items,
    add_barcode_fee,
    add_void_fee,
    add_ppbag_fee,
    add_video_out_fee,
    add_return_pickup_fee,
    add_return_courier_fee,
    add_video_ret_fee,
    add_box_fee_by_zone,
    # 개별 요금 계산
    calculate_courier_fee_by_zone,
    get_courier_fee_items,
    calculate_inbound_inspection_fee,
    calculate_remote_area_fee,
    calculate_combined_pack_fee,
    # 배송통계
    shipping_stats,
    get_shipping_count,
)

from backend.app.models import (
    InvoiceCalculateRequest,
    InvoiceCalculateResponse,
    InvoiceItem,
    CourierFeeRequest,
    CourierFeeResponse,
    InboundFeeRequest,
    InboundFeeResponse,
    RemoteFeeRequest,
    RemoteFeeResponse,
    ShippingStatsRequest,
    ShippingStatsResponse,
)

router = APIRouter(prefix="/calculate", tags=["Calculate"])


def check_admin(token: Optional[str]) -> tuple:
    """관리자 권한 확인, (is_admin, nickname) 반환"""
    if not token:
        return False, None
    with get_connection() as con:
        result = con.execute(
            "SELECT u.is_admin, u.nickname FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        if result:
            return bool(result[0]), result[1]
    return False, None


# ─────────────────────────────────────
# 통합 인보이스 계산
# ─────────────────────────────────────
@router.post("", response_model=InvoiceCalculateResponse)
@router.post("/", response_model=InvoiceCalculateResponse)
async def calculate_invoice(req: InvoiceCalculateRequest, token: Optional[str] = None) -> InvoiceCalculateResponse:
    """
    인보이스 항목 통합 계산 (관리자만).
    
    logic/ 모듈의 계산 함수들을 순차적으로 호출하여
    인보이스 항목 리스트를 생성합니다.
    """
    # 관리자 권한 체크
    is_admin, nickname = check_admin(token)
    if not is_admin:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    items: List[Dict[str, Any]] = []
    warnings: List[str] = []
    
    d_from = req.date_from.isoformat()
    d_to = req.date_to.isoformat()
    
    try:
        # 1. 택배요금 (구간별) - 반드시 먼저 계산해야 zone_counts 확보
        zone_counts: Dict[str, int] = {}
        if req.include_courier_fee:
            zone_counts = calculate_courier_fee_by_zone(
                req.vendor, d_from, d_to, items
            )
        
        # 2. 입고검수
        if req.include_inbound_fee:
            inbound = calculate_inbound_inspection_fee(req.vendor, d_from, d_to)
            if inbound:
                items.append(inbound)
        
        # 3. 도서산간
        if req.include_remote_fee:
            remote = calculate_remote_area_fee(req.vendor, d_from, d_to)
            if remote:
                items.append(remote)
        
        # 4. 작업일지
        if req.include_worklog:
            add_worklog_items(items, req.vendor, d_from, d_to)
        
        # 5. 플래그 기반 요금 (바코드, 완충작업 등)
        add_barcode_fee(items, req.vendor)
        add_void_fee(items, req.vendor)
        add_ppbag_fee(items, req.vendor)
        add_video_out_fee(items, req.vendor)
        
        # 6. 반품 관련
        add_return_pickup_fee(items, req.vendor, d_from, d_to)
        add_return_courier_fee(items, req.vendor, d_from, d_to)
        add_video_ret_fee(items, req.vendor, d_from, d_to)
        
        # 7. 박스/봉투
        if zone_counts:
            add_box_fee_by_zone(items, req.vendor, zone_counts)
        
        # 총 금액 계산
        total_amount = sum(it.get("금액", 0) for it in items)
        
        # InvoiceItem 모델로 변환
        invoice_items = [
            InvoiceItem(
                항목=it["항목"],
                수량=int(it["수량"]),
                단가=int(it["단가"]),
                금액=int(it["금액"]),
                비고=it.get("비고", "")
            )
            for it in items
        ]
        
        # 로그 기록
        add_log(
            action_type="인보이스 계산",
            target_type="invoice",
            target_id=None,
            target_name=req.vendor,
            user_nickname=nickname,
            details=f"기간: {d_from} ~ {d_to}, 항목수: {len(invoice_items)}, 총액: {int(total_amount):,}원"
        )
        
        return InvoiceCalculateResponse(
            success=True,
            vendor=req.vendor,
            date_from=req.date_from,
            date_to=req.date_to,
            items=invoice_items,
            total_amount=int(total_amount),
            warnings=warnings
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────
# 개별 요금 계산: 택배요금
# ─────────────────────────────────────
@router.post("/courier-fee", response_model=CourierFeeResponse)
async def calculate_courier_fee(req: CourierFeeRequest) -> CourierFeeResponse:
    """
    택배요금 (구간별) 계산.
    
    logic.calculate_courier_fee_by_zone() 호출.
    """
    try:
        items: List[Dict] = []
        zone_counts = calculate_courier_fee_by_zone(
            req.vendor,
            req.date_from.isoformat(),
            req.date_to.isoformat(),
            items
        )
        
        invoice_items = [
            InvoiceItem(
                항목=it["항목"],
                수량=int(it["수량"]),
                단가=int(it["단가"]),
                금액=int(it["금액"]),
                비고=""
            )
            for it in items
        ]
        
        return CourierFeeResponse(
            success=True,
            vendor=req.vendor,
            zone_counts=zone_counts,
            items=invoice_items
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────
# 개별 요금 계산: 입고검수
# ─────────────────────────────────────
@router.post("/inbound-fee", response_model=InboundFeeResponse)
async def calculate_inbound_fee(req: InboundFeeRequest) -> InboundFeeResponse:
    """
    입고검수 요금 계산.
    
    logic.calculate_inbound_inspection_fee() 호출.
    """
    try:
        result = calculate_inbound_inspection_fee(
            req.vendor,
            req.date_from.isoformat(),
            req.date_to.isoformat()
        )
        
        item = None
        if result:
            item = InvoiceItem(
                항목=result["항목"],
                수량=int(result["수량"]),
                단가=int(result["단가"]),
                금액=int(result["금액"]),
                비고=""
            )
        
        return InboundFeeResponse(
            success=True,
            vendor=req.vendor,
            item=item
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────
# 개별 요금 계산: 도서산간
# ─────────────────────────────────────
@router.post("/remote-fee", response_model=RemoteFeeResponse)
async def calculate_remote_fee(req: RemoteFeeRequest) -> RemoteFeeResponse:
    """
    도서산간 요금 계산.
    
    logic.calculate_remote_area_fee() 호출.
    """
    try:
        result = calculate_remote_area_fee(
            req.vendor,
            req.date_from.isoformat(),
            req.date_to.isoformat()
        )
        
        item = None
        if result:
            item = InvoiceItem(
                항목=result["항목"],
                수량=int(result["수량"]),
                단가=int(result["단가"]),
                금액=int(result["금액"]),
                비고=""
            )
        
        return RemoteFeeResponse(
            success=True,
            vendor=req.vendor,
            item=item
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────
# 배송통계 조회
# ─────────────────────────────────────
@router.post("/shipping-stats", response_model=ShippingStatsResponse)
async def get_shipping_stats(req: ShippingStatsRequest) -> ShippingStatsResponse:
    """
    배송통계 조회.
    
    logic.shipping_stats() 호출.
    """
    try:
        df = shipping_stats(req.vendor, req.date_from, req.date_to)
        count = len(df)
        
        # DataFrame → dict list (최대 100건)
        data = df.head(100).to_dict(orient="records")
        
        return ShippingStatsResponse(
            success=True,
            vendor=req.vendor,
            count=count,
            data=data
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

