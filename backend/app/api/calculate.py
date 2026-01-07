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
    add_storage_fee,
    add_combined_pack_fee,
    add_remote_area_fee,
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
        # 1. 기본 출고비
        df_items = pd.DataFrame(columns=["항목", "수량", "단가", "금액"])
        try:
            df_items = add_basic_shipping(df_items, req.vendor, d_from, d_to)
            for _, row in df_items.iterrows():
                if row["수량"] > 0:
                    items.append({
                        "항목": row["항목"],
                        "수량": row["수량"],
                        "단가": row["단가"],
                        "금액": row["금액"],
                        "비고": ""
                    })
        except Exception as e:
            warnings.append(f"기본 출고비 계산 오류: {str(e)}")
        
        # 2. 택배요금 (구간별) - 반드시 먼저 계산해야 zone_counts 확보
        zone_counts: Dict[str, int] = {}
        if req.include_courier_fee:
            try:
                zone_counts = calculate_courier_fee_by_zone(
                    req.vendor, d_from, d_to, items
                )
                # 택배비 항목이 추가되었는지 확인
                courier_items_count = sum(1 for item in items if "택배요금" in item.get("항목", ""))
                if courier_items_count == 0 and zone_counts:
                    # zone_counts는 있지만 items에 추가되지 않은 경우
                    warnings.append(f"택배요금 계산: 구간별 수량은 있으나 항목 추가 실패 (구간: {list(zone_counts.keys())})")
                elif not zone_counts:
                    warnings.append("택배요금 계산: 해당 기간에 배송 데이터가 없거나 shipping_zone 테이블에 요금제 데이터가 없습니다.")
            except Exception as e:
                warnings.append(f"택배요금 계산 오류: {str(e)}")
        
        # 3. 합포장 (택배요금 바로 다음)
        if req.include_combined_fee:
            try:
                # 배송통계 조회
                df_ship = shipping_stats(req.vendor, d_from, d_to)
                if not df_ship.empty:
                    success, error_msg = add_combined_pack_fee(df_ship, items)
                    if not success and error_msg:
                        warnings.append(f"합포장 계산 오류: {error_msg}")
            except Exception as e:
                warnings.append(f"합포장 계산 오류: {str(e)}")
        
        # 4. 도서산간 (택배요금 바로 다음)
        if req.include_remote_fee:
            try:
                success, error_msg, info_msg = add_remote_area_fee(req.vendor, d_from, d_to, items)
                if not success and error_msg:
                    warnings.append(f"도서산간 계산 오류: {error_msg}")
            except Exception as e:
                warnings.append(f"도서산간 계산 오류: {str(e)}")
        
        # 5. 박스/봉투 (택배요금 다음에 바로 추가)
        if zone_counts:
            add_box_fee_by_zone(items, req.vendor, zone_counts)
        
        # 6. 플래그 기반 요금 (바코드, 완충작업 등)
        add_barcode_fee(items, req.vendor)
        add_void_fee(items, req.vendor)
        add_ppbag_fee(items, req.vendor)
        add_video_out_fee(items, req.vendor)
        
        # 7. 반품 관련
        add_return_pickup_fee(items, req.vendor, d_from, d_to)
        add_return_courier_fee(items, req.vendor, d_from, d_to)
        add_video_ret_fee(items, req.vendor, d_from, d_to)
        
        # 8. 입고검수
        if req.include_inbound_fee:
            inbound = calculate_inbound_inspection_fee(req.vendor, d_from, d_to)
            if inbound:
                items.append(inbound)
        
        # 9. 작업일지 (플래그/반품 요금 뒤에 추가)
        if req.include_worklog:
            add_worklog_items(items, req.vendor, d_from, d_to)
        
        # 10. 거래처별 보관료 (활성 상태인 항목은 매월 자동 청구)
        # 보관료가 한 번 추가되면 이후 모든 월에 계속 반영됨 (수정하기 전까지 고정)
        # period 컬럼이 있더라도 기간 조건 없이 is_active=1인 모든 항목을 가져옴
        try:
            add_storage_fee(items, req.vendor)
        except Exception as e:
            warnings.append(f"보관료 조회 오류: {str(e)}")
        
        # 11. 거래처별 추가 비용 (기타)
        try:
            with get_connection() as con:
                # vendor_charges 테이블이 있는지 확인
                table_exists = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vendor_charges'"
                ).fetchone()
                
                if table_exists:
                    charges = con.execute(
                        """
                        SELECT item_name, qty, unit_price, amount, remark, charge_type
                        FROM vendor_charges
                        WHERE vendor_id = ? AND is_active = 1
                        """,
                        (req.vendor,)
                    ).fetchall()
                    
                    for charge in charges:
                        items.append({
                            "항목": charge[0],
                            "수량": charge[1],
                            "단가": charge[2],
                            "금액": charge[3],
                            "비고": charge[4] or ""  # 비고 값만 사용
                        })
        except Exception as e:
            warnings.append(f"추가 비용 조회 오류: {str(e)}")
        
        # 총 금액 계산
        total_amount = sum(it.get("금액", 0) for it in items)
        
        # InvoiceItem 모델로 변환
        invoice_items = [
            InvoiceItem(
                항목=it["항목"],
                수량=int(float(it["수량"])),
                단가=int(float(it["단가"])),
                금액=int(float(it["금액"])),
                비고=it.get("비고", "")
            )
            for it in items
        ]
        
        # DB에 인보이스 저장
        invoice_id = None
        if invoice_items:  # 항목이 있을 때만 저장
            with get_connection() as con:
                # vendor_id 조회 (vendors 테이블에서)
                vendor_row = con.execute(
                    "SELECT vendor_id FROM vendors WHERE vendor = ? OR name = ?",
                    (req.vendor, req.vendor)
                ).fetchone()
                vendor_id = vendor_row[0] if vendor_row else req.vendor
                
                # invoices 테이블에 INSERT
                cur = con.execute(
                    """INSERT INTO invoices 
                       (vendor_id, period_from, period_to, total_amount, status, created_at)
                       VALUES (?, ?, ?, ?, '미확정', datetime('now'))""",
                    (vendor_id, d_from, d_to, int(total_amount))
                )
                invoice_id = cur.lastrowid
                
                # invoice_items 테이블에 INSERT
                for item in invoice_items:
                    con.execute(
                        """INSERT INTO invoice_items 
                           (invoice_id, item_name, qty, unit_price, amount, remark)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (invoice_id, item.항목, item.수량, item.단가, item.금액, item.비고)
                    )
                
                con.commit()
        
        # 로그 기록
        add_log(
            action_type="인보이스 생성",
            target_type="invoice",
            target_id=str(invoice_id) if invoice_id else None,
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
            warnings=warnings,
            invoice_id=invoice_id
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
# 디버그: kpost_in 도서행 데이터 확인
# ─────────────────────────────────────
@router.get("/debug/kpost-doseo")
async def debug_kpost_doseo(vendor: str, d_from: str, d_to: str):
    """kpost_in 테이블의 도서행 데이터 확인 (디버그용)"""
    try:
        with get_connection() as con:
            # 테이블 존재 확인
            tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            
            result = {
                "tables": tables,
                "kpost_in_exists": "kpost_in" in tables,
                "aliases_exists": "aliases" in tables,
            }
            
            if "kpost_in" not in tables:
                return result
            
            # kpost_in 총 건수
            total = con.execute("SELECT COUNT(*) FROM kpost_in").fetchone()[0]
            result["kpost_in_total"] = total
            
            # 도서행 컬럼 존재 확인
            cols = [c[1] for c in con.execute("PRAGMA table_info(kpost_in);")]
            result["has_doseo_column"] = "도서행" in cols
            result["kpost_in_columns"] = cols
            
            if "도서행" in cols:
                # 도서행 값 분포
                doseo_dist = pd.read_sql("SELECT 도서행, COUNT(*) as cnt FROM kpost_in GROUP BY 도서행", con)
                result["doseo_distribution"] = doseo_dist.to_dict(orient="records")
            
            # 별칭 확인
            name_list = [vendor]
            if "aliases" in tables:
                alias_df = pd.read_sql(
                    "SELECT alias FROM aliases WHERE vendor = ? AND file_type IN ('kpost_in', 'all')",
                    con, params=(vendor,)
                )
                name_list.extend(alias_df["alias"].astype(str).str.strip().tolist())
            
            result["name_list_for_vendor"] = name_list
            
            placeholders = ",".join("?" * len(name_list))
            
            # 해당 vendor의 전체 건수
            vendor_total = con.execute(
                f"SELECT COUNT(*) FROM kpost_in WHERE TRIM(발송인명) IN ({placeholders})",
                (*name_list,)
            ).fetchone()[0]
            result["vendor_total"] = vendor_total
            
            # 해당 vendor + 기간의 건수
            vendor_period = con.execute(
                f"""SELECT COUNT(*) FROM kpost_in 
                    WHERE TRIM(발송인명) IN ({placeholders})
                    AND DATE(접수일자) BETWEEN DATE(?) AND DATE(?)""",
                (*name_list, d_from, d_to)
            ).fetchone()[0]
            result["vendor_period_count"] = vendor_period
            
            # 해당 vendor + 기간 + 도서행=Y 건수
            if "도서행" in cols:
                vendor_doseo = con.execute(
                    f"""SELECT COUNT(*) FROM kpost_in 
                        WHERE TRIM(발송인명) IN ({placeholders})
                        AND DATE(접수일자) BETWEEN DATE(?) AND DATE(?)
                        AND UPPER(TRIM(도서행)) = 'Y'""",
                    (*name_list, d_from, d_to)
                ).fetchone()[0]
                result["vendor_doseo_y_count"] = vendor_doseo
            
            return result
            
    except Exception as e:
        return {"error": str(e)}


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

