import streamlit as st

from utils.utils_courier import add_courier_fee_by_zone


def test_followme_202506():
    # 초기화
    st.session_state["items"] = []

    # 팔로우미코스메틱(예시) 데이터가 DB에 있어야 테스트 통과
    add_courier_fee_by_zone("팔로우미코스메틱", "2025-06-01", "2025-06-30")
    counts = {i["항목"]: i["수량"] for i in st.session_state["items"]}

    assert counts.get("택배요금 (극소)", 0) == 1379
    assert counts.get("택배요금 (중)", 0) == 1 