import discord
from discord.ext import commands
import database
from utils.i18n import t
import json
from utils.logger import log
import time
import random

def get_event_conf(name):
    try:
        from utils.jsonc import load_jsonc
        config_data = load_jsonc('config.json')
        events = config_data.get("events_config", [])
        for e in events:
            if e.get("name") == name:
                return e
    except Exception:
        pass
    return None

class DynamicEventView(discord.ui.View):
    def __init__(self, bot, event_id: str, event_conf: dict = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.event_id = event_id
        self.event_conf = event_conf

        # Setup buttons
        accept_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="✅", custom_id=f"accept_{event_id}")
        accept_btn.callback = self.accept_callback
        self.add_item(accept_btn)

        decline_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="❌", custom_id=f"decline_{event_id}")
        decline_btn.callback = self.decline_callback
        self.add_item(decline_btn)

        tentative_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="❔", custom_id=f"tentative_{event_id}")
        tentative_btn.callback = self.tentative_callback
        self.add_item(tentative_btn)

    async def accept_callback(self, interaction: discord.Interaction):
        await self.handle_rsvp(interaction, "accepted")

    async def decline_callback(self, interaction: discord.Interaction):
        await self.handle_rsvp(interaction, "declined")

    async def tentative_callback(self, interaction: discord.Interaction):
        await self.handle_rsvp(interaction, "tentative")

    async def delete_callback(self, interaction: discord.Interaction):
        # Allow anyone with Administrator rights to delete
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(t("ERR_NO_PERM"), ephemeral=True)
            return

        await interaction.response.defer()
        await database.delete_active_event(self.event_id)
        
        embed = interaction.message.embeds[0]
        embed.title = f"{t('TAG_DELETED')} {embed.title}"
        embed.color = discord.Color.red()
        
        for child in self.children:
            child.disabled = True
            
        await interaction.message.edit(embed=embed, view=self)
        log.info(f"Event {self.event_id} deleted by {interaction.user}")

    async def generate_embed(self, db_event=None):
        if not db_event:
            db_event = await database.get_active_event(self.event_id)
            
        # Preference: 1. Passed event_conf, 2. Database data, 3. Config.json template
        if not self.event_conf and db_event:
            # Check if database has the data
            if db_event.get("title"):
                self.event_conf = db_event
            else:
                self.event_conf = get_event_conf(db_event["config_name"])

        if not self.event_conf:
            return discord.Embed(title="Missing configuration", color=discord.Color.red())

        rsvps = await database.get_rsvps(self.event_id)
        
        accepted = []
        declined = []
        tentative = []
        
        for user_id, status in rsvps:
            user_mention = f"<@{user_id}>"
            if status == "accepted":
                accepted.append(user_mention)
            elif status == "declined":
                declined.append(user_mention)
            elif status == "tentative":
                tentative.append(user_mention)

        color_hex = str(self.event_conf.get("color", "0x3498db"))
        if color_hex.startswith("0x"):
            color = int(color_hex, 16)
        elif color_hex.startswith("#"):
            color = int(color_hex[1:], 16)
        else:
            color = discord.Color.blue()

        embed = discord.Embed(
            title=self.event_conf.get("title", "Event"),
            description=self.event_conf.get("description", ""),
            color=color
        )
        
        start_ts = db_event['start_time'] if db_event else time.time()
        embed.add_field(name=t("EMBED_START_TIME"), value=f"<t:{int(start_ts)}:F>", inline=False)
        
        recurrence = self.event_conf.get('recurrence_type', 'none')
        if recurrence != 'none':
            embed.add_field(name=t("EMBED_RECURRENCE"), value=recurrence.capitalize(), inline=False)
            
        max_acc = self.event_conf.get('max_accepted', 0)
        acc_label = f"{len(accepted)}/{max_acc}" if max_acc > 0 else f"{len(accepted)}"
            
        embed.add_field(name=t("EMBED_ACC", count=acc_label), value="\n".join(accepted) or t("EMBED_NONE"), inline=True)
        embed.add_field(name=t("EMBED_DEC", count=len(declined)), value="\n".join(declined) or t("EMBED_NONE"), inline=True)
        embed.add_field(name=t("EMBED_TEN", count=len(tentative)), value="\n".join(tentative) or t("EMBED_NONE"), inline=True)

        image_url = self.event_conf.get("image_urls") or self.event_conf.get("image_url")
        if image_url:
            if isinstance(image_url, list):
                embed.set_image(url=random.choice(image_url))
            elif isinstance(image_url, str) and "," in image_url:
                urls = [u.strip() for u in image_url.split(",")]
                # If recurring, send random. Original request: "ha nem recurring akkor csak az elsőt nézi"
                if recurrence != "none":
                    embed.set_image(url=random.choice(urls))
                else:
                    embed.set_image(url=urls[0])
            else:
                embed.set_image(url=image_url)
            
        # Creator logic
        creator_text = "System"
        creator_id_val = self.event_conf.get("creator_id") or (db_event.get("creator_id") if db_event else None)
        
        if creator_id_val:
            if creator_id_val.isdigit():
                # It's a User ID, try to get the user name
                user = self.bot.get_user(int(creator_id_val))
                if not user:
                    try:
                        user = await self.bot.fetch_user(int(creator_id_val))
                    except:
                        user = None
                
                if user:
                    creator_text = user.display_name
                else:
                    creator_text = f"ID: {creator_id_val}"
            else:
                # It's some custom string like "System" or "Dota Master"
                creator_text = creator_id_val

        embed.set_footer(text=t("EMBED_FOOTER", event_id=self.event_id, creator_id=creator_text))

        return embed

    async def handle_rsvp(self, interaction: discord.Interaction, status: str):
        db_event = await database.get_active_event(self.event_id)
        if not db_event:
            await interaction.response.send_message(t("ERR_EV_NOT_FOUND"), ephemeral=True)
            return

        if db_event["status"] != 'active':
            await interaction.response.send_message(t("ERR_EV_INACTIVE"), ephemeral=True)
            return
            
        if not self.event_conf:
            self.event_conf = get_event_conf(db_event["config_name"])
            
        if status == 'accepted' and self.event_conf:
            max_acc = self.event_conf.get('max_accepted', 0)
            if max_acc > 0:
                rsvps = await database.get_rsvps(self.event_id)
                current_acc = sum(1 for _, s in rsvps if s == 'accepted')
                
                # If changing status to accepted, check capacity
                already_accepted = False
                for uid, s in rsvps:
                    if uid == interaction.user.id and s == 'accepted':
                        already_accepted = True
                        break
                        
                if not already_accepted and current_acc >= max_acc:
                    await interaction.response.send_message("Sajnálom, de ez az esemény már betelt!", ephemeral=True)
                    return

        await interaction.response.defer()
        await database.update_rsvp(self.event_id, interaction.user.id, status)
        
        embed = await self.generate_embed(db_event)
        await interaction.message.edit(embed=embed, view=self)
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) RSVP'd {status} for event {self.event_id}")

async def setup(bot):
    pass
