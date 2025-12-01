# ── 서드파티 ────────────────────────────────────
import streamlit as st
import pandas as pd

# ── 로컬 모듈 ───────────────────────────────────
from common import get_connection

"""pages/3_rate_manager.py – 글로벌 요금표 관리 (출고·추가작업·배송·부자재)
────────────────────────────────────────────────────────────
* shipping_zone / material_rates / out_basic / out_extra 편집
* shipping_zone: 숫자 범위(len_min_cm, len_max_cm) 기반 구조
"""

TABLES = {
    "out_basic": "출고비 (SKU 구간)",
    "out_extra": "추가 작업 단가",
    "shipping_zone": "배송 요금 구간",
    "material_rates": "부자재 요금표",
}

DEFAULT_DATA = {
    "out_basic": pd.DataFrame({
        "sku_group": ["≤100", "≤300", "≤500", "≤1,000", "≤2,000", ">2,000"],
        "단가": [900, 950, 1000, 1100, 1200, 1300],
    }),
    "out_extra": pd.DataFrame({
        "항목": ["입고검수", "바코드 부착", "합포장", "완충작업", "출고영상촬영", "반품영상촬영"],
        "단가": [100, 150, 100, 100, 200, 400],
    }),
    "shipping_zone": pd.DataFrame({
        "요금제": ["표준"] * 6 + ["A"] * 6,
        "구간": ["극소", "소", "중", "대", "특대", "특특대"] * 2,
        "len_min_cm": [0, 51, 71, 101, 121, 141] * 2,
        "len_max_cm": [50, 70, 100, 120, 140, 160] * 2,
        "요금": [2100, 2400, 2900, 3800, 7400, 10400, 1900, 2100, 2500, 3300, 7200, 10200],
    }),
}

try:
    st.set_page_config(page_title="요금 관리", layout="wide")
except Exception:
    pass
st.title("📋 글로벌 요금표 관리")

# ─────────────────────────────────────
# 1. 테이블 선택
# ─────────────────────────────────────
selected_table = st.selectbox(
    "💾 요금 테이블 선택", list(TABLES.keys()), format_func=lambda x: TABLES[x]
)

# ─────────────────────────────────────
# 2. 테이블 & 초기 데이터 보장
# ─────────────────────────────────────
with get_connection() as con:
    con.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}  # ✅ 수정 포인트

    if selected_table == "shipping_zone":
        cols = [r["name"] for r in con.execute("PRAGMA table_info(shipping_zone);")]
        if not {"len_min_cm", "len_max_cm"}.issubset(cols):
            st.warning("shipping_zone 구조 갱신 (len_min_cm, len_max_cm 추가)")
            con.executescript(
                """
                ALTER TABLE shipping_zone RENAME TO shipping_zone_old;
                CREATE TABLE shipping_zone(
                    요금제 TEXT,
                    구간   TEXT,
                    len_min_cm INTEGER,
                    len_max_cm INTEGER,
                    요금   INTEGER,
                    PRIMARY KEY (요금제, 구간)
                );
                INSERT INTO shipping_zone(요금제, 구간, 요금)
                  SELECT 요금제, 구간, 요금 FROM shipping_zone_old;
                DROP TABLE shipping_zone_old;
                """
            )

    if selected_table in DEFAULT_DATA:
        df_def = DEFAULT_DATA[selected_table]
        if selected_table == "shipping_zone":
            con.execute(
                """CREATE TABLE IF NOT EXISTS shipping_zone(
                    요금제 TEXT,
                    구간 TEXT,
                    len_min_cm INTEGER,
                    len_max_cm INTEGER,
                    요금 INTEGER,
                    PRIMARY KEY(요금제, 구간)
                )"""
            )
        else:
            cols_sql = ", ".join(f"[{c}] TEXT" for c in df_def.columns)
            pk = df_def.columns[0]
            con.execute(
                f"CREATE TABLE IF NOT EXISTS {selected_table}({cols_sql}, PRIMARY KEY([{pk}]))"
            )
        if not pd.read_sql(f"SELECT * FROM {selected_table}", con).shape[0]:
            df_def.to_sql(selected_table, con, index=False, if_exists="append")
            st.info(f"초기 '{TABLES[selected_table]}' 데이터가 등록되었습니다.")

@st.cache_data(ttl=5)
def fetch_df(tbl: str):
    with get_connection() as con:
        return pd.read_sql(f"SELECT * FROM {tbl}", con)

def replace_df(tbl: str, df: pd.DataFrame):
    with get_connection() as con:
        con.execute(f"DELETE FROM {tbl}")
        df.to_sql(tbl, con, index=False, if_exists="append")

if selected_table == "shipping_zone":
    rate_type = st.radio("요금제", ["표준", "A"], horizontal=True)
    full_df = fetch_df("shipping_zone")
    view_df = full_df[full_df["요금제"] == rate_type].reset_index(drop=True)
else:
    view_df = fetch_df(selected_table)

st.subheader(f"✏️ {TABLES[selected_table]} 수정")

# ─────────────────────────────────────
# PyArrow 완전 우회: HTML + CSV 기반 편집
# ─────────────────────────────────────

# 1. 컬럼/데이터 정리
if not view_df.empty:
    columns = list(view_df.columns)
elif selected_table in DEFAULT_DATA:
    columns = list(DEFAULT_DATA[selected_table].columns)
else:
    columns = []

if not view_df.empty:
    view_df_clean = view_df.copy()
else:
    view_df_clean = pd.DataFrame(columns=columns)

# 2. 현재 데이터 HTML 테이블로 표시
if view_df_clean.empty:
    st.info("표시할 데이터가 없습니다.")
else:
    st.markdown(
        view_df_clean.to_html(index=False, escape=False, classes="dataframe"),
        unsafe_allow_html=True,
    )

# 3. CSV 다운로드 버튼
csv_bytes = view_df_clean.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "⬇️ CSV 다운로드",
    csv_bytes,
    file_name=f"{selected_table}_rates.csv",
    mime="text/csv",
    key="download_rates",
)

# 4. 수정된 CSV 업로드 후 DB 반영
uploaded = st.file_uploader("수정된 CSV 업로드", type=["csv"], key="upload_rates")

if uploaded is not None:
    try:
        edit_df = pd.read_csv(uploaded)

        # 컬럼 구성 검증
        if columns and set(edit_df.columns) != set(columns):
            st.error("CSV 컬럼 구성이 현재 테이블과 다릅니다. 컬럼명을 수정하지 말고 값만 변경해주세요.")
        else:
            if selected_table == "shipping_zone":
                # 선택된 요금제(rate_type) 구간만 교체
                other_df = full_df[full_df["요금제"] != rate_type]
                replace_df(
                    "shipping_zone",
                    pd.concat([other_df, edit_df], ignore_index=True),
                )
            else:
                replace_df(selected_table, edit_df)

            st.cache_data.clear()
            st.success("저장 완료")
            st.rerun()
    except Exception as e:
        st.error(f"CSV 처리 중 오류: {e}")