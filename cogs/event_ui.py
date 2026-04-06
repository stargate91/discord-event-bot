import discord
from discord.ext import commands
import database
from utils.i18n import t

class DynamicEventView(discord.ui.View):
    def __init__(self, bot, event_id: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.event_id = event_id

        # Accept
        accept_btn = discord.ui.Button(label=t("BTN_ACCEPT"), style=discord.ButtonStyle.success, emoji="✅", custom_id=f"accept_{event_id}")
        accept_btn.callback = self.accept_callback
        self.add_item(accept_btn)

        # Decline
        decline_btn = discord.ui.Button(label=t("BTN_DECLINE"), style=discord.ButtonStyle.danger, emoji="❌", custom_id=f"decline_{event_id}")
        decline_btn.callback = self.decline_callback
        self.add_item(decline_btn)

        # Tentative
        tentative_btn = discord.ui.Button(label=t("BTN_TENTATIVE"), style=discord.ButtonStyle.secondary, emoji="❔", custom_id=f"tentative_{event_id}")
        tentative_btn.callback = self.tentative_callback
        self.add_item(tentative_btn)

        # Delete
        delete_btn = discord.ui.Button(label=t("BTN_DELETE"), style=discord.ButtonStyle.danger, emoji="🗑️", custom_id=f"delete_{event_id}", row=1)
        delete_btn.callback = self.delete_callback
        self.add_item(delete_btn)

    async def accept_callback(self, interaction: discord.Interaction):
        await self.handle_rsvp(interaction, "accepted")

    async def decline_callback(self, interaction: discord.Interaction):
        await self.handle_rsvp(interaction, "declined")

    async def tentative_callback(self, interaction: discord.Interaction):
        await self.handle_rsvp(interaction, "tentative")

    async def delete_callback(self, interaction: discord.Interaction):
        event_dict = await database.get_event(self.event_id)
        if not event_dict:
            await interaction.response.send_message(t("ERR_EV_NOT_FOUND"), ephemeral=True)
            return
            
        if interaction.user.id != event_dict["creator_id"] and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(t("ERR_NO_PERM"), ephemeral=True)
            return

        await interaction.response.defer()
        await database.delete_event(self.event_id)
        
        embed = interaction.message.embeds[0]
        embed.title = f"{t('TAG_DELETED')} {embed.title}"
        embed.color = discord.Color.red()
        
        # Disable all buttons
        for child in self.children:
            child.disabled = True
            
        await interaction.message.edit(embed=embed, view=self)

    async def generate_embed(self, event_data):
        rsvps = await database.get_rsvps(self.event_id)
        
        accepted = []
        declined = []
        tentative = []
        
        for user_id, status in rsvps:
            user_mention = f"<@{user_id}>"
            if status == "accepted":
                accepted.append(user_mention)
            elif status == "declined":
                declined.append(user_mention)
            elif status == "tentative":
                tentative.append(user_mention)

        embed = discord.Embed(
            title=event_data["title"],
            description=event_data["description"],
            color=discord.Color.blue()
        )
        
        embed.add_field(name=t("EMBED_START_TIME"), value=f"<t:{int(event_data['start_time'])}:F>", inline=False)
        if event_data['recurrence_rule'] != 'none':
            embed.add_field(name=t("EMBED_RECURRENCE"), value=event_data['recurrence_rule'], inline=False)
            
        embed.add_field(name=t("EMBED_ACC", count=len(accepted)), value="\n".join(accepted) or t("EMBED_NONE"), inline=True)
        embed.add_field(name=t("EMBED_DEC", count=len(declined)), value="\n".join(declined) or t("EMBED_NONE"), inline=True)
        embed.add_field(name=t("EMBED_TEN", count=len(tentative)), value="\n".join(tentative) or t("EMBED_NONE"), inline=True)

        if event_data.get("image_url"):
            embed.set_thumbnail(url=event_data["image_url"])
            
        embed.set_footer(text=t("EMBED_FOOTER", event_id=self.event_id, creator_id=event_data['creator_id']))
        return embed

    async def handle_rsvp(self, interaction: discord.Interaction, status: str):
        await interaction.response.defer()
        
        event_dict = await database.get_event(self.event_id)
        if not event_dict:
            await interaction.followup.send(t("ERR_EV_NOT_FOUND"), ephemeral=True)
            return

        if event_dict["status"] != 'active':
            await interaction.followup.send(t("ERR_EV_INACTIVE"), ephemeral=True)
            return

        await database.update_rsvp(self.event_id, interaction.user.id, status)
        
        embed = await self.generate_embed(event_dict)
        await interaction.message.edit(embed=embed, view=self)

async def setup(bot):
    pass
