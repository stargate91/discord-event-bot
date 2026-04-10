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
            
            val_guilds = f"**{stats['guilds']}**"
            val_events = f"**{stats['events']}**"
            val_rsvps = f"**{stats['rsvps']}**"
            val_lat = f"{round(self.bot.latency * 1000)}ms"

            body_text = (
                f"{t('MASTER_STATS_GUILDS', guild_id=None)}: {val_guilds}\n"
                f"{t('MASTER_STATS_EVENTS', guild_id=None)}: {val_events}\n"
                f"{t('MASTER_STATS_RSVPS', guild_id=None)}: {val_rsvps}\n\n"
                f"{t('MASTER_STATS_VERSION', guild_id=None)}: **v2.1.0**\n"
                f"{t('MASTER_STATS_PYTHON', guild_id=None)}: **3.14**\n"
                f"{t('MASTER_STATS_LATENCY', guild_id=None)}: **{val_lat}**"
            )

            layout = ui.LayoutView(
                ui.Container(
                    ui.TextDisplay(f"### {t('MASTER_STATS_TITLE', guild_id=None)}"),
                    ui.Separator(),
                    ui.TextDisplay(body_text),
                    ui.Separator(),
                    ui.TextDisplay(f"__{t('MASTER_STATS_FOOTER', guild_id=None)}__"),
                    accent_color=0x00bfff
                )
            )
            
            await interaction.followup.send(view=layout)
        except Exception as e:
            log.error(f"[Master] Error getting stats: {e}")
            await interaction.followup.send(t("MASTER_STATS_ERR", guild_id=None).replace("{e}", str(e)))

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
                title=t("MASTER_EMOJI_TITLE", guild_id=None),
                description=t("MASTER_EMOJI_DESC", guild_id=None),
                color=discord.Color.dark_magenta()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            log.error(f"[Master] Error in global-sets: {e}")
            await interaction.response.send_message(t("MASTER_EMOJI_ERR", guild_id=None).replace("{e}", str(e)), ephemeral=True)

import uuid

class PresenceConfigModal(ui.Modal):
    rotate_time = ui.TextInput(label="Time", placeholder="30", default="30")
    rotate_mode = ui.TextInput(label="Mode", placeholder="random", default="random")

    def __init__(self, current_config, refresh_callback):
        super().__init__(title=t("MASTER_PRESENCE_CFG_TITLE", guild_id=None))
        self.rotate_time.label = t("MASTER_PRESENCE_CFG_TIME", guild_id=None)
        self.rotate_mode.label = t("MASTER_PRESENCE_CFG_MODE", guild_id=None)
        
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
            config = {"statuses": [{"id": str(uuid.uuid4()), "type": "watching", "text": txt} for txt in config]}
        
        config["time"] = time_val
        config["mode"] = mode_val
        
        await database.save_global_setting("bot_presence_list", json.dumps(config))
        await interaction.response.defer()
        await self.refresh_callback(interaction)

class StatusModal(ui.Modal):
    text_input = ui.TextInput(label="Text", placeholder="...", required=True)
    type_input = ui.TextInput(label="Type", placeholder="watching", default="watching", required=False)

    def __init__(self, refresh_callback, status_id=None, current_data=None):
        title = t("MASTER_PRESENCE_EDIT_TITLE", guild_id=None) if status_id else t("MASTER_PRESENCE_ADD_TITLE", guild_id=None)
        super().__init__(title=title)
        
        self.text_input.label = t("MASTER_PRESENCE_TXT_LBL", guild_id=None)
        self.text_input.placeholder = t("MASTER_PRESENCE_TXT_PH", guild_id=None)
        self.type_input.label = t("MASTER_PRESENCE_TYPE_LBL", guild_id=None)
        
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
            title=t("MASTER_PRESENCE_TITLE", guild_id=None),
            description=t("MASTER_PRESENCE_DESC", guild_id=None),
            color=discord.Color.blue()
        )
        
        time_cfg = self.current_config.get("time", 30)
        mode_cfg = self.current_config.get("mode", "random")
        val = t("MASTER_PRESENCE_CFG_VAL", guild_id=None).replace("{time}", str(time_cfg)).replace("{mode}", mode_cfg.capitalize())
        embed.add_field(name=t("MASTER_PRESENCE_CFG", guild_id=None), value=val, inline=False)
        
        statuses = self.current_config.get("statuses", [])
        if statuses:
            lines = []
            icon_map = {"playing": "🎮", "watching": "👀", "listening": "🎧", "competing": "🏆"}
            for i, s in enumerate(statuses):
                icon = icon_map.get(s.get("type", "watching"), "👀")
                lines.append(f"`{i+1}.` {icon} **{s.get('type', 'watching').capitalize()}**: {s.get('text', '')}")
            embed.add_field(name=t("MASTER_PRESENCE_ACTIVE", guild_id=None), value="\n".join(lines), inline=False)
        else:
            embed.add_field(name=t("MASTER_PRESENCE_ACTIVE", guild_id=None), value=t("MASTER_PRESENCE_NONE", guild_id=None), inline=False)

        # Rebuild view
        self.clear_items()
        
        add_btn = ui.Button(label=t("MASTER_PRESENCE_BTN_ADD", guild_id=None), style=discord.ButtonStyle.primary)
        async def add_cb(it):
            await it.response.send_modal(StatusModal(self.refresh_message))
        add_btn.callback = add_cb
        self.add_item(add_btn)
        
        cfg_btn = ui.Button(label=t("MASTER_PRESENCE_BTN_CFG", guild_id=None), style=discord.ButtonStyle.secondary)
        async def cfg_cb(it):
            await it.response.send_modal(PresenceConfigModal(self.current_config, self.refresh_message))
        cfg_btn.callback = cfg_cb
        self.add_item(cfg_btn)

        if statuses:
            options = []
            for s in statuses:
                label = f"{s.get('type', 'Watching').capitalize()}: {s.get('text', '')}"[:100]
                options.append(discord.SelectOption(label=label, value=s["id"]))
            
            select = ui.Select(placeholder=t("MASTER_PRESENCE_SEL_PH", guild_id=None), options=options)
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
        desc = t("MASTER_PRESENCE_EDIT_DESC", guild_id=None).replace("{type}", self.status_data.get('type', 'watching').capitalize()).replace("{text}", self.status_data.get('text', ''))
        embed = discord.Embed(
            title=t("MASTER_PRESENCE_EDIT_MODE", guild_id=None),
            description=desc,
            color=discord.Color.yellow()
        )
        
        edit_btn = ui.Button(label=t("MASTER_PRESENCE_BTN_EDIT", guild_id=None), style=discord.ButtonStyle.primary)
        async def edit_cb(it):
            await it.response.send_modal(StatusModal(self.parent_view.refresh_message, self.status_id, self.status_data))
        edit_btn.callback = edit_cb
        
        del_btn = ui.Button(label=t("MASTER_PRESENCE_BTN_DEL", guild_id=None), style=discord.ButtonStyle.danger)
        async def del_cb(it):
            db_presence = await database.get_global_setting("bot_presence_list")
            config = json.loads(db_presence)
            config["statuses"] = [s for s in config["statuses"] if s["id"] != self.status_id]
            await database.save_global_setting("bot_presence_list", json.dumps(config))
            await it.response.defer()
            await self.parent_view.refresh_message(it)
        del_btn.callback = del_cb
        
        back_btn = ui.Button(label=t("MASTER_PRESENCE_BTN_BACK", guild_id=None), style=discord.ButtonStyle.secondary)
        async def back_cb(it):
            await it.response.defer()
            await self.parent_view.refresh_message(it)
        back_btn.callback = back_cb

        self.clear_items()
        self.add_item(edit_btn); self.add_item(del_btn); self.add_item(back_btn)
        
        await interaction.response.edit_message(embed=embed, view=self)



async def setup(bot):
    await bot.add_cog(MasterCommands(bot))

