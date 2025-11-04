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
    "barcode_f", "custbox_f", "void_f", "pp_bag_f", "mailer_f",
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
st.title("📋 거래처 매핑 리스트")

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
# 검색 및 필터
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    kw = st.text_input("🔍 검색어 (거래처/별칭)", placeholder="검색...").strip().lower()

with col2:
    filter_mode = st.selectbox("📊 상태", ["활성만", "비활성만", "전체"], index=0)

with col3:
    # 통계 메트릭
    total_vendors = len(df_vendors)
    active_cnt = len(df_vendors[df_vendors.get('active', 'YES') == 'YES'])
    inactive_cnt = len(df_vendors[df_vendors.get('active', 'YES') == 'NO'])
    
    if filter_mode == "활성만":
        st.metric("표시 중", f"{active_cnt}개", delta="활성", delta_color="normal")
    elif filter_mode == "비활성만":
        st.metric("표시 중", f"{inactive_cnt}개", delta="비활성", delta_color="off")
    else:
        st.metric("표시 중", f"{total_vendors}개", delta="전체", delta_color="normal")

# 검색 필터
if kw:
    matched = df_alias[df_alias.alias.str.lower().str.contains(kw)].vendor.unique()
    df_disp = df_vendors[
        df_vendors.vendor.str.lower().str.contains(kw) | df_vendors.vendor.isin(matched)
    ]
else:
    df_disp = df_vendors.copy()

# 활성 상태 필터 적용
if filter_mode == "활성만":
    df_disp = df_disp[df_disp.get('active', 'YES') == 'YES']
elif filter_mode == "비활성만":
    df_disp = df_disp[df_disp.get('active', 'YES') == 'NO']

st.markdown("---")

main_cols = [
    "vendor", "active", "rate_type", "sku_group",
    "barcode_f", "custbox_f", "void_f", "pp_bag_f", "mailer_f",
    "video_out_f", "video_ret_f",
]

st.dataframe(df_disp[main_cols], width='stretch', height=400)

# ─────────────────────────────────────
# 4-bis. 미매칭 alias 통계
# ─────────────────────────────────────
st.markdown("---")
st.subheader("📊 미매칭 Alias 통계")

def get_unmatched_stats():
    """파일별 미매칭 alias 개수 반환"""
    parts = []
    with get_connection() as con:
        for tbl, col, ft in SRC_TABLES:
            # 테이블 존재 확인
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)).fetchone():
                continue
            # 컬럼 존재 확인
            cols = [c[1] for c in con.execute(f"PRAGMA table_info({tbl});")]
            if col not in cols:
                continue
            
            parts.append(
                f"SELECT DISTINCT {col} AS alias, '{ft}' AS file_type FROM {tbl} "
                f"WHERE {col} IS NOT NULL AND TRIM({col}) != ''"
            )
        
        if not parts:
            return pd.DataFrame(columns=["file_type", "미매칭_건수"])
        
        # 전체 alias 가져오기
        all_aliases_query = " UNION ".join(parts)
        df_all = pd.read_sql(all_aliases_query, con)
        
        # aliases 테이블의 매핑된 alias 가져오기
        df_mapped = pd.read_sql("SELECT alias, file_type FROM aliases", con)
        
        # 미매칭 찾기
        df_merged = df_all.merge(
            df_mapped,
            on=['alias', 'file_type'],
            how='left',
            indicator=True
        )
        
        df_unmatched = df_merged[df_merged['_merge'] == 'left_only']
        
        # 파일별 집계
        if df_unmatched.empty:
            return pd.DataFrame(columns=["file_type", "미매칭_건수"])
        
        stats = df_unmatched.groupby('file_type').size().reset_index(name='미매칭_건수')
        return stats

try:
    df_unmatch_stats = get_unmatched_stats()
    
    if df_unmatch_stats.empty:
        st.success("✅ 모든 데이터가 정상 매핑되었습니다!")
    else:
        # 파일 타입 한글명 매핑
        file_type_names = {
            "inbound_slip": "입고전표",
            "shipping_stats": "배송통계",
            "kpost_in": "우체국접수",
            "kpost_ret": "우체국반품",
            "work_log": "작업일지"
        }
        
        df_unmatch_stats['파일명'] = df_unmatch_stats['file_type'].map(file_type_names)
        
        col1, col2 = st.columns([2, 3])
        
        with col1:
            st.metric("총 미매칭 건수", f"{df_unmatch_stats['미매칭_건수'].sum():,}건")
        
        with col2:
            st.dataframe(
                df_unmatch_stats[['파일명', '미매칭_건수']].rename(columns={'미매칭_건수': '건수'}),
                width='stretch',
                hide_index=True
            )
        
        st.info("💡 **매핑 관리** 페이지에서 미매칭 alias를 추가할 수 있습니다.")
except Exception as e:
    st.error(f"미매칭 통계 오류: {e}")

st.markdown("---")

# ─────────────────────────────────────
# 5. 상세 편집 영역
# ─────────────────────────────────────
sel_vendor = st.selectbox("✏️ 수정/삭제할 거래처", [""] + df_vendors.vendor.tolist())
if not sel_vendor:
    st.stop()

row_v = df_vendors[df_vendors.vendor == sel_vendor].iloc[0]
df_alias_v = df_alias[df_alias.vendor == sel_vendor]

def get_options_and_defaults(file_type: str) -> (List[str], List[str]):
    """multiselect 에 필요한 옵션과 기본값을 반환합니다.
    
    현재 공급처에 매핑된 별칭 + 아직 매핑되지 않은 별칭만 선택 가능합니다.
    다른 공급처에 이미 매핑된 별칭들은 제외됩니다.
    """
    # 현재 공급처에 매핑된 별칭들
    default_aliases = df_alias_v[df_alias_v.file_type == file_type].alias.tolist()
    
    # 원본 데이터의 모든 별칭들
    source_aliases = all_source_aliases.get(file_type, [])
    
    # 다른 공급처에 이미 매핑된 별칭들 제외
    with get_connection() as con:
        try:
            other_mapped = pd.read_sql(
                "SELECT DISTINCT alias FROM aliases WHERE file_type = ? AND vendor != ?", 
                con, params=[file_type, sel_vendor]
            )
            other_mapped_list = other_mapped.alias.tolist() if not other_mapped.empty else []
        except Exception:
            other_mapped_list = []
    
    # 사용 가능한 옵션 = 현재 매핑된 별칭들 + (원본 별칭들 - 다른 공급처 매핑된 별칭들)
    available_source = [alias for alias in source_aliases if alias not in other_mapped_list]
    options = sorted(list(set(default_aliases + available_source)))
    
    return options, default_aliases

# 파일 타입별로 multiselect 생성 (매핑 매니저와 동일한 스타일)
c1, c2 = st.columns(2)
c3, c4 = st.columns(2) 
c5, _ = st.columns(2)

inb_opts, inb_defs = get_options_and_defaults("inbound_slip")
ship_opts, ship_defs = get_options_and_defaults("shipping_stats")
kpin_opts, kpin_defs = get_options_and_defaults("kpost_in")
ktrt_opts, ktrt_defs = get_options_and_defaults("kpost_ret")
wl_opts, wl_defs = get_options_and_defaults("work_log")

inb  = c1.multiselect("입고전표 별칭", inb_opts, default=inb_defs)
ship = c2.multiselect("배송통계 별칭", ship_opts, default=ship_defs)
kpin = c3.multiselect("우체국접수 별칭", kpin_opts, default=kpin_defs)
ktrt = c4.multiselect("우체국반품 별칭", ktrt_opts, default=ktrt_defs)
wl   = c5.multiselect("작업일지 별칭", wl_opts, default=wl_defs)

st.divider()

l, r = st.columns(2)
active      = l.selectbox("🟢 활성 상태", ["YES", "NO"], index=["YES", "NO"].index(row_v.get("active") or "YES"), help="계약 종료 시 NO로 설정")
rate_type   = l.selectbox("요금타입", ["A", "STD"], index=["A", "STD"].index(row_v.rate_type or "A"))
sku_group   = r.selectbox("SKU 구간", SKU_OPTS, index=SKU_OPTS.index(row_v.sku_group or SKU_OPTS[0]))
barcode_f   = l.selectbox("바코드 부착", ["YES", "NO"], index=["YES", "NO"].index(row_v.barcode_f or "NO"))
custbox_f   = l.selectbox("박스", ["YES", "NO"], index=["YES", "NO"].index(row_v.custbox_f or "NO"))
void_f      = r.selectbox("완충재", ["YES", "NO"], index=["YES", "NO"].index(row_v.void_f or "NO"))
pp_bag_f    = r.selectbox("PP 봉투", ["YES", "NO"], index=["YES", "NO"].index(row_v.pp_bag_f or "NO"))
mailer_f    = r.selectbox("📦 택배 봉투 (극소/소/중)", ["YES", "NO"], index=["YES", "NO"].index(row_v.get("mailer_f") or "NO"))
video_out_f = l.selectbox("출고영상촬영", ["YES", "NO"], index=["YES", "NO"].index(row_v.video_out_f or "NO"))
video_ret_f = l.selectbox("반품영상촬영", ["YES", "NO"], index=["YES", "NO"].index(row_v.video_ret_f or "NO"))

save_col, del_col = st.columns(2)

# ─────────────────────────────────────
# 6. 저장
# ─────────────────────────────────────
if save_col.button("💾 변경 사항 저장"):
    # 저장하기 전 선택된 값들 확인
    st.write("🔍 **저장할 데이터 확인:**")
    st.write(f"- 입고전표: {inb}")
    st.write(f"- 배송통계: {ship}")  
    st.write(f"- 우체국접수: {kpin}")
    st.write(f"- 우체국반품: {ktrt}")
    st.write(f"- 작업일지: {wl}")
    
    try:
        with get_connection() as con:
            con.execute(
                """UPDATE vendors SET active=?, rate_type=?, sku_group=?, barcode_f=?, custbox_f=?, void_f=?, pp_bag_f=?, mailer_f=?, video_out_f=?, video_ret_f=? WHERE vendor=?""",
                (
                    active, rate_type, sku_group, barcode_f, custbox_f,
                    void_f, pp_bag_f, mailer_f, video_out_f, video_ret_f, sel_vendor,
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
            
            # ✅ 중요: 트랜잭션 커밋
            con.commit()
            
        # 저장 후 실제 데이터 확인
        with get_connection() as check_con:
            saved_aliases = check_con.execute(
                "SELECT file_type, COUNT(*) as cnt FROM aliases WHERE vendor=? GROUP BY file_type", 
                (sel_vendor,)
            ).fetchall()
            
            alias_counts = {row[0]: row[1] for row in saved_aliases}
            
        st.cache_data.clear()
        st.success("✅ 저장 완료!")
        
        # 저장된 별칭 개수 표시
        st.info(f"""
        📊 **저장된 별칭 개수:**
        - 입고전표: {alias_counts.get('inbound_slip', 0)}개
        - 배송통계: {alias_counts.get('shipping_stats', 0)}개  
        - 우체국접수: {alias_counts.get('kpost_in', 0)}개
        - 우체국반품: {alias_counts.get('kpost_ret', 0)}개
        - 작업일지: {alias_counts.get('work_log', 0)}개
        """)
        
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
