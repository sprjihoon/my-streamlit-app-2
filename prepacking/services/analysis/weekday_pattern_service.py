from __future__ import annotations

import datetime as dt
from collections import defaultdict
from statistics import mean, pstdev

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


def _range_weekday_counts(d0: dt.date, d1: dt.date) -> dict[int, int]:
    c: dict[int, int] = {i: 0 for i in range(7)}
    d = d0
    while d <= d1:
        c[d.weekday()] += 1
        d += dt.timedelta(days=1)
    return c


def _variability(weekday_counts: dict[int, int]) -> float:
    arr = [int(weekday_counts.get(i, 0)) for i in range(7)]
    m = mean(arr)
    if m <= 0:
        return 0.0
    return pstdev(arr) / m


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


def analyze_weekday_patterns(
    supplier_name: str, date_from: str, date_to: str
) -> dict:
    today = dt.date.today()
    d_from = _parse_date(date_from) or today
    d_to = _parse_date(date_to) or today
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    span = _range_weekday_counts(d_from, d_to)

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

    sku_wc: dict[tuple[str, str], dict[int, int]] = defaultdict(
        lambda: {i: 0 for i in range(7)}
    )
    combo_wc: dict[str, dict[int, int]] = defaultdict(
        lambda: {i: 0 for i in range(7)}
    )
    combo_names: dict[str, str] = {}
    overall_orders_by_wd: dict[int, int] = {i: 0 for i in range(7)}

    groups: dict[tuple[str, str], list] = defaultdict(list)
    for row in raw_rows:
        sd, combo_no, invoice_no, order_no = row[0], row[1], row[2], row[3]
        bucket = _group_bucket(combo_no, invoice_no, order_no)
        if not bucket:
            continue
        sd_key = safe_str(sd)[:10]
        groups[(sd_key, bucket)].append(row)

    for (sd_key, _bucket), lines in groups.items():
        d = _parse_date(sd_key)
        if not d:
            continue
        wd = d.weekday()
        overall_orders_by_wd[wd] += 1

        for _sd, _c, _i, _o, pn, on, sku, q, _iq in lines:
            pn2 = normalize_sku_name(pn)
            on2 = normalize_sku_name(on)
            qv = max(1, safe_int(q, 1))
            sku_wc[(pn2, on2)][wd] += qv

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
        for _sd, _c, _i, _o, pn, on, sku, q, _iq in lines:
            nm = _sku_line_name(sku, pn, on)
            qty_by_name[nm] += max(1, safe_int(q, 1))
        items_for_key = [{"name": k, "qty": v} for k, v in sorted(qty_by_name.items())]
        ckey = make_combination_key(items_for_key)
        combo_wc[ckey][wd] += 1
        if ckey not in combo_names:
            combo_names[ckey] = ckey

    sku_patterns: list[dict] = []
    for (pn2, on2), wc in sku_wc.items():
        display = f"{pn2} {on2}".strip() or pn2 or on2
        avgs = {
            w: (wc[w] / span[w]) if span[w] else 0.0 for w in range(7)
        }
        peak = max(range(7), key=lambda w: wc.get(w, 0))
        sku_patterns.append(
            {
                "name": display,
                "weekday_counts": dict(wc),
                "weekday_avgs": avgs,
                "peak_day": peak,
                "variability": _variability(wc),
            }
        )
    sku_patterns.sort(key=lambda x: sum(x["weekday_counts"].values()), reverse=True)

    combo_patterns: list[dict] = []
    for ckey, wc in combo_wc.items():
        avgs = {
            w: (wc[w] / span[w]) if span[w] else 0.0 for w in range(7)
        }
        peak = max(range(7), key=lambda w: wc.get(w, 0))
        combo_patterns.append(
            {
                "name": combo_names.get(ckey, ckey),
                "weekday_counts": dict(wc),
                "weekday_avgs": avgs,
                "peak_day": peak,
                "variability": _variability(wc),
            }
        )
    combo_patterns.sort(key=lambda x: sum(x["weekday_counts"].values()), reverse=True)

    avg_orders_by_weekday = {
        w: overall_orders_by_wd[w] / span[w] if span[w] else 0.0 for w in range(7)
    }

    return {
        "sku_patterns": sku_patterns,
        "combo_patterns": combo_patterns,
        "overall": {
            "total_orders_by_weekday": dict(overall_orders_by_wd),
            "avg_orders_by_weekday": avg_orders_by_weekday,
        },
    }
