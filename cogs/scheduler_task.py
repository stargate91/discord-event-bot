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

def parse_offset(offset_str):
    """Parse offset like '5m', '3h', '6d' into timedelta."""
    match = re.match(r'^(\d+)([mhd])$', offset_str.strip())
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
            config_name = db_event["config_name"]
            event_conf = get_event_conf(config_name)
            if not event_conf:
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
                end_str = event_conf.get("end", "")
                if end_str:
                    local_tz = dttz.gettz(event_conf.get("timezone", "UTC"))
                    end_dt = dtparser.parse(end_str).replace(tzinfo=local_tz)
                    repost_at = end_dt.timestamp() + offset.total_seconds()
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
                        embed = old_msg.embeds[0]
                        embed.title = f"{t('TAG_PAST')} {embed.title}"
                        await old_msg.edit(embed=embed, view=view)
            except Exception as e:
                print(f"[Scheduler] Could not update old message for {old_event_id}: {e}")

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
                start_time=next_start
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

    @check_events.before_loop
    async def before_check_events(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(SchedulerTask(bot))
