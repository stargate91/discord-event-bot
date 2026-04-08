import discord
from discord import ui
import database
from utils.i18n import t
from utils.logger import log
import datetime
import time
from dateutil import parser
from dateutil import tz

class Step1Modal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=t("BTN_STEP_1"))
        self.wizard_view = wizard_view
        data = wizard_view.data

        self.name = ui.TextInput(label=t("LBL_WIZ_NAME"), default=(data.get("config_name") or ""), required=True)
        self.title = ui.TextInput(label=t("LBL_WIZ_TITLE"), default=(data.get("title") or ""), required=True)
        self.desc = ui.TextInput(label=t("LBL_WIZ_DESC"), style=discord.TextStyle.paragraph, default=(data.get("description") or ""), required=False)
        self.images = ui.TextInput(label=t("LBL_WIZ_IMAGES"), default=(data.get("image_urls") or ""), required=False)
        
        self.add_item(self.name)
        self.add_item(self.title)
        self.add_item(self.desc)
        self.add_item(self.images)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.data["config_name"] = self.name.value
        self.wizard_view.data["title"] = self.title.value
        self.wizard_view.data["description"] = self.desc.value
        self.wizard_view.data["image_urls"] = self.images.value
        self.wizard_view.steps_completed["step1"] = True
        await self.wizard_view.update_message(interaction)

class Step2Modal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=t("BTN_STEP_2"))
        self.wizard_view = wizard_view
        data = wizard_view.data

        self.color = ui.TextInput(label=t("LBL_WIZ_COLOR"), default=(data.get("color") or "0x3498db"), required=False)
        self.max_acc = ui.TextInput(label=t("LBL_WIZ_MAX"), default=str(data.get("max_accepted") or 0), required=False)
        self.ping = ui.TextInput(label=t("LBL_WIZ_PING"), default=str(data.get("ping_role") or ""), required=False)
        self.start = ui.TextInput(label=t("LBL_WIZ_START"), placeholder="YYYY-MM-DD HH:MM", default=(data.get("start_str") or ""), required=True)
        self.end = ui.TextInput(label=t("LBL_WIZ_END"), placeholder="YYYY-MM-DD HH:MM", default=(data.get("end_str") or ""), required=False)

        self.add_item(self.color)
        self.add_item(self.max_acc)
        self.add_item(self.ping)
        self.add_item(self.start)
        self.add_item(self.end)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.wizard_view.data["color"] = self.color.value
            self.wizard_view.data["max_accepted"] = int(self.max_acc.value) if self.max_acc.value.isdigit() else 0
            self.wizard_view.data["ping_role"] = int(self.ping.value) if self.ping.value.isdigit() else 0
            self.wizard_view.data["start_str"] = self.start.value
            self.wizard_view.data["end_str"] = self.end.value
            self.wizard_view.steps_completed["step2"] = True
            await self.wizard_view.update_message(interaction)
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)

class Step3Modal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=t("SEL_TRIG_TYPE"))
        self.wizard_view = wizard_view
        data = wizard_view.data

        self.offset = ui.TextInput(
            label=t("LBL_WIZ_OFFSET"), 
            placeholder="pl. 4h, 30m, 1d", 
            default=(data.get("repost_offset") or "1h"), 
            required=True
        )
        self.add_item(self.offset)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.data["repost_offset"] = self.offset.value
        self.wizard_view.steps_completed["step3"] = True
        await self.wizard_view.update_message(interaction)

class EventWizardView(ui.View):
    def __init__(self, bot, creator_id, existing_data=None, is_edit=False):
        super().__init__(timeout=600)
        self.bot = bot
        self.creator_id = creator_id
        self.is_edit = is_edit
        self.data = existing_data or {}
        self.steps_completed = {
            "step1": bool(self.data.get("title")),
            "step2": bool(self.data.get("start_str")),
            "step3": bool(self.data.get("repost_offset"))
        }
        
    def get_status_text(self):
        s1 = t("WIZARD_STATUS_OK") if self.steps_completed["step1"] else t("WIZARD_STATUS_WAIT")
        s2 = t("WIZARD_STATUS_OK") if self.steps_completed["step2"] else t("WIZARD_STATUS_WAIT")
        s3 = t("WIZARD_STATUS_OK") if self.steps_completed["step3"] else t("WIZARD_STATUS_WAIT")
        return f"- {t('BTN_STEP_1')}: {s1}\n- {t('BTN_STEP_2')}: {s2}\n- Offset: {s3}"

    async def update_message(self, interaction: discord.Interaction):
        embed = discord.Embed(title=t("WIZARD_TITLE"), description=t("WIZARD_DESC", status=self.get_status_text()), color=discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="1. Alapadatok / Basic Info", style=discord.ButtonStyle.gray, custom_id="wiz_step_1", row=0)
    async def step1_btn(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.send_modal(Step1Modal(self))
        except Exception as e:
            log.error(f"Error opening Step1Modal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)

    @ui.button(label="2. Részletek / Details", style=discord.ButtonStyle.gray, custom_id="wiz_step_2", row=0)
    async def step2_btn(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.send_modal(Step2Modal(self))
        except Exception as e:
            log.error(f"Error opening Step2Modal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)

    @ui.button(label="3. Értesítés / Offset", style=discord.ButtonStyle.gray, custom_id="wiz_step_3", row=0)
    async def step3_btn(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.send_modal(Step3Modal(self))
        except Exception as e:
            log.error(f"Error opening Step3Modal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)

    @ui.select(
        placeholder="Recurrence Type",
        options=[
            discord.SelectOption(label="None", value="none", emoji="❌"),
            discord.SelectOption(label="Daily", value="daily", emoji="📅"),
            discord.SelectOption(label="Weekly", value="weekly", emoji="🗓️"),
            discord.SelectOption(label="Monthly", value="monthly", emoji="📊")
        ]
    )
    async def recurrence_select(self, interaction: discord.Interaction, select: ui.Select):
        self.data["recurrence_type"] = select.values[0]
        await self.update_message(interaction)

    @ui.select(
        placeholder="Repost Trigger",
        options=[
            discord.SelectOption(label="Before Start", value="before_start"),
            discord.SelectOption(label="After Start", value="after_start"),
            discord.SelectOption(label="After End", value="after_end")
        ]
    )
    async def trigger_select(self, interaction: discord.Interaction, select: ui.Select):
        self.data["repost_trigger"] = select.values[0]
        await self.update_message(interaction)

    @ui.button(label="SUBMIT", style=discord.ButtonStyle.green, row=4)
    async def submit_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not self.steps_completed["step1"] or not self.steps_completed["step2"]:
            await interaction.response.send_message("Please complete Step 1 and 2 before submitting.", ephemeral=True)
            return

        # Final Parsing
        try:
            local_tz = tz.gettz("Europe/Budapest")
            start_dt = parser.parse(self.data["start_str"]).replace(tzinfo=local_tz)
            self.data["start_time"] = start_dt.timestamp()
            
            if self.data.get("end_str"):
                end_dt = parser.parse(self.data["end_str"]).replace(tzinfo=local_tz)
                self.data["end_time"] = end_dt.timestamp()
            else:
                self.data["end_time"] = None
        except Exception as e:
            await interaction.response.send_message(f"Date format error: {e}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        import uuid
        from cogs.event_ui import DynamicEventView
        
        event_id = self.data.get("event_id") or str(uuid.uuid4())[:8]
        self.data["event_id"] = event_id
        
        if self.is_edit:
            await database.update_active_event(event_id, self.data)
            # Update existing message
            db_event = await database.get_active_event(event_id)
            if db_event and db_event.get("message_id") and db_event.get("channel_id"):
                channel = self.bot.get_channel(db_event["channel_id"])
                if channel:
                    msg = await channel.fetch_message(db_event["message_id"])
                    view = DynamicEventView(self.bot, event_id, self.data)
                    embed = await view.generate_embed(db_event)
                    await msg.edit(embed=embed, view=view)
            await interaction.followup.send("Event updated successfully!", ephemeral=True)
        else:
            await database.create_active_event(
                event_id=event_id,
                config_name=self.data["config_name"],
                channel_id=interaction.channel_id,
                start_time=self.data["start_time"],
                data=self.data
            )
            view = DynamicEventView(self.bot, event_id, self.data)
            embed = await view.generate_embed()
            msg = await interaction.channel.send(content=t("MSG_EV_CREATED_PUBLIC"), embed=embed, view=view)
            await database.set_event_message(event_id, msg.id)
            self.bot.add_view(view)
            await interaction.followup.send("Event created successfully!", ephemeral=True)

        self.stop()
