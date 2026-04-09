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
        super().__init__(title=(t("BTN_STEP_1")[:45]))
        self.wizard_view = wizard_view
        data = wizard_view.data

        self.name_input = ui.TextInput(label=t("LBL_WIZ_NAME"), default=str(data.get("config_name") or ""), required=True)
        self.title_input = ui.TextInput(label=t("LBL_WIZ_TITLE"), default=str(data.get("title") or ""), required=True)
        self.desc_input = ui.TextInput(label=t("LBL_WIZ_DESC"), style=discord.TextStyle.paragraph, default=str(data.get("description") or ""), required=False)
        self.images_input = ui.TextInput(label=t("LBL_WIZ_IMAGES"), default=str(data.get("image_urls") or ""), required=False)
        self.creator_input = ui.TextInput(label=t("LBL_WIZ_CREATOR"), default=str(data.get("creator_id") or wizard_view.creator_id), required=False)
        
        self.add_item(self.name_input)
        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.images_input)
        self.add_item(self.creator_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.data["config_name"] = str(self.name_input.value)
        self.wizard_view.data["title"] = str(self.title_input.value)
        self.wizard_view.data["description"] = str(self.desc_input.value)
        self.wizard_view.data["image_urls"] = str(self.images_input.value)
        self.wizard_view.data["creator_id"] = str(self.creator_input.value)
        self.wizard_view.steps_completed["step1"] = True
        await self.wizard_view.update_message(interaction)

class Step2Modal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=(t("BTN_STEP_2")[:45]))
        self.wizard_view = wizard_view
        data = wizard_view.data

        self.color_input = ui.TextInput(label=t("LBL_WIZ_COLOR"), default=str(data.get("color") or "0x3498db"), required=False)
        self.max_acc_input = ui.TextInput(label=t("LBL_WIZ_MAX"), default=str(data.get("max_accepted") or 0), required=False)
        self.ping_input = ui.TextInput(label=t("LBL_WIZ_PING"), default=str(data.get("ping_role") or ""), required=False)
        self.start_input = ui.TextInput(label=t("LBL_WIZ_START"), placeholder="YYYY-MM-DD HH:MM", default=str(data.get("start_str") or ""), required=True)
        self.end_input = ui.TextInput(label=t("LBL_WIZ_END"), placeholder="YYYY-MM-DD HH:MM", default=str(data.get("end_str") or ""), required=False)

        self.add_item(self.color_input)
        self.add_item(self.max_acc_input)
        self.add_item(self.ping_input)
        self.add_item(self.start_input)
        self.add_item(self.end_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.wizard_view.data["color"] = str(self.color_input.value)
            self.wizard_view.data["max_accepted"] = int(self.max_acc_input.value) if str(self.max_acc_input.value).isdigit() else 0
            self.wizard_view.data["ping_role"] = int(self.ping_input.value) if str(self.ping_input.value).isdigit() else 0
            self.wizard_view.data["start_str"] = str(self.start_input.value)
            self.wizard_view.data["end_str"] = str(self.end_input.value)
            self.wizard_view.steps_completed["step2"] = True
            await self.wizard_view.update_message(interaction)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Hiba: {e}", ephemeral=True)

class Step3Modal(ui.Modal):
    def __init__(self, wizard_view):
        super().__init__(title=(t("SEL_TRIG_TYPE")[:45]))
        self.wizard_view = wizard_view
        data = wizard_view.data

        self.offset_input = ui.TextInput(
            label=t("LBL_WIZ_OFFSET"), 
            placeholder="pl. 4h, 30m, 1d", 
            default=str(data.get("repost_offset") or "1h"), 
            required=True
        )
        self.add_item(self.offset_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.data["repost_offset"] = str(self.offset_input.value)
        self.wizard_view.steps_completed["step3"] = True
        await self.wizard_view.update_message(interaction)

class EventWizardView(ui.View):
    def __init__(self, bot, creator_id, existing_data=None, is_edit=False):
        super().__init__(timeout=600)
        self.bot = bot
        self.creator_id = creator_id
        self.is_edit = is_edit
        self.data = existing_data or {}
        self.can_publish = False
        
        # Ensure we check both singular and plural for pre-filling
        if not self.data.get("image_urls") and self.data.get("image_url"):
            self.data["image_urls"] = self.data["image_url"]

        self.steps_completed = {
            "step1": bool(self.data.get("title") or self.data.get("config_name")),
            "step2": bool(self.data.get("start_str") or self.data.get("start_time")),
            "step3": bool(self.data.get("repost_offset"))
        }

        # Pre-select values in Select menus if we have them
        current_rec = self.data.get("recurrence_type", "none")
        for opt in self.recurrence_select.options:
            opt.default = (opt.value == current_rec)

        current_trig = self.data.get("repost_trigger", "before_start")
        for opt in self.trigger_select.options:
            opt.default = (opt.value == current_trig)

    def get_status_text(self):
        s1 = t("WIZARD_STATUS_OK") if self.steps_completed["step1"] else t("WIZARD_STATUS_WAIT")
        s2 = t("WIZARD_STATUS_OK") if self.steps_completed["step2"] else t("WIZARD_STATUS_WAIT")
        s3 = t("WIZARD_STATUS_OK") if self.steps_completed["step3"] else t("WIZARD_STATUS_WAIT")
        return f"- {t('BTN_STEP_1')}: {s1}\n- {t('BTN_STEP_2')}: {s2}\n- Offset: {s3}"

    async def update_message(self, interaction: discord.Interaction):
        status = self.get_status_text()
        embed = discord.Embed(
            title=t("WIZARD_TITLE"), 
            description=t("WIZARD_DESC", status=status), 
            color=discord.Color.blue() if not self.is_edit else discord.Color.gold()
        )
        
        # Add publish button if saved
        if self.can_publish:
            publish_btn = ui.Button(label=t("BTN_PUBLISH"), style=discord.ButtonStyle.green, row=4, custom_id="wiz_publish")
            publish_btn.callback = self.publish_btn
            self.add_item(publish_btn)
            # Remove the save button or change its style? 
            # Let's just find and update it
            for child in self.children:
                if getattr(child, "custom_id", "") == "wiz_save":
                    child.disabled = True
                    child.label = t("BTN_SAVE_PREVIEW")

        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)

    @ui.button(label="1. Alapadatok / Basic Info", style=discord.ButtonStyle.gray, custom_id="wiz_step_1", row=0)
    async def step1_btn(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.send_modal(Step1Modal(self))
        except Exception as e:
            log.error(f"Error opening Step1Modal: {e}")

    @ui.button(label="2. Részletek / Details", style=discord.ButtonStyle.gray, custom_id="wiz_step_2", row=0)
    async def step2_btn(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.send_modal(Step2Modal(self))
        except Exception as e:
            log.error(f"Error opening Step2Modal: {e}")

    @ui.button(label="3. Értesítés / Offset", style=discord.ButtonStyle.gray, custom_id="wiz_step_3", row=0)
    async def step3_btn(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.send_modal(Step3Modal(self))
        except Exception as e:
            log.error(f"Error opening Step3Modal: {e}")

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
        self.data["recurrence_type"] = str(select.values[0])
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
        self.data["repost_trigger"] = str(select.values[0])
        await self.update_message(interaction)

    @ui.button(label="SAVE & PREVIEW", style=discord.ButtonStyle.primary, row=4, custom_id="wiz_save")
    async def save_preview_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not self.steps_completed["step1"] or not self.steps_completed["step2"]:
            await interaction.response.send_message("Kérlek töltsd ki az 1. és 2. lépést!", ephemeral=True)
            return

        # DATA CLEANING: Ensure no non-serializable objects (like TextInput) are in self.data
        clean_data = {}
        for k, v in self.data.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                clean_data[k] = v
            elif isinstance(v, list):
                # Join lists with comma for storage
                clean_data[k] = ",".join(str(i) for i in v)
            else:
                clean_data[k] = str(v)
        self.data = clean_data

        try:
            local_tz = tz.gettz(str(self.data.get("timezone") or "Europe/Budapest"))
            start_dt = parser.parse(str(self.data["start_str"])).replace(tzinfo=local_tz)
            self.data["start_time"] = start_dt.timestamp()
            
            if self.data.get("end_str"):
                end_dt = parser.parse(str(self.data["end_str"])).replace(tzinfo=local_tz)
                self.data["end_time"] = end_dt.timestamp()
            else:
                self.data["end_time"] = None
        except Exception as e:
            await interaction.response.send_message(f"Dátum vagy időzóna hiba: {e}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        import uuid
        from cogs.event_ui import DynamicEventView
        
        event_id = str(self.data.get("event_id") or str(uuid.uuid4())[:8])
        self.data["event_id"] = event_id
        
        if self.is_edit:
            # Keep existing creator_id if not present
            if "creator_id" not in self.data:
                self.data["creator_id"] = str(self.creator_id)
            await database.update_active_event(event_id, self.data)
        else:
            self.data["creator_id"] = str(self.creator_id)
            await database.create_active_event(
                event_id=event_id,
                config_name=str(self.data.get("config_name") or "manual"),
                channel_id=interaction.channel_id,
                start_time=self.data["start_time"],
                data=self.data
            )

        # Update state to allow publication
        self.can_publish = True
        
        # Generate preview
        view = DynamicEventView(self.bot, event_id, self.data)
        embed = await view.generate_embed()
        
        await interaction.followup.send(t("MSG_SAVED_PREVIEW"), embed=embed, ephemeral=True)
        await self.update_message(interaction)

    async def publish_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        from cogs.event_ui import DynamicEventView
        event_id = self.data["event_id"]
        db_event = await database.get_active_event(event_id)
        
        if self.is_edit:
            if db_event and db_event.get("message_id") and db_event.get("channel_id"):
                channel = self.bot.get_channel(db_event["channel_id"])
                if channel:
                    try:
                        msg = await channel.fetch_message(db_event["message_id"])
                        view = DynamicEventView(self.bot, event_id, self.data)
                        embed = await view.generate_embed(db_event)
                        await msg.edit(embed=embed, view=view)
                    except Exception as e:
                        log.error(f"Error updating message: {e}")
            await interaction.followup.send("Esemény sikeresen frissítve!", ephemeral=True)
        else:
            view = DynamicEventView(self.bot, event_id, self.data)
            embed = await view.generate_embed()
            msg = await interaction.channel.send(content=t("MSG_EV_CREATED_PUBLIC"), embed=embed, view=view)
            await database.set_event_message(event_id, msg.id)
            self.bot.add_view(view)
            await interaction.followup.send("Esemény sikeresen közzétéve!", ephemeral=True)

        # Clean up wizard
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)
        self.stop()
