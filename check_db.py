import sqlite3

# billing.db 확인
con = sqlite3.connect('billing.db')
con.row_factory = sqlite3.Row
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('Tables in billing.db:', tables)

if 'billing_invoices' in tables:
    rows = con.execute("""
        SELECT id, client_name, service_month, total_amount, supply_amount, vat_amount
        FROM billing_invoices
        ORDER BY created_at DESC
        LIMIT 30
    """).fetchall()
    print(f"\nRecent invoices ({len(rows)}):")
    for r in rows:
        print(dict(r))

con.close()
