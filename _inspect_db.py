import sqlite3

conn = sqlite3.connect('billing.db')
cur = conn.cursor()

# List tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print("=== TABLES ===")
for t in tables:
    print(t)

# Print schema for key tables
key_tables = [t for t in tables if any(k in t for k in ['inbound', 'defect', 'repair', 'share', 'batch', 'item'])]
print("\n=== KEY TABLE SCHEMAS ===")
for t in key_tables:
    cur.execute(f"PRAGMA table_info({t})")
    cols = cur.fetchall()
    print(f"\n--- {t} ---")
    for c in cols:
        print(f"  {c[1]} {c[2]} {'NOT NULL' if c[3] else ''} {'PK' if c[5] else ''}")

conn.close()
