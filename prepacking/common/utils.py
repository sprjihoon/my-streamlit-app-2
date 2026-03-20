"""
prepacking/common/utils.py - 공통 유틸
"""
from __future__ import annotations

import hashlib
import re


def safe_str(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", "null", "nat"):
        return ""
    return s


def safe_int(val, default: int = 0) -> int:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def normalize_sku_name(name: str) -> str:
    return re.sub(r"\s+", " ", safe_str(name)).strip()


def make_combination_key(items: list[dict]) -> str:
    """SKU 목록 → 정렬된 고유 키 (name:qty|name:qty)"""
    sorted_items = sorted(items, key=lambda x: x.get("name", ""))
    return "|".join(f"{it['name']}:{it.get('qty', 1)}" for it in sorted_items)


def hash_combination_key(key: str) -> str:
    return hashlib.md5(key.encode()).hexdigest()[:12]
