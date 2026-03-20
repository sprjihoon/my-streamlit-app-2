"""
prepacking/common/enums.py - 상태값 Enum 정의
"""
from enum import Enum


class RecommendationStatus(str, Enum):
    RECOMMENDED = "recommended"
    APPROVED = "approved"
    MODIFIED = "modified"
    HELD = "held"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ExecutionStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    CANCELED = "canceled"


class PackStatus(str, Enum):
    PACKED = "packed"
    PARTIALLY_USED = "partially_used"
    FULLY_USED = "fully_used"
    WAITING_UNWRAP = "waiting_unwrap"
    UNWRAPPED = "unwrapped"
    EXPIRED = "expired"
    DISPOSED = "disposed"


class LocationAction(str, Enum):
    PUTAWAY = "putaway"
    MOVE = "move"
    USE = "use"
    UNWRAP = "unwrap"
    RETURN = "return"
    DISPOSE = "dispose"


class ValidationResult(str, Enum):
    MATCHED = "matched"
    OVER = "over"
    UNDER = "under"
    MISSED = "missed"


class ExceptionType(str, Enum):
    EXCLUDED = "excluded"
    CONDITIONAL = "conditional"
    TEMPORARY_HOLD = "temporary_hold"
    NEW_SKU = "new_sku"


class TargetType(str, Enum):
    SINGLE_SKU = "single_sku"
    COMBINATION = "combination"
