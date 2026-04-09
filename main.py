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
                "cogs.emoji_set_commands"
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
                    log.error(f"Failed to load persistent view for event {event.get('event_id')}: {e}")
                
            # Sync slash commands
            guild_id = self.config.get("guild_id")
            if guild_id:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                log.info(f"Synced {len(synced)} commands to guild {guild_id}")
            else:
                synced = await self.tree.sync()
                log.info(f"Synced {len(synced)} commands globally")
        except Exception as e:
            log.error(f"Critical error during setup_hook: {e}", exc_info=True)

        # Start dynamic presence task
        self.loop.create_task(self.status_task())

    async def status_task(self):
        """Periodically update the bot's rich presence from config."""
        await self.wait_until_ready()
        
        while not self.is_closed():
            try:
                # Get active events count
                event_count = await database.get_active_event_count()
                
                # Load custom statuses from config
                globals_cfg = self.config.get("globals", {})
                presence_list = globals_cfg.get("bot_presence", [])
                
                if not presence_list:
                    presence_list = [f"watching {event_count} events"]
                
                # Select random status and replace placeholders
                import random
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
