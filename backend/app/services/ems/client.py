"""EMS / K-Packet 국제발송 OpenAPI 클라이언트.

Infront apps/admin/lib/ems/client.ts 와 동일 계약.
https://eship.epost.go.kr
"""

from __future__ import annotations

import os
import random
import re
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.app.services.ems.dimension_limits import (
    validate_shipping_dimensions,
    validate_weight,
)
from backend.app.services.ems.fields import build_ems_params, env_clean
from backend.app.services.epost.seed128 import seed128_encrypt

EMS_BASE = "https://eship.epost.go.kr"
EMS_USER_AGENT = "Apache-HttpClient/4.5.1 (Java/1.8.0_91)"
EPOST_RELAY_URL = (os.getenv("EPOST_RELAY_URL") or "").strip().rstrip("/")
EPOST_RELAY_SECRET = (os.getenv("EPOST_RELAY_SECRET") or "").strip()


class EmsApiError(RuntimeError):
    pass


def _key() -> str:
    return env_clean("EMS_API_KEY")


def _sec() -> str:
    return env_clean("EMS_SECURITY_KEY")


def _cust() -> str:
    return env_clean("EMS_CUSTOMER_NO")


def _appr() -> str:
    return env_clean("EMS_APPROVAL_NO")


def has_ems_credentials() -> bool:
    return bool(_key() and _sec() and _cust() and _appr())


def _strip_cdata(raw: str) -> str:
    m = re.match(r"^<!\[CDATA\[([\s\S]*?)\]\]>$", raw)
    return m.group(1).strip() if m else raw


def parse_xml(xml: str, tag: str) -> str | None:
    cdata = re.search(rf"<{tag}>\s*<!\[CDATA\[(.*?)\]\]>\s*</{tag}>", xml, flags=re.S | re.I)
    if cdata:
        return cdata.group(1).strip()
    plain = re.search(rf"<{tag}>(.*?)</{tag}>", xml, flags=re.S | re.I)
    if not plain:
        return None
    return _strip_cdata(plain.group(1).strip())


def parse_all(xml: str, tag: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(rf"<{tag}>([\s\S]*?)</{tag}>", xml, flags=re.I):
        out.append(_strip_cdata(m.group(1).strip()))
    return out


def _check_error(xml: str) -> None:
    trimmed = xml.lstrip()
    if trimmed.startswith("<!") or trimmed.lower().startswith("<html"):
        raise EmsApiError("해당 국가 또는 서비스는 지원되지 않습니다.")
    if "<error>" in xml or "ERR-" in xml:
        code = parse_xml(xml, "error_code") or parse_xml(xml, "resultcd") or "ERR"
        msg = parse_xml(xml, "message") or parse_xml(xml, "resultmsg") or xml[:200]
        raise EmsApiError(f"{code}: {msg}")


def _call_via_relay(method: str, url: str, form_body: str, timeout: float) -> str:
    if not EPOST_RELAY_URL or not EPOST_RELAY_SECRET:
        raise EmsApiError("우체국 EMS 중계(EPOST_RELAY_URL)가 설정되지 않았습니다.")
    relay_endpoint = f"{EPOST_RELAY_URL}/api/epost-relay"
    try:
        with httpx.Client(timeout=timeout + 5, follow_redirects=True) as client:
            resp = client.post(
                relay_endpoint,
                json={"method": method, "url": url, "form_body": form_body},
                headers={"x-relay-secret": EPOST_RELAY_SECRET},
            )
        if resp.status_code == 401:
            raise EmsApiError("중계 인증 실패: EPOST_RELAY_SECRET을 확인하세요.")
        if resp.status_code >= 400:
            snippet = re.sub(r"\s+", " ", resp.text).strip()[:200]
            raise EmsApiError(f"우체국 EMS 중계 오류(HTTP {resp.status_code}): {snippet}")
        xml = resp.text
        _check_error(xml)
        return xml
    except EmsApiError:
        raise
    except httpx.TimeoutException as exc:
        raise EmsApiError("우체국 EMS 서버 응답 시간 초과. 잠시 후 다시 시도하세요.") from exc
    except httpx.HTTPError as exc:
        raise EmsApiError(f"우체국 EMS 서버에 연결할 수 없습니다. ({exc})") from exc


def _direct_get(url: str, timeout: float) -> str:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": EMS_USER_AGENT})
    if resp.status_code >= 400:
        raise EmsApiError(f"EMS HTTP {resp.status_code}")
    xml = resp.text
    _check_error(xml)
    return xml


def _direct_post(url: str, form_body: str, timeout: float) -> str:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.post(
            url,
            content=form_body,
            headers={
                "User-Agent": EMS_USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    if resp.status_code >= 400:
        raise EmsApiError(f"EMS HTTP {resp.status_code}")
    xml = resp.text
    _check_error(xml)
    return xml


def _get_query(endpoint: str, params: dict[str, str], timeout: float = 10.0) -> str:
    if not _key():
        raise EmsApiError("EMS_API_KEY 환경변수가 설정되지 않았습니다.")
    query = {"regkey": _key(), **params}
    url = f"{EMS_BASE}/{endpoint}?" + urlencode(query)
    if EPOST_RELAY_URL and EPOST_RELAY_SECRET:
        return _call_via_relay("GET", url, "", timeout)
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            return _direct_get(url, timeout)
        except EmsApiError as exc:
            last_err = exc
            if "연결" in str(exc) and attempt == 0:
                time.sleep(1.5)
                continue
            raise
    raise EmsApiError(str(last_err) if last_err else "우체국 EMS 조회 실패")


def _post_encrypted(endpoint: str, params: dict[str, Any], timeout: float = 10.0) -> str:
    sec = _sec()
    if not sec:
        raise EmsApiError("EMS_SECURITY_KEY 환경변수가 설정되지 않았습니다.")
    if not _key():
        raise EmsApiError("EMS_API_KEY 환경변수가 설정되지 않았습니다.")
    plain = build_ems_params(params)
    encrypted = seed128_encrypt(plain, sec)
    form_body = urlencode({"key": _key(), "regData": encrypted})
    url = f"{EMS_BASE}/{endpoint}"
    if EPOST_RELAY_URL and EPOST_RELAY_SECRET:
        return _call_via_relay("POST", url, form_body, timeout)
    return _direct_post(url, form_body, timeout)


def get_shipping_quote(
    premiumcd: str,
    em_ee: str,
    countrycd: str,
    totweight: int,
    *,
    boxlength: int | None = None,
    boxwidth: int | None = None,
    boxheight: int | None = None,
) -> dict[str, int]:
    weight_err = validate_weight(premiumcd, em_ee, totweight)
    if weight_err:
        raise EmsApiError(weight_err)
    if boxlength and boxwidth and boxheight:
        dim_err = validate_shipping_dimensions(
            premiumcd, em_ee, countrycd, boxlength, boxwidth, boxheight
        )
        if dim_err:
            raise EmsApiError(dim_err)
    params: dict[str, str] = {
        "premiumcd": premiumcd,
        "em_ee": em_ee,
        "countrycd": countrycd,
        "totweight": str(totweight),
        "boyn": "N",
        "boprc": "0",
    }
    if boxlength:
        params["boxlength"] = str(boxlength)
    if boxwidth:
        params["boxwidth"] = str(boxwidth)
    if boxheight:
        params["boxheight"] = str(boxheight)
    apprno = _appr()
    if apprno:
        params["apprno"] = apprno
    xml = _get_query("api.EmsTotProcCmd.ems", params)
    fee = parse_xml(xml, "emsTotProc")
    if not fee:
        raise EmsApiError("해당 국가 또는 서비스는 지원되지 않습니다.")
    return {"totalFee": int(fee)}


def get_available_nations(premiumcd: str) -> list[dict[str, str]]:
    xml = _get_query("api.RetrieveNationListRequest.ems", {"premiumcd": premiumcd})
    cds = parse_all(xml, "nationcd")
    nms = parse_all(xml, "nationnm")
    fns = parse_all(xml, "nationfn")
    return [
        {
            "nationcd": cd,
            "nationnm": nms[i] if i < len(nms) else "",
            "nationfn": fns[i] if i < len(fns) else "",
            "premiumcd": premiumcd,
        }
        for i, cd in enumerate(cds)
    ]


def apply_ems(params: dict[str, Any]) -> dict[str, str]:
    custno = str(params.get("custno") or _cust())
    apprno = str(params.get("apprno") or _appr())
    if not custno:
        raise EmsApiError("EMS_CUSTOMER_NO 환경변수가 설정되지 않았습니다.")
    if not apprno:
        raise EmsApiError("EMS_APPROVAL_NO 환경변수가 설정되지 않았습니다.")
    em_ee = str(params.get("em_ee") or "")
    if em_ee != "ee":
        dim_err = validate_shipping_dimensions(
            str(params.get("premiumcd") or ""),
            em_ee,
            str(params.get("countrycd") or ""),
            int(params.get("boxlength") or 0),
            int(params.get("boxwidth") or 0),
            int(params.get("boxheight") or 0),
        )
        if dim_err:
            raise EmsApiError(dim_err)
    body = {**params, "custno": custno, "apprno": apprno}
    xml = _post_encrypted("api.EmsApplyInsertReceiveTempCmdNew.ems", body)
    result = {
        "receiveseq": parse_xml(xml, "receiveseq") or "",
        "prerecevprc": parse_xml(xml, "prerecevprc") or "0",
        "regino": parse_xml(xml, "regino") or "",
        "reqno": parse_xml(xml, "reqno") or "",
        "treatporegipocd": parse_xml(xml, "treatporegipocd") or "",
        "treatporegipoengnm": parse_xml(xml, "treatporegipoengnm") or "",
        "orderno": parse_xml(xml, "orderno") or str(params.get("orderno") or ""),
    }
    if not result["regino"]:
        raise EmsApiError("우체국 EMS 응답에 등기번호(regino)가 없습니다.")
    return result


def mock_apply_ems(premiumcd: str, em_ee: str, countrycd: str) -> dict[str, str]:
    prefix = "FX" if premiumcd == "32" else "LK" if em_ee == "rl" else "EG"
    stamp = str(int(time.time() * 1000))
    return {
        "receiveseq": f"S{stamp}",
        "prerecevprc": "36500",
        "regino": f"{prefix}{random.randint(0, 999_999_999):09d}KR",
        "reqno": stamp,
        "treatporegipocd": "10186",
        "treatporegipoengnm": "SEOUL GWANJIN",
        "orderno": f"TIL-{stamp}",
        "countrycd": countrycd,
    }


def cancel_ems(reqno: str, regino: str) -> dict[str, str]:
    xml = _post_encrypted(
        "api.EmsApplyCancel.ems",
        {
            "custno": _cust(),
            "apprno": _appr(),
            "reqno": reqno,
            "regino": regino,
            "cancelyn": "Y",
        },
    )
    return {
        "canceledyn": parse_xml(xml, "canceledyn") or "N",
        "notcancelreason": parse_xml(xml, "notcancelreason") or "",
    }


def mock_quote_fee(totweight: int, premiumcd: str) -> int:
    base = 18000 if premiumcd == "14" else 28000 if premiumcd == "31" else 42000
    extra = max(0, (totweight - 500) // 500) * 2500
    return base + extra
