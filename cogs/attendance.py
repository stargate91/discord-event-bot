import discord
from discord.ext import commands
from discord import app_commands, ui
import database
from utils.i18n import t
from utils.auth import is_admin
from utils.logger import log
from utils import emojis
import time
import math

import asyncio

class AttendanceView(ui.LayoutView):
    def __init__(self, bot, event_id, participants, guild_id, title="Event"):
        super().__init__(timeout=600)
        self.bot = bot
        self.event_id = event_id
        self.participants = participants  # list of dicts {user_id, status, attendance}
        self.guild_id = guild_id
        self.event_title = title
        self.page = 0
        self.per_page = 5  # Premium Section Layout: 5 users fit comfortably
        self.name_cache = {} # Avoid redundant member lookups

    async def build(self):
        self.clear_items()
        
        start = self.page * self.per_page
        end = start + self.per_page
        page_users = self.participants[start:end]
        total_pages = math.ceil(len(self.participants) / self.per_page) if self.participants else 1
        
        # 1. Parallel Member Resolution (Performance Boost)
        missing_ids = [str(p["user_id"]) for p in page_users if str(p["user_id"]) not in self.name_cache]
        if missing_ids:
            guild = self.bot.get_guild(int(self.guild_id)) if self.guild_id and str(self.guild_id).isdigit() else None
            if guild:
                async def fetch(uid):
                    try:
                        mem = guild.get_member(int(uid)) or await guild.fetch_member(int(uid))
                        return uid, mem.display_name
                    except:
                        return uid, t("LBL_USER_DEFAULT", guild_id=self.guild_id).replace("{uid}", str(uid))
                
                results = await asyncio.gather(*(fetch(uid) for uid in missing_ids))
                for uid, name in results:
                    self.name_cache[uid] = name

        # 2. Prepare Container Items
        no_shows = sum(1 for p in self.participants if p.get("attendance") == "no_show")
        
        # Localized Stats
        stats_text = t("MSG_ATT_STATS", guild_id=self.guild_id)
        stats_text = stats_text.replace("{attended}", str(len(self.participants) - no_shows))
        stats_text = stats_text.replace("{noshows}", str(no_shows))
        
        page_label = f"{t('LBL_PAGE', guild_id=self.guild_id)} {self.page + 1}/{total_pages}"
        
        container_items = [
            ui.TextDisplay(f"### {self.event_title}"),
            ui.TextDisplay(f"-# {stats_text} • {page_label}")
        ]
        
        for i, p in enumerate(page_users):
            idx = (self.page * self.per_page) + i + 1
            uid = str(p["user_id"])
            att = p.get("attendance", "present")
            is_noshow = (att == "no_show")
            
            # Name Lookup (from cache)
            user_name = self.name_cache.get(uid, t("LBL_USER_DEFAULT", guild_id=self.guild_id).replace("{uid}", str(uid)))
            
            # Create Toggle Button as Accessory
            label = t("LBL_ATT_NOSHOW", guild_id=self.guild_id) if is_noshow else t("LBL_ATT_PRESENT", guild_id=self.guild_id)
            style = discord.ButtonStyle.danger if is_noshow else discord.ButtonStyle.success
            
            toggle_btn = ui.Button(
                label=label, 
                style=style, 
                custom_id=f"att_tg_{uid}_{self.page}"
            )
            
            def create_callback(u_id, current_att, current_idx):
                async def callback(interaction: discord.Interaction):
                    # Safety First: Defer
                    try: await interaction.response.defer()
                    except: pass
                    
                    log.info(f"[Attendance Debug] SECTION CLICK: User #{current_idx} (UID: {u_id})")
                    try:
                        new_att = "present" if current_att == "no_show" else "no_show"
                        await database.update_rsvp_attendance(self.event_id, u_id, new_att)
                        for part in self.participants:
                            if part["user_id"] == u_id:
                                part["attendance"] = new_att
                                break
                        await self.refresh(interaction)
                    except Exception as e:
                        import traceback
                        log.error(f"[Attendance] Section callback failure: {e}\n{traceback.format_exc()}")
                        try: await interaction.followup.send(f"{emojis.ERROR} {t('ERR_WIZARD_GENERAL', guild_id=self.guild_id).replace('{e}', str(e))}", ephemeral=True)
                        except: pass
                return callback
                
            toggle_btn.callback = create_callback(uid, att, idx)
            
            # Use ui.Section for the side-by-side layout (Modern V2 style)
            section = ui.Section(f"**{idx}. {user_name}**", accessory=toggle_btn)
            container_items.append(section)

        # Add the Container to the View
        main_container = ui.Container(*container_items, accent_color=0x3498db)
        self.add_item(main_container)
        
        # 3. Navigation Buttons (if needed)
        if total_pages > 1:
            prev_btn = ui.Button(label=emojis.BACK, style=discord.ButtonStyle.gray, disabled=(self.page == 0), custom_id=f"att_pre_{self.page}")
            next_btn = ui.Button(label=emojis.FORWARD, style=discord.ButtonStyle.gray, disabled=(self.page >= total_pages - 1), custom_id=f"att_nxt_{self.page}")
            
            async def prev_cb(it):
                try: await it.response.defer()
                except: pass
                log.info(f"[Attendance Debug] NAV: Prev")
                self.page -= 1
                await self.refresh(it)
            async def next_cb(it):
                try: await it.response.defer()
                except: pass
                log.info(f"[Attendance Debug] NAV: Next")
                self.page += 1
                await self.refresh(it)
                
            prev_btn.callback = prev_cb
            next_btn.callback = next_cb
            self.add_item(ui.ActionRow(prev_btn, next_btn))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        import traceback
        log.error(f"[Attendance] View Error on {item}: {error}\n{traceback.format_exc()}")
        try: 
            msg = f"{emojis.ERROR} {t('ERR_WIZARD_GENERAL', guild_id=self.guild_id).replace('{e}', str(error))}"
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except: pass

    async def refresh(self, interaction: discord.Interaction):
        # Fresh Instance Pattern 
        new_view = AttendanceView(self.bot, self.event_id, self.participants, self.guild_id, self.event_title)
        new_view.page = self.page
        new_view.name_cache = self.name_cache
        await new_view.build()
        
        log.info(f"[Attendance Debug] REFRESH: Updating message with new view state")
        if interaction.response.is_done():
            await interaction.edit_original_response(content=None, embeds=[], view=new_view)
        else:
            await interaction.response.edit_message(content=None, embeds=[], view=new_view)

class AttendanceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    attendance_group = app_commands.Group(name="attendance", description="Manage event attendance")
    
    @attendance_group.command(name="manage", description="Track who showed up for a recent event")
    @app_commands.describe(event_id="The ID of the event to manage")
    async def manage_attendance(self, interaction: discord.Interaction, event_id: str):
        # 1. DEFER IMMEDIATELY (Safety First)
        await interaction.response.defer(ephemeral=True)
        
        # 2. LOUD LOG: Command start
        log.info(f"[Attendance Debug] COMMAND START: Event {event_id}")
        
        guild_id = interaction.guild_id
        
        try:
            from utils.auth import is_admin
            if not await is_admin(interaction):
                await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
                return
                
            # Fetch event
            db_event = await database.get_active_event(event_id, guild_id)
            if not db_event:
                # Check history
                pool = await database.get_pool()
                db_event = await pool.fetchrow("SELECT * FROM active_events WHERE event_id = $1 AND guild_id = $2", event_id, str(guild_id))
                
            if not db_event:
                await interaction.followup.send(t("ERR_EV_NOT_FOUND", guild_id=guild_id), ephemeral=True)
                return
                
            # Get RSVPs
            rsvps = await database.get_event_attendance_data(event_id)
            
            # Filter for positive statuses
            from cogs.event_ui import get_active_set
            active_set = get_active_set(db_event["icon_set"])
            from utils.lobby_utils import positive_status_ids
            pos_ids = positive_status_ids(active_set)
            
            eligible = [dict(r) for r in rsvps if r["status"] in pos_ids]
            
            if not eligible:
                await interaction.followup.send(t("ERR_ATT_NO_RSVPS", guild_id=guild_id), ephemeral=True)
                return
                
            view = AttendanceView(self.bot, event_id, eligible, guild_id, title=db_event.get("title", t("LBL_EVENT", guild_id=guild_id)))
            await view.build()
            
            # Send using followup (since we deferred)
            log.info(f"[Attendance Debug] COMMAND SUCCESS: Sending View")
            await interaction.followup.send(view=view, ephemeral=True)
            
        except Exception as e:
            import traceback
            log.error(f"[Attendance] Command Error: {e}\n{traceback.format_exc()}")
            try:
                await interaction.followup.send(f"{emojis.ERROR} {t('ERR_WIZARD_GENERAL', guild_id=guild_id).replace('{e}', str(e))}", ephemeral=True)
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
