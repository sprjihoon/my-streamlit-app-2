# -*- coding: utf-8 -*-
import sqlite3

con = sqlite3.connect('billing.db')

print("=== 투에버 물류센터 관련 별칭 검색 ===")
cursor = con.execute("SELECT * FROM aliases WHERE alias LIKE '%투에버%' OR alias LIKE '%물류센터%'")
results = cursor.fetchall()
if results:
    for row in results:
        print(f"별칭: {row[0]}, 거래처: {row[1]}, 파일타입: {row[2]}")
else:
    print("결과 없음")

print("\n=== 우체국반품(kpost_ret) 전체 별칭 ===")
cursor2 = con.execute("SELECT * FROM aliases WHERE file_type = 'kpost_ret'")
results2 = cursor2.fetchall()
if results2:
    for row in results2:
        print(f"별칭: {row[0]}, 거래처: {row[1]}, 파일타입: {row[2]}")
else:
    print("결과 없음")

print("\n=== aliases 테이블 스키마 ===")
cursor3 = con.execute("PRAGMA table_info(aliases)")
for row in cursor3.fetchall():
    print(row)

print("\n=== 전체 별칭 수 ===")
cursor4 = con.execute("SELECT file_type, COUNT(*) FROM aliases GROUP BY file_type")
for row in cursor4.fetchall():
    print(f"{row[0]}: {row[1]}개")

con.close()
