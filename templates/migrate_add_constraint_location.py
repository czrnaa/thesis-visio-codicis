"""
One-time migration: add lat / lon / constraint_type / task_id /
reported_by / resolved_at columns to existing road_constraint table.

Run this ONCE:  python migrate_add_constraint_location.py
After it succeeds, you can safely run main.py normally.
"""
import sqlite3
import glob

candidates = glob.glob('*.db') + glob.glob('instance/*.db')
if not candidates:
    print("No .db file found in current directory or ./instance/")
    print("Make sure you run this script from the project folder.")
    raise SystemExit(1)

db_path = candidates[0]
print(f"Found database: {db_path}")

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("PRAGMA table_info(road_constraint)")
existing = {row[1] for row in cur.fetchall()}
print(f"   Existing columns: {sorted(existing)}")

new_cols = [
    ("lat",             "FLOAT"),
    ("lon",             "FLOAT"),
    ("constraint_type", "VARCHAR(30)"),
    ("task_id",         "VARCHAR(20)"),
    ("reported_by",     "VARCHAR(50)"),
    ("resolved_at",     "DATETIME"),
]

added = []
for name, sqltype in new_cols:
    if name in existing:
        print(f"   '{name}' already present — skipping.")
        continue
    cur.execute(f"ALTER TABLE road_constraint ADD COLUMN {name} {sqltype}")
    added.append(name)
    print(f"   added '{name}' ({sqltype})")

conn.commit()
conn.close()

if added:
    print(f"\nDone. Added columns: {', '.join(added)}")
else:
    print("\nDone. No changes needed.")