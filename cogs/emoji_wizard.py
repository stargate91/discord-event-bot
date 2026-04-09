import discord
from discord import ui
import json
import database
from utils.i18n import t
from utils.auth import is_admin

class EmojiWizardView(ui.View):
    """Main management console for emoji sets."""
    def __init__(self, bot, guild_id):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id
        self.selected_set_id = None

    async def refresh_message(self, interaction: discord.Interaction):
        sets = await database.get_emoji_sets(self.guild_id)
        
        embed = discord.Embed(
            title="✨ Emoji & Role Kezelő",
            description="Válaszd ki a szerkeszteni kívánt készletet, vagy hozz létre újat.",
            color=discord.Color.purple()
        )
        
        # Build select options
        options = []
        for s in sets:
            sdata = json.loads(s["data"]) if isinstance(s["data"], str) else s["data"]
            opts = sdata.get("options", [])
            preview = " ".join([o.get("emoji") or "?" for o in opts[:3]])
            options.append(discord.SelectOption(
                label=s["name"], 
                value=s["set_id"], 
                description=f"{preview}...",
                default=(s["set_id"] == self.selected_set_id)
            ))
            
        if not options:
            options.append(discord.SelectOption(label="Nincs egyedi szett", value="none", disabled=True))

        self.set_select.options = options
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @ui.select(placeholder="Válassz egy készletet...", row=0)
    async def set_select(self, interaction: discord.Interaction, select: ui.Select):
        if select.values[0] == "none": return
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
            return await interaction.response.send_message("Válassz ki egy szettet a szerkesztéshez!", ephemeral=True)
        
        # Open detailed editor
        await interaction.response.send_message("🚧 Az opciók részletes szerkesztése hamarosan érkezik. Használd a /emoji set create parancsot komplex szettekhez.", ephemeral=True)

    @ui.button(label="🗑️ Törlés", style=discord.ButtonStyle.danger, row=1)
    async def delete_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await is_admin(interaction):
            return await interaction.response.send_message(t("ERR_ADMIN_ONLY", guild_id=self.guild_id), ephemeral=True)
        if not self.selected_set_id:
            return await interaction.response.send_message("Válassz ki egy szettet a törléshez!", ephemeral=True)
        
        await database.delete_emoji_set(self.guild_id, self.selected_set_id)
        self.selected_set_id = None
        await interaction.response.send_message(f"✅ Szett törölve.", ephemeral=True)
        await self.refresh_message(interaction)

class CreateEmojiSetModal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title="Új Emoji Szett")
        self.wizard_view = wizard_view
        self.name_input = ui.TextInput(label="Szett neve", placeholder="Pl. Raid Csapat", required=True)
        self.id_input = ui.TextInput(label="Azonosító (angol, kisbetű)", placeholder="Pl. raid_set", required=True)
        self.add_item(self.name_input)
        self.add_item(self.id_input)

    async def on_submit(self, interaction: discord.Interaction):
        set_id = self.id_input.value.lower().strip().replace(" ", "_")
        # Default empty data
        data = {
            "options": [
                {"id": "accepted", "emoji": "✅", "label": "Igen"},
                {"id": "declined", "emoji": "❌", "label": "Nem"}
            ],
            "positive_count": 1,
            "buttons_per_row": 5
        }
        await database.save_emoji_set(self.wizard_view.guild_id, set_id, self.name_input.value, data)
        self.wizard_view.selected_set_id = set_id
        await interaction.response.send_message(f"✅ Szett létrehozva: {self.name_input.value}", ephemeral=True)
        await self.wizard_view.refresh_message(interaction)
