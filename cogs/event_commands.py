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
from utils.auth import is_admin
from utils.logger import log

# We load the config for command suffixes
try:
    from utils.jsonc import load_jsonc
    config_data = load_jsonc('config.json')
    SUFFIX = config_data.get("command_suffix", "")
    EVENTS_CONFIG = config_data.get("events_config", [])
except Exception:
    SUFFIX = ""
    EVENTS_CONFIG = []


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
            await interaction.followup.send(f"❌ {t('ERR_CRITICAL_WIZARD', guild_id=interaction.guild_id)}: `{e}`", ephemeral=True)

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
                await interaction.followup.send(t("ERR_EV_NOT_FOUND"), ephemeral=True)
                return
            
            if occurrence is not None:
                if occurrence > len(series_events): 
                    return await interaction.response.send_message(t("ERR_SERIES_COUNT", guild_id=interaction.guild_id, occurrence=occurrence), ephemeral=True)
                db_event = series_events[occurrence - 1]
            else:
                db_event = series_events[0]
                bulk_ids = [ev['event_id'] for ev in series_events]
        else:
            db_event = await database.get_active_event(event_id)

        if not db_event:
            await interaction.followup.send(t("ERR_EV_NOT_FOUND"), ephemeral=True)
            return

        try:
            config_name = db_event.get("config_name")
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
        for config_name, evs in series.items():
            title = evs[0].get("title", config_name)
            label = t("LBL_SERIES_AUTOCOMPLETE", guild_id=interaction.guild_id, title=title, count=len(evs))
            results.append(discord.app_commands.Choice(name=label[:100], value=f"series:{config_name}"))
        
        for ev in single_events:
            label = t("LBL_EVENT_AUTOCOMPLETE", guild_id=interaction.guild_id, title=ev.get('title') or 'Unnamed', id=ev['event_id'])
            results.append(discord.app_commands.Choice(name=label[:100], value=ev["event_id"]))
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
            text += f"- `{ev['event_id']}`: {title} (<t:{int(ev['start_time'])}:R>)\n"
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

        if not db_event: return await interaction.followup.send(t("ERR_EV_NOT_FOUND"), ephemeral=True)

        if status == "postponed" and new_time:
            try:
                local_tz = tz.gettz(DEFAULT_TIMEZONE)
                dt = parser.parse(new_time).replace(tzinfo=local_tz)
                await database.update_event_time(event_id, dt.timestamp())
            except Exception as e:
                return await interaction.response.send_message(t("ERR_INVALID_TIME", guild_id=interaction.guild_id, e=e), ephemeral=True)

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
        
        for ev in target_events:
            eid = ev["event_id"]
            
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
        
        await interaction.response.send_message(t("MSG_EVENT_REMOVED", guild_id=interaction.guild_id), ephemeral=True)

    @remove_event.autocomplete("event_id")
    async def remove_event_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.edit_event_autocomplete(interaction, current)

    @event_group.command(name="continue-draft", description="Finish an event you started earlier")
    async def continue_draft(self, interaction: discord.Interaction, draft_id: str):
        data = await database.get_draft(draft_id, interaction.guild_id)
        if not data: return await interaction.response.send_message(t("ERR_DRAFT_NOT_FOUND"), ephemeral=True)
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

    @event_group.command(name="delete-draft", description="Delete one of your drafts")
    async def delete_draft_cmd(self, interaction: discord.Interaction, draft_id: str):
        await database.delete_draft(draft_id, interaction.guild_id)
        await interaction.response.send_message(t("MSG_DRAFT_DELETED"), ephemeral=True)

    @delete_draft_cmd.autocomplete("draft_id")
    async def delete_draft_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.continue_draft_autocomplete(interaction, current)

    @event_group.command(name="delete-all-drafts", description="Delete all your drafts at once")
    async def delete_all_drafts(self, interaction: discord.Interaction):
        await database.delete_all_user_drafts(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(t("MSG_DRAFTS_CLEARED"), ephemeral=True)


    # --- PREFIXED COMMANDS (Sync/Clear) ---

    @commands.command(name="sync", aliases=["sync_nexus"])
    @commands.guild_only()
    async def sync_prefix(self, ctx: commands.Context, spec: str | None = None):
        if not await is_admin(ctx):
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
        if not await is_admin(ctx):
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

class AdminCommands(commands.GroupCog, name="admin"):
    """Cog for server administrators to manage server settings."""
    def __init__(self, bot):
        self.bot = bot

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
            await view.refresh_message(interaction)
        except Exception as e:
            await interaction.response.send_message(f"{t('ERR_CRITICAL_SETUP', guild_id=interaction.guild_id)}: `{e}`", ephemeral=True)

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
            await view.prepare()
            
            embed = discord.Embed(
                title=t("MSG_WIZ_TITLE", guild_id=interaction.guild_id),
                description=t("MSG_WIZ_DESC", guild_id=interaction.guild_id),
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            from utils.logger import log
            log.error(f"Error in admin_messages: {e}")
            await interaction.followup.send(f"❌ {t('ERR_CRITICAL_WIZARD', guild_id=interaction.guild_id)}: `{e}`", ephemeral=True)

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
        confirm_btn = ui.Button(label=t("BTN_RESET_CONFIRM", guild_id=guild_id), style=discord.ButtonStyle.danger)
        cancel_btn = ui.Button(label=t("BTN_CANCEL", guild_id=guild_id), style=discord.ButtonStyle.secondary)

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

async def setup(bot):
    await bot.add_cog(EventCommands(bot))
    await bot.add_cog(AdminCommands(bot))
