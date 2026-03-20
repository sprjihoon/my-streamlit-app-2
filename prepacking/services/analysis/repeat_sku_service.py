from __future__ import annotations

import datetime as dt
from collections import defaultdict

from prepacking.common.utils import normalize_sku_name, safe_int
from prepacking.database import get_pp_connection


def _parse_date(s: str) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def analyze_repeat_skus(
    supplier_name: str, date_from: str, date_to: str, min_count: int = 3
) -> list[dict]:
    min_count = max(1, int(min_count))
    with get_pp_connection() as con:
        cur = con.execute(
            """
            SELECT shipping_date, product_name, option_name, qty
            FROM pp_shipping_stats
            WHERE TRIM(supplier_name) = TRIM(?)
              AND shipping_date IS NOT NULL AND shipping_date != ''
              AND date(shipping_date) >= date(?)
              AND date(shipping_date) <= date(?)
            """,
            (supplier_name.strip(), date_from[:10], date_to[:10]),
        )
        raw_rows = cur.fetchall()

    agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "total_count": 0,
            "weekday_counts": {i: 0 for i in range(7)},
            "dates": set(),
            "first": None,
            "last": None,
        }
    )
    for shipping_date, product_name, option_name, qty in raw_rows:
        pn = normalize_sku_name(product_name)
        on = normalize_sku_name(option_name)
        key = (pn, on)
        d = _parse_date(shipping_date or "")
        q = max(1, safe_int(qty, 1))
        a = agg[key]
        a["total_count"] += q
        if d:
            a["weekday_counts"][d.weekday()] += q
            a["dates"].add(d.isoformat())
            ds = d.isoformat()
            if a["first"] is None or ds < a["first"]:
                a["first"] = ds
            if a["last"] is None or ds > a["last"]:
                a["last"] = ds

    out: list[dict] = []
    for (pn, on), a in agg.items():
        if a["total_count"] < min_count:
            continue
        nd = len(a["dates"])
        daily_avg = a["total_count"] / nd if nd else 0.0
        out.append(
            {
                "sku_name": pn,
                "option_name": on,
                "total_count": a["total_count"],
                "daily_avg": daily_avg,
                "weekday_counts": dict(a["weekday_counts"]),
                "first_seen": a["first"] or "",
                "last_seen": a["last"] or "",
            }
        )
    out.sort(key=lambda x: x["total_count"], reverse=True)
    return out
