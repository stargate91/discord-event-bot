import discord
from discord.ext import commands
import database
from utils.i18n import t
from database import DEFAULT_TIMEZONE
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
    """Return the set config for a given key, searching templates first then DB cache."""
    # 1. Check hardcoded templates first (authoritative for standard IDs)
    from utils.templates import get_template_data
    tmpl_data = get_template_data(key)
    if tmpl_data:
        return tmpl_data
    
    # 2. Fall back to DB-loaded custom sets
    if key in CUSTOM_ICON_SETS:
        return CUSTOM_ICON_SETS[key]
    
    return {"options": []}

class DynamicEventView(discord.ui.LayoutView):
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
        
    async def prepare(self):
        """Builds the complete V2 event card with TextDisplay content and buttons."""
        self.clear_items()
        
        # Load event data from DB if available
        db_event = await database.get_active_event(self.event_id)
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

        event_conf = self.event_conf or {}
        guild_id = event_conf.get("guild_id")

        # --- RSVP DATA ---
        rsvps = await database.get_rsvps(self.event_id)
        status_map = {opt["id"]: [] for opt in self.active_set["options"]}
        total_positive_count = 0
        positive_statuses = [o["id"] for o in self.active_set["options"] if o.get("positive")]
        if not positive_statuses and "positive_count" in self.active_set:
            cnt = self.active_set["positive_count"]
            positive_statuses = [o["id"] for o in self.active_set["options"][:cnt]]

        for user_id, status in rsvps:
            if status not in status_map:
                status_map[status] = []
            status_map[status].append(f"<@{user_id}>")
            if status in positive_statuses:
                total_positive_count += 1

        # Role limits from extra_data
        extra_data = event_conf.get("extra_data")
        if not extra_data and db_event:
            extra_data = db_event.get("extra_data")
        role_limits = {}
        if extra_data:
            try:
                if isinstance(extra_data, str):
                    role_limits = json.loads(extra_data).get("role_limits", {})
                else:
                    role_limits = extra_data.get("role_limits", {})
            except: pass

        # === BUILD CONTAINER ITEMS ===
        container_items = []

        # --- TITLE ---
        max_acc = event_conf.get("max_accepted", 0)
        is_full = (max_acc > 0 and total_positive_count >= max_acc)
        desc = event_conf.get("description", "")
        if is_full:
            full_label = t('EMBED_FULL', guild_id=guild_id) or 'ESEMÉNY BETELT'
            desc = f"### ⚠️ {full_label}\n{desc}"

        status_cfg = event_conf.get("status", "active")
        title_prefix = ""
        if status_cfg == "cancelled":
            title_prefix = f"**[{t('TAG_CANCELLED', guild_id=guild_id) or 'TÖRÖLVE'}]** "
        elif status_cfg == "postponed":
            title_prefix = f"**[{t('TAG_POSTPONED', guild_id=guild_id) or 'ELHALASZTVA'}]** "
        elif status_cfg == "deleted":
            title_prefix = f"**[{t('TAG_DELETED', guild_id=guild_id) or 'TÖRÖLVE'}]** "

        title_str = f"## {title_prefix}{event_conf.get('title', t('LBL_EVENT', guild_id=guild_id))}"
        container_items.append(discord.ui.TextDisplay(title_str))

        if desc:
            container_items.append(discord.ui.TextDisplay(desc))

        # --- TIME ---
        start_ts = event_conf.get('start_time') or (db_event['start_time'] if db_event else time.time())
        time_str = f"**{t('EMBED_START_TIME', guild_id=guild_id)}:** <t:{int(start_ts)}:F>"
        
        end_ts = event_conf.get('end_time') or (db_event.get('end_time') if db_event else None)
        if end_ts:
            end_label = t('EMBED_END_TIME', guild_id=guild_id)
            if end_label == 'EMBED_END_TIME': end_label = 'Befejezés ideje'
            time_str += f"\n**{end_label}:** <t:{int(end_ts)}:F>"

        recurrence = event_conf.get('recurrence_type', 'none')
        if recurrence != 'none':
            time_str += f"\n**{t('EMBED_RECURRENCE', guild_id=guild_id)}:** {recurrence.capitalize()}"
        container_items.append(discord.ui.TextDisplay(time_str))

        # --- ROLE LISTS ---
        container_items.append(discord.ui.Separator())
        waiting_list = []
        role_sections = []
        for opt in self.active_set["options"]:
            role_id = opt["id"]
            users = status_map.get(role_id, [])
            limit = role_limits.get(role_id, opt.get("max_slots"))
            label_text = opt.get("list_label") or (t(opt["label_key"], guild_id=guild_id) if "label_key" in opt else opt.get("label", ""))

            count_text = str(len(users))
            is_pos = (role_id in positive_statuses)
            if is_pos and max_acc > 0:
                count_text = f"{len(users)}/{max_acc}"
            if limit:
                count_text = f"{len(users)}/{limit}"

            if not opt.get("show_in_list", True):
                continue

            name_parts = []
            if opt.get("emoji"):
                name_parts.append(opt["emoji"])
            if label_text:
                name_parts.append(label_text)

            users_str = ", ".join(users) if users else t("EMBED_NONE", guild_id=guild_id)
            role_sections.append(f"**{' '.join(name_parts)} ({count_text}):** {users_str}")

            wait_tag = f"wait_{role_id}"
            if wait_tag in status_map:
                emoji = opt.get("emoji", "")
                for u in status_map[wait_tag]:
                    if limit and emoji:
                        waiting_list.append(f"{u} {emoji}")
                    else:
                        waiting_list.append(u)

        if role_sections:
            container_items.append(discord.ui.TextDisplay("\n\n".join(role_sections) + "\n\n"))

        if waiting_list:
            container_items.append(discord.ui.Separator())
            wait_header = t('EMBED_WAITLIST', guild_id=guild_id) or 'Waiting List'
            wait_str = f"**⏳ {wait_header} ({len(waiting_list)}):** " + ", ".join(waiting_list)
            container_items.append(discord.ui.TextDisplay(wait_str))

        # --- IMAGE ---
        image_url = None
        if db_event and db_event.get("image_urls"):
            image_url = str(db_event["image_urls"]).split(",")[0].strip()
        elif event_conf.get("image_urls"):
            val = event_conf["image_urls"]
            if isinstance(val, list):
                image_url = random.choice(val)
            elif isinstance(val, str) and "," in val:
                image_url = random.choice([u.strip() for u in val.split(",")])
            else:
                image_url = str(val)

        if image_url:
            try:
                from discord.ui.media_gallery import MediaGalleryItem
                container_items.append(discord.ui.MediaGallery(MediaGalleryItem(media=image_url)))
            except Exception:
                container_items.append(discord.ui.Thumbnail(media=image_url))

        # --- FOOTER ---
        creator_text = "System"
        cid = event_conf.get("creator_id")
        if cid and str(cid).isdigit():
            user = self.bot.get_user(int(cid))
            if not user:
                try:
                    user = await self.bot.fetch_user(int(cid))
                except: pass
            if user:
                creator_text = f"@{user.display_name}"
        elif cid:
            creator_text = str(cid)
        footer_text = t("EMBED_FOOTER", guild_id=guild_id, event_id=self.event_id, creator_id=creator_text)

        # Calendar Links
        cal_title = event_conf.get("title") or (db_event.get("title") if db_event else "Event")
        cal_desc = event_conf.get("description") or (db_event.get("description") if db_event else "")
        cal_start_ts = event_conf.get('start_time') or (db_event['start_time'] if db_event else time.time())
        cal_end_ts = event_conf.get('end_time') or (db_event.get('end_time') if db_event else None)

        from utils.calendar_utils import get_google_calendar_url, get_outlook_calendar_url, get_yahoo_calendar_url
        google_url = get_google_calendar_url(cal_title, cal_desc, cal_start_ts, cal_end_ts)
        outlook_url = get_outlook_calendar_url(cal_title, cal_desc, cal_start_ts, cal_end_ts)
        yahoo_url = get_yahoo_calendar_url(cal_title, cal_desc, cal_start_ts, cal_end_ts)

        cal_links = f"[Gmail]({google_url}) │ [Yahoo]({yahoo_url}) │ [Outlook]({outlook_url})"

        container_items.append(discord.ui.TextDisplay(f"-# {footer_text} • {cal_links}"))

        # Build container
        accent_color = int(str(event_conf.get("color") or "0x3498db").replace("0x", ""), 16)
        container = discord.ui.Container(*container_items, accent_color=accent_color)
        self.add_item(container)

        # === BUTTONS (Outside Container) ===
        per_row = self.active_set.get("buttons_per_row", 5)
        options = self.active_set.get("options", [])
        rows = []
        current_row_items = []
        added_count = 0

        for opt in options:
            if added_count >= 40:
                break
            role_id = opt.get("id")
            if not role_id:
                continue

            if role_id in role_limits:
                opt["max_slots"] = role_limits[role_id]

            label = opt.get("label") if "label" in opt else ""
            if role_id in ["accepted", "declined", "tentative"]:
                label_key = f"BTN_{role_id.upper()}"
                localized_label = t(label_key, guild_id=guild_id)
                if localized_label != label_key:
                    label = localized_label

            btn_style = opt.get("button_style", "both")
            btn_emoji = opt.get("emoji") if btn_style in ["both", "emoji"] else None
            btn_label = label if btn_style in ["both", "label"] else None

            color_map = {
                "success": discord.ButtonStyle.green,
                "danger": discord.ButtonStyle.red,
                "primary": discord.ButtonStyle.primary,
                "secondary": discord.ButtonStyle.secondary
            }
            btn_color = color_map.get(opt.get("button_color"), discord.ButtonStyle.secondary)

            btn = discord.ui.Button(
                style=btn_color,
                emoji=btn_emoji or None,
                label=btn_label or None,
                custom_id=f"{role_id}_{self.event_id}"
            )

            def create_callback(status_id):
                async def callback(interaction: discord.Interaction):
                    await self.handle_rsvp(interaction, status_id)
                return callback

            btn.callback = create_callback(role_id)
            current_row_items.append(btn)
            added_count += 1

            if len(current_row_items) >= per_row:
                rows.append(discord.ui.ActionRow(*current_row_items))
                current_row_items = []

        if current_row_items:
            rows.append(discord.ui.ActionRow(*current_row_items))

        # Management buttons in a separate row
        if self.active_set.get("show_mgmt", True) and added_count < 40:
            mgmt_items = []

            edit_btn = discord.ui.Button(label=t("BTN_EDIT", guild_id=guild_id), style=discord.ButtonStyle.gray, custom_id=f"edit_{self.event_id}")
            edit_btn.callback = self.edit_callback
            mgmt_items.append(edit_btn)

            delete_btn = discord.ui.Button(label=t("BTN_DELETE", guild_id=guild_id), style=discord.ButtonStyle.danger, custom_id=f"delete_{self.event_id}")
            delete_btn.callback = self.delete_callback
            mgmt_items.append(delete_btn)

            rows.append(discord.ui.ActionRow(*mgmt_items))

        for r in rows:
            self.add_item(r)

        self.update_button_states(rsvps, event_conf)

    def update_button_states(self, rsvps_list, event_conf):
        """Disables buttons if limits are reached OR if status is inactive."""
        status = event_conf.get("status", "active")
        
        # Helper to find all buttons in V2 layout (within Container -> ActionRows)
        all_buttons = []
        for child in self.children:
            if isinstance(child, discord.ui.Container):
                for row in child.children:
                    if isinstance(row, discord.ui.ActionRow):
                        for item in row.children:
                            if isinstance(item, discord.ui.Button):
                                all_buttons.append(item)
                    elif isinstance(row, discord.ui.Button):
                        all_buttons.append(row)
            elif isinstance(child, discord.ui.Button):
                all_buttons.append(child)

        if status in ["cancelled", "postponed", "deleted"]:
            for btn in all_buttons:
                if not btn.custom_id.startswith(("edit_", "delete_", "calendar_")):
                    btn.disabled = True
            return

        use_waiting = event_conf.get("use_waiting_list", True)
        if use_waiting:
            for btn in all_buttons:
                if btn.custom_id and "_" in btn.custom_id and not btn.custom_id.startswith(("edit_", "delete_", "calendar_")):
                    btn.disabled = False
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

        for btn in all_buttons:
            if not btn.custom_id: continue
            if btn.custom_id.startswith(("edit_", "delete_", "calendar_")): continue

            parts = btn.custom_id.split("_")
            if len(parts) < 2: continue
            role_id = "_".join(parts[:-1])

            btn.disabled = False

            if role_id in positive_statuses and max_acc > 0:
                if total_pos >= max_acc: btn.disabled = True

            role_limit = role_limits.get(role_id)
            if role_limit is None:
                opt = next((o for o in self.active_set.get("options", []) if o["id"] == role_id), None)
                if opt: role_limit = opt.get("max_slots")

            if role_limit and role_limit > 0:
                curr_role_count = status_counts.get(role_id, 0)
                if curr_role_count >= role_limit: btn.disabled = True

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
        local_tz = tz.gettz(db_event.get("timezone", DEFAULT_TIMEZONE))
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

    async def delete_callback(self, interaction: discord.Interaction):
        if not await is_admin(interaction):
            await interaction.response.send_message(t("ERR_NO_PERM", guild_id=interaction.guild_id), ephemeral=True)
            return
        await interaction.response.defer()
        await database.delete_active_event(self.event_id)
        # Rebuild view with deleted state
        if not self.event_conf:
            self.event_conf = {}
        self.event_conf["status"] = "deleted"
        await self.prepare()
        # Disable all buttons
        for child in self.children:
            if isinstance(child, discord.ui.Container):
                for row in child.children:
                    if isinstance(row, discord.ui.ActionRow):
                        for item in row.children:
                            if isinstance(item, discord.ui.Button):
                                item.disabled = True
        await interaction.message.edit(view=self)
        log.info(f"Event {self.event_id} deleted by {interaction.user}")

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
            if self.event_conf.get("use_waiting_list", True): 
                target_status = f"wait_{status}"
                # Send waitlist hint
                try:
                    hint = t("MSG_WAITLIST_HINT", guild_id=interaction.guild_id, user_id=interaction.user.id, role=(opt.get('label') or status))
                    await interaction.user.send(hint)
                except: pass
            else: return await interaction.response.send_message(t("ERR_POS_FULL", guild_id=interaction.guild_id, name=(opt.get('label') or opt['id'])), ephemeral=True)

        positive_statuses = self.active_set.get("positive", [])
        if not positive_statuses and "positive_count" in self.active_set:
            cnt = self.active_set["positive_count"]; positive_statuses = [o["id"] for o in self.active_set["options"][:cnt]]

        if target_status in positive_statuses:
            max_acc = self.event_conf.get('max_accepted', 0)
            if max_acc > 0 and sum(1 for _, s in rsvps_list if s in positive_statuses) >= max_acc and old_status not in positive_statuses:
                if not target_status.startswith("wait_"): 
                    target_status = f"wait_{status}"
                    # Send waitlist hint (event-level limit)
                    try:
                        hint = t("MSG_WAITLIST_HINT", guild_id=interaction.guild_id, user_id=interaction.user.id, role=(opt.get('label') or status))
                        await interaction.user.send(hint)
                    except: pass

        await interaction.response.defer()
        await database.update_rsvp(self.event_id, interaction.user.id, target_status)

        # Temp Role Management
        temp_role_id = db_event.get("temp_role_id")
        if temp_role_id and isinstance(interaction.user, discord.Member):
            if not interaction.guild.me.guild_permissions.manage_roles:
                log.warning(f"[RSVP] Missing 'Manage Roles' permission to handle temp role {temp_role_id} in guild {interaction.guild_id}")
            else:
                role = interaction.guild.get_role(int(temp_role_id))
                if role:
                    try:
                        if target_status in positive_statuses:
                            if role not in interaction.user.roles:
                                await interaction.user.add_roles(role, reason=f"RSVP positive: {self.event_id}")
                                log.info(f"[RSVP] Added role {temp_role_id} to {interaction.user.id} for event {self.event_id}")
                        else:
                            if role in interaction.user.roles:
                                await interaction.user.remove_roles(role, reason=f"RSVP negative/left: {self.event_id}")
                                log.info(f"[RSVP] Removed role {temp_role_id} from {interaction.user.id} for event {self.event_id}")
                    except Exception as e:
                        log.error(f"[RSVP] Role management error: {e}")

        if old_status and old_status != target_status:
            old_role_limit = role_limits.get(old_status, next((o.get("max_slots") for o in self.active_set["options"] if o["id"] == old_status), None))
            if old_role_limit:
                max_acc, current_acc = self.event_conf.get('max_accepted', 0), sum(1 for _, s in rsvps_list if s in positive_statuses)
                if max_acc == 0 or current_acc < max_acc:
                    promoted_uid = await database.promote_next_waiting(self.event_id, f"wait_{old_status}", old_status)
                    if promoted_uid: await self.notify_promotion(interaction, promoted_uid, next(o for o in self.active_set["options"] if o["id"] == old_status))

        await self.prepare()
        await interaction.message.edit(view=self)
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
        
        # Add to temp role if promoted
        db_event = await database.get_active_event(self.event_id, interaction.guild_id)
        if db_event and db_event.get("temp_role_id"):
            guild = interaction.guild
            if not guild.me.guild_permissions.manage_roles:
                log.warning(f"[Promotion] Missing 'Manage Roles' permission to handle temp role in guild {guild.id}")
            else:
                member = guild.get_member(user_id) or await guild.fetch_member(user_id)
                if member:
                    role = guild.get_role(int(db_event["temp_role_id"]))
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason=f"Promoted to active: {self.event_id}")
                            log.info(f"[Promotion] Added role {db_event['temp_role_id']} to {user_id} for event {self.event_id}")
                        except Exception as e:
                            log.error(f"[Promotion] Role management error: {e}")

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
                        msg = await chan.fetch_message(ev["message_id"]); view = DynamicEventView(self.bot, eid, ev); await view.prepare(); await msg.edit(view=view)
                    except: pass
        if self.notify_type == "none": return
        participants = set()
        for eid in event_ids:
            rsvps = await database.get_rsvps(eid)
            for uid, s in rsvps:
                if not s.startswith("wait_"): participants.add(uid)
        if not participants: return
        guild_id = interaction.guild_id
        title = self.db_event.get('title') or 'Event'
        
        if self.new_status == "cancelled":
            msg_body = t("MSG_EVENT_CANCELLED", guild_id=guild_id, title=title)
        elif self.new_status == "postponed":
            msg_body = t("MSG_EVENT_POSTPONED", guild_id=guild_id, title=title)
        else:
            status_text = self.new_status.upper()
            msg_body = t("MSG_EVENT_NOTIF_PREFIX", guild_id=guild_id, status=status_text, title=title)
        notification_msg = f"📢 {msg_body}"
        if self.notify_type in ["dm", "both"]:
            for uid in participants:
                try:
                    user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                    if user: await user.send(notification_msg)
                except: pass
        if self.notify_type in ["chat", "both"]:
            pings = ' '.join([f'<@{uid}>' for uid in participants])
            await interaction.channel.send(f"{notification_msg}\n{pings}")

async def setup(bot):
    await load_custom_sets()
