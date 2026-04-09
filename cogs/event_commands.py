import discord
from discord.ext import commands
from discord import app_commands
import database
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

# We load the config to know things like command suffixes and admin roles
try:
    from utils.jsonc import load_jsonc
    config_data = load_jsonc('config.json')
    SUFFIX = config_data.get("command_suffix", "")
    EVENTS_CONFIG = config_data.get("events_config", [])
    ADMIN_CHANNEL_ID = config_data.get("admin_channel_id")
    ADMIN_ROLE_ID = config_data.get("admin_role_id")
except Exception:
    SUFFIX = ""
    EVENTS_CONFIG = []
    ADMIN_CHANNEL_ID = None
    ADMIN_ROLE_ID = None


class EventCommands(commands.GroupCog, name="event"):
    # Subgroup for administrative tasks
    admin_group = app_commands.Group(name="admin", description="Administrative commands for server managers")
    # Subgroup for Bot Owner / System tasks
    master_group = app_commands.Group(name="master", description="System-level commands for the Bot Owner")

    def __init__(self, bot):
        self.bot = bot

    @master_group.command(name="status", description="Manage the global bot presence status list")
    async def master_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self.bot.is_owner(interaction.user):
            return await interaction.followup.send("❌ Ez a parancs csak a Bot Owner számára érhető el.", ephemeral=True)

        presence_json = await database.get_global_setting("bot_presence_list")
        presence_list = json.loads(presence_json) if presence_json else []

        embed = discord.Embed(
            title="🛠️ Global Presence Manager",
            description="Itt kezelheted a bot státusz üzeneteit. Ezek pörögnek minden szerveren.",
            color=discord.Color.dark_red()
        )
        
        status_text = "\n".join([f"• {s}" for s in presence_list]) or "*Nincs egyedi státusz beállítva.*"
        embed.add_field(name="Jelenlegi státuszok", value=status_text, inline=False)
        embed.set_footer(text="Használd a gombokat a lista módosításához.")

        view = MasterPresenceView(presence_list)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @admin_group.command(name="emojis", description="Manage server emoji sets via visual wizard")
    async def admin_emojis(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        from utils.i18n import load_guild_translations
        await load_guild_translations(guild_id)
        
        if not await is_admin(interaction):
            return await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
        
        from cogs.emoji_wizard import EmojiWizardView
        view = EmojiWizardView(self.bot, interaction.guild_id)
        embed = discord.Embed(
            title="✨ Emoji & Role Kezelő",
            description="Itt hozhatsz létre és módosíthatsz egyedi ikon-készleteket az eseményekhez.",
            color=discord.Color.purple()
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @admin_group.command(name="messages", description="Manage global bot messages and strings")
    async def admin_messages(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        from utils.i18n import load_guild_translations
        await load_guild_translations(guild_id)
        
        if not await is_admin(interaction):
            return await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
        
        from cogs.message_wizard import MessageWizardView
        view = MessageWizardView(self.bot, interaction.guild_id)
        embed = discord.Embed(
            title="💬 Message Wizard",
            description="Válaszd ki a kategóriát és a szöveget, amit módosítani szeretnél.",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @admin_group.command(name="setup", description="Configure server-wide default values and admin settings")
    async def admin_setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        from utils.i18n import load_guild_translations
        await load_guild_translations(guild_id)
        
        if not await is_admin(interaction):
            return await interaction.followup.send(t("ERR_ADMIN_ONLY", guild_id=guild_id), ephemeral=True)
            
        from cogs.server_setup import ServerSetupView
        view = ServerSetupView(self.bot, guild_id)
        embed = discord.Embed(
            title="⚙️ Server Setup & Defaults",
            description="Itt állíthatod be a szerver alapértelmezett értékeit (időzóna, színek, nyelv) és az admin jogosultságokat.",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="create", description="Start the interactive event creation wizard")
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
            embed = discord.Embed(
                title=t("WIZARD_TITLE", guild_id=guild_id), 
                description="Kérlek válaszd ki az esemény típusát az indításhoz!", 
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            log.error(f"Error in create_event: {e}", exc_info=True, guild_id=guild_id)
            await interaction.followup.send(f"❌ Hiba történt a varázsló megnyitásakor: `{e}`", ephemeral=True)

    @app_commands.command(name="edit", description="Edit an existing event")
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
                idx = occurrence - 1
                if 0 <= idx < len(series_events):
                    db_event = series_events[idx]
                else:
                    await interaction.followup.send(f"❌ Nincs ennyi ({occurrence}) aktív esemény ebben a sorozatban.", ephemeral=True)
                    return
            else:
                db_event = series_events[0]
                bulk_ids = [ev['event_id'] for ev in series_events]
        else:
            db_event = await database.get_active_event(event_id)

        if not db_event:
            await interaction.followup.send(t("ERR_EV_NOT_FOUND"), ephemeral=True)
            return

        local_tz = tz.gettz("Europe/Budapest")
        if db_event.get("start_time"):
            start_dt = datetime.datetime.fromtimestamp(db_event["start_time"], tz=local_tz)
            db_event["start_str"] = start_dt.strftime("%Y-%m-%d %H:%M")
        
        if db_event.get("end_time"):
            end_dt = datetime.datetime.fromtimestamp(db_event["end_time"], tz=local_tz)
            db_event["end_str"] = end_dt.strftime("%Y-%m-%d %H:%M")
        else:
            db_event["end_str"] = ""

        try:
            view = EventWizardView(self.bot, interaction.user.id, existing_data=db_event, is_edit=True, guild_id=interaction.guild_id, bulk_ids=bulk_ids)
            guild_id = interaction.guild_id
            title = t("WIZARD_TITLE", guild_id=guild_id)
            if bulk_ids: title = f"📦 {title} (TÖMEGES SZERKESZTÉS)"
            
            embed = discord.Embed(
                title=title, 
                description=t("WIZARD_DESC", guild_id=guild_id, status=view.get_status_text()), 
                color=discord.Color.gold()
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            log.error(f"Error in edit_event: {e}", exc_info=True, guild_id=guild_id)
            await interaction.followup.send(f"❌ Hiba történt a szerkesztő megnyitásakor: `{e}`", ephemeral=True)

    @edit_event.autocomplete("event_id")
    async def edit_event_autocomplete(self, interaction: discord.Interaction, current: str):
        active_events = await database.get_all_active_events(interaction.guild_id)
        groups = {}
        for ev in active_events:
            cfg = ev.get('config_name') or 'manual'
            if cfg not in groups: groups[cfg] = []
            groups[cfg].append(ev)

        choices = []
        for cfg, evs in groups.items():
            if cfg != 'manual':
                title = evs[0].get('title') or cfg
                label = f"📦 [SOROZAT] {title} ({len(evs)} aktív)"
                if current.lower() in label.lower(): choices.append(app_commands.Choice(name=label, value=f"series:{cfg}"))
            else:
                for ev in evs:
                    label = f"📝 {ev.get('title') or 'Unnamed'} ({ev['event_id']})"
                    if current.lower() in label.lower(): choices.append(app_commands.Choice(name=label, value=ev['event_id']))
        return choices[:25]

    @app_commands.command(name="list", description="Show all active events")
    async def list_events(self, interaction: discord.Interaction):
        if not await is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return

        events = await database.get_all_active_events(interaction.guild_id)
        if not events:
            await interaction.response.send_message("Nincsenek aktív események.", ephemeral=True)
            return

        text = "**Aktív események:**\n"
        for ev in events:
            title = ev.get('title') or ev.get('config_name') or "Unnamed"
            text += f"- `{ev['event_id']}`: {title} (<t:{int(ev['start_time'])}:R>)\n"
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="cancel", description="Mark an event as CANCELLED")
    @app_commands.describe(event_id="The short ID or series name", notify="How to notify participants", occurrence="Occurrence number for series")
    @app_commands.choices(notify=[app_commands.Choice(name="None", value="none"), app_commands.Choice(name="DM only", value="dm"), app_commands.Choice(name="Chat only", value="chat"), app_commands.Choice(name="Both DM and Chat", value="both")])
    async def cancel_event(self, interaction: discord.Interaction, event_id: str, notify: str = "none", occurrence: int = None):
        await self._handle_status_change(interaction, event_id, "cancelled", notify, occurrence)

    @app_commands.command(name="postpone", description="Mark an event as POSTPONED")
    @app_commands.describe(event_id="The short ID or series name", new_time="Optional new date/time (e.g. 2026-05-10 18:00)", notify="How to notify participants", occurrence="Occurrence number for series")
    @app_commands.choices(notify=[app_commands.Choice(name="None", value="none"), app_commands.Choice(name="DM only", value="dm"), app_commands.Choice(name="Chat only", value="chat"), app_commands.Choice(name="Both DM and Chat", value="both")])
    async def postpone_event(self, interaction: discord.Interaction, event_id: str, new_time: str = None, notify: str = "none", occurrence: int = None):
        await self._handle_status_change(interaction, event_id, "postponed", notify, occurrence, new_time)

    @app_commands.command(name="activate", description="Set a cancelled/postponed event back to ACTIVE")
    @app_commands.describe(event_id="The short ID or series name", occurrence="Occurrence number for series")
    async def activate_event(self, interaction: discord.Interaction, event_id: str, occurrence: int = None):
        await self._handle_status_change(interaction, event_id, "active", "none", occurrence)

    async def _handle_status_change(self, interaction, event_id, status, notify, occurrence, new_time=None):
        if not await is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        db_event, series_events, is_series_target = None, [], event_id.startswith("series:")

        if is_series_target:
            config_name = event_id.replace("series:", "")
            series_events = await database.get_active_events_by_config(config_name, interaction.guild_id)
            if not series_events: return await interaction.followup.send(t("ERR_EV_NOT_FOUND"), ephemeral=True)
            if occurrence is not None:
                idx = occurrence - 1
                if 0 <= idx < len(series_events): db_event = series_events[idx]; event_id = db_event["event_id"]; is_series_target = False
                else: return await interaction.followup.send(f"❌ Nincs ennyi ({occurrence}) esemény.", ephemeral=True)
            else: db_event = series_events[0]
        else: db_event = await database.get_active_event(event_id)

        if not db_event: return await interaction.followup.send(t("ERR_EV_NOT_FOUND"), ephemeral=True)

        if status == "postponed" and new_time:
            try:
                local_tz = tz.gettz("Europe/Budapest")
                dt = parser.parse(new_time).replace(tzinfo=local_tz)
                await database.update_event_time(event_id, dt.timestamp())
            except Exception as e: return await interaction.followup.send(f"❌ Hibás időpont: {e}", ephemeral=True)

        from cogs.event_ui import StatusChoiceView, DynamicEventView
        if is_series_target and not occurrence:
             view = StatusChoiceView(self.bot, event_id, db_event, series_events, status, notify)
             await interaction.followup.send(f"💡 Ez egy sorozat része. Szeretnéd az ÖSSZES jövőbeli alkalmat **{status}** állapotra állítani?", view=view, ephemeral=True)
        else:
            await database.update_event_status(event_id, status)
            ev = await database.get_active_event(event_id)
            if ev and ev.get("message_id") and ev.get("channel_id"):
                chan = self.bot.get_channel(ev["channel_id"])
                if chan:
                    try:
                        msg = await chan.fetch_message(ev["message_id"])
                        dv = DynamicEventView(self.bot, event_id, ev)
                        emb = await dv.generate_embed(ev)
                        await msg.edit(embed=emb, view=dv)
                    except: pass
            choice_view = StatusChoiceView(self.bot, event_id, ev, [], status, notify)
            await choice_view.refresh_and_notify(interaction, [event_id])
            await interaction.followup.send(f"✅ Esemény mostantól: `{status}`", ephemeral=True)

    @cancel_event.autocomplete("event_id")
    @postpone_event.autocomplete("event_id")
    @activate_event.autocomplete("event_id")
    async def status_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.edit_event_autocomplete(interaction, current)

    @app_commands.command(name="remove", description="Delete an active event message")
    @app_commands.describe(event_id="The event you want to remove")
    async def remove_event(self, interaction: discord.Interaction, event_id: str):
        if not await is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        db_event = await database.get_active_event(event_id, interaction.guild_id)
        if not db_event: return await interaction.followup.send(f"Event `{event_id}` not found.", ephemeral=True)
        try:
            channel = self.bot.get_channel(db_event["channel_id"])
            if channel and db_event.get("message_id"):
                old_msg = await channel.fetch_message(db_event["message_id"])
                if old_msg:
                    view = discord.ui.View.from_message(old_msg)
                    for child in view.children: child.disabled = True
                    embed = old_msg.embeds[0] if old_msg.embeds else None
                    if embed: embed.title = f"{t('TAG_PAST')} {embed.title}"; await old_msg.edit(embed=embed, view=view)
                    else: await old_msg.edit(view=view)
        except Exception as e: log.warning(f"Could not update message for event {event_id}: {e}")
        await database.delete_active_event(event_id, interaction.guild_id)
        await interaction.followup.send(f"✅ Event removed.", ephemeral=True)

    @remove_event.autocomplete("event_id")
    async def remove_event_autocomplete(self, interaction: discord.Interaction, current: str):
        active_events = await database.get_all_active_events(interaction.guild_id)
        choices = []
        for ev in active_events:
            label = f"{ev.get('title') or ev.get('config_name')} ({ev['event_id']})"
            if current.lower() in label.lower(): choices.append(app_commands.Choice(name=label, value=ev['event_id']))
        return choices[:25]

    @app_commands.command(name="continue-draft", description="Finish an event you started earlier")
    @app_commands.describe(draft_id="Select which draft to finish")
    async def continue_draft(self, interaction: discord.Interaction, draft_id: str):
        data = await database.get_draft(draft_id, interaction.guild_id)
        if not data: return await interaction.response.send_message("Draft not found.", ephemeral=True)
        from cogs.event_wizard import EventWizardView
        view = EventWizardView(self.bot, interaction.user.id, existing_data=data, guild_id=interaction.guild_id)
        embed = discord.Embed(title=t("WIZARD_TITLE"), description=t("WIZARD_DESC", status=view.get_status_text()), color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @continue_draft.autocomplete("draft_id")
    async def continue_draft_autocomplete(self, interaction: discord.Interaction, current: str):
        drafts = await database.get_user_drafts(interaction.guild_id, interaction.user.id)
        choices = []
        for d in drafts:
            label = f"{d['title']} ({d['draft_id']})"
            if current.lower() in label.lower(): choices.append(app_commands.Choice(name=label, value=d['draft_id']))
        return choices[:25]

    @app_commands.command(name="delete-draft", description="Delete one of your drafts")
    @app_commands.describe(draft_id="Select which draft to delete")
    async def delete_draft_cmd(self, interaction: discord.Interaction, draft_id: str):
        await database.delete_draft(draft_id, interaction.guild_id)
        await interaction.response.send_message("Draft deleted.", ephemeral=True)

    @delete_draft_cmd.autocomplete("draft_id")
    async def delete_draft_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.continue_draft_autocomplete(interaction, current)

    @app_commands.command(name="delete-all-drafts", description="Delete all your drafts at once")
    async def delete_all_drafts(self, interaction: discord.Interaction):
        await database.delete_all_user_drafts(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(t("MSG_DRAFTS_CLEARED"), ephemeral=True)

    # --- ADMIN SUBGROUP ---

    @admin_group.command(name="reset", description="WIPE ALL DATA for this server (Active events, RSVPs, drafts, custom symbols)")
    async def reset_server(self, interaction: discord.Interaction):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)

        class ConfirmReset(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)
                self.value = None
            @discord.ui.button(label="YES, PERMANENTLY DELETE EVERYTHING", style=discord.ButtonStyle.danger)
            async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.value = True; self.stop(); await interaction.response.defer()
            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.value = False; self.stop(); await interaction.response.send_message("Reset cancelled.", ephemeral=True)

        confirm_view = ConfirmReset()
        await interaction.response.send_message("⚠️ **DANGER ZONE** ⚠️\nThis will permanently delete all events, RSVPs, drafts, and custom icons for **THIS SERVER ONLY**.\nAre you absolutely sure?", view=confirm_view, ephemeral=True)
        await confirm_view.wait()
        if confirm_view.value:
            try:
                guild_id = interaction.guild_id
                await database.clear_guild_data(guild_id)
                log.info(f"[Admin] Guild {guild_id} data was WIPED by {interaction.user}", guild_id=guild_id)
                try:
                    from cogs.event_ui import load_custom_sets
                    await load_custom_sets()
                except: pass
                await interaction.followup.send(f"✅ All data for this server has been successfully deleted.", ephemeral=True)
            except Exception as e: log.error(f"Error during guild reset: {e}", guild_id=guild_id); await interaction.followup.send(f"❌ Error during reset: `{e}`", ephemeral=True)

    @commands.command(name="sync")
    @commands.guild_only()
    async def sync_prefix(self, ctx: commands.Context, spec: str | None = None):
        if not await is_admin(ctx): return await ctx.send(t("ERR_ADMIN_ONLY"))
        if ADMIN_CHANNEL_ID and ctx.channel.id != ADMIN_CHANNEL_ID: return await ctx.send(t("ERR_CHANNEL_ONLY"))
        await ctx.send(t("SYNC_START_MSG"))
        try:
            if spec == "global": synced = await self.bot.tree.sync(); await ctx.send(t("SYNC_SUCCESS_GLOBAL", count=len(synced)))
            elif spec == "copy": self.bot.tree.copy_global_to(guild=ctx.guild); synced = await self.bot.tree.sync(guild=ctx.guild); await ctx.send(t("SYNC_SUCCESS_COPY", count=len(synced)))
            else: synced = await self.bot.tree.sync(guild=ctx.guild); await ctx.send(t("SYNC_SUCCESS_GUILD", count=len(synced)))
        except discord.Forbidden: await ctx.send("❌ Error: Missing 'Applications.Commands' scope or permissions!")
        except Exception as e: await ctx.send(f"❌ Sync failed: `{e}`")

    @commands.command(name="clear_commands")
    @commands.guild_only()
    async def clear_commands_prefix(self, ctx: commands.Context):
        if not await is_admin(ctx): return await ctx.send(t("ERR_ADMIN_ONLY"))
        if ADMIN_CHANNEL_ID and ctx.channel.id != ADMIN_CHANNEL_ID: return await ctx.send(t("ERR_CHANNEL_ONLY"))
        await ctx.send(t("SYNC_CLEAR_START"))
        try:
            self.bot.tree.clear_commands(guild=None); await self.bot.tree.sync(guild=None)
            self.bot.tree.clear_commands(guild=ctx.guild); await self.bot.tree.sync(guild=ctx.guild)
            suffix = self.bot.config.get("command_suffix", "")
            await ctx.send(t("SYNC_CLEAR_SUCCESS", suffix=suffix))
        except Exception as e: await ctx.send(f"❌ Clear failed: `{e}`")

    @app_commands.command(name="sync", description="Sync slash commands manually")
    @app_commands.describe(mode="Choose: guild, global, or copy")
    async def sync_slash(self, interaction: discord.Interaction, mode: str = "guild"):
        if not await is_admin(interaction): return await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        if mode == "global": synced = await self.bot.tree.sync(); await interaction.followup.send(t("SYNC_SUCCESS_GLOBAL", count=len(synced)), ephemeral=True)
        elif mode == "copy": self.bot.tree.copy_global_to(guild=interaction.guild); synced = await self.bot.tree.sync(guild=interaction.guild); await interaction.followup.send(t("SYNC_SUCCESS_COPY", count=len(synced)), ephemeral=True)
        else: synced = await self.bot.tree.sync(guild=interaction.guild); await interaction.followup.send(t("SYNC_SUCCESS_GUILD", count=len(synced)), ephemeral=True)

# --- MASTER UI COMPONENTS ---

class MasterPresenceView(discord.ui.View):
    def __init__(self, presence_list):
        super().__init__(timeout=300)
        self.presence_list = presence_list
    @discord.ui.button(label="➕ Hozzáadás", style=discord.ButtonStyle.green)
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddPresenceModal(self))
    @discord.ui.button(label="🗑️ Lista ürítése", style=discord.ButtonStyle.danger)
    async def clear_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.presence_list = []; await database.save_global_setting("bot_presence_list", json.dumps(self.presence_list)); await interaction.response.send_message("✅ Státusz lista törölve.", ephemeral=True)

class AddPresenceModal(discord.ui.Modal, title="Új Státusz Hozzáadása"):
    status_input = discord.ui.TextInput(label="Státusz szövege", placeholder="Pl. watching {event_count} events", required=True, style=discord.TextStyle.short)
    def __init__(self, parent_view):
        super().__init__(); self.parent_view = parent_view
    async def on_submit(self, interaction: discord.Interaction):
        new_status = self.status_input.value.strip(); self.parent_view.presence_list.append(new_status); await database.save_global_setting("bot_presence_list", json.dumps(self.parent_view.presence_list)); await interaction.response.send_message(f"✅ Hozzáadva: `{new_status}`", ephemeral=True)

async def setup(bot):
    cog = EventCommands(bot)
    config = getattr(bot, 'config', {})
    suffix = config.get('command_suffix', '')
    if suffix:
        cog.sync_prefix.aliases = [f"sync{suffix}"]
        cog.clear_commands_prefix.aliases = [f"clear_commands{suffix}"]
        log.info(f"[Admin] Dynamic aliases prepared for suffix: {suffix}")
    await bot.add_cog(cog)
