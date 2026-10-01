"""우체국에 보내는 HS는 검색으로 확인한 10자리만 쓴다."""
from __future__ import annotations

from backend.app.services.ems.epost_hs import epost_hs_table, known_epost_hs_codes, resolve_epost_hs
from backend.app.services.ems.fields import hs_code_for_epost
from backend.app.services.ems.item_categories import ITEM_CATEGORIES


def test_catalog_codes_resolve_to_verified_ten_digits():
    table = epost_hs_table()
    known = known_epost_hs_codes()
    checked = 0
    for cat in ITEM_CATEGORIES:
        raw = cat["hs_code"]
        if not raw:
            continue
        sent = hs_code_for_epost(raw)
        assert len(sent) == 10 and sent.isdigit()
        assert sent.startswith(raw)
        assert sent in table[raw]
        assert sent in known
        assert sent == resolve_epost_hs(raw)
        checked += 1
    assert checked >= 50


def test_rejected_six_digit_jewelry_uses_listed_code():
    assert "7117199000" in epost_hs_table()["711719"]
    assert hs_code_for_epost("711719") == "7117199000"
    assert hs_code_for_epost("7117190000") == "7117199000"
    assert hs_code_for_epost("7117199000") == "7117199000"


def test_documents_keep_book_code_and_parcel_codes_stay_ten_digits():
    assert hs_code_for_epost("490199") == "4901999000"
    assert hs_code_for_epost("610910", document=True) == "4901999000"
    assert hs_code_for_epost("", document=True) == "4901999000"
    sent = hs_code_for_epost("711719;610910")
    assert sent == "7117199000;6109109000"
    assert all(len(part) == 10 for part in sent.split(";"))


def test_mismatched_headings_use_the_product_code():
    expect = {
        "200599": "2005991000",
        "200980": "2005991000",
        "220299": "2202992000",
        "220290": "2202992000",
        "330510": "3305100000",
        "330511": "3305100000",
        "620140": "6201401010",
        "620111": "6201401010",
        "851713": "8517130000",
        "851712": "8517130000",
        "851762": "8517621010",
        "910211": "9102119010",
        "910210": "9102119010",
        "950300": "9503003919",
        "950399": "9503003919",
        "960200": "9602009090",
        "950340": "9602009090",
        "920290": "9202901000",
        "920599": "9202901000",
    }
    for raw, code in expect.items():
        assert hs_code_for_epost(raw) == code
        assert code in known_epost_hs_codes()


def test_unknown_code_still_uses_a_listed_ten_digit():
    sent = hs_code_for_epost("999999")
    assert len(sent) == 10
    assert sent in known_epost_hs_codes()
    assert hs_code_for_epost("610991") == hs_code_for_epost("610910")
