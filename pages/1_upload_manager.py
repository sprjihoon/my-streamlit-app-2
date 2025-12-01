import os
import sqlite3
from pathlib import Path
from typing import Dict
import time
import io
from datetime import date

import pandas as pd
import streamlit as st

"""pages/1_upload_data.py – 원본 엑셀 업로드 (중복제거 + 백업 저장)
────────────────────────────────────────────
• 기존 테이블 데이터 유지 + 새로운 데이터 추가 (중복 제거)
• 업로드 성공 시: 신규 추가된 건수 따로 표시
• 테이블 삭제 시: 백업 테이블로 복사한 후 삭제
"""

# ─────────────────────────────────────
# 기본 설정
# ─────────────────────────────────────
try:
    st.set_page_config(page_title="데이터 업로드", layout="wide")
except Exception:
    pass

st.title("📤 원본 데이터 업로드")
MESSAGE_DELAY = 2.5

db_path = "billing.db"

# 안전한 rerun 헬퍼

def safe_rerun():
    if callable(getattr(st, "rerun", None)):
        st.rerun()
    elif callable(getattr(st, "experimental_rerun", None)):
        st.experimental_rerun()
    else:
        st.info("🔄 페이지를 새로고침(F5) 해주세요.")

# 업로드 대상 정의
TARGETS: Dict[str, Dict] = {
    "inbound_slip":   {"label": "입고전표",   "key": "공급처"},
    "shipping_stats": {"label": "배송통계",   "key": "공급처"},
    "kpost_in":       {"label": "우체국접수", "key": "발송인명"},
    "kpost_ret":      {"label": "우체국반품", "key": "수취인명"},
    "work_log":       {"label": "작업일지",   "key": "업체명"},
}

# ─────────────────────────────────────
# HELPER
# ─────────────────────────────────────

def save_df_to_db(df: pd.DataFrame, table: str):
    with sqlite3.connect(db_path) as con:
        try:
            df_exist = pd.read_sql(f"SELECT * FROM {table}", con)
        except Exception:
            df_exist = pd.DataFrame()

        before = len(df_exist)

        if not df_exist.empty:
            df_merge = pd.concat([df_exist, df]).drop_duplicates()
        else:
            df_merge = df

        df_merge.to_sql(table, con, if_exists="replace", index=False)
        after = len(df_merge)

    added = after - before
    return after, added


def delete_table_with_backup(table: str):
    with sqlite3.connect(db_path) as con:
        try:
            con.execute(f"DROP TABLE IF EXISTS {table}_backup")
            con.execute(f"CREATE TABLE {table}_backup AS SELECT * FROM {table}")
            con.execute(f"DROP TABLE IF EXISTS {table}")
            st.success(f"{TARGETS[table]['label']} 테이블을 백업 후 삭제했습니다.")
        except Exception as e:
            st.error(f"삭제 실패: {e}")

# ─────────────────────────────────────
# 캐시된 테이블 존재 확인 함수
# ─────────────────────────────────────
@st.cache_data(ttl=30)
def check_table_exists(table_name):
    with sqlite3.connect(db_path) as con:
        try:
            result = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", 
                (table_name,)
            ).fetchone()
            if result:
                count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                return count > 0, count
            return False, 0
        except Exception:
            return False, 0

# ─────────────────────────────────────
# 업로드 UI (최적화)
# ─────────────────────────────────────

cols = st.columns(len(TARGETS))
for (tbl, meta), col in zip(TARGETS.items(), cols):
    label = meta["label"]
    col.subheader(label)

    upl = col.file_uploader("엑셀 파일", type=["xlsx"], key=f"upl_{tbl}")
    if upl is not None:
        try:
            df_up = pd.read_excel(upl)
            if df_up.empty:
                col.warning("빈 파일입니다.")
            else:
                # 간략한 정보만 표시 (성능 개선)
                col.info(f"📊 {len(df_up):,}행 × {len(df_up.columns)}컬럼")
                
                # 상세 보기는 expander로
                with col.expander("📋 상세 미리보기"):
                    st.dataframe(df_up.head(3).astype(str), width='stretch')
                    st.caption(f"컬럼: {', '.join(df_up.columns[:5])}{'...' if len(df_up.columns) > 5 else ''}")

                if col.button("✅ 신규 데이터 저장", key=f"save_{tbl}"):
                    try:
                        with st.spinner("신규 데이터 저장 중..."):
                            t0 = time.time()
                            total, added = save_df_to_db(df_up, tbl)
                            elapsed = time.time() - t0

                        if added == 0:
                            col.warning(f"⚠️ 새로운 데이터가 없습니다. ({elapsed:.2f}s)")
                        else:
                            col.success(f"✅ {added:,}건 추가! (전체 {total:,}건, {elapsed:.2f}s)")
                        time.sleep(MESSAGE_DELAY)
                        safe_rerun()
                    except Exception as e:
                        col.error(f"❌ 저장 중 오류: {e}")
        except Exception as e:
            col.error(f"읽기 실패: {e}")

    # 📥 현 테이블 다운로드 버튼 (캐시 사용)
    has_data, row_count = check_table_exists(tbl)
    
    if has_data:
        if col.button(f"⬇️ 다운로드 ({row_count:,}건)", key=f"dl_prep_{tbl}"):
            with st.spinner("Excel 생성 중..."):
                with sqlite3.connect(db_path) as con:
                    df_tbl = pd.read_sql(f"SELECT * FROM {tbl}", con)
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df_tbl.to_excel(writer, index=False, sheet_name=tbl)
                buffer.seek(0)
                
                col.download_button(
                    label="📁 다운로드",
                    data=buffer.getvalue(),
                    file_name=f"{tbl}_{date.today()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_table_{tbl}"
                )
    else:
        col.caption("데이터 없음")

    if col.button("🗑 삭제", key=f"del_{tbl}"):
        delete_table_with_backup(tbl)
        time.sleep(MESSAGE_DELAY)
        safe_rerun()

# ─────────────────────────────────────
# DB 상태 요약 (캐시 적용)
# ─────────────────────────────────────

@st.cache_data(ttl=60)  # 1분 캐시
def get_db_status():
    status_rows = []
    with sqlite3.connect(db_path) as con:
        for tbl, meta in TARGETS.items():
            exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
            ).fetchone()
            if exists:
                cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                cnt_str = f"{cnt:,}"  # 숫자를 포맷팅된 문자열로 변환
            else:
                cnt_str = "(없음)"
            status_rows.append({"테이블": meta["label"], "행 수": cnt_str})
    # dtype을 명시적으로 지정하여 PyArrow 변환 문제 방지
    df = pd.DataFrame(status_rows)
    # 모든 컬럼을 명시적으로 문자열로 변환
    for col in df.columns:
        df[col] = df[col].astype(str)
    return df.set_index("테이블")

st.divider()
col1, col2 = st.columns([3, 1])
with col1:
    st.subheader("📊 DB 테이블 현황")
with col2:
    if st.button("🔄 새로고침", key="refresh_db_status"):
        st.cache_data.clear()
        st.rerun()

st.dataframe(get_db_status(), use_container_width=True)
