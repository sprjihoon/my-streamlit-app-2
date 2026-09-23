"""해외배송 주문 엑셀(HTML .xls / xlsx)을 접수 입력값으로 바꾼다.

합포번호가 같으면 접수 1건이다. 상품 행은 그 건의 인보이스 품목이다.
엑셀에 없거나 숫자로 쓸 수 없는 값은 비워 두고 missing에 적는다.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from io import BytesIO
from typing import Any

from backend.app.services.ems.fields import FALLBACK_NATIONS

_REQUIRED_HEADERS = ("수령자", "배송지주소", "실제 상품명", "상품명")
_KR_ORIGIN_WORDS = (
    "국내",
    "한국",
    "대한민국",
    "korea",
    "south korea",
    "republic of korea",
)
_KR_REGIONS = (
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
    "경기",
    "강원",
    "충청",
    "충북",
    "충남",
    "전라",
    "전북",
    "전남",
    "경상",
    "경북",
    "경남",
    "제주",
    "천안",
)
_COUNTRY_ALIASES = {
    "usa": "US",
    "u.s.a": "US",
    "u.s.a.": "US",
    "america": "US",
    "united states of america": "US",
    "uk": "GB",
    "u.k": "GB",
    "u.k.": "GB",
    "great britain": "GB",
    "england": "GB",
    "korea": "KR",
    "south korea": "KR",
    "republic of korea": "KR",
    "한국": "KR",
    "대한민국": "KR",
}


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._in_cell = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._in_cell = True
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._buf)).strip())
            self._in_cell = False
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._buf.append(data)


def parse_order_workbook(raw: bytes, *, filename: str = "") -> list[dict[str, Any]]:
    if not raw or not raw.strip():
        raise ValueError("엑셀 파일이 비어 있습니다.")
    if len(raw) > 5_000_000:
        raise ValueError("엑셀 파일은 5MB 이하여야 합니다.")
    rows = _read_rows(raw, filename)
    return shipments_from_rows(rows)


def shipments_from_rows(rows: list[list[str]]) -> list[dict[str, Any]]:
    header_at = _header_index(rows)
    if header_at is None:
        raise ValueError("주문 엑셀 헤더를 찾지 못했습니다. 수령자, 배송지주소, 상품명 열이 있는 파일인지 확인해주세요.")
    headers = rows[header_at]
    index = _header_map(headers)
    grouped: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    for offset, cells in enumerate(rows[header_at + 1 :]):
        record = {name: _cell(cells, pos) for name, pos in index.items()}
        if not any(record.values()):
            continue
        key = _group_key(record, offset)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(record)
    shipments = [build_shipment(grouped[key]) for key in order]
    shipments = [item for item in shipments if item["items"] or item["receivename"] or item["receiveaddr3"]]
    if not shipments:
        raise ValueError("엑셀에서 접수할 주문을 찾지 못했습니다.")
    return shipments


def build_shipment(records: list[dict[str, str]]) -> dict[str, Any]:
    first = records[0]
    address = _split_address(first.get("배송지주소", ""), first.get("배송지우편번호", ""))
    if not address["countrycd"]:
        address["countrycd"] = _country_in_text(first.get("메모", ""))
    phone = first.get("수령자전화") or first.get("수령자전화2") or ""
    items = [_item_from_row(row) for row in records]
    items = [item for item in items if item["product_name"]]
    missing = _missing_fields(address, phone, items)
    bundle = first.get("합포번호") or first.get("관리번호") or ""
    return {
        "bundle_no": bundle,
        "receivename": first.get("수령자", ""),
        "receivetelno": phone,
        "receivemail": "",
        "countrycd": address["countrycd"],
        "receivezipcode": address["zipcode"],
        "receiveaddr1": address["addr1"],
        "receiveaddr2": address["addr2"],
        "receiveaddr3": address["addr3"],
        "notes": first.get("메모", ""),
        "totweight": 0,
        "boxlength": 0,
        "boxwidth": 0,
        "boxheight": 0,
        "items": items,
        "missing": missing,
    }


def _read_rows(raw: bytes, filename: str) -> list[list[str]]:
    if _looks_like_html(raw):
        return _rows_from_html(raw)
    name = (filename or "").lower()
    if name.endswith(".xls") and not name.endswith(".xlsx"):
        raise ValueError("이 .xls 파일은 주문표 HTML이 아닙니다. xlsx로 저장하거나 주문 내려받기 파일을 올려주세요.")
    return _rows_from_xlsx(raw)


def _looks_like_html(raw: bytes) -> bool:
    head = raw.lstrip()[:400].lower()
    return head.startswith(b"<") or b"<table" in head or b"<html" in head


def _rows_from_html(raw: bytes) -> list[list[str]]:
    text = raw.decode("utf-8-sig", errors="replace")
    parser = _TableParser()
    parser.feed(text)
    if not parser.rows:
        raise ValueError("엑셀 표에서 행을 읽지 못했습니다.")
    return parser.rows


def _rows_from_xlsx(raw: bytes) -> list[list[str]]:
    try:
        import openpyxl
    except ImportError as exc:
        raise ValueError("xlsx를 읽는 라이브러리가 없습니다.") from exc
    try:
        workbook = openpyxl.load_workbook(BytesIO(raw), data_only=True, read_only=True)
    except Exception as exc:
        raise ValueError("엑셀 파일을 열지 못했습니다. xlsx 또는 주문 HTML(.xls) 파일인지 확인해주세요.") from exc
    try:
        sheet = workbook.active
        rows: list[list[str]] = []
        for row in sheet.iter_rows(values_only=True):
            cells = [_excel_cell(value) for value in row]
            if any(cells):
                rows.append(cells)
        return rows
    finally:
        workbook.close()


def _excel_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, bool):
        return "Y" if value else "N"
    return str(value).strip()


def _header_index(rows: list[list[str]]) -> int | None:
    for i, row in enumerate(rows[:8]):
        names = {cell.strip() for cell in row}
        if "수령자" in names and ("배송지주소" in names or "실제 상품명" in names or "상품명" in names):
            return i
    return None


def _header_map(headers: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for pos, name in enumerate(headers):
        key = name.strip()
        if key and key not in found:
            found[key] = pos
    if not any(name in found for name in _REQUIRED_HEADERS):
        raise ValueError("주문 엑셀 헤더를 찾지 못했습니다. 수령자, 배송지주소, 상품명 열이 있는 파일인지 확인해주세요.")
    return found


def _cell(cells: list[str], pos: int) -> str:
    if pos >= len(cells):
        return ""
    return cells[pos].strip()


def _group_key(record: dict[str, str], offset: int) -> str:
    bundle = record.get("합포번호", "")
    if bundle:
        return f"bundle:{bundle}"
    recipient = record.get("수령자", "")
    address = record.get("배송지주소", "")
    if recipient or address:
        return f"ship:{recipient}|{address}"
    return f"row:{offset}"


def _item_from_row(row: dict[str, str]) -> dict[str, Any]:
    name = row.get("실제 상품명") or row.get("상품명") or ""
    name = re.sub(r"^<상품명>", "", name).strip()
    qty_raw = row.get("판매개수", "")
    try:
        quantity = int(float(qty_raw)) if qty_raw else 1
    except ValueError:
        quantity = 1
    if quantity < 1:
        quantity = 1
    return {
        "product_name": name[:80],
        "name_en": "",
        "quantity": quantity,
        "unit_price_usd": 0,
        "hs_code": "",
        "origin_country": _origin_code(row.get("원산지", "")),
    }


def _origin_code(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in {"kr", "kor"} or any(word in lowered for word in _KR_ORIGIN_WORDS):
        return "KR"
    if any(region in text for region in _KR_REGIONS):
        return "KR"
    if re.fullmatch(r"[A-Za-z]{2}", text):
        return text.upper()
    return ""


def _split_address(address: str, zip_hint: str) -> dict[str, str]:
    parts = [part.strip() for part in (address or "").split(",") if part.strip()]
    countrycd = ""
    if parts:
        matched = _match_country(parts[-1])
        if matched:
            countrycd = matched
            parts = parts[:-1]
    if not countrycd:
        countrycd = _country_in_text(address)
    zipcode = re.sub(r"\s+", "", zip_hint or "")
    addr1 = ""
    addr2 = ""
    if parts and not re.search(r"\d", parts[-1]) and len(parts[-1]) <= 40:
        addr1 = parts[-1]
        parts = parts[:-1]
    if parts:
        postal = re.match(r"^(\d{3,10}(?:-\d{3,4})?)\s+(.+)$", parts[-1])
        if postal:
            if not zipcode:
                zipcode = postal.group(1)
            addr2 = postal.group(2).strip()
            parts = parts[:-1]
        elif not re.search(r"\d", parts[-1]):
            addr2 = parts[-1]
            parts = parts[:-1]
    addr3 = ", ".join(parts)
    if not addr3 and address and not (addr1 or addr2):
        addr3 = address.strip()
    return {
        "countrycd": countrycd,
        "zipcode": zipcode,
        "addr1": addr1,
        "addr2": addr2,
        "addr3": addr3,
    }


def _match_country(token: str) -> str:
    text = re.sub(r"\s+", " ", (token or "").strip())
    if not text:
        return ""
    folded = text.lower().rstrip(".")
    alias = _COUNTRY_ALIASES.get(folded) or _COUNTRY_ALIASES.get(text.lower())
    if alias:
        return alias
    if re.fullmatch(r"[A-Za-z]{2}", text):
        code = text.upper()
        if any(item["nationcd"] == code for item in FALLBACK_NATIONS) or code == "KR":
            return code
    for item in FALLBACK_NATIONS:
        if text.upper() == item["nationfn"].upper() or text == item["nationnm"] or text.upper() == item["nationcd"]:
            return item["nationcd"]
    return ""


def _country_in_text(text: str) -> str:
    raw = text or ""
    if not raw.strip():
        return ""
    best = ""
    best_len = 0
    for item in FALLBACK_NATIONS:
        for label in (item["nationnm"], item["nationfn"]):
            if label and label.lower() in raw.lower() and len(label) > best_len:
                best = item["nationcd"]
                best_len = len(label)
    for alias, code in _COUNTRY_ALIASES.items():
        if alias in raw.lower() and len(alias) > best_len:
            best = code
            best_len = len(alias)
    return best


def _missing_fields(address: dict[str, str], phone: str, items: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    if not address.get("countrycd"):
        missing.append("국가")
    if not phone:
        missing.append("연락처")
    missing.append("이메일")
    if not address.get("zipcode"):
        missing.append("우편번호")
    if not address.get("addr1"):
        missing.append("주/도")
    if not address.get("addr2"):
        missing.append("시/군")
    if not address.get("addr3"):
        missing.append("상세주소")
    missing.extend(["총중량(g)", "가로(cm)", "세로(cm)", "높이(cm)"])
    if not items:
        missing.append("품목")
    elif any(not item.get("unit_price_usd") for item in items):
        missing.append("단가 USD")
    if items and any(not item.get("name_en") for item in items):
        missing.append("HS 품목")
    if items and any(not item.get("hs_code") for item in items):
        missing.append("HS코드")
    if items and any(not item.get("origin_country") for item in items):
        missing.append("원산지")
    return missing
