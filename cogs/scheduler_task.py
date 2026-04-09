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
            # 1. We check if anyone needs a reminder
            try:
                await self.handle_reminders(db_event, now)
            except Exception as e:
                log.error(f"[Scheduler] Error handling reminders for {db_event['event_id']}: {e}")

            # 2. We check if it's time to repost a recurring event
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

            # We calculate EXACTLY when we should make the next message
            if trigger == "before_start":
                next_start = calc_next_start(start_ts, event_conf)
                if next_start is None:
                    continue
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
                continue

            # --- Okay, it's time to repost! ---
            old_event_id = db_event["event_id"]
            await database.set_event_status(old_event_id, "closed")

            # We disable the buttons on the old message so people don't click them
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

            # Find the new start time
            next_start = calc_next_start(start_ts, event_conf)
            if next_start is None:
                continue

            # Check if we already reached the repetition limit
            rec_limit = int(db_event.get("recurrence_limit") or 0)
            rec_count = int(db_event.get("recurrence_count") or 0)
            
            if rec_limit > 0 and (rec_count + 1) >= rec_limit:
                log.info(f"[Scheduler] Limit ({rec_limit}) reached. No more events for today.")
                continue

            # Create the brand new event in the database
            new_event_id = str(uuid.uuid4())[:8]
            channel_id = event_conf.get("channel_id") or db_event["channel_id"]

            event_conf["recurrence_count"] = rec_count + 1
            event_conf["recurrence_limit"] = rec_limit

            await database.create_active_event(
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

                content = t("MSG_REC_ALERT")
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
        rsvps = await database.get_event_rsvps(event_id)
        # We only remind those who said they are coming
        participants = [r for r in rsvps if r["status"] == "accepted"]
        
        if not participants:
            await database.mark_reminder_sent(event_id)
            return

        mentions = [f"<@{p['user_id']}>" for p in participants]
        
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
                    rem_text = t("MSG_REM_DESC", title=db_event['title'])

                # Send a message in the channel
                if send_ping:
                    channel = self.bot.get_channel(db_event["channel_id"])
                    if channel:
                        mention_str = ", ".join(mentions)
                        embed = discord.Embed(
                            title=f"🔔 Emlékeztető / Reminder",
                            description=rem_text,
                            color=discord.Color.orange()
                        )
                        embed.add_field(name="Kezdés / Starts", value=f"<t:{int(start_ts)}:R>")
                        await channel.send(content=mention_str, embed=embed)

                # Send a private message (DM) to everyone
                if send_dm:
                    for p in participants:
                        try:
                            user = self.bot.get_user(p['user_id']) or await self.bot.fetch_user(p['user_id'])
                            if user:
                                embed = discord.Embed(
                                    title=f"🔔 Emlékeztető / Reminder",
                                    description=rem_text,
                                    color=discord.Color.orange()
                                )
                                embed.add_field(name="Kezdés / Starts", value=f"<t:{int(start_ts)}:R>")
                                await user.send(embed=embed)
                        except Exception as e:
                            log.error(f"Could not send DM to {p['user_id']}: {e}")

        await database.mark_reminder_sent(event_id)

    @check_events.before_loop
    async def before_check_events(self):
        # Wait until the bot is logged in before starting the loop
        await self.bot.wait_until_ready()

async def setup(bot):
    # Load this cog into the bot
    await bot.add_cog(SchedulerTask(bot))
