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

try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config_data = json.load(f)
        SUFFIX = config_data.get("command_suffix", "")
except Exception:
    SUFFIX = ""

class EventCreateModal(discord.ui.Modal, title=t("MODAL_TITLE")):
    event_title = discord.ui.TextInput(
        label=t("MODAL_TITLE_LABEL"),
        placeholder=t("MODAL_TITLE_PH"),
        max_length=100
    )
    
    event_description = discord.ui.TextInput(
        label=t("MODAL_DESC_LABEL"),
        style=discord.TextStyle.long,
        placeholder=t("MODAL_DESC_PH"),
        required=False
    )
    
    start_time_str = discord.ui.TextInput(
        label=t("MODAL_TIME_LABEL"),
        placeholder=t("MODAL_TIME_PH"),
        max_length=16
    )
    
    recurrence = discord.ui.TextInput(
        label=t("MODAL_REC_LABEL"),
        placeholder=t("MODAL_REC_PH"),
        default='none',
        max_length=10
    )
    
    image_url = discord.ui.TextInput(
        label=t("MODAL_IMG_LABEL"),
        placeholder=t("MODAL_IMG_PH"),
        required=False
    )

    def __init__(self, bot):
        # We must set dynamic title like this because class attrs are evaluated at import time,
        # but Modal super() uses the class title argument properly if evaluated.
        # Actually in pycord, we can do title=t("MODAL_TITLE") on class definition since t() is synchronous.
        super().__init__(title=t("MODAL_TITLE"))
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        try:
            dt = datetime.datetime.strptime(self.start_time_str.value, '%Y-%m-%d %H:%M')
            dt = dt.replace(tzinfo=datetime.timezone.utc)
            start_timestamp = dt.timestamp()
        except ValueError:
            await interaction.response.send_message(t("ERR_DATE_FMT"), ephemeral=True)
            return

        recurrence_rule = self.recurrence.value.lower().strip()
        if recurrence_rule not in ['none', 'daily', 'weekly']:
            await interaction.response.send_message(t("ERR_REC_FMT"), ephemeral=True)
            return

        event_id = str(uuid.uuid4())[:8]
        
        await database.create_event(
            event_id=event_id,
            title=self.event_title.value,
            description=self.event_description.value,
            start_time=start_timestamp,
            recurrence_rule=recurrence_rule,
            creator_id=interaction.user.id,
            image_url=self.image_url.value or None,
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id
        )

        view = DynamicEventView(self.bot, event_id)
        event_dict = await database.get_event(event_id)
        embed = await view.generate_embed(event_dict)

        await interaction.response.send_message(t("MSG_EV_CREATED_EPHEMERAL"), ephemeral=True)
        msg = await interaction.channel.send(content=t("MSG_EV_CREATED_PUBLIC"), embed=embed, view=view)
        
        await database.set_event_message(event_id, msg.id)
        self.bot.add_view(view)

class EventCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="event_create", description=t("SYNC_DESC_CREATE"))
    async def event_create(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EventCreateModal(self.bot))

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
