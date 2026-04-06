# Discord Event Scheduler Bot

This is a Discord bot I made to help with scheduling events for my server. It allows users to create events with a start time, description, and even an optional image. Then it posts an embed message that has buttons so people can RSVP (Accept, Decline, Tentative).

I also added a feature to support recurring events. If you set an event to be daily or weekly, the bot has a background task that checks the time. When the event is over, it will post a new cloned event for the next occurance and reset all the RSVPs.

## Technologies I Used
- Python 3.10
- discord.py (for the bot framework and slash commands)
- aiosqlite (for asynchronous SQLite database handling)
- python-dotenv (to hide the bot token)

## How to Set It Up

1. Install the requirements:
`pip install discord.py aiosqlite python-dotenv`

2. Set up the Environment Variables:
Create a file called `.env` in the root folder and add your bot token:
`BOT_TOKEN=your_bot_token_here`

3. Set up the Configuration:
Create a `config.json` file in the root directory like this:
```json
{
  "guild_id": 1234567890,
  "ping_role_id": null,
  "language": "hu",
  "command_suffix": "_ev",
  "command_prefix": "!"
}
```
Note: If you leave `guild_id` as null, slash commands will sync globally (it might take an hour). If you put your server ID there, it syncs instantly.

4. Run the bot:
`python main.py`

## Commands
Slash command:
- `/event_create`: Opens a modal window to create a new event.

Prefix commands (Admin only):
- `!sync_ev`: Syncs slash commands into the server.
- `!clear_commands_ev`: Clears old disabled slash commands.

## Learnings
Working with persistent views was a bit tricky at first because Discord forgets the buttons when the bot restarts. I fixed it by making the bot load active events from the database on startup and re-adding the view with dynamic custom IDs. 
