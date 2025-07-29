import streamlit as st
from datetime import date

st.set_page_config(
    page_title="Main",
    page_icon="🏠",
    layout="wide",
)

c1, c2, c3 = st.columns(3)
c1.metric("오늘 날짜", date.today().strftime("%Y-%m-%d"))
c2.metric("선택된 공급처", "—")
c3.metric("생성된 청구서", "—")

st.image("assets/logo.png", width=200)
st.title(" 통합 정산 관리 시스템")
st.markdown("---")
st.info("좌측 메뉴에서 페이지를 선택하면 해당 기능 화면으로 이동합니다.")
