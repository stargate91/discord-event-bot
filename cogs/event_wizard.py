import discord
from utils.emojis import WARNING, PING
from utils.emojis import SUCCESS, ERROR, INFO, DROPDOWN_OPEN, DROPDOWN_CLOSED, REC_DAILY, REC_WEEKLY, REC_MONTHLY, REC_BIWEEKLY, REC_WEEKDAYS, REC_WEEKENDS, REC_CUSTOM, REC_RELATIVE
from discord import ui
import uuid
import re
import database
from database import DEFAULT_TIMEZONE
from utils.i18n import t
from utils.logger import log
import datetime
import time
import json
from dateutil import parser
from dateutil import tz
from utils.text_utils import slugify
from utils.templates import ICON_SET_TEMPLATES
from utils.emoji_utils import parse_emoji_config, to_emoji, resolve_placeholders, make_select_option

async def resolve_channel(guild, channel_query):
    """Tries to resolve a channel by ID or Name. Returns channel_id or None."""
    if not channel_query: return None
    query = str(channel_query).strip().lstrip('#')
    if query.isdigit():
        chan = guild.get_channel(int(query))
        if chan: return chan.id
    for chan in guild.text_channels:
        if chan.name == query:
            return chan.id
    return None

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
        desc = t("WIZARD_TYPE_DESC", guild_id=guild_id) + "\n" + t("WIZARD_TYPE_LOBBY_HINT", guild_id=guild_id)
        
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
                    await it.response.send_message(f"{ERROR} {e}", ephemeral=True)

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
                    await it.response.send_message(f"{ERROR} {e}", ephemeral=True)

        recurring_btn.callback = recurring_cb
        
        row = ui.ActionRow(single_btn, recurring_btn)
        
        container = ui.Container(
            ui.TextDisplay(f"### {title}"),
            ui.Separator(),
            ui.TextDisplay(desc),
            ui.Separator(),
            row,
            accent_color=0x40C4FF
        )
        view.add_item(container)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(content=None, embeds=[], view=view)
        elif interaction.type == discord.InteractionType.component:
            await interaction.response.edit_message(content=None, embeds=[], view=view)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

class SingleEventModal(ui.Modal):
    """Step 1 for Single Events (lobby: no start/end; max létszám itt)."""
    def __init__(self, wizard_view):
        super().__init__(title=t("TITLE_BASIC_INFO", guild_id=wizard_view.guild_id)[:45])
        self.wizard_view = wizard_view
        data = wizard_view.data
        guild_id = self.wizard_view.guild_id
        is_lobby = wizard_view.wizard_type == "lobby"

        self.title_input = ui.TextInput(label=t("LBL_WIZ_TITLE", guild_id=guild_id), default=str(data.get("title") or ""), required=True)
        self.desc_input = ui.TextInput(label=t("LBL_WIZ_DESC", guild_id=guild_id), style=discord.TextStyle.paragraph, default=str(data.get("description") or ""), required=False)

        if is_lobby:
            self.max_acc_input = ui.TextInput(
                label=t("LBL_WIZ_MAX", guild_id=guild_id),
                default=str(data.get("max_accepted") or 0),
                required=False,
            )
            self.time_input = None
        else:
            self.max_acc_input = None
            combined_time = ""
            if data.get("start_str"):
                combined_time = str(data["start_str"])
                if data.get("end_str"):
                    combined_time += f", {data['end_str']}"
            self.time_input = ui.TextInput(
                label=t("LBL_WIZ_START", guild_id=guild_id),
                placeholder=t("PH_WIZ_START_COMBINED", guild_id=guild_id),
                default=combined_time,
                required=True,
            )

        self.images_input = ui.TextInput(label=t("LBL_WIZ_IMAGES", guild_id=guild_id), default=str(data.get("image_urls") or ""), required=False)
        self.ping_input = ui.TextInput(label=t("LBL_WIZ_PING", guild_id=guild_id), default=str(data.get("ping_role") or ""), required=False)

        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        if is_lobby:
            self.add_item(self.max_acc_input)
        else:
            self.add_item(self.time_input)
        self.add_item(self.images_input)
        self.add_item(self.ping_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            title = str(self.title_input.value)
            self.wizard_view.data["title"] = title
            self.wizard_view.data["config_name"] = "manual"
            self.wizard_view.data["description"] = str(self.desc_input.value)
            self.wizard_view.data["image_urls"] = str(self.images_input.value)
            self.wizard_view.data["ping_role"] = int(self.ping_input.value) if str(self.ping_input.value).isdigit() else 0

            if self.wizard_view.wizard_type == "lobby":
                self.wizard_view.data["start_str"] = ""
                self.wizard_view.data["end_str"] = ""
                self.wizard_view.data["max_accepted"] = (
                    int(self.max_acc_input.value) if str(self.max_acc_input.value).isdigit() else 0
                )
                if self.wizard_view.data["max_accepted"] == 0:
                    self.wizard_view.data["use_waiting_list"] = False
            else:
                time_val = str(self.time_input.value).strip()
                if "," in time_val:
                    parts = time_val.split(",", 1)
                elif " - " in time_val:
                    parts = time_val.split(" - ", 1)
                elif ". " in time_val:
                    parts = time_val.split(". ", 1)
                else:
                    parts = [time_val]

                self.wizard_view.data["start_str"] = parts[0].strip()
                self.wizard_view.data["end_str"] = parts[1].strip() if len(parts) > 1 else ""

            self.wizard_view.steps_completed["step1"] = bool(title) and (
                self.wizard_view.wizard_type == "lobby" or bool(self.wizard_view.data.get("start_str"))
            )
            await self.wizard_view.save_to_draft()
            await self.wizard_view.refresh_message(interaction)
        except Exception as e:
            log.error(f"[Wizard] SingleEventModal on_submit error: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{ERROR} {e}", ephemeral=True)

class SingleEventSupplementaryModal(ui.Modal):
    """Step 2: single = tz + max + channel; lobby = tz + channel + lejárati offset."""
    def __init__(self, wizard_view):
        gid = wizard_view.guild_id
        is_lobby = wizard_view.wizard_type == "lobby"
        title_key = "BTN_STEP_2_LOBBY" if is_lobby else "BTN_STEP_2_SINGLE"
        super().__init__(title=t(title_key, guild_id=gid, default="2. Kiegészítő")[:45])
        self.wizard_view = wizard_view
        self.is_lobby = is_lobby
        data = wizard_view.data

        self.timezone_input = ui.TextInput(label=t("LBL_WIZ_TZ", guild_id=gid), default=str(data.get("timezone") or DEFAULT_TIMEZONE), required=True)
        self.channel_id_input = ui.TextInput(label=t("LBL_CHANNEL_ID", guild_id=gid), placeholder=t("PH_CURRENT_CHANNEL", guild_id=gid), default=str(data.get("channel_id") or ""), required=False)

        if is_lobby:
            self.max_acc_input = None
            self.lobby_expire_input = ui.TextInput(
                label=t("LBL_LOBBY_EXPIRE_OFFSET", guild_id=gid),
                default=str(data.get("lobby_expire_offset") or "12h"),
                placeholder=t("PH_DURATION", guild_id=gid),
                required=True,
                max_length=24,
            )
            self.add_item(self.timezone_input)
            self.add_item(self.channel_id_input)
            self.add_item(self.lobby_expire_input)
        else:
            self.lobby_expire_input = None
            self.max_acc_input = ui.TextInput(label=t("LBL_WIZ_MAX", guild_id=gid), default=str(data.get("max_accepted") or 0), required=False)
            self.add_item(self.timezone_input)
            self.add_item(self.max_acc_input)
            self.add_item(self.channel_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.data["timezone"] = str(self.timezone_input.value)
        self.wizard_view.data["channel_id"] = str(self.channel_id_input.value)
        if self.is_lobby:
            raw = str(self.lobby_expire_input.value).strip().lower() or "12h"
            if not re.match(r"^(\d+)([mhd])$", raw):
                return await interaction.response.send_message(
                    t("ERR_LOBBY_EXPIRE_OFFSET", guild_id=self.wizard_view.guild_id, e=raw),
                    ephemeral=True,
                )
            self.wizard_view.data["lobby_expire_offset"] = raw
        else:
            self.wizard_view.data["max_accepted"] = (
                int(self.max_acc_input.value) if str(self.max_acc_input.value).isdigit() else 0
            )
            if self.wizard_view.data["max_accepted"] == 0:
                self.wizard_view.data["use_waiting_list"] = False

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
            base_slug = slugify(title) or "ev"
            self.wizard_view.data["config_name"] = f"{base_slug}-{uuid.uuid4().hex[:6]}"
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

        self.color_input = ui.TextInput(label=t("LBL_WIZ_COLOR", guild_id=guild_id), default=str(data.get("color") or "0x40C4FF"), required=False)
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
        if self.wizard_view.data["max_accepted"] == 0:
            self.wizard_view.data["use_waiting_list"] = False
        self.wizard_view.data["ping_role"] = int(self.ping_input.value) if str(self.ping_input.value).isdigit() else 0
        
        start_val = str(self.start_input.value).strip()
        end_val = str(self.end_input.value).strip()
        
        if not end_val:
            if "," in start_val: parts = start_val.split(",", 1)
            elif " - " in start_val: parts = start_val.split(" - ", 1)
            elif ". " in start_val: parts = start_val.split(". ", 1)
            else: parts = [start_val]
            
            start_val = parts[0].strip()
            end_val = parts[1].strip() if len(parts) > 1 else ""

        self.wizard_view.data["start_str"] = start_val
        self.wizard_view.data["end_str"] = end_val
        self.wizard_view.steps_completed["step2"] = True
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class Step3Modal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=(t("SEL_TRIG_TYPE", guild_id=wizard_view.guild_id)[:45]))
        self.wizard_view = wizard_view
        data = wizard_view.data
        guild_id = self.wizard_view.guild_id

        self.timezone_input = ui.TextInput(label=t("LBL_WIZ_TZ", guild_id=guild_id), default=str(data.get("timezone") or DEFAULT_TIMEZONE), required=True)
        self.cleanup_offset = ui.TextInput(
            label=t("LBL_CLEANUP_OFFSET", guild_id=guild_id),
            placeholder=t("PH_EXAMPLE_4H", guild_id=guild_id),
            default=data.get("cleanup_offset", "4h"),
            required=True,
        )
        ro = data.get("reminder_offsets")
        if isinstance(ro, list) and ro:
            def_offset = "\n".join(ro[:database.MAX_EVENT_REMINDERS])
        else:
            def_offset = str(data.get("reminder_offset", ""))
        self.rem_offset = ui.TextInput(
            label=t("LBL_REMINDER_OFFSETS_PARAGRAPH", guild_id=guild_id),
            placeholder=t("PH_REMINDER_OFFSETS", guild_id=guild_id),
            default=def_offset,
            style=discord.TextStyle.paragraph,
            max_length=400,
            required=False,
        )
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
        lines = [
            x.strip()
            for x in str(self.rem_offset.value).splitlines()
            if x.strip()
        ][: database.MAX_EVENT_REMINDERS]
        self.wizard_view.data["reminder_offsets"] = lines
        self.wizard_view.data["reminder_offset"] = lines[0] if lines else ""
        
        limit_val = str(self.rec_limit.value).strip()
        if limit_val.isdigit():
            self.wizard_view.data["recurrence_limit"] = int(limit_val)
        else:
            try:
                dt = parser.parse(limit_val)
                extra = self.wizard_view.data.get("extra_data", {})
                if isinstance(extra, str): extra = json.loads(extra)
                extra["recurrence_limit_date"] = dt.timestamp()
                self.wizard_view.data["extra_data"] = json.dumps(extra)
                self.wizard_view.data["recurrence_limit"] = 0
            except Exception as e:
                log.debug("RecurrenceLimitModal limit_date parse: %s", e)
                self.wizard_view.data["recurrence_limit"] = 0

        self.wizard_view.data["reminder_type"] = str(self.rem_type.value).lower()
        self.wizard_view.steps_completed["step3"] = True
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class RecurrenceSettingsModal(ui.Modal):
    """Step 4 for Series: recurrence_limit + repost_offset."""
    def __init__(self, wizard_view):
        super().__init__(title=t("BTN_STEP_4_SERIES", guild_id=wizard_view.guild_id, default="4. Ismétlődés")[:45])
        self.wizard_view = wizard_view
        data = wizard_view.data
        guild_id = wizard_view.guild_id
        
        self.repost_input = ui.TextInput(label=t("SETTING_REPOST_OFFSET", guild_id=guild_id), placeholder=t("PH_DURATION", guild_id=guild_id), default=str(data.get("repost_offset", "12h")), required=False)
        self.limit_input = ui.TextInput(label=t("LBL_RECURRENCE_LIMIT", guild_id=guild_id), default=str(data.get("recurrence_limit", 0)), required=False)
        
        self.add_item(self.repost_input)
        self.add_item(self.limit_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.data["repost_offset"] = str(self.repost_input.value)
        
        limit_val = str(self.limit_input.value).strip()
        if limit_val.isdigit():
            self.wizard_view.data["recurrence_limit"] = int(limit_val)
        else:
            try:
                dt = parser.parse(limit_val)
                extra = self.wizard_view.data.get("extra_data", {})
                if isinstance(extra, str): extra = json.loads(extra)
                extra["recurrence_limit_date"] = dt.timestamp()
                self.wizard_view.data["extra_data"] = json.dumps(extra)
                self.wizard_view.data["recurrence_limit"] = 0
            except Exception as e:
                log.debug("RecurrenceSettingsModal limit_date parse: %s", e)
                self.wizard_view.data["recurrence_limit"] = 0

        self.wizard_view.steps_completed["step4"] = True
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
        super().__init__(title=t("WIZARD_LIMITS_TITLE", guild_id=wizard_view.guild_id)[:45])
        self.wizard_view = wizard_view
        self.options = icon_set_data.get("options", [])
        
        extra_data = wizard_view.data.get("extra_data")
        existing_limits = {}
        if extra_data:
            try:
                existing_limits = json.loads(extra_data).get("role_limits", {})
            except Exception as e:
                log.debug("RoleLimitsModal extra_data: %s", e)
            
        lines = []
        for opt in self.options:
            rid = opt["id"]
            lim = existing_limits.get(rid, opt.get("max_slots", 0))
            emoji = opt.get("emoji", "")
            lines.append(f"{emoji} {rid}: {lim}".strip())
            
        self.limits_input = ui.TextInput(
            label=t("LBL_ROLE_LIMITS_FORMAT", guild_id=wizard_view.guild_id),
            style=discord.TextStyle.paragraph,
            default="\n".join(lines),
            required=False,
        )
        self.add_item(self.limits_input)

    async def on_submit(self, interaction: discord.Interaction):
        role_limits = {}
        lines = str(self.limits_input.value).split("\n")
        for line in lines:
            if ":" not in line: continue
            left, right = line.rsplit(":", 1)
            right = right.strip()
            matched_id = None
            for opt in self.options:
                if opt["id"] in left:
                    matched_id = opt["id"]
                    break
            if matched_id and right.isdigit():
                role_limits[matched_id] = int(right)
                
        extra = self.wizard_view.data.get("extra_data", {})
        if isinstance(extra, str): extra = json.loads(extra)
        extra["role_limits"] = role_limits
        self.wizard_view.data["extra_data"] = json.dumps(extra)
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class RsvpRolesModal(ui.Modal):
    """Comma-separated role IDs; OR logic; empty = everyone can RSVP (stored on active_events)."""

    def __init__(self, wizard_view):
        super().__init__(title=t("TITLE_RSVP_ROLES", guild_id=wizard_view.guild_id)[:45])
        self.wizard_view = wizard_view
        gid = wizard_view.guild_id
        cur = database.normalize_rsvp_allowed_role_ids_value(wizard_view.data.get("rsvp_allowed_role_ids"))
        self.roles_input = ui.TextInput(
            label=t("LBL_RSVP_ALLOWED_ROLES", guild_id=gid)[:45],
            placeholder=t("PH_RSVP_ALLOWED_ROLES", guild_id=gid)[:45],
            default=cur,
            style=discord.TextStyle.paragraph,
            max_length=400,
            required=False,
        )
        self.add_item(self.roles_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.data["rsvp_allowed_role_ids"] = database.normalize_rsvp_allowed_role_ids_value(
            self.roles_input.value
        )
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class NotificationSettingsModal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=t("WIZARD_MESSAGES_TITLE", guild_id=wizard_view.guild_id))
        self.wizard_view = wizard_view
        extra = wizard_view.data.get("extra_data", {})
        if isinstance(extra, str): extra = json.loads(extra)
        
        self.promo_input = ui.TextInput(
            label=t("LBL_PROMO_MSG", guild_id=wizard_view.guild_id),
            default=extra.get("custom_promo_msg", ""),
            style=discord.TextStyle.paragraph,
            required=False
        )
        self.add_item(self.promo_input)

    async def on_submit(self, interaction: discord.Interaction):
        extra = self.wizard_view.data.get("extra_data", {})
        if isinstance(extra, str): extra = json.loads(extra)
        extra["custom_promo_msg"] = self.promo_input.value
        self.wizard_view.data["extra_data"] = json.dumps(extra)
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class ReminderMessagesModal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=t("TITLE_REMINDER_MESSAGES", guild_id=wizard_view.guild_id)[:45])
        self.wizard_view = wizard_view
        gid = wizard_view.guild_id
        data = wizard_view.data
        
        offsets = data.get("reminder_offsets") or []
        msgs = data.get("reminder_messages") or []
        
        # Ensure we don't display default if empty
        display_offsets = offsets if offsets else []
        
        self.inputs = []
        for i in range(len(display_offsets)):
            off_full = display_offsets[i]
            label = t("LBL_REMINDER_MSG_N", guild_id=gid, n=i+1, offset=off_full)
            
            default_val = msgs[i] if i < len(msgs) else ""
            
            inp = ui.TextInput(
                label=label[:45],
                style=discord.TextStyle.paragraph,
                default=str(default_val or ""),
                required=False,
                max_length=400
            )
            self.inputs.append(inp)
            self.add_item(inp)

    async def on_submit(self, interaction: discord.Interaction):
        msgs = [inp.value.strip() for inp in self.inputs]
        self.wizard_view.data["reminder_messages"] = msgs
        await self.wizard_view.save_to_draft()
        await self.wizard_view.refresh_message(interaction)

class EventWizardView(ui.LayoutView):
    """Main wizard controller using Components V2 architecture."""
    def __init__(self, bot, creator_id, existing_data=None, is_edit=False, guild_id=None, bulk_ids=None, wizard_type=None, show_advanced=False, show_reminder=False):
        super().__init__(timeout=600)
        self.bot = bot
        self.creator_id = creator_id
        self.is_edit = is_edit
        self.guild_id = guild_id
        self.bulk_ids = bulk_ids
        self.data = existing_data or {}

        # wizard_type detection/persistence
        if wizard_type:
            self.wizard_type = wizard_type
        elif self.data.get("wizard_type"):
            self.wizard_type = self.data["wizard_type"]
        elif self.data.get("lobby_mode"):
            self.wizard_type = "lobby"
        elif self.data.get("recurrence_type") and self.data["recurrence_type"] != "none":
            self.wizard_type = "series"
        else:
            # Fallback for old drafts or unspecified
            self.wizard_type = "single"
        
        # Ensure it's saved in data for future save_to_draft calls
        self.data["wizard_type"] = self.wizard_type

        self.show_advanced = show_advanced
        self.show_reminder = show_reminder

        self.can_publish = False
        self.chan_warning = ""
        if self.wizard_type == "lobby":
            s1 = bool(self.data.get("title"))
        elif self.wizard_type == "single":
            s1 = bool(self.data.get("title") and self.data.get("start_str"))
        else:
            s1 = bool(self.data.get("title"))
        self.steps_completed = {
            "step1": s1,
            "step2": bool(self.data.get("start_str") or self.data.get("start_time"))
            if self.wizard_type == "series"
            else bool(self.data.get("timezone")),
            "step3": bool(self.data.get("timezone")) if self.wizard_type == "series" else True,
        }

    async def refresh_message(self, interaction: discord.Interaction, send_followup: bool = False):
        view = EventWizardView(self.bot, self.creator_id, existing_data=self.data, is_edit=self.is_edit, guild_id=self.guild_id, bulk_ids=self.bulk_ids, wizard_type=self.wizard_type, show_advanced=self.show_advanced, show_reminder=self.show_reminder)
        view.can_publish = self.can_publish
        view.clear_items()
        await view.refresh_ui_data()
        
        # Components
        async def s1_cb(it):
            try:
                log.info(f"[Wizard] s1_cb called. wizard_type={view.wizard_type}, guild_id={view.guild_id}")
                if view.wizard_type == "series":
                    modal = Step1Modal(view)
                else:
                    modal = SingleEventModal(view)
                await it.response.send_modal(modal)
                log.info(f"[Wizard] Modal sent successfully")
            except Exception as e:
                log.error(f"[Wizard] s1_cb error: {e}", exc_info=True)
                if not it.response.is_done():
                    await it.response.send_message(f"{ERROR} {e}", ephemeral=True)
        step1 = ui.Button(label=t("BTN_STEP_1", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        step1.callback = s1_cb

        # Step 2: Single/Lobby = Supplementary, Series = Recurrence Settings
        async def s2_cb(it):
            if view.wizard_type in ("single", "lobby"):
                await it.response.send_modal(SingleEventSupplementaryModal(view))
            else:
                await it.response.send_modal(Step2Modal(view))

        if view.wizard_type == "lobby":
            s2_label = t("BTN_STEP_2_LOBBY", guild_id=self.guild_id)
        elif view.wizard_type == "single":
            s2_label = t("BTN_STEP_2_SINGLE", guild_id=self.guild_id)
        else:
            s2_label = t("BTN_STEP_2_SERIES", guild_id=self.guild_id)
        step2 = ui.Button(label=s2_label, style=discord.ButtonStyle.gray)
        step2.callback = s2_cb

        # Step 3: Series only — timezone, max participants, channel (multi-reminder: use Reminder toggle)
        async def s3_cb(it):
            if view.wizard_type == "series":
                await it.response.send_modal(Step3Modal(view))
            else:
                await it.response.send_modal(SingleEventSupplementaryModal(view))
        step3 = ui.Button(label=t("BTN_STEP_3_SERIES", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        step3.callback = s3_cb

        async def role_cb(it):
            from cogs.event_ui import get_active_set
            active_set = get_active_set(view.data.get("icon_set", "standard"))
            await it.response.send_modal(RoleLimitsModal(view, active_set))
        role_btn = ui.Button(label=t("BTN_ROLE_LIMITS", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        role_btn.callback = role_cb

        async def msg_cb(it): await it.response.send_modal(NotificationSettingsModal(view))
        msg_btn = ui.Button(label=t("BTN_MESSAGES", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        msg_btn.callback = msg_cb

        async def rsvp_roles_cb(it):
            await it.response.send_modal(RsvpRolesModal(view))

        rsvp_roles_btn = ui.Button(label=t("BTN_RSVP_ROLES", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        rsvp_roles_btn.callback = rsvp_roles_cb

        async def wait_cb(it):
            # Guard: waiting list requires at least one capacity limit
            has_global_cap = int(view.data.get("max_accepted") or 0) > 0
            has_role_cap = False
            extra = view.data.get("extra_data")
            if extra:
                try:
                    d = json.loads(extra) if isinstance(extra, str) else extra
                    rl = d.get("role_limits", {})
                    if any(int(v) > 0 for v in rl.values()):
                        has_role_cap = True
                except Exception:
                    pass
            
            if not has_global_cap and not has_role_cap:
                # Trying to enable without any capacity set
                if not view.data.get("use_waiting_list", False):
                    return await it.response.send_message(
                        t("ERR_WAITLIST_NO_CAP", guild_id=self.guild_id),
                        ephemeral=True,
                    )
            
            view.data["use_waiting_list"] = not view.data.get("use_waiting_list", False)
            await view.save_to_draft()
            await view.refresh_message(it)
        use_waiting = view.data.get("use_waiting_list", False)

        wait_btn = ui.Button(label=t("SEL_WAIT_ENABLED" if use_waiting else "SEL_WAIT_DISABLED", guild_id=self.guild_id), style=discord.ButtonStyle.green if use_waiting else discord.ButtonStyle.gray)
        wait_btn.callback = wait_cb

        # Temp Role Toggle
        async def temp_role_cb(it):
            view.data["use_temp_role"] = not view.data.get("use_temp_role", False)
            await view.save_to_draft()
            await view.refresh_message(it)
        
        use_temp = view.data.get("use_temp_role", False)
        temp_role_btn = ui.Button(
            label=t("LBL_WIZ_TEMP_ROLE", guild_id=self.guild_id) + (f": {t('LBL_TEMP_ROLE_ON', guild_id=self.guild_id)}" if use_temp else f": {t('LBL_TEMP_ROLE_OFF', guild_id=self.guild_id)}"),
            style=discord.ButtonStyle.green if use_temp else discord.ButtonStyle.gray
        )
        temp_role_btn.callback = temp_role_cb

        # Thread Toggle
        async def thread_cb(it):
            view.data["use_threads"] = not view.data.get("use_threads", False)
            await view.save_to_draft()
            await view.refresh_message(it)
        
        use_threads = view.data.get("use_threads", False)
        thread_btn = ui.Button(
            label=t("LBL_WIZ_THREADS", guild_id=self.guild_id) + (f": {t('LBL_THREADS_ON', guild_id=self.guild_id)}" if use_threads else f": {t('LBL_THREADS_OFF', guild_id=self.guild_id)}"),
            style=discord.ButtonStyle.green if use_threads else discord.ButtonStyle.gray
        )
        thread_btn.callback = thread_cb

        save_style = discord.ButtonStyle.green
        save_btn = ui.Button(label=t("BTN_SAVE_PREVIEW", guild_id=self.guild_id), style=save_style, disabled=view.can_publish)
        async def save_cb(it): await view.handle_save_preview(it)
        save_btn.callback = save_cb

        # Selects
        sel_rec = ui.Select(placeholder=t("SEL_REC_TYPE", guild_id=self.guild_id), options=view.recurrence_options)
        async def rec_cb(it):
            view.data["recurrence_type"] = sel_rec.values[0]
            await view.save_to_draft()
            await view.refresh_message(it)
        sel_rec.callback = rec_cb

        # Repost Trigger Select (Series only)
        if view.wizard_type == "series":
            cur_trig = view.data.get("repost_trigger", "after_end")
            trig_opts = [
                discord.SelectOption(label=t("SEL_TRIG_BEFORE", guild_id=self.guild_id), value="before_start", default=(cur_trig=="before_start")),
                discord.SelectOption(label=t("SEL_TRIG_AFTER_START", guild_id=self.guild_id), value="after_start", default=(cur_trig=="after_start")),
                discord.SelectOption(label=t("SEL_TRIG_AFTER_END", guild_id=self.guild_id), value="after_end", default=(cur_trig=="after_end")),
            ]
            sel_trig = ui.Select(placeholder=t("SEL_TRIG_TYPE", guild_id=self.guild_id), options=trig_opts)
            async def trig_cb(it):
                await it.response.defer()
                view.data["repost_trigger"] = sel_trig.values[0]
                await view.save_to_draft()
                await view.refresh_message(it)
            sel_trig.callback = trig_cb

        sel_icon = ui.Select(placeholder=t("SEL_ICON_SET", guild_id=self.guild_id), options=view.icon_set_options)
        async def icon_cb(it):
            await it.response.defer()
            view.data["icon_set"] = sel_icon.values[0]
            await view.save_to_draft()
            await view.refresh_message(it)
        sel_icon.callback = icon_cb

        # Single Event specific Advanced Toggles
        adv_btn = ui.Button(label=t("BTN_ADVANCED", guild_id=self.guild_id), emoji=to_emoji(DROPDOWN_OPEN) if view.show_advanced else to_emoji("◀️"), style=discord.ButtonStyle.secondary)
        async def adv_cb(it):
            await it.response.defer()
            view.show_advanced = not view.show_advanced
            if view.show_advanced:
                view.show_reminder = False
            await view.refresh_message(it)
        adv_btn.callback = adv_cb

        # Reminder Toggle
        rem_toggle_btn = ui.Button(label=t("BTN_REMINDER_TOGGLE", guild_id=self.guild_id), emoji=to_emoji(DROPDOWN_OPEN) if view.show_reminder else to_emoji("◀️"), style=discord.ButtonStyle.secondary)
        async def rem_toggle_cb(it):
            await it.response.defer()
            view.show_reminder = not view.show_reminder
            if view.show_reminder:
                view.show_advanced = False
            await view.refresh_message(it)
        rem_toggle_btn.callback = rem_toggle_cb

        # Reminder Offset Button (for expanded reminder section)
        rem_offset_btn = ui.Button(label=t("BTN_REMINDER_OFFSET", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def rem_offset_cb(it):
            class ReminderOffsetModal(ui.Modal):
                def __init__(self, v):
                    super().__init__(title=t("BTN_REMINDER_OFFSET", guild_id=v.guild_id)[:45])
                    self.v = v
                    ro = self.v.data.get("reminder_offsets")
                    if isinstance(ro, list) and ro:
                        dflt = "\n".join(ro[: database.MAX_EVENT_REMINDERS])
                    else:
                        dflt = str(self.v.data.get("reminder_offset", ""))
                    self.inp = ui.TextInput(
                        label=t("LBL_REMINDER_OFFSETS_PARAGRAPH", guild_id=v.guild_id),
                        placeholder="15m, 1h,dm,all, 30m,ping,Tank",
                        default=dflt,
                        style=discord.TextStyle.paragraph,
                        max_length=400,
                        required=False,
                    )
                    self.add_item(self.inp)
                async def on_submit(self, i):
                    raw_val = str(self.inp.value).strip()
                    if not raw_val:
                        # Empty modal = Disable reminders
                        self.v.data["reminder_offsets"] = []
                        self.v.data["reminder_type"] = "none"
                        self.v.data["reminder_offset"] = "" 
                        await self.v.save_to_draft()
                        return await self.v.refresh_message(i)

                    lines = [x.strip() for x in raw_val.splitlines() if x.strip()]
                    
                    # Validation
                    valid_pattern = re.compile(r"^(\d+)([mhd])(?:,([^,]*))?(?:,(.*))?$", re.IGNORECASE)
                    for line in lines:
                        if not valid_pattern.match(line):
                            return await i.response.send_message(
                                t("ERR_INVALID_OFFSET_FORMAT", guild_id=self.v.guild_id),
                                ephemeral=True
                            )
                    
                    self.v.data["reminder_offsets"] = lines[: database.MAX_EVENT_REMINDERS]
                    self.v.data["reminder_offset"] = lines[0] if lines else ""
                    await self.v.save_to_draft()
                    await self.v.refresh_message(i)
            await it.response.send_modal(ReminderOffsetModal(view))
        rem_offset_btn.callback = rem_offset_cb

        # New Reminder Messages Button
        rem_msg_raw = view.data.get("reminder_offsets") or []
        has_reminders = len(rem_msg_raw) > 0
        rem_msg_btn = ui.Button(
            label=t("BTN_REMINDER_MESSAGES", guild_id=self.guild_id), 
            style=discord.ButtonStyle.gray,
            disabled=not has_reminders
        )
        async def rem_msg_cb(it):
            await it.response.send_modal(ReminderMessagesModal(view))
        rem_msg_btn.callback = rem_msg_cb

        # Reminder Type Dropdown (lobby: megteléskori értesítés módja)
        cur_rem_type = view.data.get("reminder_type", "none")
        rem_type_opts = [
            discord.SelectOption(label=t("SEL_REM_NONE", guild_id=self.guild_id), value="none", default=(cur_rem_type=="none")),
            discord.SelectOption(label=t("SEL_REM_DM", guild_id=self.guild_id), value="dm", default=(cur_rem_type=="dm")),
            discord.SelectOption(label=t("SEL_REM_PING", guild_id=self.guild_id), value="ping", default=(cur_rem_type=="ping")),
            discord.SelectOption(label=t("SEL_REM_BOTH", guild_id=self.guild_id), value="both", default=(cur_rem_type=="both"))
        ]
        rem_ph = (
            t("SEL_LOBBY_FILL_NOTIFY", guild_id=self.guild_id)
            if view.wizard_type == "lobby"
            else t("BTN_REMINDERS", guild_id=self.guild_id)
        )
        rem_type_sel = ui.Select(placeholder=rem_ph, options=rem_type_opts)
        async def rem_type_cb(it):
            await it.response.defer()
            view.data["reminder_type"] = rem_type_sel.values[0]
            await view.save_to_draft()
            await view.refresh_message(it)
        rem_type_sel.callback = rem_type_cb

        # Promotion Notify Selection (Waiting List Automation)
        cur_promo_type = view.data.get("notify_promotion")
        if cur_promo_type is None:
            cur_promo_type = await database.get_guild_setting(self.guild_id, "default_notify_promotion", default="none")
            view.data["notify_promotion"] = cur_promo_type

        promo_type_opts = [
            discord.SelectOption(label=t("SEL_NOTIFY_NONE", guild_id=self.guild_id), value="none", default=(cur_promo_type=="none")),
            discord.SelectOption(label=t("SEL_NOTIFY_CHANNEL", guild_id=self.guild_id), value="channel", default=(cur_promo_type=="channel")),
            discord.SelectOption(label=t("SEL_NOTIFY_DM", guild_id=self.guild_id), value="dm", default=(cur_promo_type=="dm")),
            discord.SelectOption(label=t("SEL_NOTIFY_BOTH", guild_id=self.guild_id), value="both", default=(cur_promo_type=="both"))
        ]
        promo_type_sel = ui.Select(placeholder=t("LBL_PROMOTION_NOTIFY", guild_id=self.guild_id), options=promo_type_opts)
        async def promo_type_cb(it):
            await it.response.defer()
            view.data["notify_promotion"] = promo_type_sel.values[0]
            await view.save_to_draft()
            await view.refresh_message(it)
        promo_type_sel.callback = promo_type_cb

        creator_btn = ui.Button(label=t("LBL_WIZ_CREATOR", guild_id=self.guild_id), style=discord.ButtonStyle.gray)
        async def creator_cb(it):
            class CreatorModal(ui.Modal):
                def __init__(self, v):
                    super().__init__(title=t("LBL_WIZ_CREATOR", guild_id=v.guild_id)[:45])
                    self.v = v
                    self.inp = ui.TextInput(label=t("LBL_WIZ_CREATOR", guild_id=v.guild_id), default=str(v.data.get("creator_id") or v.creator_id), required=True)
                    self.add_item(self.inp)
                async def on_submit(self, i):
                    self.v.data["creator_id"] = str(self.inp.value)
                    await self.v.save_to_draft()
                    await self.v.refresh_message(i)
            await it.response.send_modal(CreatorModal(view))
        creator_btn.callback = creator_cb

        # Color Dropdown for Single Events
        cur_color_raw = view.data.get("color", "0x40c4ff")
        cur_color = cur_color_raw.lower().strip().replace("#", "0x")
        if not cur_color.startswith("0x"): cur_color = "0x" + cur_color
        
        color_opts = [
            make_select_option(label=t("COLOR_DEFAULT", guild_id=self.guild_id), value="0x40c4ff", default=(cur_color=="0x40c4ff")),
            make_select_option(label=t("COLOR_BLURPLE", guild_id=self.guild_id), value="0x5865f2", default=(cur_color=="0x5865f2")),
            make_select_option(label=t("COLOR_GOLD", guild_id=self.guild_id), value="0xffd700", default=(cur_color=="0xffd700")),
            make_select_option(label=t("COLOR_MINT", guild_id=self.guild_id), value="0x57f287", default=(cur_color=="0x57f287")),
            make_select_option(label=t("COLOR_FUCHSIA", guild_id=self.guild_id), value="0xeb459e", default=(cur_color=="0xeb459e")),
            make_select_option(label=t("COLOR_CUSTOM", guild_id=self.guild_id), value="custom", default=(cur_color not in ["0x40c4ff","0x5865f2","0xffd700","0x57f287","0xeb459e"]))
        ]
        color_sel = ui.Select(placeholder=t("SEL_COLOR", guild_id=self.guild_id), options=color_opts)
        async def color_cb(it):
            val = color_sel.values[0]
            if val == "custom":
                class ColorModal(ui.Modal):
                    def __init__(self, v):
                        super().__init__(title=t("COLOR_CUSTOM", guild_id=v.guild_id)[:45])
                        self.v = v
                        self.inp = ui.TextInput(label=t("LBL_WIZ_COLOR", guild_id=v.guild_id), default=cur_color, required=True)
                        self.add_item(self.inp)
                    async def on_submit(self, i):
                        self.v.data["color"] = str(self.inp.value)
                        await self.v.save_to_draft()
                        await self.v.refresh_message(i)
                await it.response.send_modal(ColorModal(view))
            else:
                await it.response.defer()
                view.data["color"] = val
                await view.save_to_draft()
                await view.refresh_message(it)
        color_sel.callback = color_cb

        # Complex Recurrence Selects
        if view.wizard_type == "series" and view.data.get("recurrence_type") == "custom":
            cust_days = view.data.get("custom_days", [])
            day_opts = [
                discord.SelectOption(label=t("DAY_MON", guild_id=self.guild_id), value="monday", default=("monday" in cust_days)),
                discord.SelectOption(label=t("DAY_TUE", guild_id=self.guild_id), value="tuesday", default=("tuesday" in cust_days)),
                discord.SelectOption(label=t("DAY_WED", guild_id=self.guild_id), value="wednesday", default=("wednesday" in cust_days)),
                discord.SelectOption(label=t("DAY_THU", guild_id=self.guild_id), value="thursday", default=("thursday" in cust_days)),
                discord.SelectOption(label=t("DAY_FRI", guild_id=self.guild_id), value="friday", default=("friday" in cust_days)),
                discord.SelectOption(label=t("DAY_SAT", guild_id=self.guild_id), value="saturday", default=("saturday" in cust_days)),
                discord.SelectOption(label=t("DAY_SUN", guild_id=self.guild_id), value="sunday", default=("sunday" in cust_days))
            ]
            cust_sel = ui.Select(placeholder=t("SEL_CUSTOM_DAYS", guild_id=self.guild_id), options=day_opts, min_values=1, max_values=7)
            async def cust_cb(it):
                await it.response.defer()
                view.data["custom_days"] = cust_sel.values
                await view.save_to_draft()
                await view.refresh_message(it)
            cust_sel.callback = cust_cb

        if view.wizard_type == "series" and view.data.get("recurrence_type") == "relative":
            rel_combo = view.data.get("relative_combo", [])
            rel_opts = [
                discord.SelectOption(label=t("REL_WEEK_1", guild_id=self.guild_id), value="wk_1", default=("wk_1" in rel_combo)),
                discord.SelectOption(label=t("REL_WEEK_2", guild_id=self.guild_id), value="wk_2", default=("wk_2" in rel_combo)),
                discord.SelectOption(label=t("REL_WEEK_3", guild_id=self.guild_id), value="wk_3", default=("wk_3" in rel_combo)),
                discord.SelectOption(label=t("REL_WEEK_4", guild_id=self.guild_id), value="wk_4", default=("wk_4" in rel_combo)),
                discord.SelectOption(label=t("REL_WEEK_LAST", guild_id=self.guild_id), value="wk_last", default=("wk_last" in rel_combo)),
                discord.SelectOption(label=t("DAY_MON", guild_id=self.guild_id), value="day_monday", default=("day_monday" in rel_combo)),
                discord.SelectOption(label=t("DAY_TUE", guild_id=self.guild_id), value="day_tuesday", default=("day_tuesday" in rel_combo)),
                discord.SelectOption(label=t("DAY_WED", guild_id=self.guild_id), value="day_wednesday", default=("day_wednesday" in rel_combo)),
                discord.SelectOption(label=t("DAY_THU", guild_id=self.guild_id), value="day_thursday", default=("day_thursday" in rel_combo)),
                discord.SelectOption(label=t("DAY_FRI", guild_id=self.guild_id), value="day_friday", default=("day_friday" in rel_combo)),
                discord.SelectOption(label=t("DAY_SAT", guild_id=self.guild_id), value="day_saturday", default=("day_saturday" in rel_combo)),
                discord.SelectOption(label=t("DAY_SUN", guild_id=self.guild_id), value="day_sunday", default=("day_sunday" in rel_combo))
            ]
            rel_sel = ui.Select(placeholder=t("SEL_REL_COMBO", guild_id=self.guild_id), options=rel_opts, min_values=1, max_values=2)
            async def rel_cb(it):
                await it.response.defer()
                view.data["relative_combo"] = rel_sel.values
                await view.save_to_draft()
                await view.refresh_message(it)
            rel_sel.callback = rel_cb

        # Container Assembly
        title_text = f"### {t('WIZARD_TITLE', guild_id=self.guild_id)}"
        if view.wizard_type == "lobby":
            title_text += f"\n{t('WIZARD_LOBBY_SUBTITLE', guild_id=self.guild_id)}"
        if view.bulk_ids: title_text += f" {t('LBL_BULK_EDIT', guild_id=self.guild_id)}"
        
        container_items = [
            ui.TextDisplay(title_text),
            ui.Separator(),
            ui.TextDisplay(self.chan_warning + "\n" + t("WIZARD_DESC", guild_id=self.guild_id, status=view.get_status_text()) if self.chan_warning else t("WIZARD_DESC", guild_id=self.guild_id, status=view.get_status_text())),
            ui.Separator()
        ]

        if view.can_publish:
            pub_btn = ui.Button(label=t("BTN_PUBLISH", guild_id=self.guild_id), style=discord.ButtonStyle.green)
            async def pub_cb(it): await view.publish_btn(it)
            pub_btn.callback = pub_cb

        if view.wizard_type == "single":
            container_items.append(ui.ActionRow(step1, step2, adv_btn, rem_toggle_btn))

            pub_row = [save_btn]
            if view.can_publish:
                pub_row.append(pub_btn)
            container_items.append(ui.ActionRow(*pub_row))

            if view.show_advanced:
                container_items.append(ui.Separator())
                container_items.append(ui.ActionRow(wait_btn, temp_role_btn, thread_btn))
                container_items.append(ui.ActionRow(creator_btn, role_btn, msg_btn, rsvp_roles_btn))
                container_items.append(ui.ActionRow(color_sel))
                container_items.append(ui.ActionRow(promo_type_sel))
                container_items.append(ui.Separator())
            elif view.show_reminder:
                ro_list = view.data.get("reminder_offsets") or []
                if not isinstance(ro_list, list):
                    ro_list = []
                off_preview = ", ".join(ro_list) if ro_list else str(view.data.get("reminder_offset") or "—")
                if len(off_preview) > 500:
                    off_preview = off_preview[:497] + "..."
                container_items.append(ui.Separator())
                container_items.append(
                    ui.TextDisplay(
                        t("LBL_REMINDER_LIST_PREVIEW", guild_id=self.guild_id, offsets=off_preview)
                    )
                )
                container_items.append(ui.ActionRow(rem_offset_btn, rem_msg_btn))
                container_items.append(ui.Separator())

            container_items.append(ui.ActionRow(sel_icon))
        elif view.wizard_type == "lobby":
            container_items.append(ui.ActionRow(step1, step2, adv_btn, rem_toggle_btn))

            pub_row = [save_btn]
            if view.can_publish:
                pub_row.append(pub_btn)
            container_items.append(ui.ActionRow(*pub_row))

            if view.show_advanced:
                container_items.append(ui.Separator())
                container_items.append(ui.ActionRow(temp_role_btn, thread_btn, creator_btn, role_btn, msg_btn))
                container_items.append(ui.ActionRow(rsvp_roles_btn))
                container_items.append(ui.ActionRow(color_sel))
                container_items.append(ui.Separator())
            elif view.show_reminder:
                container_items.append(ui.Separator())
                container_items.append(ui.TextDisplay(t("MSG_LOBBY_REMINDER_HINT", guild_id=self.guild_id)))
                container_items.append(ui.ActionRow(rem_type_sel))
                container_items.append(ui.Separator())

            container_items.append(ui.ActionRow(sel_icon))
        else:
            container_items.append(ui.ActionRow(step1, step2, step3))
            
            r2 = [adv_btn, rem_toggle_btn, save_btn]
            if view.can_publish: r2.append(pub_btn)
            container_items.append(ui.ActionRow(*r2))
            
            if view.show_advanced:
                container_items.append(ui.Separator())
                container_items.append(ui.ActionRow(wait_btn, temp_role_btn, creator_btn, role_btn, msg_btn))
                container_items.append(ui.ActionRow(rsvp_roles_btn))
                container_items.append(ui.ActionRow(color_sel))
                container_items.append(ui.ActionRow(promo_type_sel))
                container_items.append(ui.Separator())
            elif view.show_reminder:
                ro_list = view.data.get("reminder_offsets") or []
                if not isinstance(ro_list, list):
                    ro_list = []
                off_preview = ", ".join(ro_list) if ro_list else str(view.data.get("reminder_offset") or "—")
                if len(off_preview) > 500:
                    off_preview = off_preview[:497] + "..."
                container_items.append(ui.Separator())
                container_items.append(
                    ui.TextDisplay(
                        t("LBL_REMINDER_LIST_PREVIEW", guild_id=self.guild_id, offsets=off_preview)
                    )
                )
                container_items.append(ui.ActionRow(rem_offset_btn, rem_msg_btn))
                container_items.append(ui.Separator())
            
            container_items.append(ui.ActionRow(sel_rec))
            container_items.append(ui.ActionRow(sel_trig))
            
            if view.data.get("recurrence_type") == "custom":
                container_items.append(ui.ActionRow(cust_sel))
            elif view.data.get("recurrence_type") == "relative":
                container_items.append(ui.ActionRow(rel_sel))
                
            container_items.append(ui.ActionRow(sel_icon))

        view.add_item(ui.Container(*container_items, accent_color=0x40C4FF))
        
        if send_followup: await interaction.followup.send(view=view, ephemeral=True)
        elif interaction.response.is_done(): await interaction.edit_original_response(view=view)
        else: await interaction.response.edit_message(view=view)

    async def refresh_ui_data(self):
        current_set = self.data.get("icon_set", "standard")
        current_rec = self.data.get("recurrence_type", "none")
        
        # Load server-level defaults if missing in data
        if "repost_offset" not in self.data:
            self.data["repost_offset"] = await database.get_guild_setting(self.guild_id, "default_repost_offset", default="12h")
        if "repost_trigger" not in self.data:
            self.data["repost_trigger"] = await database.get_guild_setting(self.guild_id, "default_repost_trigger", default="after_end")
        if "reminder_offset" not in self.data:
            self.data["reminder_offset"] = await database.get_guild_setting(self.guild_id, "default_reminder_offset", default="")
        if "reminder_type" not in self.data:
            self.data["reminder_type"] = await database.get_guild_setting(self.guild_id, "reminder_type", default="none")
        if "reminder_offsets" not in self.data:
            ev_id = self.data.get("event_id")
            if ev_id:
                rem_rows = await database.get_event_reminders(ev_id)
                if rem_rows:
                    self.data["reminder_offsets"] = [r["offset_str"] for r in rem_rows]
                    self.data["reminder_messages"] = [r["custom_message"] for r in rem_rows]
                else:
                    def_ro = self.data.get("reminder_offset") or await database.get_guild_setting(
                        self.guild_id, "default_reminder_offset", default=""
                    )
                    ro_list = [x.strip() for x in def_ro.splitlines() if x.strip()]
                    rt = self.data.get("reminder_type") or await database.get_guild_setting(self.guild_id, "reminder_type", default="none")
                    self.data["reminder_offsets"] = ro_list if rt != "none" else []
                    self.data["reminder_messages"] = []
            else:
                    def_ro = await database.get_guild_setting(self.guild_id, "default_reminder_offset", default="")
                    ro_list = [x.strip() for x in def_ro.splitlines() if x.strip()]
                    rt = self.data.get("reminder_type") or await database.get_guild_setting(
                        self.guild_id, "reminder_type", default="none"
                    )
                    self.data["reminder_type"] = rt
                    self.data["reminder_offsets"] = ro_list if rt != "none" else []
                    self.data["reminder_messages"] = []
        if not (self.data.get("reminder_message") or "").strip() and self.data.get("extra_data"):
            try:
                ed = (
                    json.loads(self.data["extra_data"])
                    if isinstance(self.data["extra_data"], str)
                    else self.data["extra_data"]
                )
                if isinstance(ed, dict):
                    self.data["reminder_message"] = (
                        (ed.get("custom_reminder_msg") or "").strip() or None
                    )
            except Exception:
                pass
        if "color" not in self.data:
            self.data["color"] = await database.get_guild_setting(self.guild_id, "default_color", default="0x40C4FF")
        self.data["rsvp_allowed_role_ids"] = database.normalize_rsvp_allowed_role_ids_value(
            self.data.get("rsvp_allowed_role_ids")
        )
        if "timezone" not in self.data:
            self.data["timezone"] = await database.get_guild_setting(self.guild_id, "timezone", default=DEFAULT_TIMEZONE)

        if self.wizard_type == "lobby":
            self.data["lobby_mode"] = True
            self.data["use_waiting_list"] = False
            self.data["reminder_offsets"] = []
            if "lobby_expire_offset" not in self.data:
                self.data["lobby_expire_offset"] = "12h"
            if self.is_edit:
                rt = (self.data.get("reminder_type") or "none").strip().lower()
                if rt in ("none", "") and self.data.get("lobby_remind_on_fill", True):
                    g_rt = (
                        await database.get_guild_setting(self.guild_id, "reminder_type", default="none")
                        or "none"
                    ).strip().lower()
                    if g_rt not in ("none", ""):
                        self.data["reminder_type"] = g_rt
        
        if "max_accepted" not in self.data:
            m = await database.get_guild_setting(self.guild_id, "default_max_participants", default="0")
            self.data["max_accepted"] = int(m) if str(m).isdigit() else 0
            
        # Resolve Channel
        self.chan_warning = ""
        raw_ch = self.data.get("channel_id")
        if not raw_ch:
            raw_ch = await database.get_guild_setting(self.guild_id, "default_event_channel", default="")
        
        if raw_ch:
            guild = self.bot.get_guild(int(self.guild_id))
            if guild:
                ch_id = await resolve_channel(guild, raw_ch)
                if ch_id:
                    self.data["channel_id"] = ch_id
                else:
                    self.chan_warning = t("MSG_CHANNEL_NOT_FOUND", guild_id=self.guild_id).format(name=raw_ch)
                    # Don't overwrite channel_id if it was already an ID? 
                    # Actually if resolve failed, we should probably keep it as is for the user to fix 
                    # but the warning will show up.
        
        if "use_waiting_list" not in self.data:
            val = await database.get_guild_setting(self.guild_id, "default_use_waiting_list", default="false")
            self.data["use_waiting_list"] = val.lower() == "true"
        
        if "use_temp_role" not in self.data:
            val = await database.get_guild_setting(self.guild_id, "default_use_temp_role", default="false")
            self.data["use_temp_role"] = val.lower() == "true"
        
        # Build options for hardcoded templates
        self.icon_set_options = []
        for k, v in ICON_SET_TEMPLATES.items():
            opts, _ = parse_emoji_config(v["text"])
            preview_emojis = [o["emoji"] for o in opts[:3]]
            preview_raw = f" ( {' / '.join(preview_emojis)} )" if preview_emojis else ""
            preview_str = resolve_placeholders(preview_raw)
            label = t(v["label_key"], guild_id=self.guild_id) + preview_str
            
            self.icon_set_options.append(discord.SelectOption(
                label=label[:100], 
                value=k, 
                emoji=to_emoji(v["emoji"]) or None, 
                default=(current_set == k)
            ))
            
        # Build options for DB-based sets
        db_sets = await database.get_emoji_sets(self.guild_id)
        for s in db_sets:
            if s["set_id"] in ICON_SET_TEMPLATES: continue
            
            sdata = json.loads(s["data"]) if isinstance(s["data"], str) else s["data"]
            opts = sdata.get("options", [])
            preview_emojis = [o.get("emoji") or "?" for o in opts[:3]]
            preview_raw = f" ( {' / '.join(preview_emojis)} )" if preview_emojis else ""
            preview_str = resolve_placeholders(preview_raw)
            label = (s["name"][:30] + preview_str)[:100]
            
            self.icon_set_options.append(discord.SelectOption(
                label=label, 
                value=s["set_id"], 
                default=(current_set == s["set_id"])
            ))
            
        rec_types = [
            ("daily", REC_DAILY), ("weekly", REC_WEEKLY), ("monthly", REC_MONTHLY),
            ("biweekly", REC_BIWEEKLY), ("weekdays", REC_WEEKDAYS), ("weekends", REC_WEEKENDS),
            ("custom", REC_CUSTOM), ("relative", REC_RELATIVE)
        ]
        self.recurrence_options = [discord.SelectOption(label=t(f"SEL_REC_{k.upper()}", guild_id=self.guild_id), value=k, emoji=to_emoji(e), default=(current_rec == k)) for k, e in rec_types]

    def get_status_text(self):
        s1 = SUCCESS if self.steps_completed["step1"] else ERROR

        if self.wizard_type == "lobby":
            s2 = SUCCESS if self.steps_completed.get("step2") else f"{INFO} {t('LBL_OPTIONAL', guild_id=self.guild_id)}"
            return f"- {t('BTN_STEP_1', guild_id=self.guild_id)}: {s1}\n- {t('BTN_STEP_2_LOBBY', guild_id=self.guild_id)}: {s2}"
        if self.wizard_type == "single":
            s2 = SUCCESS if self.steps_completed.get("step2") else f"{INFO} {t('LBL_OPTIONAL', guild_id=self.guild_id)}"
            return f"- {t('BTN_STEP_1', guild_id=self.guild_id)}: {s1}\n- {t('BTN_STEP_2_SINGLE', guild_id=self.guild_id)}: {s2}"
        else:
            s2 = SUCCESS if self.steps_completed.get("step2") else ERROR
            s3 = SUCCESS if self.steps_completed.get("step3") else f"{INFO} {t('LBL_OPTIONAL', guild_id=self.guild_id)}"
            return f"- {t('BTN_STEP_1', guild_id=self.guild_id)}: {s1}\n- {t('BTN_STEP_2_SERIES', guild_id=self.guild_id)}: {s2}\n- {t('BTN_STEP_3_SERIES', guild_id=self.guild_id)}: {s3}"

    async def save_to_draft(self):
        self.can_publish = False
        if not self.data.get("draft_id"): self.data["draft_id"] = str(uuid.uuid4())[:8]
        await database.save_draft(self.guild_id, self.data["draft_id"], str(self.creator_id), self.data.get("title") or "manual", self.data)

    async def handle_save_preview(self, interaction: discord.Interaction):
        """Processes the Save & Preview logic and updates the V2 UI."""
        if not self.steps_completed["step1"] or (self.wizard_type != "single" and not self.steps_completed["step2"]):
            await interaction.response.send_message(t("ERR_FILL_STEPS", guild_id=self.guild_id), ephemeral=True)
            return
            
        if self.wizard_type == "series":
            rtype = self.data.get("recurrence_type")
            if rtype == "custom" and not self.data.get("custom_days"):
                await interaction.response.send_message(t("ERR_FILL_CUSTOM_DAYS", guild_id=self.guild_id), ephemeral=True)
                return
            if rtype == "relative":
                rel_combo = self.data.get("relative_combo", [])
                if len(rel_combo) != 2:
                    await interaction.response.send_message(t("ERR_FILL_RELATIVE", guild_id=self.guild_id), ephemeral=True)
                    return
                # Ensure they actually picked 1 week and 1 day, not 2 weeks or 2 days!
                has_wk = any(c.startswith("wk_") for c in rel_combo)
                has_day = any(c.startswith("day_") for c in rel_combo)
                if not (has_wk and has_day):
                    await interaction.response.send_message(t("ERR_FILL_RELATIVE_MIX", guild_id=self.guild_id), ephemeral=True)
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

        if self.wizard_type == "lobby":
            self.data["lobby_mode"] = True
            self.data["start_time"] = None
            self.data["end_time"] = None
            self.data["use_waiting_list"] = False
            self.data["reminder_offsets"] = []
            from cogs.event_ui import get_active_set
            from utils.lobby_utils import effective_lobby_capacity, role_limits_from_extra

            active_set = get_active_set(self.data.get("icon_set", "standard"))
            rl = role_limits_from_extra(self.data.get("extra_data"))
            cap = effective_lobby_capacity(int(self.data.get("max_accepted") or 0), active_set, rl)
            if cap is None:
                await interaction.response.send_message(
                    t("ERR_LOBBY_CAP_INVALID", guild_id=self.guild_id), ephemeral=True
                )
                return
        else:
            try:
                local_tz = tz.gettz(str(self.data.get("timezone") or DEFAULT_TIMEZONE))
                # provide a default 'now' to ensure 13:00 parses as today, not some default year like 2016
                base_now = datetime.datetime.now(local_tz)
                
                start_dt = parser.parse(str(self.data["start_str"]), default=base_now).replace(tzinfo=local_tz)
                self.data["start_time"] = start_dt.timestamp()

                if self.data.get("end_str"):
                    end_dt = parser.parse(str(self.data["end_str"]), default=start_dt).replace(
                        tzinfo=local_tz
                    )
                    self.data["end_time"] = end_dt.timestamp()
                else:
                    self.data["end_time"] = None
            except Exception as e:
                await interaction.response.send_message(
                    t("ERR_DATE_TZ", guild_id=self.guild_id, e=str(e)), ephemeral=True
                )
                return

        await interaction.response.defer(ephemeral=True)
        
        try:
            from cogs.event_ui import DynamicEventView
            event_id = str(self.data.get("event_id") or str(uuid.uuid4())[:8])
            self.data["event_id"] = event_id
            
            if self.is_edit:
                # Do not save to DB yet, wait for publish
                if "creator_id" not in self.data:
                    self.data["creator_id"] = str(self.creator_id)
            else:
                self.data["creator_id"] = str(self.data.get("creator_id") or self.creator_id)
                self.data["guild_id"] = self.guild_id
                
                target_channel_id = interaction.channel_id
                if self.data.get("channel_id") and str(self.data["channel_id"]).isdigit():
                    target_channel_id = int(self.data["channel_id"])
                    
                self.data["target_channel_id"] = target_channel_id

            self.can_publish = True
            
            view = DynamicEventView(self.bot, event_id, self.data, is_preview=True)
            await view.prepare()
            
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
                except Exception as e:
                    log.debug("handle_save_preview role_limits: %s", e)
            
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
                warning = t("WARN_ROLE_LIMIT_MISMATCH", guild_id=self.guild_id, role_sum=role_sum, global_max=global_max, default=f"\n\n{WARNING} **Figyelem:** A szerepkörök összege (**{role_sum}**) nem egyezik a globális limittel (**{global_max}**).")
                if role_sum < global_max:
                    warning += f"\nAz esemény már **{role_sum}** főnél meg fog telni, mert a szerepkörök betelnek."
                else:
                    warning += f"\nNéhány szerepkör gombja váratlanul kikapcsolhat **{global_max}** főnél."

            preview_text = t("MSG_SAVED_PREVIEW", guild_id=self.guild_id) + warning
            if preview_text:
                await interaction.followup.send(preview_text, ephemeral=True)
            await interaction.followup.send(view=view, ephemeral=True)
            await self.refresh_message(interaction)
        except Exception as e:
            log.error(f"Error in handle_save_preview: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    f"{ERROR} {t('ERR_CRITICAL_WIZARD', guild_id=self.guild_id)}: `{e}`",
                    ephemeral=True,
                )
            except Exception as send_err:
                log.error(f"handle_save_preview followup failed: {send_err}")
    async def publish_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        from cogs.event_ui import DynamicEventView, get_active_set
        from utils.offset_parse import parse_offset
        from utils.lobby_utils import effective_lobby_capacity, role_limits_from_extra

        event_id = self.data["event_id"]

        try:
            if self.wizard_type == "lobby":
                self.data["lobby_mode"] = True
                active_set = get_active_set(self.data.get("icon_set", "standard"))
                rl = role_limits_from_extra(self.data.get("extra_data"))
                cap = effective_lobby_capacity(int(self.data.get("max_accepted") or 0), active_set, rl)
                if cap is None:
                    await interaction.followup.send(
                        t("ERR_LOBBY_CAP_INVALID", guild_id=self.guild_id), ephemeral=True
                    )
                    return
                off = parse_offset(str(self.data.get("lobby_expire_offset") or "12h"))
                self.data["lobby_expires_at"] = time.time() + off.total_seconds()
                self.data["start_time"] = None
                self.data["end_time"] = None
                self.data["use_waiting_list"] = False
                self.data["reminder_offsets"] = []
                self.data["lobby_remind_on_fill"] = (
                    (self.data.get("reminder_type") or "none").lower() not in ("none", "")
                )

            # Temp Role Logic
            if self.data.get("use_temp_role") and not self.data.get("temp_role_id"):
                guild = self.bot.get_guild(int(self.guild_id))
                if guild:
                    title = (self.data.get("title") or "Event")[:30]
                    date_str = ""
                    try:
                        ts = float(self.data.get("start_time") or 0)
                        if ts:
                            dt = datetime.datetime.fromtimestamp(ts)
                            date_str = dt.strftime("%m%d")
                    except Exception as e:
                        log.debug("publish_btn temp role date_str: %s", e)
                    
                    role_name = f"{title} - {date_str}" if date_str else title
                    try:
                        new_role = await guild.create_role(name=role_name, mentionable=True, reason=f"Nexus Event: {event_id}")
                        self.data["temp_role_id"] = new_role.id
                        log.info(f"[Wizard] Created temp role {new_role.name} ({new_role.id}) for event {event_id}")
                    except Exception as e:
                        log.error(f"[Wizard] Failed to create temp role: {e}")
            
            target_chan = interaction.channel
            if self.data.get("channel_id") and str(self.data["channel_id"]).isdigit():
                chan = self.bot.get_channel(int(self.data["channel_id"]))
                if chan:
                    target_chan = chan
                else:
                    try:
                        target_chan = await self.bot.fetch_channel(int(self.data["channel_id"]))
                    except Exception as e:
                        log.warning(
                            "[Wizard] fetch_channel %s: %s",
                            self.data.get("channel_id"),
                            e,
                        )
                        
            # Save to Database RIGHT NOW
            if self.is_edit:
                if self.bulk_ids:
                    await database.update_active_events_metadata_bulk(self.bulk_ids, self.data)
                else:
                    await database.update_active_event(event_id, self.data)
            else:
                existing = await database.get_active_event(event_id, self.guild_id)
                target_cid = target_chan.id if target_chan else interaction.channel_id
                if not existing:
                    await database.create_active_event(
                        guild_id=self.guild_id,
                        event_id=event_id,
                        config_name=str(self.data.get("config_name") or "manual"),
                        channel_id=target_cid,
                        start_time=self.data["start_time"],
                        data=self.data
                    )
                else:
                    await database.update_active_event(event_id, self.data)

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
                                await view.prepare()
                                await msg.edit(view=view)
                            except Exception as e:
                                log.error(f"Error updating message {eid}: {e}")
                
                msg_text = t("MSG_BULK_UPDATE_DONE", guild_id=self.guild_id) if self.bulk_ids else t("MSG_UPDATED", guild_id=self.guild_id)
                await interaction.followup.send(msg_text, ephemeral=True)
            else:
                view = DynamicEventView(self.bot, event_id, self.data)
                await view.prepare()
                
                ping_role_id = self.data.get("ping_role")
                ping_prefix = ""
                if ping_role_id and str(ping_role_id).isdigit() and int(ping_role_id) > 0:
                    ping_prefix = f"{PING} <@&{ping_role_id}> "
                
                promo_msg = t("MSG_DEFAULT_PROMO", guild_id=self.guild_id)
                promo_content = f"{ping_prefix}{promo_msg}".strip()
                
                if promo_content:
                    await target_chan.send(content=promo_content)
                
                msg = await target_chan.send(view=view)
                await database.set_event_message(event_id, msg.id)
                self.bot.add_view(view)

                # --- NEW: Automatic Thread Creation ---
                if self.data.get("use_threads"):
                    try:
                        title = self.data.get("title") or "Event"
                        thread_name = title
                        
                        start_ts = self.data.get("start_time")
                        if start_ts and not self.data.get("lobby_mode"):
                            dt = datetime.datetime.fromtimestamp(float(start_ts))
                            thread_name = f"{title} - {dt.strftime('%m/%d')}"
                        
                        thread = await msg.create_thread(name=thread_name[:100])
                        
                        # Store thread_id in extra_data for future use
                        extra_data = self.data.get("extra_data", {})
                        if isinstance(extra_data, str):
                            extra_data = json.loads(extra_data)
                        extra_data["thread_id"] = thread.id
                        self.data["extra_data"] = json.dumps(extra_data)
                        await database.update_active_event(event_id, self.data)
                        
                        log.info(f"[Wizard] Created thread '{thread_name}' for event {event_id}")
                    except Exception as te:
                        log.error(f"[Wizard] Failed to create thread: {te}")

                await interaction.followup.send(
                    t("MSG_PUBLISHED_IN_CHANNEL", guild_id=self.guild_id, channel_id=target_chan.id),
                    ephemeral=True,
                )

            if self.data.get("draft_id"):
                await database.delete_draft(self.data.get("draft_id"), self.guild_id)

            await interaction.delete_original_response()
            self.stop()
        except Exception as e:
            log.error(f"[Wizard] Publish failed: {e}", exc_info=True)
            await interaction.followup.send(
                f"{ERROR} {t('ERR_PUBLISH_FAILED', guild_id=self.guild_id, e=str(e))}",
                ephemeral=True,
            )
