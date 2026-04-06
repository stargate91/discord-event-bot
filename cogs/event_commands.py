import discord
from discord.ext import commands
from discord import app_commands
import database
import time
import uuid
import datetime
import json
from cogs.event_ui import DynamicEventView
from utils.i18n import t
from dateutil import parser
from dateutil import tz

try:
    from utils.jsonc import load_jsonc
    config_data = load_jsonc('config.json')
    SUFFIX = config_data.get("command_suffix", "")
    EVENTS_CONFIG = config_data.get("events_config", [])
except Exception:
    SUFFIX = ""
    EVENTS_CONFIG = []

def get_event_dict(name):
    for e in EVENTS_CONFIG:
        if e.get("name") == name:
            return e
    return None

class EventCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="event_publish", description="Publish a specific configured event")
    @app_commands.describe(name="Event configuration name")
    async def event_publish(self, interaction: discord.Interaction, name: str):
        event_conf = get_event_dict(name)
        if not event_conf:
            await interaction.response.send_message("Event not found in config.", ephemeral=True)
            return
            
        if not event_conf.get("enabled"):
            await interaction.response.send_message("This event is disabled in config.", ephemeral=True)
            return

        # Time calculation
        try:
            local_tz = tz.gettz(event_conf.get("timezone", "UTC"))
            dt = parser.parse(event_conf.get("start"))
            dt = dt.replace(tzinfo=local_tz)
            start_timestamp = dt.timestamp()
        except Exception as e:
            await interaction.response.send_message(f"Time parsing error: {e}", ephemeral=True)
            return

        channel_id = event_conf.get("channel_id") or interaction.channel_id
        
        event_id = str(uuid.uuid4())[:8]
        
        # We need a new event persistence
        await database.create_active_event(
            event_id=event_id,
            config_name=name,
            channel_id=channel_id,
            start_time=start_timestamp
        )

        view = DynamicEventView(self.bot, event_id, event_conf)
        embed = await view.generate_embed()

        await interaction.response.send_message(t("MSG_EV_CREATED_EPHEMERAL"), ephemeral=True)
        
        target_channel = self.bot.get_channel(channel_id)
        if not target_channel:
            target_channel = interaction.channel
            
        content = t("MSG_EV_CREATED_PUBLIC")
        ping_role = event_conf.get("ping_role", "")
        if ping_role:
            content += f" <@&{ping_role}>"
            
        msg = await target_channel.send(content=content, embed=embed, view=view)
        
        await database.set_event_message(event_id, msg.id)
        self.bot.add_view(view)

    @event_publish.autocomplete("name")
    async def publish_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=e["name"], value=e["name"])
            for e in EVENTS_CONFIG if current.lower() in e["name"].lower() and e.get("enabled", True)
        ][:25]

    @commands.command(name=f"sync{SUFFIX}")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def sync_prefix(self, ctx: commands.Context, spec: str | None = None):
        if spec == "global":
            synced = await self.bot.tree.sync()
            await ctx.send(t("SYNC_GL_COUNT", count=len(synced)))
        elif spec == "copy":
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send(t("SYNC_CP_COUNT", count=len(synced)))
        else:
            synced = await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send(t("SYNC_GU_COUNT", count=len(synced)))

    @commands.command(name=f"clear_commands{SUFFIX}")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def clear_commands_prefix(self, ctx: commands.Context):
        self.bot.tree.clear_commands(guild=None)
        await self.bot.tree.sync(guild=None)
        
        self.bot.tree.clear_commands(guild=ctx.guild)
        await self.bot.tree.sync(guild=ctx.guild)
        
        await ctx.send(t("SYNC_CLEAR"))

async def setup(bot):
    await bot.add_cog(EventCommands(bot))
