import discord
from discord.ext import commands
from discord import app_commands
import database
import time
import uuid
import datetime
import json
from cogs.event_ui import DynamicEventView
from cogs.event_wizard import EventWizardView
from utils.i18n import t
from dateutil import parser
from dateutil import tz
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

def get_event_dict(name):
    # Find event info by name in our config list
    for e in EVENTS_CONFIG:
        if e.get("name") == name:
            return e
    return None

def is_admin(ctx_or_interaction):
    # Check if the user is an administrator or has the special admin role
    user = ctx_or_interaction.author if hasattr(ctx_or_interaction, 'author') else ctx_or_interaction.user
    if user.guild_permissions.administrator:
        return True
    if ADMIN_ROLE_ID and discord.utils.get(user.roles, id=ADMIN_ROLE_ID):
        return True
    return False

class EventCommands(commands.GroupCog, name="event"):
    # Subgroup for administrative tasks
    admin_group = app_commands.Group(name="admin", description="Administrative commands for server management")

    # This class holds all the slash commands for managing events under /event
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="create", description="Start the wizard to create a new event")
    async def create_event(self, interaction: discord.Interaction):
        # Open the multi-step form (Wizard) for a new event
        if not is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)

        try:
            view = EventWizardView(self.bot, interaction.user.id, guild_id=interaction.guild_id)
            embed = discord.Embed(
                title=t("WIZARD_TITLE"), 
                description=t("WIZARD_DESC", status=view.get_status_text()), 
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            log.error(f"Error in create_event: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Hiba történt a varázsló megnyitásakor: `{e}`", ephemeral=True)


    @app_commands.command(name="edit", description="Edit an event that already exists")
    @app_commands.describe(event_id="The ID of the event you want to change")
    async def edit_event(self, interaction: discord.Interaction, event_id: str):
        # Open the Wizard for a specific event to change its details
        if not is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)

        db_event = await database.get_active_event(event_id)
        if not db_event:
            await interaction.followup.send(t("ERR_EV_NOT_FOUND"), ephemeral=True)
            return

        # Prepare dates so the wizard can show them clearly
        local_tz = tz.gettz("Europe/Budapest")
        start_dt = datetime.datetime.fromtimestamp(db_event["start_time"], tz=local_tz)
        db_event["start_str"] = start_dt.strftime("%Y-%m-%d %H:%M")
        
        if db_event.get("end_time"):
            end_dt = datetime.datetime.fromtimestamp(db_event["end_time"], tz=local_tz)
            db_event["end_str"] = end_dt.strftime("%Y-%m-%d %H:%M")
        else:
            db_event["end_str"] = ""

        try:
            view = EventWizardView(self.bot, interaction.user.id, existing_data=db_event, is_edit=True, guild_id=interaction.guild_id)
            embed = discord.Embed(
                title=t("WIZARD_TITLE"), 
                description=t("WIZARD_DESC", status=view.get_status_text()), 
                color=discord.Color.gold()
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            log.error(f"Error in edit_event: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Hiba történt a szerkesztő megnyitásakor: `{e}`", ephemeral=True)

    @edit_event.autocomplete("event_id")
    async def edit_event_autocomplete(self, interaction: discord.Interaction, current: str):
        # Helps the user search for event IDs while they type
        active_events = await database.get_all_active_events(interaction.guild_id)
        choices = []
        for ev in active_events:
            label = f"{ev.get('title') or ev['config_name']} ({ev['event_id']})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=ev['event_id']))
        return choices[:25]

    @app_commands.command(name="list", description="Show all active events")
    async def list_events(self, interaction: discord.Interaction):
        # Simply lists everything currently in the database
        if not is_admin(interaction):
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

    @app_commands.command(name="publish", description="Post an event using a preset template")
    @app_commands.describe(name="The name of the event in config.json")
    async def event_publish(self, interaction: discord.Interaction, name: str):
        # Create an event immediately using a template from config.json
        if not is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        event_conf = get_event_dict(name)
        if not event_conf:
            await interaction.followup.send("Event not found in config.", ephemeral=True)
            return
            
        if not event_conf.get("enabled"):
            await interaction.followup.send("This event is disabled in config.", ephemeral=True)
            return

        local_tz = tz.gettz(event_conf.get("timezone", "Europe/Budapest"))
        
        # Turn the start and end strings into numbers (timestamps)
        try:
            start_str = event_conf.get("start_time")
            if not start_str:
                await interaction.followup.send("Error: 'start_time' is missing!", ephemeral=True)
                return
            start_dt = parser.parse(str(start_str)).replace(tzinfo=local_tz)
            start_timestamp = start_dt.timestamp()
            event_conf["start_time"] = start_timestamp

            end_str = event_conf.get("end_time")
            if end_str:
                end_dt = parser.parse(str(end_str)).replace(tzinfo=local_tz)
                event_conf["end_time"] = end_dt.timestamp()
        except Exception as e:
            await interaction.followup.send(f"Error reading dates: {e}", ephemeral=True)
            return
        
        channel_id = event_conf.get("channel_id") or interaction.channel_id
        event_id = str(uuid.uuid4())[:8]
        
        creator_val = event_conf.get("creator_id")
        if not creator_val:
            creator_val = str(interaction.user.id)
        event_conf["creator_id"] = creator_val
        
        await database.create_active_event(
            guild_id=interaction.guild_id,
            event_id=event_id,
            config_name=name,
            channel_id=channel_id,
            start_time=start_timestamp,
            data=event_conf
        )

        view = DynamicEventView(self.bot, event_id, event_conf)
        embed = await view.generate_embed()

        await interaction.followup.send(t("MSG_EV_CREATED_EPHEMERAL"), ephemeral=True)
        
        target_channel = self.bot.get_channel(channel_id)
        if not target_channel:
            target_channel = interaction.channel
            
        content = t("MSG_EV_CREATED_PUBLIC")
        ping_role = event_conf.get("ping_role", "")
        if ping_role:
            content += f" <@&{ping_role}>"
            
        msg = await target_channel.send(content=content, embed=embed, view=view)
        await database.set_event_message(event_id, msg.id, interaction.guild_id)
        self.bot.add_view(view)

    @app_commands.command(name="remove", description="Delete an active event message")
    @app_commands.describe(event_id="The event you want to remove")
    async def remove_event(self, interaction: discord.Interaction, event_id: str):
        # Completely delete an event and clean up the message
        if not is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        db_event = await database.get_active_event(event_id, interaction.guild_id)
        if not db_event:
            await interaction.followup.send(f"Event `{event_id}` not found.", ephemeral=True)
            return

        # Try to disable buttons on the old message
        try:
            channel = self.bot.get_channel(db_event["channel_id"])
            if channel and db_event.get("message_id"):
                old_msg = await channel.fetch_message(db_event["message_id"])
                if old_msg:
                    view = discord.ui.View.from_message(old_msg)
                    for child in view.children:
                        child.disabled = True
                    embed = old_msg.embeds[0] if old_msg.embeds else None
                    if embed:
                        embed.title = f"{t('TAG_PAST')} {embed.title}"
                        await old_msg.edit(embed=embed, view=view)
                    else:
                        await old_msg.edit(view=view)
        except Exception as e:
            log.warning(f"Could not update message for event {event_id}: {e}")

        await database.delete_active_event(event_id, interaction.guild_id)
        await interaction.followup.send(f"✅ Event removed.", ephemeral=True)

    @remove_event.autocomplete("event_id")
    async def remove_event_autocomplete(self, interaction: discord.Interaction, current: str):
        # Same autocomplete logic as edit
        active_events = await database.get_all_active_events(interaction.guild_id)
        choices = []
        for ev in active_events:
            label = f"{ev.get('title') or ev.get('config_name')} ({ev['event_id']})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=ev['event_id']))
        return choices[:25]

    @app_commands.command(name="continue-draft", description="Finish an event you started earlier")
    @app_commands.describe(draft_id="Select which draft to finish")
    async def continue_draft(self, interaction: discord.Interaction, draft_id: str):
        # Reload a draft from the database so you don't lose progress
        data = await database.get_draft(draft_id, interaction.guild_id)
        if not data:
            await interaction.response.send_message("Draft not found.", ephemeral=True)
            return
            
        view = EventWizardView(self.bot, interaction.user.id, existing_data=data, guild_id=interaction.guild_id)
        embed = discord.Embed(
            title=t("WIZARD_TITLE"), 
            description=t("WIZARD_DESC", status=view.get_status_text()), 
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @continue_draft.autocomplete("draft_id")
    async def continue_draft_autocomplete(self, interaction: discord.Interaction, current: str):
        # Helps the user search for draft IDs while they type
        drafts = await database.get_user_drafts(interaction.guild_id, interaction.user.id)
        choices = []
        for d in drafts:
            label = f"{d['title']} ({d['draft_id']})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=d['draft_id']))
        return choices[:25]

    @delete_draft_cmd.autocomplete("draft_id")
    async def delete_draft_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.continue_draft_autocomplete(interaction, current)

    @app_commands.command(name="delete-draft", description="Delete one of your drafts")
    @app_commands.describe(draft_id="Select which draft to delete")
    async def delete_draft_cmd(self, interaction: discord.Interaction, draft_id: str):
        # Delete a specific draft
        await database.delete_draft(draft_id, interaction.guild_id)
        await interaction.response.send_message("Draft deleted.", ephemeral=True)

    @app_commands.command(name="delete-all-drafts", description="Delete all your drafts at once")
    async def delete_all_drafts(self, interaction: discord.Interaction):
        # Wipe all drafts for the user
        await database.delete_all_user_drafts(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(t("MSG_DRAFTS_CLEARED"), ephemeral=True)

    # --- ADMIN SUBGROUP ---

    @admin_group.command(name="reset", description="WIPE ALL DATA for this server (Active events, RSVPs, drafts, custom symbols)")
    async def reset_server(self, interaction: discord.Interaction):
        """DANGER: Completely removes all database entries linked to this guild."""
        if not is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return

        # Simple confirmation check
        class ConfirmReset(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)
                self.value = None

            @discord.ui.button(label="YES, PERMANENTLY DELETE EVERYTHING", style=discord.ButtonStyle.danger)
            async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.value = True
                self.stop()
                await interaction.response.defer()

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.value = False
                self.stop()
                await interaction.response.send_message("Reset cancelled.", ephemeral=True)

        confirm_view = ConfirmReset()
        await interaction.response.send_message(
            "⚠️ **DANGER ZONE** ⚠️\nThis will permanently delete all events, RSVPs, drafts, and custom icons for **THIS SERVER ONLY**.\nAre you absolutely sure?",
            view=confirm_view,
            ephemeral=True
        )

        await confirm_view.wait()

        if confirm_view.value:
            try:
                guild_id = interaction.guild_id
                await database.clear_guild_data(guild_id)
                log.info(f"[Admin] Guild {guild_id} data was WIPED by {interaction.user}")
                # We also need to reload custom sets in memory if some were deleted
                try:
                    from cogs.event_ui import load_custom_sets
                    await load_custom_sets()
                except: pass
                await interaction.followup.send(f"✅ All data for this server has been successfully deleted.", ephemeral=True)
            except Exception as e:
                log.error(f"Error during guild reset: {e}")
                await interaction.followup.send(f"❌ Error during reset: `{e}`", ephemeral=True)

    @commands.command(name="sync")
    @commands.guild_only()
    async def sync_prefix(self, ctx: commands.Context, spec: str | None = None):
        # Traditional prefix command to sync slash commands with Discord
        if not is_admin(ctx):
            await ctx.send(t("ERR_ADMIN_ONLY"))
            return
        if ADMIN_CHANNEL_ID and ctx.channel.id != ADMIN_CHANNEL_ID:
            await ctx.send(t("ERR_CHANNEL_ONLY"))
            return
        
        await ctx.send(t("SYNC_START_MSG"))
        try:
            if spec == "global":
                synced = await self.bot.tree.sync()
                await ctx.send(t("SYNC_SUCCESS_GLOBAL", count=len(synced)))
            elif spec == "copy":
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await self.bot.tree.sync(guild=ctx.guild)
                await ctx.send(t("SYNC_SUCCESS_COPY", count=len(synced)))
            else:
                synced = await self.bot.tree.sync(guild=ctx.guild)
                await ctx.send(t("SYNC_SUCCESS_GUILD", count=len(synced)))
        except discord.Forbidden:
            await ctx.send("❌ Error: Missing 'Applications.Commands' scope or permissions!")
        except Exception as e:
            await ctx.send(f"❌ Sync failed: `{e}`")

    @commands.command(name="clear_commands")
    @commands.guild_only()
    async def clear_commands_prefix(self, ctx: commands.Context):
        # Command to remove all slash commands (useful if something breaks)
        if not is_admin(ctx):
            await ctx.send(t("ERR_ADMIN_ONLY"))
            return
        if ADMIN_CHANNEL_ID and ctx.channel.id != ADMIN_CHANNEL_ID:
            await ctx.send(t("ERR_CHANNEL_ONLY"))
            return
            
        await ctx.send(t("SYNC_CLEAR_START"))
        try:
            self.bot.tree.clear_commands(guild=None)
            await self.bot.tree.sync(guild=None)
            self.bot.tree.clear_commands(guild=ctx.guild)
            await self.bot.tree.sync(guild=ctx.guild)
            
            suffix = self.bot.config.get("command_suffix", "")
            await ctx.send(t("SYNC_CLEAR_SUCCESS", suffix=suffix))
        except Exception as e:
            await ctx.send(f"❌ Clear failed: `{e}`")

    @app_commands.command(name="sync", description="Sync slash commands manually")
    @app_commands.describe(mode="Choose: guild, global, or copy")
    async def sync_slash(self, interaction: discord.Interaction, mode: str = "guild"):
        # Slash command version of the sync process
        if not is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if mode == "global":
            synced = await self.bot.tree.sync()
            await interaction.followup.send(t("SYNC_SUCCESS_GLOBAL", count=len(synced)), ephemeral=True)
        elif mode == "copy":
            self.bot.tree.copy_global_to(guild=interaction.guild)
            synced = await self.bot.tree.sync(guild=interaction.guild)
            await interaction.followup.send(t("SYNC_SUCCESS_COPY", count=len(synced)), ephemeral=True)
        else:
            synced = await self.bot.tree.sync(guild=interaction.guild)
            await interaction.followup.send(t("SYNC_SUCCESS_GUILD", count=len(synced)), ephemeral=True)

async def setup(bot):
    # This prepares the commands class and sets up dynamic command aliases
    cog = EventCommands(bot)
    config = getattr(bot, 'config', {})
    suffix = config.get('command_suffix', '')
    
    if suffix:
        cog.sync_prefix.aliases = [f"sync{suffix}"]
        cog.clear_commands_prefix.aliases = [f"clear_commands{suffix}"]
        log.info(f"[Admin] Dynamic aliases prepared for suffix: {suffix}")
        
    await bot.add_cog(cog)
