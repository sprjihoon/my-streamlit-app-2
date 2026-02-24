"""
backend/app/api/estimate.py - 가견적 계산 및 PDF 출력 API
────────────────────────────────────────────────────────
입력: 업체명, 연락처, 이메일, 월 출고건, 구간 비율, 반품건 등
출력: 견적 항목 리스트, PDF 출력 시 수신처 정보 반영
"""

from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
import pandas as pd
from datetime import datetime

from logic.db import get_connection
from logic.invoice_pdf_v2 import create_billing_invoice_pdf

from backend.app.models import (
    EstimateCalculateRequest,
    EstimateCalculateResponse,
    EstimateExportPdfRequest,
    InvoiceItem,
)

router = APIRouter(prefix="/estimate", tags=["estimate"])

# 기본 출고비 단가 (logic/invoice_calc.py와 동일)
BASIC_SHIPPING_UNIT = 900

# 구간 기본 비율 (합 1.0) - zone_ratios 없을 때
DEFAULT_ZONE_RATIOS = {
    "극소": 0.30,
    "소": 0.40,
    "중": 0.20,
    "대": 0.07,
    "특대": 0.02,
    "특특대": 0.01,
}


def _get_out_extra_unit(con, item_name: str) -> int:
    """out_extra 테이블에서 단가 조회."""
    try:
        row = con.execute(
            "SELECT 단가 FROM out_extra WHERE 항목 = ?", (item_name,)
        ).fetchone()
        if row:
            return int(float(row[0]))
    except Exception:
        pass
    defaults = {
        "입고검수": 100,
        "합포장": 100,
        "도서산간": 0,
        "반품회수": 1100,
    }
    return defaults.get(item_name, 0)


def _get_shipping_zone_rates(con, rate_type: str) -> List[Dict[str, Any]]:
    """shipping_zone에서 요금제별 구간·요금 조회."""
    try:
        df = pd.read_sql(
            "SELECT [구간], [요금] FROM shipping_zone WHERE [요금제] = ? ORDER BY len_min_cm",
            con, params=(rate_type,)
        )
        return df.to_dict("records")
    except Exception:
        return []


@router.post("", response_model=EstimateCalculateResponse)
@router.post("/", response_model=EstimateCalculateResponse)
async def calculate_estimate(req: EstimateCalculateRequest) -> EstimateCalculateResponse:
    """
    가견적 계산.
    월 출고건, 구간 비율, 반품건 등으로 견적 항목을 계산합니다.
    업체명·연락처·이메일은 응답에 그대로 포함되어 PDF/저장 시 사용합니다.
    """
    items: List[Dict[str, Any]] = []
    warnings: List[str] = []
    rate_type = (req.rate_type or "표준").strip()
    if rate_type.upper() == "A":
        rate_type = "A"
    else:
        rate_type = "표준"

    try:
        with get_connection() as con:
            # 1. 기본 출고비
            if req.monthly_outbound > 0:
                items.append({
                    "항목": "기본 출고비",
                    "수량": req.monthly_outbound,
                    "단가": BASIC_SHIPPING_UNIT,
                    "금액": req.monthly_outbound * BASIC_SHIPPING_UNIT,
                    "비고": "",
                })

            # 2. 택배요금 (구간별)
            zone_ratios = req.zone_ratios or {"극소": 1.0}
            total_ratio = sum(zone_ratios.values())
            if total_ratio <= 0:
                zone_ratios = DEFAULT_ZONE_RATIOS.copy()
                total_ratio = 1.0
            zone_rates = _get_shipping_zone_rates(con, rate_type)
            if zone_rates and req.monthly_outbound > 0:
                for z in zone_rates:
                    label = z.get("구간", "")
                    fee = int(z.get("요금", 0))
                    ratio = zone_ratios.get(label, 0) / total_ratio
                    count = int(round(req.monthly_outbound * ratio))
                    if count > 0:
                        items.append({
                            "항목": f"택배요금 ({label})",
                            "수량": count,
                            "단가": fee,
                            "금액": count * fee,
                            "비고": "",
                        })

            # 3. 반품 회수비
            if req.return_count > 0:
                unit = _get_out_extra_unit(con, "반품회수")
                items.append({
                    "항목": "반품 회수비",
                    "수량": req.return_count,
                    "단가": unit,
                    "금액": req.return_count * unit,
                    "비고": "",
                })

            # 4. 입고검수
            if req.inbound_qty and req.inbound_qty > 0:
                unit = _get_out_extra_unit(con, "입고검수")
                items.append({
                    "항목": "입고검수",
                    "수량": req.inbound_qty,
                    "단가": unit,
                    "금액": req.inbound_qty * unit,
                    "비고": "",
                })

            # 5. 합포장
            if req.combined_over_qty and req.combined_over_qty > 0:
                unit = _get_out_extra_unit(con, "합포장")
                items.append({
                    "항목": "합포장 (2개 초과/개)",
                    "수량": req.combined_over_qty,
                    "단가": unit,
                    "금액": req.combined_over_qty * unit,
                    "비고": "",
                })

            # 6. 도서산간
            if req.remote_count and req.remote_count > 0:
                unit = _get_out_extra_unit(con, "도서산간")
                if unit > 0:
                    items.append({
                        "항목": "도서산간",
                        "수량": req.remote_count,
                        "단가": unit,
                        "금액": req.remote_count * unit,
                        "비고": "",
                    })

            # 7. 작업일지 (의류 등)
            if req.work_log_entries:
                for w in req.work_log_entries:
                    qty = max(0, w.수량)
                    unit = max(0, w.단가)
                    items.append({
                        "항목": w.분류,
                        "수량": qty,
                        "단가": unit,
                        "금액": qty * unit,
                        "비고": "",
                    })

        total_amount = sum(it["금액"] for it in items)
        invoice_items = [
            InvoiceItem(항목=it["항목"], 수량=it["수량"], 단가=it["단가"], 금액=it["금액"], 비고=it.get("비고", ""))
            for it in items
        ]
        return EstimateCalculateResponse(
            success=True,
            items=invoice_items,
            total_amount=total_amount,
            company_name=req.company_name or "",
            contact=req.contact or "",
            email=req.email or "",
            warnings=warnings,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export/pdf")
async def export_estimate_pdf(body: EstimateExportPdfRequest):
    """
    견적서 PDF 출력.
    업체명·연락처·이메일을 수신란에 반영합니다.
    """
    try:
        with get_connection() as con:
            table_exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='company_settings'"
            ).fetchone()
            if not table_exists:
                con.execute("""
                    CREATE TABLE company_settings(
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        company_name TEXT DEFAULT '회사명',
                        business_number TEXT DEFAULT '000-00-00000',
                        address TEXT DEFAULT '주소를 입력하세요',
                        business_type TEXT DEFAULT '서비스',
                        business_item TEXT DEFAULT '물류대행',
                        bank_name TEXT DEFAULT '은행명',
                        account_holder TEXT DEFAULT '예금주',
                        account_number TEXT DEFAULT '계좌번호',
                        representative TEXT DEFAULT '대표자명',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                con.commit()
            row_check = con.execute("SELECT 1 FROM company_settings WHERE id = 1").fetchone()
            if not row_check:
                con.execute("""
                    INSERT INTO company_settings (id, company_name, business_number, address,
                        business_type, business_item, bank_name, account_holder, account_number, representative)
                    VALUES (1, '틸리언', '766-55-00323', '대구시 동구 첨단로8길 8 씨제이빌딩302호',
                        '서비스', '포장 및 충전업', '카카오뱅크', '장지훈', '3333-02-9946468', '장지훈')
                """)
                con.commit()
            company_row = con.execute("""
                SELECT company_name, business_number, address, business_type, business_item,
                       bank_name, account_holder, account_number, representative
                FROM company_settings WHERE id = 1
            """).fetchone()
        if company_row:
            supplier_info = {
                "사업자번호": company_row[1] or "",
                "상호": company_row[0] or "",
                "소재지": company_row[2] or "",
                "업태": company_row[3] or "",
                "종목": company_row[4] or "",
            }
            bank_info = {
                "은행명": company_row[5] or "",
                "예금주": company_row[6] or "",
                "계좌번호": company_row[7] or "",
            }
            representative = company_row[8] or ""
            company_display_name = company_row[0] or ""
        else:
            supplier_info = {"사업자번호": "", "상호": "", "소재지": "", "업태": "", "종목": ""}
            bank_info = {"은행명": "", "예금주": "", "계좌번호": ""}
            representative = ""
            company_display_name = ""

        invoice_date = datetime.now().strftime("%Y-%m-%d")
        doc_number = f"EST-{invoice_date.replace('-', '')}"
        recipient_name = (body.company_name or "").strip() or "(업체명)"
        if recipient_name != "(업체명)" and not recipient_name.endswith(" 귀하"):
            recipient_name = f"{recipient_name} 귀하"
        title = "물류대행 서비스 견적서"
        payment_deadline = ""

        items_for_pdf = [
            {"항목": it.항목, "수량": it.수량, "단가": it.단가, "금액": it.금액, "비고": it.비고 or ""}
            for it in body.items
        ]

        pdf_bytes = create_billing_invoice_pdf(
            invoice_id=0,
            invoice_date=invoice_date,
            recipient_name=recipient_name,
            title=title,
            supplier_info=supplier_info,
            items=items_for_pdf,
            payment_deadline=payment_deadline,
            bank_info=bank_info,
            stamp_holder=representative,
            manager=representative,
            company_name=company_display_name,
            recipient_contact=body.contact or "",
            recipient_email=body.email or "",
            doc_title="물류대행 서비스 견적서",
        )

        filename = f"estimate_{invoice_date}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
