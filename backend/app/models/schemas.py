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


class InvoiceCalculateResponse(BaseModel):
    """인보이스 계산 응답."""
    success: bool = True
    vendor: str
    date_from: date
    date_to: date
    items: List[InvoiceItem]
    total_amount: int = Field(..., description="총 금액")
    warnings: List[str] = Field(default_factory=list, description="경고 메시지")


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

