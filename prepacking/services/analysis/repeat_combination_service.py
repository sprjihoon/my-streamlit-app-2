from __future__ import annotations

import datetime as dt
from collections import defaultdict

from prepacking.common.utils import (
    make_combination_key,
    normalize_sku_name,
    safe_int,
    safe_str,
)
from prepacking.database import get_pp_connection


def _parse_date(s: str) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _group_bucket(combo_no: str, invoice_no: str, order_no: str) -> str:
    c = safe_str(combo_no)
    if c:
        return c
    i = safe_str(invoice_no)
    if i:
        return i
    return safe_str(order_no)


def _sku_line_name(sku_code: str, product_name: str, option_name: str) -> str:
    sc = safe_str(sku_code)
    if sc:
        return sc
    return f"{normalize_sku_name(product_name)}|{normalize_sku_name(option_name)}"


def analyze_repeat_combinations(
    supplier_name: str, date_from: str, date_to: str, min_count: int = 3
) -> list[dict]:
    min_count = max(1, int(min_count))
    with get_pp_connection() as con:
        cur = con.execute(
            """
            SELECT shipping_date, combo_no, invoice_no, order_no,
                   product_name, option_name, sku_code, qty, inner_qty
            FROM pp_shipping_stats
            WHERE TRIM(supplier_name) = TRIM(?)
              AND shipping_date IS NOT NULL AND shipping_date != ''
              AND date(shipping_date) >= date(?)
              AND date(shipping_date) <= date(?)
            """,
            (supplier_name.strip(), date_from[:10], date_to[:10]),
        )
        raw_rows = cur.fetchall()

    groups: dict[tuple[str, str], list] = defaultdict(list)
    for row in raw_rows:
        sd, combo_no, invoice_no, order_no = row[0], row[1], row[2], row[3]
        bucket = _group_bucket(combo_no, invoice_no, order_no)
        if not bucket:
            continue
        sd_key = safe_str(sd)[:10]
        groups[(sd_key, bucket)].append(row)

    combo_occurrences: list[tuple[str, dt.date | None, list[dict]]] = []
    for (sd_key, _bucket), lines in groups.items():
        sku_keys = set()
        for _sd, _c, _i, _o, pn, on, sku, _q, iq in lines:
            sku_keys.add(
                (
                    safe_str(sku),
                    normalize_sku_name(pn),
                    normalize_sku_name(on),
                )
            )
        multi_sku = len(sku_keys) >= 2
        inner_hit = any(max(1, safe_int(x[8], 1)) >= 2 for x in lines)
        if not (multi_sku or inner_hit):
            continue
        qty_by_name: dict[str, int] = defaultdict(int)
        merged: dict[tuple[str, str, str], dict] = {}
        for _sd, _c, _i, _o, pn, on, sku, q, iq in lines:
            nm = _sku_line_name(sku, pn, on)
            qv = max(1, safe_int(q, 1))
            qty_by_name[nm] += qv
            ik = (safe_str(sku), normalize_sku_name(pn), normalize_sku_name(on))
            iq_v = max(1, safe_int(iq, 1))
            if ik not in merged:
                merged[ik] = {
                    "sku_code": safe_str(sku),
                    "product_name": ik[1],
                    "option_name": ik[2],
                    "qty": 0,
                    "inner_qty": iq_v,
                }
            merged[ik]["qty"] += qv
            merged[ik]["inner_qty"] = max(merged[ik]["inner_qty"], iq_v)
        items_canonical = list(merged.values())
        items_for_key = [{"name": k, "qty": v} for k, v in sorted(qty_by_name.items())]
        ckey = make_combination_key(items_for_key)
        d = _parse_date(sd_key)
        combo_occurrences.append((ckey, d, items_canonical))

    agg: dict[str, dict] = defaultdict(
        lambda: {
            "items": [],
            "total_count": 0,
            "weekday_counts": {i: 0 for i in range(7)},
            "dates": set(),
            "first": None,
            "last": None,
        }
    )
    for ckey, d, items_detail in combo_occurrences:
        a = agg[ckey]
        if not a["items"]:
            a["items"] = list(items_detail)
        a["total_count"] += 1
        if d:
            a["weekday_counts"][d.weekday()] += 1
            ds = d.isoformat()
            a["dates"].add(ds)
            if a["first"] is None or ds < a["first"]:
                a["first"] = ds
            if a["last"] is None or ds > a["last"]:
                a["last"] = ds

    out: list[dict] = []
    for ckey, a in agg.items():
        if a["total_count"] < min_count:
            continue
        nd = len(a["dates"])
        daily_avg = a["total_count"] / nd if nd else 0.0
        out.append(
            {
                "combination_key": ckey,
                "items": a["items"],
                "total_count": a["total_count"],
                "daily_avg": daily_avg,
                "weekday_counts": dict(a["weekday_counts"]),
                "first_seen": a["first"] or "",
                "last_seen": a["last"] or "",
            }
        )
    out.sort(key=lambda x: x["total_count"], reverse=True)
    return out


def load_repeat_combo_daily_totals(
    supplier_name: str, target_date: str, lookback_days: int
) -> list[dict]:
    """forecast_service에서 호출: 조합별 일별 출하 합계 + 구성 SKU 상세를 반환."""
    d_end = _parse_date(target_date)
    if not d_end:
        return []
    d_start = d_end - dt.timedelta(days=max(1, lookback_days))
    with get_pp_connection() as con:
        cur = con.execute(
            """
            SELECT shipping_date, combo_no, invoice_no, order_no,
                   product_name, option_name, sku_code, qty, inner_qty, barcode
            FROM pp_shipping_stats
            WHERE TRIM(supplier_name) = TRIM(?)
              AND shipping_date IS NOT NULL AND shipping_date != ''
              AND date(shipping_date) >= date(?)
              AND date(shipping_date) < date(?)
            """,
            (supplier_name.strip(), d_start.isoformat(), d_end.isoformat()),
        )
        raw_rows = cur.fetchall()

    groups: dict[tuple[str, str], list] = defaultdict(list)
    for row in raw_rows:
        sd, combo_no, invoice_no, order_no = row[0], row[1], row[2], row[3]
        bucket = _group_bucket(combo_no, invoice_no, order_no)
        if not bucket:
            continue
        sd_key = safe_str(sd)[:10]
        groups[(sd_key, bucket)].append(row)

    combo_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    combo_dates: dict[str, set] = defaultdict(set)
    combo_name_map: dict[str, str] = {}
    combo_items_map: dict[str, list[dict]] = {}
    for (sd_key, _bucket), lines in groups.items():
        sku_keys = set()
        for row in lines:
            _sd, _c, _i, _o, pn, on, sku, _q, iq = row[:9]
            sku_keys.add((safe_str(sku), normalize_sku_name(pn), normalize_sku_name(on)))
        multi_sku = len(sku_keys) >= 2
        inner_hit = any(max(1, safe_int(x[8], 1)) >= 2 for x in lines)
        if not (multi_sku or inner_hit):
            continue
        qty_by_name: dict[str, int] = defaultdict(int)
        merged: dict[tuple[str, str, str], dict] = {}
        for row in lines:
            pn, on, sku, q, iq = row[4], row[5], row[6], row[7], row[8]
            barcode = safe_str(row[9]) if len(row) > 9 else ""
            nm = _sku_line_name(sku, pn, on)
            qv = max(1, safe_int(q, 1))
            qty_by_name[nm] += qv
            ik = (safe_str(sku), normalize_sku_name(pn), normalize_sku_name(on))
            if ik not in merged:
                merged[ik] = {
                    "sku_code": safe_str(sku),
                    "barcode": barcode,
                    "product_name": ik[1],
                    "option_name": ik[2],
                    "qty": 0,
                }
            merged[ik]["qty"] += qv
            if barcode and not merged[ik]["barcode"]:
                merged[ik]["barcode"] = barcode
        items_for_key = [{"name": k, "qty": v} for k, v in sorted(qty_by_name.items())]
        ckey = make_combination_key(items_for_key)
        combo_daily[ckey][sd_key] += 1
        if sd_key:
            combo_dates[ckey].add(sd_key)
        if ckey not in combo_name_map:
            combo_name_map[ckey] = ckey
        if ckey not in combo_items_map:
            combo_items_map[ckey] = list(merged.values())

    out: list[dict] = []
    for ckey, daily in combo_daily.items():
        out.append({
            "target_name": combo_name_map.get(ckey, ckey),
            "combination_key": ckey,
            "daily": dict(daily),
            "frequency": len(combo_dates[ckey]),
            "items": combo_items_map.get(ckey, []),
        })
    return out
