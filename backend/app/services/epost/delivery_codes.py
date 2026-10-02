"""우편번호별 집배코드. modo 의 delivery_codes 표와 같은 파일이다."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

_CSV = Path(__file__).with_name("delivery_codes.csv")


class DeliveryCode:
    def __init__(self, row: dict[str, str]) -> None:
        self.zipcode = row["zipcode"]
        self.sort_code_1 = row["sort_code_1"]
        self.sort_code_2 = row["sort_code_2"]
        self.sort_code_3 = row["sort_code_3"]
        self.sort_code_4 = row["sort_code_4"]
        self.arr_cnpo_nm = row["arr_cnpo_nm"]
        self.deliv_po_nm = row["deliv_po_nm"]
        self.course_no = row.get("course_no") or ""


@lru_cache(maxsize=1)
def _table() -> dict[str, DeliveryCode]:
    table: dict[str, DeliveryCode] = {}
    with _CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            zipcode = (row.get("zipcode") or "").strip()
            if len(zipcode) == 5:
                table[zipcode] = DeliveryCode(row)
    return table


def lookup_delivery_code(zipcode: str) -> DeliveryCode | None:
    digits = "".join(ch for ch in (zipcode or "") if ch.isdigit())
    if len(digits) != 5:
        return None
    return _table().get(digits)
