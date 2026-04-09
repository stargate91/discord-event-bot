import discord
from discord import ui
import database
from utils.i18n import t
from utils.logger import log
import datetime
import time
import json
from dateutil import parser
from dateutil import tz

class Step1Modal(ui.Modal):
    # This pop-up handles the basic info like the name and title
    def __init__(self, wizard_view):
        super().__init__(title=(t("BTN_STEP_1")[:45]))
        self.wizard_view = wizard_view
        data = wizard_view.data

        self.name_input = ui.TextInput(label=t("LBL_WIZ_NAME"), default=str(data.get("config_name") or ""), required=True)
        self.title_input = ui.TextInput(label=t("LBL_WIZ_TITLE"), default=str(data.get("title") or ""), required=True)
        self.desc_input = ui.TextInput(label=t("LBL_WIZ_DESC"), style=discord.TextStyle.paragraph, default=str(data.get("description") or ""), required=False)
        self.images_input = ui.TextInput(label=t("LBL_WIZ_IMAGES"), default=str(data.get("image_urls") or ""), required=False)
        self.creator_input = ui.TextInput(label=t("LBL_WIZ_CREATOR"), default=str(data.get("creator_id") or wizard_view.creator_id), required=False)
        
        self.add_item(self.name_input)
        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.images_input)
        self.add_item(self.creator_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Save things to our data dictionary
        self.wizard_view.data["config_name"] = str(self.name_input.value)
        self.wizard_view.data["title"] = str(self.title_input.value)
        self.wizard_view.data["description"] = str(self.desc_input.value)
        self.wizard_view.data["image_urls"] = str(self.images_input.value)
        self.wizard_view.data["creator_id"] = str(self.creator_input.value)
        self.wizard_view.steps_completed["step1"] = True
        await self.wizard_view.update_message(interaction)

class Step2Modal(ui.Modal):
    # This pop-up handles technical things like colors and dates
    def __init__(self, wizard_view):
        super().__init__(title=(t("BTN_STEP_2")[:45]))
        self.wizard_view = wizard_view
        data = wizard_view.data

        self.color_input = ui.TextInput(label=t("LBL_WIZ_COLOR"), default=str(data.get("color") or "0x3498db"), required=False)
        self.max_acc_input = ui.TextInput(label=t("LBL_WIZ_MAX"), default=str(data.get("max_accepted") or 0), required=False)
        self.ping_input = ui.TextInput(label=t("LBL_WIZ_PING"), default=str(data.get("ping_role") or ""), required=False)
        self.start_input = ui.TextInput(label=t("LBL_WIZ_START"), placeholder="YYYY-MM-DD HH:MM", default=str(data.get("start_str") or ""), required=True)
        self.end_input = ui.TextInput(label=t("LBL_WIZ_END"), placeholder="YYYY-MM-DD HH:MM", default=str(data.get("end_str") or ""), required=False)

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
            # Save our progress as a draft automatically
            await self.wizard_view.save_to_draft()
            await self.wizard_view.update_message(interaction)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Oops! Something went wrong: {e}", ephemeral=True)

class Step3Modal(ui.Modal):
    # This pop-up handles notifications and limits
    def __init__(self, wizard_view):
        super().__init__(title=(t("SEL_TRIG_TYPE")[:45]))
        self.wizard_view = wizard_view
        data = wizard_view.data

        self.timezone_input = ui.TextInput(
            label=t("LBL_WIZ_TZ"),
            default=str(data.get("timezone") or "Europe/Budapest"),
            required=True
        )
        self.offset_input = ui.TextInput(
            label=t("LBL_WIZ_OFFSET"), 
            placeholder="e.g. 4h, 30m, 1d", 
            default=str(data.get("repost_offset") or "1h"), 
            required=True
        )
        self.reminder_offset_input = ui.TextInput(
            label=t("LBL_WIZ_REMINDER_OFFSET"),
            placeholder="e.g. 15m, 1h",
            default=str(data.get("reminder_offset") or "15m"),
            required=True
        )
        self.rec_limit_input = ui.TextInput(
            label=t("LBL_WIZ_REC_LIMIT"),
            placeholder="0 = forever",
            default=str(data.get("recurrence_limit") or 0),
            required=True
        )
        self.rem_type_input = ui.TextInput(
            label="Rem. Type (none, channel, dm, both)",
            default=str(data.get("reminder_type") or "both"),
            required=True
        )

        self.add_item(self.timezone_input)
        self.add_item(self.offset_input)
        self.add_item(self.reminder_offset_input)
        self.add_item(self.rec_limit_input)
        self.add_item(self.rem_type_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.data["timezone"] = str(self.timezone_input.value)
        self.wizard_view.data["repost_offset"] = str(self.offset_input.value)
        self.wizard_view.data["reminder_offset"] = str(self.reminder_offset_input.value)
        self.wizard_view.data["recurrence_limit"] = int(self.rec_limit_input.value) if str(self.rec_limit_input.value).isdigit() else 0
        self.wizard_view.data["reminder_type"] = str(self.rem_type_input.value).lower()
        
        self.wizard_view.steps_completed["step3"] = True
        await self.wizard_view.save_to_draft()
        await self.wizard_view.update_message(interaction)

class RoleLimitsModal(ui.Modal):
    # This pop-up allows setting per-role capacities dynamically
    def __init__(self, wizard_view, icon_set_data):
        super().__init__(title=(t("WIZARD_LIMITS_TITLE")[:45]))
        self.wizard_view = wizard_view
        self.options = icon_set_data.get("options", [])
        
        # Get existing limits from extra_data if any
        extra_data = wizard_view.data.get("extra_data")
        existing_limits = {}
        if extra_data:
            try:
                existing_limits = json.loads(extra_data).get("role_limits", {})
            except: pass
            
        self.inputs = {}
        # Discord limit is 5 items in a Modal
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
                
        # Update extra_data dictionary
        extra_data_raw = self.wizard_view.data.get("extra_data")
        extra_dict = {}
        if extra_data_raw:
            try:
                if isinstance(extra_data_raw, str):
                    extra_dict = json.loads(extra_data_raw)
                else:
                    extra_dict = extra_data_raw # Already a dict in some cases
            except: pass
        
        extra_dict["role_limits"] = role_limits
        self.wizard_view.data["extra_data"] = json.dumps(extra_dict)
        
        await interaction.response.send_message("✅ Sikerült menteni a limiteket!", ephemeral=True)

class NotificationSettingsModal(ui.Modal):
    # This pop-up allows users to define custom strings for promotions and reminders
    def __init__(self, wizard_view):
        super().__init__(title=(t("WIZARD_MESSAGES_TITLE")[:45]))
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
            label="Promo Msg (Placeholders: {user_id}, {role})",
            placeholder="e.g. Grats <@{user_id}>! You are now {role}!",
            default=promo_val,
            style=discord.TextStyle.paragraph,
            required=False
        )
        self.rem_input = ui.TextInput(
            label="Reminder Msg (Placeholders: {title})",
            placeholder="e.g. Hurry up! {title} is starting!",
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
        
        await interaction.response.send_message("✅ Üzenetek mentve!", ephemeral=True)

class EventWizardView(ui.View):
    # This is the main view with all the buttons and select menus
    def __init__(self, bot, creator_id, existing_data=None, is_edit=False):
        # Allow custom timeout from config
        globals_cfg = bot.config.get("globals", {})
        timeout = globals_cfg.get("wizard_timeout", 600)
        super().__init__(timeout=timeout)
        self.bot = bot
        self.creator_id = creator_id
        self.is_edit = is_edit
        self.data = existing_data or {}
        self.can_publish = False
        
        # We check images data correctly
        if not self.data.get("image_urls") and self.data.get("image_url"):
            self.data["image_urls"] = self.data["image_url"]

        # Track which steps the user finished
        self.steps_completed = {
            "step1": bool(self.data.get("title") or self.data.get("config_name")),
            "step2": bool(self.data.get("start_str") or self.data.get("start_time")),
            "step3": bool(self.data.get("repost_offset"))
        }

        # Pre-select things if we are editing or resuming
        current_rec = self.data.get("recurrence_type", "none")
        for opt in self.recurrence_select.options:
            opt.default = (opt.value == current_rec)

        current_trig = self.data.get("repost_trigger", "before_start")
        for opt in self.trigger_select.options:
            opt.default = (opt.value == current_trig)

        current_set = self.data.get("icon_set", "standard")
        
        # Build the options list uniquely to avoid "already used" errors
        base_values = ["standard", "mmo", "team", "timing"]
        final_options = [
            discord.SelectOption(label="Standard (✅, ❌, ❔)", value="standard", emoji="💠", default=(current_set == "standard")),
            discord.SelectOption(label="MMO / Raid (🛡️, 🏥, ⚔️)", value="mmo", emoji="⚔️", default=(current_set == "mmo")),
            discord.SelectOption(label="Teams (🅰️, 🅱️, 👁️)", value="team", emoji="🚩", default=(current_set == "team")),
            discord.SelectOption(label="Timing (✅, ⏰, 🏃)", value="timing", emoji="⏰", default=(current_set == "timing"))
        ]
        
        # Add custom sets if they exist in event_ui cache
        from cogs.event_ui import CUSTOM_ICON_SETS
        for set_id, sdata in CUSTOM_ICON_SETS.items():
            # Skip if it's already in the base list
            if set_id in base_values:
                continue
                
            opts = sdata.get("options", [])
            preview = " ".join([o.get("emoji") or o.get("label") or "?" for o in opts[:3]])
            final_options.append(
                discord.SelectOption(
                    label=set_id[:25], # discord limit
                    description=f"{preview}...",
                    value=set_id,
                    default=(current_set == set_id)
                )
            )
            
        self.icon_set_select.options = final_options

    def get_status_text(self):
        # Build the status checklist for the user
        s1 = t("WIZARD_STATUS_OK") if self.steps_completed["step1"] else t("WIZARD_STATUS_WAIT")
        s2 = t("WIZARD_STATUS_OK") if self.steps_completed["step2"] else t("WIZARD_STATUS_WAIT")
        s3 = t("WIZARD_STATUS_OK") if self.steps_completed["step3"] else t("WIZARD_STATUS_WAIT")
        return f"- {t('BTN_STEP_1')}: {s1}\n- {t('BTN_STEP_2')}: {s2}\n- Offset: {s3}"

    async def update_message(self, interaction: discord.Interaction):
        # Refresh the main Wizard message
        status = self.get_status_text()
        embed = discord.Embed(
            title=t("WIZARD_TITLE"), 
            description=t("WIZARD_DESC", status=status), 
            color=discord.Color.blue() if not self.is_edit else discord.Color.gold()
        )
        
        # Show "PUBLISH" button only after first save
        if self.can_publish:
            publish_btn = ui.Button(label=t("BTN_PUBLISH"), style=discord.ButtonStyle.green, row=4, custom_id="wiz_publish")
            publish_btn.callback = self.publish_btn
            self.add_item(publish_btn)
            for child in self.children:
                if getattr(child, "custom_id", "") == "wiz_save":
                    child.disabled = True
                    child.label = t("BTN_SAVE_PREVIEW")

        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)

    # Step buttons to open modals
    @ui.button(label="1. Info", style=discord.ButtonStyle.gray, custom_id="wiz_step_1", row=0)
    async def step1_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(Step1Modal(self))

    @ui.button(label="2. Details", style=discord.ButtonStyle.gray, custom_id="wiz_step_2", row=0)
    async def step2_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(Step2Modal(self))

    @ui.button(label="3. Offset", style=discord.ButtonStyle.gray, custom_id="wiz_step_3", row=0)
    async def step3_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(Step3Modal(self))

    @ui.button(label="Role Limits", style=discord.ButtonStyle.gray, custom_id="wiz_role_limits", row=0)
    async def role_limits_btn(self, interaction: discord.Interaction, button: ui.Button):
        from cogs.event_ui import get_active_set
        icon_set_key = self.data.get("icon_set", "standard")
        if icon_set_key == "standard":
            await interaction.response.send_message("A standard készletnél nincsenek külön szerepkör limitek.", ephemeral=True)
            return
            
        active_set = get_active_set(icon_set_key)
        await interaction.response.send_modal(RoleLimitsModal(self, active_set))

    @ui.button(label="Messages", style=discord.ButtonStyle.gray, custom_id="wiz_messages", row=0)
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
        row=2
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
        row=3
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
        row=1
    )
    async def trigger_select(self, interaction: discord.Interaction, select: ui.Select):
        self.data["repost_trigger"] = str(select.values[0])
        await self.update_message(interaction)

    @ui.button(label="SAVE & PREVIEW", style=discord.ButtonStyle.primary, row=4, custom_id="wiz_save")
    async def save_preview_btn(self, interaction: discord.Interaction, button: ui.Button):
        # We need step 1 and 2 before saving
        if not self.steps_completed["step1"] or not self.steps_completed["step2"]:
            await interaction.response.send_message("Please fill Step 1 and 2 first!", ephemeral=True)
            return

        # Make sure we don't save weird objects to data
        clean_data = {}
        for k, v in self.data.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                clean_data[k] = v
            elif isinstance(v, list):
                # Join lists with comma for storage
                clean_data[k] = ",".join(str(i) for i in v)
            else:
                clean_data[k] = str(v)
        self.data = clean_data

        # Try to parse the dates
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
            await interaction.response.send_message(f"Date or Timezone error: {e}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        import uuid
        from cogs.event_ui import DynamicEventView
        
        event_id = str(self.data.get("event_id") or str(uuid.uuid4())[:8])
        self.data["event_id"] = event_id
        
        if self.is_edit:
            # Keep existing creator_id if not present
            if "creator_id" not in self.data:
                self.data["creator_id"] = str(self.creator_id)
            await database.update_active_event(event_id, self.data)
        else:
            self.data["creator_id"] = str(self.creator_id)
            await database.create_active_event(
                event_id=event_id,
                config_name=str(self.data.get("config_name") or "manual"),
                channel_id=interaction.channel_id,
                start_time=self.data["start_time"],
                data=self.data
            )

        # Update state to allow publication
        self.can_publish = True
        
        # Show what the event will look like
        view = DynamicEventView(self.bot, event_id, self.data)
        embed = await view.generate_embed()
        
        await interaction.followup.send(t("MSG_SAVED_PREVIEW"), embed=embed, ephemeral=True)
        await self.update_message(interaction)

    async def publish_btn(self, interaction: discord.Interaction):
        # This actually shows the event to everyone in the channel
        await interaction.response.defer(ephemeral=True)
        
        from cogs.event_ui import DynamicEventView
        event_id = self.data["event_id"]
        db_event = await database.get_active_event(event_id)
        
        if self.is_edit:
            if db_event and db_event.get("message_id") and db_event.get("channel_id"):
                channel = self.bot.get_channel(db_event["channel_id"])
                if channel:
                    try:
                        msg = await channel.fetch_message(db_event["message_id"])
                        view = DynamicEventView(self.bot, event_id, self.data)
                        embed = await view.generate_embed(db_event)
                        await msg.edit(embed=embed, view=view)
                    except Exception as e:
                        log.error(f"Error updating message: {e}")
            await interaction.followup.send("Updated!", ephemeral=True)
        else:
            view = DynamicEventView(self.bot, event_id, self.data)
            embed = await view.generate_embed()
            msg = await interaction.channel.send(content=t("MSG_EV_CREATED_PUBLIC"), embed=embed, view=view)
            await database.set_event_message(event_id, msg.id)
            self.bot.add_view(view)
            await interaction.followup.send("Published!", ephemeral=True)

        # Stop the wizard
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)
        self.stop()

        # Delete draft once published
        await database.delete_draft(self.data.get("draft_id"))
