import sqlite3

TARGETS = [
    ("shipping_stats", "공급처"),
    ("kpost_ret",     "수취인명"),
]

def main():
    with sqlite3.connect("billing.db") as con:
        cur = con.cursor()
        for tbl, col in TARGETS:
            cols = [r[1] for r in cur.execute(f"PRAGMA table_info({tbl})")]
            print("▶", tbl, "columns:", cols)
            if col not in cols:
                print(f"  └─ Adding missing column → {col}")
                cur.execute(f"ALTER TABLE {tbl} ADD COLUMN [{col}] TEXT")
        con.commit()
        print("✅ 완료 (All missing columns ensured)")

if __name__ == "__main__":
    main() 