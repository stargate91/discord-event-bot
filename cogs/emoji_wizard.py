import discord
from discord import app_commands
from discord import ui
import json
import database
from utils.i18n import t
from utils.auth import is_admin
import unicodedata
import re

def slugify(text: str) -> str:
    """Converts a string to a safe ASCII slug (lowercase, underscores, no accents)."""
    # Normalize to NFD to separate accents (e.g. á -> a + ´)
    text = unicodedata.normalize('NFD', text)
    # Filter out non-ASCII characters (accents)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    # Lowercase and replace anything non-alphanumeric with underscores
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    # Remove leading/trailing underscores
    return text.strip('_')

class EmojiWizardView(ui.View):
    """Main management console for emoji sets."""
    def __init__(self, bot, guild_id, selected_set_id=None):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id
        self.selected_set_id = selected_set_id
        
        # Localize button labels
        self.add_btn.label = t("BTN_NEW_SET", guild_id=guild_id)
        self.edit_btn.label = t("BTN_EDIT", guild_id=guild_id)
        self.delete_btn.label = t("BTN_DELETE", guild_id=guild_id)

    async def prepare(self):
        """Initial data fetch to populate the view before sending."""
        sets = await database.get_emoji_sets(self.guild_id)
        
        options = []
        for s in sets:
            s_data = s["data"]
            sdata = json.loads(s_data) if isinstance(s_data, str) else s_data
            opts = sdata.get("options", [])
            icons = [o.get("emoji") for o in opts[:3]]
            preview = ", ".join(icons) if icons else t("LBL_NO_PREVIEW", guild_id=self.guild_id)
            options.append(discord.SelectOption(
                label=s["name"], 
                value=s["set_id"], 
                description=preview,
                default=(s["set_id"] == self.selected_set_id)
            ))
            
        if not options:
            options.append(discord.SelectOption(label=t("LBL_NO_SETS", guild_id=self.guild_id), value="none"))

        self.set_select.placeholder = t("SEL_EMOJI_SET", guild_id=self.guild_id)
        self.set_select.options = options

    async def refresh_message(self, interaction: discord.Interaction):
        await self.prepare()
        
        desc = t("EMOJI_WIZ_INIT_DESC", guild_id=self.guild_id)
        if self.selected_set_id:
            sets = await database.get_emoji_sets(self.guild_id)
            current = next((s for s in sets if s["set_id"] == self.selected_set_id), None)
            if current:
                s_data = current["data"]
                sdata = json.loads(s_data) if isinstance(s_data, str) else s_data
                opts = sdata.get("options", [])
                preview = " ".join([f"{o.get('emoji')} `{o.get('label')}`" for o in opts])
                desc = t("EMOJI_WIZ_SELECTED_DESC", guild_id=self.guild_id, name=current['name'], preview=preview)

        embed = discord.Embed(
            title=t("EMOJI_WIZ_TITLE", guild_id=self.guild_id),
            description=desc,
            color=discord.Color.purple()
        )
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @ui.select(placeholder="Válassz egy készletet...", row=0)
    async def set_select(self, interaction: discord.Interaction, select: ui.Select):
        if select.values[0] == "none": 
            await interaction.response.defer()
            return
        self.selected_set_id = select.values[0]
        await self.refresh_message(interaction)

    @ui.button(label="➕ Új szett", style=discord.ButtonStyle.green, row=1)
    async def add_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY", guild_id=self.guild_id), ephemeral=True)
        
        view = TemplateChoiceView(self)
        await interaction.response.send_message(t("LBL_CHOOSE_TEMPLATE", guild_id=self.guild_id), view=view, ephemeral=True)

    @ui.button(label="👯 Másolás", style=discord.ButtonStyle.secondary, row=1)
    async def clone_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY", guild_id=self.guild_id), ephemeral=True)
        if not self.selected_set_id:
            return await interaction.response.send_message(t("ERR_NO_CUSTOM_SETS", guild_id=self.guild_id), ephemeral=True)
        
        # Fetch actual data from DB
        sets = await database.get_emoji_sets(self.guild_id)
        current = next((s for s in sets if s["set_id"] == self.selected_set_id), None)
        if not current:
             return await interaction.response.send_message("❌ Set not found.", ephemeral=True)

        modal = EditEmojiSetModal(self, current)
        modal.title = t("BTN_CLONE", guild_id=self.guild_id)
        modal.is_clone = True # Mark as clone so on_submit generates a NEW set
        await interaction.response.send_modal(modal)

    @ui.button(label="⚙️ Szerkesztés", style=discord.ButtonStyle.primary, row=1)
    async def edit_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_set_id:
            return await interaction.response.send_message(t("ERR_NO_CUSTOM_SETS", guild_id=self.guild_id), ephemeral=True)
        
        # Fetch actual data from DB
        sets = await database.get_emoji_sets(self.guild_id)
        current = next((s for s in sets if s["set_id"] == self.selected_set_id), None)
        if not current:
             return await interaction.response.send_message("❌ Set not found.", ephemeral=True)

        await interaction.response.send_modal(EditEmojiSetModal(self, current))

    @ui.button(label="🗑️ Törlés", style=discord.ButtonStyle.danger, row=1)
    async def delete_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY", guild_id=self.guild_id), ephemeral=True)
        if not self.selected_set_id:
            return await interaction.response.send_message(t("ERR_SELECT_SET_DELETE", guild_id=self.guild_id), ephemeral=True)
        
        await database.delete_emoji_set(self.guild_id, self.selected_set_id)
        self.selected_set_id = None
        await interaction.response.send_message(t("MSG_SET_DELETED", guild_id=self.guild_id), ephemeral=True)
        await self.refresh_message(interaction)

class TemplateChoiceView(ui.View):
    def __init__(self, wizard_view):
        super().__init__(timeout=300)
        self.wizard_view = wizard_view
        
    @ui.select(placeholder="Válassz sablont...", options=[
        discord.SelectOption(label="Alap (Igen / Nem)", value="basic", emoji="✅"),
        discord.SelectOption(label="Raid (Tank / Heal / DPS)", value="raid", emoji="⚔️"),
        discord.SelectOption(label="Szavazás (👍 / 👎)", value="survey", emoji="📊"),
        discord.SelectOption(label="Üres szett", value="empty", emoji="🆕")
    ])
    async def select_template(self, interaction: discord.Interaction, select: ui.Select):
        template = select.values[0]
        
        # Pre-defined data for templates in the 6-column format
        templates = {
            "basic": "✅ | Résztveszek | Résztvevők | accepted | 0 | SPBG\n❓ | Talán | Bizonytalan | tentative | 0 | SB\n❌ | Nem jövök | - | declined | 0 | ER",
            "raid": "🛡️ | Tank | Tankok | tank | 2 | SPBG\n🏥 | Heal | Healerek | heal | 4 | SPBG\n🗡️ | DPS | DPS-ek | dps | 10 | SPBG\n❓ | Tartalék | Tartalékok | backup | 0 | SB\n❌ | Nem jövök | - | declined | 0 | ER",
            "survey": "👍 | Szuper | Szerintük jó | up | 0 | SPBG\n👎 | Rossz | Szerintük rossz | down | 0 | ER",
            "empty": ""
        }
        
        initial_text = templates.get(template, "")
        
        # Now show the CreateModal but passing the pre-filled text
        modal = CreateEmojiSetModal(self.wizard_view)
        # Note: We'll modify CreateEmojiSetModal to accept initial text if we want, 
        # but for simplicity let's just use EditEmojiSetModal with a dummy record
        dummy_record = {
            "set_id": "",
            "name": "",
            "data": json.dumps({
                "options": [], # Parsing logic will handle initial_text if we pass it correctly
                "buttons_per_row": 5,
                "show_mgmt": True
            })
        }
        edit_modal = EditEmojiSetModal(self.wizard_view, dummy_record)
        edit_modal.title = t("MODAL_NEW_SET_TITLE", guild_id=self.wizard_view.guild_id)
        edit_modal.opts_input.default = initial_text
        edit_modal.is_new = True 
        
        await interaction.response.send_modal(edit_modal)

class CreateEmojiSetModal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=t("MODAL_NEW_SET_TITLE", guild_id=wizard_view.guild_id))
        self.wizard_view = wizard_view
        self.name_input = ui.TextInput(label=t("LBL_SET_NAME", guild_id=wizard_view.guild_id), placeholder=t("PH_SET_NAME", guild_id=wizard_view.guild_id), required=True)
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        base_id = slugify(self.name_input.value)
        if not base_id:
            base_id = "custom_set"
            
        # Collision handling
        existing_sets = await database.get_emoji_sets(self.wizard_view.guild_id)
        existing_ids = [s["set_id"] for s in existing_sets]
        
        set_id = base_id
        counter = 2
        while set_id in existing_ids:
            set_id = f"{base_id}_{counter}"
            counter += 1

        data = {
            "options": [
                {"id": "accepted", "emoji": "✅", "label": t("LBL_YES", guild_id=self.wizard_view.guild_id)},
                {"id": "declined", "emoji": "❌", "label": t("LBL_NO", guild_id=self.wizard_view.guild_id)}
            ],
            "positive_count": 1,
            "buttons_per_row": 5
        }
        await database.save_emoji_set(self.wizard_view.guild_id, set_id, self.name_input.value, data)
        self.wizard_view.selected_set_id = set_id
        
        # Update the ORIGINAL message with the new list
        await self.wizard_view.refresh_message(interaction)

class EditEmojiSetModal(ui.Modal):
    def __init__(self, wizard_view, set_record):
        super().__init__(title=t("MODAL_EDIT_SET_TITLE", guild_id=wizard_view.guild_id))
        self.wizard_view = wizard_view
        self.set_id = set_record["set_id"]
        self.is_clone = False # Set by cloned button
        self.is_new = False # Set by template logic
        
        # Parse data
        s_data = set_record["data"]
        sdata = json.loads(s_data) if isinstance(s_data, str) else s_data
        opts = sdata.get("options", [])
        row_limit = sdata.get("buttons_per_row", 5)
        
        # Format options for text field: Emoji | Button | Embed | ID | Limit | Flags
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
            
            btn_lbl = o.get("label", "")
            list_lbl = o.get("list_label", "")
            
            lines.append(f"{o.get('emoji')} | {btn_lbl} | {list_lbl} | {o.get('id')} | {limit} | {flags}")
        
        opt_text = "\n".join(lines)
        
        show_mgmt_val = t("LBL_YES") if sdata.get("show_mgmt", True) else t("LBL_NO")
        
        self.name_input = ui.TextInput(label=t("LBL_SET_NAME", guild_id=wizard_view.guild_id), default=set_record["name"], required=True)
        self.opts_input = ui.TextInput(label=t("LBL_EDIT_OPTIONS", guild_id=wizard_view.guild_id), placeholder=t("PH_EDIT_OPTIONS", guild_id=wizard_view.guild_id), style=discord.TextStyle.paragraph, default=opt_text, required=True)
        self.row_limit = ui.TextInput(label=t("LBL_ROW_LIMIT", guild_id=wizard_view.guild_id), default=str(row_limit), required=True)
        self.mgmt_input = ui.TextInput(label=t("LBL_SHOW_MGMT", guild_id=wizard_view.guild_id), default=show_mgmt_val, placeholder=t("PH_SHOW_MGMT", guild_id=wizard_view.guild_id), required=True)
        
        self.add_item(self.name_input)
        self.add_item(self.opts_input)
        self.add_item(self.row_limit)
        self.add_item(self.mgmt_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Parse settings
        try:
            row_l = int(self.row_limit.value)
            if not (1 <= row_l <= 5): raise ValueError("Row limit must be 1-5")
        except:
             return await interaction.response.send_message("❌ Invalid number for Row Limit.", ephemeral=True)

        show_m = (self.mgmt_input.value.strip().lower() in [t("LBL_YES").lower(), "yes", "igen", "y", "i"])

        # Parse options
        new_opts = []
        positive_count = 0
        lines = self.opts_input.value.strip().split("\n")
        
        color_map = {"G": "success", "R": "danger", "B": "primary", "Y": "secondary"}
        
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line: continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2: 
                return await interaction.response.send_message(t("ERR_PARSING_LINE", guild_id=interaction.guild_id, line=i, error="Too few columns"), ephemeral=True)
            
            try:
                emoji = parts[0]
                btn_label = parts[1]
                list_label = parts[2] if len(parts) > 2 and parts[2] else ""
                oid = parts[3] if len(parts) > 3 and parts[3] else slugify(btn_label)
                
                # Limit
                limit = 0
                if len(parts) > 4:
                    try: limit = int(parts[4])
                    except: pass
                
                # Flags (S=Show in list, P=Positive, B/E/T=Style, G/R/B/Y=Color)
                flags = parts[5].upper() if len(parts) > 5 else "SPB"
                show_in_list = "S" in flags
                is_positive = "P" in flags
                if is_positive: positive_count += 1
                
                style = "both"
                if "E" in flags: style = "emoji"
                elif "T" in flags: style = "label"
                
                # Color
                btn_color = "secondary"
                for code, name in color_map.items():
                    if code in flags:
                        btn_color = name
                        break
                
                new_opts.append({
                    "id": oid, 
                    "emoji": emoji, 
                    "label": btn_label, 
                    "list_label": list_label,
                    "max_slots": limit,
                    "button_style": style,
                    "button_color": btn_color,
                    "show_in_list": show_in_list,
                    "positive": is_positive
                })
            except Exception as e:
                return await interaction.response.send_message(t("ERR_PARSING_LINE", guild_id=interaction.guild_id, line=i, error=str(e)), ephemeral=True)

        if not new_opts:
            return await interaction.response.send_message("❌ You must have at least one icon.", ephemeral=True)

        new_data = {
            "options": new_opts,
            "positive_count": positive_count,
            "buttons_per_row": row_l,
            "show_mgmt": show_m
        }

        # Handling ID for cloning or new template-based sets
        target_id = self.set_id
        if getattr(self, "is_clone", False) or getattr(self, "is_new", False):
            target_id = slugify(self.name_input.value)
            # Check for collisions
            sets = await database.get_emoji_sets(interaction.guild_id)
            existing_ids = [s["set_id"] for s in sets]
            
            base_id = target_id
            counter = 2
            while target_id in existing_ids:
                target_id = f"{base_id}_{counter}"
                counter += 1
        
        await database.save_emoji_set(self.wizard_view.guild_id, target_id, self.name_input.value, new_data)
        
        msg = t("MSG_SET_CLONED") if getattr(self, "is_clone", False) else "✅ Done!"
        await interaction.response.send_message(msg, ephemeral=True)
        await self.wizard_view.refresh_message(interaction)

class EditGlobalEmojiSetModal(EditEmojiSetModal):
    def __init__(self, wizard_view, set_record):
        super().__init__(wizard_view, set_record)
        self.title = t("LBL_GLOBAL_TITLE")

    async def on_submit(self, interaction: discord.Interaction):
        # We reuse the parsing logic but save to the GLOBAL table
        # We need to copy-paste the core parsing logic or refactor it. 
        # For simplicity and to avoid deep inheritance issues in discord.py Modals, I'll repeat the core parsing but target the global save.
        
        # Parse settings
        try:
            row_l = int(self.row_limit.value)
        except:
             return await interaction.response.send_message("❌ Invalid number for Row Limit.", ephemeral=True)

        lines = self.opts_input.value.strip().split("\n")
        new_opts = []
        positive_count = 0
        color_map = {"G": "success", "R": "danger", "B": "primary", "Y": "secondary"}

        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line: continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2: 
                return await interaction.response.send_message(t("ERR_PARSING_LINE", guild_id=interaction.guild_id, line=i, error="Too few columns"), ephemeral=True)
            
            try:
                emoji, btn_label = parts[0], parts[1]
                list_label = parts[2] if len(parts) > 2 and parts[2] else ""
                oid = parts[3] if len(parts) > 3 and parts[3] else slugify(btn_label)
                limit = 0
                if len(parts) > 4:
                    try: limit = int(parts[4])
                    except: pass
                flags = parts[5].upper() if len(parts) > 5 else "SPB"
                show_in_list = "S" in flags
                is_positive = "P" in flags
                if is_positive: positive_count += 1
                style = "emoji" if "E" in flags else ("label" if "T" in flags else "both")
                btn_color = "secondary"
                for code, name in color_map.items():
                    if code in flags: btn_color = name; break
                
                new_opts.append({
                    "id": oid, "emoji": emoji, "label": btn_label, "list_label": list_label,
                    "max_slots": limit, "button_style": style, "button_color": btn_color,
                    "show_in_list": show_in_list, "positive": is_positive
                })
            except Exception as e:
                return await interaction.response.send_message(t("ERR_PARSING_LINE", guild_id=interaction.guild_id, line=i, error=str(e)), ephemeral=True)

        new_data = {
            "options": new_opts,
            "positive_count": positive_count,
            "buttons_per_row": row_l,
            "show_mgmt": True
        }

        tid = self.set_id
        if getattr(self, "is_new", False):
            tid = slugify(self.name_input.value)

        await database.save_global_emoji_set(tid, self.name_input.value, new_data)
        
        # Refresh global cache
        from cogs.event_ui import load_custom_sets
        await load_custom_sets()
        
        await interaction.response.send_message(t("MSG_GLOBAL_SAVED"), ephemeral=True)
        await self.wizard_view.refresh_message(interaction)

class GlobalEmojiWizardView(EmojiWizardView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id)
        self.selected_set_id = None

    async def get_sets_options(self):
        sets = await database.get_all_global_emoji_sets()
        if not sets:
            return [discord.SelectOption(label="No sets found", value="none")]
        return [discord.SelectOption(label=s["name"], value=s["set_id"]) for s in sets]

    @ui.button(label="➕ Új Globális", style=discord.ButtonStyle.green, row=1)
    async def add_btn(self, interaction: discord.Interaction, button: ui.Button):
        # Global templates or empty
        modal = EditGlobalEmojiSetModal(self, {"set_id": "", "name": "", "data": "{}"})
        modal.title = "Új Globális Szett"
        modal.is_new = True
        await interaction.response.send_modal(modal)

    @ui.button(label="⚙️ Szerkesztés", style=discord.ButtonStyle.primary, row=1)
    async def edit_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_set_id:
            return await interaction.response.send_message("❌ Select a set first.", ephemeral=True)
        sets = await database.get_all_global_emoji_sets()
        current = next((s for s in sets if s["set_id"] == self.selected_set_id), None)
        await interaction.response.send_modal(EditGlobalEmojiSetModal(self, current))

    @ui.button(label="🗑️ Törlés", style=discord.ButtonStyle.danger, row=1)
    async def delete_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_set_id:
            return await interaction.response.send_message("❌ Select a set first.", ephemeral=True)
        await database.delete_global_emoji_set(self.selected_set_id)
        from cogs.event_ui import load_custom_sets
        await load_custom_sets()
        await interaction.response.send_message(t("MSG_GLOBAL_DELETED"), ephemeral=True)
        await self.refresh_message(interaction)

    async def refresh_message(self, interaction: discord.Interaction):
        options = await self.get_sets_options()
        self.clear_items()
        
        select = ui.Select(placeholder="Válassz globális szettet...", options=options, custom_id="global_set_select")
        async def select_callback(interaction):
            self.selected_set_id = select.values[0]
            await interaction.response.defer()
        select.callback = select_callback
        self.add_item(select)
        
        self.add_item(self.add_btn)
        self.add_item(self.edit_btn)
        self.add_item(self.delete_btn)
        
        embed = discord.Embed(title=t("LBL_GLOBAL_TITLE"), description=t("LBL_GLOBAL_EMOJI_DESC"), color=discord.Color.blue())
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

class EmojiWizard(commands.GroupCog, name="admin"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="emojis", description="Manage customized emoji sets for this server")
    async def manage_emojis(self, interaction: discord.Interaction):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY", guild_id=interaction.guild_id), ephemeral=True)
        
        view = EmojiWizardView(self.bot, interaction.guild_id)
        # Note: we need to call prepare now or in the view
        await view.prepare()
        
        embed = discord.Embed(
            title="✨ Emoji Wizard",
            description="Manage your server's custom emoji sets here.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="global-emojis", description="Manage system-wide global emoji sets (Owner Only)")
    async def manage_global_emojis(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message(t("ERR_OWNER_ONLY"), ephemeral=True)
        
        view = GlobalEmojiWizardView(self.bot, interaction.guild_id)
        await view.refresh_message(interaction)

async def setup(bot):
    await bot.add_cog(EmojiWizard(bot))
