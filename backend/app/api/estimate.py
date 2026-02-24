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
        "양품화": 500,
        "텍작업": 150,
        "바코드 부착": 150,
        "완충작업": 100,
        "출고영상촬영": 200,
        "반품영상촬영": 400,
    }
    return defaults.get(item_name, 0)


def _get_material_unit(con, item_name: str) -> int:
    """material_rates 테이블에서 단가 조회."""
    try:
        row = con.execute(
            "SELECT 단가 FROM material_rates WHERE 항목 = ?", (item_name,)
        ).fetchone()
        if row:
            return int(float(row[0]))
    except Exception:
        pass
    defaults = {
        "PP 봉투 중형": 80,
        "택배 봉투 소형": 80,
        "택배 봉투 대형": 120,
    }
    return defaults.get(item_name, 0)


def _get_storage_unit(con, item_name: str) -> int:
    """storage_rates 테이블에서 보관료 단가 조회 (견적용)."""
    try:
        row = con.execute(
            "SELECT unit_price FROM storage_rates WHERE item_name = ?",
            (item_name,),
        ).fetchone()
        if row:
            return int(row[0])
    except Exception:
        pass
    defaults = {"PLT": 30000, "중량랙": 60000}
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


@router.get("/chargeable-items")
async def get_chargeable_items():
    """
    견적 추가 작업용 청구서 항목 목록 (out_extra + material_rates).
    항목명·단가를 반환하여 프론트에서 선택 후 수량만 입력하면 됨.
    """
    result: List[Dict[str, Any]] = []
    try:
        with get_connection() as con:
            try:
                df_extra = pd.read_sql("SELECT * FROM out_extra ORDER BY 1", con)
                cols = list(df_extra.columns)
                name_col = next((c for c in cols if "항목" in str(c)), cols[0] if cols else None)
                price_col = next((c for c in cols if "단가" in str(c)), cols[1] if len(cols) > 1 else None)
                for _, row in df_extra.iterrows():
                    result.append({
                        "item_name": str(row.get(name_col, "")),
                        "unit_price": int(float(row.get(price_col, 0))),
                        "source": "out_extra",
                    })
            except Exception:
                pass
            try:
                df_mat = pd.read_sql("SELECT * FROM material_rates ORDER BY 1", con)
                cols = list(df_mat.columns)
                name_col = next((c for c in cols if "항목" in str(c)), cols[0] if cols else None)
                price_col = next((c for c in cols if "단가" in str(c)), cols[1] if len(cols) > 1 else None)
                for _, row in df_mat.iterrows():
                    result.append({
                        "item_name": str(row.get(name_col, "")),
                        "unit_price": int(float(row.get(price_col, 0))),
                        "source": "material_rates",
                    })
            except Exception:
                pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"items": result}


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
    # 견적에서는 택배 요금제 무조건 표준만 적용
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

            # 2. 택배요금 (구간별) + 구간별 수량 저장 (택배 봉투용)
            zone_ratios = req.zone_ratios or {"극소": 1.0}
            total_ratio = sum(zone_ratios.values())
            if total_ratio <= 0:
                zone_ratios = DEFAULT_ZONE_RATIOS.copy()
                total_ratio = 1.0
            zone_rates = _get_shipping_zone_rates(con, rate_type)
            zone_counts: Dict[str, int] = {}
            if zone_rates and req.monthly_outbound > 0:
                for z in zone_rates:
                    label = z.get("구간", "")
                    fee = int(z.get("요금", 0))
                    ratio = zone_ratios.get(label, 0) / total_ratio
                    count = int(round(req.monthly_outbound * ratio))
                    zone_counts[label] = count
                    if count > 0:
                        items.append({
                            "항목": f"택배요금 ({label})",
                            "수량": count,
                            "단가": fee,
                            "금액": count * fee,
                            "비고": "",
                        })

            # 3. 반품 회수비 (출고건 대비 %)
            return_pct = getattr(req, "return_percentage", None)
            if return_pct is None:
                return_pct = 0
            return_count = int(round(req.monthly_outbound * return_pct / 100)) if return_pct else 0
            if return_count > 0:
                unit = _get_out_extra_unit(con, "반품회수")
                items.append({
                    "항목": "반품 회수비",
                    "수량": return_count,
                    "단가": unit,
                    "금액": return_count * unit,
                    "비고": "",
                })
                # 3-1. 반품 택배비 (실제 청구됨 → 견적은 택배 구간별 비율 중 최대 비율 구간 단가 적용)
                if zone_rates and zone_ratios:
                    max_zone = max(zone_ratios.keys(), key=lambda z: zone_ratios.get(z, 0))
                    return_courier_fee = next(
                        (int(z.get("요금", 0)) for z in zone_rates if z.get("구간") == max_zone),
                        0,
                    )
                    if return_courier_fee > 0:
                        items.append({
                            "항목": f"반품 택배비 ({max_zone})",
                            "수량": return_count,
                            "단가": return_courier_fee,
                            "금액": return_count * return_courier_fee,
                            "비고": "최대 비율 구간 단가 적용",
                        })

            # 4. 입고검수 (입고수량)
            inbound_qty = req.inbound_qty or 0
            if inbound_qty > 0:
                unit = _get_out_extra_unit(con, "입고검수")
                items.append({
                    "항목": "입고검수",
                    "수량": inbound_qty,
                    "단가": unit,
                    "금액": inbound_qty * unit,
                    "비고": "",
                })

            # 5. 합포장 (출고건 대비 %, 평균 수량 기반: 건수 × (평균 수량 - 2) × 단가)
            combined_pct = getattr(req, "combined_percentage", None)
            if combined_pct is None:
                combined_pct = 0
            combined_over_qty = int(round(req.monthly_outbound * combined_pct / 100)) if combined_pct else 0
            combined_avg_qty = getattr(req, "combined_avg_qty", None)
            if combined_over_qty > 0:
                unit = _get_out_extra_unit(con, "합포장")
                if unit <= 0:
                    unit = 100
                if combined_avg_qty is not None and combined_avg_qty > 2:
                    chargeable_qty = combined_over_qty * (combined_avg_qty - 2)
                    remark = f"평균 {combined_avg_qty}개/건, 2개 초과분"
                else:
                    chargeable_qty = combined_over_qty
                    remark = f"평균 {combined_avg_qty}개/건" if (combined_avg_qty is not None and combined_avg_qty > 0) else ""
                items.append({
                    "항목": "합포장 (2개 초과/개)",
                    "수량": chargeable_qty,
                    "단가": unit,
                    "금액": chargeable_qty * unit,
                    "비고": remark,
                })

            # 6. 양품화 (패션 + 필요 시): 입고수량 × 500원
            brand_type = (getattr(req, "brand_type", None) or "etc").strip().lower()
            need_quality = getattr(req, "need_quality_work", False)
            if brand_type == "fashion" and need_quality and inbound_qty > 0:
                unit = _get_out_extra_unit(con, "양품화")
                if unit <= 0:
                    unit = 500
                items.append({
                    "항목": "양품화 작업 (기본양품화 최저비용)",
                    "수량": inbound_qty,
                    "단가": unit,
                    "금액": inbound_qty * unit,
                    "비고": "입고수량 × 500원/건",
                })

            # 7. PP 봉투 (우리 쪽 사용 시): 입고수량 × 단가
            pp_provider = (getattr(req, "pp_bag_provider", None) or "brand").strip().lower()
            if pp_provider == "ours" and inbound_qty > 0:
                unit = _get_material_unit(con, "PP 봉투 중형")
                items.append({
                    "항목": "PP 봉투",
                    "수량": inbound_qty,
                    "단가": unit,
                    "금액": inbound_qty * unit,
                    "비고": "",
                })

            # 8. 택배 봉투 (우리 쪽 사용 시): 구간별 수량 × 택배 봉투 단가
            mailer_provider = (getattr(req, "mailer_provider", None) or "brand").strip().lower()
            if mailer_provider == "ours" and zone_counts:
                # 극소 → 택배 봉투 소형, 소/중 → 택배 봉투 대형
                small_qty = zone_counts.get("극소", 0)
                if small_qty > 0:
                    unit = _get_material_unit(con, "택배 봉투 소형")
                    items.append({
                        "항목": "택배 봉투 소형",
                        "수량": small_qty,
                        "단가": unit,
                        "금액": small_qty * unit,
                        "비고": "",
                    })
                mid_qty = zone_counts.get("소", 0) + zone_counts.get("중", 0)
                if mid_qty > 0:
                    unit = _get_material_unit(con, "택배 봉투 대형")
                    items.append({
                        "항목": "택배 봉투 대형",
                        "수량": mid_qty,
                        "단가": unit,
                        "금액": mid_qty * unit,
                        "비고": "",
                    })

            # 9. 텍작업 (150원/건)
            need_tex = getattr(req, "need_tex_work", False)
            if need_tex and inbound_qty > 0:
                unit = _get_out_extra_unit(con, "텍작업")
                if unit <= 0:
                    unit = 150
                items.append({
                    "항목": "텍작업",
                    "수량": inbound_qty,
                    "단가": unit,
                    "금액": inbound_qty * unit,
                    "비고": "",
                })

            # 9-1. 바코드 부착 (입고수량 × 단가)
            need_barcode = getattr(req, "need_barcode_attach", False)
            if need_barcode and inbound_qty > 0:
                unit = _get_out_extra_unit(con, "바코드 부착")
                if unit <= 0:
                    unit = 150
                items.append({
                    "항목": "바코드 부착",
                    "수량": inbound_qty,
                    "단가": unit,
                    "금액": inbound_qty * unit,
                    "비고": "",
                })

            # 9-2. 완충작업 (출고건 × 단가)
            need_void = getattr(req, "need_void_work", False)
            if need_void and req.monthly_outbound > 0:
                unit = _get_out_extra_unit(con, "완충작업")
                items.append({
                    "항목": "완충작업",
                    "수량": req.monthly_outbound,
                    "단가": unit,
                    "금액": req.monthly_outbound * unit,
                    "비고": "",
                })

            # 9-3. 출고영상촬영 (출고건 × 단가)
            need_video_out = getattr(req, "need_video_out", False)
            if need_video_out and req.monthly_outbound > 0:
                unit = _get_out_extra_unit(con, "출고영상촬영")
                items.append({
                    "항목": "출고영상촬영",
                    "수량": req.monthly_outbound,
                    "단가": unit,
                    "금액": req.monthly_outbound * unit,
                    "비고": "",
                })

            # 9-4. 반품영상촬영 (반품건 × 단가)
            need_video_ret = getattr(req, "need_video_ret", False)
            if need_video_ret and return_count > 0:
                unit = _get_out_extra_unit(con, "반품영상촬영")
                items.append({
                    "항목": "반품영상촬영",
                    "수량": return_count,
                    "단가": unit,
                    "금액": return_count * unit,
                    "비고": "",
                })

            # 10. 추가 작업 (청구서 항목 중 선택, 단가 API 조회)
            extra_entries = getattr(req, "extra_work_entries", None) or []
            for ent in extra_entries:
                name = (ent.get("item_name") or ent.get("항목") or "").strip()
                qty = int(ent.get("qty") or ent.get("수량") or 0)
                if not name or qty <= 0:
                    continue
                unit = _get_out_extra_unit(con, name)
                if unit <= 0:
                    unit = _get_material_unit(con, name)
                if unit > 0:
                    items.append({
                        "항목": name,
                        "수량": qty,
                        "단가": unit,
                        "금액": qty * unit,
                        "비고": "",
                    })

            # 10-1. 보관료 (PLT 3만원 기본): 1 PLT당 SKU > 2이면 2 PLT당 1 중량랙 + 나머지 PLT
            storage_plt = getattr(req, "storage_plt", None)
            sku_count = getattr(req, "sku_count", None)
            if storage_plt and storage_plt > 0:
                plt_unit = _get_storage_unit(con, "PLT")
                if plt_unit <= 0:
                    plt_unit = 30000
                if sku_count is not None and sku_count > 0 and (sku_count / storage_plt) > 2:
                    # 2 PLT당 1 중량랙, 나머지는 PLT
                    weight_rack_qty = storage_plt // 2
                    plt_qty = storage_plt % 2
                    weight_rack_unit = _get_storage_unit(con, "중량랙")
                    if weight_rack_unit <= 0:
                        weight_rack_unit = 60000
                    if weight_rack_qty > 0:
                        items.append({
                            "항목": "보관료 (중량랙)",
                            "수량": weight_rack_qty,
                            "단가": weight_rack_unit,
                            "금액": weight_rack_qty * weight_rack_unit,
                            "비고": "1 PLT당 SKU 2개 초과 시 2 PLT당 1 중량랙",
                        })
                    if plt_qty > 0:
                        items.append({
                            "항목": "보관료 (PLT)",
                            "수량": plt_qty,
                            "단가": plt_unit,
                            "금액": plt_qty * plt_unit,
                            "비고": "나머지 PLT",
                        })
                else:
                    items.append({
                        "항목": "보관료 (PLT)",
                        "수량": storage_plt,
                        "단가": plt_unit,
                        "금액": storage_plt * plt_unit,
                        "비고": "보관량 PLT 기준",
                    })

            # 11. 작업일지 (의류 등)
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
