"""
One-time migration: add 'email' column to existing user table.
Run this ONCE: python migrate_add_email.py
After it succeeds, you can safely run main.py normally.
"""
import sqlite3
import os
import glob

# Find the database file in current directory
candidates = glob.glob('*.db') + glob.glob('instance/*.db')
if not candidates:
    print("❌ No .db file found in current directory or ./instance/")
    print("   Make sure you run this script from the THESIS folder.")
    exit(1)

db_path = candidates[0]
print(f"📂 Found database: {db_path}")

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Check existing columns on `user` table
cur.execute("PRAGMA table_info(user)")
columns = [row[1] for row in cur.fetchall()]
print(f"   Existing columns: {columns}")

if 'email' in columns:
    print("✅ 'email' column already exists. Nothing to do.")
else:
    print("⚙️  Adding 'email' column...")
    cur.execute("ALTER TABLE user ADD COLUMN email VARCHAR(120) DEFAULT ''")
    conn.commit()
    print("✅ 'email' column added successfully.")

conn.close()
print("\n Done. You can now run: python main.py")