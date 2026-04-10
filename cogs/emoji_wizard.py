import discord
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
        await interaction.response.send_modal(CreateEmojiSetModal(self))

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
        
        # Parse data
        s_data = set_record["data"]
        sdata = json.loads(s_data) if isinstance(s_data, str) else s_data
        opts = sdata.get("options", [])
        pos_count = sdata.get("positive_count", 1)
        row_limit = sdata.get("buttons_per_row", 5)
        
        # Format options for text field
        opt_text = "\n".join([f"{o.get('emoji')} | {o.get('label')} | {o.get('id')}" for o in opts])
        
        self.name_input = ui.TextInput(label=t("LBL_SET_NAME", guild_id=wizard_view.guild_id), default=set_record["name"], required=True)
        self.opts_input = ui.TextInput(label=t("LBL_EDIT_OPTIONS", guild_id=wizard_view.guild_id), placeholder=t("PH_EDIT_OPTIONS", guild_id=wizard_view.guild_id), style=discord.TextStyle.paragraph, default=opt_text, required=True)
        self.pos_count = ui.TextInput(label=t("LBL_POS_COUNT", guild_id=wizard_view.guild_id), default=str(pos_count), required=True)
        self.row_limit = ui.TextInput(label=t("LBL_ROW_LIMIT", guild_id=wizard_view.guild_id), default=str(row_limit), required=True)
        
        self.add_item(self.name_input)
        self.add_item(self.opts_input)
        self.add_item(self.pos_count)
        self.add_item(self.row_limit)

    async def on_submit(self, interaction: discord.Interaction):
        # Parse settings
        try:
            pos_c = int(self.pos_count.value)
            row_l = int(self.row_limit.value)
            if not (1 <= row_l <= 5): raise ValueError("Row limit must be 1-5")
        except:
             return await interaction.response.send_message("❌ Invalid numbers for Count or Row Limit.", ephemeral=True)

        # Parse options
        new_opts = []
        lines = self.opts_input.value.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line: continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2: continue
            
            emoji = parts[0]
            label = parts[1]
            oid = parts[2] if len(parts) > 2 else slugify(label)
            
            new_opts.append({"id": oid, "emoji": emoji, "label": label})

        if not new_opts:
            return await interaction.response.send_message("❌ You must have at least one icon.", ephemeral=True)

        new_data = {
            "options": new_opts,
            "positive_count": pos_c,
            "buttons_per_row": row_l
        }
        
        await database.save_emoji_set(self.wizard_view.guild_id, self.set_id, self.name_input.value, new_data)
        await interaction.response.send_message("✅ Emoji set updated successfully.", ephemeral=True)
        await self.wizard_view.refresh_message(interaction)
