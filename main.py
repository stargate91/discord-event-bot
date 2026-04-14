import discord
from discord.ext import commands
import os
import asyncio
import random
from dotenv import load_dotenv
import database
import json
import uuid
from utils.logger import log
from utils.i18n import t
from cogs.event_ui import DynamicEventView, load_custom_sets

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

from utils.config import config

class EventBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix=config.command_prefix, intents=intents)
        # Keep a reference to the config object for convenience
        self.config_obj = config


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

            master_ids = config.master_guild_ids
            if master_ids:
                from utils.i18n import load_guild_translations
                for gid in master_ids:
                    await load_guild_translations(gid)

            global_sets = await database.get_all_global_emoji_sets()
            if not global_sets:
                log.info("No global emoji sets in database. Seeding factory defaults from templates...")
                from utils.templates import ICON_SET_TEMPLATES, get_template_data

                count = 0
                for tid, tmpl in ICON_SET_TEMPLATES.items():
                    name = t(tmpl.get("label_key"), guild_id=None) if "label_key" in tmpl else tid
                    data = get_template_data(tid)
                    if data:
                        await database.save_global_emoji_set(tid, name, data)
                        count += 1
                log.info(f"Seeded {count} global emoji set(s) from templates.")
        except Exception as e:
            log.error(f"Failed to connect to PostgreSQL: {e}")
            exit(1)
        
        # Apply global logging level from config
        from utils.logger import set_log_level
        log_level = config.get("globals", {}).get("logging_level", "INFO")
        set_log_level(log_level)

        # Master Guild configuration
        self.master_guild_ids = config.master_guild_ids

        try:
            # Load standard (Global) extensions
            global_extensions = [
                "cogs.event_commands",
                "cogs.scheduler_task",
                "cogs.server_setup",
                "cogs.emoji_wizard",
                "cogs.attendance"
            ]
            
            # Load Master (Restricted) extensions
            master_extensions = [
                "cogs.master_commands"
            ]
            
            # 1. Load global extensions
            for ext in global_extensions:
                try:
                    await self.load_extension(ext)
                    log.info(f"Loaded extension: {ext}")
                except Exception as e:
                    log.error(f"Failed to load extension {ext}: {e}", exc_info=True)
            
            # 2. Load master extensions
            for ext in master_extensions:
                try:
                    await self.load_extension(ext)
                    log.info(f"Loaded master extension: {ext}")
                except Exception as e:
                    log.error(f"Failed to load master extension {ext}: {e}", exc_info=True)

            # 3. Handle Special Synchronization Logic
            if self.master_guild_ids:
                # We specifically find the 'master' command group and bind it to our master guilds
                # In discord.py 2.x, GroupCog automatically registers to global tree. 
                # We MUST remove it from global to prevent 'copy_global_to' leakage.
                master_cog = self.get_cog("MasterCommands")
                if master_cog:
                    # Remove from global tree
                    self.tree.remove_command("master")
                    
                    # Add to specific guild trees
                    for gid in self.master_guild_ids:
                        master_guild = discord.Object(id=gid)
                        self.tree.add_command(master_cog, guild=master_guild)
                    log.info(f"Master Hub isolated to guilds: {self.master_guild_ids} (Removed from Global)")

            # Load custom emoji sets into cache before persistent views
            await load_custom_sets()
            
            # Load persistent views for existing active events
            from cogs.event_ui import get_event_conf, DynamicEventView
            active_events = await database.get_all_active_events()
            for event in active_events:
                try:
                    conf = get_event_conf(event['config_name'])
                    view = DynamicEventView(self, event['event_id'], conf)
                    await view.prepare()
                    self.add_view(view)
                except Exception as e:
                    log.error(f"Failed to load persistent view for event {event.get('event_id')}: {e}", guild_id=event.get('guild_id'))
                
            # NOTE: Automatic sync removed per user request for manual 'master system sync' control.
            log.info("Setup complete. Manual sync required via /master system sync.")

        except Exception as e:
            log.error(f"Critical error during setup_hook: {e}", exc_info=True)

        # Start dynamic presence task
        self.loop.create_task(self.status_task())

    async def status_task(self):
        """Periodically update the bot's rich presence from database or config."""
        await self.wait_until_ready()
        
        last_index = -1
        
        while not self.is_closed():
            try:
                # Default config
                config = {
                    "time": 30,
                    "mode": "random",
                    "statuses": [{"id": "default", "type": "watching", "text": t("PRESENCE_DEFAULT", guild_id=None)}]
                }
                
                db_presence = await database.get_global_setting("bot_presence_list")
                parsed = None
                if db_presence:
                    try:
                        parsed = json.loads(db_presence)
                    except json.JSONDecodeError:
                        log.warning("[Presence] bot_presence_list is not valid JSON; using config/defaults.")

                if isinstance(parsed, dict):
                    config.update(parsed)
                elif isinstance(parsed, list):
                    log.warning(
                        "[Presence] bot_presence_list uses deprecated list JSON; "
                        "store a dict {time, mode, statuses} via Master. Using config/defaults for this cycle."
                    )

                if not isinstance(parsed, dict):
                    cfg_list = config.get("dynamic_status", [])
                    if cfg_list:
                        config_data["statuses"] = [
                            {"id": str(uuid.uuid4()), "type": "watching", "text": text}
                            for text in cfg_list
                        ]

                statuses = config.get("statuses", [])
                if not statuses:
                    statuses = [{"id": "default", "type": "watching", "text": t("PRESENCE_DEFAULT", guild_id=None)}]

                # Choose next status
                if config.get("mode") == "sequential":
                    last_index = (last_index + 1) % len(statuses)
                    chosen = statuses[last_index]
                else:
                    chosen = random.choice(statuses)

                # Get stats for placeholders
                stats = await database.get_global_stats()
                
                # Replace placeholders
                status_text = chosen.get("text", "")
                status_text = status_text.replace("{event_count}", str(stats.get("events", 0)))
                status_text = status_text.replace("{guild_count}", str(stats.get("guilds", 0)))
                status_text = status_text.replace("{rsvp_count}", str(stats.get("rsvps", 0)))
                
                # Map activity type
                type_map = {
                    "playing": discord.ActivityType.playing,
                    "watching": discord.ActivityType.watching,
                    "listening": discord.ActivityType.listening,
                    "competing": discord.ActivityType.competing
                }
                act_type = type_map.get(chosen.get("type", "watching"), discord.ActivityType.watching)
                
                activity = discord.Activity(
                    type=act_type,
                    name=status_text
                )
                await self.change_presence(activity=activity, status=discord.Status.online)
                log.info(f"[Presence] Updated to: {act_type.name} - {status_text}")
                
            except Exception as e:
                log.error(f"[Presence] Error updating status: {e}", exc_info=True)
            
            # Rotate based on configured time (default 30s, minimum 15s to avoid API spam)
            sleep_time = max(15, config.get("time", 30))
            await asyncio.sleep(sleep_time)

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
