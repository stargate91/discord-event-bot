import sqlite3
import os

DB_PATH = os.path.join("data", "events.db")

def migrate():
    if not os.path.exists(DB_PATH):
        print("Database not found, skipping migration.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("ALTER TABLE active_events ADD COLUMN extra_data TEXT;")
        conn.commit()
        print("Migration successful: added extra_data to active_events.")
    except Exception as e:
        print(f"Migration skipped or failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
