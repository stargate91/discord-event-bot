import discord
from discord.ext import commands, tasks
import database
import time
import uuid
import datetime
import json
import re
from cogs.event_ui import DynamicEventView, get_event_conf
from utils.i18n import t
from dateutil import parser as dtparser
from dateutil import tz as dttz
from dateutil.relativedelta import relativedelta
from utils.logger import log

def parse_offset(offset_str):
    # This turns strings like "5m" or "3h" into actual time durations
    match = re.match(r'^(\d+)([mhd])$', str(offset_str).strip())
    if not match:
        return datetime.timedelta(hours=1)
    val, unit = int(match.group(1)), match.group(2)
    if unit == 'm':
        return datetime.timedelta(minutes=val)
    elif unit == 'h':
        return datetime.timedelta(hours=val)
    elif unit == 'd':
        return datetime.timedelta(days=val)
    return datetime.timedelta(hours=1)

def calc_next_start(current_start_ts, event_conf):
    # This calculates when the same event should happen next (Daily, Weekly, etc)
    local_tz = dttz.gettz(event_conf.get("timezone", "UTC"))
    dt = datetime.datetime.fromtimestamp(current_start_ts, tz=local_tz)
    rec = event_conf.get("recurrence_type", "once")

    if rec == "daily":
        dt += datetime.timedelta(days=1)
    elif rec == "weekly":
        dt += datetime.timedelta(weeks=1)
    elif rec == "weekdays":
        dt += datetime.timedelta(days=1)
        while dt.weekday() >= 5:
            dt += datetime.timedelta(days=1)
    elif rec == "monthly":
        dt += relativedelta(months=1)
    else:
        return None
    return dt.timestamp()

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

    async def check_role_cleanup(self, db_event, now):
        """Deletes temporary Discord roles once the event has finished."""
        temp_role_id = db_event.get("temp_role_id")
        if not temp_role_id:
            return

        should_delete = False
        end_ts = db_event.get("end_time")
        start_ts = db_event["start_time"]
        
        if end_ts and now > end_ts:
            should_delete = True
        elif not end_ts and now > (start_ts + 14400): # 4 hours fallback
            should_delete = True
        
        # Also cleanup if the event was marked as closed/finished
        if db_event.get("status") == "closed":
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

    async def handle_reposting(self, db_event, now):
        """Checks if a recurring event needs to be reposted."""
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
        await database.set_event_status(old_event_id, "closed")

        # Find the new start time
        next_start = calc_next_start(start_ts, event_conf)
        if next_start is None:
            return

        # Check if we already reached the repetition limit
        rec_limit = int(db_event.get("recurrence_limit") or 0)
        rec_count = int(db_event.get("recurrence_count") or 0)
        
        if rec_limit > 0 and (rec_count + 1) >= rec_limit:
            log.info(f"[Scheduler] Limit ({rec_limit}) reached. No more events for today.", guild_id=db_event.get("guild_id"))
            return
            
        # Check for specific cut-off date limit
        extra_data = db_event.get("extra_data")
        if extra_data:
            try:
                if isinstance(extra_data, str): extra_data = json.loads(extra_data)
                limit_ts = extra_data.get("recurrence_limit_date")
                if limit_ts and next_start > limit_ts:
                    log.info(f"[Scheduler] Cut-off date limit reached. No more events.", guild_id=db_event.get("guild_id"))
                    return
            except:
                pass

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
            embed = await view.generate_embed()

            guild_id = db_event.get("guild_id")
            content = t("MSG_REC_ALERT", guild_id=guild_id)
            ping_role = event_conf.get("ping_role", "")
            if ping_role:
                content += f" <@&{ping_role}>"

            new_msg = await channel.send(content=content, embed=embed, view=view)
            await database.set_event_message(new_event_id, new_msg.id)
            self.bot.add_view(view)

    async def handle_reminders(self, db_event, now):
        # This function checks if we need to send a "Hey, it starts soon!" message
        rem_type = db_event.get("reminder_type", "none")
        if rem_type == "none" or db_event.get("reminder_sent", 0) == 1:
            return

        start_ts = db_event["start_time"]
        offset = parse_offset(db_event.get("reminder_offset", "15m"))
        rem_ts = start_ts - offset.total_seconds()

        if now < rem_ts:
            return

        # Time to remind people!
        event_id = db_event["event_id"]
        guild_id = db_event.get("guild_id")
        
        # Optimized RSVP fetch: get once, use for both ping and DM logic
        rsvps = await database.get_event_rsvps(event_id)
        participants = [r for r in rsvps if r["status"] == "accepted"]
        if not participants:
            await database.mark_reminder_sent(event_id)
            return

        # Temp Role Logic for Pings
        temp_role_id = db_event.get("temp_role_id")
        if temp_role_id:
            mention_str = f"<@&{temp_role_id}>"
        else:
            mention_str = ", ".join([f"<@{p['user_id']}>" for p in participants])
        
        send_ping = rem_type in ["ping", "both"]
        send_dm = rem_type in ["dm", "both"]

        # Check for custom reminder message
        extra_data = db_event.get("extra_data")
        custom_reminder = None
        if extra_data:
            try:
                if isinstance(extra_data, str):
                    custom_reminder = json.loads(extra_data).get("custom_reminder_msg")
                else:
                    custom_reminder = extra_data.get("custom_reminder_msg")
            except: pass
        
        if custom_reminder:
            rem_text = custom_reminder.format(title=db_event['title'])
        else:
            rem_text = t("MSG_REM_DESC", guild_id=guild_id, title=db_event['title'])

        # Send a message in the channel
        if send_ping:
            channel = self.bot.get_channel(db_event["channel_id"])
            if channel:
                embed = discord.Embed(
                    title=t("LBL_REMINDER_TITLE", guild_id=guild_id),
                    description=rem_text,
                    color=discord.Color.orange()
                )
                embed.add_field(name=t("LBL_STARTS", guild_id=guild_id), value=f"<t:{int(start_ts)}:R>")
                await channel.send(content=mention_str, embed=embed)

        # Send a private message (DM) to everyone
        if send_dm:
            for p in participants:
                try:
                    user = self.bot.get_user(p['user_id']) or await self.bot.fetch_user(p['user_id'])
                    if user:
                        guild_id = db_event.get("guild_id")
                        embed = discord.Embed(
                            title=t("LBL_REMINDER_TITLE", guild_id=guild_id),
                            description=rem_text,
                            color=discord.Color.orange()
                        )
                        embed.add_field(name=t("LBL_STARTS", guild_id=guild_id), value=f"<t:{int(start_ts)}:R>")
                        await user.send(embed=embed)
                except Exception as e:
                    log.error(f"Could not send DM to {p['user_id']}: {e}", guild_id=db_event.get("guild_id"))

        await database.mark_reminder_sent(event_id)

    @check_events.before_loop
    async def before_check_events(self):
        # Wait until the bot is logged in before starting the loop
        await self.bot.wait_until_ready()

async def setup(bot):
    # Load this cog into the bot
    await bot.add_cog(SchedulerTask(bot))
