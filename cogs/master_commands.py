import discord
from discord import app_commands
from discord.ext import commands
import database
import json
from utils.logger import log
from utils.i18n import t

class MasterCommands(commands.GroupCog, name="master"):
    """Global Bot Management commands. Only visible in the Master Guild."""
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="stats")
    async def stats(self, interaction: discord.Interaction):
        """View global bot usage and database statistics."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            stats = await database.get_global_stats()
            
            embed = discord.Embed(
                title="📊 Nexus Global Statistics",
                color=discord.Color.purple(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(name="🌐 Guilds", value=f"**{stats['guilds']}**", inline=True)
            embed.add_field(name="📅 Active Events", value=f"**{stats['events']}**", inline=True)
            embed.add_field(name="📝 Total RSVPs", value=f"**{stats['rsvps']}**", inline=True)
            
            # Additional bot info
            embed.add_field(name="🤖 Bot Version", value="v2.1.0", inline=True)
            embed.add_field(name="⚙️ Python Version", value="3.14", inline=True)
            embed.add_field(name="🛰️ Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
            
            embed.set_footer(text="Nexus Event Bot - Owner Console")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            log.error(f"[Master] Error getting stats: {e}")
            await interaction.followup.send(f"❌ Error retrieving stats: {e}")

    @app_commands.command(name="status")
    @app_commands.describe(
        action="What to do: list, add, remove",
        text="The status text (use {event_count} for dynamic number)"
    )
    async def status_mgmt(self, interaction: discord.Interaction, action: str, text: str = None):
        """Manage the bot's dynamic presence list."""
        await interaction.response.defer(ephemeral=True)
        
        db_presence = await database.get_global_setting("bot_presence_list")
        presence_list = json.loads(db_presence) if db_presence else []

        if action.lower() == "list":
            if not presence_list:
                return await interaction.followup.send("📭 The status list is empty.")
            
            msg = "**Current Status Roster:**\n"
            for i, p in enumerate(presence_list):
                msg += f"{i+1}. `{p}`\n"
            await interaction.followup.send(msg)

        elif action.lower() == "add":
            if not text:
                return await interaction.followup.send("❌ Please provide the status text.")
            
            presence_list.append(text)
            await database.save_global_setting("bot_presence_list", json.dumps(presence_list))
            await interaction.followup.send(f"✅ Added status: `{text}`")
            log.info(f"[Master] Owner added presence: {text}")

        elif action.lower() == "remove":
            if not text:
                return await interaction.followup.send("❌ Please provide the text or index to remove.")
            
            try:
                if text.isdigit():
                    idx = int(text) - 1
                    removed = presence_list.pop(idx)
                else:
                    presence_list.remove(text)
                    removed = text
                
                await database.save_global_setting("bot_presence_list", json.dumps(presence_list))
                await interaction.followup.send(f"✅ Removed status: `{removed}`")
                log.info(f"[Master] Owner removed presence: {removed}")
            except (ValueError, IndexError):
                await interaction.followup.send("❌ Status not found in list.")

    @app_commands.command(name="global-sets")
    async def global_emoji_sets(self, interaction: discord.Interaction):
        """Manage system-wide global emoji sets used by all guilds."""
        try:
            from cogs.emoji_wizard import EmojiWizardView
            view = EmojiWizardView(self.bot, interaction.guild_id, is_global=True)
            await view.prepare()
            
            embed = discord.Embed(
                title=f"🌍 Global Emoji Management",
                description="Managing the central icon sets available to all servers.",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            log.error(f"[Master] Error in global-sets: {e}")
            await interaction.response.send_message(f"❌ Error opening Global Emoji Wizard: {e}", ephemeral=True)

    # --- PREFIXED COMMANDS (Manual management as requested) ---

    # These are for the Bot Owner to manage the command tree manually.

    @commands.command(name="sync")
    @commands.is_owner()
    async def sync_prefix(self, ctx: commands.Context, spec: str | None = None):
        """Manual sync: !sync (guild), !sync copy (copy global to guild), !sync global"""
        await ctx.send("🔄 Starting synchronization...")
        try:
            if spec == "global":
                synced = await self.bot.tree.sync()
                await ctx.send(f"✅ Synced {len(synced)} commands globally.")
            elif spec == "copy":
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await self.bot.tree.sync(guild=ctx.guild)
                await ctx.send(f"✅ Global commands copied and synced to this guild ({len(synced)} total).")
            else:
                # Default: Guild only
                synced = await self.bot.tree.sync(guild=ctx.guild)
                await ctx.send(f"✅ Synced {len(synced)} commands to this guild.")
        except Exception as e:
            await ctx.send(f"❌ Sync failed: `{e}`")

    @commands.command(name="clear_commands")
    @commands.is_owner()
    async def clear_commands_prefix(self, ctx: commands.Context):
        """Totally clear slash commands tree."""
        await ctx.send("🗑️ Clearing all command registrations...")
        try:
            # Clear Global
            self.bot.tree.clear_commands(guild=None)
            await self.bot.tree.sync(guild=None)
            # Clear Guild
            self.bot.tree.clear_commands(guild=ctx.guild)
            await self.bot.tree.sync(guild=ctx.guild)
            
            await ctx.send("✅ Command tree cleared. Use `!sync` to re-register.")
        except Exception as e:
            await ctx.send(f"❌ Clear failed: `{e}`")

async def setup(bot):
    cog = MasterCommands(bot)
    
    # Apply SUFFIX aliases if configured
    try:
        from utils.jsonc import load_jsonc
        config_data = load_jsonc('config.json')
        suffix = config_data.get("command_suffix", "")
        if suffix:
            cog.sync_prefix.aliases = [f"sync{suffix}"]
            cog.clear_commands_prefix.aliases = [f"clear_commands{suffix}"]
            log.info(f"[Master] Prefixed aliases prepared: sync{suffix}, clear_commands{suffix}")
    except: pass

    await bot.add_cog(cog)
