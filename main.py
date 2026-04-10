import discord
from discord.ext import commands
import os
import asyncio
import random
from dotenv import load_dotenv
import database
import json
from utils.logger import log
from utils.i18n import t
from cogs.event_ui import DynamicEventView, load_custom_sets

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

class EventBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        
        try:
            from utils.jsonc import load_jsonc
            config_data = load_jsonc('config.json')
            prefix = config_data.get("command_prefix", "!")
            self.config = config_data
        except Exception:
            prefix = "!"
            self.config = {}
            
        super().__init__(command_prefix=prefix, intents=intents)

    async def setup_hook(self):
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            log.error("DATABASE_URL is not set in .env! Cannot start bot.")
            exit(1)
            
        import asyncpg
        try:
            pool = await asyncpg.create_pool(dsn)
            await database.set_pool(pool)
            await database.init_db()
            log.info("Successfully connected to PostgreSQL.")
            
            # --- Auto-Migration ---
            guild_id = self.config.get("guild_id")
            if guild_id:
                # Preload translations for the main guild
                from utils.i18n import load_guild_translations
                await load_guild_translations(guild_id)

                if await database.check_emoji_sets_empty(guild_id):
                    log.info(f"Emoji sets table is empty for guild {guild_id}. Migrating from config.json...", guild_id=guild_id)
                    sets = self.config.get("emoji_sets", [])
                    for s in sets:
                        await database.save_emoji_set(guild_id, s["set_id"], s["name"], s["data"])
                    log.info(f"Migration complete: {len(sets)} sets imported.", guild_id=guild_id)
                
                # --- Presence Migration (Global) ---
                if await database.get_global_setting("bot_presence_list") is None:
                    globals_cfg = self.config.get("globals", {})
                    presence_list = globals_cfg.get("bot_presence", [])
                    if presence_list:
                        log.info("Migrating bot presence list to global_settings...")
                        await database.save_global_setting("bot_presence_list", json.dumps(presence_list))
                
                # --- Emoji Sets Migration (Global) ---
                # Check if global sets table is empty
                global_sets = await database.get_all_global_emoji_sets()
                if not global_sets:
                    config_sets = self.config.get("emoji_sets", [])
                    if config_sets:
                        log.info("Migrating global emoji sets to database...")
                        for s in config_sets:
                            await database.save_global_emoji_set(s["set_id"], s["name"], s["data"])
                        log.info(f"Migration complete: {len(config_sets)} global sets imported.")
        except Exception as e:
            log.error(f"Failed to connect to PostgreSQL: {e}")
            exit(1)
        
        # Apply global logging level from config
        from utils.logger import set_log_level
        globals_cfg = self.config.get("globals", {})
        if "logging_level" in globals_cfg:
            set_log_level(globals_cfg["logging_level"])

        try:
            # Load cogs
            extensions = [
                "cogs.event_commands",
                "cogs.scheduler_task",
                "cogs.server_setup"
            ]
            
            for ext in extensions:
                try:
                    await self.load_extension(ext)
                    log.info(f"Loaded extension: {ext}")
                except Exception as e:
                    log.error(f"Failed to load extension {ext}: {e}", exc_info=True)
            
            # Load custom emoji sets into cache before persistent views
            await load_custom_sets()
            
            # Load persistent views for existing active events
            from cogs.event_ui import get_event_conf, DynamicEventView
            active_events = await database.get_all_active_events()
            for event in active_events:
                try:
                    conf = get_event_conf(event['config_name'])
                    self.add_view(DynamicEventView(self, event['event_id'], conf))
                except Exception as e:
                    log.error(f"Failed to load persistent view for event {event.get('event_id')}: {e}", guild_id=event.get('guild_id'))
                
            # Sync slash commands
            guild_id = self.config.get("guild_id")
            if guild_id:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                log.info(f"Synced {len(synced)} commands to guild {guild_id}", guild_id=guild_id)
            else:
                synced = await self.tree.sync()
                log.info("Synced commands globally")
        except Exception as e:
            log.error(f"Critical error during setup_hook: {e}", exc_info=True)

        # Start dynamic presence task
        self.loop.create_task(self.status_task())

    async def status_task(self):
        """Periodically update the bot's rich presence from database or config."""
        await self.wait_until_ready()
        
        while not self.is_closed():
            try:
                # Get active events count
                event_count = await database.get_active_event_count()
                
                # 1. Try to load custom statuses from database
                db_presence = await database.get_global_setting("bot_presence_list")
                if db_presence:
                    presence_list = json.loads(db_presence)
                else:
                    # 2. Fallback to config.json (initial setup)
                    presence_list = self.config.get("dynamic_status", [])
                
                if not presence_list:
                    presence_list = [t("PRESENCE_DEFAULT", guild_id=None)]
                
                # Select random status and replace placeholders
                status_text = random.choice(presence_list).replace("{event_count}", str(event_count))
                
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name=status_text
                )
                await self.change_presence(activity=activity, status=discord.Status.online)
                
            except Exception as e:
                log.error(f"[Presence] Error updating status: {e}")
            
            # Rotate every 60 seconds
            await asyncio.sleep(60)

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        log.info("Nexus Event Bot is ready and monitoring events.")
        log.info("------")

if __name__ == "__main__":
    if not TOKEN:
        log.error("BOT_TOKEN is not set in .env")
        exit(1)
        
    bot = EventBot()
    bot.run(TOKEN)
