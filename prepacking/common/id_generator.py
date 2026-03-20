"""
prepacking/common/id_generator.py - ID 생성
"""
from __future__ import annotations

import uuid
from .date_helper import now_kst


def generate_id(prefix: str = "PP") -> str:
    ts = now_kst().strftime("%Y%m%d%H%M%S")
    short = uuid.uuid4().hex[:6].upper()
    return f"{prefix}-{ts}-{short}"
