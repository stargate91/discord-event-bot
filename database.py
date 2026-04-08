import aiosqlite
import os

DB_PATH = os.path.join("data", "events.db")

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_events (
                event_id TEXT PRIMARY KEY,
                config_name TEXT,
                message_id INTEGER,
                channel_id INTEGER,
                start_time REAL,
                status TEXT DEFAULT 'active',
                title TEXT,
                description TEXT,
                image_urls TEXT,
                color TEXT,
                max_accepted INTEGER,
                ping_role INTEGER,
                end_time REAL,
                recurrence_type TEXT,
                repost_trigger TEXT,
                repost_offset TEXT,
                timezone TEXT DEFAULT 'Europe/Budapest'
            )
        """)
        
        # Migration for existing databases
        new_columns = [
            ("title", "TEXT"), ("description", "TEXT"), ("image_urls", "TEXT"),
            ("color", "TEXT"), ("max_accepted", "INTEGER"), ("ping_role", "INTEGER"),
            ("end_time", "REAL"), ("recurrence_type", "TEXT"), ("repost_trigger", "TEXT"),
            ("repost_offset", "TEXT"), ("timezone", "TEXT DEFAULT 'Europe/Budapest'")
        ]
        for col_name, col_type in new_columns:
            try:
                await db.execute(f"ALTER TABLE active_events ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass # Column already exists
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rsvps (
                event_id TEXT,
                user_id INTEGER,
                status TEXT,
                PRIMARY KEY (event_id, user_id)
            )
        """)
        await db.commit()

async def create_active_event(event_id, config_name, channel_id, start_time, data=None):
    if data is None:
        data = {}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO active_events (
                event_id, config_name, channel_id, start_time,
                title, description, image_urls, color, max_accepted, 
                ping_role, end_time, recurrence_type, repost_trigger, 
                repost_offset, timezone
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id, config_name, channel_id, start_time,
            data.get("title"), data.get("description"), data.get("image_urls"),
            data.get("color"), data.get("max_accepted"), data.get("ping_role"),
            data.get("end_time"), data.get("recurrence_type"), data.get("repost_trigger"),
            data.get("repost_offset"), data.get("timezone", "Europe/Budapest")
        ))
        await db.commit()

async def update_active_event(event_id, data):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE active_events SET 
                title = ?, description = ?, image_urls = ?, 
                color = ?, max_accepted = ?, ping_role = ?, 
                start_time = ?, end_time = ?, recurrence_type = ?, 
                repost_trigger = ?, repost_offset = ?, timezone = ?
            WHERE event_id = ?
        """, (
            data.get("title"), data.get("description"), data.get("image_urls"),
            data.get("color"), data.get("max_accepted"), data.get("ping_role"),
            data.get("start_time"), data.get("end_time"), data.get("recurrence_type"),
            data.get("repost_trigger"), data.get("repost_offset"), 
            data.get("timezone", "Europe/Budapest"), event_id
        ))
        await db.commit()

async def set_event_message(event_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE active_events SET message_id = ? WHERE event_id = ?", (message_id, event_id))
        await db.commit()

async def get_active_event(event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM active_events WHERE event_id = ?", (event_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None

async def set_event_status(event_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE active_events SET status = ? WHERE event_id = ?", (status, event_id))
        await db.commit()

async def get_all_active_events():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM active_events WHERE status = 'active'") as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

async def update_rsvp(event_id, user_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO rsvps (event_id, user_id, status)
            VALUES (?, ?, ?)
            ON CONFLICT(event_id, user_id) DO UPDATE SET status = excluded.status
        """, (event_id, user_id, status))
        await db.commit()

async def get_rsvps(event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, status FROM rsvps WHERE event_id = ?", (event_id,)) as cursor:
            return await cursor.fetchall()

async def delete_active_event(event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM active_events WHERE event_id = ?", (event_id,))
        await db.execute("DELETE FROM rsvps WHERE event_id = ?", (event_id,))
        await db.commit()
