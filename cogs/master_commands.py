import discord
from discord import app_commands, ui
from discord.ext import commands
import database
import json
from utils.logger import log
from utils.i18n import t
from utils.auth import is_admin

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
    async def status_mgmt(self, interaction: discord.Interaction):
        """Manage the bot's dynamic presence list using a visual console."""
        view = MasterPresenceView(self.bot)
        await view.refresh_message(interaction)

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

import uuid

class PresenceConfigModal(ui.Modal, title="⚙️ Jelenlét Beállítások"):
    rotate_time = ui.TextInput(label="Forgási idő (másodperc)", placeholder="pl. 30", default="30")
    rotate_mode = ui.TextInput(label="Mód (random vagy sequential)", placeholder="random", default="random")

    def __init__(self, current_config, refresh_callback):
        super().__init__()
        self.refresh_callback = refresh_callback
        self.rotate_time.default = str(current_config.get("time", 30))
        self.rotate_mode.default = current_config.get("mode", "random")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            time_val = int(self.rotate_time.value)
        except ValueError:
            time_val = 30
        
        mode_val = self.rotate_mode.value.lower()
        if mode_val not in ["random", "sequential"]:
            mode_val = "random"

        db_presence = await database.get_global_setting("bot_presence_list")
        config = json.loads(db_presence) if db_presence else {"statuses": []}
        if isinstance(config, list):
            config = {"statuses": [{"id": str(uuid.uuid4()), "type": "watching", "text": t} for t in config]}
        
        config["time"] = time_val
        config["mode"] = mode_val
        
        await database.save_global_setting("bot_presence_list", json.dumps(config))
        await interaction.response.defer()
        await self.refresh_callback(interaction)

class StatusModal(ui.Modal):
    text_input = ui.TextInput(label="Státusz Szöveg", placeholder="pl. {event_count} esemény", required=True)
    type_input = ui.TextInput(label="Típus (playing/watching/listening/competing)", placeholder="watching", default="watching", required=False)

    def __init__(self, refresh_callback, status_id=None, current_data=None):
        title = "✏️ Státusz Szerkesztése" if status_id else "➕ Új Státusz"
        super().__init__(title=title)
        self.refresh_callback = refresh_callback
        self.status_id = status_id
        
        if current_data:
            self.text_input.default = current_data.get("text", "")
            self.type_input.default = current_data.get("type", "watching")

    async def on_submit(self, interaction: discord.Interaction):
        db_presence = await database.get_global_setting("bot_presence_list")
        config = json.loads(db_presence) if db_presence else {"time": 30, "mode": "random", "statuses": []}
        if isinstance(config, list):
            config = {"time": 30, "mode": "random", "statuses": [{"id": str(uuid.uuid4()), "type": "watching", "text": t} for t in config]}
        
        text_val = self.text_input.value.strip()
        type_val = self.type_input.value.lower().strip()
        if type_val not in ["playing", "watching", "listening", "competing"]:
            type_val = "watching"
            
        if self.status_id:
            for s in config["statuses"]:
                if s["id"] == self.status_id:
                    s["text"] = text_val
                    s["type"] = type_val
                    break
        else:
            config["statuses"].append({"id": str(uuid.uuid4()), "type": type_val, "text": text_val})
            
        await database.save_global_setting("bot_presence_list", json.dumps(config))
        await interaction.response.defer()
        await self.refresh_callback(interaction)

class MasterPresenceView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot
        self.current_config = {"time": 30, "mode": "random", "statuses": []}

    async def load_config(self):
        db_presence = await database.get_global_setting("bot_presence_list")
        if db_presence:
            parsed = json.loads(db_presence)
            if isinstance(parsed, list):
                self.current_config["statuses"] = [{"id": str(uuid.uuid4()), "type": "watching", "text": t} for t in parsed]
            else:
                self.current_config = parsed
        else:
            self.current_config = {"time": 30, "mode": "random", "statuses": []}

    async def refresh_message(self, interaction: discord.Interaction):
        await self.load_config()
        
        embed = discord.Embed(
            title="🎮 Jelenlét (Presence) Vezérlő",
            description="Állítsd be a bot státuszát, rotációs idejét és a megjelenített információkat.\nHasználható placeholderek: `{event_count}`, `{guild_count}`, `{rsvp_count}`",
            color=discord.Color.blue()
        )
        
        time_cfg = self.current_config.get("time", 30)
        mode_cfg = self.current_config.get("mode", "random")
        embed.add_field(name="⚙️ Beállítások", value=f"**Forgás:** {time_cfg} másodperc\n**Mód:** {mode_cfg.capitalize()}", inline=False)
        
        statuses = self.current_config.get("statuses", [])
        if statuses:
            lines = []
            icon_map = {"playing": "🎮", "watching": "👀", "listening": "🎧", "competing": "🏆"}
            for i, s in enumerate(statuses):
                icon = icon_map.get(s.get("type", "watching"), "👀")
                lines.append(f"`{i+1}.` {icon} **{s.get('type', 'watching').capitalize()}**: {s.get('text', '')}")
            embed.add_field(name="📝 Aktív Státuszok", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="📝 Aktív Státuszok", value="*Nincs beállítva státusz. Kattints a Hozzáadás gombra.*", inline=False)

        # Rebuild view
        self.clear_items()
        
        add_btn = ui.Button(label="➕ Új Státusz", style=discord.ButtonStyle.primary)
        async def add_cb(it):
            await it.response.send_modal(StatusModal(self.refresh_message))
        add_btn.callback = add_cb
        self.add_item(add_btn)
        
        cfg_btn = ui.Button(label="⚙️ Beállítások", style=discord.ButtonStyle.secondary)
        async def cfg_cb(it):
            await it.response.send_modal(PresenceConfigModal(self.current_config, self.refresh_message))
        cfg_btn.callback = cfg_cb
        self.add_item(cfg_btn)

        if statuses:
            options = []
            for s in statuses:
                label = f"{s.get('type', 'Watching').capitalize()}: {s.get('text', '')}"[:100]
                options.append(discord.SelectOption(label=label, value=s["id"]))
            
            select = ui.Select(placeholder="Szerkesztés/Törlés kiválasztása...", options=options)
            async def select_cb(it):
                sel_id = select.values[0]
                sel_data = next((x for x in self.current_config["statuses"] if x["id"] == sel_id), None)
                if sel_data:
                    # Show edit/delete view
                    edit_view = PresenceEditView(self, sel_id, sel_data)
                    await edit_view.refresh_message(it)
            select.callback = select_cb
            self.add_item(select)
            
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.send_message(embed=embed, view=self, ephemeral=True)

class PresenceEditView(ui.View):
    def __init__(self, parent_view, status_id, status_data):
        super().__init__(timeout=300)
        self.parent_view = parent_view
        self.status_id = status_id
        self.status_data = status_data

    async def refresh_message(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Szerkesztő Mód",
            description=f"Kiválasztva: **{self.status_data.get('type', 'watching').capitalize()}**: {self.status_data.get('text', '')}",
            color=discord.Color.yellow()
        )
        
        edit_btn = ui.Button(label="✏️ Szerkesztés", style=discord.ButtonStyle.primary)
        async def edit_cb(it):
            await it.response.send_modal(StatusModal(self.parent_view.refresh_message, self.status_id, self.status_data))
        edit_btn.callback = edit_cb
        
        del_btn = ui.Button(label="🗑️ Törlés", style=discord.ButtonStyle.danger)
        async def del_cb(it):
            db_presence = await database.get_global_setting("bot_presence_list")
            config = json.loads(db_presence)
            config["statuses"] = [s for s in config["statuses"] if s["id"] != self.status_id]
            await database.save_global_setting("bot_presence_list", json.dumps(config))
            await it.response.defer()
            await self.parent_view.refresh_message(it)
        del_btn.callback = del_cb
        
        back_btn = ui.Button(label="◀️ Vissza", style=discord.ButtonStyle.secondary)
        async def back_cb(it):
            await it.response.defer()
            await self.parent_view.refresh_message(it)
        back_btn.callback = back_cb

        self.clear_items()
        self.add_item(edit_btn); self.add_item(del_btn); self.add_item(back_btn)
        
        await interaction.response.edit_message(embed=embed, view=self)



async def setup(bot):
    await bot.add_cog(MasterCommands(bot))

