#!/usr/bin/env python3
"""
배송 사이즈 집계에서 누락되는 업체 진단 스크립트
===============================================

1. vendors 테이블과 aliases 테이블 불일치 확인
2. kpost_in의 발송인명과 매핑되지 않은 업체 찾기
3. 각 업체별 데이터 건수 및 별칭 매핑 상태 확인
"""

import sqlite3
import pandas as pd
from datetime import date, timedelta

def diagnose_missing_vendors():
    print("🔍 배송 사이즈 집계 누락 업체 진단 시작\n")
    
    with sqlite3.connect("billing.db") as con:
        # 1. 테이블 존재 확인
        tables = [t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print("📋 존재하는 테이블:", tables)
        
        if "vendors" not in tables:
            print("❌ vendors 테이블이 없습니다!")
            return
            
        if "aliases" not in tables:
            print("❌ aliases 테이블이 없습니다!")
            return
            
        if "kpost_in" not in tables:
            print("❌ kpost_in 테이블이 없습니다!")
            return
        
        # 2. vendors 테이블 스키마 확인
        vendor_schema = con.execute("PRAGMA table_info(vendors)").fetchall()
        print(f"\n📊 vendors 테이블 스키마: {[c[1] for c in vendor_schema]}")
        
        # 3. 전체 공급처 목록
        vendors_df = pd.read_sql("SELECT * FROM vendors", con)
        print(f"\n👥 등록된 공급처 수: {len(vendors_df)}")
        
        # 4. kpost_in 데이터의 고유 발송인명 목록
        kpost_senders = pd.read_sql("SELECT DISTINCT 발송인명, COUNT(*) as 건수 FROM kpost_in GROUP BY 발송인명 ORDER BY 건수 DESC", con)
        print(f"\n📦 kpost_in 고유 발송인명: {len(kpost_senders)}개")
        print("상위 10개:")
        print(kpost_senders.head(10).to_string(index=False))
        
        # 5. 별칭 매핑 상태 확인
        aliases_df = pd.read_sql("SELECT * FROM aliases WHERE file_type = 'kpost_in'", con)
        print(f"\n🔗 kpost_in 별칭 매핑: {len(aliases_df)}개")
        
        # 6. 매핑되지 않은 발송인명 찾기
        mapped_senders = set(aliases_df["alias"].tolist())
        all_senders = set(kpost_senders["발송인명"].tolist())
        unmapped = all_senders - mapped_senders
        
        # vendors에 직접 이름이 있는지도 확인
        vendor_names = set(vendors_df["vendor"].tolist())
        if "name" in vendors_df.columns:
            vendor_names.update(vendors_df["name"].dropna().tolist())
        
        really_unmapped = unmapped - vendor_names
        
        print(f"\n❌ 매핑되지 않은 발송인명: {len(really_unmapped)}개")
        if really_unmapped:
            unmapped_with_count = kpost_senders[kpost_senders["발송인명"].isin(really_unmapped)].sort_values("건수", ascending=False)
            print("상위 누락 발송인명:")
            print(unmapped_with_count.head(15).to_string(index=False))
        
        # 7. 각 공급처별 실제 데이터 건수 확인 (최근 30일)
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        print(f"\n📈 최근 30일 ({start_date} ~ {end_date}) 공급처별 데이터 건수:")
        
        vendor_data_counts = []
        for _, vendor_row in vendors_df.iterrows():
            vendor = vendor_row["vendor"]
            
            # 별칭 목록 가져오기
            vendor_aliases = aliases_df[aliases_df["vendor"] == vendor]["alias"].tolist()
            search_names = [vendor] + vendor_aliases
            
            # 데이터 건수 조회
            placeholders = ",".join(["?"] * len(search_names))
            count = con.execute(f"""
                SELECT COUNT(*) FROM kpost_in 
                WHERE TRIM(발송인명) IN ({placeholders})
                AND DATE(접수일자) BETWEEN ? AND ?
            """, (*search_names, str(start_date), str(end_date))).fetchone()[0]
            
            vendor_data_counts.append({
                "공급처": vendor,
                "별칭수": len(vendor_aliases),
                "최근30일건수": count,
                "별칭목록": ", ".join(vendor_aliases[:3]) + ("..." if len(vendor_aliases) > 3 else "")
            })
        
        vendor_data_df = pd.DataFrame(vendor_data_counts).sort_values("최근30일건수", ascending=False)
        print(vendor_data_df.head(20).to_string(index=False))
        
        # 8. 데이터는 있지만 별칭이 없는 경우
        no_alias_but_has_data = vendor_data_df[(vendor_data_df["별칭수"] == 0) & (vendor_data_df["최근30일건수"] > 0)]
        if not no_alias_but_has_data.empty:
            print(f"\n⚠️  별칭 없이 직접 매칭되는 공급처 ({len(no_alias_but_has_data)}개):")
            print(no_alias_but_has_data.to_string(index=False))
        
        # 9. 별칭은 있지만 데이터가 없는 경우
        has_alias_no_data = vendor_data_df[(vendor_data_df["별칭수"] > 0) & (vendor_data_df["최근30일건수"] == 0)]
        if not has_alias_no_data.empty:
            print(f"\n⚠️  별칭은 있지만 데이터가 없는 공급처 ({len(has_alias_no_data)}개):")
            print(has_alias_no_data.to_string(index=False))

if __name__ == "__main__":
    diagnose_missing_vendors() 