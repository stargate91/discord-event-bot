import re

with open("cogs/event_wizard.py", "r", encoding="utf-8") as f:
    code = f.read()

# Replace handle_save_preview
old_preview = '''            view = DynamicEventView(self.bot, event_id, self.data)
            await view.prepare()
            embed = await view.generate_embed()
            await interaction.followup.send(t("MSG_SAVED_PREVIEW") + warning, embed=embed, ephemeral=True)'''

new_preview = '''            view = DynamicEventView(self.bot, event_id, self.data)
            await view.prepare()
            await interaction.followup.send(t("MSG_SAVED_PREVIEW") + warning, view=view, ephemeral=True)'''

code = code.replace(old_preview, new_preview)

# Replace bulk edit message update
old_bulk = '''                            view = DynamicEventView(self.bot, eid, self.data)
                            embed = await view.generate_embed(curr_db_event)
                            await msg.edit(content=None, embed=embed, view=view)'''
                            
new_bulk = '''                            view = DynamicEventView(self.bot, eid, self.data)
                            await view.prepare()
                            await msg.edit(content=None, embeds=[], view=view)'''

code = code.replace(old_bulk, new_bulk)

# Replace single edit message update
old_single = '''                        view = DynamicEventView(self.bot, event_id, self.data)
                        embed = await view.generate_embed(curr_db_event)
                        await msg.edit(content=None, embed=embed, view=view)'''
                        
new_single = '''                        view = DynamicEventView(self.bot, event_id, self.data)
                        await view.prepare()
                        await msg.edit(content=None, embeds=[], view=view)'''

code = code.replace(old_single, new_single)

with open("cogs/event_wizard.py", "w", encoding="utf-8") as f:
    f.write(code)
