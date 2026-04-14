import discord
from utils.emojis import WARNING, PING, SYNC
from utils.emoji_utils import to_emoji, resolve_placeholders
from discord.ext import commands
import database
from utils.i18n import t
from database import DEFAULT_TIMEZONE
import json
from utils.logger import log
import time
import random

# We try to load the config to see who is the boss (admin)
from utils.config import config
ADMIN_ROLE_ID = config.get("admin_role_id")

from utils.auth import is_admin

def get_event_conf(name):
    # This helper gets the settings for a specific event type from config.json
    try:
        events = config.get("events_config", [])
        defaults = config.get("globals", {}).get("event_defaults", {})
        
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


async def send_lobby_fill_notifications(bot, db_event, active_set: dict, guild_id_int: int):
    from utils.lobby_utils import positive_status_ids

    et = (db_event.get("reminder_type") or "").strip().lower()
    if et in ("none", ""):
        if not db_event.get("lobby_remind_on_fill", True):
            return
        et = (
            await database.get_guild_setting(guild_id_int, "reminder_type", default="none") or "none"
        ).lower()
    if et in ("none", ""):
        return
    rem_type = et

    pos_ids = positive_status_ids(active_set)
    rsvps = await database.get_rsvps(db_event["event_id"])
    participants = []
    for r in rsvps:
        st = r["status"]
        if st in pos_ids and not str(st).startswith("wait_"):
            participants.append(int(r["user_id"]))
    if not participants:
        return

    title = db_event.get("title") or "Event"
    rem_text = t("MSG_LOBBY_FILL_DESC", guild_id=guild_id_int, title=title)
    rem_text = resolve_placeholders(rem_text)
    start_ts = int(db_event.get("start_time") or time.time())
    send_ping = rem_type in ("ping", "both")
    send_dm = rem_type in ("dm", "both")

    temp_role_id = db_event.get("temp_role_id")
    if temp_role_id:
        mention_str = f"<@&{temp_role_id}>"
    else:
        mention_str = ", ".join(f"<@{uid}>" for uid in participants)

    if send_ping:
        channel = bot.get_channel(int(db_event["channel_id"]))
        if channel:
            embed = discord.Embed(
                title=t("LBL_LOBBY_FILL_TITLE", guild_id=guild_id_int),
                description=rem_text,
                color=discord.Color.green(),
            )
            embed.add_field(
                name=t("LBL_STARTS", guild_id=guild_id_int),
                value=f"<t:{start_ts}:F>",
            )
            try:
                await channel.send(content=mention_str, embed=embed)
            except Exception as e:
                log.error("[Lobby fill] channel notify %s: %s", db_event["event_id"], e)

    if send_dm:
        for uid in participants:
            try:
                user = bot.get_user(uid) or await bot.fetch_user(uid)
                if not user:
                    continue
                embed = discord.Embed(
                    title=t("LBL_LOBBY_FILL_TITLE", guild_id=guild_id_int),
                    description=rem_text,
                    color=discord.Color.green(),
                )
                embed.add_field(
                    name=t("LBL_STARTS", guild_id=guild_id_int),
                    value=f"<t:{start_ts}:F>",
                )
                await user.send(embed=embed)
            except Exception as e:
                log.debug("[Lobby fill] DM %s: %s", uid, e)

import time

# Cooldown cache for RSVP button presses (only enforced when waiting list is active)
# Key: (event_id, user_id) -> timestamp of last RSVP change
_rsvp_cooldowns: dict[tuple, float] = {}
RSVP_COOLDOWN_SECONDS = 60

async def send_status_notification(bot, event_id, db_event, status_name, guild_id):
    """Sends a ping broadcast in the channel and DMs participants about status changes."""
    rsvps = await database.get_rsvps(event_id)
    participants = set()
    for uid, s in rsvps:
        participants.add(uid)

    channel_id = db_event.get("channel_id")
    if not channel_id: return

    channel = bot.get_channel(int(channel_id))
    if not channel:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except Exception:
            return

    ping_role = db_event.get("ping_role")
    ping_prefix = ""
    if ping_role and str(ping_role).isdigit() and int(ping_role) > 0:
        ping_prefix = f"{PING} <@&{ping_role}> "

    title = db_event.get("title", "Event")
    if status_name == "cancelled":
        msg_body = t("MSG_EVENT_CANCELLED", guild_id=guild_id, title=title)
    elif status_name == "postponed":
        msg_body = t("MSG_EVENT_POSTPONED", guild_id=guild_id, title=title)
    elif status_name == "deleted":
        msg_body = f"Az esemény ({title}) törölve lett."
    else:
        msg_body = f"Esemény: ({title}) státusza megváltozott: {status_name}"

    if msg_body:
        msg_body = resolve_placeholders(msg_body)
        content = f"{ping_prefix}{msg_body}"

    notify_type = await database.get_guild_setting(guild_id, "status_notification_type", default="none")
    notify_type = notify_type.lower()
    
    if notify_type in ["chat", "both"]:
        await channel.send(content=content)

    if notify_type in ["dm", "both"]:
        notification_msg = f"{PING} {msg_body}"
        for uid in participants:
            try:
                user = bot.get_user(uid) or await bot.fetch_user(uid)
                if user:
                    await user.send(notification_msg)
            except Exception:
                log.debug(f"Failed to DM {uid} for {status_name}")

async def process_lobby_transition(bot, event_id: str, active_set: dict, guild_id_int: int):
    from utils.lobby_utils import (
        count_positive_rsvps,
        effective_lobby_capacity,
        lobby_is_full,
        positive_status_ids,
        role_limits_from_extra,
    )

    db_event = await database.get_active_event(event_id)
    if not db_event or not db_event.get("lobby_mode"):
        return

    pos = positive_status_ids(active_set)
    rl = role_limits_from_extra(db_event.get("extra_data"))
    cap = effective_lobby_capacity(int(db_event.get("max_accepted") or 0), active_set, rl)
    if cap is None or cap <= 0:
        return

    rsvps = await database.get_rsvps(event_id)
    cnt = count_positive_rsvps(rsvps, pos)
    had_start = db_event.get("start_time") is not None
    full = lobby_is_full(cnt, cap)

    if full and not had_start:
        await database.set_lobby_start_time(event_id, time.time())
        db_event = await database.get_active_event(event_id)
        await send_lobby_fill_notifications(bot, db_event, active_set, guild_id_int)
    elif not full and had_start:
        await database.set_lobby_start_time(event_id, None)


class DynamicEventView(discord.ui.LayoutView):
    # This class creates the buttons people see under the event message
    def __init__(self, bot, event_id: str, event_conf: dict = None, is_preview: bool = False):
        super().__init__(timeout=None)
        self.bot = bot
        self.event_id = event_id
        self.event_conf = event_conf
        self.is_preview = is_preview
        
        # We check which icon set this event should use
        icon_set_key = "standard"
        if event_conf:
            icon_set_key = event_conf.get("icon_set", "standard")
        
        self.active_set = get_active_set(icon_set_key).copy()
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if getattr(self, "is_preview", False):
            # Csak egy előnézeti kártya, ezen nem lehet gombokat nyomni
            await interaction.response.send_message(t("MSG_SAVED_PREVIEW", guild_id=interaction.guild_id), ephemeral=True)
            return False
        return True
        
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
                    except Exception as e:
                        log.debug("prepare extra_data: %s", e)

        if db_event:
            merged = dict(self.event_conf or {})
            if db_event.get("guild_id"):
                merged["guild_id"] = db_event["guild_id"]
            merged["lobby_mode"] = bool(db_event.get("lobby_mode"))
            v = db_event.get("lobby_remind_on_fill")
            merged["lobby_remind_on_fill"] = True if v is None else bool(v)
            merged["lobby_expires_at"] = db_event.get("lobby_expires_at")
            merged["start_time"] = db_event.get("start_time")
            merged["end_time"] = db_event.get("end_time")
            merged["status"] = db_event.get("status") or merged.get("status") or "active"
            if db_event.get("max_accepted") is not None:
                merged["max_accepted"] = db_event["max_accepted"]
            self.event_conf = merged

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
            except Exception as e:
                log.debug("prepare role_limits: %s", e)

        # === BUILD CONTAINER ITEMS ===
        container_items = []

        # --- TITLE ---
        from utils.lobby_utils import effective_lobby_capacity, lobby_is_full

        max_acc = event_conf.get("max_accepted", 0)
        lobby_mode = bool(event_conf.get("lobby_mode"))
        lobby_cap = None
        if lobby_mode:
            lobby_cap = effective_lobby_capacity(int(max_acc or 0), self.active_set, role_limits)
        is_full = False
        if lobby_mode and lobby_cap:
            is_full = lobby_is_full(total_positive_count, lobby_cap)
        elif not lobby_mode:
            is_full = max_acc > 0 and total_positive_count >= max_acc
        desc = event_conf.get("description", "")
        if is_full and not (lobby_mode and event_conf.get("start_time")):
            full_label = t("EMBED_FULL", guild_id=guild_id) or "ESEMÉNY BETELT"
            desc = f"### {WARNING} {full_label}\n{desc}"

        status_cfg = event_conf.get("status", "active")
        if (
            lobby_mode
            and status_cfg == "active"
            and event_conf.get("start_time") is None
            and event_conf.get("lobby_expires_at") is not None
            and time.time() > float(event_conf["lobby_expires_at"])
        ):
            status_cfg = "lobby_expired"
        title_prefix = ""
        if status_cfg == "cancelled":
            title_prefix = f"[{t('TAG_CANCELLED', guild_id=guild_id) or 'TÖRÖLVE'}]"
        elif status_cfg == "postponed":
            title_prefix = f"[{t('TAG_POSTPONED', guild_id=guild_id) or 'ELHALASZTVA'}]"
        elif status_cfg == "deleted":
            title_prefix = f"[{t('TAG_DELETED', guild_id=guild_id) or 'TÖRÖLVE'}]"
        elif status_cfg == "rescheduled":
            title_prefix = f"[{t('TAG_RESCHEDULED', guild_id=guild_id) or 'ÁTRAKVA'}]"
        elif status_cfg == "lobby_expired":
            title_prefix = f"[{t('TAG_LOBBY_EXPIRED', guild_id=guild_id)}]"
        elif status_cfg == "closed":
            title_prefix = f"[{t('TAG_CLOSED', guild_id=guild_id) or 'VÉGE'}]"

        title_str = ""
        if title_prefix:
            title_str += f"### **{title_prefix}**\n"
            
        raw_title = event_conf.get('title', t('LBL_EVENT', guild_id=guild_id))
        title_str += f"## {raw_title}"
        container_items.append(discord.ui.TextDisplay(title_str))

        if desc:
            container_items.append(discord.ui.TextDisplay(desc))

        # --- TIME ---
        start_ts_db = event_conf.get("start_time")
        if lobby_mode:
            if start_ts_db is None and status_cfg == "active":
                cap_disp = int(lobby_cap) if lobby_cap else "?"
                time_str = t("EMBED_LOBBY_FILL", guild_id=guild_id, cap=cap_disp)
                exp = event_conf.get("lobby_expires_at")
                if exp:
                    time_str += "\n" + t(
                        "EMBED_LOBBY_EXPIRES_FROM_PUBLISH",
                        guild_id=guild_id,
                        ts=int(float(exp)),
                    )
            elif start_ts_db is not None:
                time_str = f"**{t('EMBED_START_TIME', guild_id=guild_id)}:** <t:{int(start_ts_db)}:F>\n*{t('EMBED_LOBBY_STARTED', guild_id=guild_id)}*"
                end_ts = event_conf.get("end_time") or (db_event.get("end_time") if db_event else None)
                if end_ts:
                    import datetime

                    s_date = datetime.datetime.fromtimestamp(float(start_ts_db)).date()
                    e_date = datetime.datetime.fromtimestamp(float(end_ts)).date()
                    if s_date == e_date:
                        time_str += f" - <t:{int(end_ts)}:t>"
                    else:
                        end_label = t("EMBED_END_TIME", guild_id=guild_id)
                        if end_label == "EMBED_END_TIME":
                            end_label = "End" if "Time" in t("EMBED_START_TIME", guild_id=guild_id) else "Vége"
                        time_str += f"\n**{end_label}:** <t:{int(end_ts)}:F>"
            else:
                time_str = t("EMBED_LOBBY_EXPIRED_BODY", guild_id=guild_id)
        else:
            start_ts = event_conf.get("start_time") or (
                db_event["start_time"] if db_event and db_event.get("start_time") else time.time()
            )
            time_str = f"**{t('EMBED_START_TIME', guild_id=guild_id)}:** <t:{int(start_ts)}:F>"
            end_ts = event_conf.get("end_time") or (db_event.get("end_time") if db_event else None)
            if end_ts:
                import datetime
                s_date = datetime.datetime.fromtimestamp(float(start_ts)).date()
                e_date = datetime.datetime.fromtimestamp(float(end_ts)).date()

                if s_date == e_date:
                    time_str += f" - <t:{int(end_ts)}:t>"
                else:
                    end_label = t("EMBED_END_TIME", guild_id=guild_id)
                    if end_label == "EMBED_END_TIME":
                        end_label = "End" if "Time" in t("EMBED_START_TIME", guild_id=guild_id) else "Vége"
                    time_str += f"\n**{end_label}:** <t:{int(end_ts)}:F>"

            recurrence = event_conf.get("recurrence_type", "none")
            if recurrence != "none":
                rec_text = t(f"SEL_REC_{recurrence.upper()}", guild_id=guild_id) or recurrence.capitalize()
                time_str += f"\n**{t('EMBED_RECURRENCE', guild_id=guild_id)}:** {rec_text}"
        container_items.append(discord.ui.TextDisplay(time_str))

        # --- ROLE LISTS ---
        container_items.append(discord.ui.Separator())
        waiting_list = []
        role_sections = []
        for opt in self.active_set["options"]:
            role_id = opt["id"]
            users = status_map.get(role_id, [])
            limit = role_limits.get(role_id, opt.get("max_slots"))
            if "list_label_key" in opt:
                label_text = t(opt["list_label_key"], guild_id=guild_id, use_template_lang=True)
            else:
                label_text = opt.get("list_label") or (t(opt["label_key"], guild_id=guild_id, use_template_lang=True) if "label_key" in opt else opt.get("label", ""))

            count_text = str(len(users))
            is_pos = (role_id in positive_statuses)
            if is_pos and max_acc > 0:
                count_text = f"{len(users)}/{max_acc}"
            if limit:
                count_text = f"{len(users)}/{limit}"

            name_parts = []
            if opt.get("emoji"):
                name_parts.append(resolve_placeholders(opt["emoji"]))
            if label_text:
                name_parts.append(label_text)

            if not opt.get("show_in_list", True):
                # Anonymous mode: only show the count
                role_sections.append(f"**{' '.join(name_parts)} ({count_text})**")
            else:
                users_str = ", ".join(users) if users else t("EMBED_NONE", guild_id=guild_id)
                role_sections.append(f"**{' '.join(name_parts)} ({count_text}):**\n{users_str}" if users else f"**{' '.join(name_parts)} ({count_text}):** {users_str}")


            wait_tag = f"wait_{role_id}"
            if wait_tag in status_map:
                emoji = resolve_placeholders(opt.get("emoji", ""))
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
            
            wait_str = ", ".join(waiting_list)
            
            container_items.append(discord.ui.TextDisplay(f"**⏳ {wait_header} ({len(waiting_list)}):**\n{wait_str}"))

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
                except Exception as e:
                    log.debug("fetch_user creator %s: %s", cid, e)
            if user:
                creator_text = f"@{user.display_name}"
        elif cid:
            creator_text = str(cid)
        footer_text = t("EMBED_FOOTER", guild_id=guild_id, event_id=self.event_id, creator_id=creator_text)

        # Calendar Links
        cal_title = event_conf.get("title") or (db_event.get("title") if db_event else "Event")
        cal_desc = event_conf.get("description") or (db_event.get("description") if db_event else "")
        cal_start_raw = event_conf.get("start_time") or (db_event.get("start_time") if db_event else None)
        cal_end_ts = event_conf.get("end_time") or (db_event.get("end_time") if db_event else None)

        if lobby_mode and cal_start_raw is None:
            cal_suffix = t("EMBED_LOBBY_NO_CAL_LINKS", guild_id=guild_id)
        else:
            cal_start_ts = float(cal_start_raw) if cal_start_raw is not None else time.time()
            from utils.calendar_utils import get_google_calendar_url, get_outlook_calendar_url, get_yahoo_calendar_url

            google_url = get_google_calendar_url(cal_title, cal_desc, cal_start_ts, cal_end_ts)
            outlook_url = get_outlook_calendar_url(cal_title, cal_desc, cal_start_ts, cal_end_ts)
            yahoo_url = get_yahoo_calendar_url(cal_title, cal_desc, cal_start_ts, cal_end_ts)
            cal_suffix = f"[Gmail]({google_url}) │ [Yahoo]({yahoo_url}) │ [Outlook]({outlook_url})"

        container_items.append(discord.ui.TextDisplay(f"-# {footer_text} • {cal_suffix}"))

        # Build container
        status_for_color = status_cfg
        if status_for_color == "cancelled":
            accent_hex = "0xe74c3c" # Red
        elif status_for_color == "postponed":
            accent_hex = "0xf1c40f" # Yellow
        elif status_for_color in ["deleted", "closed"]:
            accent_hex = "0x95a5a6" # Gray
        elif status_for_color == "rescheduled":
            accent_hex = "0x2ecc71" # Green
        elif status_for_color == "lobby_expired":
            accent_hex = "0x95a5a6"
        else:
            accent_hex = str(event_conf.get("color") or "0x3498db")
            
        accent_color = int(accent_hex.replace("0x", "").replace("#", ""), 16)
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
            if "label_key" in opt:
                label = t(opt["label_key"], guild_id=guild_id, use_template_lang=True)
            elif role_id in ["accepted", "declined", "tentative"]:
                label_key = f"BTN_{role_id.upper()}"
                localized_label = t(label_key, guild_id=guild_id, use_template_lang=True)
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
                emoji=to_emoji(btn_emoji) or None,
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

        status = event_conf.get("status", "active") if event_conf else db_event.get("status", "active") if db_event else "active"
        if status == "postponed":
            if current_row_items:
                rows.append(discord.ui.ActionRow(*current_row_items))
            if self.active_set.get("show_mgmt", True) and added_count < 40:
                mgmt_items = []
                resched_btn = discord.ui.Button(label=t("BTN_RESCHEDULE", guild_id=guild_id), style=discord.ButtonStyle.primary, custom_id=f"resched_{self.event_id}")
                resched_btn.callback = self.reschedule_callback
                mgmt_items.append(resched_btn)
                
                cancel_btn = discord.ui.Button(label=t("BTN_CANCEL_EVENT", guild_id=guild_id) or "Lemondás", style=discord.ButtonStyle.danger, custom_id=f"cancel_{self.event_id}")
                cancel_btn.callback = self.cancel_callback
                mgmt_items.append(cancel_btn)
                
                rows.append(discord.ui.ActionRow(*mgmt_items))
        else:
            if self.active_set.get("show_mgmt", True) and added_count < 40:
                mgmt_items = []

                postpone_btn = discord.ui.Button(label=t("BTN_POSTPONE_EVENT", guild_id=guild_id) or "Elhalasztás", style=discord.ButtonStyle.gray, custom_id=f"postpone_{self.event_id}")
                postpone_btn.callback = self.postpone_callback
                mgmt_items.append(postpone_btn)

                cancel_btn = discord.ui.Button(label=t("BTN_CANCEL_EVENT", guild_id=guild_id) or "Lemondás", style=discord.ButtonStyle.danger, custom_id=f"cancel_{self.event_id}")
                cancel_btn.callback = self.cancel_callback
                mgmt_items.append(cancel_btn)

                if len(current_row_items) + len(mgmt_items) <= 5:
                    current_row_items.extend(mgmt_items)
                    if current_row_items:
                        rows.append(discord.ui.ActionRow(*current_row_items))
                else:
                    if current_row_items:
                        rows.append(discord.ui.ActionRow(*current_row_items))
                    rows.append(discord.ui.ActionRow(*mgmt_items))
            else:
                if current_row_items:
                    rows.append(discord.ui.ActionRow(*current_row_items))

        for r in rows:
            self.add_item(r)

        self.update_button_states(rsvps, event_conf, ui_status=status_cfg)

    def update_button_states(self, rsvps_list, event_conf, ui_status=None):
        """Disables buttons if limits are reached OR if status is inactive."""
        status = ui_status or event_conf.get("status", "active")

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
            elif isinstance(child, discord.ui.ActionRow):
                for item in child.children:
                    if isinstance(item, discord.ui.Button):
                        all_buttons.append(item)
            elif isinstance(child, discord.ui.Button):
                all_buttons.append(child)

        if status in ["cancelled", "postponed", "deleted", "lobby_expired", "closed"]:
            for btn in all_buttons:
                allowed_prefix = ("edit_", "delete_", "calendar_", "resched_")
                if status == "postponed":
                    allowed_prefix += ("cancel_",)
                if not btn.custom_id.startswith(allowed_prefix):
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
            except Exception as e:
                log.debug("_apply_rsvp_limits role_limits: %s", e)

        from utils.lobby_utils import effective_lobby_capacity

        lobby_mode = bool(event_conf.get("lobby_mode"))
        lobby_cap = None
        if lobby_mode:
            lobby_cap = effective_lobby_capacity(int(max_acc or 0), self.active_set, role_limits)
        eff_event_cap = int(max_acc or 0)
        if lobby_mode and lobby_cap is not None:
            eff_event_cap = lobby_cap

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

            if role_id in positive_statuses and eff_event_cap > 0:
                if total_pos >= eff_event_cap:
                    btn.disabled = True

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

        await interaction.response.defer(ephemeral=True, thinking=True)
        db_event = await database.get_active_event(self.event_id)
        if not db_event:
            await interaction.followup.send(
                t("ERR_EV_NOT_FOUND", guild_id=guild_id), ephemeral=True
            )
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

        config_name = db_event.get("config_name")
        if db_event.get("lobby_mode"):
            wtype = "lobby"
        else:
            wtype = "single" if not config_name or config_name == "manual" else "series"
        from cogs.event_wizard import EventWizardView
        view = EventWizardView(self.bot, interaction.user.id, existing_data=db_event, is_edit=True, guild_id=interaction.guild_id, bulk_ids=bulk_ids, wizard_type=wtype)
        await view.refresh_message(interaction, send_followup=True)

    async def postpone_callback(self, interaction: discord.Interaction):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_NO_PERM", guild_id=interaction.guild_id), ephemeral=True)
        await interaction.response.send_modal(PostponeModal(self.bot, self.event_id, self, interaction.guild_id))

    async def reschedule_callback(self, interaction: discord.Interaction):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_NO_PERM", guild_id=interaction.guild_id), ephemeral=True)
        await interaction.response.send_modal(PostponeModal(self.bot, self.event_id, self, interaction.guild_id))

    async def cancel_callback(self, interaction: discord.Interaction):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_NO_PERM", guild_id=interaction.guild_id), ephemeral=True)
        await interaction.response.defer()
        await database.update_event_status(self.event_id, "cancelled")
        if not self.event_conf: self.event_conf = {}
        self.event_conf["status"] = "cancelled"
        await self.prepare()
        for child in self.children:
            if isinstance(child, discord.ui.Container):
                for row in child.children:
                    if isinstance(row, discord.ui.ActionRow):
                        for item in row.children:
                            if isinstance(item, discord.ui.Button): item.disabled = True
        await interaction.message.edit(view=self)
        db_ev = await database.get_active_event(self.event_id)
        if db_ev:
            await send_status_notification(self.bot, self.event_id, db_ev, "cancelled", interaction.guild_id)
        log.info(f"Event {self.event_id} cancelled by {interaction.user}")

    async def delete_callback(self, interaction: discord.Interaction):
        if not await is_admin(interaction):
            await interaction.response.send_message(t("ERR_NO_PERM", guild_id=interaction.guild_id), ephemeral=True)
            return
        await interaction.response.defer()
        
        # Role cleanup
        db_event = await database.get_active_event(self.event_id, interaction.guild_id)
        if db_event:
            temp_role_id = db_event.get("temp_role_id")
            if temp_role_id:
                guild = interaction.guild
                if guild and guild.me.guild_permissions.manage_roles:
                    try:
                        role = guild.get_role(int(temp_role_id))
                        if role:
                            await role.delete(reason=f"Event {self.event_id} deleted by UI button ({interaction.user})")
                            log.info(f"[UI-Delete] Deleted temp role {temp_role_id} for event {self.event_id}")
                    except Exception as e:
                        log.error(f"[UI-Delete] Failed to delete role {temp_role_id}: {e}")

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
        
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)
        log.info(f"Event {self.event_id} deleted by {interaction.user}")

    async def handle_rsvp(self, interaction: discord.Interaction, status: str):
        db_event = await database.get_active_event(self.event_id)
        if not db_event: return await interaction.response.send_message(t("ERR_EV_NOT_FOUND"), ephemeral=True)

        # Cooldown check: only enforce when waiting list is explicitly enabled
        has_waitlist = db_event.get("use_waiting_list", False)
        if has_waitlist:
            cd_key = (self.event_id, interaction.user.id)
            last_press = _rsvp_cooldowns.get(cd_key, 0)
            elapsed = time.time() - last_press
            if elapsed < RSVP_COOLDOWN_SECONDS:
                remaining = int(RSVP_COOLDOWN_SECONDS - elapsed)
                return await interaction.response.send_message(
                    t("ERR_RSVP_COOLDOWN", guild_id=interaction.guild_id, seconds=remaining),
                    ephemeral=True,
                )
            _rsvp_cooldowns[cd_key] = time.time()

        gid_chk = interaction.guild_id or db_event.get("guild_id")
        if db_event.get("status") == "lobby_expired":
            return await interaction.response.send_message(
                t("ERR_LOBBY_EXPIRED", guild_id=gid_chk), ephemeral=True
            )
        if (
            db_event.get("lobby_mode")
            and db_event.get("status") == "active"
            and db_event.get("start_time") is None
        ):
            exp = db_event.get("lobby_expires_at")
            if exp is not None and time.time() > float(exp):
                return await interaction.response.send_message(
                    t("ERR_LOBBY_EXPIRED", guild_id=gid_chk), ephemeral=True
                )
        if db_event["status"] not in ["active", "rescheduled"]:
            return await interaction.response.send_message(t("ERR_EV_INACTIVE"), ephemeral=True)

        raw_allowed = db_event.get("rsvp_allowed_role_ids")
        if raw_allowed:
            allowed_ids = [x.strip() for x in str(raw_allowed).split(",") if x.strip().isdigit()]
        else:
            allowed_ids = []
        if allowed_ids:
            if not isinstance(interaction.user, discord.Member):
                return await interaction.response.send_message(
                    t("ERR_RSVP_NEED_SERVER", guild_id=interaction.guild_id),
                    ephemeral=True,
                )
            user_role_ids = {str(r.id) for r in interaction.user.roles}
            if not any(rid in user_role_ids for rid in allowed_ids):
                return await interaction.response.send_message(
                    t("ERR_RSVP_ROLE_REQUIRED", guild_id=interaction.guild_id),
                    ephemeral=True,
                )

        if not self.event_conf:
            self.event_conf = get_event_conf(db_event["config_name"])
            if not self.event_conf:
                self.event_conf = dict(db_event)
                ex = db_event.get("extra_data")
                if ex:
                    try:
                        d = json.loads(ex) if isinstance(ex, str) else ex
                        if isinstance(d, dict): self.event_conf.update(d)
                    except Exception as e:
                        log.debug("handle_rsvp extra_data: %s", e)
        
        rsvps_list = await database.get_rsvps(self.event_id)
        old_status = next((s for uid, s in rsvps_list if uid == interaction.user.id), None)
        target_status, opt = status, next((o for o in self.active_set["options"] if o["id"] == status), None)
        
        ex = db_event.get("extra_data")
        role_limits = {}
        if ex:
            try:
                d = json.loads(ex) if isinstance(ex, str) else ex
                role_limits = d.get("role_limits", {})
            except Exception as e:
                log.debug("handle_rsvp role_limits: %s", e)
            
        role_limit = role_limits.get(status, opt.get("max_slots") if opt else None)
        if role_limit and sum(1 for _, s in rsvps_list if s == status) >= role_limit and old_status != status:
            if self.event_conf.get("use_waiting_list", True): 
                target_status = f"wait_{status}"
                # Send waitlist hint
                try:
                    hint = t("MSG_WAITLIST_HINT", guild_id=interaction.guild_id, user_id=interaction.user.id, role=(opt.get('label') or status))
                    hint = resolve_placeholders(hint)
                    await interaction.user.send(hint)
                except Exception as e:
                    log.debug("waitlist hint DM: %s", e)
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
                        hint = resolve_placeholders(hint)
                        await interaction.user.send(hint)
                    except Exception as e:
                        log.debug("waitlist hint DM (event cap): %s", e)

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

        # Check for promotions if a slot was vacated
        was_positive = old_status in positive_statuses
        still_positive = target_status in positive_statuses
        if was_positive and not still_positive:
            await self.try_promote_waiting(interaction, db_event, role_limits)
        elif was_positive and still_positive and old_status != target_status:
            # Swapped roles: Role A vacated, Role B filled.
            # Role A might have a waitlist that can now be filled.
            await self.try_promote_waiting(interaction, db_event, role_limits)

        gid_raw = interaction.guild_id or db_event.get("guild_id")
        if db_event.get("lobby_mode") and gid_raw:
            await process_lobby_transition(self.bot, self.event_id, self.active_set, int(str(gid_raw)))

        await self.prepare()
        
        # Robust UI refresh: try response.edit_message first for faster feedback
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(view=self)
            else:
                await interaction.message.edit(view=self)
        except Exception as e:
            log.debug(f"Refresh handling: {e}")
            # Fallback if both fail for some reason
            try: await interaction.edit_original_response(view=self)
            except: pass
        log.info(f"User {interaction.user} RSVP'd {status} for event {self.event_id}", guild_id=interaction.guild_id)

    async def notify_promotion(self, interaction, user_id, opt):
        notify_type = self.event_conf.get("notify_promotion", "none")
        if notify_type == "none": return
        
        db_event = await database.get_active_event(self.event_id, interaction.guild_id)
        if not db_event: return

        role_name = opt.get("label") or opt.get("list_label") or opt["id"]
        extra = self.event_conf.get("extra_data")
        custom_msg = None
        if extra:
            try:
                d = json.loads(extra) if isinstance(extra, str) else extra
                custom_msg = d.get("custom_promo_msg")
            except Exception as e:
                log.debug("notify_promotion extra_data: %s", e)
        
        if custom_msg: 
            msg = custom_msg.format(user_id=user_id, role=role_name, emoji=opt.get("emoji", ""), title=self.event_conf.get("title", ""))
        else: 
            msg = t("MSG_PROMOTED_DEFAULT", guild_id=interaction.guild_id, user_id=user_id, role=role_name, emoji=opt.get("emoji", ""))
        
        # Resolve placeholders (!IMPORTANT: fix for {TEMP_STD_YES} appearing in text)
        msg = resolve_placeholders(msg)
            
        # Add jump link for better UX
        jump_link = f"https://discord.com/channels/{interaction.guild_id}/{db_event['channel_id']}/{db_event['message_id']}"
        msg += f"\n🔗 {jump_link}"

        if notify_type in ["channel", "both"]: await interaction.channel.send(msg)
        if notify_type in ["dm", "both"]:
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                if user: await user.send(msg)
            except Exception as e:
                log.debug("notify_promotion DM %s: %s", user_id, e)
        
        # Add to temp role if promoted
        if db_event.get("temp_role_id"):
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

    async def try_promote_waiting(self, interaction, db_event, role_limits):
        """Attempts to promote the earliest waiting user across all eligible roles."""
        rsvps = await database.get_rsvps_with_time(self.event_id)
        
        positive_statuses = [o["id"] for o in self.active_set["options"] if o.get("positive")]
        if not positive_statuses and "positive_count" in self.active_set:
            cnt = self.active_set["positive_count"]
            positive_statuses = [o["id"] for o in self.active_set["options"][:cnt]]
            
        max_acc = self.event_conf.get('max_accepted', 0)
        
        # Sort by joined_at to ensure fairness (earliest first)
        waiting = sorted([r for r in rsvps if str(r["status"]).startswith("wait_")], key=lambda x: x["joined_at"])
        if not waiting:
            return

        for w in waiting:
            # Re-fetch counts as they might change if we promote multiple people
            current_acc = sum(1 for r in rsvps if r["status"] in positive_statuses)
            if max_acc > 0 and current_acc >= max_acc:
                break # Event level limit still reached, nobody else can be promoted
                
            wait_status = str(w["status"])
            target_status = wait_status.replace("wait_", "")
            
            # Check role-specific limit
            role_limit = role_limits.get(target_status)
            if role_limit is None:
                opt = next((o for o in self.active_set.get("options", []) if o["id"] == target_status), None)
                if opt: role_limit = opt.get("max_slots")
            
            if role_limit and sum(1 for r in rsvps if r["status"] == target_status) >= role_limit:
                continue # This role is still full, check next waiting person
                
            # PROMOTION FOUND!
            user_id = w["user_id"]
            await database.update_rsvp(self.event_id, user_id, target_status)
            
            opt = next((o for o in self.active_set["options"] if o["id"] == target_status), None)
            if opt:
                await self.notify_promotion(interaction, user_id, opt)
                
            log.info(f"[Promotion] User {user_id} promoted to {target_status} for event {self.event_id}")
            
            # Update local list state so we can potentially promote more in the same pass (if event had multiple slots open)
            for r in rsvps:
                if r["user_id"] == user_id:
                    r["status"] = target_status
                    break

class PostponeModal(discord.ui.Modal):
    def __init__(self, bot, event_id, parent_view, guild_id):
        super().__init__(title=t("MODAL_POSTPONE_TITLE", guild_id=guild_id), timeout=300)
        self.bot = bot
        self.event_id = event_id
        self.parent_view = parent_view
        
        self.start_input = discord.ui.TextInput(
            label=t("MODAL_POSTPONE_START", guild_id=guild_id),
            placeholder=t("PH_POSTPONE_START_EXAMPLE", guild_id=guild_id),
            required=False
        )
        self.add_item(self.start_input)
        
        self.end_input = discord.ui.TextInput(
            label=t("MODAL_POSTPONE_END", guild_id=guild_id),
            placeholder=t("PH_POSTPONE_END_EXAMPLE", guild_id=guild_id),
            required=False
        )
        self.add_item(self.end_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        import datetime
        from dateutil import parser, tz
        from database import DEFAULT_TIMEZONE
        import database
        
        local_tz = tz.gettz(DEFAULT_TIMEZONE)

        row = await database.get_active_event(self.event_id)
        if not row:
            return await interaction.followup.send(
                t("ERR_EV_NOT_FOUND", guild_id=interaction.guild_id), ephemeral=True
            )
        db_event = dict(row)

        # Ha a dátum mezeje teljesen üres, akkor csak simán "Halasztott" státuszt kap új kártya nélkül!
        if not self.start_input.value.strip():
            db_event["status"] = "postponed"
            await database.update_active_event(self.event_id, db_event)
            
            if not self.parent_view.event_conf: self.parent_view.event_conf = {}
            self.parent_view.event_conf["status"] = "postponed"
            await self.parent_view.prepare()
            for child in self.parent_view.children:
                if isinstance(child, discord.ui.Container):
                    for row in child.children:
                        if isinstance(row, discord.ui.ActionRow):
                            for item in row.children:
                                if isinstance(item, discord.ui.Button) and not item.custom_id.startswith("resched_"):
                                    item.disabled = True
                                    
            if interaction.message:
                await interaction.message.edit(view=self.parent_view)
            
            await send_status_notification(self.bot, self.event_id, db_event, "postponed", interaction.guild_id)
            
            return await interaction.followup.send(
                t("MSG_STATUS_UPDATED", guild_id=interaction.guild_id, status="postponed"),
                ephemeral=True,
            )

        try:
            start_dt = parser.parse(self.start_input.value).replace(tzinfo=local_tz)
            start_ts = int(start_dt.timestamp())
        except Exception:
            return await interaction.followup.send(
                t("ERR_INVALID_START", guild_id=interaction.guild_id),
                ephemeral=True,
            )
            
        end_ts = None
        if self.end_input.value:
            try:
                end_dt = parser.parse(self.end_input.value).replace(tzinfo=local_tz)
                end_ts = int(end_dt.timestamp())
            except Exception:
                return await interaction.followup.send(
                    t("ERR_INVALID_END", guild_id=interaction.guild_id),
                    ephemeral=True,
                )
        
        # db_event már betöltve a submit elején
        db_event["start_time"] = start_ts
        if end_ts:
            db_event["end_time"] = end_ts
        db_event["status"] = "rescheduled"
        await database.update_active_event(self.event_id, db_event)
        
        if not self.parent_view.event_conf: self.parent_view.event_conf = {}
        self.parent_view.event_conf["status"] = "rescheduled"
        self.parent_view.event_conf["start_time"] = start_ts
        if end_ts:
            self.parent_view.event_conf["end_time"] = end_ts
            
        await self.parent_view.prepare()
        for child in self.parent_view.children:
            if isinstance(child, discord.ui.Container):
                for row in child.children:
                    if isinstance(row, discord.ui.ActionRow):
                        for item in row.children:
                            if isinstance(item, discord.ui.Button): item.disabled = True
                            
        # If the origin of interaction was the card itself or thread
        if interaction.message:
            await interaction.message.edit(view=self.parent_view)

        # Spawn newly active card
        channel = await self.bot.fetch_channel(int(db_event["channel_id"]))
        from cogs.event_ui import DynamicEventView
        new_view = DynamicEventView(self.bot, self.event_id, db_event)
        await new_view.prepare()
        
        # Determine if we need to ping
        ping_role_id = db_event.get("ping_role")
        ping_prefix = ""
        if ping_role_id and str(ping_role_id).isdigit() and int(ping_role_id) > 0:
            ping_prefix = f"{PING} <@&{ping_role_id}> "
            
        new_msg = await channel.send(
            content=f"{ping_prefix}{SYNC} **{t('MSG_RESCHEDULED_BROADCAST', guild_id=interaction.guild_id)}**",
            view=new_view,
        )
        await database.set_event_message(self.event_id, new_msg.id)
        
        # DM participants dynamically
        rsvps = await database.get_rsvps(self.event_id)
        notification_msg = f"{PING} {t('MSG_RESCHEDULED_BROADCAST', guild_id=interaction.guild_id)}"
        
        notify_type = await database.get_guild_setting(interaction.guild_id, "status_notification_type", default="none")
        notify_type = notify_type.lower()
        if notify_type in ["dm", "both"]:
            for uid, s in rsvps:
                try:
                    user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                    if user: await user.send(notification_msg)
                except Exception:
                    pass
        
        await interaction.followup.send(
            t("MSG_RESCHEDULE_DONE", guild_id=interaction.guild_id),
            ephemeral=True,
        )

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
                    except Exception as e:
                        log.debug("refresh_and_notify edit %s: %s", eid, e)
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
        notification_msg = f"{PING} {msg_body}"
        if self.notify_type in ["dm", "both"]:
            for uid in participants:
                try:
                    user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                    if user: await user.send(notification_msg)
                except Exception as e:
                    log.debug("status notify DM %s: %s", uid, e)
        if self.notify_type in ["chat", "both"]:
            pings = ' '.join([f'<@{uid}>' for uid in participants])
            await interaction.channel.send(f"{notification_msg}\n{pings}")

async def setup(bot):
    await load_custom_sets()
