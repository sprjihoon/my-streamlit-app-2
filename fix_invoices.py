import sqlite3, os

db = None
for p in ['backend/invoice.db', 'backend/app/invoice.db', 'invoice.db']:
    if os.path.exists(p):
        db = p
        break

if not db:
    print("DB not found")
    exit(1)

print(f"Using DB: {db}")
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row

# 3건 조회
rows = con.execute("""
    SELECT id, client_name, service_month, total_amount, supply_amount, vat_amount
    FROM billing_invoices
    WHERE client_name LIKE '%AVAUMA%'
       OR client_name LIKE '%팔로우미%'
       OR client_name LIKE '%퀀텀%'
    ORDER BY created_at DESC
""").fetchall()

print(f"\n=== 검색된 인보이스 ({len(rows)}건) ===")
for r in rows:
    print(dict(r))

# 실제 수정 (사용자 이미지 기준)
# AVAUMA: total_amount에 62,250 누락 → 총액 수정
# 팔로우미코스메틱: total_amount에 10,000,000 과다 → 수정
# 퀀텀점프유: 9,735 차이 → 수정

fixes = []
for r in rows:
    d = dict(r)
    if 'AVAUMA' in d['client_name'].upper():
        # 올바른 total = 현재 + 62,250 (62,250 + 11,273,515 원이 공급가액)
        # supply_amount도 62,250 증가
        new_supply = (d['supply_amount'] or 0) + 62250
        new_vat = round(new_supply * 0.1)
        new_total = new_supply + new_vat
        fixes.append((new_supply, new_vat, new_total, d['id'], 'AVAUMA'))
    elif '팔로우미' in d['client_name']:
        # 10,000,000 과다 → 빼기
        new_supply = (d['supply_amount'] or 0) - 10000000
        new_vat = round(new_supply * 0.1)
        new_total = new_supply + new_vat
        fixes.append((new_supply, new_vat, new_total, d['id'], '팔로우미코스메틱'))
    elif '퀀텀' in d['client_name']:
        # 9,735 차이 → 정확한 값으로 수정
        new_supply = (d['supply_amount'] or 0) + 9735
        new_vat = round(new_supply * 0.1)
        new_total = new_supply + new_vat
        fixes.append((new_supply, new_vat, new_total, d['id'], '퀀텀점프유'))

print(f"\n=== 수정 예정 ({len(fixes)}건) ===")
for f in fixes:
    print(f"  {f[4]}: supply={f[0]:,.0f}, vat={f[1]:,.0f}, total={f[2]:,.0f}")

if fixes:
    confirm = input("\n수정을 진행하시겠습니까? (y/n): ")
    if confirm.lower() == 'y':
        for f in fixes:
            con.execute(
                "UPDATE billing_invoices SET supply_amount=?, vat_amount=?, total_amount=?, paid_amount=? WHERE id=?",
                (f[0], f[1], f[2], f[2], f[3])
            )
        con.commit()
        print("수정 완료!")
    else:
        print("취소됨")
else:
    print("수정할 항목 없음")

con.close()
