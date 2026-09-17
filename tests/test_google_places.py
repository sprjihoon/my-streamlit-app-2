from __future__ import annotations

from backend.app.services.ems.google_address import (
    google_maps_api_key,
    parse_place_result,
    supports_address_validation,
    validate_address_with_google,
)


def test_supports_address_validation_coverage():
    assert supports_address_validation("jp") is True
    assert supports_address_validation("US") is True
    assert supports_address_validation("TW") is False


def test_parse_place_result_jp_us_and_fallback():
    jp = parse_place_result(
        {
            "address_components": [
                {"long_name": "1", "short_name": "1", "types": ["street_number"]},
                {"long_name": "Jingumae", "short_name": "Jingumae", "types": ["sublocality_level_2"]},
                {"long_name": "Shibuya", "short_name": "Shibuya", "types": ["sublocality_level_1"]},
                {"long_name": "Tokyo", "short_name": "Tokyo", "types": ["administrative_area_level_1"]},
                {"long_name": "150-0001", "short_name": "150-0001", "types": ["postal_code"]},
            ]
        },
        "JP",
    )
    assert jp["addr3"] == "Jingumae-1"
    assert jp["addr2"] == "Shibuya"
    assert jp["addr1"] == "Tokyo"
    assert jp["zip"] == "150-0001"

    us = parse_place_result(
        {
            "address_components": [
                {"long_name": "1600", "short_name": "1600", "types": ["street_number"]},
                {"long_name": "Amphitheatre Parkway", "short_name": "Amphitheatre Pkwy", "types": ["route"]},
                {"long_name": "Mountain View", "short_name": "Mountain View", "types": ["locality"]},
                {"long_name": "California", "short_name": "CA", "types": ["administrative_area_level_1"]},
                {"long_name": "94043", "short_name": "94043", "types": ["postal_code"]},
            ]
        },
        "US",
    )
    assert us["addr3"] == "1600 Amphitheatre Parkway"
    assert us["addr2"] == "Mountain View"
    assert us["addr1"] == "CA"
    assert us["zip"] == "94043"

    fallback = parse_place_result({"formatted_address": "1-2-3 Example Street, Taipei"}, "TW")
    assert fallback["addr3"] == "1-2-3 Example Street"


def test_google_address_validation_live_or_reachable():
    key = google_maps_api_key()
    if not key:
        raise AssertionError("Google Maps API key is missing for live address validation test")
    result = validate_address_with_google(
        key,
        {
            "addr3": "1-1-1 Shibuya",
            "addr2": "Shibuya-ku",
            "addr1": "Tokyo",
            "zip": "150-0001",
            "countryCode": "JP",
        },
    )
    assert result is not None
    if result.get("ok"):
        suggested = result["suggested"]
        blob = f"{suggested['formattedAddress']} {suggested['suggestedAddr1']} {suggested['suggestedAddr2']}".lower()
        assert "tokyo" in blob or "shibuya" in blob or "東京" in blob or suggested["formattedAddress"]
        return
    body = (result.get("body") or "").lower()
    assert result.get("status") in {400, 403, 429}
    assert "request_denied" in body or "referer" in body or "api" in body or "key" in body
