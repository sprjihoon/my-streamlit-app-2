"""우체국 계약소포 API. Infront lib/epost/client.ts 의 InsertOrder/GetResInfo/Cancel."""

from __future__ import annotations

import os
import random
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

from backend.app.services.epost.fields import (
    EPOST_PICKUP_DETAIL_MIN_LEN,
    build_epost_params,
    normalize_addr1,
    require_phone,
    resolve_cancel_req_ymd,
    resolve_office_ser,
    sanitize_insert_order_body,
    treat_status_from_tracking_text,
    treat_status_label,
)
from backend.app.services.epost.seed128 import seed128_encrypt

EPOST_BASE_URL = "https://ship.epost.go.kr"
EPOST_BASE_URLS = ("https://ship.epost.go.kr", "http://ship.epost.go.kr")
EPOST_USER_AGENT = "Apache-HttpClient/4.5.1 (Java/1.8.0_91)"

# Vercel Seoul 중계 URL (싱가포르 → 우체국 직접 연결 불가 대응)
# 예: https://tillion.io.kr  → /api/epost-relay 로 POST
EPOST_RELAY_URL: str = os.getenv("EPOST_RELAY_URL", "").strip().rstrip("/")
EPOST_RELAY_SECRET: str = os.getenv("EPOST_RELAY_SECRET", "").strip()
KST = ZoneInfo("Asia/Seoul")


class EpostError(RuntimeError):
    def __init__(self, message: str, maybe_booked: bool = False):
        super().__init__(message)
        self.maybe_booked = maybe_booked


def env_value(key: str) -> str:
    return (os.getenv(key) or "").strip().strip('"').strip("'")


def _friendly_epost_error(code: str, message: str) -> str:
    text = f"{code}: {message}".strip()
    blob = f"{code} {message}"
    if "custNo" in blob or "custno" in blob.lower() or "고객번호" in blob:
        if any(token in blob for token in ("ERR-111", "ERR-211", "누락", "없습니다")):
            return (
                "우체국이 접수 데이터(고객번호)를 읽지 못했습니다. "
                "오픈API신청결과의 소포신청 '보안키보기' 값을 Railway EPOST_SECURITY_KEY에 다시 넣어주세요. "
                f"({text})"
            )
    return f"EPost Error {text}"


def has_epost_credentials() -> bool:
    return bool(
        env_value("EPOST_API_KEY")
        and env_value("EPOST_SECURITY_KEY")
        and env_value("EPOST_CUSTOMER_ID")
        and env_value("EPOST_APPROVAL_NO")
    )


def parse_xml(xml: str, tag: str) -> str | None:
    cdata = re.search(rf"<{tag}>\s*<!\[CDATA\[(.*?)\]\]>\s*</{tag}>", xml, flags=re.S)
    if cdata:
        return cdata.group(1).strip()
    plain = re.search(rf"<{tag}>(.*?)</{tag}>", xml, flags=re.S)
    return plain.group(1).strip() if plain else None


def _plain_fields(plain_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for pair in plain_text.split("&"):
        idx = pair.find("=")
        if idx > 0:
            fields[pair[:idx]] = pair[idx + 1 :]
    return fields


def _validate_return_pickup_plain(plain_text: str) -> None:
    fields = _plain_fields(plain_text)
    rec_zip = (fields.get("recZip") or "").strip()
    if not re.fullmatch(r"\d{5}", rec_zip):
        raise EpostError(
            f'우체국 반품 수거 전송 오류: recZip="{rec_zip or "(비어 있음)"}" — 우편번호 5자리가 필요합니다.'
        )
    rec_addr1 = (fields.get("recAddr1") or "").strip()
    if len(rec_addr1) < 2:
        raise EpostError(
            f'우체국 반품 수거 전송 오류: recAddr1="{rec_addr1 or "(비어 있음)"}" — 도로명 주소가 없습니다.'
        )
    rec2 = (fields.get("recAddr2") or "").strip()
    if not rec2 or rec2 == "없음" or len(rec2) < EPOST_PICKUP_DETAIL_MIN_LEN:
        raise EpostError(
            f'우체국 반품 수거 전송 오류: recAddr2="{rec2 or "(비어 있음)"}" — 상세주소(동·호수·층)를 2글자 이상 입력해주세요.'
        )
    if "recMob" in fields:
        raise EpostError("우체국 반품 수거 전송 오류: recMob이 평문에 포함되어 있습니다.")
    rec_tel = (fields.get("recTel") or "").strip()
    if not rec_tel or not re.fullmatch(r"\d{9,12}", rec_tel):
        raise EpostError(
            f'우체국 반품 수거 전송 오류: recTel="{rec_tel or "(비어 있음)"}" — 수거 연락처를 숫자만 입력해주세요.'
        )
    for key, label in (("ordMob", "센터 연락처"), ("inqTelCn", "문의전화")):
        val = (fields.get(key) or "").strip()
        if val and not re.fullmatch(r"\d{9,12}", val):
            raise EpostError(f'우체국 반품 수거 전송 오류: {key}="{val}" — {label}는 숫자만 입력해주세요.')
    order_no = fields.get("orderNo") or ""
    if len(order_no.encode("utf-8")) > 50:
        raise EpostError("우체국 전송 오류: orderNo가 너무 깁니다.")


def _call_epost_via_relay(
    method: str,
    url: str,
    form_body: str,
    timeout: float,
) -> str:
    """Vercel Seoul 중계를 경유해 우체국 API를 호출한다."""
    import logging as _logging
    relay_endpoint = f"{EPOST_RELAY_URL}/api/epost-relay"
    try:
        with httpx.Client(timeout=timeout + 5, follow_redirects=True) as client:
            resp = client.post(
                relay_endpoint,
                json={"method": method, "url": url, "form_body": form_body},
                headers={"x-relay-secret": EPOST_RELAY_SECRET},
            )
        if resp.status_code == 401:
            raise EpostError("중계 인증 실패: EPOST_RELAY_SECRET을 확인하세요.")
        if resp.status_code >= 400:
            snippet = re.sub(r"\s+", " ", resp.text).strip()[:200]
            raise EpostError(f"우체국 중계 오류(HTTP {resp.status_code}): {snippet}")
        xml = resp.text
        _logging.getLogger("epost").info("[relay response] %s", xml[:500])
        return xml
    except EpostError:
        raise
    except httpx.TimeoutException as exc:
        raise EpostError(
            f"우체국 API 응답 시간 초과({int(timeout)}초). 접수목록에서 송장 생성 여부를 확인한 뒤 다시 시도해주세요.",
            maybe_booked=True,
        ) from exc
    except httpx.HTTPError as exc:
        raise EpostError(
            f"우체국 API 서버에 연결하지 못했습니다. ({exc})",
            maybe_booked=True,
        ) from exc


def call_epost(
    endpoint: str,
    params: dict[str, Any],
    test_yn: str = "N",
    *,
    timeout: float = 15.0,
    max_attempts: int = 2,
) -> str:
    api_key = env_value("EPOST_API_KEY")
    security_key = env_value("EPOST_SECURITY_KEY")
    if not api_key:
        raise EpostError("EPOST_API_KEY 환경변수가 설정되지 않았습니다.")
    if not security_key:
        raise EpostError("EPOST_SECURITY_KEY 환경변수가 설정되지 않았습니다.")

    plain_text = build_epost_params(params, endpoint)
    # InsertOrder와 GetResCancelCmd는 POST, 나머지(GetResInfo 등)는 GET
    is_post = "InsertOrder" in endpoint or "GetResCancelCmd" in endpoint
    is_insert = "InsertOrder" in endpoint
    if is_insert and str(params.get("reqType")) == "2":
        _validate_return_pickup_plain(plain_text)

    encrypted = seed128_encrypt(plain_text, security_key)
    headers = {
        "User-Agent": EPOST_USER_AGENT,
        "Connection": "keep-alive",
        "Host": "ship.epost.go.kr",
    }

    # ── Vercel Seoul 중계 경로 (EPOST_RELAY_URL 설정 시) ──────────────────
    if EPOST_RELAY_URL and EPOST_RELAY_SECRET:
        if is_post:
            body_dict: dict[str, str] = {"key": api_key, "regData": encrypted}
            if test_yn == "Y":
                body_dict["testYn"] = "Y"
            form_body = urlencode(body_dict)
            url = f"https://ship.epost.go.kr/{endpoint}"
            xml = _call_epost_via_relay("POST", url, form_body, timeout)
        else:
            query_dict: dict[str, str] = {"key": api_key, "regData": encrypted}
            if test_yn == "Y":
                query_dict["testYn"] = "Y"
            url = f"https://ship.epost.go.kr/{endpoint}?" + urlencode(query_dict)
            xml = _call_epost_via_relay("GET", url, "", timeout)
        if "<error>" in xml or "ERR-" in xml:
            code = parse_xml(xml, "error_code") or "UNKNOWN"
            msg = parse_xml(xml, "message") or xml[:200]
            raise EpostError(_friendly_epost_error(code, msg))
        return xml
    # ────────────────────────────────────────────────────────────────────────

    last_error: Exception | None = None
    attempts = max(1, int(max_attempts))
    timed_out = False
    for attempt in range(1, attempts + 1):
        for base in EPOST_BASE_URLS:
            try:
                if is_post:
                    body = {"key": api_key, "regData": encrypted}
                    if test_yn == "Y":
                        body["testYn"] = "Y"
                    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                        resp = client.post(
                            f"{base}/{endpoint}",
                            content=urlencode(body),
                            headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                        )
                else:
                    query = {"key": api_key, "regData": encrypted}
                    if test_yn == "Y":
                        query["testYn"] = "Y"
                    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                        resp = client.get(
                            f"{base}/{endpoint}",
                            params=query,
                            headers=headers,
                        )
                if resp.status_code >= 400:
                    snippet = re.sub(r"\s+", " ", resp.text).strip()[:200]
                    raise EpostError(f"우체국 API 오류(HTTP {resp.status_code}): {snippet}")
                xml = resp.text
                if "<error>" in xml or "ERR-" in xml:
                    code = parse_xml(xml, "error_code") or "UNKNOWN"
                    msg = parse_xml(xml, "message") or xml[:200]
                    raise EpostError(_friendly_epost_error(code, msg))
                return xml
            except EpostError:
                raise
            except httpx.TimeoutException as exc:
                timed_out = True
                last_error = exc
            except httpx.HTTPError as exc:
                last_error = exc
        if attempt < attempts:
            time.sleep(0.2)
    if timed_out:
        raise EpostError(
            f"우체국 API 응답 시간 초과({int(timeout)}초). 접수목록에서 송장 생성 여부를 확인한 뒤 다시 시도해주세요.",
            maybe_booked=True,
        )
    raise EpostError(
        f"우체국 API 서버({EPOST_BASE_URL})에 연결하지 못했습니다. ({last_error})",
        maybe_booked=True,
    )


def insert_order(params: dict[str, Any]) -> dict[str, str]:
    cust_no = (params.get("custNo") or env_value("EPOST_CUSTOMER_ID")).strip()
    appr_no = (params.get("apprNo") or env_value("EPOST_APPROVAL_NO")).strip()
    test_yn = "Y" if params.get("testYn") == "Y" else "N"
    weight = int(params.get("weight") or 2)
    volume = int(params.get("volume") or 60)
    body = sanitize_insert_order_body(
        {
            **params,
            "custNo": cust_no,
            "apprNo": appr_no,
            "officeSer": params.get("officeSer") or resolve_office_ser(),
            "weight": weight if weight > 0 else 2,
            "volume": volume if volume > 0 else 60,
            "printYn": params.get("printYn") or "Y",
            "microYn": "Y" if params.get("microYn") == "Y" else "N",
        }
    )
    if test_yn == "Y":
        body["testYn"] = "Y"
    else:
        body.pop("testYn", None)
    if not body.get("recZip") or len(str(body["recZip"])) != 5:
        raise EpostError("수취인 우편번호(recZip)가 없습니다.")
    if not body.get("recAddr1") or len(normalize_addr1(str(body["recAddr1"]))) < 2:
        raise EpostError("수취인 주소(recAddr1)가 없습니다.")
    if str(body.get("reqType") or "") == "2":
        rec_detail = str(body.get("recAddr2") or "").strip()
        if len(rec_detail) < EPOST_PICKUP_DETAIL_MIN_LEN or rec_detail == "없음":
            raise EpostError("반품인 상세주소(recAddr2)가 없습니다. 수거지 동·호수·층을 2글자 이상 입력해주세요.")
        require_phone(str(body.get("ordMob") or ""), "센터 연락처(ordMob)")
        require_phone(str(body.get("recTel") or body.get("recMob") or ""), "수거 연락처(recTel)")

    xml = call_epost("api.InsertOrder.jparcel", body, test_yn, timeout=8.0, max_attempts=1)
    result = {
        "reqNo": parse_xml(xml, "reqNo") or "",
        "resNo": parse_xml(xml, "resNo") or "",
        "regiNo": parse_xml(xml, "regiNo") or "",
        "regiPoNm": parse_xml(xml, "regiPoNm") or parse_xml(xml, "regipoNm") or "",
        "resDate": parse_xml(xml, "resDate") or "",
        "price": parse_xml(xml, "price") or "0",
        "vTelNo": parse_xml(xml, "vTelNo") or "",
    }
    if not result["regiNo"]:
        raise EpostError("우체국 API 응답에 운송장번호(regiNo)가 없습니다.")
    return result


def get_res_info(
    order_no: str,
    req_ymd: str,
    req_type: str = "2",
    cust_no: str | None = None,
    *,
    timeout: float = 12.0,
    max_attempts: int = 2,
) -> dict[str, str]:
    xml = call_epost(
        "api.GetResInfo.jparcel",
        {
            "custNo": (cust_no or env_value("EPOST_CUSTOMER_ID")).strip(),
            "reqType": req_type,
            "orderNo": order_no,
            "reqYmd": req_ymd,
        },
        timeout=timeout,
        max_attempts=max_attempts,
    )
    treat = parse_xml(xml, "treatStusCd") or "00"
    return {
        "reqNo": parse_xml(xml, "reqNo") or "",
        "resNo": parse_xml(xml, "resNo") or "",
        "regiNo": parse_xml(xml, "regiNo") or "",
        "regiPoNm": parse_xml(xml, "regiPoNm") or "",
        "resDate": parse_xml(xml, "resDate") or "",
        "price": parse_xml(xml, "price") or "0",
        "vTelNo": parse_xml(xml, "vTelNo") or "",
        "treatStusCd": treat,
        "treatStusNm": treat_status_label(treat),
    }


EPOST_TRACE_URL = "https://service.epost.go.kr/trace.RetrieveDomRigiTraceList.comm"
TRACKER_DELIVERY_URL = "https://apis.tracker.delivery/graphql"
TRACKER_STATUS_TO_TREAT = {
    # tracker.delivery GraphQL API (kr.epost) → 내부 처리상태코드
    "PICKUP_PENDING":   "05",  # 운송장출력 또는 수거 대기 → 수거준비
    "PICKING_UP":       "05",  # 수거 진행 중 → 수거준비
    "AT_PICKUP":        "01",  # 집하완료 → 수거완료
    "IN_TRANSIT":       "02",  # 간선 이동 → 이동중
    "OUT_FOR_DELIVERY": "07",  # 배달 출발 → 배달중
    "DELIVERED":        "03",  # 배달완료
    "ATTEMPT_FAILED":   "07",  # 배달 미완료 재시도 → 배달중으로 표시
}


def lookup_req_ymds(*values: str | None) -> list[str]:
    ymds: list[str] = []
    for raw in values:
        ymd = re.sub(r"\D", "", raw or "")[:8]
        if len(ymd) == 8 and ymd not in ymds:
            ymds.append(ymd)
    return ymds


def get_res_info_with_dates(order_no: str, req_ymds: list[str]) -> dict[str, str]:
    last_error: Exception | None = None
    for req_ymd in req_ymds:
        try:
            info = get_res_info(order_no, req_ymd)
            if info.get("regiNo") or info.get("treatStusCd") not in {"", "00"}:
                return info
            if info:
                return info
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise EpostError("우체국 접수조회(GetResInfo)에 사용할 날짜가 없습니다.")


def _track_via_tracker_delivery(regi_no: str) -> dict[str, str] | None:
    client_id = env_value("TRACKER_DELIVERY_CLIENT_ID")
    client_secret = env_value("TRACKER_DELIVERY_CLIENT_SECRET")
    if not (client_id and client_secret):
        return None
    query = """
      query TrackParcel($carrierId: ID!, $trackingNumber: String!) {
        track(carrierId: $carrierId, trackingNumber: $trackingNumber) {
          lastEvent { status { code name } description }
        }
      }
    """
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            TRACKER_DELIVERY_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"TRACKQL-API-KEY {client_id}:{client_secret}",
            },
            json={
                "query": query,
                "variables": {"carrierId": "kr.epost", "trackingNumber": regi_no},
            },
        )
    if resp.status_code >= 400:
        return None
    payload = resp.json()
    last = ((payload.get("data") or {}).get("track") or {}).get("lastEvent") or {}
    code = ((last.get("status") or {}).get("code") or "").strip()
    treat = TRACKER_STATUS_TO_TREAT.get(code)
    if not treat:
        return None
    return {"treatStusCd": treat, "treatStusNm": treat_status_label(treat), "regiNo": regi_no}


def _track_via_epost_trace(regi_no: str) -> dict[str, str] | None:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        resp = client.get(
            EPOST_TRACE_URL,
            params={"sid1": regi_no, "displayHeader": "N"},
            headers=headers,
        )
    if resp.status_code >= 400:
        return None
    html = resp.text
    treat = treat_status_from_tracking_text(html)
    if not treat:
        return None
    return {"treatStusCd": treat, "treatStusNm": treat_status_label(treat), "regiNo": regi_no}


def track_regi_no(regi_no: str) -> dict[str, str]:
    tracking_no = re.sub(r"\D", "", regi_no or "")
    if len(tracking_no) < 10:
        raise EpostError("송장번호가 없어 종적조회를 할 수 없습니다.")
    tracked = _track_via_tracker_delivery(tracking_no) or _track_via_epost_trace(tracking_no)
    if not tracked:
        raise EpostError(f"송장 {tracking_no} 조회 결과가 없습니다.")
    return tracked


def cancel_order(
    *,
    req_no: str,
    res_no: str,
    regi_no: str,
    req_ymd: str | None = None,
    insert_snapshot: dict[str, Any] | None = None,
    req_type: str = "2",
    pay_type: str = "2",
) -> dict[str, str]:
    if not (req_no and res_no and regi_no):
        raise EpostError(
            f"우체국 취소 필수값 누락 (reqNo={req_no or '(없음)'}, resNo={res_no or '(없음)'}, regiNo={regi_no or '(없음)'})"
        )
    payload = {
        **(insert_snapshot or {}),
        "custNo": env_value("EPOST_CUSTOMER_ID"),
        "apprNo": env_value("EPOST_APPROVAL_NO"),
        "payType": pay_type,
        "reqType": req_type,
        "reqNo": req_no,
        "resNo": res_no,
        "regiNo": regi_no,
        "reqYmd": (req_ymd or "").replace("-", "")[:8] or resolve_cancel_req_ymd(),
        "delYn": "Y",
    }
    xml = call_epost("api.GetResCancelCmd.jparcel", payload)
    canceled = (parse_xml(xml, "canceledYn") or parse_xml(xml, "canceledyn") or "N").upper()
    reason = parse_xml(xml, "notCancelReason") or parse_xml(xml, "notcancelreason") or ""
    if canceled not in {"Y", "D"}:
        raise EpostError(f"우체국 취소 미완료(canceledYn={canceled})" + (f": {reason}" if reason else ""))
    return {"reqNo": parse_xml(xml, "reqNo") or "", "resNo": parse_xml(xml, "resNo") or "", "canceledYn": canceled}


def mock_insert_order() -> dict[str, str]:
    now = datetime.now(KST)
    ymd = now.strftime("%Y%m%d")
    suffix = f"{int(time.time() * 1000)}{random.randint(0, 999)}"[-7:]
    return {
        "reqNo": f"MOCK-REQ-{int(time.time() * 1000)}",
        "resNo": f"MOCK-RES-{int(time.time() * 1000)}",
        "regiNo": f"7000000{suffix.zfill(7)}",
        "regiPoNm": "테스트우체국",
        "resDate": f"{ymd}120000",
        "price": "5000",
        "vTelNo": "",
    }


def is_ambiguous_insert_error(err: Exception) -> bool:
    msg = str(err)
    return any(token in msg for token in ("연결하지 못했습니다", "fetch failed", "응답 시간 초과"))
