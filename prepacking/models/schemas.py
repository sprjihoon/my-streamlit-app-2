from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class PPUploadResponse(BaseModel):
    upload_id: int
    file_name: str
    upload_status: str = "processing"


class PPUploadStatusResponse(BaseModel):
    upload_id: int
    upload_status: str
    row_count: int = 0
    skipped_count: int = 0
    total_count: int = 0
    error_message: str = ""


class PPUploadListItem(BaseModel):
    upload_id: int
    file_name: str
    file_version: int
    uploaded_at: str
    uploaded_by: str
    row_count: int
    applied_yn: bool
    note: str
    upload_status: str = "completed"
    skipped_count: int = 0
    total_count: int = 0


class PPAnalysisRequest(BaseModel):
    supplier_name: str
    date_from: str = ""
    date_to: str = ""
    min_count: int = Field(default=3, ge=1)


class PPRecommendationRequest(BaseModel):
    supplier_name: str
    target_date: str
    source_upload_id: Optional[int] = None


class PPWorkOrderRequest(BaseModel):
    target_date: str
    supplier_name: str = ""


class PPApprovalRequest(BaseModel):
    action_type: str
    adjusted_qty: Optional[int] = None
    reason: str = ""
    by: str = ""
    memo: str = ""


class PPExecutionRequest(BaseModel):
    recommendation_id: int
    executed_qty: int
    executed_by: str = ""
    location_code: str = ""
    memo: str = ""


class PPStockUseRequest(BaseModel):
    use_qty: int
    used_by: str = ""


class PPLocationCreate(BaseModel):
    location_code: str
    location_name: str = ""
    zone: str = ""
    location_type: str = "shelf"
    max_capacity: int = Field(default=100, ge=0)


class PPMoveStockRequest(BaseModel):
    stock_id: int
    from_location: str
    to_location: str
    qty: int
    moved_by: str = ""
    reason: str = ""


class PPUnwrapRequest(BaseModel):
    stock_id: int
    unwrap_qty: int
    reason: str = ""
    return_to_stock: bool = False
    return_location: str = ""
    unwrap_by: str = ""


class PPValidationRequest(BaseModel):
    supplier_name: str
    target_date: str


class PPWalkForwardRequest(BaseModel):
    supplier_name: str
    test_start: str
    test_end: str
    train_min_days: int = Field(default=30, ge=7)
    max_skus: int = Field(default=100, ge=10)


class PPExceptionCreate(BaseModel):
    supplier_name: str
    target_type: str
    target_code: str
    target_name: str
    exception_type: str
    reason: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    created_by: str = ""


class PPSettingsRequest(BaseModel):
    supplier_name: str = ""
    key: str = ""
    value: str = ""


def pp_optional_date_str(value: object | None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None
