"""국제우편(EMS/K-Packet) 공개 배송조회.

우체국 화면의 배송 진행상황 표에서 마지막 처리현황을 읽는다.
화면 안내문과 스크립트 주석의 '배달완료' 글자는 상태로 쓰지 않는다.
"""

from __future__ import annotations

import os
import re

import httpx

from backend.app.services.ems.client import EmsApiError

EMS_TRACE_URL = "https://service.epost.go.kr/trace.RetrieveEmsRigiTraceList.comm"
_TRACKING_RE = re.compile(r"^[A-Z]{2}\d{9}[A-Z]{2}$")
_EVENT_AT_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}$")
_STATUS_RULES: tuple[tuple[str, str], ...] = (
    ("배달완료", "배달완료"),
    ("미배달", "미배달"),
    ("반송", "반송"),
    ("배달중", "배달중"),
    ("배달준비", "배달준비"),
    ("통관", "통관중"),
    ("세관", "통관중"),
    ("교환국", "운송중"),
    ("발송준비", "발송준비"),
    ("발송", "발송"),
    ("도착", "운송중"),
    ("접수", "접수"),
)


def normalize_ems_tracking_no(raw: str | None) -> str:
    return re.sub(r"\s+", "", (raw or "")).upper()


def canonicalize_ems_status(raw: str | None) -> str:
    text = re.sub(r"\s+", "", raw or "")
    for needle, label in _STATUS_RULES:
        if needle in text:
            return label
    cleaned = re.sub(r"\s+", " ", raw or "").strip()
    return cleaned[:40] or "운송중"


def parse_ems_trace_html(html: str | None) -> dict[str, str]:
    """마지막 처리일시 행의 처리현황을 현재 상태로 본다."""
    events: list[dict[str, str]] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html or "", flags=re.I | re.S):
        cells = _row_cells(row)
        if len(cells) < 2 or not _EVENT_AT_RE.match(cells[0]):
            continue
        status = cells[1].strip()
        if not status:
            continue
        events.append(
            {
                "at": cells[0],
                "status": status,
                "office": cells[2].strip() if len(cells) > 2 else "",
            }
        )
    if not events:
        return {"noRecord": "1"}
    last = events[-1]
    return {
        "treatStusCd": canonicalize_ems_status(last["status"]),
        "treatStusNm": last["status"],
        "eventAt": last["at"],
        "office": last["office"],
    }


def track_ems_regino(regino: str) -> dict[str, str]:
    tracking_no = normalize_ems_tracking_no(regino)
    if not _TRACKING_RE.fullmatch(tracking_no):
        raise EmsApiError("등기번호가 없어 국제우편 배송조회를 할 수 없습니다.")
    html = _fetch_trace_html(tracking_no)
    parsed = parse_ems_trace_html(html)
    parsed["regiNo"] = tracking_no
    return parsed


def _row_cells(row_html: str) -> list[str]:
    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.I | re.S)
    texts: list[str] = []
    for cell in cells:
        text = re.sub(r"<[^>]+>", " ", cell)
        text = text.replace("\xa0", " ").replace("&nbsp;", " ")
        texts.append(re.sub(r"\s+", " ", text).strip())
    return texts


def _fetch_trace_html(tracking_no: str) -> str:
    url = f"{EMS_TRACE_URL}?POST_CODE={tracking_no}&displayHeader=N"
    secret = (os.getenv("EPOST_RELAY_SECRET") or "").strip()
    bases: list[str] = []
    for key in ("VERCEL_APP_URL", "EPOST_RELAY_URL"):
        base = (os.getenv(key) or "").strip().rstrip("/")
        if base and base not in bases:
            bases.append(base)
    last_error: Exception | None = None
    if secret:
        for base in bases:
            try:
                return _fetch_via_relay(base, secret, url)
            except Exception as exc:
                last_error = exc
    try:
        return _fetch_direct(url)
    except Exception as exc:
        last_error = exc
    raise EmsApiError(f"국제우편 배송조회에 연결하지 못했습니다. ({last_error})")


def _fetch_via_relay(base: str, secret: str, url: str) -> str:
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        resp = client.post(
            f"{base}/api/epost-relay",
            headers={"x-relay-secret": secret},
            json={"method": "GET", "url": url, "form_body": ""},
        )
    if resp.status_code >= 400:
        raise EmsApiError(f"국제우편 배송조회 중계 오류(HTTP {resp.status_code})")
    return _decode_html(resp)


def _fetch_direct(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        resp = client.get(url, headers=headers)
    if resp.status_code >= 400:
        raise EmsApiError(f"국제우편 배송조회 HTTP {resp.status_code}")
    return _decode_html(resp)


def _decode_html(resp: httpx.Response) -> str:
    raw = resp.content
    detected = (resp.charset_encoding or "").lower().replace("-", "")
    if detected in ("utf8", "utf-8"):
        return raw.decode("utf-8", errors="replace")
    try:
        return raw.decode("euc-kr")
    except (UnicodeDecodeError, LookupError):
        return raw.decode("utf-8", errors="replace")
