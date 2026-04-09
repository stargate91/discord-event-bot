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

from cogs.event_ui import DynamicEventView

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
        await database.init_db()
        
        # Load cogs
        await self.load_extension("cogs.event_commands")
        await self.load_extension("cogs.scheduler_task")
        await self.load_extension("cogs.emoji_set_commands")
        
        # Load persistent views for existing active events
        from cogs.event_ui import get_event_conf
        active_events = await database.get_all_active_events()
        for event in active_events:
            conf = get_event_conf(event['config_name'])
            self.add_view(DynamicEventView(self, event['event_id'], conf))
            
        # Sync slash commands
        try:
            guild_id = self.config.get("guild_id")
            if guild_id:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            else:
                await self.tree.sync()
        except Exception as e:
            log.error(f"Failed to sync commands: {e}")

        # Start dynamic presence task
        self.loop.create_task(self.status_task())

    async def status_task(self):
        """Periodically update the bot's rich presence with Nexus persona."""
        await self.wait_until_ready()
        
        while not self.is_closed():
            try:
                # Get active events count
                active_events = await database.get_all_active_events()
                event_count = len(active_events)
                
                # Get dynamic statuses from i18n
                # dynamic_status is a list in our JSON
                from utils.i18n import TRANSLATIONS
                statuses = TRANSLATIONS.get("dynamic_status", [t("watching_events", count=event_count)])
                
                # Select random status
                status_text = random.choice(statuses).replace("{count}", str(event_count))
                
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
