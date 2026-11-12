"""인보이스 항목 계산과 미확정 저장을 분리한다.

웹 `/calculate`는 계산 뒤 기존과 같이 미확정 인보이스를 저장한다.
MCP 미리보기는 계산만 하고, 생성 작업은 미리보기 스냅샷을 저장한다.
"""

from typing import Any, Dict, List

import pandas as pd

from logic.db import get_connection
from logic import (
    add_basic_shipping,
    add_worklog_items,
    add_barcode_fee,
    add_void_fee,
    add_ppbag_fee,
    add_video_out_fee,
    add_return_pickup_fee,
    add_return_courier_fee,
    add_video_ret_fee,
    add_box_fee_by_zone,
    add_storage_fee,
    add_combined_pack_fee,
    add_remote_area_fee,
    calculate_courier_fee_by_zone,
    calculate_inbound_inspection_fee,
    shipping_stats,
)

from backend.app.models import InvoiceCalculateRequest


def compute_invoice_draft(req: InvoiceCalculateRequest) -> Dict[str, Any]:
    """기존 `/calculate`와 같은 순서로 항목·경고·합계를 만든다. 인보이스는 저장하지 않는다."""
    items: List[Dict[str, Any]] = []
    warnings: List[str] = []

    d_from = req.date_from.isoformat()
    d_to = req.date_to.isoformat()

    if req.include_basic_shipping:
        df_items = pd.DataFrame(columns=["항목", "수량", "단가", "금액"])
        try:
            df_items = add_basic_shipping(df_items, req.vendor, d_from, d_to)
            for _, row in df_items.iterrows():
                if row["수량"] > 0:
                    items.append({
                        "항목": row["항목"],
                        "수량": row["수량"],
                        "단가": row["단가"],
                        "금액": row["금액"],
                        "비고": "",
                    })
        except Exception as e:
            warnings.append(f"기본 출고비 계산 오류: {str(e)}")

    zone_counts: Dict[str, int] = {}
    if req.include_courier_fee:
        try:
            zone_counts = calculate_courier_fee_by_zone(
                req.vendor, d_from, d_to, items
            )
            courier_items_count = sum(1 for item in items if "택배요금" in item.get("항목", ""))
            if courier_items_count == 0 and zone_counts:
                warnings.append(
                    f"택배요금 계산: 구간별 수량은 있으나 항목 추가 실패 (구간: {list(zone_counts.keys())})"
                )
            elif not zone_counts:
                warnings.append(
                    "택배요금 계산: 해당 기간에 배송 데이터가 없거나 shipping_zone 테이블에 요금제 데이터가 없습니다."
                )
        except Exception as e:
            warnings.append(f"택배요금 계산 오류: {str(e)}")

    if req.include_combined_fee:
        try:
            df_ship = shipping_stats(req.vendor, d_from, d_to)
            if not df_ship.empty:
                success, error_msg = add_combined_pack_fee(df_ship, items)
                if not success and error_msg:
                    warnings.append(f"합포장 계산 오류: {error_msg}")
        except Exception as e:
            warnings.append(f"합포장 계산 오류: {str(e)}")

    if req.include_remote_fee:
        try:
            success, error_msg, _info_msg = add_remote_area_fee(req.vendor, d_from, d_to, items)
            if not success and error_msg:
                warnings.append(f"도서산간 계산 오류: {error_msg}")
        except Exception as e:
            warnings.append(f"도서산간 계산 오류: {str(e)}")

    if zone_counts:
        box_warnings = add_box_fee_by_zone(items, req.vendor, zone_counts)
        if box_warnings:
            warnings.extend(box_warnings)

    add_barcode_fee(items, req.vendor)
    add_void_fee(items, req.vendor)
    add_ppbag_fee(items, req.vendor)
    add_video_out_fee(items, req.vendor)

    add_return_pickup_fee(items, req.vendor, d_from, d_to)
    add_return_courier_fee(items, req.vendor, d_from, d_to)
    add_video_ret_fee(items, req.vendor, d_from, d_to)

    if req.include_inbound_fee:
        inbound = calculate_inbound_inspection_fee(req.vendor, d_from, d_to)
        if inbound:
            items.append(inbound)

    if req.include_worklog:
        items_before = len(items)
        try:
            add_worklog_items(items, req.vendor, d_from, d_to, source=req.worklog_source)
            items_added = len(items) - items_before
            if items_added == 0:
                with get_connection() as con:
                    wl_total = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
                    wl_vendor = con.execute(
                        "SELECT COUNT(*) FROM work_log WHERE [업체명]=?", (req.vendor,)
                    ).fetchone()[0]
                    wl_cols = [c[1] for c in con.execute("PRAGMA table_info(work_log)")]
                    has_source = "출처" in wl_cols
                    src_info = ""
                    if has_source:
                        src_rows = con.execute(
                            "SELECT [출처], COUNT(*) FROM work_log WHERE [업체명]=? GROUP BY [출처]",
                            (req.vendor,),
                        ).fetchall()
                        src_info = f", 출처분포={dict(src_rows)}"
                    alias_rows = con.execute(
                        "SELECT alias FROM aliases WHERE vendor=? AND file_type IN ('work_log','all')",
                        (req.vendor,),
                    ).fetchall()
                    alias_list = [r[0] for r in alias_rows]
                    date_range = con.execute(
                        "SELECT MIN([날짜]), MAX([날짜]) FROM work_log WHERE [업체명]=?",
                        (req.vendor,),
                    ).fetchone()
                    warnings.append(
                        f"작업일지 0건 반영 - vendor='{req.vendor}', source='{req.worklog_source}', "
                        f"work_log전체={wl_total}건, vendor매칭={wl_vendor}건, "
                        f"aliases={alias_list}, 날짜범위={date_range}{src_info}, "
                        f"요청기간={d_from}~{d_to}"
                    )
        except Exception as e:
            warnings.append(f"작업일지 계산 오류: {str(e)}")

    try:
        add_storage_fee(items, req.vendor)
    except Exception as e:
        warnings.append(f"보관료 조회 오류: {str(e)}")

    try:
        with get_connection() as con:
            table_exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vendor_charges'"
            ).fetchone()
            if table_exists:
                charges = con.execute(
                    """
                    SELECT item_name, qty, unit_price, amount, remark, charge_type
                    FROM vendor_charges
                    WHERE vendor_id = ? AND is_active = 1
                    """,
                    (req.vendor,),
                ).fetchall()
                for charge in charges:
                    items.append({
                        "항목": charge[0],
                        "수량": charge[1],
                        "단가": charge[2],
                        "금액": charge[3],
                        "비고": charge[4] or "",
                    })
    except Exception as e:
        warnings.append(f"추가 비용 조회 오류: {str(e)}")

    raw_total = 0.0
    normalized = []
    for it in items:
        amount = float(it.get("금액") or 0)
        raw_total += amount
        normalized.append({
            "항목": it["항목"],
            "수량": int(float(it["수량"])),
            "단가": int(float(it["단가"])),
            "금액": int(amount),
            "비고": it.get("비고", "") or "",
        })
    # 기준 커밋은 원시 금액을 합친 뒤 한 번만 정수로 만든다. 항목은 각각 정수로 저장한다.
    total_amount = int(raw_total)
    return {
        "vendor": req.vendor,
        "date_from": d_from,
        "date_to": d_to,
        "items": normalized,
        "warnings": warnings,
        "total_amount": int(total_amount),
    }


def insert_unconfirmed_invoice(
    con,
    vendor: str,
    date_from: str,
    date_to: str,
    items: List[Dict[str, Any]],
    total_amount: int,
) -> int:
    """미확정 인보이스를 넣는다. 호출한 쪽에서 커밋한다. 합계가 0이어도 헤더는 남긴다."""
    vendor_row = con.execute(
        "SELECT vendor_id FROM vendors WHERE vendor = ? OR name = ?",
        (vendor, vendor),
    ).fetchone()
    vendor_id = vendor_row[0] if vendor_row else vendor
    cur = con.execute(
        """INSERT INTO invoices
           (vendor_id, period_from, period_to, total_amount, status, created_at)
           VALUES (?, ?, ?, ?, '미확정', datetime('now'))""",
        (vendor_id, date_from, date_to, int(total_amount)),
    )
    invoice_id = cur.lastrowid
    for item in items:
        con.execute(
            """INSERT INTO invoice_items
               (invoice_id, item_name, qty, unit_price, amount, remark)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                invoice_id,
                item["항목"],
                item["수량"],
                item["단가"],
                item["금액"],
                item.get("비고", "") or "",
            ),
        )
    return int(invoice_id)


def find_period_invoice(con, vendor: str, date_from: str, date_to: str):
    """같은 거래처·기간 인보이스가 있으면 id를 반환한다. 덮어쓰지 않기 위한 조회다."""
    row = con.execute(
        """
        SELECT i.invoice_id
        FROM invoices i
        LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
        WHERE i.period_from = ? AND i.period_to = ?
          AND (
            CAST(i.vendor_id AS TEXT) = ?
            OR v.vendor = ?
            OR v.name = ?
          )
        LIMIT 1
        """,
        (date_from, date_to, vendor, vendor, vendor),
    ).fetchone()
    return int(row[0]) if row else None
