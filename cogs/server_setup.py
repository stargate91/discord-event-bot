import discord
from discord import ui
import database
from utils.i18n import t, load_guild_translations
from utils.auth import is_admin

class ServerSetupView(ui.LayoutView):
    """Visual console for guild settings and defaults using Components V2."""
    def __init__(self, bot, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id

    async def refresh_message(self, interaction: discord.Interaction):
        # Fresh view instance for V2 dispatching
        view = ServerSetupView(self.bot, self.guild_id)
        view.clear_items()
        
        # Action Buttons
        general_btn = ui.Button(label=t("BTN_GENERAL", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def general_cb(it):
            v = GeneralSetupView(self.bot, self.guild_id)
            await v.refresh_message(it)
        general_btn.callback = general_cb

        local_btn = ui.Button(label=t("BTN_LOCAL", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def local_cb(it):
            modal = SimpleConfigModal(self.guild_id, "timezone", t("SETTING_TIMEZONE", guild_id=self.guild_id), placeholder=t("PH_TIMEZONE", guild_id=self.guild_id), parent_view=view)
            await it.response.send_modal(modal)
        local_btn.callback = local_cb

        color_btn = ui.Button(label=t("BTN_COLOR", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def color_cb(it):
            modal = SimpleConfigModal(self.guild_id, "default_color", t("SETTING_COLOR", guild_id=self.guild_id), placeholder=t("PH_COLOR", guild_id=self.guild_id), parent_view=view)
            await it.response.send_modal(modal)
        color_btn.callback = color_cb

        reminder_btn = ui.Button(label=t("BTN_REMINDERS", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def reminder_cb(it):
            v = ReminderSetupView(self.bot, self.guild_id)
            await v.refresh_message(it)
        reminder_btn.callback = reminder_cb

        container = ui.Container(
            ui.TextDisplay(f"### ⚙️ {t('SETUP_GENERAL_TITLE', guild_id=self.guild_id)}"),
            ui.Separator(),
            ui.TextDisplay(t("SETUP_GENERAL_DESC", guild_id=self.guild_id)),
            ui.Separator(),
            ui.ActionRow(general_btn, local_btn),
            ui.ActionRow(color_btn, reminder_btn),
            accent_color=0x00bfff
        )
        view.add_item(container)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(content=None, embeds=[], view=view)
        else:
            await interaction.response.edit_message(content=None, embeds=[], view=view)

class GeneralSetupView(ui.LayoutView):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id

    async def refresh_message(self, interaction: discord.Interaction):
        view = GeneralSetupView(self.bot, self.guild_id)
        view.clear_items()
        
        # Get current language from DB
        cur_lang = await database.get_guild_setting(self.guild_id, "language", default="en")

        lang_hu = ui.Button(
            label=t("LBL_LANG_HU", guild_id=self.guild_id), 
            style=discord.ButtonStyle.success if cur_lang == "hu" else discord.ButtonStyle.secondary
        )
        async def hu_cb(it): await view._set_lang(it, "hu")
        lang_hu.callback = hu_cb

        lang_en = ui.Button(
            label=t("LBL_LANG_EN", guild_id=self.guild_id), 
            style=discord.ButtonStyle.success if cur_lang == "en" else discord.ButtonStyle.secondary
        )
        async def en_cb(it): await view._set_lang(it, "en")
        lang_en.callback = en_cb

        roles_btn = ui.Button(label=t("BTN_ADMIN_ROLES", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def roles_cb(it):
            modal = SimpleConfigModal(self.guild_id, "admin_role_ids", t("SETTING_ADMIN_ROLES", guild_id=self.guild_id), 
                                     placeholder=t("PH_ID_LIST", guild_id=self.guild_id), is_long=True, parent_view=view)
            await it.response.send_modal(modal)
        roles_btn.callback = roles_cb

        channels_btn = ui.Button(label=t("BTN_ADMIN_CHANNELS", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def channels_cb(it):
            modal = SimpleConfigModal(self.guild_id, "admin_channel_ids", t("SETTING_ADMIN_CHANNELS", guild_id=self.guild_id), 
                                     placeholder=t("PH_ID_LIST", guild_id=self.guild_id), is_long=True, parent_view=view)
            await it.response.send_modal(modal)
        channels_btn.callback = channels_cb

        back_btn = ui.Button(label=t("BTN_BACK", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def back_cb(it):
            v = ServerSetupView(self.bot, self.guild_id)
            await v.refresh_message(it)
        back_btn.callback = back_cb

        container = ui.Container(
            ui.TextDisplay(f"### ⚙️ {t('SETUP_GENERAL_TITLE', guild_id=self.guild_id)}"),
            ui.Separator(),
            ui.TextDisplay(t("SETUP_GENERAL_DESC", guild_id=self.guild_id)),
            ui.Separator(),
            ui.ActionRow(lang_hu, lang_en),
            ui.ActionRow(roles_btn, channels_btn, back_btn),
            accent_color=0x00bfff
        )
        view.add_item(container)
        await interaction.response.edit_message(content=None, embeds=[], view=view)

    async def _set_lang(self, interaction, lang):
        await database.save_guild_setting(self.guild_id, "language", lang)
        await load_guild_translations(self.guild_id) # Reload cache
        await interaction.response.send_message(t("MSG_LANG_SET", guild_id=self.guild_id, lang=lang), ephemeral=True)
        await self.refresh_message(interaction)

class ReminderSetupView(ui.LayoutView):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id

    async def refresh_message(self, interaction: discord.Interaction):
        view = ReminderSetupView(self.bot, self.guild_id)
        view.clear_items()
        
        # Get current reminder type from DB
        cur_rem = await database.get_guild_setting(self.guild_id, "reminder_type", default="none")

        async def set_rem(it, rtype):
            await database.save_guild_setting(self.guild_id, "reminder_type", rtype)
            await it.response.send_message(t("MSG_REM_TYPE_SET", guild_id=self.guild_id) + f": `{rtype}`", ephemeral=True)
            await view.refresh_message(it)

        rem_none = ui.Button(
            label=t("SEL_REM_NONE", guild_id=self.guild_id), 
            style=discord.ButtonStyle.success if cur_rem == "none" else discord.ButtonStyle.secondary
        )
        rem_none.callback = lambda it: set_rem(it, "none")

        rem_ping = ui.Button(
            label=t("SEL_REM_PING", guild_id=self.guild_id), 
            style=discord.ButtonStyle.success if cur_rem == "ping" else discord.ButtonStyle.secondary
        )
        rem_ping.callback = lambda it: set_rem(it, "ping")

        rem_dm = ui.Button(
            label=t("SEL_REM_DM", guild_id=self.guild_id), 
            style=discord.ButtonStyle.success if cur_rem == "dm" else discord.ButtonStyle.secondary
        )
        rem_dm.callback = lambda it: set_rem(it, "dm")

        rem_both = ui.Button(
            label=t("SEL_REM_BOTH", guild_id=self.guild_id), 
            style=discord.ButtonStyle.success if cur_rem == "both" else discord.ButtonStyle.secondary
        )
        rem_both.callback = lambda it: set_rem(it, "both")

        back_btn = ui.Button(label=t("BTN_BACK", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def back_cb(it):
            v = ServerSetupView(self.bot, self.guild_id)
            await v.refresh_message(it)
        back_btn.callback = back_cb

        container = ui.Container(
            ui.TextDisplay(f"### ⚙️ {t('BTN_REMINDERS', guild_id=self.guild_id).replace('🔔 ', '')}"),
            ui.Separator(),
            ui.ActionRow(rem_none, rem_ping),
            ui.ActionRow(rem_dm, rem_both, back_btn),
            accent_color=0x00bfff
        )
        view.add_item(container)
        await interaction.response.edit_message(content=None, embeds=[], view=view)

class SimpleConfigModal(ui.Modal):
    def __init__(self, guild_id, key, title, placeholder="", is_long=False, parent_view=None):
        super().__init__(title=title[:45])
        self.guild_id = guild_id
        self.key = key
        self.parent_view = parent_view
        
        style = discord.TextStyle.paragraph if is_long else discord.TextStyle.short
        self.input_field = ui.TextInput(label=title, placeholder=placeholder, style=style, required=True)
        self.add_item(self.input_field)

    async def on_submit(self, interaction: discord.Interaction):
        val = str(self.input_field.value).strip()
        await database.save_guild_setting(self.guild_id, self.key, val)
        
        # Trigger cache reload if it affects localization/auth context
        if self.key in ["language", "admin_role_ids", "admin_channel_ids"]:
            await load_guild_translations(self.guild_id)

        await interaction.response.send_message(t("MSG_SETTING_SAVED", guild_id=self.guild_id, key=self.key, val=val[:100]), ephemeral=True)
        if self.parent_view:
            await self.parent_view.refresh_message(interaction)

async def setup(bot):
    # This cog primarily provides the view classes for other cogs to use.
    pass
