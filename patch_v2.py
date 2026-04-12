import re

with open("cogs/event_ui.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Replace prepare()
prepare_str = '''    async def prepare(self):
        """Builds the view using Components V2 Layouts."""
        self.clear_items()
        
        # Load db_event or use self.event_conf entirely
        from cogs.database import database
        import time, json, random
        db_event = await database.get_active_event(self.event_id)
        if db_event and not self.event_conf:
            self.event_conf = get_event_conf(db_event["config_name"])
            if not self.event_conf:
                self.event_conf = dict(db_event)
                ex = db_event.get("extra_data")
                if ex:
                    try:
                        d = json.loads(ex) if isinstance(ex, str) else ex
                        if isinstance(d, dict): self.event_conf.update(d)
                    except: pass
        
        event_conf = self.event_conf or {}
        guild_id = event_conf.get("guild_id")
        
        # Calculate RSVPs for lists and button states
        rsvps = await database.get_rsvps(self.event_id)
        status_map = {}
        total_positive_count = 0
        positive_statuses = [o["id"] for o in self.active_set["options"] if o.get("positive")]
        if not positive_statuses and "positive_count" in self.active_set:
            cnt = self.active_set["positive_count"]
            positive_statuses = [o["id"] for o in self.active_set["options"][:cnt]]

        for uid, s in rsvps:
            if s not in status_map: status_map[s] = []
            user = self.bot.get_user(uid)
            display_str = user.mention if user else f"<@{uid}>"
            status_map[s].append(display_str)
            if s in positive_statuses: total_positive_count += 1
            
        extra_data = db_event.get("extra_data") if db_event else None
        role_limits = {}
        if extra_data:
            try:
                if isinstance(extra_data, str):
                    role_limits = json.loads(extra_data).get("role_limits", {})
                else:
                    role_limits = extra_data.get("role_limits", {})
            except: pass

        import discord
        container_items = []
        
        max_acc = event_conf.get("max_accepted", 0)
        is_full = (max_acc > 0 and total_positive_count >= max_acc)
        desc = event_conf.get("description", "")
        if is_full: desc = f"### ⚠️ {t('EMBED_FULL', guild_id=guild_id) or 'ESEMÉNY BETELT'}\\n{desc}"

        status_cfg = event_conf.get("status", "active")
        title_prefix = ""
        if status_cfg == "cancelled": title_prefix = f"**[{t('TAG_CANCELLED', guild_id=guild_id) or 'TÖRÖLVE'}]** "
        elif status_cfg == "postponed": title_prefix = f"**[{t('TAG_POSTPONED', guild_id=guild_id) or 'ELHALASZTVA'}]** "

        title_str = f"## {title_prefix}{event_conf.get('title', t('LBL_EVENT', guild_id=guild_id))}"
        container_items.append(discord.ui.TextDisplay(title_str))
        
        if desc: container_items.append(discord.ui.TextDisplay(desc))
        
        start_ts = db_event['start_time'] if db_event else time.time()
        time_str = f"**{t('EMBED_START_TIME', guild_id=guild_id)}:** <t:{int(start_ts)}:F>"
        recurrence = event_conf.get('recurrence_type', 'none')
        if recurrence != 'none': time_str += f"\\n**{t('EMBED_RECURRENCE', guild_id=guild_id)}:** {recurrence.capitalize()}"
        container_items.append(discord.ui.TextDisplay(time_str))
        
        image_url = None
        if db_event and db_event.get("image_urls"): image_url = str(db_event["image_urls"]).split(",")[0].strip()
        elif event_conf.get("image_urls"):
            val = event_conf["image_urls"]
            if isinstance(val, list): image_url = random.choice(val)
            elif isinstance(val, str) and "," in val: image_url = random.choice([u.strip() for u in val.split(",")])
            else: image_url = str(val)
        
        if image_url:
            container_items.append(discord.ui.Thumbnail(media=image_url))

        roles_text = ""
        waiting_list = []
        for opt in self.active_set["options"]:
            role_id = opt["id"]
            users = status_map.get(role_id, [])
            limit = role_limits.get(role_id, opt.get("max_slots"))
            label_text = opt.get("list_label") or (t(opt["label_key"], guild_id=guild_id) if "label_key" in opt else opt.get("label", ""))
            
            count_text = str(len(users))
            is_pos = (role_id in positive_statuses)
            if is_pos and max_acc > 0: count_text = f"{len(users)}/{max_acc}"
            if limit: count_text = f"{len(users)}/{limit}"
            
            if not opt.get("show_in_list", True): continue

            name_parts = []
            if opt.get("emoji"): name_parts.append(opt["emoji"])
            if label_text: name_parts.append(label_text)
            
            users_list_str = "\\n".join([f"- {u}" for u in users]) if users else f"- *{t('EMBED_NONE', guild_id=guild_id)}*"
            roles_text += f"\\n**{' '.join(name_parts)} ({count_text})**\\n{users_list_str}\\n"

            wait_tag = f"wait_{role_id}"
            if wait_tag in status_map:
                emoji = opt.get("emoji", "⏳")
                for u in status_map[wait_tag]: waiting_list.append(f"{emoji} {u}")

        if roles_text:
            container_items.append(discord.ui.Separator())
            container_items.append(discord.ui.TextDisplay(roles_text.strip()))

        if waiting_list:
            container_items.append(discord.ui.Separator())
            wait_str = f"**⏳ {t('EMBED_WAITLIST', guild_id=guild_id) or 'Waiting List'} ({len(waiting_list)})**\\n" + "\\n".join([f"- {u}" for u in waiting_list])
            container_items.append(discord.ui.TextDisplay(wait_str))

        container_items.append(discord.ui.Separator())
        creator_text = "System"
        cid = event_conf.get("creator_id")
        if cid and str(cid).isdigit():
            user = self.bot.get_user(int(cid)) or await self.bot.fetch_user(int(cid))
            if user: creator_text = f"@{user.display_name}"
        elif cid: creator_text = str(cid)
        container_items.append(discord.ui.TextDisplay(f"*{t('EMBED_FOOTER', guild_id=guild_id, event_id=self.event_id, creator_id=creator_text)}*"))

        per_row = self.active_set.get("buttons_per_row", 5)
        options = self.active_set.get("options", [])
        
        rows = []
        current_row_items = []
        added_count = 0

        for opt in options:
            if added_count >= 40: break
            role_id = opt.get("id")
            if not role_id: continue
            
            if role_id in role_limits: opt["max_slots"] = role_limits[role_id]
            label = opt.get("label") if "label" in opt else ""
            if role_id in ["accepted", "declined", "tentative"]:
                label_key = f"BTN_{role_id.upper()}"
                localized_label = t(label_key, guild_id=guild_id)
                if localized_label != label_key: label = localized_label

            btn_style = opt.get("button_style", "both")
            btn_emoji = opt.get("emoji") if btn_style in ["both", "emoji"] else None
            btn_label = label if btn_style in ["both", "label"] else None
            color_map = {"success": discord.ButtonStyle.green, "danger": discord.ButtonStyle.red, "primary": discord.ButtonStyle.primary, "secondary": discord.ButtonStyle.secondary}
            btn_color = color_map.get(opt.get("button_color"), discord.ButtonStyle.secondary)

            btn = discord.ui.Button(style=btn_color, emoji=btn_emoji or None, label=btn_label or None, custom_id=f"{role_id}_{self.event_id}")
            
            def create_callback(status_id):
                async def callback(interaction: discord.Interaction):
                    await self.handle_rsvp(interaction, status_id)
                return callback
            btn.callback = create_callback(role_id)
            current_row_items.append(btn)
            added_count += 1
            if len(current_row_items) >= per_row:
                rows.append(discord.ui.ActionRow(*current_row_items))
                current_row_items = []

        if current_row_items: rows.append(discord.ui.ActionRow(*current_row_items))

        if self.active_set.get("show_mgmt", True) and added_count < 40:
            mgmt_items = []
            calendar_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="📅", custom_id=f"calendar_{self.event_id}")
            calendar_btn.callback = self.calendar_callback
            mgmt_items.append(calendar_btn)
            edit_btn = discord.ui.Button(label=t("BTN_EDIT", guild_id=guild_id), style=discord.ButtonStyle.gray, custom_id=f"edit_{self.event_id}")
            edit_btn.callback = self.edit_callback
            mgmt_items.append(edit_btn)
            delete_btn = discord.ui.Button(label=t("BTN_DELETE", guild_id=guild_id), style=discord.ButtonStyle.danger, custom_id=f"delete_{self.event_id}")
            delete_btn.callback = self.delete_callback
            mgmt_items.append(delete_btn)
            rows.append(discord.ui.ActionRow(*mgmt_items))

        for r in rows: container_items.append(r)

        accent_color = int(str(event_conf.get("color") or "0x3498db").replace("0x", ""), 16)
        container = discord.ui.Container(*container_items, accent_color=accent_color)
        self.add_item(container)
        self.update_button_states(rsvps, event_conf)'''

code = re.sub(r'    async def prepare\(self\):.*?    def update_button_states\(self, rsvps_list, event_conf\):', prepare_str + '\n\n    def update_button_states(self, rsvps_list, event_conf):', code, flags=re.DOTALL)

code = code.replace("        embed = await self.generate_embed(db_event)\n        await interaction.message.edit(embed=embed, view=self)", "        await self.prepare()\n        await interaction.message.edit(content=None, embeds=[], view=self)")

# remove generate_embed entirely
code = re.sub(r'    async def generate_embed\(self, db_event=None\):.*', '', code, flags=re.DOTALL)

with open("cogs/event_ui.py", "w", encoding="utf-8") as f:
    f.write(code)
