import discord
from utils.emojis import ERROR, GLOBE
from discord import ui
import database
from database import DEFAULT_TIMEZONE
from utils.i18n import t, load_guild_translations
from utils.emoji_utils import to_emoji, make_select_option, split_emoji, make_button
from utils.auth import is_admin
from utils.logger import log

class ServerSetupView(ui.LayoutView):
    """Visual console for guild settings and defaults using Components V2."""
    def __init__(self, bot, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id

    async def prepare(self, interaction: discord.Interaction):
        """Asynchronously build the UI components and bind callbacks."""
        self.clear_items()
        
        # 1. Action Buttons
        general_btn = make_button(label=t("BTN_GENERAL", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def general_cb(it):
            v = GeneralSetupView(self.bot, self.guild_id)
            await v.refresh_message(it)
        general_btn.callback = general_cb

        curr_tz = await database.get_guild_setting(self.guild_id, "timezone", default=DEFAULT_TIMEZONE)
        local_btn = make_button(label=curr_tz, emoji=to_emoji(GLOBE), style=discord.ButtonStyle.secondary)
        async def local_cb(it):
            modal = SimpleConfigModal(self.guild_id, "timezone", t("SETTING_TIMEZONE", guild_id=self.guild_id), 
                                     placeholder=t("PH_TIMEZONE", guild_id=self.guild_id), default_val=curr_tz, parent_view=self)
            await it.response.send_modal(modal)
        local_btn.callback = local_cb

        reminder_btn = make_button(label=t("BTN_REMINDERS", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def reminder_cb(it):
            v = ReminderSetupView(self.bot, self.guild_id)
            await v.refresh_message(it)
        reminder_btn.callback = reminder_cb

        # 2. Color Dropdown Selection
        cur_color_raw = await database.get_guild_setting(self.guild_id, "default_color", default="0x40C4FF")
        cur_color = cur_color_raw.lower().strip().replace("#", "0x")
        if not cur_color.startswith("0x"): cur_color = "0x" + cur_color
        
        presets = ["0x40c4ff", "0x5865f2", "0xffd700", "0x57f287", "0xeb459e"]
        is_preset = cur_color in presets

        color_opts = [
            make_select_option(label=t("COLOR_DEFAULT", guild_id=self.guild_id), value="0x40c4ff", default=(cur_color=="0x40c4ff")),
            make_select_option(label=t("COLOR_BLURPLE", guild_id=self.guild_id), value="0x5865f2", default=(cur_color=="0x5865f2")),
            make_select_option(label=t("COLOR_GOLD", guild_id=self.guild_id), value="0xffd700", default=(cur_color=="0xffd700")),
            make_select_option(label=t("COLOR_MINT", guild_id=self.guild_id), value="0x57f287", default=(cur_color=="0x57f287")),
            make_select_option(label=t("COLOR_FUCHSIA", guild_id=self.guild_id), value="0xeb459e", default=(cur_color=="0xeb459e")),
            make_select_option(label=t("COLOR_CUSTOM", guild_id=self.guild_id), value="custom", default=(not is_preset))
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
                await it.followup.send(t("MSG_SETTING_SAVED", guild_id=self.guild_id, key=t("SETTING_COLOR", guild_id=self.guild_id), val=val), ephemeral=True)
        color_sel.callback = color_cb

        defaults_btn = make_button(label=t("BTN_EVENT_DEFAULTS", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def defaults_cb(it):
            v = EventDefaultsView(self.bot, self.guild_id)
            await v.refresh_message(it)
        defaults_btn.callback = defaults_cb

        # 3. Final Assembly
        header = ui.Container(
            ui.TextDisplay(f"### {t('SETUP_MAIN_TITLE', guild_id=self.guild_id)}\n{t('SETUP_MAIN_DESC', guild_id=self.guild_id)}"),
            accent_color=0x40C4FF
        )
        self.add_item(header)
        self.add_item(ui.ActionRow(general_btn, local_btn, reminder_btn, defaults_btn))
        self.add_item(ui.ActionRow(color_sel))

    async def refresh_message(self, interaction: discord.Interaction):
        """Standard interaction refresh: prepare self and update the message."""
        try:
            await self.prepare(interaction)
            
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            elif interaction.type == discord.InteractionType.component:
                await interaction.response.edit_message(view=self)
            else:
                await interaction.response.send_message(view=self, ephemeral=True)
        except Exception as e:
            log.error(f"[ServerSetupView] refresh error: {e}", exc_info=True)
            msg = f"{ERROR} {e}"
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)

class GeneralSetupView(ui.LayoutView):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id

    async def prepare(self, interaction: discord.Interaction):
        """Asynchronously build the UI components and bind callbacks."""
        self.clear_items()
        
        # 1. Get current language from DB
        cur_lang = await database.get_guild_setting(self.guild_id, "language", default="en")

        lang_hu = make_button(
            label=t("LBL_LANG_HU", guild_id=self.guild_id), 
            style=discord.ButtonStyle.success if cur_lang == "hu" else discord.ButtonStyle.secondary
        )
        async def hu_cb(it): await self._set_lang(it, "hu")
        lang_hu.callback = hu_cb

        lang_en = make_button(
            label=t("LBL_LANG_EN", guild_id=self.guild_id), 
            style=discord.ButtonStyle.success if cur_lang == "en" else discord.ButtonStyle.secondary
        )
        async def en_cb(it): await self._set_lang(it, "en")
        lang_en.callback = en_cb

        roles_btn = make_button(label=t("BTN_ADMIN_ROLES", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def roles_cb(it):
            curr = await database.get_guild_setting(self.guild_id, "admin_role_ids", default="")
            modal = SimpleConfigModal(self.guild_id, "admin_role_ids", t("SETTING_ADMIN_ROLES", guild_id=self.guild_id), 
                                     placeholder=t("PH_ID_LIST", guild_id=self.guild_id), is_long=True, default_val=curr, parent_view=self)
            await it.response.send_modal(modal)
        roles_btn.callback = roles_cb

        channels_btn = make_button(label=t("BTN_ADMIN_CHANNELS", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def channels_cb(it):
            curr = await database.get_guild_setting(self.guild_id, "admin_channel_ids", default="")
            modal = SimpleConfigModal(self.guild_id, "admin_channel_ids", t("SETTING_ADMIN_CHANNELS", guild_id=self.guild_id), 
                                     placeholder=t("PH_ID_LIST", guild_id=self.guild_id), is_long=True, default_val=curr, parent_view=self)
            await it.response.send_modal(modal)
        channels_btn.callback = channels_cb

        # 2. Template Lang Select
        cur_tpl_lang = await database.get_guild_setting(self.guild_id, "template_language", default="en")
        tpl_opts = [
            make_select_option(label=t("SEL_LANG_DEFAULT", guild_id=self.guild_id), value="default", default=(cur_tpl_lang=="default")),
            make_select_option(label=t("LBL_LANG_HU", guild_id=self.guild_id), value="hu", default=(cur_tpl_lang=="hu")),
            make_select_option(label=t("LBL_LANG_EN", guild_id=self.guild_id), value="en", default=(cur_tpl_lang=="en")),
        ]
        tpl_sel = ui.Select(placeholder=t("LBL_TEMPLATE_LANG", guild_id=self.guild_id), options=tpl_opts)
        async def tpl_cb(it):
            val = tpl_sel.values[0]
            await database.save_guild_setting(self.guild_id, "template_language", val)
            await load_guild_translations(self.guild_id)
            await self.refresh_message(it)
            await it.followup.send(t("MSG_SETTING_SAVED", guild_id=self.guild_id, key=t("LBL_TEMPLATE_LANG", guild_id=self.guild_id), val=val), ephemeral=True)
        tpl_sel.callback = tpl_cb

        back_btn = make_button(label=t("BTN_BACK", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def back_cb(it):
            v = ServerSetupView(self.bot, self.guild_id)
            await v.refresh_message(it)
        back_btn.callback = back_cb

        # 3. Final Assembly
        header = ui.Container(
            ui.TextDisplay(f"### {t('SETUP_GENERAL_TITLE', guild_id=self.guild_id)}\n{t('SETUP_GENERAL_DESC', guild_id=self.guild_id)}"),
            accent_color=0x40C4FF
        )
        self.add_item(header)
        self.add_item(ui.ActionRow(lang_hu, lang_en, roles_btn, channels_btn))
        self.add_item(ui.ActionRow(tpl_sel))
        self.add_item(ui.ActionRow(back_btn))

    async def refresh_message(self, interaction: discord.Interaction):
        """Standard interaction refresh: prepare self and update the message."""
        try:
            await self.prepare(interaction)
            
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            elif interaction.type == discord.InteractionType.component:
                await interaction.response.edit_message(view=self)
            else:
                await interaction.response.send_message(view=self, ephemeral=True)
        except Exception as e:
            log.error(f"[GeneralSetupView] refresh error: {e}", exc_info=True)
            msg = f"{ERROR} {e}"
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)

    async def _set_lang(self, interaction, lang):
        await database.save_guild_setting(self.guild_id, "language", lang)
        await load_guild_translations(self.guild_id) # Reload cache
        await self.refresh_message(interaction)
        await interaction.followup.send(t("MSG_SETTING_SAVED", guild_id=self.guild_id, key="Language", val=lang), ephemeral=True)

class MultiReminderOffsetModal(ui.Modal):
    def __init__(self, guild_id, current_val, parent_view):
        super().__init__(title=t("BTN_REMINDER_OFFSET", guild_id=guild_id)[:45])
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.inp = ui.TextInput(
            label=t("LBL_REMINDER_OFFSETS_PARAGRAPH", guild_id=guild_id)[:45],
            default=current_val or "15m",
            style=discord.TextStyle.paragraph,
            max_length=400,
            required=False,
        )
        self.add_item(self.inp)

    async def on_submit(self, interaction: discord.Interaction):
        raw_val = str(self.inp.value).strip()
        if not raw_val:
            # Set to default 15m or empty
            await database.save_guild_setting(self.guild_id, "default_reminder_offset", "")
            return await self.parent_view.refresh_message(interaction)

        lines = [x.strip() for x in raw_val.splitlines() if x.strip()]
        
        # Validation
        import re
        valid_pattern = re.compile(r"^(\d+)([mhd])(?:,([^,]*))?(?:,(.*))?$", re.IGNORECASE)
        for line in lines:
            if not valid_pattern.match(line):
                return await interaction.response.send_message(
                    t("ERR_INVALID_OFFSET_FORMAT", guild_id=self.guild_id),
                    ephemeral=True
                )
        
        # Save as newline-separated string (database compatible)
        final_val = "\n".join(lines[:5])
        await database.save_guild_setting(self.guild_id, "default_reminder_offset", final_val)
        await self.parent_view.refresh_message(interaction)

class ReminderSetupView(ui.LayoutView):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id

    async def prepare(self, interaction: discord.Interaction):
        """Asynchronously build the UI components and bind callbacks."""
        self.clear_items()

        back_btn = make_button(label=t("BTN_BACK", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def back_cb(it):
            v = ServerSetupView(self.bot, self.guild_id)
            await v.refresh_message(it)
        back_btn.callback = back_cb

        # Reminder Offset button
        offset_btn = make_button(label=t("BTN_REMINDER_OFFSET", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def offset_cb(it):
            curr = await database.get_guild_setting(self.guild_id, "default_reminder_offset", default="")
            modal = MultiReminderOffsetModal(self.guild_id, curr, self)
            await it.response.send_modal(modal)
        offset_btn.callback = offset_cb
        
        # Status Change Notification config
        cur_status_notify = await database.get_guild_setting(self.guild_id, "status_notification_type", default="none")
        status_opts = [
            make_select_option(label=t("OPT_NOTIFY_NONE", guild_id=self.guild_id) or "Semmi", value="none", default=(cur_status_notify=="none")),
            make_select_option(label=t("OPT_NOTIFY_DM", guild_id=self.guild_id) or "Csak DM", value="dm", default=(cur_status_notify=="dm")),
            make_select_option(label=t("OPT_NOTIFY_CHAT", guild_id=self.guild_id) or "Csak Ping", value="chat", default=(cur_status_notify=="chat")),
            make_select_option(label=t("OPT_NOTIFY_BOTH", guild_id=self.guild_id) or "Mindkettő", value="both", default=(cur_status_notify=="both")),
        ]
        status_sel = ui.Select(placeholder=t("PH_STATUS_NOTIFY", guild_id=self.guild_id) or "Státuszváltozás értesítő...", options=status_opts)
        async def status_sel_cb(it):
            val = status_sel.values[0]
            await database.save_guild_setting(self.guild_id, "status_notification_type", val)
            await self.refresh_message(it)
            await it.followup.send(t("MSG_SETTING_SAVED", guild_id=self.guild_id, key=t("LBL_PROMOTION_NOTIFY", guild_id=self.guild_id), val=val), ephemeral=True)
        status_sel.callback = status_sel_cb

        header = ui.Container(
            ui.TextDisplay(f"### {t('TITLE_SETUP_REMINDERS', guild_id=self.guild_id)}"),
            accent_color=0x40C4FF
        )
        self.add_item(header)
        self.add_item(ui.ActionRow(status_sel))
        self.add_item(ui.ActionRow(offset_btn, back_btn))

    async def refresh_message(self, interaction: discord.Interaction):
        """Standard interaction refresh: prepare self and update the message."""
        try:
            await self.prepare(interaction)
            
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            elif interaction.type == discord.InteractionType.component:
                await interaction.response.edit_message(view=self)
            else:
                await interaction.response.send_message(view=self, ephemeral=True)
        except Exception as e:
            log.error(f"[ReminderSetupView] refresh error: {e}", exc_info=True)
            msg = f"{ERROR} {e}"
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)

class EventDefaultsView(ui.LayoutView):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id

    async def prepare(self, interaction: discord.Interaction):
        """Asynchronously build the UI components and bind callbacks."""
        self.clear_items()
        
        # 1. Static Configuration Buttons
        channel_btn = make_button(label=t("BTN_DEFAULT_CHANNEL", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def channel_cb(it):
            curr = await database.get_guild_setting(self.guild_id, "default_event_channel", default="")
            modal = SimpleConfigModal(
                self.guild_id,
                "default_event_channel",
                t("LBL_SET_CHANNEL", guild_id=self.guild_id),
                placeholder=t("PH_CHANNEL_REF", guild_id=self.guild_id),
                default_val=curr,
                parent_view=self,
            )
            await it.response.send_modal(modal)
        channel_btn.callback = channel_cb

        max_acc_btn = make_button(label=t("BTN_DEFAULT_MAX_ACC", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def max_acc_cb(it):
            curr = await database.get_guild_setting(self.guild_id, "default_max_participants", default="0")
            modal = SimpleConfigModal(
                self.guild_id,
                "default_max_participants",
                t("LBL_SET_MAX_ACC", guild_id=self.guild_id),
                placeholder=t("PH_NUMBER_ZERO", guild_id=self.guild_id),
                default_val=curr,
                parent_view=self,
            )
            await it.response.send_modal(modal)
        max_acc_btn.callback = max_acc_cb

        back_btn = make_button(label=t("BTN_BACK", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def back_cb(it):
            v = ServerSetupView(self.bot, self.guild_id)
            await v.refresh_message(it)
        back_btn.callback = back_cb

        # 2. Toggle Toggles
        wait_val = await database.get_guild_setting(self.guild_id, "default_use_waiting_list", default="false")
        is_on = wait_val.lower() == "true"
        state_text = t("LBL_WAITLIST_ON", guild_id=self.guild_id) if is_on else t("LBL_WAITLIST_OFF", guild_id=self.guild_id)
        
        wait_btn = make_button(
            label=t("BTN_DEFAULT_WAITLIST", guild_id=self.guild_id, state=state_text),
            style=discord.ButtonStyle.success if is_on else discord.ButtonStyle.secondary
        )
        async def wait_cb(it):
            new_val = "false" if is_on else "true"
            await database.save_guild_setting(self.guild_id, "default_use_waiting_list", new_val)
            await self.refresh_message(it)
            await it.followup.send(t("MSG_SETTING_SAVED", guild_id=self.guild_id, key=t("LBL_WAITLIST_LIMIT", guild_id=self.guild_id), val=new_val), ephemeral=True)
        wait_btn.callback = wait_cb

        repost_btn = make_button(label=t("BTN_DEFAULT_REPOST", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def repost_cb(it):
            curr = await database.get_guild_setting(self.guild_id, "default_repost_offset", default="12h")
            modal = SimpleConfigModal(self.guild_id, "default_repost_offset", t("SETTING_REPOST_OFFSET", guild_id=self.guild_id), 
                                     placeholder=t("PH_DURATION", guild_id=self.guild_id), default_val=curr, parent_view=self)
            await it.response.send_modal(modal)
        repost_btn.callback = repost_cb

        cur_trig = await database.get_guild_setting(self.guild_id, "default_repost_trigger", default="after_end")
        trig_opts = [
            make_select_option(label=t("SEL_TRIG_BEFORE", guild_id=self.guild_id), value="before_start", default=(cur_trig=="before_start")),
            make_select_option(label=t("SEL_TRIG_AFTER_START", guild_id=self.guild_id), value="after_start", default=(cur_trig=="after_start")),
            make_select_option(label=t("SEL_TRIG_AFTER_END", guild_id=self.guild_id), value="after_end", default=(cur_trig=="after_end")),
        ]
        trig_sel = ui.Select(placeholder=t("SEL_TRIG_TYPE", guild_id=self.guild_id), options=trig_opts)
        async def trig_cb(it):
            val = trig_sel.values[0]
            await database.save_guild_setting(self.guild_id, "default_repost_trigger", val)
            await self.refresh_message(it)
            await it.followup.send(t("MSG_SETTING_SAVED", guild_id=self.guild_id, key=t("SEL_TRIG_TYPE", guild_id=self.guild_id), val=val), ephemeral=True)
        trig_sel.callback = trig_cb

        temp_val = await database.get_guild_setting(self.guild_id, "default_use_temp_role", default="false")
        is_temp_on = temp_val.lower() == "true"
        temp_state_text = t("LBL_TEMP_ROLE_ON", guild_id=self.guild_id) if is_temp_on else t("LBL_TEMP_ROLE_OFF", guild_id=self.guild_id)
        
        temp_role_btn = make_button(
            label=t("BTN_DEFAULT_TEMP_ROLE", guild_id=self.guild_id, state=temp_state_text),
            style=discord.ButtonStyle.success if is_temp_on else discord.ButtonStyle.secondary
        )
        async def temp_cb(it):
            new_val = "false" if is_temp_on else "true"
            await database.save_guild_setting(self.guild_id, "default_use_temp_role", new_val)
            await self.refresh_message(it)
            await it.followup.send(t("MSG_SETTING_SAVED", guild_id=self.guild_id, key=t("LBL_WIZ_TEMP_ROLE", guild_id=self.guild_id), val=new_val), ephemeral=True)
        temp_role_btn.callback = temp_cb

        # 3. Archive & Promotion Selection
        archive_val = await database.get_guild_setting(self.guild_id, "auto_archive_hours", default="12")
        archive_btn = make_button(label=f"{t('LBL_AUTO_ARCHIVE', guild_id=self.guild_id)}: {archive_val}h", emoji=to_emoji("⏱️"), style=discord.ButtonStyle.gray)
        async def archive_cb(it):
            modal = SimpleConfigModal(
                self.guild_id,
                "auto_archive_hours",
                t("LBL_SET_ARCHIVE_TIME", guild_id=self.guild_id),
                placeholder="12",
                default_val=archive_val,
                parent_view=self,
            )
            await it.response.send_modal(modal)
        archive_btn.callback = archive_cb

        cur_promo = await database.get_guild_setting(self.guild_id, "default_notify_promotion", default="none")
        promo_opts = [
            make_select_option(label=t("SEL_NOTIFY_NONE", guild_id=self.guild_id), value="none", default=(cur_promo=="none")),
            make_select_option(label=t("SEL_NOTIFY_CHANNEL", guild_id=self.guild_id), value="channel", default=(cur_promo=="channel")),
            make_select_option(label=t("SEL_NOTIFY_DM", guild_id=self.guild_id), value="dm", default=(cur_promo=="dm")),
            make_select_option(label=t("SEL_NOTIFY_BOTH", guild_id=self.guild_id), value="both", default=(cur_promo=="both")),
        ]
        promo_sel = ui.Select(placeholder=t("LBL_PROMOTION_NOTIFY", guild_id=self.guild_id), options=promo_opts)
        async def promo_cb(it):
            val = promo_sel.values[0]
            await database.save_guild_setting(self.guild_id, "default_notify_promotion", val)
            await self.refresh_message(it)
            await it.followup.send(t("MSG_SETTING_SAVED", guild_id=self.guild_id, key=t("LBL_PROMOTION_NOTIFY", guild_id=self.guild_id), val=val), ephemeral=True)
        promo_sel.callback = promo_cb

        # 4. Final Assembly
        header = ui.Container(
            ui.TextDisplay(f"### {t('TITLE_EVENT_DEFAULTS', guild_id=self.guild_id)}"),
            accent_color=0x40C4FF
        )
        self.add_item(header)
        # Row 1: Primary configuration buttons (Max 4 to leave room for clarity)
        self.add_item(ui.ActionRow(channel_btn, max_acc_btn, wait_btn, repost_btn))
        # Row 2: Secondary buttons + Navigation (3 buttons)
        self.add_item(ui.ActionRow(archive_btn, temp_role_btn, back_btn))
        # Row 3: Select menu 1 (MUST be alone)
        self.add_item(ui.ActionRow(trig_sel))
        # Row 4: Select menu 2 (MUST be alone)
        self.add_item(ui.ActionRow(promo_sel))

    async def refresh_message(self, interaction: discord.Interaction):
        """Standard interaction refresh: prepare self and update the message."""
        try:
            await self.prepare(interaction)
            
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            elif interaction.type == discord.InteractionType.component:
                await interaction.response.edit_message(view=self)
            else:
                await interaction.response.send_message(view=self, ephemeral=True)
        except Exception as e:
            log.error(f"[EventDefaultsView] refresh error: {e}", exc_info=True)
            msg = f"{ERROR} {e}"
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)

class SimpleConfigModal(ui.Modal):
    def __init__(self, guild_id, key, title, placeholder="", is_long=False, default_val="", parent_view=None):
        super().__init__(title=title[:45])
        self.guild_id = guild_id
        self.key = key
        self.parent_view = parent_view
        
        style = discord.TextStyle.paragraph if is_long else discord.TextStyle.short
        self.input_field = ui.TextInput(label=title[:45], placeholder=placeholder[:45], style=style, default=default_val, required=True)
        self.add_item(self.input_field)

    async def on_submit(self, interaction: discord.Interaction):
        val = str(self.input_field.value).strip()
        log.info(f"MODAL: Submitting key {self.key} with value {val} for GID {self.guild_id}")
        
        try:
            # 1. Save to database
            await database.save_guild_setting(self.guild_id, self.key, val)
            
            # 2. Trigger cache reload if it affects localization/auth context
            if self.key in ["language", "admin_role_ids", "admin_channel_ids"]:
                await load_guild_translations(self.guild_id)

            # 3. If parent view exists, refresh it in-place (this also handles the interaction response)
            if self.parent_view:
                await self.parent_view.refresh_message(interaction)
                # Success feedback after modal submit and refresh
                await interaction.followup.send(
                    t("MSG_SETTING_SAVED", guild_id=self.guild_id, key=self.key, val=val[:100]), 
                    ephemeral=True
                )
            else:
                # No parent view, just confirm
                await interaction.response.send_message(
                    t("MSG_SETTING_SAVED", guild_id=self.guild_id, key=self.key, val=val[:100]), 
                    ephemeral=True
                )
        except Exception as e:
            log.error(f"Error in modal submit for {self.key}: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"{ERROR} {t('ERR_SETTING_SAVE_FAILED', guild_id=self.guild_id, e=str(e))}",
                    ephemeral=True,
                )

async def setup(bot):
    # This cog primarily provides the view classes for other cogs to use.
    pass
