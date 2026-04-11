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
        self.clear_items()
        
        # Action Buttons
        general_btn = ui.Button(label=t("BTN_GENERAL", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def general_cb(it):
            v = GeneralSetupView(self.bot, self.guild_id)
            await v.refresh_message(it)
        general_btn.callback = general_cb

        local_btn = ui.Button(label=t("BTN_LOCAL", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def local_cb(it):
            curr = await database.get_guild_setting(self.guild_id, "timezone", default="")
            modal = SimpleConfigModal(self.guild_id, "timezone", t("SETTING_TIMEZONE", guild_id=self.guild_id), 
                                     placeholder=t("PH_TIMEZONE", guild_id=self.guild_id), default_val=curr, parent_view=self)
            await it.response.send_modal(modal)
        local_btn.callback = local_cb

        reminder_btn = ui.Button(label=t("BTN_REMINDERS", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def reminder_cb(it):
            v = ReminderSetupView(self.bot, self.guild_id)
            await v.refresh_message(it)
        reminder_btn.callback = reminder_cb

        # Color Dropdown Selection
        cur_color_raw = await database.get_guild_setting(self.guild_id, "default_color", default="0x00bfff")
        # Normalize color format for comparison
        cur_color = cur_color_raw.lower().strip().replace("#", "0x")
        if not cur_color.startswith("0x"):
            cur_color = "0x" + cur_color
        
        presets = ["0x00bfff", "0x5865f2", "0xffd700", "0x57f287", "0xeb459e"]
        is_preset = cur_color in presets

        color_opts = [
            discord.SelectOption(label=t("COLOR_DEFAULT", guild_id=self.guild_id), value="0x00bfff", default=(cur_color=="0x00bfff")),
            discord.SelectOption(label=t("COLOR_BLURPLE", guild_id=self.guild_id), value="0x5865f2", default=(cur_color=="0x5865f2")),
            discord.SelectOption(label=t("COLOR_GOLD", guild_id=self.guild_id), value="0xffd700", default=(cur_color=="0xffd700")),
            discord.SelectOption(label=t("COLOR_MINT", guild_id=self.guild_id), value="0x57f287", default=(cur_color=="0x57f287")),
            discord.SelectOption(label=t("COLOR_FUCHSIA", guild_id=self.guild_id), value="0xeb459e", default=(cur_color=="0xeb459e")),
            discord.SelectOption(label=t("COLOR_CUSTOM", guild_id=self.guild_id), value="custom", default=(not is_preset))
        ]
        
        color_sel = ui.Select(placeholder=t("SEL_COLOR", guild_id=self.guild_id), options=color_opts)
        async def color_cb(it):
            val = color_sel.values[0]
            if val == "custom":
                modal = SimpleConfigModal(self.guild_id, "default_color", t("SETTING_COLOR", guild_id=self.guild_id), 
                                         placeholder=t("PH_COLOR", guild_id=self.guild_id), default_val=cur_color, parent_view=self)
                await it.response.send_modal(modal)
            else:
                await database.save_guild_setting(self.guild_id, "default_color", val)
                await self.refresh_message(it)
        color_sel.callback = color_cb

        defaults_btn = ui.Button(label=t("BTN_EVENT_DEFAULTS", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def defaults_cb(it):
            v = EventDefaultsView(self.bot, self.guild_id)
            await v.refresh_message(it)
        defaults_btn.callback = defaults_cb

        container = ui.Container(
            ui.TextDisplay(f"### ⚙️ {t('SETUP_GENERAL_TITLE', guild_id=self.guild_id)}"),
            ui.Separator(),
            ui.TextDisplay(t("SETUP_GENERAL_DESC", guild_id=self.guild_id)),
            ui.Separator(),
            ui.ActionRow(general_btn, local_btn, reminder_btn, defaults_btn),
            ui.ActionRow(color_sel),
            accent_color=0x00bfff
        )
        self.add_item(container)
        
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
                if interaction.message:
                    await interaction.message.edit(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception:
            if not interaction.response.is_done():
                await interaction.response.send_message(view=self, ephemeral=True)
            else:
                try: await interaction.followup.send(view=self, ephemeral=True)
                except: pass

class GeneralSetupView(ui.LayoutView):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id

    async def refresh_message(self, interaction: discord.Interaction):
        self.clear_items()
        
        # Get current language from DB
        cur_lang = await database.get_guild_setting(self.guild_id, "language", default="en")

        lang_hu = ui.Button(
            label=t("LBL_LANG_HU", guild_id=self.guild_id), 
            style=discord.ButtonStyle.success if cur_lang == "hu" else discord.ButtonStyle.secondary
        )
        async def hu_cb(it): await self._set_lang(it, "hu")
        lang_hu.callback = hu_cb

        lang_en = ui.Button(
            label=t("LBL_LANG_EN", guild_id=self.guild_id), 
            style=discord.ButtonStyle.success if cur_lang == "en" else discord.ButtonStyle.secondary
        )
        async def en_cb(it): await self._set_lang(it, "en")
        lang_en.callback = en_cb

        roles_btn = ui.Button(label=t("BTN_ADMIN_ROLES", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def roles_cb(it):
            curr = await database.get_guild_setting(self.guild_id, "admin_role_ids", default="")
            modal = SimpleConfigModal(self.guild_id, "admin_role_ids", t("SETTING_ADMIN_ROLES", guild_id=self.guild_id), 
                                     placeholder=t("PH_ID_LIST", guild_id=self.guild_id), is_long=True, default_val=curr, parent_view=self)
            await it.response.send_modal(modal)
        roles_btn.callback = roles_cb

        channels_btn = ui.Button(label=t("BTN_ADMIN_CHANNELS", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def channels_cb(it):
            curr = await database.get_guild_setting(self.guild_id, "admin_channel_ids", default="")
            modal = SimpleConfigModal(self.guild_id, "admin_channel_ids", t("SETTING_ADMIN_CHANNELS", guild_id=self.guild_id), 
                                     placeholder=t("PH_ID_LIST", guild_id=self.guild_id), is_long=True, default_val=curr, parent_view=self)
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
            ui.ActionRow(lang_hu, lang_en, roles_btn, channels_btn, back_btn),
            accent_color=0x00bfff
        )
        self.add_item(container)
        
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
                if interaction.message:
                    await interaction.message.edit(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception:
            if not interaction.response.is_done():
                await interaction.response.send_message(view=self, ephemeral=True)
            else:
                try: await interaction.followup.send(view=self, ephemeral=True)
                except: pass

    async def _set_lang(self, interaction, lang):
        await database.save_guild_setting(self.guild_id, "language", lang)
        await load_guild_translations(self.guild_id) # Reload cache
        # No ephemeral popup here for smoother transition
        await self.refresh_message(interaction)

class ReminderSetupView(ui.LayoutView):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id

    async def refresh_message(self, interaction: discord.Interaction):
        self.clear_items()
        
        # Get current reminder type from DB
        cur_rem = await database.get_guild_setting(self.guild_id, "reminder_type", default="none")

        async def set_rem(it, rtype):
            await database.save_guild_setting(self.guild_id, "reminder_type", rtype)
            # No ephemeral popup here for smoother transition
            await self.refresh_message(it)

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

        # Reminder Offset button
        offset_btn = ui.Button(label=t("BTN_REMINDER_OFFSET", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def offset_cb(it):
            curr = await database.get_guild_setting(self.guild_id, "default_reminder_offset", default="15m")
            modal = SimpleConfigModal(self.guild_id, "default_reminder_offset", t("SETTING_REMINDER_OFFSET", guild_id=self.guild_id), 
                                     placeholder=t("PH_REMINDER_OFFSET", guild_id=self.guild_id), default_val=curr, parent_view=self)
            await it.response.send_modal(modal)
        offset_btn.callback = offset_cb

        container = ui.Container(
            ui.TextDisplay(f"### ⚙️ {t('BTN_REMINDERS', guild_id=self.guild_id).replace('🔔 ', '')}"),
            ui.Separator(),
            ui.ActionRow(rem_none, rem_ping, rem_dm, rem_both, back_btn),
            ui.ActionRow(offset_btn),
            accent_color=0x00bfff
        )
        self.add_item(container)
        
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
                if interaction.message:
                    await interaction.message.edit(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception:
            if not interaction.response.is_done():
                await interaction.response.send_message(view=self, ephemeral=True)
            else:
                try: await interaction.followup.send(view=self, ephemeral=True)
                except: pass

class EventDefaultsView(ui.LayoutView):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id

    async def refresh_message(self, interaction: discord.Interaction):
        self.clear_items()
        
        channel_btn = ui.Button(label=t("BTN_DEFAULT_CHANNEL", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def channel_cb(it):
            curr = await database.get_guild_setting(self.guild_id, "default_event_channel", default="")
            modal = SimpleConfigModal(self.guild_id, "default_event_channel", t("LBL_SET_CHANNEL", guild_id=self.guild_id), 
                                     placeholder="#channel-name", default_val=curr, parent_view=self)
            await it.response.send_modal(modal)
        channel_btn.callback = channel_cb

        max_acc_btn = ui.Button(label=t("BTN_DEFAULT_MAX_ACC", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def max_acc_cb(it):
            curr = await database.get_guild_setting(self.guild_id, "default_max_participants", default="0")
            modal = SimpleConfigModal(self.guild_id, "default_max_participants", t("LBL_SET_MAX_ACC", guild_id=self.guild_id), 
                                     placeholder="0", default_val=curr, parent_view=self)
            await it.response.send_modal(modal)
        max_acc_btn.callback = max_acc_cb

        async def back_cb(it):
            v = ServerSetupView(self.bot, self.guild_id)
            await v.refresh_message(it)
        back_btn.callback = back_cb

        # Waitlist Toggle
        wait_val = await database.get_guild_setting(self.guild_id, "default_use_waiting_list", default="false")
        is_on = wait_val.lower() == "true"
        state_text = t("LBL_WAITLIST_ON", guild_id=self.guild_id) if is_on else t("LBL_WAITLIST_OFF", guild_id=self.guild_id)
        
        wait_btn = ui.Button(
            label=t("BTN_DEFAULT_WAITLIST", guild_id=self.guild_id, state=state_text),
            style=discord.ButtonStyle.success if is_on else discord.ButtonStyle.secondary
        )
        async def wait_cb(it):
            new_val = "false" if is_on else "true"
            await database.save_guild_setting(self.guild_id, "default_use_waiting_list", new_val)
            await self.refresh_message(it)
        wait_btn.callback = wait_cb

        container = ui.Container(
            ui.TextDisplay(f"### 📋 {t('BTN_EVENT_DEFAULTS', guild_id=self.guild_id)}"),
            ui.Separator(),
            ui.ActionRow(channel_btn, max_acc_btn, wait_btn),
            ui.ActionRow(back_btn),
            accent_color=0x00bfff
        )
        self.add_item(container)
        
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
                if interaction.message:
                    await interaction.message.edit(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception:
            if not interaction.response.is_done():
                await interaction.response.send_message(view=self, ephemeral=True)
            else:
                try: await interaction.followup.send(view=self, ephemeral=True)
                except: pass

class SimpleConfigModal(ui.Modal):
    def __init__(self, guild_id, key, title, placeholder="", is_long=False, default_val="", parent_view=None):
        super().__init__(title=title[:45])
        self.guild_id = guild_id
        self.key = key
        self.parent_view = parent_view
        
        style = discord.TextStyle.paragraph if is_long else discord.TextStyle.short
        self.input_field = ui.TextInput(label=title, placeholder=placeholder, style=style, default=default_val, required=True)
        self.add_item(self.input_field)

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Defer immediately to close the modal and avoid timeout
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        val = str(self.input_field.value).strip()
        from utils.logger import log
        log.info(f"MODAL: Submitting key {self.key} with value {val} for GID {self.guild_id}")
        
        try:
            # 2. Perform database operations
            await database.save_guild_setting(self.guild_id, self.key, val)
            
            # 3. Trigger cache reload if it affects localization/auth context
            if self.key in ["language", "admin_role_ids", "admin_channel_ids"]:
                await load_guild_translations(self.guild_id)

            # 4. Notify user by editing the deferred 'thinking' message
            await interaction.edit_original_response(content=t("MSG_SETTING_SAVED", guild_id=self.guild_id, key=self.key, val=val[:100]), view=None)
            
            # 5. Refresh the parent view if exists
            if self.parent_view:
                await self.parent_view.refresh_message(interaction)
        except Exception as e:
            log.error(f"Error in modal submit for {self.key}: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

async def setup(bot):
    # This cog primarily provides the view classes for other cogs to use.
    pass
