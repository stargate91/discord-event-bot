import asyncpg
import os
import json
import time
import re
from utils.logger import log

_pool = None
DEFAULT_TIMEZONE = 'UTC'
MAX_EVENT_REMINDERS = 5

async def set_pool(pool):
    global _pool
    _pool = pool

async def get_pool():
    global _pool
    if not _pool:
        raise Exception("Database pool is not initialized.")
    return _pool


def normalize_reminder_offsets_for_store(data):
    """Up to MAX_EVENT_REMINDERS offset strings; empty if reminder_type is none."""
    rt = (data.get("reminder_type") or "none").strip().lower()
    if rt == "none":
        return []
    raw = data.get("reminder_offsets")
    if isinstance(raw, list):
        offs = [str(x).strip() for x in raw if str(x).strip()]
    else:
        one = str(data.get("reminder_offset") or "15m").strip()
        offs = [one] if one else []
    return offs[:MAX_EVENT_REMINDERS]


def normalize_reminder_message_for_store(data):
    """Optional shared reminder body (not from JSON file)."""
    m = data.get("reminder_message")
    if m is None:
        return None
    s = str(m).strip()
    return s if s else None


async def _migrate_legacy_reminders(conn):
    await conn.execute("""
        INSERT INTO event_reminders (event_id, slot_idx, offset_str, sent)
        SELECT event_id, 0,
               COALESCE(NULLIF(TRIM(reminder_offset), ''), '15m'),
               COALESCE(reminder_sent, 0)
        FROM active_events ae
        WHERE COALESCE(NULLIF(TRIM(reminder_type), ''), 'none') <> 'none'
        AND NOT EXISTS (SELECT 1 FROM event_reminders er WHERE er.event_id = ae.event_id)
    """)
    rows = await conn.fetch(
        "SELECT event_id, extra_data FROM active_events WHERE extra_data IS NOT NULL AND LENGTH(TRIM(extra_data)) > 0"
    )
    for r in rows:
        eid = r["event_id"]
        raw = r["extra_data"]
        try:
            ed = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(ed, dict):
                continue
            msg = (ed.get("custom_reminder_msg") or "").strip()
            if not msg:
                continue
            await conn.execute(
                """
                UPDATE active_events SET reminder_message = $1
                WHERE event_id = $2 AND (reminder_message IS NULL OR LENGTH(TRIM(reminder_message)) = 0)
                """,
                msg,
                eid,
            )
        except Exception as e:
            log.debug("migrate reminder_message %s: %s", eid, e)


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
                guild_id TEXT,
                temp_role_id BIGINT,
                use_temp_role BOOLEAN DEFAULT FALSE
            )
        """)
        
        for stmt in (
            "ALTER TABLE active_events ADD COLUMN IF NOT EXISTS temp_role_id BIGINT",
            "ALTER TABLE active_events ADD COLUMN IF NOT EXISTS use_temp_role BOOLEAN DEFAULT FALSE",
        ):
            try:
                await conn.execute(stmt)
            except Exception as e:
                log.debug("init_db optional ALTER skipped: %s", e)
        
        # Table for storing who is coming to which event
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rsvps (
                event_id TEXT,
                user_id BIGINT,
                status TEXT,
                joined_at DOUBLE PRECISION,
                attendance TEXT DEFAULT 'present',
                PRIMARY KEY (event_id, user_id)
            )
        """)

        # Table for saving unfinished events (drafts)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS event_drafts (
                draft_id TEXT PRIMARY KEY,
                creator_id TEXT,
                title TEXT,
                data JSONB,
                updated_at DOUBLE PRECISION,
                guild_id TEXT
            )
        """)

        # Table for custom emoji/button sets per guild
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_emoji_sets (
                guild_id TEXT,
                set_id TEXT,
                name TEXT,
                data JSONB,
                PRIMARY KEY (guild_id, set_id)
            )
        """)

        # Table for per-guild translation overrides
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_translations (
                guild_id TEXT,
                key TEXT,
                value TEXT,
                PRIMARY KEY (guild_id, key)
            )
        """)

        # Table for per-guild configuration/defaults
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id TEXT,
                key TEXT,
                value TEXT,
                PRIMARY KEY (guild_id, key)
            )
        """)

        # Table for global bot settings (Owner only)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS global_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS event_reminders (
                event_id TEXT NOT NULL,
                slot_idx SMALLINT NOT NULL,
                offset_str TEXT NOT NULL,
                sent INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (event_id, slot_idx),
                CHECK (slot_idx >= 0 AND slot_idx < 5)
            )
        """)

        try:
            await conn.execute(
                "ALTER TABLE active_events ADD COLUMN IF NOT EXISTS reminder_message TEXT"
            )
        except Exception as e:
            log.debug("init_db reminder_message column: %s", e)

        await _migrate_legacy_reminders(conn)

        # Table for global emoji sets (available to all guilds)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS global_emoji_sets (
                set_id TEXT PRIMARY KEY,
                name TEXT,
                data TEXT
            )
        """)

async def get_event_reminders(event_id):
    pool = await get_pool()
    return await pool.fetch(
        """
        SELECT slot_idx, offset_str, sent
        FROM event_reminders
        WHERE event_id = $1
        ORDER BY slot_idx ASC
        """,
        event_id,
    )


async def replace_event_reminders(event_id, offsets):
    """Replace reminder slots; preserve sent=1 when offset at same index unchanged."""
    offs = [str(o).strip() for o in offsets if str(o).strip()][:MAX_EVENT_REMINDERS]
    pool = await get_pool()
    old_rows = await get_event_reminders(event_id)
    old = {r["slot_idx"]: (r["offset_str"], int(r["sent"] or 0)) for r in old_rows}
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM event_reminders WHERE event_id = $1", event_id)
        for idx, off in enumerate(offs):
            prev = old.get(idx)
            sent = 1 if prev and prev[0] == off and prev[1] == 1 else 0
            await conn.execute(
                """
                INSERT INTO event_reminders (event_id, slot_idx, offset_str, sent)
                VALUES ($1, $2, $3, $4)
                """,
                event_id,
                idx,
                off,
                sent,
            )
    if not offs:
        await pool.execute(
            "UPDATE active_events SET reminder_sent = 0 WHERE event_id = $1", event_id
        )
        return
    pending = await pool.fetchval(
        "SELECT COUNT(*) FROM event_reminders WHERE event_id = $1 AND sent = 0",
        event_id,
    )
    await pool.execute(
        "UPDATE active_events SET reminder_sent = $1 WHERE event_id = $2",
        1 if pending == 0 else 0,
        event_id,
    )


async def mark_reminder_slot_sent(event_id, slot_idx):
    pool = await get_pool()
    await pool.execute(
        "UPDATE event_reminders SET sent = 1 WHERE event_id = $1 AND slot_idx = $2",
        event_id,
        slot_idx,
    )
    pending = await pool.fetchval(
        "SELECT COUNT(*) FROM event_reminders WHERE event_id = $1 AND sent = 0",
        event_id,
    )
    if pending == 0:
        await pool.execute(
            "UPDATE active_events SET reminder_sent = 1 WHERE event_id = $1", event_id
        )


async def mark_all_reminder_slots_sent(event_id):
    pool = await get_pool()
    await pool.execute("UPDATE event_reminders SET sent = 1 WHERE event_id = $1", event_id)
    await pool.execute(
        "UPDATE active_events SET reminder_sent = 1 WHERE event_id = $1", event_id
    )


async def check_config_exists(guild_id, config_name):
    """Returns True if a config_name already exists in active_events for this guild."""
    pool = await get_pool()
    row = await pool.fetchrow("SELECT 1 FROM active_events WHERE guild_id = $1 AND config_name = $2 LIMIT 1", str(guild_id), config_name)
    return row is not None

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
    
    ping_role_raw = str(data.get("ping_role") or "")
    ping_digits = re.sub(r"\D", "", ping_role_raw)
    ping_role = int(ping_digits) if ping_digits else 0
    
    end_time = data.get("end_time")
    recurrence = data.get("recurrence_type", "none")
    repost_trigger = data.get("repost_trigger", "before_start")
    repost_offset = data.get("repost_offset", "1h")
    timezone = data.get("timezone", DEFAULT_TIMEZONE)
    creator_id = str(data.get("creator_id") or "System")
    
    reminder_type = data.get("reminder_type", "none")
    roffs = normalize_reminder_offsets_for_store(data)
    reminder_offset = roffs[0] if roffs else str(data.get("reminder_offset", "15m"))
    reminder_sent = int(data.get("reminder_sent") or 0)
    reminder_message = normalize_reminder_message_for_store(data)

    recurrence_limit = int(data.get("recurrence_limit") or 0)
    recurrence_count = int(data.get("recurrence_count") or 0)
    icon_set = str(data.get("icon_set") or "standard")
    extra_data = data.get("extra_data")

    temp_role_id = int(data.get("temp_role_id") or 0)
    use_temp_role = bool(data.get("use_temp_role", False))

    pool = await get_pool()
    await pool.execute("""
        INSERT INTO active_events (
            event_id, config_name, channel_id, start_time,
            title, description, image_urls, color, max_accepted,
            ping_role, end_time, recurrence_type, repost_trigger,
            repost_offset, timezone, creator_id,
            reminder_type, reminder_offset, reminder_sent, reminder_message,
            recurrence_limit, recurrence_count, icon_set, extra_data,
            guild_id, temp_role_id, use_temp_role
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27
        )
    """,
        event_id, config_name, channel_id, start_time,
        title, description, image_urls, color, max_acc,
        ping_role, end_time, recurrence, repost_trigger,
        repost_offset, timezone, creator_id,
        reminder_type, reminder_offset, reminder_sent, reminder_message,
        recurrence_limit, recurrence_count, icon_set, extra_data,
        str(guild_id), temp_role_id, use_temp_role,
    )
    await replace_event_reminders(event_id, roffs)
    return event_id

async def get_active_events(guild_id=None):
    pool = await get_pool()
    if guild_id:
        return await pool.fetch("SELECT * FROM active_events WHERE guild_id = $1", str(guild_id))
    return await pool.fetch("SELECT * FROM active_events")

async def get_all_active_events(guild_id=None):
    """Alias for get_active_events() used during bot startup and autocomplete."""
    return await get_active_events(guild_id)

async def get_active_events_by_config(config_name, guild_id):
    """Fetch all active events belonging to a specific series/configuration."""
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM active_events WHERE config_name = $1 AND guild_id = $2", config_name, str(guild_id))

async def get_active_event(event_id, guild_id=None):
    pool = await get_pool()
    if guild_id:
        return await pool.fetchrow("SELECT * FROM active_events WHERE event_id = $1 AND guild_id = $2", event_id, str(guild_id))
    return await pool.fetchrow("SELECT * FROM active_events WHERE event_id = $1", event_id)

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
    
    ping_role_raw = str(data.get("ping_role") or "")
    ping_digits = re.sub(r"\D", "", ping_role_raw)
    ping_role = int(ping_digits) if ping_digits else 0
    
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    status = data.get("status", "active")
    recurrence = data.get("recurrence_type", "none")
    repost_trigger = data.get("repost_trigger", "before_start")
    repost_offset = data.get("repost_offset", "1h")
    timezone = data.get("timezone", DEFAULT_TIMEZONE)
    creator_id = str(data.get("creator_id") or "System")
    
    reminder_type = data.get("reminder_type", "none")
    roffs = normalize_reminder_offsets_for_store(data)
    reminder_offset = roffs[0] if roffs else str(data.get("reminder_offset", "15m"))
    reminder_sent = int(data.get("reminder_sent") or 0)

    recurrence_limit = int(data.get("recurrence_limit") or 0)
    recurrence_count = int(data.get("recurrence_count") or 0)
    icon_set = str(data.get("icon_set") or "standard")
    extra_data = data.get("extra_data")

    temp_role_id = int(data.get("temp_role_id") or 0)
    use_temp_role = bool(data.get("use_temp_role", False))

    pool = await get_pool()
    if "reminder_message" in data:
        reminder_message = normalize_reminder_message_for_store(data)
    else:
        row = await pool.fetchrow(
            "SELECT reminder_message FROM active_events WHERE event_id = $1", event_id
        )
        reminder_message = row["reminder_message"] if row else None

    await pool.execute(
        """
        UPDATE active_events SET
            title = $1, description = $2, image_urls = $3,
            color = $4, max_accepted = $5, ping_role = $6,
            start_time = $7, end_time = $8, status = $9, recurrence_type = $10,
            repost_trigger = $11, repost_offset = $12, timezone = $13,
            creator_id = $14, reminder_type = $15, reminder_offset = $16,
            reminder_sent = $17, reminder_message = $18, recurrence_limit = $19, recurrence_count = $20,
            icon_set = $21, extra_data = $22,
            temp_role_id = $23, use_temp_role = $24
        WHERE event_id = $25
        """,
        title,
        description,
        image_urls,
        color,
        max_acc,
        ping_role,
        start_time,
        end_time,
        status,
        recurrence,
        repost_trigger,
        repost_offset,
        timezone,
        creator_id,
        reminder_type,
        reminder_offset,
        reminder_sent,
        reminder_message,
        recurrence_limit,
        recurrence_count,
        icon_set,
        extra_data,
        temp_role_id,
        use_temp_role,
        event_id,
    )

    if any(
        k in data
        for k in ("reminder_offsets", "reminder_offset", "reminder_type", "reminder_message")
    ):
        await replace_event_reminders(event_id, roffs)

async def update_event_status(event_id, status):
    """Simplified status update for cancellation or postponement."""
    pool = await get_pool()
    await pool.execute("UPDATE active_events SET status = $1 WHERE event_id = $2", status, event_id)

async def update_event_status_bulk(event_ids, status):
    """Update status for multiple events at once."""
    pool = await get_pool()
    await pool.execute("UPDATE active_events SET status = $1 WHERE event_id = ANY($2)", status, event_ids)

async def update_event_time(event_id, start_time):
    """Set a new start time for an event (e.g. postpone). Resets reminder so it can fire for the new slot."""
    pool = await get_pool()
    await pool.execute(
        "UPDATE active_events SET start_time = $1, reminder_sent = 0 WHERE event_id = $2",
        start_time,
        event_id,
    )
    await pool.execute(
        "UPDATE event_reminders SET sent = 0 WHERE event_id = $1",
        event_id,
    )

async def set_event_status(event_id, status):
    """Another alias for update_event_status used by scheduler."""
    await update_event_status(event_id, status)

async def update_active_events_metadata_bulk(event_ids, data):
    """Updates metadata (like extra_data) for multiple events, typically during bulk edit."""
    pool = await get_pool()
    extra_json = json.dumps(data.get("extra_data") or {}) if isinstance(data.get("extra_data"), dict) else data.get("extra_data")
    
    await pool.execute("""
        UPDATE active_events SET 
            title = $1, description = $2, image_urls = $3, 
            color = $4, max_accepted = $5, icon_set = $6, extra_data = $7,
            temp_role_id = $8, use_temp_role = $9
        WHERE event_id = ANY($10)
    """, 
        data.get("title"), data.get("description"), data.get("image_urls"),
        data.get("color"), data.get("max_accepted"), data.get("icon_set"), 
        extra_json, data.get("temp_role_id"), data.get("use_temp_role", False),
        event_ids
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

async def save_guild_setting(guild_id: int, key: str, value: str):
    """Upsert a guild setting with robust logging and PK enforcement."""
    pool = await get_pool()
    log.info(f"DB: Saving guild setting - GID: {guild_id} ({type(guild_id)}), Key: {key}, Val: {value}")
    try:
        await pool.execute('''
            INSERT INTO guild_settings (guild_id, key, value) 
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, key) DO UPDATE SET value = EXCLUDED.value
        ''', str(guild_id), key, str(value))
        log.info(f"DB: Successfully saved {key}")
    except Exception as e:
        log.error(f"DB ERROR saving guild setting {key}: {e}")
        # Re-raise to ensure calling logic knows it failed
        raise e

async def get_guild_setting(guild_id: int, key: str, default=None):
    """Get a specific guild setting."""
    pool = await get_pool()
    row = await pool.fetchrow("SELECT value FROM guild_settings WHERE guild_id = $1 AND key = $2", str(guild_id), key)
    log.info(f"DB: Get guild setting - GID: {guild_id}, Key: {key}, Found: {row is not None}")
    if row:
        return row['value']
    return default

async def get_all_guild_settings(guild_id: int):
    """Get all settings for a guild."""
    pool = await get_pool()
    rows = await pool.fetch("SELECT key, value FROM guild_settings WHERE guild_id = $1", str(guild_id))
    return {r['key']: r['value'] for r in rows}

async def save_global_setting(key: str, value: str):
    """Upsert a global setting."""
    pool = await get_pool()
    await pool.execute('''
        INSERT INTO global_settings (key, value) 
        VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    ''', key, str(value))

async def get_global_setting(key: str, default=None):
    """Get a specific global setting."""
    pool = await get_pool()
    row = await pool.fetchrow("SELECT value FROM global_settings WHERE key = $1", key)
    if row:
        return row['value']
    return default

async def save_global_emoji_set(set_id: str, name: str, data):
    """Upsert a global emoji set."""
    if isinstance(data, (dict, list)):
        import json
        data = json.dumps(data)
    
    pool = await get_pool()
    await pool.execute("""
        INSERT INTO global_emoji_sets (set_id, name, data)
        VALUES ($1, $2, $3)
        ON CONFLICT (set_id) DO UPDATE SET name = EXCLUDED.name, data = EXCLUDED.data
    """, set_id, name, data)

async def get_all_global_emoji_sets():
    """Get all global emoji sets."""
    pool = await get_pool()
    return await pool.fetch("SELECT set_id, name, data FROM global_emoji_sets")

async def delete_global_emoji_set(set_id: str):
    """Delete a global emoji set."""
    pool = await get_pool()
    await pool.execute("DELETE FROM global_emoji_sets WHERE set_id = $1", set_id)

async def clear_global_emoji_sets():
    """Delete all global emoji sets."""
    pool = await get_pool()
    await pool.execute("DELETE FROM global_emoji_sets")

async def get_rsvps(event_id):
    pool = await get_pool()
    return await pool.fetch("SELECT user_id, status FROM rsvps WHERE event_id = $1", event_id)

async def get_event_rsvps(event_id):
    """Alias for get_rsvps used by scheduler."""
    return await get_rsvps(event_id)

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

async def delete_active_event(event_id, guild_id=None):
    pool = await get_pool()
    await pool.execute("DELETE FROM event_reminders WHERE event_id = $1", event_id)
    await pool.execute("DELETE FROM rsvps WHERE event_id = $1", event_id)
    if guild_id:
        await pool.execute("DELETE FROM active_events WHERE event_id = $1 AND guild_id = $2", event_id, str(guild_id))
    else:
        await pool.execute("DELETE FROM active_events WHERE event_id = $1", event_id)

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
            updated_at = EXCLUDED.updated_at
    """, draft_id, creator_id, title, data_json, now, str(guild_id))

async def get_draft(draft_id, guild_id=None):
    pool = await get_pool()
    if guild_id:
        return await pool.fetchrow("SELECT * FROM event_drafts WHERE draft_id = $1 AND guild_id = $2", draft_id, str(guild_id))
    return await pool.fetchrow("SELECT * FROM event_drafts WHERE draft_id = $1", draft_id)

async def delete_draft(draft_id, guild_id=None):
    pool = await get_pool()
    if guild_id:
        await pool.execute("DELETE FROM event_drafts WHERE draft_id = $1 AND guild_id = $2", draft_id, str(guild_id))
    else:
        await pool.execute("DELETE FROM event_drafts WHERE draft_id = $1", draft_id)

async def get_user_drafts(guild_id, user_id):
    """All drafts for a user in a guild (creator_id stored as string)."""
    pool = await get_pool()
    return await pool.fetch(
        """
        SELECT draft_id, title, updated_at
        FROM event_drafts
        WHERE guild_id = $1 AND creator_id = $2
        ORDER BY updated_at DESC
        """,
        str(guild_id),
        str(user_id),
    )

async def delete_all_user_drafts(guild_id, user_id):
    """Remove every draft owned by the user in this guild."""
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM event_drafts WHERE guild_id = $1 AND creator_id = $2",
        str(guild_id),
        str(user_id),
    )

async def save_emoji_set(guild_id, set_id, name, data):
    data_json = json.dumps(data)
    pool = await get_pool()
    await pool.execute("""
        INSERT INTO guild_emoji_sets (guild_id, set_id, name, data)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (guild_id, set_id) DO UPDATE SET
            name = EXCLUDED.name,
            data = EXCLUDED.data
    """, str(guild_id), set_id, name, data_json)

async def get_emoji_sets(guild_id):
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM guild_emoji_sets WHERE guild_id = $1", str(guild_id))

async def get_all_custom_emoji_sets():
    """Fetch all guild-specific emoji sets."""
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM guild_emoji_sets")

async def delete_emoji_set(guild_id, set_id):
    pool = await get_pool()
    await pool.execute("DELETE FROM guild_emoji_sets WHERE guild_id = $1 AND set_id = $2", str(guild_id), set_id)

async def save_guild_translation(guild_id, key, value):
    pool = await get_pool()
    await pool.execute("""
        INSERT INTO guild_translations (guild_id, key, value)
        VALUES ($1, $2, $3)
        ON CONFLICT (guild_id, key) DO UPDATE SET value = EXCLUDED.value
    """, str(guild_id), key, value)

async def get_guild_translations(guild_id):
    pool = await get_pool()
    rows = await pool.fetch("SELECT key, value FROM guild_translations WHERE guild_id = $1", str(guild_id))
    return {r["key"]: r["value"] for r in rows}

async def delete_guild_translation(guild_id, key):
    pool = await get_pool()
    await pool.execute("DELETE FROM guild_translations WHERE guild_id = $1 AND key = $2", str(guild_id), key)

async def reset_guild_data(guild_id):
    """Remove all bot-owned data for a guild (events, RSVPs, drafts, emojis, settings, translations)."""
    pool = await get_pool()
    gid = str(guild_id)
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM event_reminders WHERE event_id IN (SELECT event_id FROM active_events WHERE guild_id = $1)",
            gid,
        )
        await conn.execute(
            "DELETE FROM rsvps WHERE event_id IN (SELECT event_id FROM active_events WHERE guild_id = $1)",
            gid,
        )
        await conn.execute("DELETE FROM active_events WHERE guild_id = $1", gid)
        await conn.execute("DELETE FROM event_drafts WHERE guild_id = $1", gid)
        await conn.execute("DELETE FROM guild_emoji_sets WHERE guild_id = $1", gid)
        await conn.execute("DELETE FROM guild_settings WHERE guild_id = $1", gid)
        await conn.execute("DELETE FROM guild_translations WHERE guild_id = $1", gid)

async def get_global_stats():
    """Returns bot-wide statistics for the Master Hub."""
    pool = await get_pool()
    guild_count = await pool.fetchval("SELECT COUNT(DISTINCT guild_id) FROM active_events")
    event_count = await pool.fetchval("SELECT COUNT(*) FROM active_events")
    rsvp_count = await pool.fetchval("SELECT COUNT(*) FROM rsvps")
    
    return {
        "guilds": guild_count or 0,
        "events": event_count or 0,
        "rsvps": rsvp_count or 0
    }
