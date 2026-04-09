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
                timezone TEXT DEFAULT 'Europe/Budapest',
                creator_id TEXT
            )
        """)
        
        # Migration for existing databases
        new_columns = [
            ("title", "TEXT"), ("description", "TEXT"), ("image_urls", "TEXT"),
            ("color", "TEXT"), ("max_accepted", "INTEGER"), ("ping_role", "INTEGER"),
            ("end_time", "REAL"), ("recurrence_type", "TEXT"), ("repost_trigger", "TEXT"),
            ("repost_offset", "TEXT"), ("timezone", "TEXT DEFAULT 'Europe/Budapest'"),
            ("creator_id", "TEXT")
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
    
    # Standardize field names and types
    title = data.get("title")
    description = data.get("description")
    
    # Handle image_url(s) list or string
    raw_images = data.get("image_urls") or data.get("image_url")
    if isinstance(raw_images, list):
        image_urls = ",".join(str(u) for u in raw_images)
    else:
        image_urls = str(raw_images) if raw_images else None

    color = str(data.get("color") or "0x3498db")
    max_acc = int(data.get("max_accepted") or 0)
    ping = str(data.get("ping_role") or "")
    # Ensure ping role is just digits
    import re
    ping_digits = re.sub(r"\D", "", ping)
    ping_role = int(ping_digits) if ping_digits else 0
    
    end_time = data.get("end_time") or data.get("end")
    recurrence = data.get("recurrence_type", "none")
    repost_trigger = data.get("repost_trigger", "before_start")
    repost_offset = data.get("repost_offset", "1h")
    timezone = data.get("timezone", "Europe/Budapest")
    creator_id = str(data.get("creator_id") or "System")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO active_events (
                event_id, config_name, channel_id, start_time,
                title, description, image_urls, color, max_accepted, 
                ping_role, end_time, recurrence_type, repost_trigger, 
                repost_offset, timezone, creator_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id, config_name, channel_id, start_time,
            title, description, image_urls,
            color, max_acc, ping_role,
            end_time, recurrence, repost_trigger,
            repost_offset, timezone, creator_id
        ))
        await db.commit()

async def update_active_event(event_id, data):
    # Standardize field names and types
    title = data.get("title")
    description = data.get("description")
    
    # Handle image_url(s) list or string
    raw_images = data.get("image_urls") or data.get("image_url")
    if isinstance(raw_images, list):
        image_urls = ",".join(str(u) for u in raw_images)
    else:
        image_urls = str(raw_images) if raw_images else None

    color = str(data.get("color") or "0x3498db")
    max_acc = int(data.get("max_accepted") or 0)
    
    ping = str(data.get("ping_role") or "")
    import re
    ping_digits = re.sub(r"\D", "", ping)
    ping_role = int(ping_digits) if ping_digits else 0
    
    start_time = data.get("start_time")
    end_time = data.get("end_time") or data.get("end")
    recurrence = data.get("recurrence_type", "none")
    repost_trigger = data.get("repost_trigger", "before_start")
    repost_offset = data.get("repost_offset", "1h")
    timezone = data.get("timezone", "Europe/Budapest")
    creator_id = str(data.get("creator_id") or "System")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE active_events SET 
                title = ?, description = ?, image_urls = ?, 
                color = ?, max_accepted = ?, ping_role = ?, 
                start_time = ?, end_time = ?, recurrence_type = ?, 
                repost_trigger = ?, repost_offset = ?, timezone = ?,
                creator_id = ?
            WHERE event_id = ?
        """, (
            title, description, image_urls,
            color, max_acc, ping_role,
            start_time, end_time, recurrence,
            repost_trigger, repost_offset, timezone, creator_id, event_id
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
