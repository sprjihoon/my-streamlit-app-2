# -*- coding: utf-8 -*-
"""우체국 HS 검색에서 확인한 10자리 세번.

6자리 코드는 우체국 목록에 없으면 ERR-223 으로 거절된다.
epost_hs10.json 값은 2026-10-01 우체국 상품(HSCODE) 검색 결과다.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name("epost_hs10.json")
_FALLBACK_KEY = "392690"


def _prefer(codes: list[str]) -> str:
    tens = [code for code in codes if len(code) == 10 and code.isdigit()]
    for suffix in ("9000", "0000", "9090", "1000"):
        hits = sorted(code for code in tens if code.endswith(suffix))
        if hits:
            return hits[0]
    return sorted(tens)[0]


@lru_cache(maxsize=1)
def epost_hs_table() -> dict[str, tuple[str, ...]]:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    table: dict[str, tuple[str, ...]] = {}
    for key, codes in raw.items():
        digits = re.sub(r"\D", "", str(key))
        tens = tuple(code for code in codes if len(code) == 10 and code.isdigit())
        if digits and tens:
            table[digits] = tens
    return table


def known_epost_hs_codes() -> set[str]:
    return {code for codes in epost_hs_table().values() for code in codes}


def resolve_epost_hs(code: str) -> str:
    """화면 HS를 우체국 목록에 있는 10자리로 고친다."""
    digits = re.sub(r"\D", "", code or "")
    table = epost_hs_table()
    known = known_epost_hs_codes()
    if len(digits) >= 10 and digits[:10] in known:
        return digits[:10]
    probe = digits[:6] if len(digits) >= 6 else digits
    if probe in table:
        return _prefer(list(table[probe]))

    best_key = ""
    best_n = 1
    for key in table:
        matched = 0
        for left, right in zip(key, probe):
            if left != right:
                break
            matched += 1
        if matched > best_n or (matched == best_n and best_key and key < best_key):
            best_n = matched
            best_key = key
    if best_key and best_n >= 2:
        return _prefer(list(table[best_key]))
    return _prefer(list(table[_FALLBACK_KEY]))
