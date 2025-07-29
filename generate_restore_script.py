import sqlite3
import pandas as pd
import os

# 원본 DB와 생성될 스크립트 파일 경로
SOURCE_DB = "billing.db"
OUTPUT_SCRIPT = "restore_mapping_data.py"

def generate_script():
    """로컬 DB에서 vendors와 aliases 테이블 데이터를 읽어 복원 스크립트를 생성합니다."""
    
    if not os.path.exists(SOURCE_DB):
        print(f"❌ 원본 데이터베이스 '{SOURCE_DB}'를 찾을 수 없습니다.")
        return

    with sqlite3.connect(SOURCE_DB) as con:
        try:
            vendors_df = pd.read_sql("SELECT * FROM vendors", con)
            aliases_df = pd.read_sql("SELECT * FROM aliases", con)
        except Exception as e:
            print(f"❌ 데이터베이스 테이블 읽기 실패: {e}")
            return

    if vendors_df.empty and aliases_df.empty:
        print("❌ vendors와 aliases 테이블이 모두 비어있어 스크립트를 생성할 수 없습니다.")
        return

    # DataFrame을 파이썬 코드로 변환 (to_json 사용)
    vendors_data_json = vendors_df.to_json(orient='split', index=False)
    aliases_data_json = aliases_df.to_json(orient='split', index=False)

    # 복원 스크립트 내용 생성
    script_content = f'''
# 자동 생성된 매핑 데이터 복원 스크립트입니다.
# 이 파일을 직접 수정하지 마세요.

import sqlite3
import pandas as pd
import streamlit as st

def restore_data():
    """vendors와 aliases 테이블 데이터를 DB에 복원합니다."""
    
    # JSON 데이터에서 DataFrame 복원
    vendors_df = pd.read_json("""
{vendors_data_json}
""", orient='split')
    
    aliases_df = pd.read_json("""
{aliases_data_json}
""", orient='split')

    try:
        with sqlite3.connect("billing.db") as con:
            # 기존 데이터를 삭제하고 새로 추가 (멱등성 보장)
            con.execute("DELETE FROM vendors")
            con.execute("DELETE FROM aliases")
            
            # DataFrame 데이터를 DB에 쓰기
            vendors_df.to_sql('vendors', con, if_exists='append', index=False)
            aliases_df.to_sql('aliases', con, if_exists='append', index=False)
            
            # SQLite의 VACUUM으로 정리 (선택사항)
            con.execute("VACUUM")

        st.success(f"✅ 데이터 복원 완료: 공급처 {{len(vendors_df)}}건, 별칭 {{len(aliases_df)}}건")
        st.info("이제 이 버튼은 더 이상 누르지 않아도 됩니다. 페이지를 새로고침 하세요.")
        
    except Exception as e:
        st.error(f"🚨 데이터 복원 중 오류 발생: {{e}}")
        st.error("테이블 스키마가 호환되지 않을 수 있습니다. DB 파일을 확인해주세요.")

if __name__ == '__main__':
    # 이 파일을 직접 실행하면 아무 작업도 수행하지 않습니다.
    print("이 스크립트는 Streamlit 앱 내에서 '데이터 복원' 버튼을 통해 사용되어야 합니다.")
'''

    # 파일로 저장
    with open(OUTPUT_SCRIPT, "w", encoding="utf-8") as f:
        f.write(script_content)
        
    print(f"✅ 복원 스크립트 '{OUTPUT_SCRIPT}' 생성 완료!")
    print("이제 이 파일을 Git에 커밋하고, 앱에 추가될 '데이터 복원' 버튼을 누르세요.")


if __name__ == "__main__":
    generate_script() 