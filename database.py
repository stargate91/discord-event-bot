import aiosqlite
import os
import json
import time

# This is where we save our database file
DB_PATH = os.path.join("data", "events.db")

async def init_db():
    # This function creates the tables if they don't exist yet
    async with aiosqlite.connect(DB_PATH) as db:
        # Table for storing all current events
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
                recurrence_count INTEGER DEFAULT 0,
                icon_set TEXT DEFAULT 'standard',
                extra_data TEXT
            )
        """)
        
        # Table for storing who is coming to which event
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rsvps (
                event_id TEXT,
                user_id INTEGER,
                status TEXT,
                joined_at REAL,
                PRIMARY KEY (event_id, user_id)
            )
        """)

        # Table for saving unfinished events (drafts)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_drafts (
                draft_id TEXT PRIMARY KEY,
                creator_id TEXT,
                title TEXT,
                data TEXT,
                updated_at REAL
            )
        """)

        # Table for custom emoji/button sets
        await db.execute("""
            CREATE TABLE IF NOT EXISTS emoji_sets (
                set_id TEXT PRIMARY KEY,
                name TEXT,
                data TEXT, -- JSON blob of the set config
                creator_id TEXT
            )
        """)
        await db.commit()

async def create_active_event(event_id, config_name, channel_id, start_time, data=None):
    # This function saves a brand new event to the database
    if data is None:
        data = {}
    
    # We get the info from the data dictionary
    title = data.get("title")
    description = data.get("description")
    
    # Images can be a list, so we turn them into a string with commas
    raw_images = data.get("image_urls")
    if isinstance(raw_images, list):
        image_urls = ",".join(str(u) for u in raw_images)
    else:
        image_urls = str(raw_images) if raw_images else None

    color = str(data.get("color") or "0x3498db")
    max_acc = int(data.get("max_accepted") or 0)
    
    # We use regex to make sure the role ID is just numbers
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
    extra_data = data.get("extra_data")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO active_events (
                event_id, config_name, channel_id, start_time,
                title, description, image_urls, color, max_accepted, 
                ping_role, end_time, recurrence_type, repost_trigger, 
                repost_offset, timezone, creator_id,
                reminder_type, reminder_offset, reminder_sent,
                recurrence_limit, recurrence_count, icon_set, extra_data
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id, config_name, channel_id, start_time,
            title, description, image_urls,
            color, max_acc, ping_role,
            end_time, recurrence, repost_trigger,
            repost_offset, timezone, creator_id,
            reminder_type, reminder_offset, reminder_sent,
            recurrence_limit, recurrence_count, icon_set, extra_data
        ))
        await db.commit()

async def update_active_event(event_id, data):
    # This function updates an event that already exists
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
    extra_data = data.get("extra_data")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE active_events SET 
                title = ?, description = ?, image_urls = ?, 
                color = ?, max_accepted = ?, ping_role = ?, 
                start_time = ?, end_time = ?, recurrence_type = ?, 
                repost_trigger = ?, repost_offset = ?, timezone = ?,
                creator_id = ?, reminder_type = ?, reminder_offset = ?,
                reminder_sent = ?, recurrence_limit = ?, recurrence_count = ?,
                icon_set = ?, extra_data = ?
            WHERE event_id = ?
        """, (
            title, description, image_urls,
            color, max_acc, ping_role,
            start_time, end_time, recurrence,
            repost_trigger, repost_offset, timezone, creator_id,
            reminder_type, reminder_offset, reminder_sent,
            recurrence_limit, recurrence_count, icon_set, extra_data, event_id
        ))
        await db.commit()

async def set_event_message(event_id, message_id):
    # Save the Discord message ID so we can find it later
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE active_events SET message_id = ? WHERE event_id = ?", (message_id, event_id))
        await db.commit()

async def mark_reminder_sent(event_id):
    # Mark that we already sent the reminder for this event
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE active_events SET reminder_sent = 1 WHERE event_id = ?", (event_id,))
        await db.commit()

async def get_event_rsvps(event_id):
    # Get everyone who clicked a button for this event
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, status FROM rsvps WHERE event_id = ?", (event_id,)) as cursor:
            rows = await cursor.fetchall()
            return [{"user_id": r[0], "status": r[1]} for r in rows]

async def get_active_event(event_id):
    # Get all info about one specific event
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM active_events WHERE event_id = ?", (event_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None

async def set_event_status(event_id, status):
    # Change status (for example from 'active' to something else)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE active_events SET status = ? WHERE event_id = ?", (status, event_id))
        await db.commit()

async def get_all_active_events():
    # Get every event that is currently active
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM active_events WHERE status = 'active'") as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

async def update_rsvp(event_id, user_id, status):
    # Save or update a user's reaction (Yes/No/Maybe etc)
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO rsvps (event_id, user_id, status, joined_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(event_id, user_id) DO UPDATE SET 
                status = excluded.status,
                joined_at = CASE WHEN rsvps.status != excluded.status THEN excluded.joined_at ELSE rsvps.joined_at END
        """, (event_id, user_id, status, now))
        await db.commit()

async def get_rsvps_with_time(event_id):
    # Get RSVP rows with timestamps
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, status, joined_at FROM rsvps WHERE event_id = ? ORDER BY joined_at ASC", (event_id,)) as cursor:
            return await cursor.fetchall()

async def promote_next_waiting(event_id, waiting_status, target_status):
    # Find the first person in the waiting list for a specific role and promote them
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT user_id FROM rsvps 
            WHERE event_id = ? AND status = ? 
            ORDER BY joined_at ASC LIMIT 1
        """, (event_id, waiting_status)) as cursor:
            row = await cursor.fetchone()
            if row:
                user_id = row[0]
                await db.execute("UPDATE rsvps SET status = ? WHERE event_id = ? AND user_id = ?", (target_status, event_id, user_id))
                await db.commit()
                return user_id
    return None

async def get_rsvps(event_id):
    # Just get the RSVP rows for an event
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, status FROM rsvps WHERE event_id = ?", (event_id,)) as cursor:
            return await cursor.fetchall()

async def delete_active_event(event_id):
    # Remove the event and all its RSVPs from the database
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM active_events WHERE event_id = ?", (event_id,))
        await db.execute("DELETE FROM rsvps WHERE event_id = ?", (event_id,))
        await db.commit()

async def save_draft(draft_id, creator_id, title, data):
    # Save a draft so the user can finish it later
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
    # Get a list of drafts created by a specific user
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT draft_id, title, updated_at FROM event_drafts WHERE creator_id = ? ORDER BY updated_at DESC", (str(creator_id),)) as cursor:
            rows = await cursor.fetchall()
            return [{"draft_id": r[0], "title": r[1], "updated_at": r[2]} for r in rows]

async def get_draft(draft_id):
    # Get the details of one specific draft
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT data FROM event_drafts WHERE draft_id = ?", (draft_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None

async def delete_draft(draft_id):
    # Delete a draft that is no longer needed
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM event_drafts WHERE draft_id = ?", (draft_id,))
        await db.commit()

async def delete_all_user_drafts(creator_id):
    # Clean up all drafts for a user
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM event_drafts WHERE creator_id = ?", (str(creator_id),))
        await db.commit()

# --- Custom Emoji Sets ---

async def save_custom_emoji_set(set_id, name, data, creator_id):
    # Save a new custom emoji set configuration
    import json
    data_json = json.dumps(data)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO emoji_sets (set_id, name, data, creator_id)
            VALUES (?, ?, ?, ?)
        """, (set_id, name, data_json, str(creator_id)))
        await db.commit()

async def get_all_custom_emoji_sets():
    # Fetch all custom emoji sets
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT set_id, name, data, creator_id FROM emoji_sets") as cursor:
            rows = await cursor.fetchall()
            return [{"set_id": r[0], "name": r[1], "data": json.loads(r[2]), "creator_id": r[3]} for r in rows]

async def get_custom_emoji_set(set_id):
    # Fetch a specific emoji set by ID
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT set_id, name, data, creator_id FROM emoji_sets WHERE set_id = ?", (set_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"set_id": row[0], "name": row[1], "data": json.loads(row[2]), "creator_id": row[3]}
            return None

async def delete_custom_emoji_set(set_id):
    # Remove a custom emoji set
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM emoji_sets WHERE set_id = ?", (set_id,))
        await db.commit()
