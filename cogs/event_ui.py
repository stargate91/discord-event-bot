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

def is_admin_user(interaction):
    # This checks if the person clicking a button has admin powers
    if interaction.user.guild_permissions.administrator:
        return True
    if ADMIN_ROLE_ID and discord.utils.get(interaction.user.roles, id=ADMIN_ROLE_ID):
        return True
    return False

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

# Here we define the different button sets like MMO or Teams
# These are now managed in config.json or database
ICON_SETS = {}

# This will hold sets loaded from the database
CUSTOM_ICON_SETS = {}

async def load_custom_sets():
    """Fetch custom emoji sets from config.json AND database."""
    global CUSTOM_ICON_SETS
    try:
        # 1. Load from config.json first
        from utils.jsonc import load_jsonc
        config = load_jsonc('config.json')
        config_sets = config.get("emoji_sets", [])
        for s in config_sets:
            if "set_id" in s and "data" in s:
                CUSTOM_ICON_SETS[s["set_id"]] = s["data"]
        
        # 2. Load from database (overwrites config if IDs match)
        db_sets = await database.get_all_custom_emoji_sets()
        for s in db_sets:
            CUSTOM_ICON_SETS[s["set_id"]] = s["data"]
            
        log.info(f"Loaded {len(CUSTOM_ICON_SETS)} custom emoji sets.")
    except Exception as e:
        log.error(f"Failed to load custom emoji sets: {e}")

def get_active_set(key):
    """Return the set config for a given key, searching local cache."""
    # Fallback to standard if key not found, and then to a bare minimum structure
    # to prevent KeyError: 'options' in views.
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
            row_idx = added_count // per_row
            
            if row_idx > 4:
                log.warning(f"Row limit reached for event {event_id}. Skipping option {role_id}.")
                break

            btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary, 
                emoji=opt.get("emoji") or None,
                label=label or None,
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

        # We add the calendar icon
        calendar_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="📅", custom_id=f"calendar_{event_id}", row=next_row)
        calendar_btn.callback = self.calendar_callback
        self.add_item(calendar_btn)

        # Management buttons
        if self.active_set.get("show_mgmt"):
            edit_btn = discord.ui.Button(label=t("BTN_EDIT"), style=discord.ButtonStyle.gray, custom_id=f"edit_{event_id}", row=next_row)
            edit_btn.callback = self.edit_callback
            self.add_item(edit_btn)

            delete_btn = discord.ui.Button(label=t("BTN_DELETE"), style=discord.ButtonStyle.danger, custom_id=f"delete_{event_id}", row=next_row)
            delete_btn.callback = self.delete_callback
            self.add_item(delete_btn)

    def update_button_states(self, rsvps_list, event_conf):
        """Disables buttons if limits are reached and waiting list is off."""
        use_waiting = event_conf.get("use_waiting_list", True)
        if use_waiting:
            # If waiting list is ON, we don't disable buttons (people can join waitlist)
            for child in self.children:
                if isinstance(child, discord.ui.Button) and not hasattr(child, "_original_disabled"):
                    # Don't touch utility buttons (edit/delete)
                    if "_" in child.custom_id and not child.custom_id.startswith(("edit_", "delete_", "calendar_")):
                        child.disabled = False
            return

        # 1. Get Limits
        max_acc = event_conf.get("max_accepted", 0)
        positive_statuses = []
        if "positive" in self.active_set:
            positive_statuses = self.active_set["positive"]
        elif "positive_count" in self.active_set:
            cnt = self.active_set["positive_count"]
            positive_statuses = [o["id"] for o in self.active_set["options"][:cnt]]

        extra_data = event_conf.get("extra_data")
        role_limits = {}
        if extra_data:
            try:
                d = json.loads(extra_data) if isinstance(extra_data, str) else extra_data
                role_limits = d.get("role_limits", {})
            except: pass

        # 2. Current counts
        total_pos = sum(1 for _, s in rsvps_list if s in positive_statuses)
        status_counts = {}
        for _, s in rsvps_list:
            status_counts[s] = status_counts.get(s, 0) + 1

        # 3. Update Buttons
        for child in self.children:
            if not isinstance(child, discord.ui.Button) or not child.custom_id:
                continue
            
            # Skip utility buttons
            if child.custom_id.startswith(("edit_", "delete_", "calendar_")):
                continue

            # Extract role_id from custom_id (role_id_event_id)
            parts = child.custom_id.split("_")
            if len(parts) < 2: continue
            role_id = "_".join(parts[:-1]) # Handles roles with underscores

            # Default to enabled
            child.disabled = False

            # Check Global Limit
            if role_id in positive_statuses and max_acc > 0:
                if total_pos >= max_acc:
                    child.disabled = True

            # Check Per-Role Limit
            role_limit = role_limits.get(role_id)
            if role_limit is None:
                # Check global set default
                opt = next((o for o in self.active_set.get("options", []) if o["id"] == role_id), None)
                if opt:
                    role_limit = opt.get("max_slots")

            if role_limit and role_limit > 0:
                curr_role_count = status_counts.get(role_id, 0)
                if curr_role_count >= role_limit:
                    child.disabled = True

    async def edit_callback(self, interaction: discord.Interaction):
        # When an admin clicks Edit, we check if it's part of a series
        if not is_admin_user(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        db_event = await database.get_active_event(self.event_id)
        if not db_event:
            await interaction.followup.send(t("ERR_EV_NOT_FOUND"), ephemeral=True)
            return

        config_name = db_event.get("config_name")
        if config_name and config_name != "manual":
            # Check if there are other instances of this series
            series_events = await database.get_active_events_by_config(config_name, interaction.guild_id)
            if len(series_events) > 1:
                # Show choice view
                view = EditChoiceView(self.bot, self.event_id, db_event, series_events)
                await interaction.followup.send(
                    "💡 Ez az esemény egy ismétlődő sorozat része. Mit szeretnél szerkeszteni?",
                    view=view,
                    ephemeral=True
                )
                return

        # If not a series or logic above falls through, open wizard directly
        await self._open_wizard(interaction, db_event)

    async def _open_wizard(self, interaction, db_event, bulk_ids=None):
        # Helper to turn timestamps into readable text for the wizard
        from dateutil import tz
        import datetime
        local_tz = tz.gettz(db_event.get("timezone", "Europe/Budapest"))
        if db_event.get("start_time"):
            start_dt = datetime.datetime.fromtimestamp(db_event["start_time"], tz=local_tz)
            db_event["start_str"] = start_dt.strftime("%Y-%m-%d %H:%M")
        
        if db_event.get("end_time"):
            end_dt = datetime.datetime.fromtimestamp(db_event["end_time"], tz=local_tz)
            db_event["end_str"] = end_dt.strftime("%Y-%m-%d %H:%M")
        else:
            db_event["end_str"] = ""

        # Open the Wizard view in "edit" mode
        from cogs.event_wizard import EventWizardView
        view = EventWizardView(
            self.bot, 
            interaction.user.id, 
            existing_data=db_event, 
            is_edit=True, 
            guild_id=interaction.guild_id,
            bulk_ids=bulk_ids
        )
        
        title = t("WIZARD_TITLE")
        if bulk_ids:
            title = f"📦 {title} (TÖMEGES SZERKESZTÉS)"

        embed = discord.Embed(
            title=title, 
            description=t("WIZARD_DESC", status=view.get_status_text()), 
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class EditChoiceView(discord.ui.View):
    """Small popup view to choose between editing one instance or the whole series."""
    def __init__(self, bot, event_id, db_event, series_events):
        super().__init__(timeout=180)
        self.bot = bot
        self.event_id = event_id
        self.db_event = db_event
        self.series_events = series_events

    @discord.ui.button(label="Csak ezt a példányt", style=discord.ButtonStyle.secondary)
    async def edit_single(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        # We need the parent view's logic, but since it's a callback we just call open_wizard
        # or we could make _open_wizard a standalone helper.
        dummy_view = DynamicEventView(self.bot, self.event_id) 
        await dummy_view._open_wizard(interaction, self.db_event)

    @discord.ui.button(label="Az egész sorozatot (Tömeges)", style=discord.ButtonStyle.primary)
    async def edit_series(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        bulk_ids = [ev['event_id'] for ev in self.series_events]
        dummy_view = DynamicEventView(self.bot, self.event_id)
        await dummy_view._open_wizard(interaction, self.db_event, bulk_ids=bulk_ids)


    async def calendar_callback(self, interaction: discord.Interaction):
        # Shows links to Google Calendar, Yahoo, etc.
        await interaction.response.defer(ephemeral=True)
        db_event = await database.get_active_event(self.event_id)
        if not db_event:
            await interaction.followup.send("Event not found.", ephemeral=True)
            return
        
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
        # Only admins can delete the event
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(t("ERR_NO_PERM"), ephemeral=True)
            return

        await interaction.response.defer()
        await database.delete_active_event(self.event_id)
        
        # We change the embed look to show it's deleted
        embed = interaction.message.embeds[0]
        embed.title = f"{t('TAG_DELETED')} {embed.title}"
        embed.color = discord.Color.red()
        
        # Turn off all buttons
        for child in self.children:
            child.disabled = True
            
        await interaction.message.edit(embed=embed, view=self)
        log.info(f"Event {self.event_id} deleted by {interaction.user}")

    async def generate_embed(self, db_event=None):
        # This builds the main fancy rectangular message (Embed)
        if not db_event:
            db_event = await database.get_active_event(self.event_id)
            
        if db_event and not self.event_conf:
            self.event_conf = get_event_conf(db_event["config_name"])
            if not self.event_conf:
                # Merge row data with extra_data if available
                self.event_conf = dict(db_event)
                ex_raw = db_event.get("extra_data")
                if ex_raw:
                    try:
                        ex_dict = json.loads(ex_raw) if isinstance(ex_raw, str) else ex_raw
                        if isinstance(ex_dict, dict):
                            self.event_conf.update(ex_dict)
                    except: pass

        if not self.event_conf:
            return discord.Embed(title="Missing configuration", color=discord.Color.red())

        rsvps = await database.get_rsvps(self.event_id)
        
        # Group users by their choices (Accepted, Tanks, etc)
        status_map = {opt["id"]: [] for opt in self.active_set["options"]}
        
        total_positive_count = 0
        positive_statuses = []
        if "positive" in self.active_set:
            positive_statuses = self.active_set["positive"]
        elif "positive_count" in self.active_set:
            cnt = self.active_set["positive_count"]
            positive_statuses = [o["id"] for o in self.active_set["options"][:cnt]]

        for user_id, status in rsvps:
            if status in status_map:
                tag = f"<@{user_id}>"
                status_map[status].append(tag)
                
                if status in positive_statuses:
                    total_positive_count += 1

        max_acc = self.event_conf.get("max_accepted", 0)
        is_full = (max_acc > 0 and total_positive_count >= max_acc)

        desc = self.event_conf.get("description", "")
        if is_full:
            full_text = t("EMBED_FULL") or "ESEMÉNY BETELT"
            desc = f"### ⚠️ {full_text}\n{desc}"

        embed = discord.Embed(
            title=self.event_conf.get("title", "Event"),
            description=desc,
            color=int(str(self.event_conf.get("color") or "0x3498db"), 16)
        )
        
        # Add the start time (Discord makes this pretty automatically)
        start_ts = db_event['start_time'] if db_event else time.time()
        embed.add_field(name=t("EMBED_START_TIME"), value=f"<t:{int(start_ts)}:F>", inline=False)
        
        # Add repetition info if it repeats
        recurrence = self.event_conf.get('recurrence_type', 'none')
        if recurrence != 'none':
            embed.add_field(name=t("EMBED_RECURRENCE"), value=recurrence.capitalize(), inline=False)
            
        # Add lists of people for each status
        max_acc = self.event_conf.get('max_accepted', 0)
        
        # Merge per-event role limits from extra_data
        extra_data = db_event.get("extra_data") if db_event else None
        role_limits = {}
        if extra_data:
            try:
                if isinstance(extra_data, str):
                    role_limits = json.loads(extra_data).get("role_limits", {})
                else:
                    role_limits = extra_data.get("role_limits", {})
            except: pass

        # We also collect people on the waiting list for later
        waiting_list = []

        for opt in self.active_set["options"]:
            role_id = opt["id"]
            users = status_map.get(role_id, [])
            
            # Apply per-event override
            limit = role_limits.get(role_id, opt.get("max_slots"))
            if "list_label" in opt:
                label_text = opt["list_label"]
            elif "label_key" in opt:
                label_text = t(opt["label_key"])
            else:
                label_text = opt.get("label", "")
            
            # Show how many people joined (and max limit if set)
            count_text = str(len(users))
            # Support both "accepted" ID and first N options via positive_count
            is_positive = False
            if "positive" in self.active_set:
                is_positive = (opt["id"] in self.active_set["positive"])
            elif "positive_count" in self.active_set:
                idx = self.active_set["options"].index(opt)
                is_positive = (idx < self.active_set["positive_count"])

            if is_positive and max_acc > 0:
                count_text = f"{len(users)}/{max_acc}"
            
            # Per-role limit display
            if limit:
                count_text = f"{len(users)}/{limit}"
            
            # Format field name
            name_parts = []
            if opt.get("emoji"):
                name_parts.append(opt["emoji"])
            if label_text:
                name_parts.append(label_text)
            
            field_name = f"{' '.join(name_parts)} ({count_text})"
            embed.add_field(name=field_name, value="\n".join(users) or t("EMBED_NONE"), inline=True)

            # Collect waiting users for this specific role
            wait_tag = f"wait_{opt['id']}"
            if wait_tag in status_map:
                emoji = opt.get("emoji", "⏳")
                for u in status_map[wait_tag]:
                    waiting_list.append(f"{emoji} {u}")

        # Add the waiting list if there are people in it
        if waiting_list:
            embed.add_field(name=f"⏳ {t('EMBED_WAITLIST') or 'Waiting List'} ({len(waiting_list)})", value="\n".join(waiting_list), inline=False)

        # Handle images — use the stored (already-chosen) URL from the database
        image_url = None
        if db_event and db_event.get("image_urls"):
            image_url = str(db_event["image_urls"]).split(",")[0].strip()
        elif self.event_conf.get("image_urls"):
            val = self.event_conf["image_urls"]
            if isinstance(val, list):
                image_url = random.choice(val)
            elif isinstance(val, str) and "," in val:
                image_url = random.choice([u.strip() for u in val.split(",")])
            else:
                image_url = str(val)
        
        if image_url:
            embed.set_image(url=image_url)
            
        # Add footer with IDs and Creator name
        creator_text = "System"
        creator_id_val = self.event_conf.get("creator_id")
        
        if creator_id_val:
            if str(creator_id_val).isdigit():
                user = self.bot.get_user(int(creator_id_val))
                if not user:
                    try:
                        user = await self.bot.fetch_user(int(creator_id_val))
                    except:
                        user = None
                
                if user:
                    creator_text = f"@{user.display_name}"
                else:
                    # If it's a number but no user found, fallback to System
                    creator_text = "System"
            else:
                # If it's not a number, it's a manual name (e.g. "The Bot God")
                creator_text = str(creator_id_val)

        embed.set_footer(text=t("EMBED_FOOTER", event_id=self.event_id, creator_id=creator_text))

        # Update visual button states based on current counts
        self.update_button_states(rsvps_list, self.event_conf)

        return embed

    async def handle_rsvp(self, interaction: discord.Interaction, status: str):
        # This handles when someone clicks an RSVP button
        db_event = await database.get_active_event(self.event_id)
        if not db_event:
            await interaction.response.send_message(t("ERR_EV_NOT_FOUND"), ephemeral=True)
            return

        if db_event["status"] != 'active':
            await interaction.response.send_message(t("ERR_EV_INACTIVE"), ephemeral=True)
            return
            
        if not self.event_conf:
            self.event_conf = get_event_conf(db_event["config_name"])
            if not self.event_conf:
                # Merge row data with extra_data if available
                self.event_conf = dict(db_event)
                extra_data_raw = db_event.get("extra_data")
                if extra_data_raw:
                    try:
                        extra_dict = json.loads(extra_data_raw) if isinstance(extra_data_raw, str) else extra_data_raw
                        if isinstance(extra_dict, dict):
                            self.event_conf.update(extra_dict)
                    except: pass
        
        # Check if the user is leaving a slot that might have a waiting list
        rsvps_list = await database.get_rsvps(self.event_id)
        old_status = next((s for uid, s in rsvps_list if uid == interaction.user.id), None)

        # 1. Capacity Check for the new status
        target_status = status
        opt = next((o for o in self.active_set["options"] if o["id"] == status), None)
        
        # Get limit (priority: per-event extra_data > global set default)
        extra_data_raw = db_event.get("extra_data")
        role_limits = {}
        if extra_data_raw:
            try:
                if isinstance(extra_data_raw, str):
                    role_limits = json.loads(extra_data_raw).get("role_limits", {})
                else:
                    role_limits = extra_data_raw.get("role_limits", {})
            except: pass
            
        role_limit = role_limits.get(status, opt.get("max_slots") if opt else None)

        if role_limit:
            current_count = sum(1 for _, s in rsvps_list if s == status)
            if current_count >= role_limit and old_status != status:
                # Check if waiting list is enabled
                if self.event_conf.get("use_waiting_list", True):
                    target_status = f"wait_{status}"
                else:
                    await interaction.response.send_message(f"Sajnálom, a(z) {opt.get('label') or opt['id']} pozíció betelt!", ephemeral=True)
                    return

        # 2. Total Capacity Check (Existing logic)
        positive_statuses = []
        if "positive" in self.active_set:
            positive_statuses = self.active_set["positive"]
        elif "positive_count" in self.active_set:
            cnt = self.active_set["positive_count"]
            positive_statuses = [o["id"] for o in self.active_set["options"][:cnt]]

        if target_status in positive_statuses:
            max_acc = self.event_conf.get('max_accepted', 0)
            if max_acc > 0:
                current_acc = sum(1 for _, s in rsvps_list if s in positive_statuses)
                already_has_positive = (old_status in positive_statuses)
                if not already_has_positive and current_acc >= max_acc:
                    # If total event is full, we could also move them to a global waitlist
                    # For now, let's just use the per-role waitlist if available or block
                    if not target_status.startswith("wait_"):
                        target_status = f"wait_{status}"

        # 3. Save the new status
        await interaction.response.defer()
        await database.update_rsvp(self.event_id, interaction.user.id, target_status)

        # 4. Handle Promotion (If someone left a limited slot)
        if old_status and old_status != target_status:
            # Check if old_status had a limit and someone is waiting
            old_role_limit = role_limits.get(old_status, next((o.get("max_slots") for o in self.active_set["options"] if o["id"] == old_status), None))
            
            if old_role_limit:
                # Safety: Only promote if we are under global capacity (if limit exists)
                can_promote = True
                max_acc = self.event_conf.get('max_accepted', 0)
                if max_acc > 0:
                    current_acc = sum(1 for _, s in rsvps_list if s in positive_statuses)
                    if current_acc >= max_acc:
                        can_promote = False
                
                if can_promote:
                    promoted_uid = await database.promote_next_waiting(self.event_id, f"wait_{old_status}", old_status)
                    if promoted_uid:
                        await self.notify_promotion(interaction, promoted_uid, next(o for o in self.active_set["options"] if o["id"] == old_status))

        embed = await self.generate_embed(db_event)
        await interaction.message.edit(embed=embed, view=self)
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) RSVP'd {status} for event {self.event_id}")

    async def notify_promotion(self, interaction, user_id, opt):
        # Handle the "someone got in" notification
        notify_type = self.event_conf.get("notify_promotion", "none")
        if notify_type == "none":
            return

        emoji = opt.get("emoji", "")
        role_name = opt.get("label") or opt.get("list_label") or opt["id"]
        event_title = self.event_conf.get("title", "")

        # Check for custom message in extra_data
        extra_data = self.event_conf.get("extra_data")
        custom_msg = None
        if extra_data:
            try:
                if isinstance(extra_data, str):
                    custom_msg = json.loads(extra_data).get("custom_promo_msg")
                else:
                    custom_msg = extra_data.get("custom_promo_msg")
            except: pass

        if custom_msg:
            msg = custom_msg.format(user_id=user_id, role=role_name, emoji=emoji, title=event_title)
        else:
            msg = t("MSG_PROMOTED_DEFAULT", user_id=user_id, role=role_name, emoji=emoji)

        if notify_type in ["channel", "both"]:
            await interaction.channel.send(msg)
        
        if notify_type in ["dm", "both"]:
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                if user:
                    await user.send(msg)
            except:
                pass

async def setup(bot):
    # This is for discord.py to load this extension
    await load_custom_sets()
