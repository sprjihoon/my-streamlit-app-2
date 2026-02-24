"""
backend/app/models/schemas.py - Pydantic 스키마 정의
───────────────────────────────────────────────────────
입력 검증 및 응답 직렬화용 Pydantic 모델.
계산 로직은 logic/ 모듈에서 처리.
"""

from datetime import date
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


# ─────────────────────────────────────
# 공통 응답
# ─────────────────────────────────────
class HealthResponse(BaseModel):
    """헬스체크 응답."""
    status: str = "ok"
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    """에러 응답."""
    success: bool = False
    error: str
    detail: Optional[str] = None


# ─────────────────────────────────────
# 인보이스 항목
# ─────────────────────────────────────
class InvoiceItem(BaseModel):
    """인보이스 항목."""
    항목: str = Field(..., description="항목명")
    수량: int = Field(..., description="수량")
    단가: int = Field(..., description="단가 (원)")
    금액: int = Field(..., description="금액 (원)")
    비고: Optional[str] = Field(default="", description="비고")


# ─────────────────────────────────────
# 인보이스 계산 (통합)
# ─────────────────────────────────────
class InvoiceCalculateRequest(BaseModel):
    """인보이스 계산 요청."""
    vendor: str = Field(..., description="공급처명")
    date_from: date = Field(..., description="시작일")
    date_to: date = Field(..., description="종료일")
    include_basic_shipping: bool = Field(default=True, description="기본 출고비 포함")
    include_courier_fee: bool = Field(default=True, description="택배요금 포함")
    include_inbound_fee: bool = Field(default=True, description="입고검수 포함")
    include_remote_fee: bool = Field(default=True, description="도서산간 포함")
    include_worklog: bool = Field(default=True, description="작업일지 포함")
    include_combined_fee: bool = Field(default=True, description="합포장 포함")


class InvoiceCalculateResponse(BaseModel):
    """인보이스 계산 응답."""
    success: bool = True
    vendor: str
    date_from: date
    date_to: date
    items: List[InvoiceItem]
    total_amount: int = Field(..., description="총 금액")
    warnings: List[str] = Field(default_factory=list, description="경고 메시지")
    invoice_id: Optional[int] = Field(default=None, description="생성된 인보이스 ID")


# ─────────────────────────────────────
# 택배요금 계산
# ─────────────────────────────────────
class CourierFeeRequest(BaseModel):
    """택배요금 계산 요청."""
    vendor: str = Field(..., description="공급처명")
    date_from: date = Field(..., description="시작일")
    date_to: date = Field(..., description="종료일")


class CourierFeeResponse(BaseModel):
    """택배요금 계산 응답."""
    success: bool = True
    vendor: str
    zone_counts: Dict[str, int] = Field(..., description="구간별 수량")
    items: List[InvoiceItem] = Field(default_factory=list, description="요금 항목")


# ─────────────────────────────────────
# 입고검수 요금 계산
# ─────────────────────────────────────
class InboundFeeRequest(BaseModel):
    """입고검수 요금 계산 요청."""
    vendor: str = Field(..., description="공급처명")
    date_from: date = Field(..., description="시작일")
    date_to: date = Field(..., description="종료일")


class InboundFeeResponse(BaseModel):
    """입고검수 요금 계산 응답."""
    success: bool = True
    vendor: str
    item: Optional[InvoiceItem] = None
    error: Optional[str] = None


# ─────────────────────────────────────
# 도서산간 요금 계산
# ─────────────────────────────────────
class RemoteFeeRequest(BaseModel):
    """도서산간 요금 계산 요청."""
    vendor: str = Field(..., description="공급처명")
    date_from: date = Field(..., description="시작일")
    date_to: date = Field(..., description="종료일")


class RemoteFeeResponse(BaseModel):
    """도서산간 요금 계산 응답."""
    success: bool = True
    vendor: str
    item: Optional[InvoiceItem] = None
    info: Optional[str] = None
    error: Optional[str] = None


# ─────────────────────────────────────
# 합포장 요금 계산
# ─────────────────────────────────────
class CombinedPackFeeRequest(BaseModel):
    """합포장 요금 계산 요청."""
    vendor: str = Field(..., description="공급처명")
    date_from: date = Field(..., description="시작일")
    date_to: date = Field(..., description="종료일")


class CombinedPackFeeResponse(BaseModel):
    """합포장 요금 계산 응답."""
    success: bool = True
    vendor: str
    item: Optional[InvoiceItem] = None
    error: Optional[str] = None


# ─────────────────────────────────────
# 배송통계
# ─────────────────────────────────────
class ShippingStatsRequest(BaseModel):
    """배송통계 조회 요청."""
    vendor: str = Field(..., description="공급처명")
    date_from: date = Field(..., description="시작일")
    date_to: date = Field(..., description="종료일")


class ShippingStatsResponse(BaseModel):
    """배송통계 조회 응답."""
    success: bool = True
    vendor: str
    count: int = Field(..., description="배송 건수")
    data: List[Dict[str, Any]] = Field(default_factory=list, description="상세 데이터")


# ─────────────────────────────────────
# 가견적 계산
# ─────────────────────────────────────
class WorkLogEntry(BaseModel):
    """작업일지 항목 (분류/의류 등)."""
    분류: str = Field(..., description="분류명 (예: 의류)")
    수량: int = Field(..., ge=0)
    단가: int = Field(..., ge=0)


class EstimateCalculateRequest(BaseModel):
    """가견적 계산 요청."""
    # 수신처 (PDF/저장 시 견적서에 반영)
    company_name: Optional[str] = Field(default="", description="업체명")
    contact: Optional[str] = Field(default="", description="연락처")
    email: Optional[str] = Field(default="", description="이메일")
    # 출고
    monthly_outbound: int = Field(..., ge=0, description="월 출고건수")
    rate_type: str = Field(default="표준", description="택배 요금제 (표준/A)")
    zone_ratios: Optional[Dict[str, float]] = Field(
        default=None,
        description="구간별 비율 (극소, 소, 중, 대, 특대, 특특대). 합 1.0. 없으면 극소 100%"
    )
    # 반품: 전체 출고건 대비 % (0~100)
    return_percentage: Optional[float] = Field(default=0, ge=0, le=100, description="반품 비율 (%)")
    # 입고수량
    inbound_qty: Optional[int] = Field(default=None, ge=0, description="입고수량")
    # 합포장: 출고건 대비 % (0~100), 평균 수량(건당 개수, 선택)
    combined_percentage: Optional[float] = Field(default=0, ge=0, le=100, description="합포장 비율 (%)")
    combined_avg_qty: Optional[int] = Field(default=None, ge=0, description="합포장 평균 수량 (건당 개수)")
    # 브랜드유형: 패션(fashion) / 뷰티(beauty) / 기타(etc)
    brand_type: Optional[str] = Field(default="etc", description="브랜드유형: fashion, beauty, etc")
    # 패션 선택 시 양품화 작업 필요 여부 (입고수량 × 500원)
    need_quality_work: Optional[bool] = Field(default=False, description="양품화 작업 필요 (패션일 때)")
    # PP 봉투: brand=브랜드 제공(비용 없음), ours=우리 쪽(입고수량×단가)
    pp_bag_provider: Optional[str] = Field(default="brand", description="PP 봉투: brand, ours")
    # 택배 봉투: brand=브랜드 제공(비용 없음), ours=우리 쪽(구간별 단가)
    mailer_provider: Optional[str] = Field(default="brand", description="택배 봉투: brand, ours")
    # 텍작업 150원/건 필요 여부 (입고수량 × 150원)
    need_tex_work: Optional[bool] = Field(default=False, description="텍작업 필요")
    # 바코드 부착 필요 여부 (입고수량 × 단가)
    need_barcode_attach: Optional[bool] = Field(default=False, description="바코드 부착 필요")
    # 완충작업 (출고건 × 단가)
    need_void_work: Optional[bool] = Field(default=False, description="완충작업 필요")
    # 출고영상촬영 (출고건 × 단가)
    need_video_out: Optional[bool] = Field(default=False, description="출고영상촬영 필요")
    # 반품영상촬영 (반품건 × 단가)
    need_video_ret: Optional[bool] = Field(default=False, description="반품영상촬영 필요")
    # 화장품/기타 선택 시: box=박스 입고, piece=개당 입고
    inbound_type: Optional[str] = Field(default="piece", description="입고 방식: box(박스 입고), piece(개당 입고)")
    # 보관: PLT 기준 보관량, SKU 수. 1 PLT당 SKU > 2이면 중량랙 적용
    storage_plt: Optional[int] = Field(default=None, ge=0, description="보관량 (PLT 기준)")
    sku_count: Optional[int] = Field(default=None, ge=0, description="SKU 수")
    # 추가 작업: 청구서 항목 중 선택 + 수량 (단가는 API에서 조회)
    extra_work_entries: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="추가 작업 [{ item_name: str, qty: int }, ...]"
    )
    work_log_entries: Optional[List[WorkLogEntry]] = Field(default_factory=list)


class EstimateCalculateResponse(BaseModel):
    """가견적 계산 응답."""
    success: bool = True
    items: List[InvoiceItem] = Field(default_factory=list)
    total_amount: int = 0
    company_name: str = ""
    contact: str = ""
    email: str = ""
    warnings: List[str] = Field(default_factory=list)


class EstimateExportPdfRequest(BaseModel):
    """견적서 PDF 출력 요청 (입력값 반영)."""
    company_name: str = Field(default="", description="업체명")
    contact: str = Field(default="", description="연락처")
    email: str = Field(default="", description="이메일")
    items: List[InvoiceItem] = Field(..., description="견적 항목")
    total_amount: int = Field(..., ge=0)


# ─────────────────────────────────────
# 업로드
# ─────────────────────────────────────
class UploadResponse(BaseModel):
    """업로드 응답."""
    success: bool
    message: str
    filename: Optional[str] = None


class UploadListResponse(BaseModel):
    """업로드 목록 응답."""
    success: bool = True
    uploads: List[Dict[str, Any]]


# ─────────────────────────────────────
# PDF 생성
# ─────────────────────────────────────
class PdfItem(BaseModel):
    """PDF 항목."""
    desc: str = Field(..., description="항목 설명")
    qty: int = Field(..., description="수량")
    unit_price: int = Field(..., description="단가")


class CompanyInfo(BaseModel):
    """회사 정보."""
    name: str = Field(..., description="회사명")
    address: Optional[str] = Field(default="", description="주소")
    tel: Optional[str] = Field(default="", description="전화번호")
    email: Optional[str] = Field(default="", description="이메일")


class InvoicePdfRequest(BaseModel):
    """PDF 생성 요청."""
    inv_no: str = Field(..., description="인보이스 번호")
    inv_date: date = Field(..., description="인보이스 날짜")
    seller: CompanyInfo = Field(..., description="발행자 정보")
    buyer: CompanyInfo = Field(..., description="수신자 정보")
    items: List[PdfItem] = Field(..., description="항목 리스트")
    note: Optional[str] = Field(default="", description="비고")
    lang: str = Field(default="ko", description="언어 (ko/en)")


class InvoicePdfResponse(BaseModel):
    """PDF 생성 응답."""
    success: bool = True
    filename: str
    message: str

