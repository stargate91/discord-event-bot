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

class WizardStartView(ui.LayoutView):
    """Initial choice: Single vs Recurring using Components V2."""
    def __init__(self, bot, creator_id, guild_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.creator_id = creator_id
        self.guild_id = guild_id

    async def refresh_message(self, interaction: discord.Interaction):
        self.clear_items()
        guild_id = self.guild_id
        
        # Localized content
        title = t("WIZARD_TITLE", guild_id=guild_id)
        desc = t("WIZARD_TYPE_DESC", guild_id=guild_id)
        
        # Action Buttons
        single_btn = ui.Button(
            label=t("BTN_SINGLE_EVENT", guild_id=guild_id),
            style=discord.ButtonStyle.primary
        )
        async def single_cb(it):
            view = EventWizardView(self.bot, self.creator_id, guild_id=self.guild_id, wizard_type="single")
            await view.refresh_ui()
            status = view.get_status_text()
            embed = discord.Embed(
                title=t("TITLE_SINGLE_EVENT", guild_id=self.guild_id), 
                description=t("WIZARD_DESC", guild_id=self.guild_id, status=status), 
                color=discord.Color.blue()
            )
            await it.response.edit_message(embed=embed, view=view)
        single_btn.callback = single_cb
        
        recurring_btn = ui.Button(
            label=t("BTN_RECURRING_EVENT", guild_id=guild_id),
            style=discord.ButtonStyle.secondary
        )
        async def recurring_cb(it):
            view = EventWizardView(self.bot, self.creator_id, guild_id=self.guild_id, wizard_type="series")
            await view.refresh_ui()
            status = view.get_status_text()
            embed = discord.Embed(
                title=t("TITLE_RECURRING_EVENT", guild_id=self.guild_id), 
                description=t("WIZARD_DESC", guild_id=self.guild_id, status=status), 
                color=discord.Color.blue()
            )
            await it.response.edit_message(embed=embed, view=view)
        recurring_btn.callback = recurring_cb
        
        row = ui.ActionRow(single_btn, recurring_btn)
        
        # Build Container
        container = ui.Container(
            ui.TextDisplay(f"### {title}"),
            ui.Separator(),
            ui.TextDisplay(desc),
            ui.Separator(),
            row,
            accent_color=0x00bfff
        )
        self.add_item(container)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embeds=[], view=self)
        elif interaction.type == discord.InteractionType.component:
            await interaction.response.edit_message(embeds=[], view=self)
        else:
            await interaction.response.send_message(view=self, ephemeral=True)

class SingleEventModal(ui.Modal):
    """Fast-track modal combining Step 1 and parts of Step 2."""
    def __init__(self, wizard_view):
        super().__init__(title=t("TITLE_BASIC_INFO", guild_id=wizard_view.guild_id))
        self.wizard_view = wizard_view
        data = wizard_view.data
        guild_id = self.wizard_view.guild_id

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
        
        # Mark as completed
        self.wizard_view.steps_completed["step1"] = True
        self.wizard_view.steps_completed["step2"] = True
        await self.wizard_view.update_message(interaction)

class Step1Modal(ui.Modal):
    # This pop-up handles the basic info like the name and title
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
            base_slug = slugify(title) or "event"
            final_slug = base_slug
            
            if not self.wizard_view.is_edit:
                counter = 2
                while await database.check_config_exists(self.wizard_view.guild_id, final_slug):
                    final_slug = f"{base_slug}-{counter}"
                    counter += 1
            
            self.wizard_view.data["config_name"] = final_slug

        self.wizard_view.data["description"] = str(self.desc_input.value)
        self.wizard_view.data["image_urls"] = str(self.images_input.value)
        self.wizard_view.data["channel_id"] = str(self.channel_id_input.value)
        self.wizard_view.steps_completed["step1"] = True
        await self.wizard_view.update_message(interaction)

class Step2Modal(ui.Modal):
    # This pop-up handles technical things like colors and dates
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
        try:
            self.wizard_view.data["color"] = str(self.color_input.value)
            self.wizard_view.data["max_accepted"] = int(self.max_acc_input.value) if str(self.max_acc_input.value).isdigit() else 0
            self.wizard_view.data["ping_role"] = int(self.ping_input.value) if str(self.ping_input.value).isdigit() else 0
            self.wizard_view.data["start_str"] = str(self.start_input.value)
            self.wizard_view.data["end_str"] = str(self.end_input.value)
            self.wizard_view.steps_completed["step2"] = True
            await self.wizard_view.save_to_draft()
            await self.wizard_view.update_message(interaction)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(t("ERR_WIZARD_GENERAL", guild_id=self.wizard_view.guild_id, e=e), ephemeral=True)

class Step3Modal(ui.Modal):
    # This pop-up handles notifications and limits
    def __init__(self, wizard_view):
        super().__init__(title=(t("SEL_TRIG_TYPE", guild_id=wizard_view.guild_id)[:45]))
        self.wizard_view = wizard_view
        data = wizard_view.data
        guild_id = self.wizard_view.guild_id

        self.timezone_input = ui.TextInput(
            label=t("LBL_WIZ_TZ", guild_id=guild_id),
            default=str(data.get("timezone") or "Europe/Budapest"),
            required=True
        )
        self.cleanup_offset = ui.TextInput(label=t("LBL_CLEANUP_OFFSET", guild_id=guild_id), placeholder=t("PH_DURATION", guild_id=guild_id), default=data.get("cleanup_offset", "4h"), required=True)
        self.rem_offset = ui.TextInput(label=t("LBL_REMINDER_OFFSET", guild_id=guild_id), placeholder=t("PH_DURATION", guild_id=guild_id), default=data.get("reminder_offset", "15m"), required=True)
        self.rec_limit = ui.TextInput(label=t("LBL_RECURRENCE_LIMIT", guild_id=guild_id), placeholder=t("PH_LIMIT", guild_id=guild_id), default=str(data.get("recurrence_limit", 0)), required=True)
        self.rem_type = ui.TextInput(label=t("LBL_REMINDER_TYPE", guild_id=guild_id), placeholder=t("PH_REMINDER", guild_id=guild_id), default=data.get("reminder_type", "none"), required=True)

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
        await self.wizard_view.update_message(interaction)

class AdvancedSettingsModal(ui.Modal):
    """Fourth modal for technical things like Creator ID and Waiting List properties."""
    def __init__(self, wizard_view):
        super().__init__(title=t("TITLE_ADVANCED_SETTINGS", guild_id=wizard_view.guild_id))
        self.wizard_view = wizard_view
        data = wizard_view.data
        guild_id = self.wizard_view.guild_id

        self.creator_input = ui.TextInput(
            label=t("LBL_WIZ_CREATOR", guild_id=guild_id), 
            default=str(data.get("creator_id") or wizard_view.creator_id), 
            required=False
        )
        self.wait_limit_input = ui.TextInput(
            label=t("LBL_WAITLIST_LIMIT", guild_id=guild_id),
            placeholder="e.g. 10",
            default=str(data.get("waiting_list_limit") or 0),
            required=False
        )

        self.add_item(self.creator_input)
        self.add_item(self.wait_limit_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.data["creator_id"] = str(self.creator_input.value)
        val = str(self.wait_limit_input.value)
        wait_limit = int(val) if val.isdigit() else 0
        
        extra_data_raw = self.wizard_view.data.get("extra_data")
        extra_dict = {}
        if extra_data_raw:
            try:
                if isinstance(extra_data_raw, str):
                    extra_dict = json.loads(extra_data_raw)
                else:
                    extra_dict = extra_data_raw
            except: pass
            
        extra_dict["waiting_list_limit"] = wait_limit
        self.wizard_view.data["extra_data"] = json.dumps(extra_dict)
        
        await interaction.response.send_message(t("MSG_ADVANCED_SAVED", guild_id=self.wizard_view.guild_id), ephemeral=True)
        await self.wizard_view.save_to_draft()
        await self.wizard_view.update_message(interaction)

class RoleLimitsModal(ui.Modal):
    # This pop-up allows setting per-role capacities dynamically
    def __init__(self, wizard_view, icon_set_data):
        super().__init__(title=(t("WIZARD_LIMITS_TITLE", guild_id=wizard_view.guild_id)[:45]))
        self.wizard_view = wizard_view
        self.options = icon_set_data.get("options", [])
        
        extra_data = wizard_view.data.get("extra_data")
        existing_limits = {}
        if extra_data:
            try:
                existing_limits = json.loads(extra_data).get("role_limits", {})
            except: pass
            
        self.inputs = {}
        for opt in self.options[:5]:
            role_id = opt["id"]
            label = opt.get("label") or opt.get("list_label") or role_id
            emoji = opt.get("emoji", "")
            field_label = f"{emoji} {label}"[:45]
            
            default_val = str(existing_limits.get(role_id, opt.get("max_slots", "")))
            if default_val == "None": default_val = ""
            
            text_input = ui.TextInput(
                label=field_label,
                placeholder="0 = no limit",
                default=default_val,
                required=False
            )
            self.inputs[role_id] = text_input
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction):
        role_limits = {}
        for role_id, text_input in self.inputs.items():
            val = text_input.value.strip()
            if val and val.isdigit():
                role_limits[role_id] = int(val)
            else:
                role_limits[role_id] = 0
                
        extra_data_raw = self.wizard_view.data.get("extra_data")
        extra_dict = {}
        if extra_data_raw:
            try:
                if isinstance(extra_data_raw, str):
                    extra_dict = json.loads(extra_data_raw)
                else:
                    extra_dict = extra_data_raw
            except: pass
        
        extra_dict["role_limits"] = role_limits
        self.wizard_view.data["extra_data"] = json.dumps(extra_dict)
        
        await interaction.response.send_message(t("MSG_LIMITS_SAVED", guild_id=self.wizard_view.guild_id), ephemeral=True)

class NotificationSettingsModal(ui.Modal):
    # This pop-up allows users to define custom strings for promotions and reminders
    def __init__(self, wizard_view):
        super().__init__(title=(t("WIZARD_MESSAGES_TITLE", guild_id=wizard_view.guild_id)[:45]))
        self.wizard_view = wizard_view
        
        extra_data = wizard_view.data.get("extra_data")
        promo_val = ""
        rem_val = ""
        if extra_data:
            try:
                d = json.loads(extra_data) if isinstance(extra_data, str) else extra_data
                promo_val = d.get("custom_promo_msg", "")
                rem_val = d.get("custom_reminder_msg", "")
            except: pass
            
        self.promo_input = ui.TextInput(
            label=t("LBL_PROMO_MSG", guild_id=wizard_view.guild_id),
            placeholder=t("PH_PROMO_MSG", guild_id=wizard_view.guild_id),
            default=promo_val,
            style=discord.TextStyle.paragraph,
            required=False
        )
        self.rem_input = ui.TextInput(
            label=t("LBL_REMINDER_MSG", guild_id=wizard_view.guild_id),
            placeholder=t("PH_REMINDER_MSG", guild_id=wizard_view.guild_id),
            default=rem_val,
            style=discord.TextStyle.paragraph,
            required=False
        )
        self.add_item(self.promo_input)
        self.add_item(self.rem_input)

    async def on_submit(self, interaction: discord.Interaction):
        extra_data_raw = self.wizard_view.data.get("extra_data")
        extra_dict = {}
        if extra_data_raw:
            try:
                if isinstance(extra_data_raw, str):
                    extra_dict = json.loads(extra_data_raw)
                else:
                    extra_dict = extra_data_raw
            except: pass
            
        extra_dict["custom_promo_msg"] = self.promo_input.value
        extra_dict["custom_reminder_msg"] = self.rem_input.value
        self.wizard_view.data["extra_data"] = json.dumps(extra_dict)
        
        await interaction.response.send_message(t("MSG_NOTIFS_SAVED", guild_id=self.wizard_view.guild_id), ephemeral=True)
        await self.wizard_view.save_to_draft()
        await self.wizard_view.update_message(interaction)

class EventWizardView(ui.View):
    # This is the main class that controls the whole multi-step process
    def __init__(self, bot, creator_id, existing_data=None, is_edit=False, guild_id=None, bulk_ids=None, wizard_type="series"):
        super().__init__(timeout=600)
        self.bot = bot
        self.creator_id = creator_id
        self.is_edit = is_edit
        self.guild_id = guild_id
        self.bulk_ids = bulk_ids
        self.wizard_type = wizard_type # "single" or "series"
        
        self.data = existing_data or {}
        if not is_edit and guild_id:
            from utils.i18n import GUILD_CACHE
            gid_str = str(guild_id)
            if gid_str in GUILD_CACHE:
                settings = GUILD_CACHE[gid_str].get("settings", {})
                
                if "timezone" not in self.data: 
                    self.data["timezone"] = settings.get("timezone", "Europe/Budapest")
                if "color" not in self.data:
                    self.data["color"] = settings.get("default_color", "0x5865f2")
                if "reminder_type" not in self.data:
                    self.data["reminder_type"] = settings.get("reminder_type", "none")
                if "reminder_offset" not in self.data:
                    self.data["reminder_offset"] = settings.get("reminder_offset", "15m")
            
        if "timezone" not in self.data: self.data["timezone"] = "Europe/Budapest"
        if "recurrence_type" not in self.data: self.data["recurrence_type"] = "none"
        if "use_waiting_list" not in self.data: self.data["use_waiting_list"] = False
        if "color" not in self.data: self.data["color"] = "0x5865f2"
        if "reminder_type" not in self.data: self.data["reminder_type"] = "none"
        if "reminder_offset" not in self.data: self.data["reminder_offset"] = "15m"
        self.can_publish = False
        
        # Localize button labels
        self.step1_btn.label = t("BTN_STEP_1", guild_id=guild_id)
        self.step2_btn.label = t("BTN_STEP_2", guild_id=guild_id)
        self.step3_btn.label = t("BTN_STEP_3", guild_id=guild_id)
        self.advanced_btn.label = t("BTN_STEP_4", guild_id=guild_id)
        self.role_limits_btn.label = t("BTN_ROLE_LIMITS", guild_id=guild_id)
        self.messages_btn.label = t("BTN_MESSAGES", guild_id=guild_id)
        self.save_preview_btn.label = t("BTN_SAVE_PREVIEW", guild_id=guild_id)
        self.wait_list_btn.label = t("SEL_WAIT_DISABLED", guild_id=guild_id) # Default
        
        if not self.data.get("image_urls") and self.data.get("image_url"):
            self.data["image_urls"] = self.data["image_url"]

        self.steps_completed = {
            "step1": bool(self.data.get("title") or self.data.get("config_name")),
            "step2": bool(self.data.get("start_str") or self.data.get("start_time")),
            "step3": bool(self.data.get("repost_offset"))
        }

    async def refresh_ui(self):
        """Synchronizes the Select components with the current data. Supports DB-based emoji sets."""
        current_set = self.data.get("icon_set", "standard")
        current_rec = self.data.get("recurrence_type", "none")
        current_trig = self.data.get("repost_trigger", "before_start")
        current_wait = "enabled" if self.data.get("use_waiting_list", True) else "disabled"

        # Build Emoji Set options dynamically
        # Build Emoji Set options dynamically from Shared Templates
        final_options = []
        base_ids = list(ICON_SET_TEMPLATES.keys())
        
        for tid, t_info in ICON_SET_TEMPLATES.items():
            label = t(t_info["label_key"], guild_id=self.guild_id)
            final_options.append(discord.SelectOption(
                label=label, 
                value=tid, 
                emoji=t_info["emoji"], 
                default=(current_set == tid)
            ))
        
        db_sets = await database.get_emoji_sets(self.guild_id)
        for s in db_sets:
            set_id = s["set_id"]
            if set_id in base_ids: continue
            
            sdata = json.loads(s["data"]) if isinstance(s["data"], str) else s["data"]
            opts = sdata.get("options", [])
            preview = " ".join([o.get("emoji") or "?" for o in opts[:3]])
            
            final_options.append(discord.SelectOption(
                label=s["name"][:25],
                description=f"{preview}...",
                value=set_id,
                default=(current_set == set_id)
            ))
            
        self.icon_set_select.options = final_options[:25]
        
        # Localize Select placeholders and additional options
        self.recurrence_select.placeholder = t("SEL_REC_TYPE", guild_id=self.guild_id)
        self.recurrence_select.options = [
            discord.SelectOption(label=t("SEL_REC_NONE", guild_id=self.guild_id), value="none", emoji="❌", default=(current_rec == "none")),
            discord.SelectOption(label=t("SEL_REC_DAILY", guild_id=self.guild_id), value="daily", emoji="📅", default=(current_rec == "daily")),
            discord.SelectOption(label=t("SEL_REC_WEEKLY", guild_id=self.guild_id), value="weekly", emoji="🗓️", default=(current_rec == "weekly")),
            discord.SelectOption(label=t("SEL_REC_MONTHLY", guild_id=self.guild_id), value="monthly", emoji="📊", default=(current_rec == "monthly"))
        ]
        
        self.trigger_select.placeholder = t("SEL_TRIG_TYPE", guild_id=self.guild_id)
        self.trigger_select.options = [
            discord.SelectOption(label=t("SEL_TRIG_BEFORE", guild_id=self.guild_id), value="before_start", default=(current_trig == "before_start")),
            discord.SelectOption(label=t("SEL_TRIG_AFTER_START", guild_id=self.guild_id), value="after_start", default=(current_trig == "after_start")),
            discord.SelectOption(label=t("SEL_TRIG_AFTER_END", guild_id=self.guild_id), value="after_end", default=(current_trig == "after_end"))
        ]
        
        # Update Waiting List Button
        use_waiting = self.data.get("use_waiting_list", False)
        self.wait_list_btn.label = t("SEL_WAIT_ENABLED" if use_waiting else "SEL_WAIT_DISABLED", guild_id=self.guild_id)
        self.wait_list_btn.style = discord.ButtonStyle.green if use_waiting else discord.ButtonStyle.gray

    async def save_to_draft(self):
        """Saves the current state of the wizard to the drafts table."""
        if not self.data.get("draft_id"):
            self.data["draft_id"] = str(uuid.uuid4())[:8]
        
        if not self.data.get("guild_id"):
            self.data["guild_id"] = self.guild_id
            
        await database.save_draft(
            guild_id=self.data["guild_id"],
            draft_id=self.data["draft_id"],
            creator_id=self.creator_id,
            title=self.data.get("title") or self.data.get("config_name"),
            data=self.data
        )

    def get_status_text(self):
        guild_id = self.guild_id
        s1 = t("WIZARD_STATUS_OK", guild_id=guild_id) if self.steps_completed["step1"] else t("WIZARD_STATUS_WAIT", guild_id=guild_id)
        s2 = t("WIZARD_STATUS_OK", guild_id=guild_id) if self.steps_completed["step2"] else t("WIZARD_STATUS_WAIT", guild_id=guild_id)
        s3 = t("WIZARD_STATUS_OK", guild_id=guild_id) if self.steps_completed["step3"] else t("WIZARD_STATUS_WAIT", guild_id=guild_id)
        return f"- {t('BTN_STEP_1', guild_id=guild_id)}: {s1}\n- {t('BTN_STEP_2', guild_id=guild_id)}: {s2}\n- Offset: {s3}"

    async def update_message(self, interaction: discord.Interaction):
        await self.refresh_ui()
        
        status = self.get_status_text()
        guild_id = self.guild_id
        embed = discord.Embed(
            title=t("WIZARD_TITLE", guild_id=guild_id), 
            description=t("WIZARD_DESC", guild_id=guild_id, status=status), 
            color=discord.Color.blue() if not self.is_edit else discord.Color.gold()
        )
        
        if self.can_publish:
            publish_btn = ui.Button(label=t("BTN_PUBLISH", guild_id=self.guild_id), style=discord.ButtonStyle.green, row=1, custom_id="wiz_publish")
            publish_btn.callback = self.publish_btn
            self.add_item(publish_btn)
            for child in self.children:
                if getattr(child, "custom_id", "") == "wiz_save":
                    child.disabled = True
                    child.label = t("BTN_SAVE_PREVIEW", guild_id=self.guild_id)

        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)

    @ui.button(label="1. Info", style=discord.ButtonStyle.gray, custom_id="wiz_step_1", row=0)
    async def step1_btn(self, interaction: discord.Interaction, button: ui.Button):
        if self.wizard_type == "single":
            await interaction.response.send_modal(SingleEventModal(self))
        else:
            await interaction.response.send_modal(Step1Modal(self))

    @ui.button(label="2. Details", style=discord.ButtonStyle.gray, custom_id="wiz_step_2", row=0)
    async def step2_btn(self, interaction: discord.Interaction, button: ui.Button):
        if self.wizard_type == "single":
            await interaction.response.send_message(t("MSG_SINGLE_EVENT_HINT", guild_id=self.guild_id), ephemeral=True)
            return
        await interaction.response.send_modal(Step2Modal(self))

    @ui.button(label="3. Timing", style=discord.ButtonStyle.gray, custom_id="wiz_step_3", row=0)
    async def step3_btn(self, interaction: discord.Interaction, button: ui.Button):
        if self.wizard_type == "single":
            await interaction.response.send_message(t("MSG_RECURRING_ONLY_HINT", guild_id=self.guild_id), ephemeral=True)
            return
        if self.bulk_ids:
            await interaction.response.send_message(t("MSG_BULK_EDIT_RESTRICTED", guild_id=self.guild_id), ephemeral=True)
            return
        await interaction.response.send_modal(Step3Modal(self))

    @ui.button(label="4. Advanced", style=discord.ButtonStyle.gray, custom_id="wiz_step_4", row=0)
    async def advanced_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AdvancedSettingsModal(self))

    @ui.button(label="Role Limits", style=discord.ButtonStyle.gray, custom_id="wiz_role_limits", row=0)
    async def role_limits_btn(self, interaction: discord.Interaction, button: ui.Button):
        from cogs.event_ui import get_active_set
        icon_set_key = self.data.get("icon_set", "standard")
        if icon_set_key == "standard":
            await interaction.response.send_message(t("MSG_STANDARD_LIMITS_HINT", guild_id=self.guild_id), ephemeral=True)
            return
            
        active_set = get_active_set(icon_set_key)
        await interaction.response.send_modal(RoleLimitsModal(self, active_set))

    @ui.button(label="Messages", style=discord.ButtonStyle.gray, custom_id="wiz_messages", row=1)
    async def messages_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(NotificationSettingsModal(self))

    @ui.select(
        placeholder="Icon Set (Presets)",
        options=[
            discord.SelectOption(label="Standard (✅, ❌, ❔)", value="standard", emoji="💠"),
            discord.SelectOption(label="MMO / Raid (🛡️, 🏥, ⚔️)", value="mmo", emoji="⚔️"),
            discord.SelectOption(label="Teams (🅰️, 🅱️, 👁️)", value="team", emoji="🚩"),
            discord.SelectOption(label="Timing (✅, ⏰, 🏃)", value="timing", emoji="⏰")
        ],
        row=3
    )
    async def icon_set_select(self, interaction: discord.Interaction, select: ui.Select):
        self.data["icon_set"] = str(select.values[0])
        await self.save_to_draft()
        await self.update_message(interaction)

    @ui.select(
        placeholder="Recurrence Type",
        options=[
            discord.SelectOption(label="None", value="none", emoji="❌"),
            discord.SelectOption(label="Daily", value="daily", emoji="📅"),
            discord.SelectOption(label="Weekly", value="weekly", emoji="🗓️"),
            discord.SelectOption(label="Monthly", value="monthly", emoji="📊")
        ],
        row=4
    )
    async def recurrence_select(self, interaction: discord.Interaction, select: ui.Select):
        self.data["recurrence_type"] = str(select.values[0])
        await self.save_to_draft()
        await self.update_message(interaction)

    @ui.select(
        placeholder="Repost Trigger",
        options=[
            discord.SelectOption(label="Before Start", value="before_start"),
            discord.SelectOption(label="After Start", value="after_start"),
            discord.SelectOption(label="After End", value="after_end")
        ],
        row=2
    )
    async def trigger_select(self, interaction: discord.Interaction, select: ui.Select):
        self.data["repost_trigger"] = str(select.values[0])
        await self.update_message(interaction)

    @ui.button(label="Waiting List", style=discord.ButtonStyle.gray, custom_id="wiz_wait_toggle", row=1)
    async def wait_list_btn(self, interaction: discord.Interaction, button: ui.Button):
        use_waiting = not self.data.get("use_waiting_list", False)
        self.data["use_waiting_list"] = use_waiting
        
        extra_data_raw = self.data.get("extra_data")
        extra_dict = {}
        if extra_data_raw:
            try:
                if isinstance(extra_data_raw, str):
                    extra_dict = json.loads(extra_data_raw)
                else:
                    extra_dict = extra_data_raw
            except: pass
        
        extra_dict["use_waiting_list"] = use_waiting
        self.data["extra_data"] = json.dumps(extra_dict)
        
        await self.save_to_draft()
        await self.update_message(interaction)

    @ui.button(label="SAVE & PREVIEW", style=discord.ButtonStyle.primary, row=1, custom_id="wiz_save")
    async def save_preview_btn(self, interaction: discord.Interaction, button: ui.Button):
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
            import uuid
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
            await self.update_message(interaction)
        except Exception as e:
            log.error(f"Error in save_preview_btn: {e}")
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

        # Stop the wizard
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)
        self.stop()

        # Delete draft once published
        await database.delete_draft(self.data.get("draft_id"), self.guild_id)
