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
                    if not config_sets:
                        # Add hardcoded 'factory default' sets
                        log.info("No global sets found. Injecting factory defaults...")
                        config_sets = [
                            {
                                "set_id": "standard", "name": "Alap (Igen / Nem)",
                                "data": {"options": [
                                    {"id": "accepted", "emoji": "✅", "label": "Résztveszek", "list_label": "Résztvevők", "button_style": "both", "button_color": "success", "show_in_list": True, "positive": True},
                                    {"id": "tentative", "emoji": "❓", "label": "Talán", "list_label": "Bizonytalan", "button_style": "both", "button_color": "secondary", "show_in_list": True, "positive": False},
                                    {"id": "declined", "emoji": "❌", "label": "Nem jövök", "list_label": "-", "button_style": "emoji", "button_color": "danger", "show_in_list": False, "positive": False}
                                ], "positive_count": 1, "buttons_per_row": 5, "show_mgmt": True}
                            },
                            {
                                "set_id": "raid", "name": "Raid (Tank / Heal / DPS)",
                                "data": {"options": [
                                    {"id": "tank", "emoji": "🛡️", "label": "Tank", "list_label": "Tankok", "button_style": "both", "button_color": "success", "show_in_list": True, "positive": True, "max_slots": 2},
                                    {"id": "heal", "emoji": "🏥", "label": "Heal", "list_label": "Healerek", "button_style": "both", "button_color": "success", "show_in_list": True, "positive": True, "max_slots": 4},
                                    {"id": "dps", "emoji": "🗡️", "label": "DPS", "list_label": "DPS-ek", "button_style": "both", "button_color": "success", "show_in_list": True, "positive": True, "max_slots": 10},
                                    {"id": "backup", "emoji": "❓", "label": "Tartalék", "list_label": "Tartalékok", "button_style": "both", "button_color": "secondary", "show_in_list": True, "positive": False},
                                    {"id": "declined", "emoji": "❌", "label": "Nem jövök", "list_label": "-", "button_style": "emoji", "button_color": "danger", "show_in_list": False, "positive": False}
                                ], "positive_count": 3, "buttons_per_row": 5, "show_mgmt": True}
                            },
                            {
                                "set_id": "survey", "name": "Szavazás (👍 / 👎)",
                                "data": {"options": [
                                    {"id": "up", "emoji": "👍", "label": "Szuper", "list_label": "Szerintük jó", "button_style": "both", "button_color": "success", "show_in_list": True, "positive": True},
                                    {"id": "down", "emoji": "👎", "label": "Rossz", "list_label": "Szerintük rossz", "button_style": "both", "button_color": "danger", "show_in_list": True, "positive": False}
                                ], "positive_count": 1, "buttons_per_row": 5, "show_mgmt": True}
                            },
                            {
                                "set_id": "gaming", "name": "Gaming (Expanded Roles)",
                                "data": {"options": [
                                    {"id": "play", "emoji": "🎮", "label": "Jövök", "list_label": "Játékosok", "button_style": "both", "button_color": "success", "show_in_list": True, "positive": True},
                                    {"id": "watch", "emoji": "📺", "label": "Néző", "list_label": "Nézők", "button_style": "both", "button_color": "primary", "show_in_list": True, "positive": False},
                                    {"id": "maybe", "emoji": "🤔", "label": "Talán", "list_label": "Bizonytalanok", "button_style": "both", "button_color": "secondary", "show_in_list": True, "positive": False},
                                    {"id": "no", "emoji": "❌", "label": "Nem jövök", "list_label": "-", "button_style": "emoji", "button_color": "danger", "show_in_list": False, "positive": False}
                                ], "positive_count": 1, "buttons_per_row": 5, "show_mgmt": True}
                            }
                        ]

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

        # Master Guild configuration
        self.master_guild_id = self.config.get("guild_id")

        try:
            # Load standard (Global) extensions
            global_extensions = [
                "cogs.event_commands",
                "cogs.scheduler_task",
                "cogs.server_setup",
                "cogs.emoji_wizard"
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
            if self.master_guild_id:
                master_guild = discord.Object(id=self.master_guild_id)
                # We specifically find the 'master' command group and bind it to our master guild
                # This ensures it's NOT in the global tree and only shows up in the master guild
                master_cog = self.get_cog("MasterCommands")
                if master_cog:
                    # In discord.py 2.x, GroupCog automatically registers to global tree
                    # We move it to the guild tree for isolation
                    self.tree.add_command(master_cog, guild=master_guild)
                    log.info(f"Master Hub isolated to guild {self.master_guild_id}")

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
                
                # Load from database
                db_presence = await database.get_global_setting("bot_presence_list")
                if db_presence:
                    parsed = json.loads(db_presence)
                    if isinstance(parsed, list):
                        # Migration from old format
                        migrated_statuses = []
                        for text in parsed:
                            migrated_statuses.append({"id": str(uuid.uuid4()), "type": "watching", "text": text})
                        config["statuses"] = migrated_statuses
                        await database.save_global_setting("bot_presence_list", json.dumps(config))
                    elif isinstance(parsed, dict):
                        config.update(parsed)
                else:
                    # Fallback to config.json
                    cfg_list = self.config.get("dynamic_status", [])
                    if cfg_list:
                        config["statuses"] = [{"id": str(uuid.uuid4()), "type": "watching", "text": text} for text in cfg_list]

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
                
            except Exception as e:
                log.error(f"[Presence] Error updating status: {e}")
            
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
