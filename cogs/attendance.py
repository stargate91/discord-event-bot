import discord
from discord.ext import commands
from discord import app_commands, ui
import database
from utils.i18n import t
from utils.auth import is_admin
from utils.logger import log
import time
import math

class AttendanceView(ui.View):
    def __init__(self, bot, event_id, participants, guild_id, title="Event"):
        super().__init__(timeout=600)
        self.bot = bot
        self.event_id = event_id
        self.participants = participants  # list of dicts {user_id, status, attendance}
        self.guild_id = guild_id
        self.event_title = title
        self.page = 0
        self.per_page = 4  # 4 users per page to fit Container + Nav in 5 rows

    async def build(self):
        self.clear_items()
        
        start = self.page * self.per_page
        end = start + self.per_page
        page_users = self.participants[start:end]
        total_pages = math.ceil(len(self.participants) / self.per_page) if self.participants else 1
        
        # 1. Header (Components V2 Container)
        # We use Container for the title and stats summary
        no_shows = sum(1 for p in self.participants if p.get("attendance") == "no_show")
        stats_text = f"✅ {len(self.participants) - no_shows} | ❌ {no_shows}"
        
        header = ui.Container(
            ui.TextDisplay(f"**{self.event_title}** (`{self.event_id}`)"),
            ui.TextDisplay(f"-# {stats_text} • Page {self.page + 1}/{total_pages}"),
            accent_color=0x3498db
        )
        # In V2, Containers often take row 0 or are added first
        self.add_item(header)
        
        # 2. User Rows (Toggle Buttons)
        # Every user gets an ActionRow with a Name and a Toggle
        # Rows 1, 2, 3, 4 are for users
        for i, p in enumerate(page_users):
            uid = p["user_id"]
            status = p["status"]
            att = p.get("attendance", "present")
            is_noshow = (att == "no_show")
            
            # Resolve Member
            guild = self.bot.get_guild(int(self.guild_id))
            member = guild.get_member(int(uid)) if guild else None
            user_name = member.display_name if member else f"User {uid}"
            
            row_idx = i + 1
            
            # Name Button (Disabled, just to show identity)
            name_btn = ui.Button(
                label=user_name, 
                style=discord.ButtonStyle.secondary, 
                disabled=True, 
                row=row_idx
            )
            
            # Toggle Button
            label = "❌ No-show" if is_noshow else "✅ Present"
            style = discord.ButtonStyle.danger if is_noshow else discord.ButtonStyle.success
            
            toggle_btn = ui.Button(
                label=label,
                style=style,
                row=row_idx
            )
            
            async def create_callback(u_id, current_att):
                async def callback(interaction: discord.Interaction):
                    new_att = "present" if current_att == "no_show" else "no_show"
                    await database.update_rsvp_attendance(self.event_id, u_id, new_att)
                    # Update local state to avoid re-fetching
                    for part in self.participants:
                        if part["user_id"] == u_id:
                            part["attendance"] = new_att
                            break
                    await self.refresh(interaction)
                return callback
                
            toggle_btn.callback = create_callback(uid, att)
            
            self.add_item(name_btn)
            self.add_item(toggle_btn)
            
        # 3. Navigation (Row 5 - Last row)
        if total_pages > 1:
            prev_btn = ui.Button(
                label="⬅️", 
                style=discord.ButtonStyle.gray, 
                row=4, 
                disabled=(self.page == 0)
            )
            next_btn = ui.Button(
                label="➡️", 
                style=discord.ButtonStyle.gray, 
                row=4, 
                disabled=(self.page >= total_pages - 1)
            )
            
            async def prev_cb(it):
                self.page -= 1
                await self.refresh(it)
            async def next_cb(it):
                self.page += 1
                await self.refresh(it)
                
            prev_btn.callback = prev_cb
            next_btn.callback = next_cb
            self.add_item(prev_btn)
            self.add_item(next_btn)

    async def refresh(self, interaction: discord.Interaction):
        await self.build()
        await interaction.response.edit_message(view=self)

class AttendanceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    attendance_group = app_commands.Group(name="attendance", description="Manage event attendance")
    
    @attendance_group.command(name="manage", description="Track who showed up for a recent event")
    @app_commands.describe(event_id="The ID of the event to manage")
    async def manage_attendance(self, interaction: discord.Interaction, event_id: str):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        
        if not await is_admin(interaction):
            return await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
            
        # Fetch event
        db_event = await database.get_active_event(event_id, guild_id)
        if not db_event:
            # Check history
            pool = await database.get_pool()
            db_event = await pool.fetchrow("SELECT * FROM active_events WHERE event_id = $1 AND guild_id = $2", event_id, str(guild_id))
            
        if not db_event:
            return await interaction.followup.send(t("ERR_EV_NOT_FOUND", guild_id=guild_id), ephemeral=True)
            
        # Get RSVPs
        rsvps = await database.get_event_attendance_data(event_id)
        
        # Filter for positive statuses
        from cogs.event_ui import get_active_set
        active_set = get_active_set(db_event["icon_set"])
        from utils.lobby_utils import positive_status_ids
        pos_ids = positive_status_ids(active_set)
        
        eligible = [dict(r) for r in rsvps if r["status"] in pos_ids]
        
        if not eligible:
            return await interaction.followup.send("No positive RSVPs found for this event to track attendance.", ephemeral=True)
            
        view = AttendanceView(self.bot, event_id, eligible, guild_id, title=db_event.get("title", "Event"))
        await view.build()
        await interaction.followup.send(view=view, ephemeral=True)

    @manage_attendance.autocomplete("event_id")
    async def attendance_autocomplete(self, interaction: discord.Interaction, current: str):
        events = await database.get_attendance_eligible_events(interaction.guild_id)
        choices = []
        for e in events:
            label = f"{e['title']} ({e['event_id']})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=e['event_id']))
        return choices[:25]

async def setup(bot):
    await bot.add_cog(AttendanceCog(bot))
