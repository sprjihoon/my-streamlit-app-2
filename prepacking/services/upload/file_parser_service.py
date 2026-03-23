from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

from prepacking.common.utils import safe_int, safe_str

_FIELD_ALIASES: list[tuple[str, frozenset[str]]] = [
    (
        "shipping_date",
        frozenset(
            {
                "shipping_date",
                "ship_date",
                "delivery_date",
                "배송일",
                "배송 일",
            }
        ),
    ),
    (
        "supplier_name",
        frozenset(
            {
                "supplier_name",
                "supplier",
                "vendor",
                "공급처",
                "공급 업체",
            }
        ),
    ),
    (
        "order_no",
        frozenset(
            {
                "order_no",
                "order_number",
                "orderno",
                "주문번호",
                "주문 번호",
            }
        ),
    ),
    (
        "invoice_no",
        frozenset(
            {
                "invoice_no",
                "invoice_number",
                "tracking",
                "송장번호",
                "송장 번호",
            }
        ),
    ),
    (
        "combo_no",
        frozenset(
            {
                "combo_no",
                "bundle_no",
                "합포번호",
                "합포 번호",
            }
        ),
    ),
    (
        "product_name",
        frozenset(
            {
                "product_name",
                "product",
                "item_name",
                "상품명",
                "상품 명",
            }
        ),
    ),
    (
        "option_name",
        frozenset(
            {
                "option_name",
                "option",
                "옵션",
                "옵션명",
            }
        ),
    ),
    (
        "sku_code",
        frozenset(
            {
                "sku_code",
                "sku",
                "product_code",
                "품번",
                "상품코드",
                "상품 코드",
                "sku코드",
            }
        ),
    ),
    (
        "barcode",
        frozenset(
            {
                "barcode",
                "bar_code",
                "상품바코드",
                "상품 바코드",
                "바코드",
            }
        ),
    ),
    (
        "qty",
        frozenset(
            {
                "qty",
                "quantity",
                "수량",
            }
        ),
    ),
    (
        "inner_qty",
        frozenset(
            {
                "inner_qty",
                "inner_quantity",
                "내품수량",
                "내품 수량",
            }
        ),
    ),
    (
        "admin_product_qty",
        frozenset(
            {
                "admin_product_qty",
                "admin_qty",
                "어드민상품명수량",
                "어드민 상품명수량",
            }
        ),
    ),
]


def _norm_key(h: object) -> str:
    s = safe_str(h)
    s = re.sub(r"\s+", "", s)
    return s.casefold() if s.isascii() else s


def _build_column_map(columns: list) -> dict[str, str]:
    seen: set[str] = set()
    mapping: dict[str, str] = {}
    for col in columns:
        raw = safe_str(col)
        if not raw:
            continue
        nk = _norm_key(raw)
        if nk in seen:
            continue
        seen.add(nk)
        for field, aliases in _FIELD_ALIASES:
            if nk in {_norm_key(a) for a in aliases} or raw.strip() in aliases:
                if field not in mapping:
                    mapping[field] = raw
                break
    return mapping


def _coerce_date(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if isinstance(val, pd.Timestamp):
        return val.date().isoformat()
    if isinstance(val, dt.datetime):
        return val.date().isoformat()
    if isinstance(val, dt.date):
        return val.isoformat()
    s = safe_str(val)
    if not s:
        return ""
    ts = pd.to_datetime(s, errors="coerce")
    if not pd.isna(ts):
        return ts.date().isoformat()
    try:
        x = float(s)
        if x > 1000:
            base = dt.datetime(1899, 12, 30) + dt.timedelta(days=int(x))
            return base.date().isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    return ""


def _read_frame(file_path: str) -> pd.DataFrame:
    path = Path(file_path)
    suf = path.suffix.lower()
    if suf in (".xlsx", ".xlsm"):
        return pd.read_excel(path, engine="openpyxl")
    if suf == ".xls":
        try:
            return pd.read_excel(path, engine="xlrd")
        except Exception:
            pass
        try:
            return pd.read_html(path)[0]
        except Exception:
            pass
        return pd.read_excel(path)
    if suf == ".csv":
        for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
            try:
                return pd.read_csv(path, encoding=enc)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file type: {suf}")


def parse_shipping_file(file_path: str) -> list[dict]:
    df = _read_frame(file_path)
    df.columns = [safe_str(c) for c in df.columns]
    cmap = _build_column_map(list(df.columns))
    rows: list[dict] = []
    for _, ser in df.iterrows():
        def get(field: str, default="") -> str:
            c = cmap.get(field)
            if not c or c not in ser.index:
                return default
            v = ser.get(c)
            if field == "shipping_date":
                return _coerce_date(v)
            if field in ("qty", "inner_qty"):
                return str(safe_int(v, 0))
            if pd.isna(v):
                return default
            return safe_str(v)

        rec = {
            "shipping_date": get("shipping_date"),
            "supplier_name": get("supplier_name"),
            "order_no": get("order_no"),
            "invoice_no": get("invoice_no"),
            "combo_no": get("combo_no"),
            "product_name": get("product_name"),
            "option_name": get("option_name"),
            "sku_code": get("sku_code"),
            "barcode": get("barcode"),
            "qty": safe_int(get("qty", "1"), 1),
            "inner_qty": safe_int(get("inner_qty", "1"), 1),
            "admin_product_qty": get("admin_product_qty"),
        }
        rows.append(rec)
    return rows

