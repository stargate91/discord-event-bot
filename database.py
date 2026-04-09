import aiosqlite
import os
import json
import time

DB_PATH = os.path.join("data", "events.db")

async def init_db():
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
                creator_id TEXT,
                reminder_type TEXT DEFAULT 'none',
                reminder_offset TEXT DEFAULT '15m',
                reminder_sent INTEGER DEFAULT 0,
                recurrence_limit INTEGER DEFAULT 0,
                recurrence_count INTEGER DEFAULT 0
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rsvps (
                event_id TEXT,
                user_id INTEGER,
                status TEXT,
                PRIMARY KEY (event_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_drafts (
                draft_id TEXT PRIMARY KEY,
                creator_id TEXT,
                title TEXT,
                data TEXT,
                updated_at REAL
            )
        """)
        await db.commit()

async def create_active_event(event_id, config_name, channel_id, start_time, data=None):
    if data is None:
        data = {}
    
    # Standardized keys
    title = data.get("title")
    description = data.get("description")
    
    raw_images = data.get("image_urls")
    if isinstance(raw_images, list):
        image_urls = ",".join(str(u) for u in raw_images)
    else:
        image_urls = str(raw_images) if raw_images else None

    color = str(data.get("color") or "0x3498db")
    max_acc = int(data.get("max_accepted") or 0)
    
    import re
    ping_role_raw = str(data.get("ping_role") or "")
    ping_digits = re.sub(r"\D", "", ping_role_raw)
    ping_role = int(ping_digits) if ping_digits else 0
    
    end_time = data.get("end_time")
    recurrence = data.get("recurrence_type", "none")
    repost_trigger = data.get("repost_trigger", "before_start")
    repost_offset = data.get("repost_offset", "1h")
    timezone = data.get("timezone", "Europe/Budapest")
    creator_id = str(data.get("creator_id") or "System")
    
    reminder_type = data.get("reminder_type", "none")
    reminder_offset = data.get("reminder_offset", "15m")
    reminder_sent = int(data.get("reminder_sent") or 0)
    
    recurrence_limit = int(data.get("recurrence_limit") or 0)
    recurrence_count = int(data.get("recurrence_count") or 0)
    icon_set = str(data.get("icon_set") or "standard")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO active_events (
                event_id, config_name, channel_id, start_time,
                title, description, image_urls, color, max_accepted, 
                ping_role, end_time, recurrence_type, repost_trigger, 
                repost_offset, timezone, creator_id,
                reminder_type, reminder_offset, reminder_sent,
                recurrence_limit, recurrence_count, icon_set
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id, config_name, channel_id, start_time,
            title, description, image_urls,
            color, max_acc, ping_role,
            end_time, recurrence, repost_trigger,
            repost_offset, timezone, creator_id,
            reminder_type, reminder_offset, reminder_sent,
            recurrence_limit, recurrence_count, icon_set
        ))
        await db.commit()

async def update_active_event(event_id, data):
    # Standardized keys
    title = data.get("title")
    description = data.get("description")
    
    raw_images = data.get("image_urls")
    if isinstance(raw_images, list):
        image_urls = ",".join(str(u) for u in raw_images)
    else:
        image_urls = str(raw_images) if raw_images else None

    color = str(data.get("color") or "0x3498db")
    max_acc = int(data.get("max_accepted") or 0)
    
    import re
    ping_role_raw = str(data.get("ping_role") or "")
    ping_digits = re.sub(r"\D", "", ping_role_raw)
    ping_role = int(ping_digits) if ping_digits else 0
    
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    recurrence = data.get("recurrence_type", "none")
    repost_trigger = data.get("repost_trigger", "before_start")
    repost_offset = data.get("repost_offset", "1h")
    timezone = data.get("timezone", "Europe/Budapest")
    creator_id = str(data.get("creator_id") or "System")
    
    reminder_type = data.get("reminder_type", "none")
    reminder_offset = data.get("reminder_offset", "15m")
    reminder_sent = int(data.get("reminder_sent") or 0)
    
    recurrence_limit = int(data.get("recurrence_limit") or 0)
    recurrence_count = int(data.get("recurrence_count") or 0)
    icon_set = str(data.get("icon_set") or "standard")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE active_events SET 
                title = ?, description = ?, image_urls = ?, 
                color = ?, max_accepted = ?, ping_role = ?, 
                start_time = ?, end_time = ?, recurrence_type = ?, 
                repost_trigger = ?, repost_offset = ?, timezone = ?,
                creator_id = ?, reminder_type = ?, reminder_offset = ?,
                reminder_sent = ?, recurrence_limit = ?, recurrence_count = ?,
                icon_set = ?
            WHERE event_id = ?
        """, (
            title, description, image_urls,
            color, max_acc, ping_role,
            start_time, end_time, recurrence,
            repost_trigger, repost_offset, timezone, creator_id,
            reminder_type, reminder_offset, reminder_sent,
            recurrence_limit, recurrence_count, icon_set, event_id
        ))
        await db.commit()

async def set_event_message(event_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE active_events SET message_id = ? WHERE event_id = ?", (message_id, event_id))
        await db.commit()

async def mark_reminder_sent(event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE active_events SET reminder_sent = 1 WHERE event_id = ?", (event_id,))
        await db.commit()

async def get_event_rsvps(event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, status FROM rsvps WHERE event_id = ?", (event_id,)) as cursor:
            rows = await cursor.fetchall()
            return [{"user_id": r[0], "status": r[1]} for r in rows]

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

async def save_draft(draft_id, creator_id, title, data):
    import json
    data_json = json.dumps(data)
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO event_drafts (draft_id, creator_id, title, data, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (draft_id, str(creator_id), title or "Untitled Draft", data_json, now))
        await db.commit()

async def get_user_drafts(creator_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT draft_id, title, updated_at FROM event_drafts WHERE creator_id = ? ORDER BY updated_at DESC", (str(creator_id),)) as cursor:
            rows = await cursor.fetchall()
            return [{"draft_id": r[0], "title": r[1], "updated_at": r[2]} for r in rows]

async def get_draft(draft_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT data FROM event_drafts WHERE draft_id = ?", (draft_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None

async def delete_draft(draft_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM event_drafts WHERE draft_id = ?", (draft_id,))
        await db.commit()

async def delete_all_user_drafts(creator_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM event_drafts WHERE creator_id = ?", (str(creator_id),))
        await db.commit()
