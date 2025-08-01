import pandas as pd
import streamlit as st
from common import get_connection
from typing import List

"""
pages/3_mapped_suppliers.py – 매핑된 공급처(서플라이어) 리스트 관리
────────────────────────────────────────────────────────
* vendors & aliases 테이블을 읽어 매핑 현황을 확인·수정·삭제
* vendors 테이블에 vendor 컬럼이 없을 경우 버전 호환 방식으로 자동 생성
* FLAG_COLS 는 2_mapping_manager.py 와 동일 플래그 사용
* 별칭(alias) 편집 UI 를 multiselect 로 개선
"""

# ─────────────────────────────────────
# 0. 스키마 보강: vendor 컬럼 보장 (SQLite 구버전 호환)
# ─────────────────────────────────────
with get_connection() as con:
    cols = [c[1] for c in con.execute("PRAGMA table_info(vendors);")]
    if "vendor" not in cols:
        con.execute("ALTER TABLE vendors ADD COLUMN vendor TEXT;")
        # name → vendor 복사 (name 이 있을 때만)
        if "name" in cols:
            con.execute("UPDATE vendors SET vendor = name WHERE vendor IS NULL OR vendor = '';")
        # 고유 인덱스
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_vendor ON vendors(vendor);")

# ─────────────────────────────────────
# 1. 상수 정의
# ─────────────────────────────────────
SKU_OPTS  = ["≤100", "≤300", "≤500", "≤1,000", "≤2,000", ">2,000"]
FLAG_COLS = [
    "barcode_f", "custbox_f", "void_f", "pp_bag_f",
    "video_out_f", "video_ret_f",
]
FILE_TYPES = [
    "inbound_slip", "shipping_stats", "kpost_in", "kpost_ret", "work_log",
]
SRC_TABLES = [
    ("inbound_slip","공급처",    "inbound_slip"),
    ("shipping_stats","공급처",  "shipping_stats"),
    ("kpost_in","발송인명",      "kpost_in"),
    ("kpost_ret","수취인명",     "kpost_ret"),
    ("work_log","업체명",        "work_log"),
]


# ─────────────────────────────────────
# 2. Streamlit 초기화
# ─────────────────────────────────────
try:
    st.set_page_config(page_title="매핑 리스트", layout="wide")
except Exception:
    pass
st.title("📋 공급처 매핑 리스트")

# ─────────────────────────────────────
# 3. 데이터 로드 (캐시 15초)
# ─────────────────────────────────────
@st.cache_data(ttl=15)
def load_all():
    with get_connection() as con:
        df_v = pd.read_sql("SELECT * FROM vendors ORDER BY vendor", con)
        df_a = pd.read_sql("SELECT * FROM aliases", con)
    for col in FLAG_COLS:
        if col not in df_v.columns:
            df_v[col] = "NO"
    return df_v, df_a

@st.cache_data(ttl=15)
def get_all_aliases_from_source():
    """원본 테이블에서 모든 alias 목록을 가져옵니다."""
    all_aliases = {}
    with get_connection() as con:
        for tbl, col, ft in SRC_TABLES:
            try:
                # 테이블 및 컬럼 존재 여부 확인
                tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", con)
                if tbl not in tables['name'].values:
                    all_aliases[ft] = []
                    continue
                
                cols_in_tbl = [c[1] for c in con.execute(f"PRAGMA table_info({tbl});")]
                if col not in cols_in_tbl:
                    all_aliases[ft] = []
                    continue

                df = pd.read_sql(f"SELECT DISTINCT [{col}] as alias FROM {tbl}", con)
                aliases = [str(x).strip() for x in df.alias.dropna() if str(x).strip()]
                all_aliases[ft] = sorted(list(set(aliases)))
            except Exception:
                 all_aliases[ft] = []
    return all_aliases

df_vendors, df_alias = load_all()
if df_vendors.empty:
    st.info("등록된 공급처가 없습니다. 매핑 매니저에서 먼저 추가하세요.")
    st.stop()
    
all_source_aliases = get_all_aliases_from_source()

# ─────────────────────────────────────
# 4. 검색 & 메인 리스트
# ─────────────────────────────────────
kw = st.text_input("검색어(공급처/별칭)").strip().lower()
if kw:
    matched = df_alias[df_alias.alias.str.lower().str.contains(kw)].vendor.unique()
    df_disp = df_vendors[
        df_vendors.vendor.str.lower().str.contains(kw) | df_vendors.vendor.isin(matched)
    ]
else:
    df_disp = df_vendors.copy()

main_cols = [
    "vendor", "rate_type", "sku_group",
    "barcode_f", "custbox_f", "void_f", "pp_bag_f",
    "video_out_f", "video_ret_f",
]

st.dataframe(df_disp[main_cols], use_container_width=True, height=400)

# ─────────────────────────────────────
# 5. 상세 편집 영역
# ─────────────────────────────────────
sel_vendor = st.selectbox("✏️ 수정/삭제할 공급처", [""] + df_vendors.vendor.tolist())
if not sel_vendor:
    st.stop()

row_v = df_vendors[df_vendors.vendor == sel_vendor].iloc[0]
df_alias_v = df_alias[df_alias.vendor == sel_vendor]

# ─────────────────────────────────────
# 5-1. 별칭 편집 UI 개선
# ─────────────────────────────────────
st.subheader("🏷️ 별칭 관리")

def create_alias_editor(file_type: str, display_name: str):
    """사용자 친화적인 별칭 편집기를 생성합니다."""
    current_aliases = df_alias_v[df_alias_v.file_type == file_type].alias.tolist()
    available_aliases = all_source_aliases.get(file_type, [])
    
    # 현재 설정된 별칭들을 제거한 사용 가능한 별칭 목록
    unassigned_aliases = [a for a in available_aliases if a not in current_aliases]
    
    st.write(f"**{display_name}**")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.write("✅ **현재 설정된 별칭:**")
        if current_aliases:
            # 현재 별칭들을 제거할 수 있는 체크박스로 표시
            aliases_to_remove = []
            for alias in current_aliases:
                if st.checkbox(f"🗑️ {alias}", key=f"remove_{file_type}_{alias}"):
                    aliases_to_remove.append(alias)
            # 제거할 별칭들을 제외한 나머지
            remaining_aliases = [a for a in current_aliases if a not in aliases_to_remove]
        else:
            st.info("설정된 별칭이 없습니다.")
            remaining_aliases = []
    
    with col2:
        st.write("➕ **추가 가능한 별칭:**")
        if unassigned_aliases:
            # 추가할 별칭들을 선택할 수 있는 체크박스
            aliases_to_add = []
            for alias in unassigned_aliases:
                if st.checkbox(f"➕ {alias}", key=f"add_{file_type}_{alias}"):
                    aliases_to_add.append(alias)
            # 최종 별칭 목록
            final_aliases = remaining_aliases + aliases_to_add
        else:
            st.info("추가할 수 있는 별칭이 없습니다.")
            final_aliases = remaining_aliases
    
    st.divider()
    return final_aliases

# 각 파일 타입별로 별칭 편집기 생성
inb  = create_alias_editor("inbound_slip", "📦 입고전표")
ship = create_alias_editor("shipping_stats", "🚚 배송통계")
kpin = create_alias_editor("kpost_in", "📮 우체국접수")
ktrt = create_alias_editor("kpost_ret", "📫 우체국반품")
wl   = create_alias_editor("work_log", "📝 작업일지")

l, r = st.columns(2)
rate_type   = l.selectbox("요금타입", ["A", "STD"], index=["A", "STD"].index(row_v.rate_type or "A"))
sku_group   = r.selectbox("SKU 구간", SKU_OPTS, index=SKU_OPTS.index(row_v.sku_group or SKU_OPTS[0]))
barcode_f   = l.selectbox("바코드 부착", ["YES", "NO"], index=["YES", "NO"].index(row_v.barcode_f or "NO"))
custbox_f   = l.selectbox("박스", ["YES", "NO"], index=["YES", "NO"].index(row_v.custbox_f or "NO"))
void_f      = r.selectbox("완충재", ["YES", "NO"], index=["YES", "NO"].index(row_v.void_f or "NO"))
pp_bag_f    = r.selectbox("PP 봉투", ["YES", "NO"], index=["YES", "NO"].index(row_v.pp_bag_f or "NO"))
video_out_f = l.selectbox("출고영상촬영", ["YES", "NO"], index=["YES", "NO"].index(row_v.video_out_f or "NO"))
video_ret_f = l.selectbox("반품영상촬영", ["YES", "NO"], index=["YES", "NO"].index(row_v.video_ret_f or "NO"))

save_col, del_col = st.columns(2)

# ─────────────────────────────────────
# 6. 저장
# ─────────────────────────────────────
if save_col.button("💾 변경 사항 저장"):
    try:
        with get_connection() as con:
            con.execute(
                """UPDATE vendors SET rate_type=?, sku_group=?, barcode_f=?, custbox_f=?, void_f=?, pp_bag_f=?, video_out_f=?, video_ret_f=? WHERE vendor=?""",
                (
                    rate_type, sku_group, barcode_f, custbox_f,
                    void_f, pp_bag_f, video_out_f, video_ret_f, sel_vendor,
                ),
            )
            con.execute("DELETE FROM aliases WHERE vendor=?", (sel_vendor,))
            def _ins(ft: str, lst: List[str]):
                for a in lst:
                    con.execute("INSERT INTO aliases VALUES (?,?,?)", (a, sel_vendor, ft))
            _ins("inbound_slip", inb)
            _ins("shipping_stats", ship)
            _ins("kpost_in", kpin)
            _ins("kpost_ret", ktrt)
            _ins("work_log", wl)
        st.cache_data.clear()
        st.success("저장 완료!")
        st.rerun()
    except Exception as e:
        st.error(f"❌ 업데이트 실패: {e}")

# ─────────────────────────────────────
# 7. 삭제
# ─────────────────────────────────────
if del_col.button("🗑 공급처 삭제", type="secondary"):
    try:
        if st.radio("정말 삭제할까요?", ["취소", "삭제"], horizontal=True, index=0) == "삭제":
            with get_connection() as con:
                con.execute("DELETE FROM vendors WHERE vendor=?", (sel_vendor,))
                con.execute("DELETE FROM aliases WHERE vendor=?", (sel_vendor,))
            st.cache_data.clear()
            st.success("삭제 완료")
            st.rerun()
    except Exception as e:
        st.error(f"❌ 삭제 실패: {e}")
