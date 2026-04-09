import discord
from discord.ext import commands
from discord import app_commands
import database
import re
import uuid
from utils.logger import log
from utils.i18n import t

class EmojiSetCommands(commands.GroupCog, name="emoji"):
    # We create a nested group 'set' so commands become /emoji set <name>
    set_group = app_commands.Group(name="set", description="Manage emoji sets")

    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    def is_admin(self, interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        # Check for admin role from config if available
        try:
            from utils.jsonc import load_jsonc
            config_data = load_jsonc('config.json')
            admin_role_id = config_data.get("admin_role_id")
            if admin_role_id and discord.utils.get(interaction.user.roles, id=admin_role_id):
                return True
        except:
            pass
        return False

    @set_group.command(name="create", description="Create a custom emoji set for events")
    @app_commands.describe(
        name="Name of the emoji set",
        positive_count="How many of the first options count as 'positive' RSVP",
        options="Format: emoji:button_label:list_label:limit | ...",
        per_row="Buttons per row (1-5)"
    )
    async def create_set(self, interaction: discord.Interaction, name: str, positive_count: int, options: str, per_row: int = 5):
        if not self.is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return

        # Simple ID from name
        set_id = re.sub(r'[^a-zA-Z0-9]', '_', name).lower()[:20] + "_" + str(uuid.uuid4())[:4]
        
        parsed_options = []
        option_parts = [p.strip() for p in options.split("|")]
        
        for idx, part in enumerate(option_parts):
            if not part: continue
            
            # Split by : but handle case where there might be more colons (unlikely for labels but possible for custom emojis if not careful)
            # Actually Discord emoji is <:name:id>, so we need to be careful.
            # We'll expect 3 parts: emoji, button, list
            # We'll use a regex or a smarter split.
            
            # Match <...:id> or single character or word
            # For simplicity, we'll try to find the : separators.
            # If the part starts with <, we find the first : NOT inside <>
            
            sub_parts = [s.strip() for s in part.split(":")]
            
            # Handle potential custom emojis that contain colons
            # Actually, a custom emoji is like <:name:id>. 
            # If we split by :, we get ['', 'name', 'id>']
            # Let's use a more robust split for the first part.
            
            emoji_str = ""
            button_label = ""
            list_label = ""
            
            if len(sub_parts) >= 1:
                emoji_str = sub_parts[0]
            if len(sub_parts) >= 2:
                button_label = sub_parts[1]
            if len(sub_parts) >= 3:
                list_label = sub_parts[2]
            
            # If sub_parts[0] was part of a custom emoji, it might be messed up.
            # Let's try to detect custom emoji at the start.
            custom_emoji_match = re.search(r'<(a?):([a-zA-Z0-9_]+):([0-9]+)>', part)
            if custom_emoji_match:
                emoji_str = custom_emoji_match.group(0)
                remaining = part[custom_emoji_match.end():].lstrip(':').strip()
                label_parts = [s.strip() for s in remaining.split(":")]
                button_label = label_parts[0] if len(label_parts) >= 1 else ""
                list_label = label_parts[1] if len(label_parts) >= 2 else ""
                max_slots_str = label_parts[2] if len(label_parts) >= 3 else None
            else:
                emoji_str = sub_parts[0] if len(sub_parts) >= 1 else ""
                button_label = sub_parts[1] if len(sub_parts) >= 2 else ""
                list_label = sub_parts[2] if len(sub_parts) >= 3 else ""
                max_slots_str = sub_parts[3] if len(sub_parts) >= 4 else None

            if not emoji_str and not button_label:
                continue
                
            if not list_label:
                list_label = button_label # Default to button label if empty
            
            max_slots = None
            if max_slots_str:
                try:
                    max_slots = int(max_slots_str)
                except:
                    max_slots = None

            parsed_options.append({
                "id": f"custom_{idx}",
                "emoji": emoji_str,
                "label": button_label,
                "list_label": list_label,
                "max_slots": max_slots
            })

        if not parsed_options:
            await interaction.response.send_message("Hiba: Nem sikerült feldolgozni az opciókat. Formátum: `emoji:gomb:lista:limit | ...`", ephemeral=True)
            return

        # Cap per_row between 1 and 5
        buttons_per_row = max(1, min(5, per_row))

        config = {
            "options": parsed_options,
            "positive_count": positive_count,
            "buttons_per_row": buttons_per_row,
            "show_mgmt": False # As requested
        }

        await database.save_custom_emoji_set(set_id, name, config, interaction.user.id)
        await interaction.response.send_message(f"✅ Sikerült menteni a készletet: **{name}** (ID: `{set_id}`)", ephemeral=True)

    @set_group.command(name="list", description="List all custom emoji sets")
    async def list_sets(self, interaction: discord.Interaction):
        if not self.is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return

        from cogs.event_ui import CUSTOM_ICON_SETS
        
        if not CUSTOM_ICON_SETS:
            await interaction.response.send_message("Nincsenek egyedi szettek.", ephemeral=True)
            return

        embed = discord.Embed(title="Egyedi Emoji Készletek", color=discord.Color.blue())
        for set_id, data in CUSTOM_ICON_SETS.items():
            opts = data.get("options", [])
            # Try to find a name for the set (config might have it, or we use set_id)
            # Database sets have a name field, but CUSTOM_ICON_SETS only stores the 'data' part usually.
            # Wait, let's check load_custom_sets again.
            
            preview = " ".join([o.get("emoji") or o.get("label") or "?" for o in opts[:5]])
            embed.add_field(name=f"`{set_id}`", value=f"Opciók: {preview}...", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @set_group.command(name="delete", description="Delete a custom emoji set")
    @app_commands.describe(set_id="The ID of the set to delete")
    async def delete_set(self, interaction: discord.Interaction, set_id: str):
        if not self.is_admin(interaction):
            await interaction.response.send_message(t("ERR_ADMIN_ONLY"), ephemeral=True)
            return

        existing = await database.get_custom_emoji_set(set_id)
        if not existing:
            await interaction.response.send_message("Nincs ilyen készlet.", ephemeral=True)
            return

        await database.delete_custom_emoji_set(set_id)
        await interaction.response.send_message(f"✅ Készlet törölve: `{set_id}`", ephemeral=True)

    @delete_set.autocomplete("set_id")
    async def delete_set_autocomplete(self, interaction: discord.Interaction, current: str):
        sets = await database.get_all_custom_emoji_sets()
        return [
            app_commands.Choice(name=f"{s['name']} ({s['set_id']})", value=s['set_id'])
            for s in sets if current.lower() in s['name'].lower() or current.lower() in s['set_id'].lower()
        ][:25]

async def setup(bot):
    await bot.add_cog(EmojiSetCommands(bot))
