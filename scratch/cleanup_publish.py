import os

path = r'e:\projects\python\discord-event-bot\cogs\event_commands.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if '@app_commands.command(name="publish"' in line:
        skip = True
        continue
    if skip:
        if ('@app_commands.command' in line or 'async def' in line) and 'event_publish' not in line and 'autocomplete' not in line:
             # Check if we hit the next command
             if '@app_commands.command(name="cancel"' in line:
                 skip = False
             elif 'async def _handle_status_change' in line:
                  skip = False
        
        if skip:
            continue

    new_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Success")
