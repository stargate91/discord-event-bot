import discord
from discord.ext import commands
import database
from utils.i18n import t
import json

def get_event_conf(name):
    try:
        from utils.jsonc import load_jsonc
        config_data = load_jsonc('config.json')
        events = config_data.get("events_config", [])
        for e in events:
            if e.get("name") == name:
                return e
    except Exception:
        pass
    return None

class DynamicEventView(discord.ui.View):
    def __init__(self, bot, event_id: str, event_conf: dict = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.event_id = event_id
        self.event_conf = event_conf

        # Setup buttons
        accept_btn = discord.ui.Button(label=t("BTN_ACCEPT"), style=discord.ButtonStyle.success, emoji="✅", custom_id=f"accept_{event_id}")
        accept_btn.callback = self.accept_callback
        self.add_item(accept_btn)

        decline_btn = discord.ui.Button(label=t("BTN_DECLINE"), style=discord.ButtonStyle.danger, emoji="❌", custom_id=f"decline_{event_id}")
        decline_btn.callback = self.decline_callback
        self.add_item(decline_btn)

        tentative_btn = discord.ui.Button(label=t("BTN_TENTATIVE"), style=discord.ButtonStyle.secondary, emoji="❔", custom_id=f"tentative_{event_id}")
        tentative_btn.callback = self.tentative_callback
        self.add_item(tentative_btn)

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
        # Allow anyone with Administrator rights to delete
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(t("ERR_NO_PERM"), ephemeral=True)
            return

        await interaction.response.defer()
        await database.delete_active_event(self.event_id)
        
        embed = interaction.message.embeds[0]
        embed.title = f"{t('TAG_DELETED')} {embed.title}"
        embed.color = discord.Color.red()
        
        for child in self.children:
            child.disabled = True
            
        await interaction.message.edit(embed=embed, view=self)

    async def generate_embed(self, db_event=None):
        if not db_event:
            db_event = await database.get_active_event(self.event_id)
            
        if not self.event_conf and db_event:
            self.event_conf = get_event_conf(db_event["config_name"])

        if not self.event_conf:
            return discord.Embed(title="Missing configuration", color=discord.Color.red())

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

        color_hex = self.event_conf.get("color", "0x3498db")
        if color_hex.startswith("0x"):
            color = int(color_hex, 16)
        else:
            color = discord.Color.blue()

        embed = discord.Embed(
            title=self.event_conf.get("title", "Event"),
            description=self.event_conf.get("description", ""),
            color=color
        )
        
        start_ts = db_event['start_time'] if db_event else time.time()
        embed.add_field(name=t("EMBED_START_TIME"), value=f"<t:{int(start_ts)}:F>", inline=False)
        
        recurrence = self.event_conf.get('recurrence_type', 'none')
        if recurrence != 'none':
            embed.add_field(name=t("EMBED_RECURRENCE"), value=recurrence.capitalize(), inline=False)
            
        max_acc = self.event_conf.get('max_accepted', 0)
        acc_label = f"{len(accepted)}/{max_acc}" if max_acc > 0 else f"{len(accepted)}"
            
        embed.add_field(name=t("EMBED_ACC", count=acc_label), value="\n".join(accepted) or t("EMBED_NONE"), inline=True)
        embed.add_field(name=t("EMBED_DEC", count=len(declined)), value="\n".join(declined) or t("EMBED_NONE"), inline=True)
        embed.add_field(name=t("EMBED_TEN", count=len(tentative)), value="\n".join(tentative) or t("EMBED_NONE"), inline=True)

        if self.event_conf.get("image_url"):
            embed.set_image(url=self.event_conf["image_url"])
            
        embed.set_footer(text=t("EMBED_FOOTER", event_id=self.event_id, creator_id="System"))
        return embed

    async def handle_rsvp(self, interaction: discord.Interaction, status: str):
        db_event = await database.get_active_event(self.event_id)
        if not db_event:
            await interaction.response.send_message(t("ERR_EV_NOT_FOUND"), ephemeral=True)
            return

        if db_event["status"] != 'active':
            await interaction.response.send_message(t("ERR_EV_INACTIVE"), ephemeral=True)
            return
            
        if not self.event_conf:
            self.event_conf = get_event_conf(db_event["config_name"])
            
        if status == 'accepted' and self.event_conf:
            max_acc = self.event_conf.get('max_accepted', 0)
            if max_acc > 0:
                rsvps = await database.get_rsvps(self.event_id)
                current_acc = sum(1 for _, s in rsvps if s == 'accepted')
                
                # If changing status to accepted, check capacity
                already_accepted = False
                for uid, s in rsvps:
                    if uid == interaction.user.id and s == 'accepted':
                        already_accepted = True
                        break
                        
                if not already_accepted and current_acc >= max_acc:
                    await interaction.response.send_message("Sajnálom, de ez az esemény már betelt!", ephemeral=True)
                    return

        await interaction.response.defer()
        await database.update_rsvp(self.event_id, interaction.user.id, status)
        
        embed = await self.generate_embed(db_event)
        await interaction.message.edit(embed=embed, view=self)

async def setup(bot):
    pass
