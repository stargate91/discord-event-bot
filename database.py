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


def normalize_reminders_for_store(data):
    """Parses offsets and messages into a list of dict objects for DB storage."""
    if data.get("lobby_mode"):
        return []
    rt = (data.get("reminder_type") or "none").strip().lower()
    if rt == "none":
        return []
        
    raw_offsets = data.get("reminder_offsets") or []
    if not isinstance(raw_offsets, list):
        one = str(data.get("reminder_offset") or "15m").strip()
        raw_offsets = [one] if one else []
        
    raw_msgs = data.get("reminder_messages") or []
    if not isinstance(raw_msgs, list):
        raw_msgs = []

    out = []
    for idx, full_offset in enumerate(raw_offsets[:MAX_EVENT_REMINDERS]):
        # Smart logic: "15m,tank" -> target is tank, method is ping
        # "15m,dm" -> method is dm, target is coming
        parts = [p.strip() for p in str(full_offset).split(",")]
        off_str = parts[0]
        
        # Default values
        method = "ping"
        target = "coming"
        
        if len(parts) == 2:
            p2 = parts[1].lower()
            if p2 in ("dm", "ping", "both", "none"):
                method = p2
            else:
                target = parts[1]
        elif len(parts) >= 3:
            method = parts[1] or "ping"
            target = parts[2] or "coming"
        
        cmsg = raw_msgs[idx] if idx < len(raw_msgs) else None
        if cmsg:
            cmsg = str(cmsg).strip() or None
            
        out.append({
            "offset_str": off_str,
            "method": method,
            "target": target,
            "custom_message": cmsg
        })
    return out


def normalize_reminder_message_for_store(data):
    """Optional shared reminder body (not from JSON file)."""
    m = data.get("reminder_message")
    if m is None:
        return None
    s = str(m).strip()
    return s if s else None


def normalize_rsvp_allowed_role_ids_value(raw):
    """
    Comma-separated Discord role IDs (digits only per segment).
    Empty string = any member who can see the message may RSVP (OR: user has any listed role).
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    seen = set()
    out = []
    for part in s.split(","):
        digits = re.sub(r"\D", "", part.strip())
        if digits and digits not in seen:
            seen.add(digits)
            out.append(digits)
    return ",".join(out)


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
                method TEXT,
                custom_message TEXT,
                sent INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (event_id, slot_idx),
                CHECK (slot_idx >= 0 AND slot_idx < 5)
            )
        """)

        # Migration for existing event_reminders table
        for col_name, dt in [("method", "TEXT"), ("custom_message", "TEXT"), ("target", "TEXT DEFAULT 'coming'")]:
            try:
                await conn.execute(f"ALTER TABLE event_reminders ADD COLUMN IF NOT EXISTS {col_name} {dt}")
            except Exception as e:
                log.debug(f"init_db event_reminders {col_name} column: {e}")

        try:
            await conn.execute(
                "ALTER TABLE active_events ADD COLUMN IF NOT EXISTS reminder_message TEXT"
            )
        except Exception as e:
            log.debug("init_db reminder_message column: %s", e)

        try:
            await conn.execute(
                "ALTER TABLE active_events ADD COLUMN IF NOT EXISTS rsvp_allowed_role_ids TEXT DEFAULT ''"
            )
        except Exception as e:
            log.debug("init_db rsvp_allowed_role_ids column: %s", e)

        for lobby_sql in (
            "ALTER TABLE active_events ADD COLUMN IF NOT EXISTS lobby_mode BOOLEAN DEFAULT FALSE",
            "ALTER TABLE active_events ADD COLUMN IF NOT EXISTS lobby_expires_at DOUBLE PRECISION",
            "ALTER TABLE active_events ADD COLUMN IF NOT EXISTS lobby_remind_on_fill BOOLEAN DEFAULT TRUE",
        ):
            try:
                await conn.execute(lobby_sql)
            except Exception as e:
                log.debug("init_db lobby column: %s", e)

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
        SELECT slot_idx, offset_str, method, target, custom_message, sent
        FROM event_reminders
        WHERE event_id = $1
        ORDER BY slot_idx ASC
        """,
        event_id,
    )


async def replace_event_reminders(event_id, reminders):
    """
    Replace reminder slots.
    reminders: list of dicts with 'offset_str', 'method', 'custom_message'
    """
    rems = reminders[:MAX_EVENT_REMINDERS]
    pool = await get_pool()
    old_rows = await get_event_reminders(event_id)
    # Use offset_str as key to preserve 'sent' status if offset doesn't change
    old = {r["slot_idx"]: (r["offset_str"], int(r["sent"] or 0)) for r in old_rows}
    
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM event_reminders WHERE event_id = $1", event_id)
        for idx, r in enumerate(rems):
            off = r.get("offset_str", "15m")
            method = r.get("method", "ping")
            target = r.get("target", "coming")
            msg = r.get("custom_message")
            
            prev = old.get(idx)
            sent = 1 if prev and prev[0] == off and prev[1] == 1 else 0
            
            await conn.execute(
                """
                INSERT INTO event_reminders (event_id, slot_idx, offset_str, method, target, custom_message, sent)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                event_id,
                idx,
                off,
                method,
                target,
                msg,
                sent,
            )
            
    if not rems:
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
    rems = normalize_reminders_for_store(data)
    reminder_offset = rems[0]["offset_str"] if rems else str(data.get("reminder_offset", "15m"))
    reminder_sent = int(data.get("reminder_sent") or 0)
    reminder_message = normalize_reminder_message_for_store(data)

    recurrence_limit = int(data.get("recurrence_limit") or 0)
    recurrence_count = int(data.get("recurrence_count") or 0)
    icon_set = str(data.get("icon_set") or "standard")
    extra_data = data.get("extra_data")

    temp_role_id = int(data.get("temp_role_id") or 0)
    use_temp_role = bool(data.get("use_temp_role", False))
    rsvp_allowed_role_ids = normalize_rsvp_allowed_role_ids_value(data.get("rsvp_allowed_role_ids"))
    lobby_mode = bool(data.get("lobby_mode", False))
    lobby_expires_at = data.get("lobby_expires_at")
    lobby_remind_on_fill = bool(data.get("lobby_remind_on_fill", True))

    pool = await get_pool()
    await pool.execute("""
        INSERT INTO active_events (
            event_id, config_name, channel_id, start_time,
            title, description, image_urls, color, max_accepted,
            ping_role, end_time, recurrence_type, repost_trigger,
            repost_offset, timezone, creator_id,
            reminder_type, reminder_offset, reminder_sent, reminder_message,
            recurrence_limit, recurrence_count, icon_set, extra_data,
            guild_id, temp_role_id, use_temp_role, rsvp_allowed_role_ids,
            lobby_mode, lobby_expires_at, lobby_remind_on_fill
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31
        )
    """,
        event_id, config_name, channel_id, start_time,
        title, description, image_urls, color, max_acc,
        ping_role, end_time, recurrence, repost_trigger,
        repost_offset, timezone, creator_id,
        reminder_type, reminder_offset, reminder_sent, reminder_message,
        recurrence_limit, recurrence_count, icon_set, extra_data,
        str(guild_id), temp_role_id, use_temp_role, rsvp_allowed_role_ids,
        lobby_mode, lobby_expires_at, lobby_remind_on_fill,
    )
    await replace_event_reminders(event_id, normalize_reminders_for_store(data))
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
    rems = normalize_reminders_for_store(data)
    reminder_offset = rems[0]["offset_str"] if rems else str(data.get("reminder_offset", "15m"))
    reminder_sent = int(data.get("reminder_sent") or 0)

    recurrence_limit = int(data.get("recurrence_limit") or 0)
    recurrence_count = int(data.get("recurrence_count") or 0)
    icon_set = str(data.get("icon_set") or "standard")
    extra_data = data.get("extra_data")

    temp_role_id = int(data.get("temp_role_id") or 0)
    use_temp_role = bool(data.get("use_temp_role", False))

    pool = await get_pool()
    need_row = (
        "reminder_message" not in data
        or "rsvp_allowed_role_ids" not in data
        or "lobby_mode" not in data
        or "lobby_expires_at" not in data
        or "lobby_remind_on_fill" not in data
    )
    row_m = None
    if need_row:
        row_m = await pool.fetchrow(
            """
            SELECT reminder_message, rsvp_allowed_role_ids,
                   lobby_mode, lobby_expires_at, lobby_remind_on_fill
            FROM active_events WHERE event_id = $1
            """,
            event_id,
        )

    if "reminder_message" in data:
        reminder_message = normalize_reminder_message_for_store(data)
    else:
        reminder_message = row_m["reminder_message"] if row_m else None

    if "rsvp_allowed_role_ids" in data:
        rsvp_allowed_role_ids = normalize_rsvp_allowed_role_ids_value(data.get("rsvp_allowed_role_ids"))
    else:
        raw_r = row_m["rsvp_allowed_role_ids"] if row_m else ""
        rsvp_allowed_role_ids = normalize_rsvp_allowed_role_ids_value(raw_r)

    if "lobby_mode" in data:
        lobby_mode = bool(data.get("lobby_mode"))
    else:
        lobby_mode = bool(row_m["lobby_mode"]) if row_m and row_m["lobby_mode"] is not None else False

    if "lobby_expires_at" in data:
        lobby_expires_at = data.get("lobby_expires_at")
    else:
        lobby_expires_at = row_m["lobby_expires_at"] if row_m else None

    if "lobby_remind_on_fill" in data:
        lobby_remind_on_fill = bool(data.get("lobby_remind_on_fill", True))
    else:
        v = row_m["lobby_remind_on_fill"] if row_m else None
        lobby_remind_on_fill = bool(v) if v is not None else True

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
            temp_role_id = $23, use_temp_role = $24, rsvp_allowed_role_ids = $25,
            lobby_mode = $26, lobby_expires_at = $27, lobby_remind_on_fill = $28
        WHERE event_id = $29
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
        rsvp_allowed_role_ids,
        lobby_mode,
        lobby_expires_at,
        lobby_remind_on_fill,
        event_id,
    )

    if any(
        k in data
        for k in ("reminder_offsets", "reminder_offset", "reminder_type", "reminder_message", "reminder_messages")
    ):
        await replace_event_reminders(event_id, normalize_reminders_for_store(data))

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


async def set_lobby_start_time(event_id, start_ts):
    """Lobby: set start_time when full, or NULL to reopen. Clears reminder slots for a clean slate."""
    pool = await get_pool()
    await pool.execute(
        "UPDATE active_events SET start_time = $1 WHERE event_id = $2",
        start_ts,
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
    rsvp_allowed_role_ids = normalize_rsvp_allowed_role_ids_value(data.get("rsvp_allowed_role_ids"))

    await pool.execute("""
        UPDATE active_events SET 
            title = $1, description = $2, image_urls = $3, 
            color = $4, max_accepted = $5, icon_set = $6, extra_data = $7,
            temp_role_id = $8, use_temp_role = $9, rsvp_allowed_role_ids = $10
        WHERE event_id = ANY($11)
    """, 
        data.get("title"), data.get("description"), data.get("image_urls"),
        data.get("color"), data.get("max_accepted"), data.get("icon_set"), 
        extra_json, data.get("temp_role_id"), data.get("use_temp_role", False),
        rsvp_allowed_role_ids,
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

async def get_guild_events_export(guild_id):
    """Fetches all events for a guild with basic stats for CSV export."""
    pool = await get_pool()
    # We aggregate counts in SQL for performance
    return await pool.fetch("""
        SELECT 
            e.event_id, 
            e.title, 
            e.creator_id, 
            e.start_time, 
            e.status, 
            e.config_name,
            (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.event_id) as total_rsvps,
            (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.event_id AND r.attendance = 'no_show') as no_shows
        FROM active_events e
        WHERE e.guild_id = $1
        ORDER BY e.start_time DESC
    """, str(guild_id))

async def get_guild_rsvps_export(guild_id):
    """Fetches all RSVP records for a guild joined with event titles."""
    pool = await get_pool()
    return await pool.fetch("""
        SELECT 
            e.title as event_title, 
            r.user_id, 
            r.status, 
            r.joined_at, 
            r.attendance
        FROM rsvps r
        JOIN active_events e ON r.event_id = e.event_id
        WHERE e.guild_id = $1
        ORDER BY e.start_time DESC, r.joined_at DESC
    """, str(guild_id))

async def get_attendance_eligible_events(guild_id):
    """Fetches events from the last 7 days that have started."""
    pool = await get_pool()
    now = time.time()
    one_week_ago = now - (7 * 86400)
    return await pool.fetch("""
        SELECT event_id, title, start_time, status
        FROM active_events
        WHERE guild_id = $1 AND start_time < $2 AND start_time > $3
        ORDER BY start_time DESC
    """, str(guild_id), now, one_week_ago)

async def get_event_attendance_data(event_id):
    """Fetches RSVPs and their current attendance status."""
    pool = await get_pool()
    return await pool.fetch("""
        SELECT user_id, status, attendance
        FROM rsvps
        WHERE event_id = $1
        ORDER BY status, user_id
    """, event_id)

async def update_rsvp_attendance(event_id, user_id, status):
    """Updates the attendance column (present/no_show)."""
    pool = await get_pool()
    await pool.execute("""
        UPDATE rsvps
        SET attendance = $1
        WHERE event_id = $2 AND user_id = $3
    """, status, event_id, int(user_id))

async def get_guild_reliability_stats(guild_id, all_time=False):
    """Fetches user reliability stats for a guild."""
    pool = await get_pool()
    now = time.time()
    
    where_clause = "WHERE e.guild_id = $1"
    params = [str(guild_id)]
    
    if not all_time:
        where_clause += " AND e.start_time <= $2"
        params.append(now)
        
    query = f"""
        SELECT 
            r.user_id, 
            COUNT(*) as total_rsvps,
            SUM(CASE WHEN r.attendance = 'no_show' THEN 1 ELSE 0 END) as noshow_count
        FROM rsvps r
        JOIN active_events e ON r.event_id = e.event_id
        {where_clause}
        GROUP BY r.user_id
        HAVING SUM(CASE WHEN r.attendance = 'no_show' THEN 1 ELSE 0 END) > 0
        ORDER BY noshow_count DESC
    """
    return await pool.fetch(query, *params)

async def get_event_reliability_audit(event_id, guild_id):
    """Fetches reliability stats for all participants of a specific event."""
    pool = await get_pool()
    now = time.time()
    return await pool.fetch("""
        WITH participants AS (
            SELECT DISTINCT user_id FROM rsvps WHERE event_id = $1
        )
        SELECT 
            p.user_id, 
            COUNT(r2.event_id) as total_past_rsvps,
            SUM(CASE WHEN r2.attendance = 'no_show' THEN 1 ELSE 0 END) as noshow_count
        FROM participants p
        LEFT JOIN rsvps r2 ON p.user_id = r2.user_id
        LEFT JOIN active_events e ON r2.event_id = e.event_id
        GROUP BY p.user_id
        ORDER BY noshow_count DESC
    """, event_id, str(guild_id), now)

async def get_user_event_history(guild_id, user_id, limit=20):
    """Fetches past events where the user was the organizer or a participant."""
    pool = await get_pool()
    return await pool.fetch("""
        SELECT DISTINCT e.event_id, e.title, e.start_time, e.channel_id, e.message_id, 
               e.creator_id, r.status as user_status, r.attendance
        FROM active_events e
        LEFT JOIN rsvps r ON e.event_id = r.event_id AND r.user_id = $2
        WHERE e.guild_id = $1 
          AND e.status IN ('closed', 'ended')
          AND (e.creator_id = $2 OR (r.user_id IS NOT NULL))
        ORDER BY e.start_time DESC NULLS LAST
        LIMIT $3
    """, str(guild_id), int(user_id), limit)

async def get_endable_events(guild_id):
    """Fetches active events that have already started (for autocomplete)."""
    pool = await get_pool()
    now = time.time()
    return await pool.fetch("""
        SELECT event_id, title, start_time, config_name
        FROM active_events
        WHERE guild_id = $1 AND status = 'active'
          AND (start_time <= $2 OR start_time IS NULL)
        ORDER BY start_time DESC
        LIMIT 25
    """, str(guild_id), now)

async def get_user_active_events(guild_id, user_id):
    """Fetches upcoming events where the user is either the organizer or a participant."""
    pool = await get_pool()
    now = time.time()
    return await pool.fetch("""
        SELECT DISTINCT e.event_id, e.title, e.start_time, e.channel_id, e.message_id, 
               e.creator_id, r.status as user_status
        FROM active_events e
        LEFT JOIN rsvps r ON e.event_id = r.event_id AND r.user_id = $2
        WHERE e.guild_id = $1 
          AND (e.creator_id = $2 OR r.user_id IS NOT NULL)
          AND e.status = 'active'
          AND (e.start_time > $3 OR e.start_time IS NULL)
        ORDER BY e.start_time ASC NULLS LAST
    """, str(guild_id), int(user_id), now - 86400)
