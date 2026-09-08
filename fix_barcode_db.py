import sqlite3

con = sqlite3.connect('billing.db')

# 1. 전체 현황
total = con.execute('SELECT COUNT(*) FROM repair_barcode').fetchone()[0]
print(f'Total repair_barcode: {total}')

# 2. 오늘 업로드된 것
today = con.execute("SELECT COUNT(*) FROM repair_barcode WHERE 저장시간 >= '2026-09-08'").fetchone()[0]
print(f'Today (2026-09-08~) uploads: {today}')

# 3. 잘못된 업체명 샘플 (공급처로 시작)
print('\n[잘못된 업체명 샘플 - 공급처로 시작]')
wrong = con.execute("SELECT 바코드, 업체명, 저장시간 FROM repair_barcode WHERE 업체명 LIKE '공급처%' LIMIT 10").fetchall()
for r in wrong:
    print(f'  {r}')

wrong_cnt = con.execute("SELECT COUNT(*) FROM repair_barcode WHERE 업체명 LIKE '공급처%'").fetchone()[0]
print(f'\n잘못된 업체명(공급처~) 건수: {wrong_cnt}')

# 4. 최근 저장시간 확인
print('\n[최근 저장시간 top5]')
recent = con.execute("SELECT 바코드, 업체명, 저장시간 FROM repair_barcode ORDER BY 저장시간 DESC LIMIT 5").fetchall()
for r in recent:
    print(f'  {r}')

con.close()
