import discord
from discord.ext import commands, tasks
import database
import time
import uuid
import datetime
from cogs.event_ui import DynamicEventView
import json
from utils.i18n import t

class SchedulerTask(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_events.start()
        
        with open('config.json', 'r', encoding='utf-8') as f:
            self.config = json.load(f)

    def cog_unload(self):
        self.check_events.cancel()

    @tasks.loop(minutes=1.0)
    async def check_events(self):
        current_time = time.time()
        past_recurring_events = await database.get_past_recurring_events(current_time)
        
        for event in past_recurring_events:
            event_id = event['id']
            # Disable the old event
            await database.set_event_status(event_id, 'closed')
            
            try:
                channel = self.bot.get_channel(event['channel_id'])
                if channel:
                    msg = await channel.fetch_message(event['message_id'])
                    if msg:
                        # Disable view
                        view = discord.ui.View.from_message(msg)
                        for child in view.children:
                            child.disabled = True
                        await msg.edit(view=view)
                        
                        embed = msg.embeds[0]
                        embed.title = f"{t('TAG_PAST')} {embed.title}"
                        await msg.edit(embed=embed)
            except Exception as e:
                print(f"Failed to update past event message {event_id}: {e}")

            # Calculate next time
            dt = datetime.datetime.fromtimestamp(event['start_time'], tz=datetime.timezone.utc)
            if event['recurrence_rule'] == 'daily':
                dt += datetime.timedelta(days=1)
            elif event['recurrence_rule'] == 'weekly':
                dt += datetime.timedelta(weeks=1)
                
            new_start_time = dt.timestamp()
            new_event_id = str(uuid.uuid4())[:8]
            
            # Create the cloned event
            await database.create_event(
                event_id=new_event_id,
                title=event['title'],
                description=event['description'],
                start_time=new_start_time,
                recurrence_rule=event['recurrence_rule'],
                creator_id=event['creator_id'],
                image_url=event['image_url'],
                channel_id=event['channel_id'],
                guild_id=event['guild_id']
            )

            if channel:
                view = DynamicEventView(self.bot, new_event_id)
                new_event_dict = await database.get_event(new_event_id)
                embed = await view.generate_embed(new_event_dict)
                
                content = t("MSG_REC_ALERT")
                ping_role = self.config.get("ping_role_id")
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
