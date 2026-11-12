"""중국 우편번호 권역과 성/직할시 일치 검사."""

from fastapi import HTTPException

from backend.app.services.ems.china_address import check_china_address, provinces, review_china_address
from tests.test_overseas_shipping import _req, _seed_user
from backend.app.api.overseas_shipping import preview_overseas, validate_china_address
from backend.app.api.overseas_shipping import ChinaAddressCheckRequest


def test_each_postal_zone_matches_its_province():
    for item in provinces():
        for prefix in item.prefixes:
            result = check_china_address(addr1=item.en, addr2="City", zipcode=f"{prefix}0000")
            assert result["ok"], (item.en, prefix, result)
            assert result["province"] == item.en


def test_chinese_and_korean_province_names_match_zip():
    guangdong = check_china_address(addr1="广东省", addr2="深圳市", zipcode="518000")
    assert guangdong["ok"] is True
    assert guangdong["province"] == "Guangdong"
    beijing = check_china_address(addr1="베이징", addr2="Chaoyang", zipcode="100020")
    assert beijing["ok"] is True
    assert beijing["province"] == "Beijing"
    guangxi = check_china_address(
        addr1="Guangxi Zhuang Autonomous Region", addr2="Nanning", zipcode="530000"
    )
    assert guangxi["ok"] is True


def test_shanxi_and_shaanxi_follow_the_zip():
    shanxi = check_china_address(addr1="산시", addr2="Taiyuan", zipcode="030000")
    assert shanxi["ok"] is True
    assert shanxi["province"] == "Shanxi"
    shaanxi = check_china_address(addr1="산시", addr2="Xi'an", zipcode="710000")
    assert shaanxi["ok"] is True
    assert shaanxi["province"] == "Shaanxi"
    wrong = check_china_address(addr1="산시", addr2="Chaoyang", zipcode="100000")
    assert wrong["ok"] is False
    assert wrong["suggested_addr1"] == "Beijing"


def test_mismatch_suggests_province_from_zip():
    result = check_china_address(addr1="Beijing", addr2="Shenzhen", zipcode="518000")
    assert result["ok"] is False
    assert result["suggested_addr1"] == "Guangdong"
    assert "Guangdong" in str(result["message"])
    spaced = check_china_address(addr1="北京", addr2="朝阳", zipcode="５１８０００")
    assert spaced["ok"] is False
    assert spaced["zipcode"] == "518000"


def test_rejects_bad_zip_unknown_zone_and_empty_city():
    short = check_china_address(addr1="Guangdong", addr2="Shenzhen", zipcode="51800")
    assert short["ok"] is False
    assert short["suggested_addr1"] == ""
    unknown = check_china_address(addr1="Guangdong", addr2="Shenzhen", zipcode="090000")
    assert unknown["ok"] is False
    empty_city = check_china_address(addr1="Guangdong", addr2="  ", zipcode="518000")
    assert empty_city["ok"] is False
    assert "시/구" in str(empty_city["message"])
    tibet = check_china_address(addr1="Tibet", addr2="Nyingchi", zipcode="860000")
    assert tibet["ok"] is True


def test_preview_blocks_mismatched_china_address(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    try:
        preview_overseas(
            _req(
                countrycd="CN",
                receivezipcode="518000",
                receiveaddr1="Beijing",
                receiveaddr2="Shenzhen",
                receiveaddr3="Nanshan 1",
                receivetelno="8613800138000",
            ),
            token,
        )
        raise AssertionError("mismatched province should be rejected")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Guangdong" in str(exc.detail)


def test_preview_rewrites_matching_chinese_province(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    body = preview_overseas(
        _req(
            countrycd="CN",
            receivezipcode="518 000",
            receiveaddr1="广东省",
            receiveaddr2="深圳市",
            receiveaddr3="南山区 1",
            receivetelno="8613800138000",
        ),
        token,
    )
    preview = body["preview"]
    assert preview["recipient_zip"] == "518000"
    assert preview["recipient_addr"].startswith("Guangdong ")
    assert "广" not in preview["recipient_addr"]
    labels = {row["label"]: row for row in preview["text_corrections"]}
    assert labels["주/도"]["after"] == "Guangdong"
    assert labels["우편번호"]["after"] == "518000"


def test_review_suggests_english_building_address():
    def fake(**kwargs):
        return {
            "precision": "rooftop",
            "province": "Guangdong",
            "city": "Shenzhen",
            "district": "Nanshan",
            "street": "15 Keyuan Road",
            "zipcode": "518057",
        }

    result = review_china_address(
        addr1="广东省",
        addr2="深圳市",
        addr3="科苑路15号",
        zipcode="518057",
        geocoder=fake,
    )
    assert result["ok"] is False
    assert result["suggested_addr1"] == "Guangdong"
    assert result["suggested_addr2"] == "Shenzhen"
    assert result["suggested_addr3"] == "15 Keyuan Road, Nanshan"
    assert result["zipcode"] == "518057"


def test_review_keeps_matching_english_street():
    def fake(**kwargs):
        return {
            "precision": "rooftop",
            "province": "Shanghai",
            "city": "Shanghai",
            "district": "Pudong",
            "street": "Shi Ji Da Dao",
            "zipcode": "200120",
        }

    result = review_china_address(
        addr1="Shanghai",
        addr2="Pudong",
        addr3="Century Avenue 100",
        zipcode="200120",
        geocoder=fake,
    )
    assert result["ok"] is True
    assert result["suggested_addr3"] == ""
    assert "건물 위치까지 확인" in str(result["message"])


def test_review_does_not_call_area_match_a_building():
    def fake(**kwargs):
        return {
            "precision": "area",
            "province": "Guangdong",
            "city": "Shenzhen",
            "district": "Nanshan",
            "street": "",
            "zipcode": "518057",
        }

    result = review_china_address(
        addr1="Guangdong",
        addr2="Shenzhen",
        addr3="Nowhere Road 1",
        zipcode="518057",
        geocoder=fake,
    )
    assert result["ok"] is True
    assert "건물 번호는 확인되지 않았습니다" in str(result["message"])
    assert result["suggested_addr3"] == ""


def test_validate_china_address_route(isolated_runtime, monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.ems.china_address.geocode_china",
        lambda **kwargs: {
            "precision": "rooftop",
            "province": "Shanghai",
            "city": "Shanghai",
            "district": "Pudong",
            "street": "Shi Ji Da Dao",
            "zipcode": "200120",
        },
    )
    token = _seed_user(isolated_runtime["db"])
    body = validate_china_address(
        ChinaAddressCheckRequest(
            receiveaddr1="Shanghai",
            receiveaddr2="Pudong",
            receiveaddr3="Century Ave 1",
            receivezipcode="200120",
        ),
        token,
    )
    assert body["ok"] is True
    assert body["province"] == "Shanghai"
