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
        """Builds the view using Components V2 Layouts."""
        self.clear_items()
        
        # Load db_event or use self.event_conf entirely
        import time, json, random
        db_event = await database.get_active_event(self.event_id)
        if db_event and not self.event_conf:
            self.event_conf = get_event_conf(db_event["config_name"])
            if not self.event_conf:
                self.event_conf = dict(db_event)
                ex = db_event.get("extra_data")
                if ex:
                    try:
                        d = json.loads(ex) if isinstance(ex, str) else ex
                        if isinstance(d, dict): self.event_conf.update(d)
                    except: pass
        
        event_conf = self.event_conf or {}
        guild_id = event_conf.get("guild_id")
        
        # Calculate RSVPs for lists and button states
        rsvps = await database.get_rsvps(self.event_id)
        status_map = {}
        total_positive_count = 0
        positive_statuses = [o["id"] for o in self.active_set["options"] if o.get("positive")]
        if not positive_statuses and "positive_count" in self.active_set:
            cnt = self.active_set["positive_count"]
            positive_statuses = [o["id"] for o in self.active_set["options"][:cnt]]

        for uid, s in rsvps:
            if s not in status_map: status_map[s] = []
            user = self.bot.get_user(uid)
            display_str = user.mention if user else f"<@{uid}>"
            status_map[s].append(display_str)
            if s in positive_statuses: total_positive_count += 1
            
        extra_data = db_event.get("extra_data") if db_event else None
        role_limits = {}
        if extra_data:
            try:
                if isinstance(extra_data, str):
                    role_limits = json.loads(extra_data).get("role_limits", {})
                else:
                    role_limits = extra_data.get("role_limits", {})
            except: pass

        import discord
        container_items = []
        
        max_acc = event_conf.get("max_accepted", 0)
        is_full = (max_acc > 0 and total_positive_count >= max_acc)
        desc = event_conf.get("description", "")
        if is_full: desc = f"### ⚠️ {t('EMBED_FULL', guild_id=guild_id) or 'ESEMÉNY BETELT'}\\n{desc}"

        status_cfg = event_conf.get("status", "active")
        title_prefix = ""
        if status_cfg == "cancelled": title_prefix = f"**[{t('TAG_CANCELLED', guild_id=guild_id) or 'TÖRÖLVE'}]** "
        elif status_cfg == "postponed": title_prefix = f"**[{t('TAG_POSTPONED', guild_id=guild_id) or 'ELHALASZTVA'}]** "

        title_str = f"## {title_prefix}{event_conf.get('title', t('LBL_EVENT', guild_id=guild_id))}"
        container_items.append(discord.ui.TextDisplay(title_str))
        
        if desc: container_items.append(discord.ui.TextDisplay(desc))
        
        start_ts = db_event['start_time'] if db_event else time.time()
        time_str = f"**{t('EMBED_START_TIME', guild_id=guild_id)}:** <t:{int(start_ts)}:F>"
        recurrence = event_conf.get('recurrence_type', 'none')
        if recurrence != 'none': time_str += f"\n**{t('EMBED_RECURRENCE', guild_id=guild_id)}:** {recurrence.capitalize()}"
        container_items.append(discord.ui.TextDisplay(time_str))
        
        image_url = None
        if db_event and db_event.get("image_urls"): image_url = str(db_event["image_urls"]).split(",")[0].strip()
        elif event_conf.get("image_urls"):
            val = event_conf["image_urls"]
            if isinstance(val, list): image_url = random.choice(val)
            elif isinstance(val, str) and "," in val: image_url = random.choice([u.strip() for u in val.split(",")])
            else: image_url = str(val)
        
        if image_url:
            from discord.ui.media_gallery import MediaGalleryItem
            container_items.append(discord.ui.MediaGallery(MediaGalleryItem(media=image_url)))

        roles_text = ""
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
            
            if not opt.get("show_in_list", True): continue

            name_parts = []
            if opt.get("emoji"): name_parts.append(opt["emoji"])
            if label_text: name_parts.append(label_text)
            
            users_list_str = "\n".join([f"- {u}" for u in users]) if users else f"- *{t('EMBED_NONE', guild_id=guild_id)}*"
            roles_text += f"\n**{' '.join(name_parts)} ({count_text})**\n{users_list_str}\n"

            wait_tag = f"wait_{role_id}"
            if wait_tag in status_map:
                emoji = opt.get("emoji", "⏳")
                for u in status_map[wait_tag]: waiting_list.append(f"{emoji} {u}")

        if roles_text:
            container_items.append(discord.ui.Separator())
            container_items.append(discord.ui.TextDisplay(roles_text.strip()))

        if waiting_list:
            container_items.append(discord.ui.Separator())
            wait_str = f"**⏳ {t('EMBED_WAITLIST', guild_id=guild_id) or 'Waiting List'} ({len(waiting_list)})**\n" + "\n".join([f"- {u}" for u in waiting_list])
            container_items.append(discord.ui.TextDisplay(wait_str))

        container_items.append(discord.ui.Separator())
        creator_text = "System"
        cid = event_conf.get("creator_id")
        if cid and str(cid).isdigit():
            user = self.bot.get_user(int(cid)) or await self.bot.fetch_user(int(cid))
            if user: creator_text = f"@{user.display_name}"
        elif cid: creator_text = str(cid)
        container_items.append(discord.ui.TextDisplay(f"*{t('EMBED_FOOTER', guild_id=guild_id, event_id=self.event_id, creator_id=creator_text)}*"))

        per_row = self.active_set.get("buttons_per_row", 5)
        options = self.active_set.get("options", [])
        
        rows = []
        current_row_items = []
        added_count = 0

        for opt in options:
            if added_count >= 40: break
            role_id = opt.get("id")
            if not role_id: continue
            
            if role_id in role_limits: opt["max_slots"] = role_limits[role_id]
            label = opt.get("label") if "label" in opt else ""
            if role_id in ["accepted", "declined", "tentative"]:
                label_key = f"BTN_{role_id.upper()}"
                localized_label = t(label_key, guild_id=guild_id)
                if localized_label != label_key: label = localized_label

            btn_style = opt.get("button_style", "both")
            btn_emoji = opt.get("emoji") if btn_style in ["both", "emoji"] else None
            btn_label = label if btn_style in ["both", "label"] else None
            color_map = {"success": discord.ButtonStyle.green, "danger": discord.ButtonStyle.red, "primary": discord.ButtonStyle.primary, "secondary": discord.ButtonStyle.secondary}
            btn_color = color_map.get(opt.get("button_color"), discord.ButtonStyle.secondary)

            btn = discord.ui.Button(style=btn_color, emoji=btn_emoji or None, label=btn_label or None, custom_id=f"{role_id}_{self.event_id}")
            
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

        if current_row_items: rows.append(discord.ui.ActionRow(*current_row_items))

        if self.active_set.get("show_mgmt", True) and added_count < 40:
            mgmt_items = []
            calendar_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="📅", custom_id=f"calendar_{self.event_id}")
            calendar_btn.callback = self.calendar_callback
            mgmt_items.append(calendar_btn)
            edit_btn = discord.ui.Button(label=t("BTN_EDIT", guild_id=guild_id), style=discord.ButtonStyle.gray, custom_id=f"edit_{self.event_id}")
            edit_btn.callback = self.edit_callback
            mgmt_items.append(edit_btn)
            delete_btn = discord.ui.Button(label=t("BTN_DELETE", guild_id=guild_id), style=discord.ButtonStyle.danger, custom_id=f"delete_{self.event_id}")
            delete_btn.callback = self.delete_callback
            mgmt_items.append(delete_btn)
            rows.append(discord.ui.ActionRow(*mgmt_items))

        for r in rows: container_items.append(r)

        accent_color = int(str(event_conf.get("color") or "0x3498db").replace("0x", ""), 16)
        container = discord.ui.Container(*container_items, accent_color=accent_color)
        self.add_item(container)
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

        if status in ["cancelled", "postponed"]:
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

