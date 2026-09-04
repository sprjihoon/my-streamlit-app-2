import pytest

from utils.utils_courier import add_courier_fee_by_zone


@pytest.mark.skip(reason="통합테스트: 운영 billing.db의 2025-06 팔로우미 실데이터 필요")
def test_followme_202506():
    items = []
    add_courier_fee_by_zone("팔로우미코스메틱", "2025-06-01", "2025-06-30", items_list=items)
    counts = {i["항목"]: i["수량"] for i in items}
    assert counts.get("택배요금 (극소)", 0) == 1379
    assert counts.get("택배요금 (중)", 0) == 1
