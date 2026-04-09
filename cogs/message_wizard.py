import discord
from discord import ui
import database
from utils.i18n import t, load_guild_translations
from utils.auth import is_admin

CATEGORIES = {
    "Embed": [
        "EMBED_FOOTER", "LBL_CREATED_BY", "EMBED_START_TIME", "EMBED_RECURRENCE",
        "EMBED_ACC", "EMBED_DEC", "EMBED_TEN", "EMBED_NONE", "EMBED_FULL", "EMBED_WAITLIST"
    ],
    "RSVP Labels": [
        "BTN_ACCEPT", "BTN_DECLINE", "BTN_TENTATIVE", 
        "RSVP_ACCEPTED", "RSVP_DECLINED", "RSVP_TENTATIVE"
    ],
    "Wizard UI": [
        "WIZARD_TITLE", "BTN_STEP_1", "BTN_STEP_2", "BTN_SUBMIT", 
        "BTN_SAVE_PREVIEW", "BTN_PUBLISH"
    ],
    "Status & Tags": [
        "TAG_CANCELLED", "TAG_POSTPONED", "TAG_DELETED", "TAG_PAST"
    ],
    "Reminders & Alerts": [
        "MSG_REM_DESC", "MSG_REC_ALERT", "MSG_EV_CREATED_PUBLIC", "MSG_EV_CREATED_EPHEMERAL"
    ]
}

class MessageWizardView(ui.View):
    """Admin UI to manage message overrides."""
    def __init__(self, bot, guild_id):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id
        self.selected_category = "Embed"
        self.selected_key = None

    async def refresh_message(self, interaction: discord.Interaction):
        # Ensure cache is fresh for this view
        await load_guild_translations(self.guild_id)
        
        embed = discord.Embed(
            title="💬 Message Wizard",
            description=f"Válaszd ki a kategóriát és a szöveget, amit módosítani szeretnél.\n\n**Kategória:** {self.selected_category}",
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
            options.append(discord.SelectOption(label="Nincs elérhető kulcs", value="none", disabled=True))
            
        self.key_select.options = options
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @ui.select(placeholder="Kategória választása...", row=0, options=[
        discord.SelectOption(label=cat, value=cat) for cat in CATEGORIES.keys()
    ])
    async def category_select(self, interaction: discord.Interaction, select: ui.Select):
        self.selected_category = select.values[0]
        self.selected_key = None
        await self.refresh_message(interaction)

    @ui.select(placeholder="Szöveg (Kulcs) választása...", row=1)
    async def key_select(self, interaction: discord.Interaction, select: ui.Select):
        if select.values[0] == "none": return
        self.selected_key = select.values[0]
        await self.refresh_message(interaction)

    @ui.button(label="📝 Szerkesztés", style=discord.ButtonStyle.primary, row=2)
    async def edit_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY", guild_id=self.guild_id), ephemeral=True)
        if not self.selected_key:
            return await interaction.response.send_message("Válassz ki egy szöveget a szerkesztéshez!", ephemeral=True)
        
        await interaction.response.send_modal(MessageEditModal(self, self.selected_key))

    @ui.button(label="Reset Default", style=discord.ButtonStyle.secondary, row=2)
    async def reset_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY", guild_id=self.guild_id), ephemeral=True)
        if not self.selected_key:
            return await interaction.response.send_message("Válassz ki egy szöveget!", ephemeral=True)
        
        await database.delete_translation(self.guild_id, self.selected_key)
        await load_guild_translations(self.guild_id)
        await interaction.response.send_message(f"✅ Visszaállítva alaphelyzetbe: `{self.selected_key}`", ephemeral=True)
        await self.refresh_message(interaction)

class MessageEditModal(ui.Modal):
    def __init__(self, wizard_view, key):
        super().__init__(title=f"Szerkesztés: {key}")
        self.wizard_view = wizard_view
        self.key = key
        
        default_val = t(key)
        current_val = t(key, guild_id=wizard_view.guild_id)
        
        self.text_input = ui.TextInput(
            label="Egyedi szöveg",
            placeholder=f"Alap: {default_val[:50]}...",
            default=current_val,
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        await database.save_translation(self.wizard_view.guild_id, self.key, self.text_input.value)
        # Refresh cache
        await load_guild_translations(self.wizard_view.guild_id)
        await interaction.response.send_message(f"✅ Mentve: `{self.key}`", ephemeral=True)
        await self.wizard_view.refresh_message(interaction)
