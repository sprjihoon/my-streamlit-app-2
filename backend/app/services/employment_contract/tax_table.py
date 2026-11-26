"""2023년 근로소득 간이세액표. 급여대장 엑셀과 같은 표이다."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

TABLE_PATH = Path(__file__).with_name("simple_tax_table.json")


@lru_cache(maxsize=1)
def _rows() -> tuple[tuple[int, ...], ...]:
    return tuple(tuple(row) for row in json.loads(TABLE_PATH.read_text(encoding="utf-8")))


def lookup_simple_tax(taxable: int, dependents: int = 1) -> int:
    """월 과세급여와 공제대상 가족 수로 간이세액을 찾는다. 가족 수는 1~10명."""
    count = max(1, min(int(dependents or 1), 10))
    thousand = max(int(taxable), 0) // 1000
    table = _rows()
    if thousand < table[0][0]:
        return 0
    chosen = table[-1]
    for row in table:
        if row[0] <= thousand < row[1]:
            chosen = row
            break
        if thousand >= row[0]:
            chosen = row
    return int(chosen[count + 1])
