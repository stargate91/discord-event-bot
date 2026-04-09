import asyncpg
import os
import json
import time
from utils.logger import log

_pool = None

async def set_pool(pool):
    global _pool
    _pool = pool

async def get_pool():
    global _pool
    if not _pool:
        raise Exception("Database pool is not initialized.")
    return _pool

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Table for storing all current events
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS active_events (
                event_id TEXT PRIMARY KEY,
                config_name TEXT,
                message_id BIGINT,
                channel_id BIGINT,
                start_time DOUBLE PRECISION,
                status TEXT DEFAULT 'active',
                title TEXT,
                description TEXT,
                image_urls TEXT,
                color TEXT,
                max_accepted INTEGER,
                ping_role BIGINT,
                end_time DOUBLE PRECISION,
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
                extra_data TEXT,
                guild_id TEXT
            )
        """)
        
        # Table for storing who is coming to which event
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rsvps (
                event_id TEXT,
                user_id BIGINT,
                status TEXT,
                joined_at DOUBLE PRECISION,
                PRIMARY KEY (event_id, user_id)
            )
        """)

        # Table for saving unfinished events (drafts)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS event_drafts (
                draft_id TEXT PRIMARY KEY,
                creator_id TEXT,
                title TEXT,
                data TEXT,
                updated_at DOUBLE PRECISION,
                guild_id TEXT
            )
        """)

        # Table for custom emoji/button sets
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS emoji_sets (
                set_id TEXT PRIMARY KEY,
                name TEXT,
                data TEXT,
                creator_id TEXT,
                guild_id TEXT
            )
        """)

async def create_active_event(guild_id, event_id, config_name, channel_id, start_time, data=None):
    if data is None:
        data = {}
    
    title = data.get("title")
    description = data.get("description")
    
    import random
    raw_images = data.get("image_urls")
    if isinstance(raw_images, list) and raw_images:
        image_urls = random.choice(raw_images)
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
    extra_data = data.get("extra_data")

    pool = await get_pool()
    await pool.execute("""
        INSERT INTO active_events (
            event_id, config_name, channel_id, start_time,
            title, description, image_urls, color, max_accepted, 
            ping_role, end_time, recurrence_type, repost_trigger, 
            repost_offset, timezone, creator_id,
            reminder_type, reminder_offset, reminder_sent,
            recurrence_limit, recurrence_count, icon_set, extra_data,
            guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24)
    """, 
        event_id, config_name, channel_id, start_time,
        title, description, image_urls,
        color, max_acc, ping_role,
        end_time, recurrence, repost_trigger,
        repost_offset, timezone, creator_id,
        reminder_type, reminder_offset, reminder_sent,
        recurrence_limit, recurrence_count, icon_set, extra_data,
        str(guild_id)
    )

async def update_active_events_metadata_bulk(event_ids, data):
    """Update only non-date metadata for multiple events at once."""
    if not event_ids:
        return
    
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
    
    icon_set = str(data.get("icon_set") or "standard")
    extra_data = data.get("extra_data") # Should be JSON string or dict

    pool = await get_pool()
    await pool.execute("""
        UPDATE active_events 
        SET title = $1, description = $2, image_urls = $3, color = $4, 
            max_accepted = $5, ping_role = $6, icon_set = $7, extra_data = $8
        WHERE event_id = ANY($9)
    """, 
        title, description, image_urls, color, 
        max_acc, ping_role, icon_set, extra_data,
        list(event_ids)
    )

async def update_event_status(event_id, status):
    """Simple update for event status (active, cancelled, postponed)."""
    pool = await get_pool()
    await pool.execute("UPDATE active_events SET status = $1 WHERE event_id = $2", status, event_id)

async def update_event_status_bulk(event_ids, status):
    """Update status for multiple events at once."""
    if not event_ids:
        return
    pool = await get_pool()
    await pool.execute("UPDATE active_events SET status = $1 WHERE event_id = ANY($2)", status, list(event_ids))

async def update_event_time(event_id, start_time):
    """Update the start time for a specific event."""
    pool = await get_pool()
    await pool.execute("UPDATE active_events SET start_time = $1 WHERE event_id = $2", start_time, event_id)

async def update_active_event(event_id, data):
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

    pool = await get_pool()
    await pool.execute("""
        UPDATE active_events SET 
            title = $1, description = $2, image_urls = $3, 
            color = $4, max_accepted = $5, ping_role = $6, 
            start_time = $7, end_time = $8, recurrence_type = $9, 
            repost_trigger = $10, repost_offset = $11, timezone = $12,
            creator_id = $13, reminder_type = $14, reminder_offset = $15,
            reminder_sent = $16, recurrence_limit = $17, recurrence_count = $18,
            icon_set = $19, extra_data = $20
        WHERE event_id = $21
    """, 
        title, description, image_urls, color, max_acc, ping_role, 
        start_time, end_time, recurrence, repost_trigger, repost_offset, timezone, 
        creator_id, reminder_type, reminder_offset, reminder_sent, 
        recurrence_limit, recurrence_count, icon_set, extra_data, 
        event_id
    )

async def set_event_message(event_id, message_id, guild_id=None):
    pool = await get_pool()
    if guild_id:
        await pool.execute("UPDATE active_events SET message_id = $1 WHERE event_id = $2 AND guild_id = $3", message_id, event_id, str(guild_id))
    else:
        await pool.execute("UPDATE active_events SET message_id = $1 WHERE event_id = $2", message_id, event_id)

async def mark_reminder_sent(event_id, guild_id=None):
    pool = await get_pool()
    if guild_id:
        await pool.execute("UPDATE active_events SET reminder_sent = 1 WHERE event_id = $1 AND guild_id = $2", event_id, str(guild_id))
    else:
        await pool.execute("UPDATE active_events SET reminder_sent = 1 WHERE event_id = $1", event_id)

async def get_event_rsvps(event_id):
    pool = await get_pool()
    rows = await pool.fetch("SELECT user_id, status FROM rsvps WHERE event_id = $1", event_id)
    return [{"user_id": dict(r)["user_id"], "status": dict(r)["status"]} for r in rows]

async def get_active_event(event_id, guild_id=None):
    pool = await get_pool()
    if guild_id:
        row = await pool.fetchrow("SELECT * FROM active_events WHERE event_id = $1 AND guild_id = $2", event_id, str(guild_id))
    else:
        row = await pool.fetchrow("SELECT * FROM active_events WHERE event_id = $1", event_id)
        
    if row:
        return dict(row)
    return None

async def set_event_status(event_id, status, guild_id=None):
    pool = await get_pool()
    if guild_id:
        await pool.execute("UPDATE active_events SET status = $1 WHERE event_id = $2 AND guild_id = $3", status, event_id, str(guild_id))
    else:
        await pool.execute("UPDATE active_events SET status = $1 WHERE event_id = $2", status, event_id)

async def get_all_active_events(guild_id=None):
    pool = await get_pool()
    if guild_id:
        rows = await pool.fetch("SELECT * FROM active_events WHERE status = 'active' AND guild_id = $1", str(guild_id))
    else:
        rows = await pool.fetch("SELECT * FROM active_events WHERE status = 'active'")
    return [dict(row) for row in rows]

async def get_active_events_by_config(config_name, guild_id=None):
    pool = await get_pool()
    if guild_id:
        rows = await pool.fetch(
            "SELECT * FROM active_events WHERE config_name = $1 AND status = 'active' AND guild_id = $2 ORDER BY start_time ASC",
            config_name, str(guild_id)
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM active_events WHERE config_name = $1 AND status = 'active' ORDER BY start_time ASC",
            config_name
        )
    return [dict(row) for row in rows]

async def get_active_event_count(guild_id=None):
    pool = await get_pool()
    if guild_id:
        val = await pool.fetchval("SELECT COUNT(*) FROM active_events WHERE status = 'active' AND guild_id = $1", str(guild_id))
    else:
        val = await pool.fetchval("SELECT COUNT(*) FROM active_events WHERE status = 'active'")
    return val if val else 0

async def update_rsvp(event_id, user_id, status):
    now = time.time()
    pool = await get_pool()
    await pool.execute("""
        INSERT INTO rsvps (event_id, user_id, status, joined_at)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT(event_id, user_id) DO UPDATE SET 
            status = EXCLUDED.status,
            joined_at = CASE WHEN rsvps.status != EXCLUDED.status THEN EXCLUDED.joined_at ELSE rsvps.joined_at END
    """, event_id, user_id, status, now)

async def get_rsvps_with_time(event_id):
    pool = await get_pool()
    rows = await pool.fetch("SELECT user_id, status, joined_at FROM rsvps WHERE event_id = $1 ORDER BY joined_at ASC", event_id)
    return rows

async def promote_next_waiting(event_id, waiting_status, target_status):
    pool = await get_pool()
    row = await pool.fetchrow("""
        SELECT user_id FROM rsvps 
        WHERE event_id = $1 AND status = $2 
        ORDER BY joined_at ASC LIMIT 1
    """, event_id, waiting_status)
    
    if row:
        user_id = dict(row)["user_id"]
        await pool.execute("UPDATE rsvps SET status = $1 WHERE event_id = $2 AND user_id = $3", target_status, event_id, user_id)
        return user_id
    return None

async def get_rsvps(event_id):
    pool = await get_pool()
    return await pool.fetch("SELECT user_id, status FROM rsvps WHERE event_id = $1", event_id)

async def delete_active_event(event_id, guild_id=None):
    pool = await get_pool()
    if guild_id:
        await pool.execute("DELETE FROM active_events WHERE event_id = $1 AND guild_id = $2", event_id, str(guild_id))
    else:
        await pool.execute("DELETE FROM active_events WHERE event_id = $1", event_id)
    await pool.execute("DELETE FROM rsvps WHERE event_id = $1", event_id)

async def save_draft(guild_id, draft_id, creator_id, title, data):
    data_json = json.dumps(data)
    now = time.time()
    pool = await get_pool()
    await pool.execute("""
        INSERT INTO event_drafts (draft_id, creator_id, title, data, updated_at, guild_id)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (draft_id) DO UPDATE SET
            creator_id = EXCLUDED.creator_id,
            title = EXCLUDED.title,
            data = EXCLUDED.data,
            updated_at = EXCLUDED.updated_at,
            guild_id = EXCLUDED.guild_id
    """, draft_id, str(creator_id), title or "Untitled Draft", data_json, now, str(guild_id))

async def get_user_drafts(guild_id, creator_id):
    pool = await get_pool()
    rows = await pool.fetch("SELECT draft_id, title, updated_at FROM event_drafts WHERE creator_id = $1 AND guild_id = $2 ORDER BY updated_at DESC", str(creator_id), str(guild_id))
    return [{"draft_id": dict(r)["draft_id"], "title": dict(r)["title"], "updated_at": dict(r)["updated_at"]} for r in rows]

async def get_draft(draft_id, guild_id=None):
    pool = await get_pool()
    if guild_id:
        row = await pool.fetchrow("SELECT data FROM event_drafts WHERE draft_id = $1 AND guild_id = $2", draft_id, str(guild_id))
    else:
        row = await pool.fetchrow("SELECT data FROM event_drafts WHERE draft_id = $1", draft_id)
        
    if row:
        return json.loads(dict(row)["data"])
    return None

async def delete_draft(draft_id, guild_id=None):
    pool = await get_pool()
    if guild_id:
        await pool.execute("DELETE FROM event_drafts WHERE draft_id = $1 AND guild_id = $2", draft_id, str(guild_id))
    else:
        await pool.execute("DELETE FROM event_drafts WHERE draft_id = $1", draft_id)

async def delete_all_user_drafts(guild_id, creator_id):
    pool = await get_pool()
    await pool.execute("DELETE FROM event_drafts WHERE creator_id = $1 AND guild_id = $2", str(creator_id), str(guild_id))

# --- Custom Emoji Sets ---

async def save_custom_emoji_set(guild_id, set_id, name, data, creator_id):
    data_json = json.dumps(data)
    pool = await get_pool()
    await pool.execute("""
        INSERT INTO emoji_sets (set_id, name, data, creator_id, guild_id)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (set_id) DO UPDATE SET
            name = EXCLUDED.name,
            data = EXCLUDED.data,
            creator_id = EXCLUDED.creator_id,
            guild_id = EXCLUDED.guild_id
    """, set_id, name, data_json, str(creator_id), str(guild_id))

async def get_all_custom_emoji_sets(guild_id=None):
    pool = await get_pool()
    if guild_id:
        rows = await pool.fetch("SELECT set_id, name, data, creator_id FROM emoji_sets WHERE guild_id = $1", str(guild_id))
    else:
        rows = await pool.fetch("SELECT set_id, name, data, creator_id FROM emoji_sets")
        
    return [{"set_id": dict(r)["set_id"], "name": dict(r)["name"], "data": json.loads(dict(r)["data"]), "creator_id": dict(r)["creator_id"]} for r in rows]

async def get_custom_emoji_set(set_id, guild_id=None):
    pool = await get_pool()
    if guild_id:
        row = await pool.fetchrow("SELECT set_id, name, data, creator_id FROM emoji_sets WHERE set_id = $1 AND guild_id = $2", set_id, str(guild_id))
    else:
        row = await pool.fetchrow("SELECT set_id, name, data, creator_id FROM emoji_sets WHERE set_id = $1", set_id)
        
    if row:
        r_dict = dict(row)
        return {"set_id": r_dict["set_id"], "name": r_dict["name"], "data": json.loads(r_dict["data"]), "creator_id": r_dict["creator_id"]}
    return None

async def delete_custom_emoji_set(set_id, guild_id=None):
    pool = await get_pool()
    if guild_id:
        await pool.execute("DELETE FROM emoji_sets WHERE set_id = $1 AND guild_id = $2", set_id, str(guild_id))
    else:
        await pool.execute("DELETE FROM emoji_sets WHERE set_id = $1", set_id)

async def clear_guild_data(guild_id):
    pool = await get_pool()
    # First find all active events for this guild to clean up RSVPs
    rows = await pool.fetch("SELECT event_id FROM active_events WHERE guild_id = $1", str(guild_id))
    event_ids = [dict(r)["event_id"] for r in rows]
    
    for ev_id in event_ids:
        await pool.execute("DELETE FROM rsvps WHERE event_id = $1", ev_id)
        
    await pool.execute("DELETE FROM active_events WHERE guild_id = $1", str(guild_id))
    await pool.execute("DELETE FROM event_drafts WHERE guild_id = $1", str(guild_id))
    await pool.execute("DELETE FROM emoji_sets WHERE guild_id = $1", str(guild_id))
