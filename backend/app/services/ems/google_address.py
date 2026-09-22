"""Google Places 파싱·Address Validation. Infront google-places.ts 와 동일 계약."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

ADDRESS_VALIDATION_SUPPORTED = {
    "AR", "AT", "AU", "BE", "BG", "BR", "CA", "CH", "CL", "CO", "CZ", "DE", "DK",
    "EE", "ES", "FI", "FR", "GB", "HR", "HU", "IE", "IN", "IT", "JP", "LT", "LU",
    "LV", "MX", "MY", "NL", "NO", "NZ", "PL", "PR", "PT", "SE", "SG", "SI", "SK", "US",
}


def google_maps_api_key(*extra_paths: str) -> str:
    key = (os.getenv("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY") or "").replace("\r", "").replace("\n", "").strip()
    if key:
        return key
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "frontend", ".env.local"),
        os.path.join("c:\\Users\\one\\infront\\apps\\web", ".env.local"),
        *extra_paths,
    ]
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip().startswith("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY"):
                        raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                        return raw.replace("\\r", "").replace("\\n", "").replace("\r", "").replace("\n", "").strip()
        except OSError:
            continue
    return ""


def supports_address_validation(country_code: str) -> bool:
    return (country_code or "").upper() in ADDRESS_VALIDATION_SUPPORTED


def _comp(components: list[dict[str, Any]], type_name: str, *, short: bool = False) -> str:
    for item in components:
        if type_name in (item.get("types") or []):
            return str(item.get("short_name" if short else "long_name") or "")
    return ""


def parse_place_result(place: dict[str, Any], country_code: str) -> dict[str, str]:
    components = list(place.get("address_components") or [])
    street_number = _comp(components, "street_number")
    route = _comp(components, "route")
    sublocality2 = _comp(components, "sublocality_level_2")
    sublocality1 = _comp(components, "sublocality_level_1")
    locality = _comp(components, "locality")
    admin_area1 = _comp(components, "administrative_area_level_1")
    admin_area1_short = _comp(components, "administrative_area_level_1", short=True)
    postal_code = _comp(components, "postal_code")
    country = (country_code or "").upper()

    addr3 = addr2 = addr1 = ""
    if country == "JP":
        addr3 = "-".join(p for p in (sublocality2, street_number) if p) or " ".join(p for p in (route, street_number) if p) or sublocality1
        addr2 = sublocality1 or locality
        addr1 = admin_area1
    elif country in {"US", "CA", "AU", "GB", "NZ"}:
        addr3 = " ".join(p for p in (street_number, route) if p)
        addr2 = locality
        addr1 = admin_area1_short or admin_area1
    else:
        addr3 = " ".join(p for p in (street_number, route) if p) or sublocality1
        addr2 = sublocality1 or locality
        addr1 = admin_area1

    if not addr3:
        formatted = str(place.get("formatted_address") or "")
        addr3 = formatted.split(",")[0].strip() if formatted else ""
    return {"addr3": addr3, "addr2": addr2, "addr1": addr1, "zip": postal_code}


def _component_text(components: list[dict[str, Any]], type_name: str) -> str:
    for item in components:
        if item.get("componentType") != type_name:
            continue
        name = item.get("componentName") or {}
        if isinstance(name, dict):
            return str(name.get("text") or "").strip()
        return str(name or "").strip()
    return ""


def suggested_from_validation(data: dict[str, Any]) -> dict[str, str]:
    """Address Validation 응답에서 상세주소·시/군·주/도를 나눈다.

    영국처럼 postalAddress.administrativeArea 가 비면 addressComponents 의
    administrative_area_level_1(England)을 주/도로 쓴다.
    """
    result = (data or {}).get("result") or {}
    address = result.get("address") or {}
    postal = address.get("postalAddress") or {}
    components = list(address.get("addressComponents") or [])
    lines = [str(line).strip() for line in (postal.get("addressLines") or []) if str(line).strip()]
    admin = str(postal.get("administrativeArea") or "").strip() or _component_text(
        components, "administrative_area_level_1"
    )
    city = (
        str(postal.get("locality") or "").strip()
        or _component_text(components, "postal_town")
        or _component_text(components, "locality")
    )
    return {
        "suggestedAddr3": ", ".join(lines),
        "suggestedAddr2": city,
        "suggestedAddr1": admin,
        "suggestedZip": str(postal.get("postalCode") or "").strip(),
        "formattedAddress": str(address.get("formattedAddress") or "").strip(),
    }


def validate_address_with_google(
    api_key: str,
    addr: dict[str, str],
    *,
    timeout: float = 12,
) -> dict[str, Any] | None:
    lines = [addr.get("addr3") or "", addr.get("addr2") or "", addr.get("addr1") or "", addr.get("zip") or ""]
    address_lines = [line for line in lines if line.strip()]
    if not api_key or not address_lines:
        return None
    payload = json.dumps({
        "address": {
            "regionCode": addr.get("countryCode") or addr.get("country_code") or "",
            "addressLines": address_lines,
        }
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://addressvalidation.googleapis.com/v1:validateAddress?key={api_key}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "body": body}
    except Exception as exc:
        return {"ok": False, "status": 0, "body": str(exc)}

    result = (data or {}).get("result") or {}
    address = result.get("address") or {}
    if not address:
        return {"ok": False, "status": 200, "body": "empty address"}
    return {"ok": True, "status": 200, "suggested": suggested_from_validation(data), "raw": data}
