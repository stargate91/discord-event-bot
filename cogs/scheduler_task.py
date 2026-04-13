import discord
from utils.emojis import PING
from discord.ext import commands, tasks
import database
import time
import uuid
import datetime
import json
from cogs.event_ui import DynamicEventView, get_event_conf, get_active_set
from utils.emoji_utils import slugify
from utils.lobby_utils import positive_status_ids
from utils.i18n import t
from dateutil import parser as dtparser
from dateutil import tz as dttz
from dateutil.relativedelta import relativedelta
from utils.logger import log
from utils.offset_parse import parse_offset

from utils.calendar_utils import calc_next_start

class SchedulerTask(commands.Cog):
    # This part of the bot runs in the background and checks things every minute
    def __init__(self, bot):
        self.bot = bot
        self.check_events.start()

    def cog_unload(self):
        # Stop the background loop when the bot stops
        self.check_events.cancel()

    def _load_config(self):
        # Helper to load the config file
        from utils.jsonc import load_jsonc
        return load_jsonc('config.json')

    @tasks.loop(minutes=1.0)
    async def check_events(self):
        # This is the main loop that checks all events
        now = time.time()
        active_events = await database.get_all_active_events()

        for db_event in active_events:
            try:
                await self.handle_lobby_expiry(db_event, now)
            except Exception as e:
                log.error(
                    f"[Scheduler] Lobby expiry error for {db_event['event_id']}: {e}",
                    guild_id=db_event.get("guild_id"),
                )

            # 1. Reminders
            try:
                await self.handle_reminders(db_event, now)
            except Exception as e:
                log.error(f"[Scheduler] Error handling reminders for {db_event['event_id']}: {e}", guild_id=db_event.get("guild_id"))

            # 2. Role Cleanup (CRITICAL: runs for all events now)
            try:
                await self.check_role_cleanup(db_event, now)
            except Exception as e:
                log.error(f"[Scheduler] Error cleaning roles for {db_event['event_id']}: {e}", guild_id=db_event.get("guild_id"))

            # 3. Reposting (Only for recurring)
            try:
                await self.handle_reposting(db_event, now)
            except Exception as e:
                log.error(f"[Scheduler] Error handling reposting for {db_event['event_id']}: {e}", guild_id=db_event.get("guild_id"))

            # 4. Auto-completion (Lifecycle)
            try:
                await self.handle_event_completion(db_event, now)
            except Exception as e:
                log.error(f"[Scheduler] Error handling completion for {db_event['event_id']}: {e}", guild_id=db_event.get("guild_id"))

    async def handle_event_completion(self, db_event, now):
        """Marks one-time events as 'closed' after they have finished based on guild settings."""
        if db_event.get("status") != "active":
            return
            
        rec_type = db_event.get("recurrence_type", "once")
        if rec_type not in ("once", "none"):
            return
            
        start_ts = db_event.get("start_time")
        if not start_ts:
            return
            
        # Get dynamic archive duration for this guild
        gid = db_event.get("guild_id")
        archive_hours_str = await database.get_guild_setting(gid, "auto_archive_hours", default="12")
        try:
            archive_hours = float(archive_hours_str)
        except:
            archive_hours = 12.0
            
        archive_threshold = archive_hours * 3600
        
        end_ts = db_event.get("end_time")
        should_close = False
        
        if end_ts and now > end_ts:
            should_close = True
        elif now > (float(start_ts) + archive_threshold):
            should_close = True
            
        if should_close:
            await database.set_event_status(db_event["event_id"], "closed")
            log.info(f"[Lifecycle] Auto-archived expired event {db_event['event_id']} (Threshold: {archive_hours}h)", guild_id=gid)

    async def check_role_cleanup(self, db_event, now):
        """Deletes temporary Discord roles once the event has finished."""
        temp_role_id = db_event.get("temp_role_id")
        if not temp_role_id:
            return

        should_delete = False
        end_ts = db_event.get("end_time")
        start_ts = db_event.get("start_time")
        status = db_event.get("status") or "active"
        lobby_mode = bool(db_event.get("lobby_mode"))

        if status in ("closed", "cancelled", "deleted", "lobby_expired"):
            should_delete = True
        elif lobby_mode:
            if start_ts is None:
                should_delete = False
            elif end_ts and now > end_ts:
                should_delete = True
            elif not end_ts and start_ts is not None and now > (float(start_ts) + 14400):
                should_delete = True
        else:
            if start_ts is not None:
                if end_ts and now > end_ts:
                    should_delete = True
                elif not end_ts and now > (float(start_ts) + 14400):
                    should_delete = True

        if should_delete:
            guild = self.bot.get_guild(int(db_event["guild_id"]))
            if guild:
                if not guild.me.guild_permissions.manage_roles:
                    log.warning(f"[Scheduler] Missing 'Manage Roles' permission to delete role {temp_role_id} in guild {guild.id}")
                else:
                    try:
                        role = guild.get_role(int(temp_role_id))
                        if role:
                            await role.delete(reason=f"Event {db_event['event_id']} finished/closed.")
                            log.info(f"[Scheduler] Deleted temp role {temp_role_id} for event {db_event['event_id']}")
                    except Exception as e:
                        log.error(f"[Scheduler] Failed to delete role {temp_role_id}: {e}")
            
            # Clear from DB to prevent re-attempts even if permission was missing (admin must manually cleanup then)
            pool = await database.get_pool()
            await pool.execute("UPDATE active_events SET temp_role_id = 0 WHERE event_id = $1", db_event["event_id"])

    async def handle_lobby_expiry(self, db_event, now):
        if not db_event.get("lobby_mode"):
            return
        if (db_event.get("status") or "active") != "active":
            return
        if db_event.get("start_time"):
            return
        exp = db_event.get("lobby_expires_at")
        if exp is None or now <= float(exp):
            return
        await database.update_event_status(db_event["event_id"], "lobby_expired")
        await self._refresh_event_card(db_event)

    async def _refresh_event_card(self, db_event):
        eid = db_event["event_id"]
        mid = db_event.get("message_id")
        cid = db_event.get("channel_id")
        if not mid or not cid:
            return
        channel = self.bot.get_channel(int(cid))
        if not channel:
            try:
                channel = await self.bot.fetch_channel(int(cid))
            except Exception as e:
                log.debug("[Scheduler] fetch_channel %s: %s", cid, e)
                return
        try:
            msg = await channel.fetch_message(int(mid))
            view = DynamicEventView(self.bot, eid, None)
            await view.prepare()
            await msg.edit(view=view)
        except Exception as e:
            log.error(
                f"[Scheduler] Could not refresh event card {eid}: {e}",
                guild_id=db_event.get("guild_id"),
            )

    async def handle_reposting(self, db_event, now):
        """Checks if a recurring event needs to be reposted."""
        if db_event.get("lobby_mode"):
            return

        config_name = db_event["config_name"]
        event_conf = get_event_conf(config_name)
        if not event_conf:
            return

        if not event_conf.get("enabled", True):
            await database.set_event_status(db_event["event_id"], "disabled")
            return

        rec_type = event_conf.get("recurrence_type", "once")
        if rec_type == "once":
            return

        start_ts = db_event["start_time"]
        trigger = event_conf.get("repost_trigger", "after_start")
        offset = parse_offset(event_conf.get("repost_offset", "1h"))

        # We calculate EXACTLY when we should make the next message
        if trigger == "before_start":
            next_start = calc_next_start(start_ts, event_conf)
            if next_start is None:
                return
            repost_at = next_start - offset.total_seconds()
        elif trigger == "after_end":
            end_ts = db_event.get("end_time")
            if end_ts:
                repost_at = end_ts + offset.total_seconds()
            else:
                repost_at = start_ts + offset.total_seconds()
        elif trigger == "after_start":
            repost_at = start_ts + offset.total_seconds()
        else:
            repost_at = start_ts + offset.total_seconds()

        if now < repost_at:
            return

        # --- Okay, it's time to repost! ---
        old_event_id = db_event["event_id"]
        next_start = calc_next_start(start_ts, event_conf)
        if next_start is None:
            log.warning(
                f"[Scheduler] calc_next_start returned None for recurring event {old_event_id}; disabling.",
                guild_id=db_event.get("guild_id"),
            )
            await database.set_event_status(old_event_id, "disabled")
            return

        rec_limit = int(db_event.get("recurrence_limit") or 0)
        rec_count = int(db_event.get("recurrence_count") or 0)
        if rec_limit > 0 and (rec_count + 1) >= rec_limit:
            await database.set_event_status(old_event_id, "closed")
            log.info(
                f"[Scheduler] Limit ({rec_limit}) reached. No more occurrences for {old_event_id}.",
                guild_id=db_event.get("guild_id"),
            )
            return

        extra_data = db_event.get("extra_data")
        if extra_data:
            try:
                ed = json.loads(extra_data) if isinstance(extra_data, str) else extra_data
                limit_ts = ed.get("recurrence_limit_date") if isinstance(ed, dict) else None
                if limit_ts and next_start > limit_ts:
                    await database.set_event_status(old_event_id, "closed")
                    log.info(
                        f"[Scheduler] Cut-off date reached for {old_event_id}; series ended.",
                        guild_id=db_event.get("guild_id"),
                    )
                    return
            except Exception as e:
                log.warning(
                    f"[Scheduler] Could not parse extra_data for {old_event_id}: {e}",
                    guild_id=db_event.get("guild_id"),
                )

        await database.set_event_status(old_event_id, "closed")

        # Create the brand new event in the database
        new_event_id = str(uuid.uuid4())[:8]
        channel_id = event_conf.get("channel_id") or db_event["channel_id"]

        event_conf["recurrence_count"] = rec_count + 1
        event_conf["recurrence_limit"] = rec_limit

        await database.create_active_event(
            guild_id=db_event.get("guild_id"),
            event_id=new_event_id,
            config_name=config_name,
            channel_id=channel_id,
            start_time=next_start,
            data=event_conf
        )

        # Send the new message to the channel
        channel = self.bot.get_channel(channel_id)
        if channel:
            view = DynamicEventView(self.bot, new_event_id, event_conf)
            await view.prepare()

            guild_id = db_event.get("guild_id")
            ping_role = event_conf.get("ping_role", "")
            ping_prefix = ""
            if ping_role and str(ping_role).isdigit() and int(ping_role) > 0:
                ping_prefix = f"{PING} <@&{ping_role}> "

            content = f"{ping_prefix}{t('MSG_REC_ALERT', guild_id=guild_id)}".strip()
            if content:
                await channel.send(content=content)
            new_msg = await channel.send(view=view)
            await database.set_event_message(new_event_id, new_msg.id)
            self.bot.add_view(view)

    async def handle_reminders(self, db_event, now):
        if db_event.get("lobby_mode"):
            return

        rem_type = (db_event.get("reminder_type") or "none").lower()
        if rem_type == "none":
            return

        event_id = db_event["event_id"]
        guild_id = db_event.get("guild_id")
        start_ts = db_event.get("start_time")
        if start_ts is None:
            return

        rows = list(await database.get_event_reminders(event_id))
        legacy_only = False
        if not rows and db_event.get("reminder_offset"):
            if int(db_event.get("reminder_sent") or 0) == 1:
                return
            rows = [
                {"slot_idx": 0, "offset_str": db_event.get("reminder_offset", "15m"), "sent": 0}
            ]
            legacy_only = True

        due = []
        for r in rows:
            if int(r["sent"] or 0) == 1:
                continue
            rem_ts = start_ts - parse_offset(r["offset_str"]).total_seconds()
            if now >= rem_ts:
                due.append(r)
        if not due:
            return

        due.sort(key=lambda x: int(x["slot_idx"]))

        rsvps = await database.get_event_rsvps(event_id)
        participants = [r for r in rsvps if r["status"] == "accepted"]
        if not participants:
            if legacy_only:
                await database.mark_reminder_sent(event_id)
            else:
                await database.mark_all_reminder_slots_sent(event_id)
            return

        # Shared settings/fallbacks
        global_rem_type = (db_event.get("reminder_type") or "none").lower()
        shared_custom_msg = (db_event.get("reminder_message") or "").strip() or None
        
        # Determine mention string
        temp_role_id = db_event.get("temp_role_id")
        # Resolve emoji set for positivity checks
        active_set = get_active_set(db_event.get("icon_set", "standard"))
        pos_ids = set([s.lower() for s in positive_status_ids(active_set)])
        pos_ids.add("accepted") # Ensure legacy consistency
        
        # Build a mapping of labels -> option IDs for easier target resolution
        label_to_id = {}
        for opt in active_set.get("options", []):
            oid = opt["id"].lower()
            label_to_id[oid] = oid # Map ID to itself
            
            # Slugified labels as aliases
            if opt.get("label"):
                label_to_id[slugify(opt["label"])] = oid
            if opt.get("list_label"):
                label_to_id[slugify(opt["list_label"])] = oid

        for r in due:
            target_raw = (r.get("target") or "coming")
            target_key = slugify(target_raw)
            
            # Special aliases for positivity
            is_coming_alias = target_key in ["coming", "positive", "accepted"]
            is_not_coming_alias = target_key in ["not_coming", "negative", "declined"]
            
            # Resolve Target Users
            target_users = []
            if target_key == "all":
                target_users = participants
            elif is_coming_alias:
                target_users = [p for p in participants if p["status"].lower() in pos_ids]
            elif is_not_coming_alias:
                target_users = [p for p in participants if p["status"].lower() not in pos_ids]
            elif target_key in label_to_id:
                # Resolve via our label map (hit: Tank, Tanks, or tank ID)
                resolved_id = label_to_id[target_key]
                target_users = [p for p in participants if p["status"].lower() == resolved_id]
            elif target_key in [p["status"].lower() for p in participants]:
                # Fallback check directly against status just in case
                target_users = [p for p in participants if p["status"].lower() == target_key]
            else:
                # Check for Role Name
                guild = self.bot.get_guild(int(guild_id))
                if guild:
                    role = discord.utils.get(guild.roles, name=target_raw)
                    if role:
                        target_users = [{"user_id": m.id} for m in role.members]
                    else:
                        pass
            
            if not target_users:
                # Mark as handled anyway if no one to notify
                if legacy_only: await database.mark_reminder_sent(event_id)
                else: await database.mark_reminder_slot_sent(event_id, int(r["slot_idx"]))
                continue

            # 1. Determine local reminder type
            local_type = (r.get("method") or global_rem_type or "ping").lower()
            if local_type == "none":
                if legacy_only: await database.mark_reminder_sent(event_id)
                else: await database.mark_reminder_slot_sent(event_id, int(r["slot_idx"]))
                continue
            
            # Final safety: if unknown type, fallback to ping
            if local_type not in ["ping", "dm", "both"]:
                local_type = "ping"
            
            send_ping = local_type in ["ping", "both"]
            send_dm = local_type in ["dm", "both"]
            
            # Determine mention string for this specific group
            if target_key == "all" and temp_role_id:
                mention_str = f"<@&{temp_role_id}>"
            else:
                mention_str = ", ".join([f"<@{p['user_id']}>" for p in target_users[:50]]) # Cap to 50 mentions for sanity

            # 2. Determine local reminder text
            rem_text_raw = r.get("custom_message") or shared_custom_msg
            if rem_text_raw:
                rem_text = rem_text_raw.format(title=db_event["title"])
            else:
                rem_text = t("MSG_REM_DESC", guild_id=guild_id, title=db_event["title"])

            # 3. Send Notifications
            embed = discord.Embed(
                title=t("LBL_REMINDER_TITLE", guild_id=guild_id),
                description=rem_text,
                color=discord.Color.orange(),
            )
            embed.add_field(
                name=t("LBL_STARTS", guild_id=guild_id),
                value=f"<t:{int(start_ts)}:R>",
            )

            if send_ping:
                channel = self.bot.get_channel(db_event["channel_id"])
                if channel:
                    await channel.send(content=mention_str, embed=embed)

            if send_dm:
                for p in target_users:
                    try:
                        user = self.bot.get_user(p["user_id"]) or await self.bot.fetch_user(p["user_id"])
                        if user:
                            await user.send(embed=embed)
                    except Exception as e:
                        log.debug(f"Could not send DM to {p['user_id']}: {e}")

            # 4. Mark Sent
            if legacy_only:
                await database.mark_reminder_sent(event_id)
            else:
                await database.mark_reminder_slot_sent(event_id, int(r["slot_idx"]))

    @check_events.before_loop
    async def before_check_events(self):
        # Wait until the bot is logged in before starting the loop
        await self.bot.wait_until_ready()

async def setup(bot):
    # Load this cog into the bot
    await bot.add_cog(SchedulerTask(bot))
