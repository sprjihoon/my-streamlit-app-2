"""Barcode master updates and item matching."""
from __future__ import annotations

from typing import List, Optional

from logic.db import get_connection

from .utils import logger

def _update_barcode_master(
    con,
    barcode: str,
    wholesale: str = "",
    supplier_location: str = "",
    supplier_contact: str = "",
    matched_product: str = "",   # 도매처상품명 → repair_barcode.제품명
    matched_option: str = "",    # 도매처옵션   → repair_barcode.옵션
) -> None:
    """매칭 확정 시 repair_barcode 마스터의 도매처·위치·연락처·상품명·옵션을 갱신한다.

    - 해당 바코드 레코드가 없으면 아무 작업도 하지 않는다.
    - 빈 문자열은 기존 값을 덮어쓰지 않는다.
    """
    # 신규 컬럼 마이그레이션
    for col in ("도매처주소 TEXT", "도매처연락처 TEXT"):
        try:
            con.execute(f"ALTER TABLE repair_barcode ADD COLUMN {col}")
        except Exception:
            pass

    # 업데이트할 필드 수집 (값이 있는 것만)
    col_map = [
        (wholesale,          "도매처"),
        (supplier_location,  "도매처주소"),
        (supplier_contact,   "도매처연락처"),
        (matched_product,    "제품명"),
        (matched_option,     "옵션"),
    ]
    sets, vals = [], []
    for val, col in col_map:
        if val:
            sets.append(f"{col}=?"); vals.append(val)

    if not sets:
        return

    vals.append(barcode)
    try:
        con.execute(f"UPDATE repair_barcode SET {', '.join(sets)} WHERE 바코드=?", vals)
        updated = {col_map[i][1]: vals[i] for i in range(len(sets))}
        logger.info(f"바코드 마스터 업데이트: {barcode} → {updated}")
    except Exception as e:
        logger.warning(f"바코드 마스터 업데이트 실패 ({barcode}): {e}")

# ─────────────────────────────────────
# 상품 자동 매칭
# ─────────────────────────────────────

def _resolve_vendor_names(vendor: str) -> List[str]:
    """
    주어진 vendor 문자열에 대해 매칭 가능한 모든 업체명 반환.
    1) repair_barcode 에 vendor 그대로 있으면 우선
    2) inbound_vendor_aliases 에서 canonical 또는 alias 로 등록된 업체 포함
    3) 없으면 [vendor] 그대로
    """
    names = [vendor]
    with get_connection() as con:
        # canonical 로 등록된 경우 → 별칭들도 추가 (역방향: 별칭 포함 바코드 검색 위해)
        row = con.execute(
            "SELECT aliases FROM inbound_vendor_aliases WHERE canonical=?", (vendor,)
        ).fetchone()
        if row and row[0]:
            names += [a.strip() for a in row[0].split(",") if a.strip()]
        # 혹시 vendor 가 별칭으로 등록된 경우 → canonical 추가
        rows = con.execute(
            "SELECT canonical FROM inbound_vendor_aliases WHERE aliases LIKE ?",
            (f"%{vendor}%",)
        ).fetchall()
        for r in rows:
            if r[0] not in names:
                names.append(r[0])
    return list(dict.fromkeys(names))  # 중복 제거, 순서 유지


def _match_barcode(vendor: str, item_name: str, option_text: Optional[str], wholesale: Optional[str]) -> dict:
    """
    repair_barcode DB에서 품목을 매칭한다.
    반환: {matched_barcode, matched_vendor, matched_product, matched_option, match_confidence, needs_matching}
    """
    result = {
        "matched_barcode": None,
        "matched_vendor": None,
        "matched_product": None,
        "matched_option": None,
        "supplier_location": None,   # 도매처주소
        "supplier_contact": None,    # 도매처연락처
        "match_confidence": 0.0,
        "needs_matching": True,
    }
    if not item_name:
        return result

    vendor_names = _resolve_vendor_names(vendor)  # 별칭 포함 후보 업체명 목록
    vendor_ph = ",".join("?" * len(vendor_names))  # IN (?,?,...) 플레이스홀더

    def _row_to_result(row, confidence: float, needs: bool) -> dict:
        return {
            **result,
            "matched_barcode": row[0],
            "matched_vendor": row[1],
            "matched_product": row[2] or item_name,
            "matched_option": row[3],
            "supplier_location": row[4] if len(row) > 4 else None,
            "supplier_contact": row[5] if len(row) > 5 else None,
            "match_confidence": confidence,
            "needs_matching": needs,
        }

    _sel = "SELECT 바코드, 업체명, 제품명, 옵션, 도매처주소, 도매처연락처"

    with get_connection() as con:
        # 1순위: 화주사(별칭 포함) + 도매처 + 제품명/상품명 + 옵션 정확 매칭
        if wholesale and option_text:
            row = con.execute(f"""
                {_sel}
                FROM repair_barcode
                WHERE 업체명 IN ({vendor_ph}) AND 도매처=?
                  AND (제품명=? OR 상품명=?)
                  AND 옵션=?
                LIMIT 1
            """, (*vendor_names, wholesale, item_name, item_name, option_text)).fetchone()
            if row:
                return _row_to_result(row, 1.0, False)

        # 2순위: 화주사(별칭 포함) + 도매처 + 제품명/상품명 (옵션 무시)
        if wholesale:
            row = con.execute(f"""
                {_sel}
                FROM repair_barcode
                WHERE 업체명 IN ({vendor_ph}) AND 도매처=?
                  AND (제품명=? OR 상품명=?)
                LIMIT 1
            """, (*vendor_names, wholesale, item_name, item_name)).fetchone()
            if row:
                return _row_to_result(row, 0.85, False)

        # 3순위: 화주사(별칭 포함) + 제품명/상품명
        row = con.execute(f"""
            {_sel}
            FROM repair_barcode
            WHERE 업체명 IN ({vendor_ph}) AND (제품명=? OR 상품명=?)
            LIMIT 1
        """, (*vendor_names, item_name, item_name)).fetchone()
        if row:
            return _row_to_result(row, 0.7, False)

        # 4순위: 부분 일치 (LIKE) — 화주사 별칭 포함
        keyword = f"%{item_name}%"
        row = con.execute(f"""
            {_sel}
            FROM repair_barcode
            WHERE 업체명 IN ({vendor_ph}) AND (제품명 LIKE ? OR 상품명 LIKE ?)
            LIMIT 1
        """, (*vendor_names, keyword, keyword)).fetchone()
        if row:
            return _row_to_result(row, 0.5, True)

    return result
