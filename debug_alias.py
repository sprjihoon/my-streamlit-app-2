# -*- coding: utf-8 -*-
"""
투에버 물류센터 별칭 디버깅 스크립트
이 스크립트를 서버에서 실행하여 문제를 파악합니다.
"""
import sqlite3
import os

# 배포 환경에 맞게 경로 설정
DB_PATH = "/app/data/billing.db" if os.path.exists("/app/data") else "billing.db"

def hex_dump(s):
    """문자열의 헥스 값 출력 (숨겨진 문자 확인용)"""
    return ' '.join(f'{ord(c):04x}' for c in s)

def analyze_alias():
    con = sqlite3.connect(DB_PATH)
    
    print(f"=== 데이터베이스 경로: {DB_PATH} ===\n")
    
    # 1. kpost_ret 테이블에서 '투에버' 또는 '물류센터' 포함된 별칭 찾기
    print("=== kpost_ret 테이블 내 관련 별칭 ===")
    try:
        cursor = con.execute("""
            SELECT DISTINCT 수취인명, LENGTH(수취인명) as len
            FROM kpost_ret 
            WHERE 수취인명 LIKE '%투에버%' OR 수취인명 LIKE '%물류센터%'
        """)
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                alias = row[0]
                print(f"  원본: '{alias}'")
                print(f"  길이: {row[1]}")
                print(f"  Strip 후: '{alias.strip()}' (길이: {len(alias.strip())})")
                print(f"  Hex: {hex_dump(alias)}")
                print()
        else:
            print("  → kpost_ret 테이블에 해당 별칭 없음")
    except Exception as e:
        print(f"  → 오류: {e}")
    
    # 2. aliases 테이블에서 관련 매핑 확인
    print("\n=== aliases 테이블 내 관련 매핑 ===")
    try:
        cursor = con.execute("""
            SELECT alias, vendor, file_type, LENGTH(alias) as len
            FROM aliases 
            WHERE alias LIKE '%투에버%' OR alias LIKE '%물류센터%'
        """)
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                alias = row[0]
                print(f"  별칭: '{alias}'")
                print(f"  거래처: '{row[1]}'")
                print(f"  파일타입: '{row[2]}'")
                print(f"  길이: {row[3]}")
                print(f"  Hex: {hex_dump(alias)}")
                print()
        else:
            print("  → aliases 테이블에 해당 매핑 없음 (이게 문제!)")
    except Exception as e:
        print(f"  → 오류: {e}")
    
    # 3. kpost_ret 전체 별칭 vs aliases 매핑 비교
    print("\n=== kpost_ret 별칭 매칭 상태 ===")
    try:
        # 소스 테이블의 모든 별칭
        cursor = con.execute("SELECT DISTINCT 수취인명 FROM kpost_ret WHERE 수취인명 IS NOT NULL")
        source_aliases = {row[0].strip(): row[0] for row in cursor.fetchall() if row[0]}
        
        # 매핑된 별칭
        cursor = con.execute("SELECT DISTINCT alias FROM aliases WHERE file_type = 'kpost_ret'")
        mapped_aliases = {row[0].strip() for row in cursor.fetchall() if row[0]}
        
        print(f"  소스 테이블 별칭 수: {len(source_aliases)}")
        print(f"  매핑된 별칭 수: {len(mapped_aliases)}")
        
        # 미매칭 찾기
        unmatched = []
        for stripped, original in source_aliases.items():
            if stripped not in mapped_aliases:
                unmatched.append((original, stripped))
        
        print(f"  미매칭 별칭 수: {len(unmatched)}")
        if unmatched:
            print("\n  미매칭 상세:")
            for original, stripped in unmatched[:10]:  # 처음 10개만 출력
                print(f"    원본: '{original}' → Strip: '{stripped}'")
                print(f"    Hex: {hex_dump(original)}")
    except Exception as e:
        print(f"  → 오류: {e}")
    
    # 4. 특수 문자 확인
    print("\n=== 보이지 않는 문자 확인 ===")
    try:
        cursor = con.execute("""
            SELECT DISTINCT 수취인명 
            FROM kpost_ret 
            WHERE 수취인명 != TRIM(수취인명)
              OR 수취인명 LIKE '% '
              OR 수취인명 LIKE ' %'
        """)
        rows = cursor.fetchall()
        if rows:
            print(f"  공백 문제 있는 별칭 {len(rows)}개 발견:")
            for row in rows[:5]:
                print(f"    '{row[0]}' - Hex: {hex_dump(row[0])}")
        else:
            print("  → 앞뒤 공백 문제 없음")
    except Exception as e:
        print(f"  → 오류: {e}")
    
    con.close()

if __name__ == "__main__":
    analyze_alias()
