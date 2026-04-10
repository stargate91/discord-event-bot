import discord
from discord import app_commands
from discord.ext import commands
from discord import ui
import json
import database
from utils.i18n import t
from utils.auth import is_admin
from utils.emoji_utils import slugify, parse_emoji_config
from utils.templates import ICON_SET_TEMPLATES
from utils.logger import log

async def send_emoji_help(interaction: discord.Interaction, guild_id):
    """Sends an ephemeral embed explaining the emoji set configuration."""
    embed = discord.Embed(
        title=t("HELP_EMOJI_TITLE", guild_id=guild_id),
        description=t("HELP_EMOJI_DESC", guild_id=guild_id),
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

class EmojiWizardView(ui.LayoutView):
    """Main management console for emoji sets (Guild or Global)."""
    def __init__(self, bot, guild_id, selected_set_id=None, is_global=False):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id
        self.selected_set_id = selected_set_id
        self.is_global = is_global


    async def refresh_message(self, interaction: discord.Interaction, status_msg=None):
        desc = t("EMOJI_WIZ_INIT_DESC", guild_id=self.guild_id)
        if self.is_global:
             desc = t("LBL_GLOBAL_EMOJI_DESC", guild_id=self.guild_id)

        selection_details = ""
        current = None
        if self.selected_set_id:
            if self.is_global:
                sets = await database.get_all_global_emoji_sets()
            else:
                sets = await database.get_emoji_sets(self.guild_id)
            
            current = next((s for s in sets if s["set_id"] == self.selected_set_id), None)
            if current:
                s_data = current["data"]
                sdata = json.loads(s_data) if isinstance(s_data, str) else s_data
                opts = sdata.get("options", [])
                preview = " ".join([f"{o.get('emoji')} `{o.get('label')}`" for o in opts])
                selection_details = t("EMOJI_WIZ_SELECTED_DESC", guild_id=self.guild_id, name=current['name'], preview=preview)

        # Create a FRESH view instance to ensure clean interaction handling
        # This fixes specialized V2 component dispatching issues
        new_view = EmojiWizardView(self.bot, self.guild_id, selected_set_id=self.selected_set_id, is_global=self.is_global)
        new_view.clear_items()
        
        # 1. Select Menu
        options = []
        if self.is_global:
            sets = await database.get_all_global_emoji_sets()
        else:
            sets = await database.get_emoji_sets(self.guild_id)
            
        for s in sets:
            s_data = s["data"]
            sdata = json.loads(s_data) if isinstance(s_data, str) else s_data
            opts = sdata.get("options", [])
            preview = ", ".join([o.get("emoji") for o in opts[:3]]) if opts else t("LBL_NO_PREVIEW", guild_id=self.guild_id)
            options.append(discord.SelectOption(
                label=s["name"], 
                value=s["set_id"], 
                description=preview,
                default=(s["set_id"] == new_view.selected_set_id)
            ))
        if not options:
            options.append(discord.SelectOption(label=t("LBL_NO_SETS", guild_id=self.guild_id), value="none"))

        set_select = ui.Select(placeholder=t("SEL_EMOJI_SET", guild_id=self.guild_id), options=options)
        async def select_callback(it):
            if set_select.values[0] == "none":
                return await it.response.defer()
            new_view.selected_set_id = set_select.values[0]
            await new_view.refresh_message(it)
        set_select.callback = select_callback
        
        row_select = ui.ActionRow(set_select)
        
        # 2. Buttons
        add_btn = ui.Button(label=t("BTN_NEW_SET", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def add_cb(it):
            if not new_view.is_global and not await is_admin(it):
                return await it.response.send_message(t("ERR_ADMIN_ONLY", guild_id=new_view.guild_id), ephemeral=True)
            if new_view.is_global and not await new_view.bot.is_owner(it.user):
                return await it.response.send_message(t("ERR_OWNER_ONLY"), ephemeral=True)
            view = TemplateChoiceView(new_view)
            await it.response.send_message(t("LBL_CHOOSE_TEMPLATE", guild_id=new_view.guild_id), view=view, ephemeral=True)
        add_btn.callback = add_cb
        
        clone_btn = ui.Button(label=t("BTN_CLONE", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def clone_cb(it):
            if not new_view.selected_set_id:
                return await it.response.send_message(t("ERR_SELECT_KEY_FIRST", guild_id=new_view.guild_id), ephemeral=True)
            cur_sets = await database.get_all_global_emoji_sets() if new_view.is_global else await database.get_emoji_sets(new_view.guild_id)
            curr = next((s for s in cur_sets if s["set_id"] == new_view.selected_set_id), None)
            if not curr: return await it.response.send_message("❌ Set not found.", ephemeral=True)
            modal = EditEmojiSetModal(new_view, curr)
            modal.title = t("BTN_CLONE", guild_id=new_view.guild_id); modal.is_clone = True
            await it.response.send_modal(modal)
        clone_btn.callback = clone_cb
        
        edit_btn = ui.Button(label=t("BTN_EDIT", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def edit_cb(it):
            if not new_view.selected_set_id:
                return await it.response.send_message(t("ERR_SELECT_KEY_FIRST", guild_id=new_view.guild_id), ephemeral=True)
            cur_sets = await database.get_all_global_emoji_sets() if new_view.is_global else await database.get_emoji_sets(new_view.guild_id)
            curr = next((s for s in cur_sets if s["set_id"] == new_view.selected_set_id), None)
            if not curr: return await it.response.send_message("❌ Set not found.", ephemeral=True)
            await it.response.send_modal(EditEmojiSetModal(new_view, curr))
        edit_btn.callback = edit_cb
        
        del_btn = ui.Button(label=t("BTN_DELETE", guild_id=self.guild_id), style=discord.ButtonStyle.secondary)
        async def del_cb(it):
            if not new_view.selected_set_id:
                return await it.response.send_message(t("ERR_SELECT_SET_DELETE", guild_id=new_view.guild_id), ephemeral=True)
            if new_view.is_global:
                pool = await database.get_pool()
                await pool.execute("DELETE FROM global_emoji_sets WHERE set_id = $1", new_view.selected_set_id)
                from cogs.event_ui import load_custom_sets; await load_custom_sets()
            else:
                await database.delete_emoji_set(new_view.guild_id, new_view.selected_set_id)
            new_view.selected_set_id = None
            await it.response.send_message(t("MSG_SET_DELETED", guild_id=new_view.guild_id), ephemeral=True)
            await new_view.refresh_message(it)
        del_btn.callback = del_cb
        
        help_btn = ui.Button(label="❓", style=discord.ButtonStyle.secondary)
        async def help_cb(it): await send_emoji_help(it, new_view.guild_id)
        help_btn.callback = help_cb
        
        row_btns = ui.ActionRow(add_btn, clone_btn, edit_btn, del_btn, help_btn)
        
        container_items = [
            ui.TextDisplay(f"### {t('LBL_GLOBAL_TITLE' if new_view.is_global else 'EMOJI_WIZ_TITLE', guild_id=new_view.guild_id)}"),
            ui.Separator(),
            ui.TextDisplay(f"{status_msg}\n\n{desc}" if status_msg else desc),
        ]
        
        if selection_details:
            container_items.append(ui.Separator())
            container_items.append(ui.TextDisplay(selection_details))
            
        container_items.append(ui.Separator())
        container_items.append(row_select)
        container_items.append(row_btns)
        
        container = ui.Container(*container_items, accent_color=0x00bfff)
        new_view.add_item(container)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embeds=[], view=new_view)
        elif interaction.type in (discord.InteractionType.component, discord.InteractionType.modal_submit):
            await interaction.response.edit_message(embeds=[], view=new_view)
        else:
            await interaction.response.send_message(view=new_view, ephemeral=True)



class TemplateChoiceView(ui.LayoutView):
    def __init__(self, wizard_view):
        super().__init__(timeout=300)
        self.wizard_view = wizard_view
        
        # Localize options
        options = []
        for k, v in ICON_SET_TEMPLATES.items():
            label = t(v["label_key"], guild_id=self.wizard_view.guild_id) if "label_key" in v else v["id"]
            options.append(discord.SelectOption(label=label, value=k, emoji=v["emoji"]))
        
        options.append(discord.SelectOption(label=t("LBL_EMPTY_SET", guild_id=self.wizard_view.guild_id), value="empty", emoji="🆕"))
        
        select_template = ui.Select(placeholder=t("SEL_TEMPLATE", guild_id=self.wizard_view.guild_id), options=options)
        async def select_callback(interaction: discord.Interaction):
            template = select_template.values[0]
            initial_text = ICON_SET_TEMPLATES.get(template, {}).get("text", "") if template != "empty" else ""
            dummy_record = {
                "set_id": "", "name": "",
                "data": json.dumps({"options": [], "buttons_per_row": 5, "show_mgmt": True})
            }
            edit_modal = EditEmojiSetModal(self.wizard_view, dummy_record)
            edit_modal.title = t("MODAL_NEW_SET_TITLE", guild_id=self.wizard_view.guild_id)
            edit_modal.opts_input.default = initial_text
            edit_modal.is_new = True 
            await interaction.response.send_modal(edit_modal)
        select_template.callback = select_callback

        container = ui.Container(
            ui.TextDisplay(f"### {t('LBL_CHOOSE_TEMPLATE', guild_id=self.wizard_view.guild_id)}"),
            ui.Separator(),
            ui.ActionRow(select_template),
            accent_color=0x00bfff
        )
        self.add_item(container)

class EditEmojiSetModal(ui.Modal):
    def __init__(self, wizard_view, set_record):
        super().__init__(title=t("MODAL_EDIT_SET_TITLE", guild_id=wizard_view.guild_id))
        self.wizard_view = wizard_view
        self.set_id = set_record["set_id"]
        self.is_clone = False
        self.is_new = False
        
        # Parse data
        s_data = set_record["data"]
        sdata = json.loads(s_data) if isinstance(s_data, str) else s_data
        opts = sdata.get("options", [])
        row_limit = sdata.get("buttons_per_row", 5)
        
        color_rev = {"success": "G", "danger": "R", "primary": "B", "secondary": "Y"}
        lines = []
        for o in opts:
            limit = o.get("max_slots", 0)
            flags = ""
            if o.get("show_in_list", True): flags += "S"
            if o.get("positive", False): flags += "P"
            
            style = o.get("button_style", "both")
            if style == "both": flags += "B"
            elif style == "emoji": flags += "E"
            elif style == "label": flags += "T"
            
            col = color_rev.get(o.get("button_color"), "")
            flags += col
            lines.append(f"{o.get('emoji')} | {o.get('label', '')} | {o.get('list_label', '')} | {limit} | {flags}")
        
        opt_text = "\n".join(lines)
        show_mgmt_val = t("LBL_YES", guild_id=wizard_view.guild_id) if sdata.get("show_mgmt", True) else t("LBL_NO", guild_id=wizard_view.guild_id)
        
        self.name_input = ui.TextInput(label=t("LBL_SET_NAME", guild_id=wizard_view.guild_id), default=set_record["name"], required=True)
        self.opts_input = ui.TextInput(label=t("LBL_EDIT_OPTIONS", guild_id=wizard_view.guild_id), placeholder=t("PH_EDIT_OPTIONS", guild_id=wizard_view.guild_id), style=discord.TextStyle.paragraph, default=opt_text, required=True)
        self.row_limit = ui.TextInput(label=t("LBL_ROW_LIMIT", guild_id=wizard_view.guild_id), default=str(row_limit), required=True)
        self.mgmt_input = ui.TextInput(label=t("LBL_SHOW_MGMT", guild_id=wizard_view.guild_id), default=show_mgmt_val, placeholder=t("PH_SHOW_MGMT", guild_id=wizard_view.guild_id), required=True)
        
        self.add_item(self.name_input)
        self.add_item(self.opts_input)
        self.add_item(self.row_limit)
        self.add_item(self.mgmt_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            row_l = int(self.row_limit.value)
            if not (1 <= row_l <= 5): raise ValueError()
        except:
             return await interaction.response.send_message("❌ Row limit must be 1-5.", ephemeral=True)

        show_m = (self.mgmt_input.value.strip().lower() in [t("LBL_YES", guild_id=self.wizard_view.guild_id).lower(), "yes", "igen", "y", "i"])

        try:
            new_opts, p_count = parse_emoji_config(self.opts_input.value)
        except Exception as e:
            return await interaction.response.send_message(f"❌ {e}", ephemeral=True)

        new_data = {
            "options": new_opts,
            "positive_count": p_count,
            "buttons_per_row": row_l,
            "show_mgmt": show_m
        }

        tid = self.set_id
        if self.is_clone or self.is_new:
            tid = slugify(self.name_input.value) or "custom_set"
            # Collision check
            if self.wizard_view.is_global:
                existing = await database.get_all_global_emoji_sets()
            else:
                existing = await database.get_emoji_sets(self.wizard_view.guild_id)
            
            existing_ids = [s["set_id"] for s in existing]
            base_id = tid
            counter = 2
            while tid in existing_ids:
                tid = f"{base_id}_{counter}"
                counter += 1
        
        if self.wizard_view.is_global:
            await database.save_global_emoji_set(tid, self.name_input.value, new_data)
            from cogs.event_ui import load_custom_sets
            await load_custom_sets()
            msg = t("MSG_GLOBAL_SAVED", guild_id=self.wizard_view.guild_id)
        else:
            await database.save_emoji_set(self.wizard_view.guild_id, tid, self.name_input.value, new_data)
            msg = t("MSG_ADVANCED_SAVED", guild_id=self.wizard_view.guild_id)

        self.wizard_view.selected_set_id = tid
        await self.wizard_view.refresh_message(interaction, status_msg=msg)

class EmojiWizard(commands.GroupCog, name="admin"):
    """Cog for server administrators to manage local emoji sets."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="emojis", description="Manage customized emoji sets for this server")
    async def manage_emojis(self, interaction: discord.Interaction):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY", guild_id=interaction.guild_id), ephemeral=True)
        
        view = EmojiWizardView(self.bot, interaction.guild_id)
        await view.refresh_message(interaction)

async def setup(bot):
    await bot.add_cog(EmojiWizard(bot))
