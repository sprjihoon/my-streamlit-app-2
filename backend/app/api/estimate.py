"""
backend/app/api/estimate.py - 물류 견적 계산 및 PDF 출력 API
────────────────────────────────────────────────────────
입력: 업체명, 연락처, 이메일, 월 출고건, 구간 비율, 반품건 등
출력: 견적 항목 리스트, PDF 출력 시 수신처 정보 반영
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
import pandas as pd
import json
from datetime import datetime

from logic.db import get_connection
from logic.estimate_pdf import create_estimate_pdf

from backend.app.models import (
    EstimateCalculateRequest,
    EstimateCalculateResponse,
    EstimateExportPdfRequest,
    EstimateSaveRequest,
    EstimateListItem,
    EstimateListResponse,
    InvoiceItem,
)

router = APIRouter(prefix="/estimate", tags=["estimate"])

# 기본 출고비 단가 (logic/invoice_calc.py와 동일)
BASIC_SHIPPING_UNIT = 900

# 구간 기본 비율 (합 1.0) - zone_ratios 없을 때
DEFAULT_ZONE_RATIOS = {
    "극소": 0.70,
    "소": 0.20,
    "중": 0.07,
    "대": 0.01,
    "특대": 0.01,
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
        "박스 극소형": 200,
        "박스 소형": 300,
        "박스 중형": 500,
        "박스 대형": 800,
        "박스 특대": 1200,
        "박스 특특대": 1500,
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
    물류 견적 계산.
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
                    "비고": "박스입고/개별분류검수 등 상담필요",
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

            # 6. 양품화 (패션 + 체크 시): 입고수량 × 500원 (기본양품화 비용)
            brand_type = (getattr(req, "brand_type", None) or "etc").strip().lower()
            need_quality = getattr(req, "need_quality_work", False)
            if brand_type == "fashion" and need_quality and inbound_qty > 0:
                unit = _get_out_extra_unit(con, "양품화") or 500
                if unit <= 0:
                    unit = 500
                items.append({
                    "항목": "양품화 작업 (기본양품화 최저비용)",
                    "수량": inbound_qty,
                    "단가": unit,
                    "금액": inbound_qty * unit,
                    "비고": "",
                })

            # 7. PP 봉투 (패션 + 풀필먼트 공용 포장재 사용 시): 입고수량 × 70원
            pp_provider = (getattr(req, "pp_bag_provider", None) or "brand").strip().lower()
            if brand_type == "fashion" and pp_provider == "ours" and inbound_qty > 0:
                unit = 70  # 풀필먼트 공용 포장재 단가
                items.append({
                    "항목": "PP 봉투",
                    "수량": inbound_qty,
                    "단가": unit,
                    "금액": inbound_qty * unit,
                    "비고": "풀필먼트 공용 70원",
                })

            # 청구서 로직과 동일: 택배 봉투는 극소(소형 50)/소(중형 70)/중(대형 170)만, 그 이후(대/특대/특특대)는 박스
            mailer_provider = (getattr(req, "mailer_provider", None) or "brand").strip().lower()
            courier_box_provider = getattr(req, "courier_box_provider", None) or "brand"
            courier_box_provider = str(courier_box_provider).strip().lower()

            # 8. 택배 봉투 (패션 + 풀필먼트 공용): 극소 50원(소형), 소 70원(중형), 중 170원(대형) — 대/특대/특특대는 봉투 없음
            if brand_type == "fashion" and mailer_provider == "ours" and zone_counts:
                _MAILER_BAG_UNIT = {"극소": 50, "소": 70, "중": 170}  # 봉투 소형/중형/대형
                for zone_label in ("극소", "소", "중"):
                    qty = zone_counts.get(zone_label, 0)
                    if qty > 0:
                        unit = _MAILER_BAG_UNIT[zone_label]
                        size_name = "소형" if zone_label == "극소" else ("중형" if zone_label == "소" else "대형")
                        items.append({
                            "항목": f"택배 봉투 ({zone_label})",
                            "수량": qty,
                            "단가": unit,
                            "금액": qty * unit,
                            "비고": f"풀필먼트 공용 봉투 {size_name} {unit}원",
                        })

            # 8-1. 택배박스 (패션 + 풀필먼트 공용): 대/특대/특특대만
            if brand_type == "fashion" and courier_box_provider == "ours" and zone_counts:
                _BOX_ITEM = {"대": "박스 대형", "특대": "박스 특대", "특특대": "박스 특특대"}
                for zone_label in ("대", "특대", "특특대"):
                    qty = zone_counts.get(zone_label, 0)
                    if qty > 0:
                        box_item = _BOX_ITEM[zone_label]
                        unit = _get_material_unit(con, box_item)
                        if unit <= 0:
                            unit = {"대": 800, "특대": 1200, "특특대": 1500}.get(zone_label, 800)
                        items.append({
                            "항목": f"택배박스 ({zone_label})",
                            "수량": qty,
                            "단가": unit,
                            "금액": qty * unit,
                            "비고": "풀필먼트 공용 구간별 박스",
                        })

            # 8-2. 뷰티/기타: PP/택배 봉투 미적용, 택배박스만 구간별 반영 (플래그는 택배박스만 적용)
            _ALL_BOX_ITEM = {"극소": "박스 극소형", "소": "박스 소형", "중": "박스 중형", "대": "박스 대형", "특대": "박스 특대", "특특대": "박스 특특대"}
            _ALL_BOX_DEFAULT = {"극소": 200, "소": 300, "중": 500, "대": 800, "특대": 1200, "특특대": 1500}
            if brand_type in ("beauty", "etc") and zone_counts:
                use_ours = (courier_box_provider == "ours")
                if use_ours:
                    for zone_label in ("극소", "소", "중", "대", "특대", "특특대"):
                        qty = zone_counts.get(zone_label, 0)
                        if qty > 0:
                            box_item = _ALL_BOX_ITEM[zone_label]
                            unit = _get_material_unit(con, box_item) or _ALL_BOX_DEFAULT[zone_label]
                            items.append({
                                "항목": f"택배박스 ({zone_label})",
                                "수량": qty,
                                "단가": unit,
                                "금액": qty * unit,
                                "비고": "뷰티/기타 전부 박스",
                            })

            # 9. 텍작업: 입고수량 × 150원
            need_tex = getattr(req, "need_tex_work", False)
            if need_tex and inbound_qty > 0:
                unit = _get_out_extra_unit(con, "텍작업") or 150
                if unit <= 0:
                    unit = 150
                items.append({
                    "항목": "텍작업",
                    "수량": inbound_qty,
                    "단가": unit,
                    "금액": inbound_qty * unit,
                    "비고": "",
                })

            # 9-1. 바코드 부착: 입고수량 × 150원
            need_barcode = getattr(req, "need_barcode_attach", False)
            if need_barcode and inbound_qty > 0:
                unit = _get_out_extra_unit(con, "바코드 부착") or 150
                if unit <= 0:
                    unit = 150
                items.append({
                    "항목": "바코드 부착",
                    "수량": inbound_qty,
                    "단가": unit,
                    "금액": inbound_qty * unit,
                    "비고": "",
                })

            # 9-2. 완충작업: 출고건수 × 100원
            need_void = getattr(req, "need_void_work", False)
            if need_void and req.monthly_outbound > 0:
                unit = _get_out_extra_unit(con, "완충작업") or 100
                if unit <= 0:
                    unit = 100
                items.append({
                    "항목": "완충작업",
                    "수량": req.monthly_outbound,
                    "단가": unit,
                    "금액": req.monthly_outbound * unit,
                    "비고": "",
                })

            # 9-3. 출고영상촬영: 출고건수 × 200원
            need_video_out = getattr(req, "need_video_out", False)
            if need_video_out and req.monthly_outbound > 0:
                unit = _get_out_extra_unit(con, "출고영상촬영") or 200
                if unit <= 0:
                    unit = 200
                items.append({
                    "항목": "출고영상촬영",
                    "수량": req.monthly_outbound,
                    "단가": unit,
                    "금액": req.monthly_outbound * unit,
                    "비고": "",
                })

            # 9-4. 반품영상촬영: 반품수량 × 400원
            need_video_ret = getattr(req, "need_video_ret", False)
            if need_video_ret and return_count > 0:
                unit = _get_out_extra_unit(con, "반품영상촬영") or 400
                if unit <= 0:
                    unit = 400
                items.append({
                    "항목": "반품영상촬영",
                    "수량": return_count,
                    "단가": unit,
                    "금액": return_count * unit,
                    "비고": "",
                })

            # 9-5. 스티커 부착: 1건 100원 (1장당 비용발생)
            need_sticker = getattr(req, "need_sticker_attach", False)
            if need_sticker:
                unit = 100
                items.append({
                    "항목": "스티커 부착",
                    "수량": 1,
                    "단가": unit,
                    "금액": unit,
                    "비고": "1장당 비용발생",
                })

            # 9-6. 리플릿 동봉: 1건 100원 (1장당 비용발생)
            need_leaflet = getattr(req, "need_leaflet_insert", False)
            if need_leaflet:
                unit = 100
                items.append({
                    "항목": "리플릿 동봉",
                    "수량": 1,
                    "단가": unit,
                    "금액": unit,
                    "비고": "1장당 비용발생",
                })

            # 9-7. B2B동봉서류부착: 1건 1000원 (1장당 비용발생)
            need_b2b = getattr(req, "need_b2b_document", False)
            if need_b2b:
                unit = 1000
                items.append({
                    "항목": "B2B동봉서류부착",
                    "수량": 1,
                    "단가": unit,
                    "금액": unit,
                    "비고": "1장당 비용발생",
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

            # 10-1. 보관료: 패션은 무조건 중량랙, 뷰티/기타는 PLT (1 PLT당 SKU > 2이면 중량랙+PLT 혼합)
            storage_plt = getattr(req, "storage_plt", None)
            sku_count = getattr(req, "sku_count", None)
            if storage_plt and storage_plt > 0:
                import math
                plt_unit = _get_storage_unit(con, "PLT")
                if plt_unit <= 0:
                    plt_unit = 30000
                weight_rack_unit = _get_storage_unit(con, "중량랙")
                if weight_rack_unit <= 0:
                    weight_rack_unit = 60000
                
                if brand_type == "fashion":
                    # 패션: 무조건 중량랙 (2 PLT당 1 중량랙)
                    weight_rack_qty = math.ceil(storage_plt / 2)
                    items.append({
                        "항목": "보관료 (중량랙)",
                        "수량": weight_rack_qty,
                        "단가": weight_rack_unit,
                        "금액": weight_rack_qty * weight_rack_unit,
                        "비고": f"패션 - PLT {storage_plt}개 → 중량랙 {weight_rack_qty}개",
                    })
                else:
                    # 뷰티/기타: 1 PLT당 SKU > 2이면 중량랙 필요
                    # 중량랙으로 최대한 커버하고 나머지는 PLT
                    if sku_count is not None and sku_count > 0 and (sku_count / storage_plt) > 2:
                        # 필요한 중량랙 수 계산: SKU를 커버할 수 있는 최소 중량랙
                        # 중량랙 1개 = 2 PLT = 최대 4 SKU 관리 가능
                        # 필요 중량랙 = ceil(SKU / 4), 단 최대 floor(PLT / 2)개까지
                        weight_rack_qty = storage_plt // 2
                        plt_qty = storage_plt % 2
                        
                        if weight_rack_qty > 0:
                            items.append({
                                "항목": "보관료 (중량랙)",
                                "수량": weight_rack_qty,
                                "단가": weight_rack_unit,
                                "금액": weight_rack_qty * weight_rack_unit,
                                "비고": f"PLT {weight_rack_qty * 2}개 → 중량랙 {weight_rack_qty}개",
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


@router.post("/save")
async def save_estimate(body: EstimateSaveRequest):
    """견적서를 DB에 저장 (목록 관리용)."""
    try:
        from zoneinfo import ZoneInfo
        kst_now = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")
        
        with get_connection() as con:
            con.execute(
                """
                INSERT INTO estimates (company_name, contact, email, total_amount, brand_type, items_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    body.company_name or "",
                    body.contact or "",
                    body.email or "",
                    body.total_amount,
                    (body.brand_type or "fashion").strip().lower(),
                    json.dumps([it.model_dump() for it in body.items], ensure_ascii=False),
                    kst_now,
                ),
            )
            con.commit()
            row = con.execute("SELECT last_insert_rowid()").fetchone()
            estimate_id = row[0] if row else None
        return {"id": estimate_id, "message": "저장되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_estimates(
    date_from: Optional[str] = Query(None, description="시작일 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="종료일 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """견적서 목록 (날짜 필터, 10/30/50 단위 페이징). page_size는 10, 30, 50 권장."""
    try:
        with get_connection() as con:
            tables = [row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='estimates'"
            ).fetchall()]
            if not tables:
                return EstimateListResponse(items=[], total=0, page=page, page_size=page_size)

            where = "1=1"
            params: List[Any] = []
            if date_from:
                where += " AND date(created_at) >= ?"
                params.append(date_from)
            if date_to:
                where += " AND date(created_at) <= ?"
                params.append(date_to)

            count_row = con.execute(
                f"SELECT COUNT(*) FROM estimates WHERE {where}", params
            ).fetchone()
            total = count_row[0] if count_row else 0

            offset = (page - 1) * page_size
            list_params = list(params) + [page_size, offset]
            rows = con.execute(
                f"""
                SELECT id, company_name, contact, email, total_amount, brand_type, created_at
                FROM estimates WHERE {where}
                ORDER BY id DESC LIMIT ? OFFSET ?
                """,
                list_params,
            ).fetchall()

            items = [
                EstimateListItem(
                    id=r[0],
                    company_name=r[1] or "",
                    contact=r[2] or "",
                    email=r[3] or "",
                    total_amount=int(r[4]) if r[4] is not None else 0,
                    brand_type=r[5] or "fashion",
                    created_at=r[6].strftime("%Y-%m-%d %H:%M") if hasattr(r[6], "strftime") else str(r[6] or ""),
                )
                for r in rows
            ]
        return EstimateListResponse(items=items, total=total, page=page, page_size=page_size)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/detail/{estimate_id}")
async def get_estimate_detail(estimate_id: int):
    """견적서 상세 조회 (ID로 조회, items_json 포함)."""
    try:
        with get_connection() as con:
            tables = [row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='estimates'"
            ).fetchall()]
            if not tables:
                raise HTTPException(status_code=404, detail="견적서 테이블이 없습니다.")

            row = con.execute(
                """
                SELECT id, company_name, contact, email, total_amount, brand_type, items_json, created_at
                FROM estimates WHERE id = ?
                """,
                (estimate_id,),
            ).fetchone()

            if not row:
                raise HTTPException(status_code=404, detail=f"견적서 #{estimate_id}를 찾을 수 없습니다.")

            items_json = row[6] or "[]"
            try:
                items = json.loads(items_json)
            except json.JSONDecodeError:
                items = []

            return {
                "id": row[0],
                "company_name": row[1] or "",
                "contact": row[2] or "",
                "email": row[3] or "",
                "total_amount": int(row[4]) if row[4] is not None else 0,
                "brand_type": row[5] or "fashion",
                "items": items,
                "created_at": row[7].strftime("%Y-%m-%d %H:%M") if hasattr(row[7], "strftime") else str(row[7] or ""),
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{estimate_id}")
async def update_estimate(estimate_id: int, body: EstimateSaveRequest):
    """견적서 수정 (업체명, 연락처, 이메일, 총액, 브랜드유형, 항목)."""
    try:
        with get_connection() as con:
            existing = con.execute(
                "SELECT id FROM estimates WHERE id = ?", (estimate_id,)
            ).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail=f"견적서 #{estimate_id}를 찾을 수 없습니다.")

            con.execute(
                """
                UPDATE estimates
                SET company_name = ?, contact = ?, email = ?, total_amount = ?, brand_type = ?, items_json = ?
                WHERE id = ?
                """,
                (
                    body.company_name or "",
                    body.contact or "",
                    body.email or "",
                    body.total_amount,
                    (body.brand_type or "fashion").strip().lower(),
                    json.dumps([it.model_dump() for it in body.items], ensure_ascii=False),
                    estimate_id,
                ),
            )
            con.commit()
        return {"id": estimate_id, "message": "수정되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{estimate_id}")
async def delete_estimate(estimate_id: int):
    """견적서 삭제."""
    try:
        with get_connection() as con:
            existing = con.execute(
                "SELECT id FROM estimates WHERE id = ?", (estimate_id,)
            ).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail=f"견적서 #{estimate_id}를 찾을 수 없습니다.")

            con.execute("DELETE FROM estimates WHERE id = ?", (estimate_id,))
            con.commit()
        return {"id": estimate_id, "message": "삭제되었습니다."}
    except HTTPException:
        raise
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
                    VALUES (1, '스프링풀필먼트', '766-55-00323', '대구시 동구 첨단로8길 8 씨제이빌딩302호',
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
            representative = company_row[8] or ""
            company_display_name = company_row[0] or ""
        else:
            supplier_info = {"사업자번호": "", "상호": "", "소재지": "", "업태": "", "종목": ""}
            representative = ""
            company_display_name = ""

        estimate_date = datetime.now().strftime("%Y-%m-%d")
        recipient_name = (body.company_name or "").strip() or "(업체명)"
        if recipient_name != "(업체명)" and not recipient_name.endswith(" 귀하"):
            recipient_name = f"{recipient_name} 귀하"
        title = "물류대행 서비스 견적"

        # 담당자: 패션=장성령, 뷰티/기타=장명찬
        brand_type = (getattr(body, "brand_type", None) or "fashion").strip().lower()
        manager = "장성령" if brand_type == "fashion" else "장명찬"

        items_for_pdf = [
            {"항목": it.항목, "수량": it.수량, "단가": it.단가, "금액": it.금액, "비고": it.비고 or ""}
            for it in body.items
        ]

        pdf_bytes = create_estimate_pdf(
            estimate_date=estimate_date,
            recipient_name=recipient_name,
            title=title,
            supplier_info=supplier_info,
            items=items_for_pdf,
            stamp_holder=representative,
            manager=manager,
            company_name=company_display_name,
            recipient_contact=body.contact or "",
            recipient_email=body.email or "",
            validity_days=15,
        )

        filename = f"estimate_{estimate_date}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
