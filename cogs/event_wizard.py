import discord
from discord import ui
import uuid
import database
from utils.i18n import t
from utils.logger import log
import datetime
import time
import json
from dateutil import parser
from dateutil import tz
from utils.text_utils import slugify
from utils.templates import ICON_SET_TEMPLATES
from utils.emoji_utils import parse_emoji_config

class WizardStartView(ui.LayoutView):
    """Initial choice: Single vs Recurring using Components V2."""
    def __init__(self, bot, creator_id, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.creator_id = creator_id
        self.guild_id = guild_id

    async def refresh_message(self, interaction: discord.Interaction):
        # Create a FRESH instance to avoid stale interaction issues (Components V2 pattern)
        view = WizardStartView(self.bot, self.creator_id, self.guild_id)
        view.clear_items()
        
        guild_id = self.guild_id
        title = t("WIZARD_TITLE", guild_id=guild_id)
        desc = t("WIZARD_TYPE_DESC", guild_id=guild_id)
        
        # Action Buttons
        single_btn = ui.Button(
            label=t("BTN_SINGLE_EVENT", guild_id=guild_id),
            style=discord.ButtonStyle.secondary
        )
        async def single_cb(it):
            try:
                log.info(f"[Wizard] Single event button clicked by {it.user.id}")
                new_view = EventWizardView(self.bot, self.creator_id, guild_id=self.guild_id, wizard_type="single")
                await new_view.refresh_message(it)
            except Exception as e:
                log.error(f"[Wizard] Error in single_cb: {e}", exc_info=True)
                if not it.response.is_done():
                    await it.response.send_message(f"❌ {e}", ephemeral=True)

        single_btn.callback = single_cb
        
        recurring_btn = ui.Button(
            label=t("BTN_RECURRING_EVENT", guild_id=guild_id),
            style=discord.ButtonStyle.secondary
        )
        async def recurring_cb(it):
            try:
                log.info(f"[Wizard] Recurring series button clicked by {it.user.id}")
                new_view = EventWizardView(self.bot, self.creator_id, guild_id=self.guild_id, wizard_type="series")
                await new_view.refresh_message(it)
            except Exception as e:
                log.error(f"[Wizard] Error in recurring_cb: {e}", exc_info=True)
                if not it.response.is_done():
                    await it.response.send_message(f"❌ {e}", ephemeral=True)

        recurring_btn.callback = recurring_cb
        
        row = ui.ActionRow(single_btn, recurring_btn)
        
        container = ui.Container(
            ui.TextDisplay(f"### {title}"),
            ui.Separator(),
            ui.TextDisplay(desc),
            ui.Separator(),
            row,
            accent_color=0x00bfff
        )
        view.add_item(container)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(content=None, embeds=[], view=view)
        elif interaction.type == discord.InteractionType.component:
            await interaction.response.edit_message(content=None, embeds=[], view=view)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

class SingleEventModal(ui.Modal):
    """Fast-track modal combining Step 1 and parts of Step 2."""
    def __init__(self, wizard_view):
        super().__init__(title=t("TITLE_BASIC_INFO", guild_id=wizard_view.guild_id))
        self.wizard_view = wizard_view
        data = wizard_view.data
        guild_id = self.wizard_view.guild_id

        self.title_input = ui.TextInput(label=t("LBL_WIZ_TITLE", guild_id=guild_id), default=str(data.get("title") or ""), required=True)
        self.desc_input = ui.TextInput(label=t("LBL_WIZ_DESC", guild_id=guild_id), style=discord.TextStyle.paragraph, default=str(data.get("description") or ""), required=False)
        self.start_input = ui.TextInput(label=t("LBL_WIZ_START", guild_id=guild_id), placeholder=t("PH_DATETIME", guild_id=guild_id), default=str(data.get("start_str") or ""), required=True)
        self.end_input = ui.TextInput(label=f"{t('LBL_WIZ_END', guild_id=guild_id)} {t('LBL_OPTIONAL', guild_id=guild_id)}", placeholder=t("PH_DATETIME", guild_id=guild_id), default=str(data.get("end_str") or ""), required=False)
        self.images_input = ui.TextInput(label=t("LBL_WIZ_IMAGES", guild_id=guild_id), default=str(data.get("image_urls") or ""), required=False)

        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.start_input)
        self.add_item(self.end_input)
        self.add_item(self.images_input)

    async def on_submit(self, interaction: discord.Interaction):
        title = str(self.title_input.value)
        self.wizard_view.data["title"] = title
        self.wizard_view.data["config_name"] = slugify(title) or "event"
        self.wizard_view.data["description"] = str(self.desc_input.value)
        self.wizard_view.data["start_str"] = str(self.start_input.value)
        self.wizard_view.data["end_str"] = str(self.end_input.value)
        self.wizard_view.data["image_urls"] = str(self.images_input.value)
        
        self.wizard_view.steps_completed["step1"] = True
        self.wizard_view.steps_completed["step2"] = True
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class Step1Modal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=(t("BTN_STEP_1", guild_id=wizard_view.guild_id)[:45]))
        self.wizard_view = wizard_view
        data = wizard_view.data
        guild_id = self.wizard_view.guild_id
        
        self.title_input = ui.TextInput(label=t("LBL_WIZ_TITLE", guild_id=guild_id), default=str(data.get("title") or ""), required=True)
        self.waitlist_limit = ui.TextInput(label=t("LBL_WAITLIST_LIMIT", guild_id=guild_id), default=str(data.get("waitlist_limit", 0)), required=True)
        self.desc_input = ui.TextInput(label=t("LBL_WIZ_DESC", guild_id=guild_id), style=discord.TextStyle.paragraph, default=str(data.get("description") or ""), required=False)
        self.images_input = ui.TextInput(label=t("LBL_WIZ_IMAGES", guild_id=guild_id), default=str(data.get("image_urls") or ""), required=False)
        self.channel_id_input = ui.TextInput(label=t("LBL_CHANNEL_ID", guild_id=guild_id), placeholder=t("PH_CURRENT_CHANNEL", guild_id=guild_id), default=str(data.get("channel_id") or ""), required=False)
        
        self.add_item(self.title_input)
        self.add_item(self.waitlist_limit)
        self.add_item(self.desc_input)
        self.add_item(self.images_input)
        self.add_item(self.channel_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        title = str(self.title_input.value)
        self.wizard_view.data["title"] = title
        if not self.wizard_view.data.get("config_name") or self.wizard_view.data.get("config_name") == "manual":
            self.wizard_view.data["config_name"] = slugify(title) or "event"
        self.wizard_view.data["description"] = str(self.desc_input.value)
        self.wizard_view.data["image_urls"] = str(self.images_input.value)
        self.wizard_view.data["channel_id"] = str(self.channel_id_input.value)
        self.wizard_view.steps_completed["step1"] = True
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class Step2Modal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=(t("BTN_STEP_2", guild_id=wizard_view.guild_id)[:45]))
        self.wizard_view = wizard_view
        data = wizard_view.data
        guild_id = self.wizard_view.guild_id

        self.color_input = ui.TextInput(label=t("LBL_WIZ_COLOR", guild_id=guild_id), default=str(data.get("color") or "0x3498db"), required=False)
        self.max_acc_input = ui.TextInput(label=t("LBL_WIZ_MAX", guild_id=guild_id), default=str(data.get("max_accepted") or 0), required=False)
        self.ping_input = ui.TextInput(label=t("LBL_WIZ_PING", guild_id=guild_id), default=str(data.get("ping_role") or ""), required=False)
        self.start_input = ui.TextInput(label=t("LBL_WIZ_START", guild_id=guild_id), placeholder=t("PH_DATETIME", guild_id=guild_id), default=str(data.get("start_str") or ""), required=True)
        self.end_input = ui.TextInput(label=f"{t('LBL_WIZ_END', guild_id=guild_id)} {t('LBL_OPTIONAL', guild_id=guild_id)}", placeholder=t("PH_DATETIME", guild_id=guild_id), default=str(data.get("end_str") or ""), required=False)

        self.add_item(self.color_input)
        self.add_item(self.max_acc_input)
        self.add_item(self.ping_input)
        self.add_item(self.start_input)
        self.add_item(self.end_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.data["color"] = str(self.color_input.value)
        self.wizard_view.data["max_accepted"] = int(self.max_acc_input.value) if str(self.max_acc_input.value).isdigit() else 0
        self.wizard_view.data["ping_role"] = int(self.ping_input.value) if str(self.ping_input.value).isdigit() else 0
        self.wizard_view.data["start_str"] = str(self.start_input.value)
        self.wizard_view.data["end_str"] = str(self.end_input.value)
        self.wizard_view.steps_completed["step2"] = True
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class Step3Modal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=(t("SEL_TRIG_TYPE", guild_id=wizard_view.guild_id)[:45]))
        self.wizard_view = wizard_view
        data = wizard_view.data
        guild_id = self.wizard_view.guild_id

        self.timezone_input = ui.TextInput(label=t("LBL_WIZ_TZ", guild_id=guild_id), default=str(data.get("timezone") or "Europe/Budapest"), required=True)
        self.cleanup_offset = ui.TextInput(label=t("LBL_CLEANUP_OFFSET", guild_id=guild_id), placeholder="4h", default=data.get("cleanup_offset", "4h"), required=True)
        def_offset = data.get("reminder_offset", "15m")
        self.rem_offset = ui.TextInput(label=t("LBL_REMINDER_OFFSET", guild_id=guild_id), placeholder=t("PH_REMINDER_OFFSET", guild_id=guild_id), default=def_offset, required=True)
        self.rec_limit = ui.TextInput(label=t("LBL_RECURRENCE_LIMIT", guild_id=guild_id), default=str(data.get("recurrence_limit", 0)), required=True)
        self.rem_type = ui.TextInput(label=t("LBL_REMINDER_TYPE", guild_id=guild_id), default=data.get("reminder_type", "none"), required=True)

        self.add_item(self.timezone_input)
        self.add_item(self.cleanup_offset)
        self.add_item(self.rem_offset)
        self.add_item(self.rec_limit)
        self.add_item(self.rem_type)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.data["timezone"] = str(self.timezone_input.value)
        self.wizard_view.data["repost_offset"] = str(self.cleanup_offset.value)
        self.wizard_view.data["reminder_offset"] = str(self.rem_offset.value)
        self.wizard_view.data["recurrence_limit"] = int(self.rec_limit.value) if str(self.rec_limit.value).isdigit() else 0
        self.wizard_view.data["reminder_type"] = str(self.rem_type.value).lower()
        self.wizard_view.steps_completed["step3"] = True
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class AdvancedSettingsModal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=t("TITLE_ADVANCED_SETTINGS", guild_id=wizard_view.guild_id))
        self.wizard_view = wizard_view
        data = wizard_view.data
        self.creator_input = ui.TextInput(label=t("LBL_WIZ_CREATOR", guild_id=wizard_view.guild_id), default=str(data.get("creator_id") or wizard_view.creator_id), required=False)
        self.wait_limit_input = ui.TextInput(label=t("LBL_WAITLIST_LIMIT", guild_id=wizard_view.guild_id), default=str(data.get("waiting_list_limit") or 0), required=False)
        self.add_item(self.creator_input)
        self.add_item(self.wait_limit_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.data["creator_id"] = str(self.creator_input.value)
        val = str(self.wait_limit_input.value)
        wait_limit = int(val) if val.isdigit() else 0
        extra = self.wizard_view.data.get("extra_data", {})
        if isinstance(extra, str): extra = json.loads(extra)
        extra["waiting_list_limit"] = wait_limit
        self.wizard_view.data["extra_data"] = json.dumps(extra)
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class RoleLimitsModal(ui.Modal):
    def __init__(self, wizard_view, icon_set_data):
        super().__init__(title=t("WIZARD_LIMITS_TITLE", guild_id=wizard_view.guild_id))
        self.wizard_view = wizard_view
        self.options = icon_set_data.get("options", [])
        extra_data = wizard_view.data.get("extra_data")
        existing_limits = {}
        if extra_data:
            try: existing_limits = json.loads(extra_data).get("role_limits", {})
            except: pass
        self.inputs = {}
        for opt in self.options[:5]:
            role_id = opt["id"]
            field_label = f"{opt.get('emoji', '')} {opt.get('label') or role_id}"[:45]
            text_input = ui.TextInput(label=field_label, default=str(existing_limits.get(role_id, opt.get("max_slots", ""))), required=False)
            self.inputs[role_id] = text_input
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction):
        role_limits = {rid: (int(ti.value) if ti.value.isdigit() else 0) for rid, ti in self.inputs.items()}
        extra = self.wizard_view.data.get("extra_data", {})
        if isinstance(extra, str): extra = json.loads(extra)
        extra["role_limits"] = role_limits
        self.wizard_view.data["extra_data"] = json.dumps(extra)
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class NotificationSettingsModal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=t("WIZARD_MESSAGES_TITLE", guild_id=wizard_view.guild_id))
        self.wizard_view = wizard_view
        extra = wizard_view.data.get("extra_data", {})
        if isinstance(extra, str): extra = json.loads(extra)
        self.promo_input = ui.TextInput(label=t("LBL_PROMO_MSG", guild_id=wizard_view.guild_id), default=extra.get("custom_promo_msg", ""), style=discord.TextStyle.paragraph, required=False)
        self.rem_input = ui.TextInput(label=t("LBL_REMINDER_MSG", guild_id=wizard_view.guild_id), default=extra.get("custom_reminder_msg", ""), style=discord.TextStyle.paragraph, required=False)
        self.add_item(self.promo_input)
        self.add_item(self.rem_input)

    async def on_submit(self, interaction: discord.Interaction):
        extra = self.wizard_view.data.get("extra_data", {})
        if isinstance(extra, str): extra = json.loads(extra)
        extra["custom_promo_msg"] = self.promo_input.value
        extra["custom_reminder_msg"] = self.rem_input.value
        self.wizard_view.data["extra_data"] = json.dumps(extra)
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class EventWizardView(ui.LayoutView):
    """Main wizard controller using Components V2 architecture."""
    def __init__(self, bot, creator_id, existing_data=None, is_edit=False, guild_id=None, bulk_ids=None, wizard_type="series"):
        super().__init__(timeout=600)
        self.bot = bot
        self.creator_id = creator_id
        self.is_edit = is_edit
        self.guild_id = guild_id
        self.bulk_ids = bulk_ids
        self.wizard_type = wizard_type
        self.data = existing_data or {}
        self.can_publish = False
        self.steps_completed = {
            "step1": bool(self.data.get("title") or self.data.get("config_name")),
            "step2": bool(self.data.get("start_str") or self.data.get("start_time")),
            "step3": bool(self.data.get("repost_offset"))
        }

    async def refresh_message(self, interaction: discord.Interaction):
        view = EventWizardView(self.bot, self.creator_id, existing_data=self.data, is_edit=self.is_edit, guild_id=self.guild_id, bulk_ids=self.bulk_ids, wizard_type=self.wizard_type)
        view.can_publish = self.can_publish
        view.clear_items()
        await view.refresh_ui_data()
        
        # 2. Build Component Rows
        # Row 0: Wizard Steps
        async def s1_cb(it):
            if view.wizard_type == "single": await it.response.send_modal(SingleEventModal(view))
            else: await it.response.send_modal(Step1Modal(view))
        step1 = ui.Button(label=t("BTN_STEP_1", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        step1.callback = s1_cb

        async def s2_cb(it):
            if view.wizard_type == "single": return await it.response.send_message(t("MSG_SINGLE_EVENT_HINT", guild_id=self.guild_id), ephemeral=True)
            await it.response.send_modal(Step2Modal(view))
        step2 = ui.Button(label=t("BTN_STEP_2", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        step2.callback = s2_cb

        async def s3_cb(it):
            if view.wizard_type == "single": return await it.response.send_message(t("MSG_RECURRING_ONLY_HINT", guild_id=self.guild_id), ephemeral=True)
            await it.response.send_modal(Step3Modal(view))
        step3 = ui.Button(label=t("BTN_STEP_3", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        step3.callback = s3_cb

        async def s4_cb(it): await it.response.send_modal(AdvancedSettingsModal(view))
        step4 = ui.Button(label=t("BTN_STEP_4", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        step4.callback = s4_cb

        # Row 1: Advanced
        async def role_cb(it):
            from cogs.event_ui import get_active_set
            active_set = get_active_set(view.data.get("icon_set", "standard"))
            await it.response.send_modal(RoleLimitsModal(view, active_set))
        role_btn = ui.Button(label=t("BTN_ROLE_LIMITS", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        role_btn.callback = role_cb

        async def msg_cb(it): await it.response.send_modal(NotificationSettingsModal(view))
        msg_btn = ui.Button(label=t("BTN_MESSAGES", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        msg_btn.callback = msg_cb

        async def wait_cb(it):
            view.data["use_waiting_list"] = not view.data.get("use_waiting_list", False)
            await view.save_to_draft()
            await view.refresh_message(it)
        use_waiting = view.data.get("use_waiting_list", False)
        wait_btn = ui.Button(label=t("SEL_WAIT_ENABLED" if use_waiting else "SEL_WAIT_DISABLED", guild_id=self.guild_id), style=discord.ButtonStyle.green if use_waiting else discord.ButtonStyle.gray)
        wait_btn.callback = wait_cb

        async def save_cb(it): await view.handle_save_preview(it)
        save_btn = ui.Button(label=t("BTN_SAVE_PREVIEW", guild_id=self.guild_id), style=discord.ButtonStyle.primary, disabled=view.can_publish)
        save_btn.callback = save_cb

        # Selects
        sel_rec = ui.Select(placeholder=t("SEL_REC_TYPE", guild_id=self.guild_id), options=view.recurrence_options)
        async def rec_cb(it):
            view.data["recurrence_type"] = sel_rec.values[0]
            await view.save_to_draft()
            await view.refresh_message(it)
        sel_rec.callback = rec_cb

        sel_icon = ui.Select(placeholder=t("SEL_ICON_SET", guild_id=self.guild_id), options=view.icon_set_options)
        async def icon_cb(it):
            view.data["icon_set"] = sel_icon.values[0]
            await view.save_to_draft()
            await view.refresh_message(it)
        sel_icon.callback = icon_cb

        # Container
        title_text = f"### {t('WIZARD_TITLE', guild_id=self.guild_id)}"
        if view.bulk_ids: title_text += f" {t('LBL_BULK_EDIT', guild_id=self.guild_id)}"
        
        container_items = [
            ui.TextDisplay(title_text),
            ui.Separator(),
            ui.TextDisplay(t("WIZARD_DESC", guild_id=self.guild_id, status=view.get_status_text())),
            ui.Separator(),
            ui.ActionRow(step1, step2, step3, step4),
            ui.ActionRow(role_btn, msg_btn, wait_btn, save_btn)
        ]
        if view.wizard_type == "series":
            container_items.extend([ui.Separator(), ui.ActionRow(sel_rec)])
        container_items.extend([ui.Separator(), ui.ActionRow(sel_icon)])

        if view.can_publish:
            pub_btn = ui.Button(label=t("BTN_PUBLISH", guild_id=self.guild_id), style=discord.ButtonStyle.green)
            async def pub_cb(it): await view.publish_btn(it)
            pub_btn.callback = pub_cb
            container_items.extend([ui.Separator(), ui.ActionRow(pub_btn)])

        view.add_item(ui.Container(*container_items, accent_color=0x00bfff))
        
        if interaction.response.is_done(): await interaction.edit_original_response(content=None, embeds=[], view=view)
        else: await interaction.response.edit_message(content=None, embeds=[], view=view)

    async def refresh_ui_data(self):
        current_set = self.data.get("icon_set", "standard")
        current_rec = self.data.get("recurrence_type", "none")
        
        # Load server-level defaults if missing in data
        if "reminder_offset" not in self.data:
            self.data["reminder_offset"] = await database.get_guild_setting(self.guild_id, "default_reminder_offset", default="15m")
        if "reminder_type" not in self.data:
            self.data["reminder_type"] = await database.get_guild_setting(self.guild_id, "reminder_type", default="none")
        if "color" not in self.data:
            self.data["color"] = await database.get_guild_setting(self.guild_id, "default_color", default="0x3498db")
        if "timezone" not in self.data:
            self.data["timezone"] = await database.get_guild_setting(self.guild_id, "timezone", default="Europe/Budapest")
        
        # Build options for hardcoded templates
        self.icon_set_options = []
        for k, v in ICON_SET_TEMPLATES.items():
            opts, _ = parse_emoji_config(v["text"])
            preview_emojis = [o["emoji"] for o in opts[:3]]
            preview_str = f" ( {' / '.join(preview_emojis)} )" if preview_emojis else ""
            label = t(v["label_key"], guild_id=self.guild_id) + preview_str
            
            self.icon_set_options.append(discord.SelectOption(
                label=label[:100], 
                value=k, 
                emoji=v["emoji"] or None, 
                default=(current_set == k)
            ))
            
        # Build options for DB-based sets
        db_sets = await database.get_emoji_sets(self.guild_id)
        for s in db_sets:
            if s["set_id"] in ICON_SET_TEMPLATES: continue
            
            sdata = json.loads(s["data"]) if isinstance(s["data"], str) else s["data"]
            opts = sdata.get("options", [])
            preview_emojis = [o.get("emoji") or "?" for o in opts[:3]]
            preview_str = f" ( {' / '.join(preview_emojis)} )" if preview_emojis else ""
            label = (s["name"][:30] + preview_str)[:100]
            
            self.icon_set_options.append(discord.SelectOption(
                label=label, 
                value=s["set_id"], 
                default=(current_set == s["set_id"])
            ))
            
        self.recurrence_options = [discord.SelectOption(label=t(f"SEL_REC_{k.upper()}", guild_id=self.guild_id), value=k, emoji=e, default=(current_rec == k)) for k, e in [("none", "❌"), ("daily", "📅"), ("weekly", "🗓️"), ("monthly", "📊")]]

    def get_status_text(self):
        s1 = "✅" if self.steps_completed["step1"] else "⏳"
        s2 = "✅" if self.steps_completed["step2"] else "⏳"
        s3 = "✅" if self.steps_completed["step3"] else "⏳"
        return f"- {t('BTN_STEP_1', guild_id=self.guild_id)}: {s1}\n- {t('BTN_STEP_2', guild_id=self.guild_id)}: {s2}\n- Template: {s3}"

    async def save_to_draft(self):
        if not self.data.get("draft_id"): self.data["draft_id"] = str(uuid.uuid4())[:8]
        await database.save_draft(self.guild_id, self.data["draft_id"], self.creator_id, self.data.get("title") or "manual", self.data)

    async def handle_save_preview(self, interaction: discord.Interaction):
        """Processes the Save & Preview logic and updates the V2 UI."""
        if not self.steps_completed["step1"] or not self.steps_completed["step2"]:
            await interaction.response.send_message(t("ERR_FILL_STEPS", guild_id=self.guild_id), ephemeral=True)
            return

        clean_data = {}
        for k, v in self.data.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                clean_data[k] = v
            elif isinstance(v, list):
                clean_data[k] = ",".join(str(i) for i in v)
            else:
                clean_data[k] = str(v)
        self.data = clean_data

        try:
            local_tz = tz.gettz(str(self.data.get("timezone") or "Europe/Budapest"))
            start_dt = parser.parse(str(self.data["start_str"])).replace(tzinfo=local_tz)
            self.data["start_time"] = start_dt.timestamp()
            
            if self.data.get("end_str"):
                end_dt = parser.parse(str(self.data["end_str"])).replace(tzinfo=local_tz)
                self.data["end_time"] = end_dt.timestamp()
            else:
                self.data["end_time"] = None
        except Exception as e:
            await interaction.response.send_message(t("ERR_DATE_TZ", guild_id=self.guild_id, e=str(e)), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        try:
            from cogs.event_ui import DynamicEventView
            event_id = str(self.data.get("event_id") or str(uuid.uuid4())[:8])
            self.data["event_id"] = event_id
            
            if self.is_edit:
                if "creator_id" not in self.data:
                    self.data["creator_id"] = str(self.creator_id)

                if self.bulk_ids:
                    await database.update_active_events_metadata_bulk(self.bulk_ids, self.data)
                else:
                    await database.update_active_event(event_id, self.data)
            else:
                self.data["creator_id"] = str(self.data.get("creator_id") or self.creator_id)
                self.data["guild_id"] = self.guild_id
                
                target_channel_id = interaction.channel_id
                if self.data.get("channel_id") and str(self.data["channel_id"]).isdigit():
                    target_channel_id = int(self.data["channel_id"])

                await database.create_active_event(
                    guild_id=self.guild_id,
                    event_id=event_id,
                    config_name=str(self.data.get("config_name") or "manual"),
                    channel_id=target_channel_id,
                    start_time=self.data["start_time"],
                    data=self.data
                )

            self.can_publish = True
            
            view = DynamicEventView(self.bot, event_id, self.data)
            embed = await view.generate_embed()
            
            global_max = int(self.data.get("max_accepted") or 0)
            role_sum = 0
            
            from cogs.event_ui import get_active_set
            icon_set_key = self.data.get("icon_set", "standard")
            active_set = get_active_set(icon_set_key)
            
            extra_data = self.data.get("extra_data")
            role_limits_overrides = {}
            if extra_data:
                try:
                    d = json.loads(extra_data) if isinstance(extra_data, str) else extra_data
                    role_limits_overrides = d.get("role_limits", {})
                except: pass
            
            pos_statuses = []
            if "positive" in active_set:
                pos_statuses = active_set["positive"]
            elif "positive_count" in active_set:
                cnt = active_set["positive_count"]
                pos_statuses = [o["id"] for o in active_set["options"][:cnt]]
            
            for opt in active_set.get("options", []):
                rid = opt["id"]
                if rid in pos_statuses:
                    limit = role_limits_overrides.get(rid, opt.get("max_slots", 0))
                    role_sum += (limit or 0)
            
            warning = ""
            if global_max > 0 and role_sum > 0 and global_max != role_sum:
                warning = f"\n\n⚠️ **Figyelem:** A szerepkörök összege (**{role_sum}**) nem egyezik a globális limittel (**{global_max}**)."
                if role_sum < global_max:
                    warning += f"\nAz esemény már **{role_sum}** főnél meg fog telni, mert a szerepkörök betelnek."
                else:
                    warning += f"\nNéhány szerepkör gombja váratlanul kikapcsolhat **{global_max}** főnél."

            await interaction.followup.send(t("MSG_SAVED_PREVIEW", guild_id=self.guild_id) + warning, embed=embed, ephemeral=True)
            await self.refresh_message(interaction)
        except Exception as e:
            log.error(f"Error in handle_save_preview: {e}")
            await interaction.followup.send(f"❌ Error during save: {e}", ephemeral=True)

    async def publish_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        from cogs.event_ui import DynamicEventView
        event_id = self.data["event_id"]
        
        if self.is_edit:
            target_ids = self.bulk_ids if self.bulk_ids else [event_id]
            
            for eid in target_ids:
                curr_db_event = await database.get_active_event(eid, self.guild_id)
                if curr_db_event and curr_db_event.get("message_id") and curr_db_event.get("channel_id"):
                    channel = self.bot.get_channel(curr_db_event["channel_id"])
                    if channel:
                        try:
                            msg = await channel.fetch_message(curr_db_event["message_id"])
                            view = DynamicEventView(self.bot, eid, self.data)
                            embed = await view.generate_embed(curr_db_event)
                            await msg.edit(embed=embed, view=view)
                        except Exception as e:
                            log.error(f"Error updating message {eid}: {e}")
            
            msg_text = t("MSG_BULK_UPDATE_DONE", guild_id=self.guild_id) if self.bulk_ids else t("MSG_UPDATED", guild_id=self.guild_id)
            await interaction.followup.send(msg_text, ephemeral=True)
        else:
            view = DynamicEventView(self.bot, event_id, self.data)
            embed = await view.generate_embed()
            
            target_chan = interaction.channel
            if self.data.get("channel_id") and str(self.data["channel_id"]).isdigit():
                chan = self.bot.get_channel(int(self.data["channel_id"]))
                if chan:
                    target_chan = chan
                else:
                    try:
                        target_chan = await self.bot.fetch_channel(int(self.data["channel_id"]))
                    except:
                        pass
            
            msg = await target_chan.send(content=t("MSG_DEFAULT_PROMO", guild_id=self.guild_id), embed=embed, view=view)
            await database.set_event_message(event_id, msg.id)
            self.bot.add_view(view)
            await interaction.followup.send(f"Published in <#{target_chan.id}>!", ephemeral=True)

        await interaction.edit_original_response(content=None, view=None)
        self.stop()
        await database.delete_draft(self.data.get("draft_id"), self.guild_id)
