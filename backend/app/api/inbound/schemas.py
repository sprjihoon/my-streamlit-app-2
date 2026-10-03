"""Pydantic request models for the inbound API."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

# ─────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────

class InboundBatchCreate(BaseModel):
    vendor: str                           # 화주사 (표시명 / 직접입력)
    vendor_canonical: Optional[str] = None  # repair_barcode.업체명 정식명 (선택 시)
    inbound_date: str                     # YYYY-MM-DD
    memo: Optional[str] = None
    created_by: Optional[str] = None


class InboundBatchUpdate(BaseModel):
    status: Optional[str] = None
    memo: Optional[str] = None
    vendor: Optional[str] = None
    inbound_date: Optional[str] = None


class InboundItemUpdate(BaseModel):
    actual_qty: Optional[int] = None
    missing_qty: Optional[int] = None
    status: Optional[str] = None
    memo: Optional[str] = None
    item_name: Optional[str] = None        # 상품명 직접 수정
    option_text: Optional[str] = None      # 옵션 직접 수정
    item_wholesale: Optional[str] = None   # 도매처 직접 수정 (배치 wholesale 오버라이드)
    matched_barcode: Optional[str] = None
    matched_vendor: Optional[str] = None
    matched_product: Optional[str] = None
    matched_option: Optional[str] = None
    supplier_location: Optional[str] = None
    supplier_contact: Optional[str] = None
    confirmed_by: Optional[str] = None  # 로그인 없이 접근하는 작업자 이름
    photo_decision: Optional[str] = None   # 'photo'|'existing'|'new'|'none'


class InboundItemCreate(BaseModel):
    """수동 품목 추가"""
    item_name: str
    option_text: Optional[str] = None
    unit_price: Optional[float] = None
    janggi_qty: int = 0
    actual_qty: int = 0
    missing_qty: int = 0
    matched_barcode: Optional[str] = None
    matched_vendor: Optional[str] = None
    matched_product: Optional[str] = None
    matched_option: Optional[str] = None
    supplier_location: Optional[str] = None
    supplier_contact: Optional[str] = None
    memo: Optional[str] = None

# ── 봇 inbox 사진을 특정 품목에 연결 ────────────────────────────

class InboxPhotoLink(BaseModel):
    inbox_photo_id: str

# ── 마감 (AM/PM 분리) ────────────────────

class CloseRequest(BaseModel):
    """
    close_type:
      'am'  오전 입고접수 완료  confirming → inbound_done (양품화 중)
      'pm'  오후 최종 마감      inbound_done / grading / repairing → done (수량 확정)
    """
    close_type: str = "am"  # "am" | "pm"

# ── 벤더 별칭 관리 ──────────────────────

class VendorAliasUpdate(BaseModel):
    aliases: List[str]     # 새 별칭 목록 (덮어쓰기)
    memo: Optional[str] = None

# ── 화주사 공유 링크 생성 ────────────────

class ShareLinkCreate(BaseModel):
    password: Optional[str] = None
    expires_days: int = 7
    allow_excel: bool = False

# ── 불량일지·수선일지 inbound_item 연결 ─────────────────

class DefectLogLink(BaseModel):
    불량명: str
    수량: int = 1
    비고: Optional[str] = None
    작성자: Optional[str] = None

class RepairLogLink(BaseModel):
    불량명: Optional[str] = None
    작업: str
    수량: int = 1
    비용: int = 0
    비고: Optional[str] = None
    작성자: Optional[str] = None
    repair_action: Optional[str] = None  # 허용값: _REPAIR_ACTION_TRANSITIONS 키
    # 하위 호환: repair_action 없을 때 명시적 지정 (기존 클라이언트용)
    qty_from: Optional[str] = None
    qty_to: Optional[str] = None

# ── 정상처리 수량 입력·정정 ────────────────────────────────────

class NormalQtyUpdate(BaseModel):
    normal_qty: int
    confirmed_by: Optional[str] = None
