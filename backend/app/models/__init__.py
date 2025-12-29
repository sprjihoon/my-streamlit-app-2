"""
backend/app/models - Pydantic 모델 정의
───────────────────────────────────────────
입력 검증용 Pydantic 모델.
"""

from .schemas import (
    # 공통
    HealthResponse,
    ErrorResponse,
    # 인보이스 계산
    InvoiceCalculateRequest,
    InvoiceCalculateResponse,
    InvoiceItem,
    # 개별 요금 계산
    CourierFeeRequest,
    CourierFeeResponse,
    InboundFeeRequest,
    InboundFeeResponse,
    RemoteFeeRequest,
    RemoteFeeResponse,
    CombinedPackFeeRequest,
    CombinedPackFeeResponse,
    # 배송통계
    ShippingStatsRequest,
    ShippingStatsResponse,
    # 업로드
    UploadResponse,
    UploadListResponse,
    # PDF
    InvoicePdfRequest,
    InvoicePdfResponse,
)

__all__ = [
    "HealthResponse",
    "ErrorResponse",
    "InvoiceCalculateRequest",
    "InvoiceCalculateResponse",
    "InvoiceItem",
    "CourierFeeRequest",
    "CourierFeeResponse",
    "InboundFeeRequest",
    "InboundFeeResponse",
    "RemoteFeeRequest",
    "RemoteFeeResponse",
    "CombinedPackFeeRequest",
    "CombinedPackFeeResponse",
    "ShippingStatsRequest",
    "ShippingStatsResponse",
    "UploadResponse",
    "UploadListResponse",
    "InvoicePdfRequest",
    "InvoicePdfResponse",
]

