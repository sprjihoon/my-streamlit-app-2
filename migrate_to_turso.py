import sqlite3
import pandas as pd
import streamlit as st
from contextlib import closing

# Turso 연결을 위해 common.py의 함수를 가져옵니다.
from common import get_connection

# 로컬 DB 파일명
LOCAL_DB = "billing.db"

def migrate_data():
    """로컬 SQLite DB에서 Turso 클라우드 DB로 모든 테이블의 데이터를 이전합니다."""
    
    st.info("데이터 마이그레이션을 시작합니다. 잠시만 기다려주세요...")

    try:
        # 1. 로컬 DB에서 모든 테이블 이름 가져오기
        with closing(sqlite3.connect(LOCAL_DB)) as local_con:
            local_tables_df = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'", local_con)
            table_names = local_tables_df['name'].tolist()

        if not table_names:
            st.warning("로컬 DB에 테이블이 없어 마이그레이션할 데이터가 없습니다.")
            return

        st.write(f"**대상 테이블:** {', '.join(table_names)}")

        # 2. Turso DB에 연결
        with get_connection() as turso_client:

            # 3. 각 테이블의 데이터를 로컬에서 읽어 Turso로 쓰기
            for table_name in table_names:
                with st.spinner(f"'{table_name}' 테이블 처리 중..."):
                    # 로컬에서 데이터 읽기
                    with closing(sqlite3.connect(LOCAL_DB)) as local_con:
                        df = pd.read_sql(f"SELECT * FROM {table_name}", local_con)
                    
                    if df.empty:
                        st.write(f"- '{table_name}' 테이블은 비어있어 건너뜁니다.")
                        continue

                    # Turso에 테이블 생성 (IF NOT EXISTS)
                    # DataFrame 스키마를 기반으로 DDL 생성
                    cols_with_types = []
                    for col_name, dtype in df.dtypes.items():
                        if pd.api.types.is_integer_dtype(dtype):
                            sql_type = "INTEGER"
                        elif pd.api.types.is_float_dtype(dtype):
                            sql_type = "REAL"
                        elif pd.api.types.is_datetime64_any_dtype(dtype):
                             sql_type = "TEXT" # 날짜/시간은 텍스트로 저장
                        else:
                            sql_type = "TEXT"
                        cols_with_types.append(f'"{col_name}" {sql_type}')
                    
                    # PK 정보가 없으므로 기본 컬럼으로 테이블 생성
                    create_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(cols_with_types)})"
                    turso_client.execute(create_sql)

                    # 기존 데이터 삭제 (멱등성을 위해)
                    turso_client.execute(f"DELETE FROM {table_name}")
                    
                    # 데이터를 executemany를 위한 튜플 리스트로 변환
                    records = [tuple(x) for x in df.to_records(index=False)]
                    placeholders = ', '.join(['?'] * len(df.columns))
                    insert_sql = f"INSERT INTO {table_name} ({', '.join(df.columns)}) VALUES ({placeholders})"
                    
                    # 데이터 삽입
                    turso_client.executemany(insert_sql, records)

                st.success(f"✅ '{table_name}' 테이블에 {len(df)}건의 데이터를 성공적으로 이전했습니다.")
        
        st.balloons()
        st.header("🎉 모든 데이터의 클라우드 이전이 완료되었습니다!")
        st.info("이제 이 버튼은 더 이상 누를 필요가 없습니다. 페이지를 새로고침하고 앱을 사용하세요.")

    except Exception as e:
        st.error(f"🚨 마이그레이션 중 심각한 오류 발생: {e}")
        st.error("오류를 해결한 후 다시 시도해주세요.")


def add_migration_button_to_main():
    """main.py에 마이그레이션 버튼을 추가하는 코드 조각입니다."""
    
    code_to_add = """
try:
    from migrate_to_turso import migrate_data
    
    st.warning("⚠️ 로컬 데이터를 클라우드로 이전할 때만 이 버튼을 누르세요. **단 한 번만 실행해야 합니다!**")
    if st.button("🚀 로컬 DB 데이터를 Turso 클라우드로 이전하기"):
        migrate_data()
    st.markdown("---")

except ImportError:
    # 마이그레이션 스크립트가 없으면 아무것도 표시하지 않음
    pass
"""
    
    st.subheader("main.py에 추가할 코드:")
    st.code(code_to_add, language="python")

if __name__ == "__main__":
    add_migration_button_to_main() 