import discord
from discord.ext import commands
import database
from utils.i18n import t
import json
from utils.logger import log
import time
import random

# We try to load the config to see who is the boss (admin)
try:
    from utils.jsonc import load_jsonc
    config_data = load_jsonc('config.json')
    ADMIN_ROLE_ID = config_data.get("admin_role_id")
except Exception:
    ADMIN_ROLE_ID = None

from utils.auth import is_admin

def get_event_conf(name):
    # This helper gets the settings for a specific event type from config.json
    try:
        from utils.jsonc import load_jsonc
        config_data = load_jsonc('config.json')
        events = config_data.get("events_config", [])
        globals_cfg = config_data.get("globals", {})
        defaults = globals_cfg.get("event_defaults", {})
        
        for e in events:
            if e.get("config_name") == name or e.get("name") == name:
                # Merge defaults into event (event values take priority)
                merged = defaults.copy()
                merged.update(e)
                return merged
    except Exception as e:
        log.error(f"Error loading event config: {e}")
    return None

# This will hold sets loaded from the database
CUSTOM_ICON_SETS = {}

async def load_custom_sets():
    """Fetch custom emoji sets from database (Global and Guild-specific)."""
    global CUSTOM_ICON_SETS
    try:
        # 1. Load Global Sets from Database
        global_sets = await database.get_all_global_emoji_sets()
        for s in global_sets:
            data = s["data"]
            if isinstance(data, str):
                data = json.loads(data)
            CUSTOM_ICON_SETS[s["set_id"]] = data
        
        # 2. Load Guild-specific sets (overwrites global if IDs match)
        db_sets = await database.get_all_custom_emoji_sets()
        for s in db_sets:
            data = s["data"]
            if isinstance(data, str):
                data = json.loads(data)
            CUSTOM_ICON_SETS[s["set_id"]] = data
            
        log.info(f"Loaded {len(CUSTOM_ICON_SETS)} emoji sets from database.")
    except Exception as e:
        log.error(f"Failed to load custom emoji sets: {e}")

def get_active_set(key):
    """Return the set config for a given key, searching local cache."""
    return CUSTOM_ICON_SETS.get(key, CUSTOM_ICON_SETS.get("standard", {"options": []}))

class DynamicEventView(discord.ui.View):
    # This class creates the buttons people see under the event message
    def __init__(self, bot, event_id: str, event_conf: dict = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.event_id = event_id
        self.event_conf = event_conf

        # We check which icon set this event should use
        icon_set_key = "standard"
        if event_conf:
            icon_set_key = event_conf.get("icon_set", "standard")
        
        self.active_set = get_active_set(icon_set_key).copy()
        
        # Override limits if extra_data exists (per-event limits from Wizard)
        extra_data = event_conf.get("extra_data") if event_conf else None
        role_limits = {}
        if extra_data:
            try:
                if isinstance(extra_data, str):
                    role_limits = json.loads(extra_data).get("role_limits", {})
                else:
                    role_limits = extra_data.get("role_limits", {})
            except: pass

        per_row = self.active_set.get("buttons_per_row", 5)

        # We loop through the options and make a button for each one
        added_count = 0
        for i, opt in enumerate(self.active_set.get("options", [])):
            role_id = opt.get("id")
            if not role_id:
                continue
            # Apply override if available
            if role_id in role_limits:
                opt["max_slots"] = role_limits[role_id]

            label = opt.get("label") if "label" in opt else ""
            guild_id = self.event_conf.get("guild_id") if self.event_conf else None
            
            # Try to localize standard button labels
            if role_id in ["accepted", "declined", "tentative"]:
                label_key = f"BTN_{role_id.upper()}"
                localized_label = t(label_key, guild_id=guild_id)
                if localized_label != label_key:
                    label = localized_label

            row_idx = added_count // per_row
            
            if row_idx > 4:
                log.warning(f"Row limit reached for event {event_id}. Skipping option {role_id}.")
                break

            # Button Style logic
            btn_style = opt.get("button_style", "both")
            btn_emoji = opt.get("emoji") if btn_style in ["both", "emoji"] else None
            btn_label = label if btn_style in ["both", "label"] else None

            btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary, 
                emoji=btn_emoji or None,
                label=btn_label or None,
                custom_id=f"{role_id}_{event_id}",
                row=row_idx
            )
            
            def create_callback(status_id):
                async def callback(interaction: discord.Interaction):
                    await self.handle_rsvp(interaction, status_id)
                return callback
            
            btn.callback = create_callback(role_id)
            self.add_item(btn)
            added_count += 1

        # Calculate the next available row for utility buttons
        next_row = (added_count - 1) // per_row + 1 if added_count > 0 else 0
        if next_row > 4: next_row = 4

        # Management and Utility buttons
        if self.active_set.get("show_mgmt", True):
            # Calendar icon
            calendar_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="📅", custom_id=f"calendar_{event_id}", row=next_row)
            calendar_btn.callback = self.calendar_callback
            self.add_item(calendar_btn)

            guild_id = self.event_conf.get("guild_id") if self.event_conf else None
            
            edit_btn = discord.ui.Button(label=t("BTN_EDIT", guild_id=guild_id), style=discord.ButtonStyle.gray, custom_id=f"edit_{event_id}", row=next_row)
            edit_btn.callback = self.edit_callback
            self.add_item(edit_btn)

            delete_btn = discord.ui.Button(label=t("BTN_DELETE"), style=discord.ButtonStyle.danger, custom_id=f"delete_{event_id}", row=next_row)
            delete_btn.callback = self.delete_callback
            self.add_item(delete_btn)

    def update_button_states(self, rsvps_list, event_conf):
        """Disables buttons if limits are reached OR if status is inactive."""
        status = event_conf.get("status", "active")
        
        if status in ["cancelled", "postponed"]:
            for child in self.children:
                if isinstance(child, discord.ui.Button) and not child.custom_id.startswith(("edit_", "delete_", "calendar_")):
                    child.disabled = True
            return

        use_waiting = event_conf.get("use_waiting_list", True)
        if use_waiting:
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    if "_" in child.custom_id and not child.custom_id.startswith(("edit_", "delete_", "calendar_")):
                        child.disabled = False
            return

        max_acc = event_conf.get("max_accepted", 0)
        positive_statuses = [o["id"] for o in self.active_set["options"] if o.get("positive")]
        if not positive_statuses and "positive_count" in self.active_set:
            cnt = self.active_set["positive_count"]
            positive_statuses = [o["id"] for o in self.active_set["options"][:cnt]]

        extra_data = event_conf.get("extra_data")
        role_limits = {}
        if extra_data:
            try:
                d = json.loads(extra_data) if isinstance(extra_data, str) else extra_data
                role_limits = d.get("role_limits", {})
            except: pass

        total_pos = sum(1 for _, s in rsvps_list if s in positive_statuses)
        status_counts = {}
        for _, s in rsvps_list:
            status_counts[s] = status_counts.get(s, 0) + 1

        for child in self.children:
            if not isinstance(child, discord.ui.Button) or not child.custom_id: continue
            if child.custom_id.startswith(("edit_", "delete_", "calendar_")): continue

            parts = child.custom_id.split("_")
            if len(parts) < 2: continue
            role_id = "_".join(parts[:-1])

            child.disabled = False

            if role_id in positive_statuses and max_acc > 0:
                if total_pos >= max_acc: child.disabled = True

            role_limit = role_limits.get(role_id)
            if role_limit is None:
                opt = next((o for o in self.active_set.get("options", []) if o["id"] == role_id), None)
                if opt: role_limit = opt.get("max_slots")

            if role_limit and role_limit > 0:
                curr_role_count = status_counts.get(role_id, 0)
                if curr_role_count >= role_limit: child.disabled = True

    async def edit_callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        if not await is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        db_event = await database.get_active_event(self.event_id)
        if not db_event:
            await interaction.followup.send(t("ERR_EV_NOT_FOUND"), ephemeral=True)
            return

        config_name = db_event.get("config_name")
        if config_name and config_name != "manual":
            series_events = await database.get_active_events_by_config(config_name, interaction.guild_id)
            if len(series_events) > 1:
                view = EditChoiceView(self.bot, self.event_id, db_event, series_events)
                await interaction.followup.send(t("MSG_EDIT_SERIES_PROMPT", guild_id=guild_id), view=view, ephemeral=True)
                return

        await self._open_wizard(interaction, db_event)

    async def _open_wizard(self, interaction, db_event, bulk_ids=None):
        from dateutil import tz
        import datetime
        local_tz = tz.gettz(db_event.get("timezone", "Europe/Budapest"))
        if db_event.get("start_time"):
            start_dt = datetime.datetime.fromtimestamp(db_event["start_time"], tz=local_tz)
            db_event["start_str"] = start_dt.strftime("%Y-%m-%d %H:%M")
        
        if db_event.get("end_time"):
            end_dt = datetime.datetime.fromtimestamp(db_event["end_time"], tz=local_tz)
            db_event["end_str"] = end_dt.strftime("%Y-%m-%d %H:%M")
        else: db_event["end_str"] = ""

        from cogs.event_wizard import EventWizardView
        view = EventWizardView(self.bot, interaction.user.id, existing_data=db_event, is_edit=True, guild_id=interaction.guild_id, bulk_ids=bulk_ids)
        title = t("WIZARD_TITLE")
        if bulk_ids: title = f"📦 {title} (TÖMEGES SZERKESZTÉS)"
        embed = discord.Embed(title=title, description=t("WIZARD_DESC", status=view.get_status_text()), color=discord.Color.gold())
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def calendar_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db_event = await database.get_active_event(self.event_id)
        if not db_event: return await interaction.followup.send(t("ERR_EV_NOT_FOUND", guild_id=interaction.guild_id), ephemeral=True)
        
        from utils.calendar_utils import get_google_calendar_url, get_outlook_calendar_url, get_yahoo_calendar_url
        title = db_event.get("title") or "Event"
        desc = db_event.get("description") or ""
        start_ts = db_event["start_time"]
        end_ts = db_event.get("end_time")

        google_url = get_google_calendar_url(title, desc, start_ts, end_ts)
        outlook_url = get_outlook_calendar_url(title, desc, start_ts, end_ts)
        yahoo_url = get_yahoo_calendar_url(title, desc, start_ts, end_ts)

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label=t("BTN_GOOGLE"), url=google_url, emoji="💙"))
        view.add_item(discord.ui.Button(label=t("BTN_OUTLOOK"), url=outlook_url, emoji="🧡"))
        view.add_item(discord.ui.Button(label=t("BTN_YAHOO"), url=yahoo_url, emoji="💜"))
        await interaction.followup.send(t("MSG_CHOOSE_CALENDAR"), view=view, ephemeral=True)

    async def delete_callback(self, interaction: discord.Interaction):
        if not await is_admin(interaction):
            await interaction.response.send_message(t("ERR_NO_PERM", guild_id=interaction.guild_id), ephemeral=True)
            return
        await interaction.response.defer()
        await database.delete_active_event(self.event_id)
        guild_id = interaction.guild_id
        embed = interaction.message.embeds[0]
        embed.title = f"{t('TAG_DELETED', guild_id=guild_id)} {embed.title}"
        embed.color = discord.Color.red()
        for child in self.children: child.disabled = True
        await interaction.message.edit(embed=embed, view=self)
        log.info(f"Event {self.event_id} deleted by {interaction.user}")

    async def generate_embed(self, db_event=None):
        if not db_event: db_event = await database.get_active_event(self.event_id)
        if db_event and not self.event_conf:
            self.event_conf = get_event_conf(db_event["config_name"])
            if not self.event_conf:
                self.event_conf = dict(db_event)
                ex_raw = db_event.get("extra_data")
                if ex_raw:
                    try:
                        ex_dict = json.loads(ex_raw) if isinstance(ex_raw, str) else ex_raw
                        if isinstance(ex_dict, dict): self.event_conf.update(ex_dict)
                    except: pass
        guild_id = db_event.get("guild_id") if db_event else None
        if not self.event_conf: return discord.Embed(title=t("ERR_MISSING_CONFIG", guild_id=guild_id), color=discord.Color.red())

        rsvps = await database.get_rsvps(self.event_id)
        status_map = {opt["id"]: [] for opt in self.active_set["options"]}
        total_positive_count = 0
        positive_statuses = [o["id"] for o in self.active_set["options"] if o.get("positive")]
        if not positive_statuses and "positive_count" in self.active_set:
            cnt = self.active_set["positive_count"]
            positive_statuses = [o["id"] for o in self.active_set["options"][:cnt]]

        for user_id, status in rsvps:
            if status in status_map:
                status_map[status].append(f"<@{user_id}>")
                if status in positive_statuses: total_positive_count += 1

        max_acc = self.event_conf.get("max_accepted", 0)
        is_full = (max_acc > 0 and total_positive_count >= max_acc)
        desc = self.event_conf.get("description", "")
        if is_full: desc = f"### ⚠️ {t('EMBED_FULL', guild_id=guild_id) or 'ESEMÉNY BETELT'}\n{desc}"

        status = self.event_conf.get("status", "active")
        title_prefix, color_override = "", None
        if status == "cancelled": title_prefix = f"[{t('TAG_CANCELLED', guild_id=guild_id) or 'TÖRÖLVE'}] "; color_override = 0xed4245
        elif status == "postponed": title_prefix = f"[{t('TAG_POSTPONED', guild_id=guild_id) or 'ELHALASZTVA'}] "; color_override = 0xfaa61a

        embed = discord.Embed(title=f"{title_prefix}{self.event_conf.get('title', t('LBL_EVENT', guild_id=guild_id))}", description=desc, color=color_override or int(str(self.event_conf.get("color") or "0x3498db"), 16))
        
        guild_id = self.event_conf.get("guild_id")
        start_ts = db_event['start_time'] if db_event else time.time()
        embed.add_field(name=t("EMBED_START_TIME", guild_id=guild_id), value=f"<t:{int(start_ts)}:F>", inline=False)
        
        recurrence = self.event_conf.get('recurrence_type', 'none')
        if recurrence != 'none': embed.add_field(name=t("EMBED_RECURRENCE", guild_id=guild_id), value=recurrence.capitalize(), inline=False)
            
        extra_data = db_event.get("extra_data") if db_event else None
        role_limits = {}
        if extra_data:
            try:
                d = json.loads(extra_data) if isinstance(extra_data, str) else extra_data
                role_limits = d.get("role_limits", {})
            except: pass

        waiting_list = []
        for opt in self.active_set["options"]:
            role_id = opt["id"]
            users = status_map.get(role_id, [])
            limit = role_limits.get(role_id, opt.get("max_slots"))
            label_text = opt.get("list_label") or (t(opt["label_key"], guild_id=guild_id) if "label_key" in opt else opt.get("label", ""))
            
            count_text = str(len(users))
            is_pos = (role_id in positive_statuses)
            if is_pos and max_acc > 0: count_text = f"{len(users)}/{max_acc}"
            if limit: count_text = f"{len(users)}/{limit}"
            
            # Skip if hidden from list
            if not opt.get("show_in_list", True):
                continue

            name_parts = []
            if opt.get("emoji"): name_parts.append(opt["emoji"])
            if label_text: name_parts.append(label_text)
            embed.add_field(name=f"{' '.join(name_parts)} ({count_text})", value="\n".join(users) or t("EMBED_NONE"), inline=True)

            wait_tag = f"wait_{role_id}"
            if wait_tag in status_map:
                emoji = opt.get("emoji", "⏳")
                for u in status_map[wait_tag]: waiting_list.append(f"{emoji} {u}")

        if waiting_list: embed.add_field(name=f"⏳ {t('EMBED_WAITLIST', guild_id=guild_id) or 'Waiting List'} ({len(waiting_list)})", value="\n".join(waiting_list), inline=False)

        image_url = None
        if db_event and db_event.get("image_urls"): image_url = str(db_event["image_urls"]).split(",")[0].strip()
        elif self.event_conf.get("image_urls"):
            val = self.event_conf["image_urls"]
            if isinstance(val, list): image_url = random.choice(val)
            elif isinstance(val, str) and "," in val: image_url = random.choice([u.strip() for u in val.split(",")])
            else: image_url = str(val)
        if image_url: embed.set_image(url=image_url)
            
        creator_text = "System"
        cid = self.event_conf.get("creator_id")
        if cid and str(cid).isdigit():
            user = self.bot.get_user(int(cid)) or await self.bot.fetch_user(int(cid))
            if user: creator_text = f"@{user.display_name}"
        elif cid: creator_text = str(cid)
        embed.set_footer(text=t("EMBED_FOOTER", guild_id=guild_id, event_id=self.event_id, creator_id=creator_text))
        self.update_button_states(rsvps, self.event_conf)
        return embed

    async def handle_rsvp(self, interaction: discord.Interaction, status: str):
        db_event = await database.get_active_event(self.event_id)
        if not db_event: return await interaction.response.send_message(t("ERR_EV_NOT_FOUND"), ephemeral=True)
        if db_event["status"] != 'active': return await interaction.response.send_message(t("ERR_EV_INACTIVE"), ephemeral=True)
            
        if not self.event_conf:
            self.event_conf = get_event_conf(db_event["config_name"])
            if not self.event_conf:
                self.event_conf = dict(db_event)
                ex = db_event.get("extra_data")
                if ex:
                    try:
                        d = json.loads(ex) if isinstance(ex, str) else ex
                        if isinstance(d, dict): self.event_conf.update(d)
                    except: pass
        
        rsvps_list = await database.get_rsvps(self.event_id)
        old_status = next((s for uid, s in rsvps_list if uid == interaction.user.id), None)
        target_status, opt = status, next((o for o in self.active_set["options"] if o["id"] == status), None)
        
        ex = db_event.get("extra_data")
        role_limits = {}
        if ex:
            try: d = json.loads(ex) if isinstance(ex, str) else ex; role_limits = d.get("role_limits", {})
            except: pass
            
        role_limit = role_limits.get(status, opt.get("max_slots") if opt else None)
        if role_limit and sum(1 for _, s in rsvps_list if s == status) >= role_limit and old_status != status:
            if self.event_conf.get("use_waiting_list", True): target_status = f"wait_{status}"
            else: return await interaction.response.send_message(t("ERR_POS_FULL", guild_id=interaction.guild_id, name=(opt.get('label') or opt['id'])), ephemeral=True)

        positive_statuses = self.active_set.get("positive", [])
        if not positive_statuses and "positive_count" in self.active_set:
            cnt = self.active_set["positive_count"]; positive_statuses = [o["id"] for o in self.active_set["options"][:cnt]]

        if target_status in positive_statuses:
            max_acc = self.event_conf.get('max_accepted', 0)
            if max_acc > 0 and sum(1 for _, s in rsvps_list if s in positive_statuses) >= max_acc and old_status not in positive_statuses:
                if not target_status.startswith("wait_"): target_status = f"wait_{status}"

        await interaction.response.defer()
        await database.update_rsvp(self.event_id, interaction.user.id, target_status)

        if old_status and old_status != target_status:
            old_role_limit = role_limits.get(old_status, next((o.get("max_slots") for o in self.active_set["options"] if o["id"] == old_status), None))
            if old_role_limit:
                max_acc, current_acc = self.event_conf.get('max_accepted', 0), sum(1 for _, s in rsvps_list if s in positive_statuses)
                if max_acc == 0 or current_acc < max_acc:
                    promoted_uid = await database.promote_next_waiting(self.event_id, f"wait_{old_status}", old_status)
                    if promoted_uid: await self.notify_promotion(interaction, promoted_uid, next(o for o in self.active_set["options"] if o["id"] == old_status))

        embed = await self.generate_embed(db_event)
        await interaction.message.edit(embed=embed, view=self)
        log.info(f"User {interaction.user} RSVP'd {status} for event {self.event_id}", guild_id=interaction.guild_id)

    async def notify_promotion(self, interaction, user_id, opt):
        notify_type = self.event_conf.get("notify_promotion", "none")
        if notify_type == "none": return
        role_name = opt.get("label") or opt.get("list_label") or opt["id"]
        extra = self.event_conf.get("extra_data")
        custom_msg = None
        if extra:
            try: d = json.loads(extra) if isinstance(extra, str) else extra; custom_msg = d.get("custom_promo_msg")
            except: pass
        if custom_msg: msg = custom_msg.format(user_id=user_id, role=role_name, emoji=opt.get("emoji", ""), title=self.event_conf.get("title", ""))
        else: msg = t("MSG_PROMOTED_DEFAULT", guild_id=self.event_conf.get("guild_id"), user_id=user_id, role=role_name, emoji=opt.get("emoji", ""))
        if notify_type in ["channel", "both"]: await interaction.channel.send(msg)
        if notify_type in ["dm", "both"]:
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                if user: await user.send(msg)
            except: pass

class EditChoiceView(discord.ui.View):
    def __init__(self, bot, event_id, db_event, series_events):
        super().__init__(timeout=180); self.bot, self.event_id, self.db_event, self.series_events = bot, event_id, db_event, series_events
    @discord.ui.button(label=t("BTN_SINGLE_INSTANCE"), style=discord.ButtonStyle.secondary)
    async def edit_single(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True); await DynamicEventView(self.bot, self.event_id)._open_wizard(interaction, self.db_event)
    @discord.ui.button(label=t("BTN_ENTIRE_SERIES"), style=discord.ButtonStyle.primary)
    async def edit_series(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True); await DynamicEventView(self.bot, self.event_id)._open_wizard(interaction, self.db_event, bulk_ids=[ev['event_id'] for ev in self.series_events])

class StatusChoiceView(discord.ui.View):
    def __init__(self, bot, event_id, db_event, series_events, new_status, notify_type="none"):
        super().__init__(timeout=180); self.bot, self.event_id, self.db_event, self.series_events, self.new_status, self.notify_type = bot, event_id, db_event, series_events, new_status, notify_type
    @discord.ui.button(label=t("BTN_SINGLE_INSTANCE"), style=discord.ButtonStyle.secondary)
    async def status_single(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True); await database.update_event_status(self.event_id, self.new_status); await self.refresh_and_notify(interaction, [self.event_id]); await interaction.followup.send(t("MSG_STATUS_UPDATED", guild_id=interaction.guild_id, status=self.new_status), ephemeral=True)
    @discord.ui.button(label=t("BTN_ENTIRE_SERIES"), style=discord.ButtonStyle.primary)
    async def status_series(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True); ids = [ev['event_id'] for ev in self.series_events]; await database.update_event_status_bulk(ids, self.new_status); await self.refresh_and_notify(interaction, ids); await interaction.followup.send(t("MSG_SERIES_UPDATED", guild_id=interaction.guild_id, status=self.new_status), ephemeral=True)
    async def refresh_and_notify(self, interaction, event_ids):
        for eid in event_ids:
            ev = await database.get_active_event(eid)
            if ev and ev.get("message_id") and ev.get("channel_id"):
                chan = self.bot.get_channel(ev["channel_id"])
                if chan:
                    try:
                        msg = await chan.fetch_message(ev["message_id"]); view = DynamicEventView(self.bot, eid, ev); embed = await view.generate_embed(ev); await msg.edit(embed=embed, view=view)
                    except: pass
        if self.notify_type == "none": return
        participants = set()
        for eid in event_ids:
            rsvps = await database.get_rsvps(eid)
            for uid, s in rsvps:
                if not s.startswith("wait_"): participants.add(uid)
        if not participants: return
        status_text = self.new_status.upper()
        guild_id = interaction.guild_id
        if self.new_status == "cancelled": status_text = t("TAG_CANCELLED", guild_id=guild_id) or "TÖRÖLVE"
        if self.new_status == "postponed": status_text = t("TAG_POSTPONED", guild_id=guild_id) or "ELHALASZTVA"
        msg_body = t("MSG_EVENT_NOTIF_PREFIX", guild_id=guild_id, status=status_text, title=(self.db_event.get('title') or 'Event'))
        if self.notify_type in ["dm", "both"]:
            for uid in participants:
                try:
                    user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                    if user: await user.send(msg_body)
                except: pass
        if self.notify_type in ["chat", "both"]: await interaction.channel.send(f"{msg_body}\n{' '.join([f'<@{uid}>' for uid in participants])}")

async def setup(bot):
    await load_custom_sets()
