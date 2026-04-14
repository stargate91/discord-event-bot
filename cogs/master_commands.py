import discord
import platform
from utils.emojis import ERROR
from discord import app_commands, ui
from discord.ext import commands
import database
import json
from utils.logger import log
from utils.i18n import t
from utils.auth import is_admin, is_master

@app_commands.check(is_master)
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
            db_stats = await database.get_global_stats()
            live_guilds = len(self.bot.guilds)
            
            from utils.config import config
            bot_version = config.version


            body_text = (
                f"{t('MASTER_STATS_GUILDS', guild_id=None, val=live_guilds)}\n"
                f"{t('MASTER_STATS_EVENTS', guild_id=None, val=db_stats['events'])}\n"
                f"{t('MASTER_STATS_RSVPS', guild_id=None, val=db_stats['rsvps'])}\n\n"
                f"{t('MASTER_STATS_VERSION', guild_id=None, val=bot_version)}\n"
                f"{t('MASTER_STATS_PYTHON', guild_id=None, val=platform.python_version())}\n"
                f"{t('MASTER_STATS_LATENCY', guild_id=None, val=f'{round(self.bot.latency * 1000)}ms')}"
            )

            layout = ui.LayoutView()
            container = ui.Container(
                ui.TextDisplay(f"### {t('MASTER_STATS_TITLE', guild_id=None)}"),
                ui.Separator(),
                ui.TextDisplay(body_text),
                ui.Separator(),
                ui.TextDisplay(f"{t('MASTER_STATS_FOOTER', guild_id=None)}"),
                accent_color=0x00bfff
            )
            layout.add_item(container)
            
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
            view = EmojiWizardView(self.bot, None, is_global=True)
            await view.refresh_message(interaction)
        except Exception as e:
            log.error(f"[Master] Error in global-sets: {e}")
            err_msg = t("MASTER_EMOJI_ERR", guild_id=None).replace("{e}", str(e))
            if interaction.response.is_done():
                await interaction.followup.send(err_msg, ephemeral=True)
            else:
                await interaction.response.send_message(err_msg, ephemeral=True)

    @app_commands.command(name="reset-global-sets")
    async def reset_global_sets_cmd(self, interaction: discord.Interaction):
        """Reset all global emoji sets to match the hardcoded templates in utils/templates.py."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            from utils.templates import ICON_SET_TEMPLATES, get_template_data
            from cogs.event_ui import load_custom_sets
            
            await database.clear_global_emoji_sets()
            
            count = 0
            for tid, tmpl in ICON_SET_TEMPLATES.items():
                # Use translated label if possible as the name
                name = t(tmpl.get("label_key"), guild_id=None) if "label_key" in tmpl else tid
                data = get_template_data(tid)
                if data:
                    await database.save_global_emoji_set(tid, name, data)
                    count += 1
            
            # Refresh cache
            await load_custom_sets()
            
            msg = (
                t("MSG_GLOBAL_RESETS_SUCCESS", guild_id=None, val=count)
                if count > 0
                else t("MSG_GLOBAL_RESETS_NONE", guild_id=None)
            )
            await interaction.followup.send(msg)
        except Exception as e:
            log.error(f"[Master] Error resetting global sets: {e}")
            await interaction.followup.send(f"{ERROR} {t('ERR_MASTER_FOLLOWUP', guild_id=None, e=str(e))}")

import uuid

class PresenceConfigModal(ui.Modal):
    rotate_time = ui.TextInput(label="Time", placeholder="30", default="30")
    rotate_mode = ui.TextInput(label="Mode", placeholder="random", default="random")

    def __init__(self, current_config, refresh_callback):
        super().__init__(title=t("MASTER_PRESENCE_CFG_TITLE", guild_id=None))
        self.rotate_time.label = t("MASTER_PRESENCE_CFG_TIME", guild_id=None)
        self.rotate_time.placeholder = t("MASTER_PRESENCE_CFG_TIME_PH", guild_id=None)
        self.rotate_mode.label = t("MASTER_PRESENCE_CFG_MODE", guild_id=None)
        self.rotate_mode.placeholder = t("MASTER_PRESENCE_CFG_MODE_PH", guild_id=None)
        
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
        self.type_input.placeholder = t("MASTER_PRESENCE_TYPE_PH", guild_id=None)
        
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

class MasterPresenceView(ui.LayoutView):
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
        
        time_cfg = self.current_config.get("time", 30)
        mode_cfg = self.current_config.get("mode", "random")
        val = t("MASTER_PRESENCE_CFG_VAL", guild_id=None).replace("{time}", str(time_cfg)).replace("{mode}", mode_cfg.capitalize())
        
        statuses = self.current_config.get("statuses", [])
        if statuses:
            lines = []
            for i, s in enumerate(statuses):
                type_key = f"PRESENCE_TYPE_{s.get('type', 'watching').upper()}"
                type_text = t(type_key, guild_id=None)
                lines.append(t("MASTER_PRESENCE_LIST_ITEM", guild_id=None, i=i+1, type_text=type_text, text=s.get('text', '')))
            active_val = "\n".join(lines)
        else:
            active_val = t("MASTER_PRESENCE_NONE", guild_id=None)

        self.clear_items()
        
        add_btn = ui.Button(label=t("MASTER_PRESENCE_BTN_ADD", guild_id=None), style=discord.ButtonStyle.secondary)
        async def add_cb(it):
            await it.response.send_modal(StatusModal(self.refresh_message))
        add_btn.callback = add_cb
        
        cfg_btn = ui.Button(label=t("MASTER_PRESENCE_BTN_CFG", guild_id=None), style=discord.ButtonStyle.secondary)
        async def cfg_cb(it):
            await it.response.send_modal(PresenceConfigModal(self.current_config, self.refresh_message))
        cfg_btn.callback = cfg_cb
        
        row_buttons = ui.ActionRow(add_btn, cfg_btn)

        container_items = [
            ui.TextDisplay(f"### {t('MASTER_PRESENCE_TITLE', guild_id=None)}"),
            ui.Separator(),
            ui.TextDisplay(t("MASTER_PRESENCE_DESC", guild_id=None)),
            ui.Separator(),
            ui.TextDisplay(f"**{t('MASTER_PRESENCE_CFG', guild_id=None)}**\n{val}"),
            ui.Separator(),
            ui.TextDisplay(f"**{t('MASTER_PRESENCE_ACTIVE', guild_id=None)}**\n{active_val}"),
            ui.Separator()
        ]

        if statuses:
            options = []
            for s in statuses:
                type_key = f"PRESENCE_TYPE_{s.get('type', 'watching').upper()}"
                type_text = t(type_key, guild_id=None).replace("**", "") # Strip bolding for select menu if any
                label = f"{type_text}: {s.get('text', '')}"[:100]
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
            
            row_select = ui.ActionRow(select)
            container_items.append(row_select)

        container_items.append(row_buttons)
        container = ui.Container(*container_items, accent_color=0x00bfff)
        self.add_item(container)
            
        if interaction.response.is_done():
            await interaction.edit_original_response(embeds=[], view=self)
        elif interaction.type == discord.InteractionType.component:
            await interaction.response.edit_message(embeds=[], view=self)
        else:
            await interaction.response.send_message(view=self, ephemeral=True)

class PresenceEditView(ui.LayoutView):
    def __init__(self, parent_view, status_id, status_data):
        super().__init__(timeout=300)
        self.parent_view = parent_view
        self.status_id = status_id
        self.status_data = status_data

    async def refresh_message(self, interaction: discord.Interaction):
        type_key = f"PRESENCE_TYPE_{self.status_data.get('type', 'watching').upper()}"
        type_text = t(type_key, guild_id=None)
        desc = t("MASTER_PRESENCE_EDIT_DESC", guild_id=None).replace("{type}", type_text).replace("{text}", self.status_data.get('text', ''))
        
        self.clear_items()
        edit_btn = ui.Button(label=t("MASTER_PRESENCE_BTN_EDIT", guild_id=None), style=discord.ButtonStyle.secondary)
        async def edit_cb(it):
            await it.response.send_modal(StatusModal(self.parent_view.refresh_message, self.status_id, self.status_data))
        edit_btn.callback = edit_cb
        
        del_btn = ui.Button(label=t("MASTER_PRESENCE_BTN_DEL", guild_id=None), style=discord.ButtonStyle.secondary)
        async def del_cb(it):
            db_presence = await database.get_global_setting("bot_presence_list")
            if not db_presence:
                config = {"time": 30, "mode": "random", "statuses": []}
            else:
                config = json.loads(db_presence)
                if isinstance(config, list):
                    config = {
                        "time": 30,
                        "mode": "random",
                        "statuses": [
                            {"id": str(uuid.uuid4()), "type": "watching", "text": t}
                            for t in config
                        ],
                    }
                if not isinstance(config, dict):
                    config = {"time": 30, "mode": "random", "statuses": []}
                statuses = config.get("statuses")
                if not isinstance(statuses, list):
                    statuses = []
                config["statuses"] = [s for s in statuses if s.get("id") != self.status_id]
            await database.save_global_setting("bot_presence_list", json.dumps(config))
            await it.response.defer()
            await self.parent_view.refresh_message(it)
        del_btn.callback = del_cb
        
        back_btn = ui.Button(label=t("MASTER_PRESENCE_BTN_BACK", guild_id=None), style=discord.ButtonStyle.secondary)
        async def back_cb(it):
            await it.response.defer()
            await self.parent_view.refresh_message(it)
        back_btn.callback = back_cb

        row = ui.ActionRow(edit_btn, del_btn, back_btn)
        
        container = ui.Container(
            ui.TextDisplay(f"### {t('MASTER_PRESENCE_EDIT_MODE', guild_id=None)}"),
            ui.Separator(),
            ui.TextDisplay(desc),
            row,
            accent_color=0x00bfff
        )
        self.add_item(container)
        
        await interaction.response.edit_message(embeds=[], view=self)



async def setup(bot):
    await bot.add_cog(MasterCommands(bot))

