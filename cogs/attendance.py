import discord
from discord.ext import commands
from discord import app_commands, ui
import database
from utils.i18n import t
from utils.auth import is_admin
from utils.logger import log
import time
import math

class AttendanceView(ui.LayoutView):
    def __init__(self, bot, event_id, participants, guild_id, title="Event"):
        super().__init__(timeout=600)
        self.bot = bot
        self.event_id = event_id
        self.participants = participants  # list of dicts {user_id, status, attendance}
        self.guild_id = guild_id
        self.event_title = title
        self.page = 0
        self.per_page = 3  # Compact layout for premium Container look
        self.name_cache = {} # Avoid redundant member lookups

    async def build(self):
        self.clear_items()
        
        start = self.page * self.per_page
        end = start + self.per_page
        page_users = self.participants[start:end]
        total_pages = math.ceil(len(self.participants) / self.per_page) if self.participants else 1
        
        # 1. Header Info
        no_shows = sum(1 for p in self.participants if p.get("attendance") == "no_show")
        stats_text = f"✅ {len(self.participants) - no_shows} | ❌ {no_shows}"
        
        container_items = [
            ui.TextDisplay(f"### {self.event_title}"),
            ui.TextDisplay(f"-# {stats_text} • Page {self.page + 1}/{total_pages}"),
            ui.Separator()
        ]
        
        # 2. Member Rows
        for p in page_users:
            uid = p["user_id"]
            att = p.get("attendance", "present")
            is_noshow = (att == "no_show")
            
            # Resolve Member Identity (with caching)
            user_name = self.name_cache.get(uid)
            if not user_name:
                guild = self.bot.get_guild(int(self.guild_id)) if self.guild_id and str(self.guild_id).isdigit() else None
                member = guild.get_member(int(uid)) if guild and uid and str(uid).isdigit() else None
                user_name = member.display_name if member else f"User {uid}"
                self.name_cache[uid] = user_name
            
            # Add Name as Text
            container_items.append(ui.TextDisplay(f"**{user_name}**"))
            
            # ActionRow for the Toggle Button
            label = "❌ No-show" if is_noshow else "✅ Present"
            style = discord.ButtonStyle.danger if is_noshow else discord.ButtonStyle.success
            toggle_btn = ui.Button(label=label, style=style)
            
            async def create_callback(u_id, current_att):
                async def callback(interaction: discord.Interaction):
                    # ABSOLUTE FIRST LINE: Defer to prevent timeouts
                    try:
                        await interaction.response.defer()
                    except:
                        pass
                        
                    try:
                        new_att = "present" if current_att == "no_show" else "no_show"
                        await database.update_rsvp_attendance(self.event_id, u_id, new_att)
                        for part in self.participants:
                            if part["user_id"] == u_id:
                                part["attendance"] = new_att
                                break
                        await self.refresh(interaction)
                    except Exception as e:
                        log.error(f"Attendance callback error: {e}", exc_info=True)
                        try: await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
                        except: pass
                return callback
                
            toggle_btn.callback = create_callback(uid, att)
            
            container_items.append(ui.ActionRow(toggle_btn))
            container_items.append(ui.Separator())

        # 3. Navigation Controls
        if total_pages > 1:
            prev_btn = ui.Button(label="⬅️", style=discord.ButtonStyle.gray, disabled=(self.page == 0))
            next_btn = ui.Button(label="➡️", style=discord.ButtonStyle.gray, disabled=(self.page >= total_pages - 1))
            
            async def prev_cb(it):
                await it.response.defer()
                self.page -= 1
                await self.refresh(it)
            async def next_cb(it):
                await it.response.defer()
                self.page += 1
                await self.refresh(it)
                
            prev_btn.callback = prev_cb
            next_btn.callback = next_cb
            container_items.append(ui.ActionRow(prev_btn, next_btn))
        
        # 4. Final Container Assembly
        # Use an accent color to make it pop (light blue)
        main_container = ui.Container(*container_items, accent_color=0x3498db)
        self.add_item(main_container)

    async def refresh(self, interaction: discord.Interaction):
        await self.build()
        if interaction.response.is_done():
            await interaction.edit_original_response(content=None, embeds=[], view=self)
        else:
            await interaction.response.edit_message(content=None, embeds=[], view=self)

class AttendanceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    attendance_group = app_commands.Group(name="attendance", description="Manage event attendance")
    
    @attendance_group.command(name="manage", description="Track who showed up for a recent event")
    @app_commands.describe(event_id="The ID of the event to manage")
    async def manage_attendance(self, interaction: discord.Interaction, event_id: str):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        
        try:
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
                return await interaction.followup.send(t("ERR_NO_MY_EVENTS", guild_id=guild_id) or "No positive RSVPs found for this event.", ephemeral=True)
                
            view = AttendanceView(self.bot, event_id, eligible, guild_id, title=db_event.get("title", "Event"))
            await view.build()
            await interaction.followup.send(view=view, ephemeral=True)
            
        except Exception as e:
            log.error(f"[Attendance] Error in manage_attendance for event {event_id}: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)
            except:
                pass

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
