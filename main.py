# 📊 New-Cal 홈 (엔트리포인트)
import sys, pathlib

# ── 0) 패키지 경로 주입 ─────────────────────────────
ROOT      = pathlib.Path(__file__).resolve().parent      # …/new_cal
PARENTDIR = ROOT.parent                                  # Desktop
if str(PARENTDIR) not in sys.path:
    sys.path.insert(0, str(PARENTDIR))                   # new_cal import 가능

# ── 1) 일반 import ─────────────────────────────────
import streamlit as st
from datetime import date

# ── 2) 페이지 설정 ─────────────────────────────────
st.set_page_config(page_title="New-Cal 홈", page_icon="📊", layout="wide")
st.title("📊 New-Cal Dashboard / Landing Page")

st.write(
    """
    **환영합니다!**  
    왼쪽 사이드바에서 기능을 선택하세요.

    > Upload → Mapping → Unit Price → Invoice 순으로 업무를 진행합니다.
    """
)

# ── 3) 사이드바 네비게이션 ──────────────────────────
with st.sidebar:
    st.header("🔗 메뉴")
    st.page_link("pages/1_upload_manager.py", label="📤 업로드 매니저")
    # 아직 없는 페이지는 disabled=True
    st.page_link("pages/2_mapping_manager.py", label="🔗 매핑 매니저", disabled=True)
    #st.page_link("pages/3_unit_price_manager.py", label="💲 단가표 매니저", disabled=True)
    #st.page_link("pages/4_invoice_builder.py", label="🧾 청구서 빌더", disabled=True)

# ── 4) 간단 메트릭(예시) ─────────────────────────────
c1, c2, c3 = st.columns(3)
c1.metric("오늘 날짜", date.today().isoformat())
c2.metric("업로드된 파일", "—")
c3.metric("생성된 청구서", "—")

try:
    from migrate_to_turso import migrate_data
    
    st.warning("⚠️ 로컬 데이터를 클라우드로 이전할 때만 이 버튼을 누르세요. **단 한 번만 실행해야 합니다!**")
    if st.button("🚀 로컬 DB 데이터를 Turso 클라우드로 이전하기"):
        migrate_data()
    st.markdown("---")

except ImportError:
    # 마이그레이션 스크립트가 없으면 아무것도 표시하지 않음
    pass

# 기존 페이지 내용
st.image("assets/logo.png", width=200)
st.title(" 통합 정산 관리 시스템")
st.markdown("---")
st.info("좌측 메뉴에서 페이지를 선택하면 해당 기능 화면으로 이동합니다.")

try:
    from restore_mapping_data import restore_data
    
    st.warning("🚨 업체 매핑 데이터가 유실된 경우에만 아래 버튼을 누르세요.")
    if st.button("🔄 업체 매핑 데이터 복원하기"):
        with st.spinner("데이터를 복원하는 중입니다..."):
            restore_data()
        st.info("복원이 완료되었습니다. 이 메시지는 페이지 새로고침 후 사라집니다.")

except ImportError:
    st.info("복원 스크립트가 없습니다. 모든 데이터가 정상입니다.")

st.markdown("---")

# 나머지 메인 페이지 내용
st.header("메인 페이지")
st.write("왼쪽 메뉴에서 원하는 페이지를 선택하세요.")
