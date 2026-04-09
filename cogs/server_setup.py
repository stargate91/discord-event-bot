import discord
from discord import ui
import database
from utils.i18n import t, load_guild_translations
from utils.auth import is_admin

class ServerSetupView(ui.View):
    """Visual console for guild settings and defaults."""
    def __init__(self, bot, guild_id):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id
        
        # Dynamically set button labels based on current language
        self.general_btn.label = t("BTN_GENERAL", guild_id=guild_id)
        self.local_btn.label = t("BTN_LOCAL", guild_id=guild_id)
        self.color_btn.label = t("BTN_COLOR", guild_id=guild_id)
        self.reminder_btn.label = t("BTN_REMINDERS", guild_id=guild_id)

    @ui.button(label="🌐 General", style=discord.ButtonStyle.primary, row=0)
    async def general_btn(self, interaction: discord.Interaction, button: ui.Button):
        view = GeneralSetupView(self.bot, self.guild_id)
        embed = discord.Embed(
            title=t("SETUP_GENERAL_TITLE", guild_id=self.guild_id),
            description=t("SETUP_GENERAL_DESC", guild_id=self.guild_id),
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @ui.button(label="🌍 Timezone & Localization", style=discord.ButtonStyle.secondary, row=0)
    async def local_btn(self, interaction: discord.Interaction, button: ui.Button):
        modal = SimpleConfigModal(self.guild_id, "timezone", t("SETTING_TIMEZONE", guild_id=self.guild_id), placeholder="e.g. Europe/Budapest")
        await interaction.response.send_modal(modal)

    @ui.button(label="🎨 Aesthetics (Color)", style=discord.ButtonStyle.secondary, row=1)
    async def color_btn(self, interaction: discord.Interaction, button: ui.Button):
        modal = SimpleConfigModal(self.guild_id, "default_color", t("SETTING_COLOR", guild_id=self.guild_id), placeholder="e.g. 0x5865f2 or #5865f2")
        await interaction.response.send_modal(modal)

    @ui.button(label="🔔 Reminders", style=discord.ButtonStyle.secondary, row=1)
    async def reminder_btn(self, interaction: discord.Interaction, button: ui.Button):
        view = ReminderSetupView(self.bot, self.guild_id)
        await interaction.response.send_message(f"🔔 **{t('BTN_REMINDERS', guild_id=self.guild_id)}**", view=view, ephemeral=True)

class GeneralSetupView(ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        
        # Localization
        self.roles_btn.label = t("BTN_ADMIN_ROLES", guild_id=guild_id)
        self.channels_btn.label = t("BTN_ADMIN_CHANNELS", guild_id=guild_id)

    @ui.button(label="🇭🇺 Hungarian", style=discord.ButtonStyle.success)
    async def lang_hu(self, interaction: discord.Interaction, button: ui.Button):
        await self._set_lang(interaction, "hu")

    @ui.button(label="🇺🇸 English", style=discord.ButtonStyle.primary)
    async def lang_en(self, interaction: discord.Interaction, button: ui.Button):
        await self._set_lang(interaction, "en")

    @ui.button(label="👥 Admin Roles", style=discord.ButtonStyle.gray)
    async def roles_btn(self, interaction: discord.Interaction, button: ui.Button):
        modal = SimpleConfigModal(self.guild_id, "admin_role_ids", t("SETTING_ADMIN_ROLES", guild_id=self.guild_id), 
                                 placeholder="ID1, ID2, ID3...", is_long=True)
        await interaction.response.send_modal(modal)

    @ui.button(label="📺 Admin Channels", style=discord.ButtonStyle.gray)
    async def channels_btn(self, interaction: discord.Interaction, button: ui.Button):
        modal = SimpleConfigModal(self.guild_id, "admin_channel_ids", t("SETTING_ADMIN_CHANNELS", guild_id=self.guild_id), 
                                 placeholder="ID_A, ID_B...", is_long=True)
        await interaction.response.send_modal(modal)

    async def _set_lang(self, interaction, lang):
        await database.save_guild_setting(self.guild_id, "language", lang)
        await load_guild_translations(self.guild_id) # Reload cache
        await interaction.response.send_message(f"✅ Language set to `{lang}`.", ephemeral=True)

class ReminderSetupView(ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id

    @ui.button(label="None", style=discord.ButtonStyle.gray)
    async def rem_none(self, interaction: discord.Interaction, button: ui.Button):
        await self._set_rem(interaction, "none")

    @ui.button(label="Ping Only", style=discord.ButtonStyle.primary)
    async def rem_ping(self, interaction: discord.Interaction, button: ui.Button):
        await self._set_rem(interaction, "ping")

    @ui.button(label="DM Only", style=discord.ButtonStyle.primary)
    async def rem_dm(self, interaction: discord.Interaction, button: ui.Button):
        await self._set_rem(interaction, "dm")

    @ui.button(label="Both (Ping + DM)", style=discord.ButtonStyle.success)
    async def rem_both(self, interaction: discord.Interaction, button: ui.Button):
        await self._set_rem(interaction, "both")

    async def _set_rem(self, interaction, rtype):
        await database.save_guild_setting(self.guild_id, "reminder_type", rtype)
        await interaction.response.send_message(f"✅ Default reminder type set to `{rtype}`.", ephemeral=True)

class SimpleConfigModal(ui.Modal):
    def __init__(self, guild_id, key, title, placeholder="", is_long=False):
        super().__init__(title=title[:45])
        self.guild_id = guild_id
        self.key = key
        
        style = discord.TextStyle.paragraph if is_long else discord.TextStyle.short
        self.input_field = ui.TextInput(label=title, placeholder=placeholder, style=style, required=True)
        self.add_item(self.input_field)

    async def on_submit(self, interaction: discord.Interaction):
        val = str(self.input_field.value).strip()
        await database.save_guild_setting(self.guild_id, self.key, val)
        
        # Trigger cache reload if it affects localization/auth context
        if self.key in ["language", "admin_role_ids", "admin_channel_ids"]:
            await load_guild_translations(self.guild_id)

        await interaction.response.send_message(f"✅ Saved `{self.key}`: `{val[:100]}`", ephemeral=True)

async def setup(bot):
    # This cog primarily provides the view classes for other cogs to use.
    pass
