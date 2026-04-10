import discord
from discord import app_commands, ui
from discord.ext import commands
import database
import json
from utils.logger import log
from utils.i18n import t
from utils.auth import is_admin

class MasterCommands(commands.GroupCog, name="master"):
    """Global Bot Management commands. Only visible in the Master Guild."""
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="stats")
    async def stats(self, interaction: discord.Interaction):
        """View global bot usage and database statistics."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            stats = await database.get_global_stats()
            
            embed = discord.Embed(
                title="📊 Nexus Global Statistics",
                color=discord.Color.purple(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(name="🌐 Guilds", value=f"**{stats['guilds']}**", inline=True)
            embed.add_field(name="📅 Active Events", value=f"**{stats['events']}**", inline=True)
            embed.add_field(name="📝 Total RSVPs", value=f"**{stats['rsvps']}**", inline=True)
            
            # Additional bot info
            embed.add_field(name="🤖 Bot Version", value="v2.1.0", inline=True)
            embed.add_field(name="⚙️ Python Version", value="3.14", inline=True)
            embed.add_field(name="🛰️ Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
            
            embed.set_footer(text="Nexus Event Bot - Owner Console")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            log.error(f"[Master] Error getting stats: {e}")
            await interaction.followup.send(f"❌ Error retrieving stats: {e}")

    @app_commands.command(name="status")
    async def status_mgmt(self, interaction: discord.Interaction):
        """Manage the bot's dynamic presence list using a visual console."""
        view = MasterPresenceView(self.bot)
        await view.refresh_message(interaction)

class MasterPresenceView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot
        
        # Localize button labels
        self.add_btn.label = t("BTN_ADD", guild_id=None)
        self.clear_btn.label = t("BTN_CLEAR", guild_id=None)

    async def refresh_message(self, interaction: discord.Interaction):
        # Load from DB instead of config
        db_presence = await database.get_global_setting("bot_presence_list")
        statuses = json.loads(db_presence) if db_presence else []
        
        embed = discord.Embed(
            title=t("MASTER_PRESENCE_TITLE"),
            description=t("MASTER_PRESENCE_DESC"),
            color=discord.Color.blue()
        )
        status_list = "\n".join([f"• {s}" for s in statuses]) if statuses else t("MASTER_PRESENCE_NONE")
        embed.add_field(name=t("LBL_CURRENT_STATUSES"), value=status_list, inline=False)
        embed.set_footer(text=t("MASTER_PRESENCE_FOOTER"))
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.send_message(embed=embed, view=self, ephemeral=True)

    @ui.button(label="➕ Status", style=discord.ButtonStyle.primary)
    async def add_btn(self, interaction: discord.Interaction, button: ui.Button):
        modal = ui.Modal(title=t("MASTER_PRESENCE_ADD_TITLE"))
        status_input = ui.TextInput(label=t("MASTER_PRESENCE_INPUT"), placeholder=t("MASTER_PRESENCE_PH"), required=True)
        modal.add_item(status_input)
        
        async def on_submit(it: discord.Interaction):
            new_status = status_input.value.strip()
            if new_status:
                db_presence = await database.get_global_setting("bot_presence_list")
                statuses = json.loads(db_presence) if db_presence else []
                statuses.append(new_status)
                await database.save_global_setting("bot_presence_list", json.dumps(statuses))
                await it.response.defer()
                await self.refresh_message(it)
        
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @ui.button(label="🗑️ Clear", style=discord.ButtonStyle.danger)
    async def clear_btn(self, interaction: discord.Interaction, button: ui.Button):
        await database.save_global_setting("bot_presence_list", json.dumps([]))
        await interaction.response.defer()
        await self.refresh_message(interaction)


    @app_commands.command(name="global-sets")
    async def global_emoji_sets(self, interaction: discord.Interaction):
        """Manage system-wide global emoji sets used by all guilds."""
        try:
            from cogs.emoji_wizard import EmojiWizardView
            view = EmojiWizardView(self.bot, interaction.guild_id, is_global=True)
            await view.prepare()
            
            embed = discord.Embed(
                title=f"🌍 Global Emoji Management",
                description="Managing the central icon sets available to all servers.",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            log.error(f"[Master] Error in global-sets: {e}")
            await interaction.response.send_message(f"❌ Error opening Global Emoji Wizard: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MasterCommands(bot))
