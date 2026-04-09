import discord
from discord.ext import commands
import database
from utils.i18n import t
import json
from utils.logger import log
import time
import random

try:
    from utils.jsonc import load_jsonc
    config_data = load_jsonc('config.json')
    ADMIN_ROLE_ID = config_data.get("admin_role_id")
except Exception:
    ADMIN_ROLE_ID = None

def is_admin_user(interaction):
    """Check if user is server admin or has the configured admin role."""
    if interaction.user.guild_permissions.administrator:
        return True
    if ADMIN_ROLE_ID and discord.utils.get(interaction.user.roles, id=ADMIN_ROLE_ID):
        return True
    return False

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

ICON_SETS = {
    "standard": {
        "options": [
            {"id": "accepted", "emoji": "✅", "label_key": "RSVP_ACCEPTED"},
            {"id": "declined", "emoji": "❌", "label_key": "RSVP_DECLINED"},
            {"id": "tentative", "emoji": "❔", "label_key": "RSVP_TENTATIVE"}
        ],
        "positive": ["accepted"],
        "show_mgmt": True
    },
    "mmo": {
        "options": [
            {"id": "tank", "emoji": "🛡️", "label_key": "RSVP_TANK"},
            {"id": "heal", "emoji": "🏥", "label_key": "RSVP_HEAL"},
            {"id": "dps", "emoji": "⚔️", "label_key": "RSVP_DPS"},
            {"id": "tentative", "emoji": "❔", "label_key": "RSVP_TENTATIVE"},
            {"id": "declined", "emoji": "❌", "label_key": "RSVP_DECLINED"}
        ],
        "positive": ["tank", "heal", "dps"],
        "show_mgmt": False
    },
    "team": {
        "options": [
            {"id": "team_a", "emoji": "🅰️", "label_key": "RSVP_TEAM_A"},
            {"id": "team_b", "emoji": "🅱️", "label_key": "RSVP_TEAM_B"},
            {"id": "spectator", "emoji": "👁️", "label_key": "RSVP_SPECTATOR"},
            {"id": "tentative", "emoji": "❔", "label_key": "RSVP_TENTATIVE"},
            {"id": "declined", "emoji": "❌", "label_key": "RSVP_DECLINED"}
        ],
        "positive": ["team_a", "team_b", "spectator"],
        "show_mgmt": False
    },
    "timing": {
        "options": [
            {"id": "on_time", "emoji": "✅", "label_key": "RSVP_ON_TIME"},
            {"id": "late", "emoji": "⏰", "label_key": "RSVP_LATE"},
            {"id": "interim", "emoji": "🏃", "label_key": "RSVP_INTERIM"},
            {"id": "tentative", "emoji": "❔", "label_key": "RSVP_TENTATIVE"},
            {"id": "declined", "emoji": "❌", "label_key": "RSVP_DECLINED"}
        ],
        "positive": ["on_time", "late", "interim"],
        "show_mgmt": False
    }
}

class DynamicEventView(discord.ui.View):
    def __init__(self, bot, event_id: str, event_conf: dict = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.event_id = event_id
        self.event_conf = event_conf

        # Determine icon set
        icon_set_key = "standard"
        if event_conf:
            icon_set_key = event_conf.get("icon_set", "standard")
        
        self.active_set = ICON_SETS.get(icon_set_key, ICON_SETS["standard"])

        # Dynamic RSVP Buttons
        for opt in self.active_set["options"]:
            btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary, 
                emoji=opt["emoji"], 
                custom_id=f"{opt['id']}_{event_id}"
            )
            # Create a closure for the callback
            def create_callback(status_id):
                async def callback(interaction: discord.Interaction):
                    await self.handle_rsvp(interaction, status_id)
                return callback
            
            btn.callback = create_callback(opt["id"])
            self.add_item(btn)

        # Calendar always available
        calendar_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="📅", custom_id=f"calendar_{event_id}")
        calendar_btn.callback = self.calendar_callback
        self.add_item(calendar_btn)

        # Management Buttons (Admin only, only for Standard set)
        if self.active_set["show_mgmt"]:
            edit_btn = discord.ui.Button(label=t("BTN_EDIT"), style=discord.ButtonStyle.gray, custom_id=f"edit_{event_id}")
            edit_btn.callback = self.edit_callback
            self.add_item(edit_btn)

            delete_btn = discord.ui.Button(label=t("BTN_DELETE"), style=discord.ButtonStyle.danger, custom_id=f"delete_{event_id}")
            delete_btn.callback = self.delete_callback
            self.add_item(delete_btn)

    async def edit_callback(self, interaction: discord.Interaction):
        if not is_admin_user(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        db_event = await database.get_active_event(self.event_id)
        if not db_event:
            await interaction.followup.send(t("ERR_EV_NOT_FOUND"), ephemeral=True)
            return

        # Prepare existing data for the wizard
        from dateutil import tz
        import datetime
        local_tz = tz.gettz(db_event.get("timezone", "Europe/Budapest"))
        start_dt = datetime.datetime.fromtimestamp(db_event["start_time"], tz=local_tz)
        db_event["start_str"] = start_dt.strftime("%Y-%m-%d %H:%M")
        
        if db_event.get("end_time"):
            end_dt = datetime.datetime.fromtimestamp(db_event["end_time"], tz=local_tz)
            db_event["end_str"] = end_dt.strftime("%Y-%m-%d %H:%M")
        else:
            db_event["end_str"] = ""

        from cogs.event_wizard import EventWizardView
        view = EventWizardView(self.bot, interaction.user.id, existing_data=db_event, is_edit=True)
        
        from utils.i18n import t
        embed = discord.Embed(
            title=t("WIZARD_TITLE"), 
            description=t("WIZARD_DESC", status=view.get_status_text()), 
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def calendar_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db_event = await database.get_active_event(self.event_id)
        if not db_event:
            await interaction.followup.send("Event not found.", ephemeral=True)
            return
        
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
        
        # Organize RSVPs by status
        status_map = {}
        for user_id, status in rsvps:
            if status not in status_map:
                status_map[status] = []
            status_map[status].append(f"<@{user_id}>")

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
            
        # Build dynamic fields based on icon set
        max_acc = self.event_conf.get('max_accepted', 0)
        
        for opt in self.active_set["options"]:
            users = status_map.get(opt["id"], [])
            
            # Label logic: Use translated label key
            label_text = t(opt["label_key"])
            
            # Handle count/max for the primary "accept" status if applicable
            # (Usually 'accepted' for standard, 'tank'/'heal'/'dps' for MMO)
            # For simplicity, we only show max limit on the FIRST option 
            # OR we could just show count for all. 
            # User request didn't specify, so we'll show count for all.
            # But for 'accepted', we keep the special count/max label.
            
            count_text = str(len(users))
            if opt["id"] == "accepted" and max_acc > 0:
                count_text = f"{len(users)}/{max_acc}"
            
            field_name = f"{opt['emoji']} {label_text} ({count_text})"
            embed.add_field(name=field_name, value="\n".join(users) or t("EMBED_NONE"), inline=True)

        image_urls_val = self.event_conf.get("image_urls")
        if image_urls_val:
            if isinstance(image_urls_val, list):
                embed.set_image(url=random.choice(image_urls_val))
            elif isinstance(image_urls_val, str) and "," in image_urls_val:
                urls = [u.strip() for u in image_urls_val.split(",")]
                # If recurring, send random.
                if recurrence != "none":
                    embed.set_image(url=random.choice(urls))
                else:
                    embed.set_image(url=urls[0])
            else:
                embed.set_image(url=image_urls_val)
            
        # Creator logic
        creator_text = "System"
        creator_id_val = self.event_conf.get("creator_id")
        
        if creator_id_val:
            if str(creator_id_val).isdigit():
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
                creator_text = str(creator_id_val)

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
            if not self.event_conf:
                self.event_conf = db_event

        # Generic Capacity Check
        positive_statuses = self.active_set.get("positive", ["accepted"])
        if status in positive_statuses:
            max_acc = self.event_conf.get('max_accepted', 0)
            if max_acc > 0:
                rsvps = await database.get_rsvps(self.event_id)
                current_acc = sum(1 for _, s in rsvps if s in positive_statuses)
                
                # If changing status to a positive one, check capacity
                already_has_positive = False
                for uid, s in rsvps:
                    if uid == interaction.user.id and s in positive_statuses:
                        already_has_positive = True
                        break
                        
                if not already_has_positive and current_acc >= max_acc:
                    await interaction.response.send_message("Sajnálom, de ez az esemény már betelt!", ephemeral=True)
                    return

        await interaction.response.defer()
        await database.update_rsvp(self.event_id, interaction.user.id, status)
        
        embed = await self.generate_embed(db_event)
        await interaction.message.edit(embed=embed, view=self)
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) RSVP'd {status} for event {self.event_id}")

async def setup(bot):
    pass
