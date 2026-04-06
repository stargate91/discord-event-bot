import aiosqlite
import os

DB_PATH = os.path.join("data", "events.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                start_time REAL,
                recurrence_rule TEXT,
                creator_id INTEGER,
                image_url TEXT,
                message_id INTEGER,
                channel_id INTEGER,
                guild_id INTEGER,
                status TEXT DEFAULT 'active'
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
        await db.commit()

async def create_event(event_id, title, description, start_time, recurrence_rule, creator_id, image_url, channel_id, guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO events (id, title, description, start_time, recurrence_rule, creator_id, image_url, channel_id, guild_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (event_id, title, description, start_time, recurrence_rule, creator_id, image_url, channel_id, guild_id))
        await db.commit()

async def set_event_message(event_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE events SET message_id = ? WHERE id = ?", (message_id, event_id))
        await db.commit()

async def get_event(event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM events WHERE id = ?", (event_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None

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

async def get_active_events():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM events WHERE status = 'active'") as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

async def set_event_status(event_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE events SET status = ? WHERE id = ?", (status, event_id))
        await db.commit()

async def get_past_recurring_events(current_time):
    # status='active' AND start_time < current_time AND recurrence_rule != 'none'
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM events WHERE status = 'active' AND start_time <= ? AND recurrence_rule != 'none'", (current_time,)) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

async def delete_event(event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM events WHERE id = ?", (event_id,))
        await db.execute("DELETE FROM rsvps WHERE event_id = ?", (event_id,))
        await db.commit()
