import discord
from discord import ui
import database
from utils.i18n import t, load_guild_translations, CATEGORIES
from utils.auth import is_admin

class MessageWizardView(ui.View):
    """Admin UI to manage message overrides."""
    def __init__(self, bot, guild_id):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id
        self.selected_category = "Embed"
        self.selected_key = None
    async def prepare(self):
        """Prepare the initial set of options for the wizard."""
        await load_guild_translations(self.guild_id)
        
        # Populate key_select options based on default category (Embed)
        keys = CATEGORIES.get(self.selected_category, [])
        options = []
        for k in keys:
            current_val = t(k, guild_id=self.guild_id)
            is_overridden = (current_val != t(k))
            label = f"{'🔹 ' if is_overridden else ''}{k}"
            options.append(discord.SelectOption(
                label=label[:100], 
                value=k, 
                description=current_val[:100]
            ))

        if not options:
            options.append(discord.SelectOption(label=t("ERR_NO_KEYS_AVAILABLE", guild_id=self.guild_id), value="none", disabled=True))
            
        self.key_select.options = options

    async def refresh_message(self, interaction: discord.Interaction):
        # Ensure cache is fresh for this view
        await load_guild_translations(self.guild_id)
        
        embed = discord.Embed(
            title=t("MSG_WIZ_TITLE", guild_id=self.guild_id),
            description=t("MSG_WIZ_DESC", guild_id=self.guild_id),
            color=discord.Color.blue()
        )
        
        # 1. Category Select
        # 2. Key Select based on Category
        
        keys = CATEGORIES.get(self.selected_category, [])
        options = []
        for k in keys:
            current_val = t(k, guild_id=self.guild_id)
            is_overridden = (current_val != t(k)) # Simplified check
            label = f"{'🔹 ' if is_overridden else ''}{k}"
            options.append(discord.SelectOption(
                label=label[:100], 
                value=k, 
                description=current_val[:100],
                default=(k == self.selected_key)
            ))

        if not options:
            options.append(discord.SelectOption(label=t("ERR_NO_KEYS_AVAILABLE", guild_id=self.guild_id), value="none", disabled=True))
            
        self.key_select.options = options
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @ui.select(row=0, options=[
        discord.SelectOption(label=cat, value=cat) for cat in CATEGORIES.keys()
    ])
    async def category_select(self, interaction: discord.Interaction, select: ui.Select):
        self.selected_category = select.values[0]
        self.selected_key = None
        await self.refresh_message(interaction)

    @ui.select(row=1)
    async def key_select(self, interaction: discord.Interaction, select: ui.Select):
        if select.values[0] == "none": return
        self.selected_key = select.values[0]
        await self.refresh_message(interaction)

    @ui.button(label="BTN_EDIT", style=discord.ButtonStyle.primary, row=2)
    async def edit_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY", guild_id=self.guild_id), ephemeral=True)
        if not self.selected_key:
            return await interaction.response.send_message(t("ERR_SELECT_KEY_FIRST", guild_id=self.guild_id), ephemeral=True)
        
        current_val = t(self.selected_key, guild_id=self.guild_id)
        await interaction.response.send_modal(MessageEditModal(self, self.selected_key, current_val, self.guild_id))

    @ui.button(label="Reset Default", style=discord.ButtonStyle.secondary, row=2)
    async def reset_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY", guild_id=self.guild_id), ephemeral=True)
        if not self.selected_key:
            return await interaction.response.send_message(t("ERR_SELECT_KEY_RESET", guild_id=self.guild_id), ephemeral=True)
        
        await database.delete_translation(self.guild_id, self.selected_key)
        await load_guild_translations(self.guild_id)
        await interaction.response.send_message(t("MSG_RESET_SUCCESS_KEY", guild_id=self.guild_id, key=self.selected_key), ephemeral=True)
        await self.refresh_message(interaction)

class MessageEditModal(ui.Modal):
    def __init__(self, wizard_view, key, current_val, guild_id):
        super().__init__(title=f"{t('BTN_EDIT', guild_id=guild_id)}: {key}")
        self.wizard_view = wizard_view
        self.key = key
        self.guild_id = guild_id
        
        self.text_input = ui.TextInput(
            label=t("LBL_CUSTOM_TEXT", guild_id=guild_id),
            default=current_val,
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await database.save_translation(self.guild_id, self.key, self.text_input.value)
        # Refresh cache
        await load_guild_translations(self.wizard_view.guild_id)
        await interaction.followup.send(t("MSG_KEY_SAVED", guild_id=self.wizard_view.guild_id, key=self.key), ephemeral=True)
        await self.wizard_view.refresh_message(interaction)
