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
    sanitize_insert_order_body,
)
from backend.app.services.epost.seed128 import seed128_encrypt

EPOST_BASE_URL = "https://ship.epost.go.kr"
EPOST_USER_AGENT = "Apache-HttpClient/4.5.1 (Java/1.8.0_91)"
KST = ZoneInfo("Asia/Seoul")


class EpostError(RuntimeError):
    def __init__(self, message: str, maybe_booked: bool = False):
        super().__init__(message)
        self.maybe_booked = maybe_booked


def env_value(key: str) -> str:
    return (os.getenv(key) or "").strip()


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


def call_epost(endpoint: str, params: dict[str, Any], test_yn: str = "N") -> str:
    api_key = env_value("EPOST_API_KEY")
    security_key = env_value("EPOST_SECURITY_KEY")
    if not api_key:
        raise EpostError("EPOST_API_KEY 환경변수가 설정되지 않았습니다.")
    if not security_key:
        raise EpostError("EPOST_SECURITY_KEY 환경변수가 설정되지 않았습니다.")

    plain_text = build_epost_params(params, endpoint)
    is_insert = "InsertOrder" in endpoint
    if is_insert and str(params.get("reqType")) == "2":
        _validate_return_pickup_plain(plain_text)

    encrypted = seed128_encrypt(plain_text, security_key)
    headers = {"User-Agent": EPOST_USER_AGENT}
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            if is_insert:
                body = {"key": api_key, "regData": encrypted}
                if test_yn == "Y":
                    body["testYn"] = "Y"
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(
                        f"{EPOST_BASE_URL}/{endpoint}",
                        content=urlencode(body),
                        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                    )
            else:
                query = {"key": api_key, "regData": encrypted}
                if test_yn == "Y":
                    query["testYn"] = "Y"
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(
                        f"{EPOST_BASE_URL}/{endpoint}",
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
                raise EpostError(f"EPost Error {code}: {msg}")
            return xml
        except EpostError:
            raise
        except httpx.TimeoutException as exc:
            last_error = exc
            if attempt >= 3:
                raise EpostError("우체국 API 응답 시간 초과(30초). 잠시 후 다시 시도해주세요.", maybe_booked=True)
            time.sleep(attempt)
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt >= 3:
                raise EpostError(
                    f"우체국 API 서버({EPOST_BASE_URL})에 연결하지 못했습니다. ({exc})",
                    maybe_booked=True,
                )
            time.sleep(attempt)
    raise EpostError(str(last_error or "우체국 API 호출 실패"), maybe_booked=True)


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
            "officeSer": params.get("officeSer") or env_value("EPOST_OFFICE_SER") or "260940699",
            "weight": weight if weight > 0 else 2,
            "volume": volume if volume > 0 else 60,
            "printYn": params.get("printYn") or "Y",
            "microYn": "Y" if params.get("microYn") == "Y" else "N",
        }
    )
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

    xml = call_epost("api.InsertOrder.jparcel", body, test_yn)
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


def get_res_info(order_no: str, req_ymd: str, req_type: str = "2", cust_no: str | None = None) -> dict[str, str]:
    xml = call_epost(
        "api.GetResInfo.jparcel",
        {
            "custNo": (cust_no or env_value("EPOST_CUSTOMER_ID")).strip(),
            "reqType": req_type,
            "orderNo": order_no,
            "reqYmd": req_ymd,
        },
    )
    treat = parse_xml(xml, "treatStusCd") or "00"
    names = {"00": "신청접수", "01": "집하완료", "02": "수거중", "03": "배달완료"}
    return {
        "reqNo": parse_xml(xml, "reqNo") or "",
        "resNo": parse_xml(xml, "resNo") or "",
        "regiNo": parse_xml(xml, "regiNo") or "",
        "regiPoNm": parse_xml(xml, "regiPoNm") or "",
        "resDate": parse_xml(xml, "resDate") or "",
        "price": parse_xml(xml, "price") or "0",
        "vTelNo": parse_xml(xml, "vTelNo") or "",
        "treatStusCd": treat,
        "treatStusNm": names.get(treat, treat),
    }


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
