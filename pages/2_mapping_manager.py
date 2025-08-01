import pandas as pd
import streamlit as st
from typing import List
from common import get_connection

"""
pages/2_mapping_manager.py – 공급처 매핑 매니저 (vendors / aliases)
──────────────────────────────────────────────────────────────────
* 신규 공급처 + 파일별 별칭 매핑
* 플래그 컬럼(YES/NO): barcode_f, custbox_f, void_f, pp_bag_f,
  video_out_f, video_ret_f
* vendors.name 컬럼을 화면용, vendors.vendor 컬럼을 PK 로 통일
* 미매칭 alias 검사 + 캐시 재생성
"""

# ─────────────────────────────────────
# 0. 상수
# ─────────────────────────────────────
SKU_OPTS  = ["≤100","≤300","≤500","≤1,000","≤2,000",">2,000"]
FLAG_COLS = ["barcode_f","custbox_f","void_f","pp_bag_f","video_out_f","video_ret_f"]

# ─────────────────────────────────────
# 1. Streamlit 설정
# ─────────────────────────────────────
try:
    st.set_page_config(page_title="업체 매핑 관리", layout="wide")
except Exception:
    pass

# 저장 완료 후 안내 메시지 표시
if st.session_state.get('save_completed', False):
    st.success("✅ 이전에 저장이 완료되었습니다!")
    st.info("📋 좌측 사이드바에서 '📋 공급처 매핑 리스트' 페이지로 이동하여 확인해주세요.")
    # 상태 초기화
    st.session_state.save_completed = False

st.title("🔗 공급처 매핑 관리 (vendors / aliases)")

# ─────────────────────────────────────
# 2. 유틸
# ─────────────────────────────────────
def ensure_column(tbl:str, col:str, coltype:str="TEXT") -> None:
    """없으면 ALTER TABLE ADD COLUMN"""
    with get_connection() as con:
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({tbl});")]
        if col not in cols:
            con.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {coltype};")

# ─────────────────────────────────────
# 3. vendors·aliases 테이블 + 컬럼 보강
# ─────────────────────────────────────
with get_connection() as con:
    # vendors
    con.execute("""
        CREATE TABLE IF NOT EXISTS vendors(
            vendor     TEXT PRIMARY KEY,
            name       TEXT,
            rate_type  TEXT,
            sku_group  TEXT
        )""")
    for base_col in ("name","rate_type","sku_group"):
        ensure_column("vendors", base_col)
    for col in FLAG_COLS:
        ensure_column("vendors", col)

    # aliases
    con.execute("""
        CREATE TABLE IF NOT EXISTS aliases(
            alias     TEXT,
            vendor    TEXT,
            file_type TEXT,
            PRIMARY KEY(alias, file_type)
        )""")

# ─────────────────────────────────────
# 3-b. 레거시 -> vendors 동기화
# ─────────────────────────────────────
def sync_vendors_from_aliases():
    with get_connection() as con:
        missing = con.execute("""
            SELECT DISTINCT vendor FROM aliases
             WHERE vendor NOT IN (SELECT vendor FROM vendors)
               AND vendor IS NOT NULL AND vendor <> '' """).fetchall()
        for (vend,) in missing:
            con.execute("INSERT OR IGNORE INTO vendors(vendor,name) VALUES(?,?)",(vend,vend))
        con.execute("""UPDATE vendors SET vendor=name
                         WHERE (vendor IS NULL OR vendor='') AND name NOT NULL AND name<>'';""")
sync_vendors_from_aliases()

# ─────────────────────────────────────
# 4. 원본 테이블 스켈레톤
# ─────────────────────────────────────
SRC_TABLES = [
    ("inbound_slip","공급처",    "inbound_slip"),
    ("shipping_stats","공급처",  "shipping_stats"),
    ("kpost_in","발송인명",      "kpost_in"),
    ("kpost_ret","수취인명",     "kpost_ret"),
    ("work_log","업체명",        "work_log"),
]
for tbl,col,_ in SRC_TABLES:
    with get_connection() as con:
        con.execute(f"CREATE TABLE IF NOT EXISTS {tbl}([{col}] TEXT);")

# ─────────────────────────────────────
# 5. 캐시 재생성·미매칭 확인
# ─────────────────────────────────────
def refresh_alias_vendor_cache():
    with get_connection() as con:
        con.executescript("""
            DROP TABLE IF EXISTS alias_vendor_cache;
            CREATE TABLE alias_vendor_cache AS
            SELECT alias, file_type, vendor FROM aliases;
        """)

def find_unmatched_aliases() -> pd.DataFrame:
    refresh_alias_vendor_cache()
    parts=[]
    with get_connection() as con:
        for tbl,col,ft in SRC_TABLES:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)).fetchone():
                continue
            cols=[c[1] for c in con.execute(f"PRAGMA table_info({tbl});")]
            if col not in cols: continue
            parts.append(
                f"SELECT DISTINCT {col} AS alias, '{ft}' AS file_type FROM {tbl} "
                f"LEFT JOIN alias_vendor_cache c ON {col}=c.alias AND c.file_type='{ft}' "
                "WHERE c.alias IS NULL"
            )
        if not parts: return pd.DataFrame(columns=["alias","file_type"])
        return pd.read_sql(" UNION ALL ".join(parts)+" ORDER BY file_type, alias", con)

# ─────────────────────────────────────
# 6. 캐시 로드 (옵션 목록)
# ─────────────────────────────────────
@st.cache_data(ttl=15)
def load_alias_cache():
    with get_connection() as con:
        try:
            return pd.read_sql("SELECT alias,file_type FROM alias_vendor_cache", con)
        except Exception:
            return pd.DataFrame(columns=["alias","file_type"])

refresh_alias_vendor_cache()  # ★ 새 업로드 반영
st.cache_data.clear()
a_cache = load_alias_cache()

def uniq(tbl: str, col: str, ft: str) -> List[str]:
    """Return distinct values from given table/column that are not already in alias cache.

    If the source table or column is missing, show a warning instead of raising,
    so the Streamlit app continues to run.
    """
    try:
        with get_connection() as con:
            df = pd.read_sql(f"SELECT DISTINCT [{col}] AS v FROM {tbl}", con)
    except Exception as e:
        # Gracefully degrade when schema is incomplete on server
        st.warning(f"{ft} 원본({tbl}.{col}) 읽기 실패 → {e}")
        return []

    df = df[~df.v.isin(a_cache[a_cache.file_type == ft].alias)]
    return sorted(x for x in df.v.dropna().astype(str).str.strip() if x)

opt = {ft: uniq(tbl,col,ft) for tbl,col,ft in SRC_TABLES}

# ─────────────────────────────────────
# 7. 신규 업체 등록 폼
# ─────────────────────────────────────
st.subheader("🆕 신규 공급처 등록")
vendor_pk = st.text_input("공급처명 (PK)", help="DB에 저장될 고유 키 (수정불가)")
name      = st.text_input("공급처명 (표준)")

c1,c2 = st.columns(2); c3,c4 = st.columns(2); c5,_ = st.columns(2)
alias_inb  = c1.multiselect("입고전표 별칭",     opt["inbound_slip"])
alias_ship = c2.multiselect("배송통계 별칭",     opt["shipping_stats"])
alias_kpin = c3.multiselect("우체국접수 별칭",   opt["kpost_in"])
alias_kprt = c4.multiselect("우체국반품 별칭",   opt["kpost_ret"])
alias_wl   = c5.multiselect("작업일지 별칭",     opt["work_log"])

st.divider()
l,r = st.columns(2)
rate_type   = l.selectbox("요금타입", ["A","STD"])
barcode_f   = l.selectbox("바코드 부착", ["YES","NO"])
custbox_f   = l.selectbox("박스", ["YES","NO"])
void_f      = r.selectbox("완충재", ["YES","NO"])
pp_bag_f    = r.selectbox("PP 봉투", ["YES","NO"])
sku_group   = r.selectbox("대표 SKU 구간", SKU_OPTS)
video_out_f = l.selectbox("출고영상촬영", ["YES","NO"])
video_ret_f = l.selectbox("반품영상촬영", ["YES","NO"])

# ─────────────────────────────────────
# 8. 저장
# ─────────────────────────────────────
if st.button("💾 공급처 저장/업데이트"):
    vendor = vendor_pk.strip()
    if not vendor:
        st.warning("⚠️ 공급처명(PK)를 입력하세요.")
        st.stop()
    if not name.strip():
        st.warning("⚠️ 공급처명(표준)을 입력하세요.")
        st.stop()

    try:
        with get_connection() as con:
            # 존재 여부 체크
            existing = con.execute("SELECT 1 FROM vendors WHERE vendor=?", (vendor,)).fetchone()
            
            if existing:
                # 업데이트
                con.execute("""
                    UPDATE vendors SET 
                        name=?, rate_type=?, sku_group=?,
                        barcode_f=?, custbox_f=?, void_f=?, pp_bag_f=?,
                        video_out_f=?, video_ret_f=?
                    WHERE vendor=?
                """, (name.strip(), rate_type, sku_group,
                      barcode_f, custbox_f, void_f, pp_bag_f,
                      video_out_f, video_ret_f, vendor))
                action = "업데이트"
            else:
                # 새로 삽입
                con.execute("""
                    INSERT INTO vendors(
                        vendor,name,rate_type,sku_group,
                        barcode_f,custbox_f,void_f,pp_bag_f,
                        video_out_f,video_ret_f
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """, (vendor, name.strip(), rate_type, sku_group,
                      barcode_f, custbox_f, void_f, pp_bag_f,
                      video_out_f, video_ret_f))
                action = "신규 등록"
            
            # 별칭 저장
            con.execute("DELETE FROM aliases WHERE vendor=?", (vendor,))
            def _ins(ft,lst): 
                for a in lst:
                    con.execute("INSERT INTO aliases VALUES(?,?,?)",(a,vendor,ft))
            _ins("inbound_slip",alias_inb)
            _ins("shipping_stats",alias_ship)
            _ins("kpost_in",alias_kpin)
            _ins("kpost_ret",alias_kprt)
            _ins("work_log",alias_wl)
            
            # ✅ 중요: 트랜잭션 커밋
            con.commit()

        # 저장 완료 상태 설정
        st.session_state.save_completed = True
        
        refresh_alias_vendor_cache()
        st.cache_data.clear()
        st.success("✅ 저장 완료!")
        
        # 저장된 데이터 확인해서 보여주기
        with get_connection() as check_con:
            vendor_check = check_con.execute("SELECT * FROM vendors WHERE vendor=?", (vendor,)).fetchone()
            alias_check = check_con.execute("SELECT COUNT(*) FROM aliases WHERE vendor=?", (vendor,)).fetchone()[0]
        
        if vendor_check:
            st.success(f"✅ 공급처 '{vendor}' {action} 완료! (별칭 {alias_check}개)")
            st.info("📋 좌측 사이드바에서 '📋 공급처 매핑 리스트' 페이지로 이동하여 확인해주세요.")
        else:
            st.error("❌ 저장 확인 실패 - 다시 시도해주세요.")
        
        # 성공한 경우 폼 초기화를 위한 rerun
        if vendor_check:
            st.rerun()
        
    except Exception as e:
        st.error(f"❌ 저장 실패: {e}")

# ─────────────────────────────────────
# 9. 미매칭 alias 표시 (저장 완료 후에는 숨김)
# ─────────────────────────────────────
# 저장 버튼이 눌렸는지 확인하는 상태 관리
if 'save_completed' not in st.session_state:
    st.session_state.save_completed = False

# 저장이 완료되지 않았을 때만 미매칭 정보 표시
if not st.session_state.save_completed:
    st.divider()
    st.subheader("📁 실제 데이터 기준 미매칭 Alias")
    df_unmatch = find_unmatched_aliases()

    if df_unmatch.empty:
        st.success("모든 업로드 데이터가 정상 매핑되었습니다 🎉")
    else:
        st.write("### 🔢 파일별 미매칭 개수",
                 df_unmatch.groupby("file_type")["alias"].count()
                            .rename("건수").to_frame().T)
        st.warning(f"⚠️ 미매칭 alias {len(df_unmatch):,}건 발견")
        st.dataframe(df_unmatch.reset_index(drop=True), use_container_width=True, height=300)
        st.download_button("⬇️ CSV 다운로드",
                           df_unmatch.to_csv(index=False).encode("utf-8-sig"),
                           "unmatched_alias.csv",
                           mime="text/csv")

    if st.button("♻️ 캐시 재생성 후 새로고침"):
        refresh_alias_vendor_cache()
        st.cache_data.clear()
        st.rerun()
