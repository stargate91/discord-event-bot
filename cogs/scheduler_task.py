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
    """Parse offset like '5m', '3h', '6d' into timedelta."""
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
    """Calculate the next start timestamp based on recurrence_type."""
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
    def __init__(self, bot):
        self.bot = bot
        self.check_events.start()

    def cog_unload(self):
        self.check_events.cancel()

    def _load_config(self):
        from utils.jsonc import load_jsonc
        return load_jsonc('config.json')

    @tasks.loop(minutes=1.0)
    async def check_events(self):
        now = time.time()
        active_events = await database.get_all_active_events()

        for db_event in active_events:
            # 1. Handle Reminders
            try:
                await self.handle_reminders(db_event, now)
            except Exception as e:
                log.error(f"[Scheduler] Error handling reminders for {db_event['event_id']}: {e}")

            # 2. Handle Reposting / Recurrence
            config_name = db_event["config_name"]
            event_conf = get_event_conf(config_name)
            if not event_conf:
                continue

            if not event_conf.get("enabled", True):
                await database.set_event_status(db_event["event_id"], "disabled")
                continue

            rec_type = event_conf.get("recurrence_type", "once")
            if rec_type == "once":
                continue

            start_ts = db_event["start_time"]
            trigger = event_conf.get("repost_trigger", "after_start")
            offset = parse_offset(event_conf.get("repost_offset", "1h"))

            # Determine the repost moment
            if trigger == "before_start":
                next_start = calc_next_start(start_ts, event_conf)
                if next_start is None:
                    continue
                repost_at = next_start - offset.total_seconds()
            elif trigger == "after_end":
                # Fallback if end_time column is used instead of end string
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
                continue

            # --- Time to repost! ---
            old_event_id = db_event["event_id"]
            await database.set_event_status(old_event_id, "closed")

            # Disable buttons on old message
            try:
                channel = self.bot.get_channel(db_event["channel_id"])
                if channel and db_event.get("message_id"):
                    old_msg = await channel.fetch_message(db_event["message_id"])
                    if old_msg:
                        view = discord.ui.View.from_message(old_msg)
                        for child in view.children:
                            child.disabled = True
                        if old_msg.embeds:
                            embed = old_msg.embeds[0]
                            embed.title = f"{t('TAG_PAST')} {embed.title}"
                            await old_msg.edit(embed=embed, view=view)
            except Exception as e:
                log.error(f"[Scheduler] Could not update old message for {old_event_id}: {e}")

            # Calculate next start
            next_start = calc_next_start(start_ts, event_conf)
            if next_start is None:
                continue

            new_event_id = str(uuid.uuid4())[:8]
            channel_id = event_conf.get("channel_id") or db_event["channel_id"]

            await database.create_active_event(
                event_id=new_event_id,
                config_name=config_name,
                channel_id=channel_id,
                start_time=next_start,
                data=event_conf
            )

            channel = self.bot.get_channel(channel_id)
            if channel:
                view = DynamicEventView(self.bot, new_event_id, event_conf)
                embed = await view.generate_embed()

                content = t("MSG_REC_ALERT")
                ping_role = event_conf.get("ping_role", "")
                if ping_role:
                    content += f" <@&{ping_role}>"

                new_msg = await channel.send(content=content, embed=embed, view=view)
                await database.set_event_message(new_event_id, new_msg.id)
                self.bot.add_view(view)

    async def handle_reminders(self, db_event, now):
        rem_type = db_event.get("reminder_type", "none")
        if rem_type == "none" or db_event.get("reminder_sent", 0) == 1:
            return

        start_ts = db_event["start_time"]
        offset = parse_offset(db_event.get("reminder_offset", "15m"))
        rem_ts = start_ts - offset.total_seconds()

        if now < rem_ts:
            return

        # It's time!
        event_id = db_event["event_id"]
        rsvps = await database.get_event_rsvps(event_id)
        # Filters participants who accepted
        participants = [r for r in rsvps if r["status"] == "accepted"]
        
        if not participants:
            # No one to remind, but mark as sent anyway
            await database.mark_reminder_sent(event_id)
            return

        mentions = [f"<@{p['user_id']}>" for p in participants]
        
        # Determine notification channels
        send_ping = rem_type in ["ping", "both"]
        send_dm = rem_type in ["dm", "both"]

        # Send Ping in channel
        if send_ping:
            channel = self.bot.get_channel(db_event["channel_id"])
            if channel:
                mention_str = ", ".join(mentions)
                embed = discord.Embed(
                    title=f"🔔 Emlékeztető / Reminder",
                    description=f"{t('MSG_REM_DESC', title=db_event['title'])}",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Kezdés / Starts", value=f"<t:{int(start_ts)}:R>")
                await channel.send(content=mention_str, embed=embed)

        # Send DM to each participant
        if send_dm:
            for p in participants:
                try:
                    user = self.bot.get_user(p['user_id']) or await self.bot.fetch_user(p['user_id'])
                    if user:
                        embed = discord.Embed(
                            title=f"🔔 Emlékeztető / Reminder",
                            description=f"{t('MSG_REM_DESC', title=db_event['title'])}",
                            color=discord.Color.orange()
                        )
                        embed.add_field(name="Kezdés / Starts", value=f"<t:{int(start_ts)}:R>")
                        await user.send(embed=embed)
                except Exception as e:
                    log.error(f"Could not send DM to {p['user_id']}: {e}")

        await database.mark_reminder_sent(event_id)

    @check_events.before_loop
    async def before_check_events(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(SchedulerTask(bot))
