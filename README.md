# Nexus - Discord Event Bot

Nexus is a professional-grade Discord event scheduling and management bot designed for gaming communities, e-sports organizers, and corporate servers. It features an interactive wizard-driven event creation process, robust recurring event logic, and deep integration with Discord roles.

![Nexus Banner](file:///e:/projects/python/bot_imgs/nexus_banner.jpg)

## ✨ Features

- **Interactive Event Wizard**: Create complex events step-by-step using modern Discord Components V2.
- **Recurring Events**: Support for Daily, Weekly, Monthly, and custom weekday recurrences with automatic reposting.
- **Dynamic RSVP System**: Custom buttons (Accept, Decline, Tentative) with real-time participant lists.
- **Advanced Slot Management**:
    - **Role Limits**: Define slots for specific roles (e.g., Tank, Heal, DPS).
    - **Waiting Lists**: Automatic promotion from queue when slots open up.
- **Smart Notifications**:
    - **Reminders**: Automatic Pings or DMs before events start.
    - **Temp Roles**: Automatically give participants a role for the duration of the event.
- **Full Localization**: Seamlessly switch between **Hungarian (HU)** and **English (EN)**.
- **Custom Branding**: Create and manage your own emoji/button sets for different event types.
- **Professional Admin Hub**: Dedicated console for server-wide settings and defaults.

## 🛠️ Technology Stack

- **Language**: Python 3.10+
- **Library**: [discord.py](https://github.com/Rapptz/discord.py) (v2.0+)
- **Database**: [PostgreSQL](https://www.postgresql.org/) (via `asyncpg` for high performance)
- **Time Handling**: Centralized timezone management with `python-dateutil`.
- **UI Architecture**: Custom `LayoutView` system optimized for Components V2.

## 🚀 Getting Started

### 1. Requirements
- Python 3.10 or higher
- PostgreSQL 13+
- Discord Bot Token (with Message Content Intent)

### 2. Installation
```powershell
# Clone the repository
git clone https://github.com/your-repo/nexus-bot.git
cd nexus-bot

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
BOT_TOKEN=your_discord_token_here
DATABASE_URL=postgres://user:password@localhost:5432/nexus_db
```

Configure `config.json` for your master guild:
```json
{
  "guild_id": 1234567890,
  "command_prefix": "!",
  "language": "hu",
  "support_invite": "https://discord.gg/your-invite"
}
```

### 4. Running the Bot
```powershell
python main.py
```

## 🎮 Commands

### General User Commands
- `/event create`: Start the interactive creation wizard.
- `/event list`: Show all active events in the server.
- `/event search`: Find specific events by ID or title.

### Administrative Commands
- `/event admin setup`: Open the visual configuration console.
- `/event admin emojis`: Start the Emoji Wizard to create custom button sets.
- `/event admin messages`: Manage custom bot strings and localization.
- `/master system sync`: (Owner only) Sync slash commands globally or to the guild.

## 🤝 Support
If you have questions or need help setting up Nexus, join our community: [Support Server](https://discord.gg/your-invite)

---
*Created with ❤️ by Nexus Team*
