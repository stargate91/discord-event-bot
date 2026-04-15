import discord
from discord.ext import commands
from discord import app_commands, ui
import database
from database import DEFAULT_TIMEZONE
import time
import uuid
import datetime
import json
# imports moved inside methods to prevent circular dependency
from utils.i18n import t
from dateutil import parser
from dateutil import tz
from utils.auth import is_admin, is_master
from utils.logger import log
from utils import emojis
from utils.emoji_utils import make_button, make_select_option

# We load the config for command suffixes
from utils.config import config
SUFFIX = config.command_suffix
EVENTS_CONFIG = config.get("events_config", [])



class MyEventsView(ui.LayoutView):
    def __init__(self, bot, guild_id, user_id, events):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.events = events
        self.page = 0
        self.per_page = 3

    async def build(self):
        self.clear_items()
        
        start = self.page * self.per_page
        end = start + self.per_page
        slice = self.events[start:end]
        
        for ev in slice:
            title = ev["title"] or "Unnamed Event"
            st = ev["start_time"]
            eid = ev["event_id"]
            cid = ev["channel_id"]
            mid = ev["message_id"]
            creator_id = ev["creator_id"]
            status_raw = ev["user_status"]
            
            # Container with accent color (Gold for Organizer, Blue for Participant)
            accent = 0xFFD700 if int(creator_id) == self.user_id else 0x5865F2
            container = ui.Container(accent_color=accent)
            
            # Content
            time_rel = f"<t:{int(st)}:R>" if st else t("LBL_LOBBY_LIST_NO_START", guild_id=self.guild_id)
            container.add_item(ui.TextDisplay(
                f"📅 **{title}**\nID: `{eid}` | {time_rel}"
            ))
            
            if int(creator_id) == self.user_id:
                state_text = f"👑 **{t('LBL_ORGANIZER', guild_id=self.guild_id)}**"
            else:
                state_text = f"✨ {str(status_raw).capitalize()}"
                
            status_lbl = t("LBL_STATUS", guild_id=self.guild_id) or "Status"
            container.add_item(ui.TextDisplay(
                f"**{status_lbl}:** {state_text}"
            ))
            
            self.add_item(container)
            
            # Link button
            link = f"https://discord.com/channels/{self.guild_id}/{cid}/{mid}"
            self.add_item(make_button(
                label=t("BTN_GO_TO_EVENT", guild_id=self.guild_id) or "View",
                url=link,
                style=discord.ButtonStyle.link
            ))

        # Pagination controls
        if len(self.events) > self.per_page:
            prev_btn = make_button(label="⬅️", style=discord.ButtonStyle.secondary, disabled=(self.page == 0))
            async def prev_cb(it):
                self.page -= 1
                await self.build()
                await it.response.edit_message(view=self)
            prev_btn.callback = prev_cb
            
            next_btn = make_button(label="➡️", style=discord.ButtonStyle.secondary, disabled=(end >= len(self.events)))
            async def next_cb(it):
                self.page += 1
                await self.build()
                await it.response.edit_message(view=self)
            next_btn.callback = next_cb
            
            self.add_item(prev_btn)
            self.add_item(next_btn)

class EventHistoryView(ui.LayoutView):
    def __init__(self, bot, guild_id, user_id, events):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.events = events
        self.page = 0
        self.per_page = 3

    async def build(self):
        self.clear_items()
        
        start = self.page * self.per_page
        end = start + self.per_page
        slice = self.events[start:end]
        
        for ev in slice:
            title = ev["title"] or "Unnamed Event"
            st = ev["start_time"]
            eid = ev["event_id"]
            cid = ev["channel_id"]
            mid = ev["message_id"]
            creator_id = ev["creator_id"]
            status_raw = ev["user_status"]
            attendance = ev["attendance"]
            
            # Container (Gold for Organized, Gray for Joined)
            is_creator = int(creator_id) == self.user_id
            accent = 0xFFD700 if is_creator else 0x99AAB5
            container = ui.Container(accent_color=accent)
            
            # Content
            time_str = f"<t:{int(st)}:d> (<t:{int(st)}:R>)" if st else "Past event"
            title_prefix = "👑" if is_creator else "📅"
            container.add_item(ui.TextDisplay(
                f"{title_prefix} **{title}**\n{time_str}"
            ))
            
            if is_creator:
                res_text = f"👑 {t('LBL_ORGANIZER', guild_id=self.guild_id)}"
            else:
                if attendance == "present":
                    res_text = f"✅ {t('LBL_PRESENT', guild_id=self.guild_id) or 'Present'}"
                elif attendance == "no_show":
                    res_text = f"❌ {t('LBL_NOSHOW', guild_id=self.guild_id) or 'No-show'}"
                else:
                    res_text = f"✨ {str(status_raw).capitalize()}"
                
            res_lbl = t("LBL_RESULT", guild_id=self.guild_id) or "Result"
            container.add_item(ui.TextDisplay(
                f"**{res_lbl}:** {res_text}"
            ))
            
            self.add_item(container)
            
            # Link button
            link = f"https://discord.com/channels/{self.guild_id}/{cid}/{mid}"
            self.add_item(make_button(
                label=t("BTN_GO_TO_EVENT", guild_id=self.guild_id) or "View",
                url=link,
                style=discord.ButtonStyle.link
            ))

        # Pagination controls
        if len(self.events) > self.per_page:
            prev_btn = make_button(label="⬅️", style=discord.ButtonStyle.secondary, disabled=(self.page == 0))
            async def prev_cb(it):
                self.page -= 1
                await self.build()
                await it.response.edit_message(view=self)
            prev_btn.callback = prev_cb
            
            next_btn = make_button(label="➡️", style=discord.ButtonStyle.secondary, disabled=(end >= len(self.events)))
            async def next_cb(it):
                self.page += 1
                await self.build()
                await it.response.edit_message(view=self)
            next_btn.callback = next_cb
            
            self.add_item(prev_btn)
            self.add_item(next_btn)

class EventCommands(commands.Cog):
    """Cog for general event management commands."""
    
    event_group = app_commands.Group(name="event", description="Event management commands")
    
    # --- CLEANUP: Master Hub logic moved to MasterCommands Cog ---

    def __init__(self, bot):
        self.bot = bot





    @event_group.command(name="create", description="Start the interactive event creation wizard")
    async def create_event(self, interaction: discord.Interaction):
        from cogs.event_wizard import WizardStartView
        from utils.i18n import load_guild_translations
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        await load_guild_translations(guild_id)
        
        if not await is_admin(interaction):
            await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
            return

        try:
            view = WizardStartView(self.bot, interaction.user.id, guild_id=guild_id)
            await view.refresh_message(interaction)
        except Exception as e:
            log.error(f"Error starting wizard: {e}")
            await interaction.followup.send(f"{t('ERR_CRITICAL_WIZARD', guild_id=interaction.guild_id)}: `{e}`", ephemeral=True)

    @event_group.command(name="lobby", description="Create a fill-to-start lobby event (no fixed time until full)")
    async def create_lobby_event(self, interaction: discord.Interaction):
        from cogs.event_wizard import EventWizardView
        from utils.i18n import load_guild_translations

        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        await load_guild_translations(guild_id)

        if not await is_admin(interaction):
            await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
            return

        try:
            view = EventWizardView(
                self.bot,
                interaction.user.id,
                guild_id=guild_id,
                wizard_type="lobby",
            )
            await view.refresh_message(interaction)
        except Exception as e:
            log.error(f"Error starting lobby wizard: {e}")
            await interaction.followup.send(
                f"{t('ERR_CRITICAL_WIZARD', guild_id=interaction.guild_id)}: `{e}`", ephemeral=True
            )

    @event_group.command(name="edit", description="Edit an existing event")
    @app_commands.describe(
        event_id="The short ID or series name of the event to edit",
        occurrence="Optional: which occurrence number of a series to edit (1, 2, 3...)"
    )
    async def edit_event(self, interaction: discord.Interaction, event_id: str, occurrence: int = None):
        from cogs.event_wizard import EventWizardView
        from utils.i18n import load_guild_translations
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        await load_guild_translations(guild_id)
        
        if not await is_admin(interaction):
            await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
            return
            
        db_event = None
        bulk_ids = None

        if event_id.startswith("series:"):
            config_name = event_id.replace("series:", "")
            series_events = await database.get_active_events_by_config(config_name, interaction.guild_id)
            if not series_events:
                await interaction.followup.send(
                    t("ERR_EV_NOT_FOUND", guild_id=guild_id), ephemeral=True
                )
                return
            
            if occurrence is not None:
                if occurrence > len(series_events): 
                    return await interaction.followup.send(t("ERR_SERIES_COUNT", guild_id=interaction.guild_id, occurrence=occurrence), ephemeral=True)
                db_event = series_events[occurrence - 1]
            else:
                db_event = series_events[0]
                bulk_ids = [ev['event_id'] for ev in series_events]
        else:
            db_event = await database.get_active_event(event_id)

        if db_event:
            db_event = dict(db_event)

        if not db_event:
            await interaction.followup.send(
                t("ERR_EV_NOT_FOUND", guild_id=interaction.guild_id), ephemeral=True
            )
            return

        try:
            config_name = db_event.get("config_name")
            if db_event.get("lobby_mode"):
                wtype = "lobby"
            else:
                wtype = "single" if not config_name or config_name == "manual" else "series"
            from cogs.event_wizard import EventWizardView
            view = EventWizardView(self.bot, interaction.user.id, existing_data=db_event, is_edit=True, guild_id=interaction.guild_id, bulk_ids=bulk_ids, wizard_type=wtype)
            await view.refresh_message(interaction)
        except Exception as e:
            log.error(f"Error starting edit wizard: {e}")
            await interaction.followup.send(f"{t('ERR_CRITICAL_EDIT', guild_id=interaction.guild_id)}: `{e}`", ephemeral=True)

    @edit_event.autocomplete("event_id")
    async def edit_event_autocomplete(self, interaction: discord.Interaction, current: str):
        active_events = await database.get_all_active_events(interaction.guild_id)
        series = {}
        single_events = []
        for ev in active_events:
            cfg = ev.get('config_name')
            if cfg and cfg != 'manual':
                if cfg not in series: series[cfg] = []
                series[cfg].append(ev)
            else:
                single_events.append(ev)

        results = []
        q = current.lower()
        
        for config_name, evs in series.items():
            title = evs[0].get("title", config_name)
            if q and q not in title.lower() and q not in config_name.lower():
                continue
            label = t("LBL_SERIES_AUTOCOMPLETE", guild_id=interaction.guild_id, title=title, count=len(evs))
            results.append(discord.app_commands.Choice(name=label[:100], value=f"series:{config_name}"))
        
        for ev in single_events:
            title = ev.get('title') or 'Unnamed'
            eid = ev['event_id']
            if q and q not in title.lower() and q not in eid.lower():
                continue
            label = t("LBL_EVENT_AUTOCOMPLETE", guild_id=interaction.guild_id, title=title, id=eid)
            results.append(discord.app_commands.Choice(name=label[:100], value=eid))
        return results[:25]

    @event_group.command(name="list", description="Show all active events")
    async def list_events(self, interaction: discord.Interaction):
        if not await is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return

        events = await database.get_all_active_events(interaction.guild_id)
        if not events: return await interaction.response.send_message(t("ERR_NO_ACTIVE_EVENTS", guild_id=interaction.guild_id), ephemeral=True)

        text = t("LBL_ACTIVE_EVENTS_LIST", guild_id=interaction.guild_id) + "\n"
        for ev in events:
            title = ev.get('title') or ev.get('config_name') or "Unnamed"
            st = ev.get("start_time")
            if st is not None:
                text += f"- `{ev['event_id']}`: {title} (<t:{int(st)}:R>)\n"
            else:
                text += f"- `{ev['event_id']}`: {title} ({t('LBL_LOBBY_LIST_NO_START', guild_id=interaction.guild_id)})\n"
        await interaction.response.send_message(text, ephemeral=True)

    @event_group.command(name="cancel", description="Mark an event as CANCELLED")
    async def cancel_event(self, interaction: discord.Interaction, event_id: str, notify: str = "none", occurrence: int = None):
        await self._handle_status_change(interaction, event_id, "cancelled", notify, occurrence)

    @event_group.command(name="postpone", description="Mark an event as POSTPONED")
    async def postpone_event(self, interaction: discord.Interaction, event_id: str, new_time: str = None, notify: str = "none", occurrence: int = None):
        await self._handle_status_change(interaction, event_id, "postponed", notify, occurrence, new_time)

    @event_group.command(name="activate", description="Set a cancelled/postponed event back to ACTIVE")
    async def activate_event(self, interaction: discord.Interaction, event_id: str, occurrence: int = None):
        await self._handle_status_change(interaction, event_id, "active", "none", occurrence)

    @event_group.command(name="sheets", description="Export all event data to CSV for Google Sheets")
    async def sheets_export(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        from utils.i18n import load_guild_translations
        await load_guild_translations(guild_id)
        
        if not await is_admin(interaction):
            return await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
            
        try:
            import io
            import csv
            import datetime
            
            # Fetch Data
            events = await database.get_guild_events_export(guild_id)
            rsvps = await database.get_guild_rsvps_export(guild_id)
            
            # 1. Events Summary CSV
            e_buffer = io.StringIO()
            e_writer = csv.writer(e_buffer)
            # Headers
            e_writer.writerow(["Event ID", "Title", "Creator ID", "Start Time", "Status", "Template", "Total RSVPs", "No-shows"])
            for e in events:
                st = datetime.datetime.fromtimestamp(e["start_time"]).strftime("%Y-%m-%d %H:%M") if e["start_time"] else "Lobby"
                e_writer.writerow([e["event_id"], e["title"], e["creator_id"], st, e["status"], e["config_name"], e["total_rsvps"], e.get("no_shows", 0)])
            
            e_buffer.seek(0)
            e_file = discord.File(e_buffer, filename=f"events_summary_{guild_id}.csv")
            
            # 2. RSVPs Details CSV
            r_buffer = io.StringIO()
            r_writer = csv.writer(r_buffer)
            r_writer.writerow(["Event Title", "User ID", "Status", "Joined At", "Attendance"])
            for r in rsvps:
                ja = datetime.datetime.fromtimestamp(r["joined_at"]).strftime("%Y-%m-%d %H:%M") if r["joined_at"] else ""
                r_writer.writerow([r["event_title"], r["user_id"], r["status"], ja, r["attendance"]])
                
            r_buffer.seek(0)
            r_file = discord.File(r_buffer, filename=f"rsvps_details_{guild_id}.csv")
            
            await interaction.followup.send(
                t("MSG_SHEETS_EXPORT_READY", guild_id=guild_id),
                files=[e_file, r_file],
                ephemeral=True
            )
            
        except Exception as ex:
            log.error(f"Sheets export error: {ex}")
            await interaction.followup.send(f"Error: {ex}", ephemeral=True)

    @event_group.command(name="ics", description="Export all future events to a .ics calendar file")
    async def ics_export(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        from utils.i18n import load_guild_translations
        await load_guild_translations(guild_id)
        
        try:
            import io
            from utils.calendar_utils import generate_ics_batch
            
            # Fetch active events
            events = await database.get_all_active_events(guild_id)
            if not events:
                return await interaction.followup.send(t("ERR_NO_ACTIVE_EVENTS", guild_id=guild_id), ephemeral=True)
            
            now = time.time()
            # Include events starting within the last 24h as well for safety
            future_events = [e for e in events if (e["start_time"] or 0) > (now - 86400)]
            
            if not future_events:
                return await interaction.followup.send(t("ERR_NO_ACTIVE_EVENTS", guild_id=guild_id), ephemeral=True)

            ics_text = generate_ics_batch(future_events)
            
            buffer = io.BytesIO(ics_text.encode("utf-8"))
            ics_file = discord.File(buffer, filename=f"events_{guild_id}.ics")
            
            await interaction.followup.send(
                t("MSG_ICS_EXPORT_READY", guild_id=guild_id),
                file=ics_file,
                ephemeral=True
            )
            
        except Exception as ex:
            log.error(f"ICS export error: {ex}")
            await interaction.followup.send(f"Error: {ex}", ephemeral=True)

    @event_group.command(name="my-events", description="List all events you are organizing or attending")
    async def my_events(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        user_id = interaction.user.id
        from utils.i18n import load_guild_translations
        await load_guild_translations(guild_id)
        
        try:
            events = await database.get_user_active_events(guild_id, user_id)
            if not events:
                return await interaction.followup.send(t("MSG_NO_MY_EVENTS", guild_id=guild_id), ephemeral=True)
            
            view = MyEventsView(self.bot, guild_id, user_id, events)
            await view.build()
            await interaction.followup.send(view=view, ephemeral=True)
            
        except Exception as ex:
            log.error(f"My events error: {ex}")
            await interaction.followup.send(f"Error: {ex}", ephemeral=True)

    @event_group.command(name="end", description="Manually close an active event and move it to history")
    @app_commands.describe(event_id="The ID of the event to close")
    async def event_end(self, interaction: discord.Interaction, event_id: str):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            
        await database.set_event_status(event_id, "closed")
        await interaction.response.send_message(f"✅ Event `{event_id}` has been closed and moved to history.", ephemeral=True)

    @event_end.autocomplete("event_id")
    async def end_autocomplete(self, interaction: discord.Interaction, current: str):
        events = await database.get_endable_events(interaction.guild_id)
        return [
            app_commands.Choice(name=f"{ev['title']} ({ev['event_id']})", value=ev["event_id"])
            for ev in events if current.lower() in ev["title"].lower() or current.lower() in ev["event_id"].lower()
        ][:25]

    @event_group.command(name="history", description="View your past event participation")
    async def event_history(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        user_id = interaction.user.id
        from utils.i18n import load_guild_translations
        await load_guild_translations(guild_id)
        
        try:
            events = await database.get_user_event_history(guild_id, user_id)
            if not events:
                return await interaction.followup.send(t("MSG_NO_HISTORY", guild_id=guild_id), ephemeral=True)
            
            view = EventHistoryView(self.bot, guild_id, user_id, events)
            await view.build()
            await interaction.followup.send(view=view, ephemeral=True)
            
        except Exception as ex:
            log.error(f"Event history error: {ex}")
            await interaction.followup.send(f"Error: {ex}", ephemeral=True)

    async def _handle_status_change(self, interaction, event_id, status, notify_type, occurrence, new_time=None):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        db_event = None
        if event_id.startswith("series:"):
            config_name = event_id.replace("series:", "")
            series_events = await database.get_active_events_by_config(config_name, interaction.guild_id)
            if series_events:
                db_event = series_events[0]
                event_id = db_event["event_id"]
        else:
            db_event = await database.get_active_event(event_id, interaction.guild_id)
            if not db_event:
                db_event = await database.get_active_event(event_id)

        if not db_event:
            return await interaction.followup.send(
                t("ERR_EV_NOT_FOUND", guild_id=interaction.guild_id), ephemeral=True
            )

        if status == "postponed" and new_time:
            try:
                local_tz = tz.gettz(DEFAULT_TIMEZONE)
                dt = parser.parse(new_time).replace(tzinfo=local_tz)
                await database.update_event_time(event_id, dt.timestamp())
            except Exception as e:
                return await interaction.followup.send(t("ERR_INVALID_TIME", guild_id=interaction.guild_id, e=e), ephemeral=True)

        series_events = await database.get_active_events_by_config(db_event["config_name"], interaction.guild_id) if db_event.get("config_name") and db_event["config_name"] != "manual" else []
        if len(series_events) > 1 and not occurrence:
            from cogs.event_ui import StatusChoiceView
            msg = t("MSG_SERIES_STATUS_CONFIRM", guild_id=interaction.guild_id, status=status)
            view = StatusChoiceView(self.bot, event_id, db_event, series_events, status, notify_type)
            return await interaction.followup.send(msg, view=view, ephemeral=True)

        await database.update_event_status(event_id, status)
        await interaction.followup.send(t("MSG_STATUS_UPDATED", guild_id=interaction.guild_id, status=status), ephemeral=True)

    @cancel_event.autocomplete("event_id")
    @postpone_event.autocomplete("event_id")
    @activate_event.autocomplete("event_id")
    async def status_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.edit_event_autocomplete(interaction, current)

    @event_group.command(name="remove", description="Delete an active event message")
    async def remove_event(self, interaction: discord.Interaction, event_id: str):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
        
        log.info(f"[Remove] Looking for event_id={event_id!r} guild_id={interaction.guild_id!r}")
        
        target_events = []
        if event_id.startswith("series:"):
            config_name = event_id.replace("series:", "")
            target_events = await database.get_active_events_by_config(config_name, interaction.guild_id)
        else:
            db_event = await database.get_active_event(event_id, interaction.guild_id)
            if not db_event:
                db_event = await database.get_active_event(event_id)
            if db_event:
                target_events = [db_event]

        if not target_events:
            all_events = await database.get_active_events(interaction.guild_id)
            all_ids = [e["event_id"] for e in all_events]
            log.warning(f"[Remove] Not found! All event IDs in guild: {all_ids}")
            return await interaction.response.send_message(t("ERR_EV_NOT_FOUND", guild_id=interaction.guild_id), ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)

        for ev in target_events:
            eid = ev["event_id"]
            
            # Update the live card to show DELETED status
            msg_id = ev.get("message_id")
            chan_id = ev.get("channel_id")
            if msg_id and chan_id:
                try:
                    channel = self.bot.get_channel(int(chan_id))
                    if channel:
                        msg = await channel.fetch_message(int(msg_id))
                        if msg:
                            from cogs.event_ui import DynamicEventView
                            ev_conf = dict(ev)
                            ev_conf["status"] = "deleted"
                            view = DynamicEventView(self.bot, eid, ev_conf)
                            await view.prepare()
                            # Disable all buttons
                            for child in view.children:
                                if isinstance(child, discord.ui.Container):
                                    for row in child.children:
                                        if isinstance(row, discord.ui.ActionRow):
                                            for item in row.children:
                                                if isinstance(item, discord.ui.Button):
                                                    item.disabled = True
                            await msg.edit(view=view)
                except Exception as e:
                    log.warning(f"[Remove] Could not update card for {eid}: {e}")

            # Role cleanup
            temp_role_id = ev.get("temp_role_id")
            if temp_role_id:
                guild = interaction.guild
                if guild:
                    if not guild.me.guild_permissions.manage_roles:
                        log.warning(f"[Remove] Missing 'Manage Roles' permission to delete role {temp_role_id} in guild {guild.id}")
                    else:
                        try:
                            role = guild.get_role(int(temp_role_id))
                            if role:
                                await role.delete(reason=f"Event {eid} removed by {interaction.user}")
                                log.info(f"[Remove] Deleted temp role {temp_role_id} for event {eid}")
                        except Exception as e:
                            log.error(f"[Remove] Failed to delete role {temp_role_id}: {e}")

            await database.delete_active_event(eid, interaction.guild_id)
        
        await interaction.followup.send(t("MSG_EVENT_REMOVED", guild_id=interaction.guild_id), ephemeral=True)

    @remove_event.autocomplete("event_id")
    async def remove_event_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.edit_event_autocomplete(interaction, current)



    # --- PREFIXED COMMANDS (Sync/Clear) ---

    @commands.command(name="sync", aliases=["sync_nexus"])
    @commands.guild_only()
    async def sync_prefix(self, ctx: commands.Context, spec: str | None = None):
        if not await is_master(ctx):
            return await ctx.send(t("ERR_ADMIN_ONLY", guild_id=ctx.guild.id))
        
        await ctx.send(t("SYNC_START", guild_id=ctx.guild.id))
        try:
            if spec == "global":
                synced = await self.bot.tree.sync()
                await ctx.send(t("SYNC_GLOBAL_OK", guild_id=ctx.guild.id).replace("{count}", str(len(synced))))
            elif spec == "copy":
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await self.bot.tree.sync(guild=ctx.guild)
                await ctx.send(t("SYNC_COPY_OK", guild_id=ctx.guild.id).replace("{count}", str(len(synced))))
            else:
                synced = await self.bot.tree.sync(guild=ctx.guild)
                await ctx.send(t("SYNC_GUILD_OK", guild_id=ctx.guild.id).replace("{count}", str(len(synced))))
        except Exception as e:
            await ctx.send(t("SYNC_FAILED", guild_id=ctx.guild.id).replace("{e}", str(e)))

    @commands.command(name="clear_commands", aliases=["clear_commands_nexus"])
    @commands.guild_only()
    async def clear_commands_prefix(self, ctx: commands.Context):
        if not await is_master(ctx):
            return await ctx.send(t("ERR_ADMIN_ONLY", guild_id=ctx.guild.id))
        
        await ctx.send(t("SYNC_CLEAR_START", guild_id=ctx.guild.id))
        try:
            self.bot.tree.clear_commands(guild=None)
            await self.bot.tree.sync(guild=None)
            self.bot.tree.clear_commands(guild=ctx.guild)
            await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send(t("SYNC_CLEAR_SUCCESS", guild_id=ctx.guild.id).replace("{suffix}", SUFFIX))
        except Exception as e:
            await ctx.send(t("SYNC_FAILED", guild_id=ctx.guild.id).replace("{e}", str(e)))

class ReliabilityAuditView(ui.LayoutView):
    def __init__(self, bot, guild, stats, title="Reliability Audit"):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild = guild
        self.stats = stats # List of {user_id, noshow_count, total_past_rsvps}
        self.audit_title = title
        self.page = 0
        self.per_page = 10 

    async def build(self):
        self.clear_items()
        
        start = self.page * self.per_page
        end = start + self.per_page
        page_stats = self.stats[start:end]
        total_pages = math.ceil(len(self.stats) / self.per_page) if self.stats else 1
        
        container_items = [
            ui.TextDisplay(self.audit_title),
            ui.TextDisplay(f"-# {t('LBL_AUDIT_ENTRIES', guild_id=self.guild.id).replace('{count}', str(len(self.stats)))} • {t('LBL_PAGE', guild_id=self.guild.id)} {self.page + 1}/{total_pages}"),
            ui.Separator()
        ]
        
        for i, s in enumerate(page_stats):
            idx = (self.page * self.per_page) + i + 1
            uid = s["user_id"]
            ns = int(s["noshow_count"] or 0)
            tot = int(s["total_past_rsvps"] or 0)
            ratio = ns / tot if tot > 0 else 0
            
            # Resolve name
            member = self.guild.get_member(int(uid))
            if not member and self.guild:
                try: member = await self.guild.fetch_member(int(uid))
                except: pass
                
            name = member.display_name if member else t("LBL_USER_DEFAULT", guild_id=self.guild.id).replace("{uid}", str(uid))
            
            # Accessory Button for stats (side-by-side feel)
            status_label = f"{ns}/{tot} ({ratio*100:.1f}%)"
            style = discord.ButtonStyle.secondary
            if ns > 2: style = discord.ButtonStyle.danger
            elif ns > 0: style = discord.ButtonStyle.primary
            
            stat_btn = make_button(label=status_label, style=style, disabled=True)
            
            section = ui.Section(f"**{idx}. {name}**", accessory=stat_btn)
            container_items.append(section)

        main_container = ui.Container(*container_items, accent_color=0x40C4FF)
        self.add_item(main_container)
        
        # Navigation
        if total_pages > 1:
            prev_btn = make_button(label=emojis.BACK, style=discord.ButtonStyle.gray, disabled=(self.page == 0))
            next_btn = make_button(label=emojis.FORWARD, style=discord.ButtonStyle.gray, disabled=(self.page >= total_pages - 1))
            
            async def prev_cb(it):
                try: await it.response.defer()
                except: pass
                self.page -= 1
                await self.refresh(it)
            async def next_cb(it):
                try: await it.response.defer()
                except: pass
                self.page += 1
                await self.refresh(it)
                
            prev_btn.callback = prev_cb
            next_btn.callback = next_cb
            self.add_item(ui.ActionRow(prev_btn, next_btn))

    async def refresh(self, interaction: discord.Interaction):
        await self.build()
        log.info(f"[Audit Debug] REFRESH: Page {self.page}")
        await interaction.edit_original_response(view=self)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        import traceback
        log.error(f"[Audit View] Error: {error}\n{traceback.format_exc()}")
        try: 
            msg = t('ERR_WIZARD_GENERAL', guild_id=self.guild.id).replace('{e}', str(error))
            await interaction.followup.send(msg, ephemeral=True)
        except: pass

class AdminCommands(commands.GroupCog, name="admin"):
    """Cog for server administrators to manage server settings."""
    def __init__(self, bot):
        self.bot = bot

    check_group = app_commands.Group(name="check", description="Audit checks for administrators")

    @check_group.command(name="no-show", description="Check member reliability scores (no-shows)")
    @app_commands.describe(
        event_id="Check the reliability of all participants in a specific event",
        all_time="Show a global leaderboard of all users with no-shows in this guild"
    )
    async def admin_check_noshow(self, interaction: discord.Interaction, event_id: str = None, all_time: bool = False):
        # 1. DEFER (Safety First)
        await interaction.response.defer(ephemeral=True)
        
        log.info(f"[Audit Debug] START: event_id={event_id}, all_time={all_time}")
        
        guild_id = interaction.guild_id
        from utils.i18n import load_guild_translations
        await load_guild_translations(guild_id)
        
        if not await is_admin(interaction):
            return await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
            
        if not event_id and not all_time:
            return await interaction.followup.send(t("MSG_AUDIT_HINT", guild_id=guild_id), ephemeral=True)

        try:
            if event_id:
                # Mode A: Focus on specific event's participants
                stats = await database.get_event_reliability_audit(event_id, guild_id)
                title = t("LBL_AUDIT_TITLE_EVENT", guild_id=guild_id).replace("{event_id}", str(event_id))
                # For specific event, we show everyone to see who attended vs who didn't
                filtered_stats = stats 
            else:
                # Mode B: Global leaderboard
                stats = await database.get_guild_reliability_stats(guild_id, all_time=True)
                title = t("LBL_AUDIT_TITLE_GLOBAL", guild_id=guild_id)
                # For global leaderboard, only show those with at least 1 no-show
                filtered_stats = [s for s in stats if int(s.get("noshow_count") or 0) > 0]

            if not filtered_stats:
                return await interaction.followup.send(t("ERR_AUDIT_NO_DATA", guild_id=guild_id), ephemeral=True)
                
            view = ReliabilityAuditView(self.bot, interaction.guild, filtered_stats, title=title)
            await view.build()
            
            log.info(f"[Audit Debug] SUCCESS: Sending View with {len(filtered_stats)} rows")
            await interaction.followup.send(view=view, ephemeral=True)
            
        except Exception as e:
            import traceback
            log.error(f"[Audit] Command Error: {e}\n{traceback.format_exc()}")
            try: await interaction.followup.send(t('ERR_WIZARD_GENERAL', guild_id=guild_id).replace('{e}', str(e)), ephemeral=True)
            except: pass

    @admin_check_noshow.autocomplete("event_id")
    async def check_noshow_autocomplete(self, interaction: discord.Interaction, current: str):
        # List active events (usable cards)
        events = await database.get_all_active_events(interaction.guild_id)
        choices = []
        for e in events:
            label = f"{e['title']} ({e['event_id']})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=e['event_id']))
        return choices[:25]

    @app_commands.command(name="setup", description="Configure server-wide default values and admin settings")
    async def admin_setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        try:
            from utils.i18n import load_guild_translations
            await load_guild_translations(guild_id)
            
            if not await is_admin(interaction):
                return await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
                
            from cogs.server_setup import ServerSetupView
            view = ServerSetupView(self.bot, guild_id)
            await view.prepare(interaction)
            await interaction.followup.send(view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"{t('ERR_CRITICAL_SETUP', guild_id=interaction.guild_id)}: `{e}`", ephemeral=True)

    @app_commands.command(name="messages", description="Manage global bot messages and strings")
    async def admin_messages(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        try:
            from utils.i18n import load_guild_translations
            await load_guild_translations(guild_id)
            
            if not await is_admin(interaction):
                return await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
            
            from cogs.message_wizard import MessageWizardView
            view = MessageWizardView(self.bot, interaction.guild.id)
            await view.prepare(interaction)
            await interaction.followup.send(view=view, ephemeral=True)
        except Exception as e:
            from utils.logger import log
            log.error(f"Error in admin_messages: {e}")
            await interaction.followup.send(f"{t('ERR_CRITICAL_WIZARD', guild_id=interaction.guild_id)}: `{e}`", ephemeral=True)

    @app_commands.command(name="emojis", description="Manage customized emoji sets for this server")
    async def manage_emojis(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        try:
            from utils.i18n import load_guild_translations
            await load_guild_translations(guild_id)
            
            if not await is_admin(interaction):
                return await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
            
            from cogs.emoji_wizard import EmojiWizardView
            view = EmojiWizardView(self.bot, interaction.guild_id)
            await view.refresh_message(interaction)
        except Exception as e:
            await interaction.followup.send(f"{t('ERR_CRITICAL_EMOJI', guild_id=interaction.guild_id)}: `{e}`", ephemeral=True)

    @app_commands.command(name="reset", description="WIPE ALL DATA for this server")
    async def reset(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        from utils.i18n import load_guild_translations
        await load_guild_translations(guild_id)
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)

        view = ui.View()
        confirm_btn = make_button(label=t("BTN_RESET_CONFIRM", guild_id=guild_id), style=discord.ButtonStyle.danger)
        cancel_btn = make_button(label=t("BTN_CANCEL", guild_id=guild_id), style=discord.ButtonStyle.secondary)

        async def confirm_callback(it: discord.Interaction):
            try:
                await database.reset_guild_data(it.guild.id)
                await it.response.send_message(t("MSG_RESET_SUCCESS", guild_id=it.guild_id), ephemeral=True)
            except Exception as e:
                await it.response.send_message(f"{t('ERR_RESET_FAILED', guild_id=it.guild_id)}: `{e}`", ephemeral=True)

        async def cancel_callback(it: discord.Interaction):
            await it.response.send_message(t("MSG_RESET_CANCELLED", guild_id=it.guild_id), ephemeral=True)

        confirm_btn.callback = confirm_callback
        cancel_btn.callback = cancel_callback
        view.add_item(confirm_btn); view.add_item(cancel_btn)
        await interaction.response.send_message(t("MSG_RESET_WARNING", guild_id=guild_id), view=view, ephemeral=True)

class DraftCommands(commands.GroupCog, name="draft"):
    """Cog for users to manage their event drafts."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="continue", description="Finish an event you started earlier")
    async def continue_draft(self, interaction: discord.Interaction, draft_id: str):
        await interaction.response.defer(ephemeral=True)
        record = await database.get_draft(draft_id, interaction.guild_id)
        if not record: 
            return await interaction.followup.send(t("ERR_DRAFT_NOT_FOUND"), ephemeral=True)
        
        # Extract the actual draft data from the JSONB column
        data = record["data"]
        if isinstance(data, str):
            import json
            data = json.loads(data)

        from cogs.event_wizard import EventWizardView
        view = EventWizardView(self.bot, interaction.user.id, existing_data=data, guild_id=interaction.guild_id)
        await view.refresh_message(interaction)


    @continue_draft.autocomplete("draft_id")
    async def continue_draft_autocomplete(self, interaction: discord.Interaction, current: str):
        drafts = await database.get_user_drafts(interaction.guild_id, interaction.user.id)
        choices = []
        for d in drafts:
            label = f"{d['title']} ({d['draft_id']})"
            if current.lower() in label.lower(): choices.append(app_commands.Choice(name=label, value=d['draft_id']))
        return choices[:25]

    @app_commands.command(name="delete", description="Delete one of your drafts")
    async def delete_draft_cmd(self, interaction: discord.Interaction, draft_id: str):
        await database.delete_draft(draft_id, interaction.guild_id)
        await interaction.response.send_message(t("MSG_DRAFT_DELETED"), ephemeral=True)

    @delete_draft_cmd.autocomplete("draft_id")
    async def delete_draft_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.continue_draft_autocomplete(interaction, current)

    @app_commands.command(name="delete-all", description="Delete all your drafts at once")
    async def delete_all_drafts(self, interaction: discord.Interaction):
        await database.delete_all_user_drafts(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(t("MSG_DRAFTS_CLEARED"), ephemeral=True)

async def setup(bot):
    await bot.add_cog(EventCommands(bot))
    await bot.add_cog(AdminCommands(bot))
    await bot.add_cog(DraftCommands(bot))
