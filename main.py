import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import database
import json

from cogs.event_ui import DynamicEventView

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

class EventBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                prefix = config_data.get("command_prefix", "!")
        except Exception:
            prefix = "!"
            
        super().__init__(command_prefix=prefix, intents=intents)

    async def setup_hook(self):
        await database.init_db()
        
        # Load cogs
        await self.load_extension("cogs.event_commands")
        await self.load_extension("cogs.scheduler_task")
        
        # Load persistent views
        active_events = await database.get_active_events()
        for event in active_events:
            self.add_view(DynamicEventView(self, event['id']))
            
        # Sync slash commands
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            guild_id = config.get("guild_id")
            if guild_id:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            else:
                await self.tree.sync()
        except Exception as e:
            print(f"Failed to sync commands: {e}")

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: BOT_TOKEN is not set in .env")
        exit(1)
        
    bot = EventBot()
    bot.run(TOKEN)
