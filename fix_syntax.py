import re

with open("cogs/event_ui.py", "r", encoding="utf-8") as f:
    text = f.read()

# Fix the broken f-strings caused by literal newlines being inserted instead of \n
text = text.replace(
'''        if is_full: desc = f"### ⚠️ {t('EMBED_FULL', guild_id=guild_id) or 'ESEMÉNY BETELT'}
{desc}"''',
'''        if is_full: desc = f"### ⚠️ {t('EMBED_FULL', guild_id=guild_id) or 'ESEMÉNY BETELT'}\\n{desc}"'''
)

text = text.replace(
'''        if recurrence != 'none': time_str += f"
**{t('EMBED_RECURRENCE', guild_id=guild_id)}:** {recurrence.capitalize()}"''',
'''        if recurrence != 'none': time_str += f"\\n**{t('EMBED_RECURRENCE', guild_id=guild_id)}:** {recurrence.capitalize()}"'''
)

text = text.replace(
'''            users_list_str = "
".join([f"- {u}" for u in users]) if users else f"- *{t('EMBED_NONE', guild_id=guild_id)}*"''',
'''            users_list_str = "\\n".join([f"- {u}" for u in users]) if users else f"- *{t('EMBED_NONE', guild_id=guild_id)}*"'''
)

text = text.replace(
'''            roles_text += f"
**{' '.join(name_parts)} ({count_text})**
{users_list_str}
"''',
'''            roles_text += f"\\n**{' '.join(name_parts)} ({count_text})**\\n{users_list_str}\\n"'''
)

text = text.replace(
'''            wait_str = f"**⏳ {t('EMBED_WAITLIST', guild_id=guild_id) or 'Waiting List'} ({len(waiting_list)})**
" + "
".join([f"- {u}" for u in waiting_list])''',
'''            wait_str = f"**⏳ {t('EMBED_WAITLIST', guild_id=guild_id) or 'Waiting List'} ({len(waiting_list)})**\\n" + "\\n".join([f"- {u}" for u in waiting_list])'''
)

# And one special case, encoding might have broken the icon! Let's just fix the whole string using regex
text = re.sub(r'if is_full: desc = f"### .*?\{desc\}"', 'if is_full: desc = f"### ⚠️ {t(\'EMBED_FULL\', guild_id=guild_id) or \'ESEMÉNY BETELT\'}\\n{desc}"', text, flags=re.DOTALL)
text = re.sub(r'if recurrence != \'none\': time_str \+= f"\s*\*\*\{t\(\'EMBED_RECURRENCE\', guild_id=guild_id\)\}:\*\* \{recurrence\.capitalize\(\)\}"', 'if recurrence != \'none\': time_str += f"\\n**{t(\'EMBED_RECURRENCE\', guild_id=guild_id)}:** {recurrence.capitalize()}"', text, flags=re.DOTALL)
text = re.sub(r'users_list_str = "\s*"\.join\(\[f"- \{u\}" for u in users\]\) if users else f"- \*\{t\(\'EMBED_NONE\', guild_id=guild_id\)\}\*"', 'users_list_str = "\\n".join([f"- {u}" for u in users]) if users else f"- *{t(\'EMBED_NONE\', guild_id=guild_id)}*"', text, flags=re.DOTALL)
text = re.sub(r'roles_text \+= f"\s*\*\*\{\' \'\.join\(name_parts\)\} \(\{count_text\}\)\*\*\s*\{users_list_str\}\s*"', 'roles_text += f"\\n**{\' \'.join(name_parts)} ({count_text})**\\n{users_list_str}\\n"', text, flags=re.DOTALL)
text = re.sub(r'wait_str = f"\*\*⏳ \{t\(\'EMBED_WAITLIST\', guild_id=guild_id\) or \'Waiting List\'\} \(\{len\(waiting_list\)\}\)\*\*\s*" \+ "\s*"\.join\(\[f"- \{u\}" for u in waiting_list\]\)', 'wait_str = f"**⏳ {t(\'EMBED_WAITLIST\', guild_id=guild_id) or \'Waiting List\'} ({len(waiting_list)})**\\n" + "\\n".join([f"- {u}" for u in waiting_list])', text, flags=re.DOTALL)

with open("cogs/event_ui.py", "w", encoding="utf-8") as f:
    f.write(text)
