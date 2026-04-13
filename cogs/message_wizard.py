import discord
from utils.emojis import SHIELD
from discord import ui
import database
from utils.i18n import t, load_guild_translations, CATEGORIES
from utils.auth import is_admin

class MessageWizardView(ui.LayoutView):
    """Admin UI to manage message overrides."""
    def __init__(self, bot, guild_id, selected_key=None):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id
        # Default to first category available
        self.selected_category = "Notifications"
        self.selected_key = selected_key

    async def prepare(self):
        """Prepare the initial set of options for the wizard."""
        pass # Not needed for LayoutView caching anymore, we do it in refresh

    async def refresh_message(self, interaction: discord.Interaction):
        await load_guild_translations(self.guild_id)
        
        new_view = MessageWizardView(self.bot, self.guild_id, selected_key=self.selected_key)
        new_view.clear_items()
        
        desc = t("MSG_WIZ_DESC", guild_id=self.guild_id)
        
        if new_view.selected_key:
            friendly_name = t(f"KEY_{new_view.selected_key}", guild_id=self.guild_id)
            if friendly_name == f"KEY_{new_view.selected_key}": friendly_name = new_view.selected_key
            
            current_val = t(new_view.selected_key, guild_id=self.guild_id)
            preview = current_val.replace("{user_id}", f"<@{interaction.user.id}>")\
                                 .replace("{title}", "Példa Esemény")\
                                 .replace("{role}", "Tank")\
                                 .replace("{emoji}", SHIELD)\
                                 .replace("{status}", "AKTÍV")
            
            desc += f"\n\n**🔍 {t('LBL_PREVIEW', guild_id=self.guild_id)} ({friendly_name}):**\n> {preview}"
            desc += f"\n\n**💡 {t('LBL_VARIABLES', guild_id=self.guild_id)}:**\n`{{title}}`, `{{user_id}}`, `{{role}}`, `{{emoji}}`, `{{status}}`"

        # Key Select Dropdown (in a container)
        keys = CATEGORIES.get(new_view.selected_category, [])
        options = []
        for k in keys:
            friendly_name = t(f"KEY_{k}", guild_id=self.guild_id)
            if friendly_name == f"KEY_{k}": friendly_name = k
            
            current_val = t(k, guild_id=self.guild_id)
            is_overridden = (current_val != t(k))
            label = f"{'🔹 ' if is_overridden else ''}{friendly_name}"
            options.append(discord.SelectOption(
                label=label[:100], 
                value=k, 
                description=current_val[:100],
                default=(k == new_view.selected_key)
            ))

        if not options:
            options.append(discord.SelectOption(label=t("ERR_NO_KEYS_AVAILABLE", guild_id=self.guild_id), value="none", disabled=True))
            
        key_select = ui.Select(placeholder=t("SEL_KEY", guild_id=self.guild_id), options=options)
        async def key_callback(it: discord.Interaction):
            if key_select.values[0] == "none": return await it.response.defer()
            new_view.selected_key = key_select.values[0]
            await new_view.refresh_message(it)
        key_select.callback = key_callback

        row_select = ui.ActionRow(key_select)

        # Buttons
        edit_btn = ui.Button(label=t("BTN_EDIT", guild_id=self.guild_id), style=discord.ButtonStyle.primary)
        async def edit_cb(it: discord.Interaction):
            if not await is_admin(it):
                return await it.response.send_message(t("ERR_ADMIN_ONLY", guild_id=new_view.guild_id), ephemeral=True)
            if not new_view.selected_key:
                return await it.response.send_message(t("ERR_SELECT_KEY_FIRST", guild_id=new_view.guild_id), ephemeral=True)
            
            current_val = t(new_view.selected_key, guild_id=new_view.guild_id)
            await it.response.send_modal(MessageEditModal(new_view, new_view.selected_key, current_val, new_view.guild_id))
        edit_btn.callback = edit_cb

        reset_btn = ui.Button(label=t("BTN_RESET_DEFAULT", guild_id=self.guild_id), style=discord.ButtonStyle.secondary) # Note: can be localized too
        async def reset_cb(it: discord.Interaction):
            if not await is_admin(it):
                return await it.response.send_message(t("ERR_ADMIN_ONLY", guild_id=new_view.guild_id), ephemeral=True)
            if not new_view.selected_key:
                return await it.response.send_message(t("ERR_SELECT_KEY_RESET", guild_id=new_view.guild_id), ephemeral=True)
            
            await database.delete_guild_translation(new_view.guild_id, new_view.selected_key)
            await load_guild_translations(new_view.guild_id)
            await new_view.refresh_message(it)
        reset_btn.callback = reset_cb

        row_btns = ui.ActionRow(edit_btn, reset_btn)

        container_items = [
            ui.TextDisplay(f"### {t('MSG_WIZ_TITLE', guild_id=new_view.guild_id)}"),
            ui.Separator(),
            ui.TextDisplay(desc),
            ui.Separator(),
            row_select,
            row_btns
        ]
        
        container = ui.Container(*container_items, accent_color=0x4169E1)
        new_view.add_item(container)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embeds=[], view=new_view)
        elif interaction.type in (discord.InteractionType.component, discord.InteractionType.modal_submit):
            await interaction.response.edit_message(embeds=[], view=new_view)
        else:
            await interaction.response.send_message(view=new_view, ephemeral=True)


class MessageEditModal(ui.Modal):
    def __init__(self, wizard_view, key, current_val, guild_id):
        super().__init__(title=f"{t('BTN_EDIT', guild_id=guild_id)}: {key}")
        self.wizard_view = wizard_view
        self.key = key
        self.guild_id = guild_id
        
        self.text_input = ui.TextInput(
            label=f"{t('LBL_CUSTOM_TEXT', guild_id=guild_id)} ({t('LBL_VARIABLES', guild_id=guild_id)}: {{{{user_id}}}}, {{{{title}}}}...)",
            default=current_val,
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await database.save_guild_translation(self.guild_id, self.key, self.text_input.value)
        await load_guild_translations(self.wizard_view.guild_id)
        await interaction.followup.send(t("MSG_KEY_SAVED", guild_id=self.wizard_view.guild_id, key=self.key), ephemeral=True)
        await self.wizard_view.refresh_message(interaction)
