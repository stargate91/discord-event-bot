# Nexus - Discord Event Bot

Nexus is a professional-grade Discord event scheduling and management bot designed for gaming communities, e-sports organizers, and corporate servers. It features an interactive wizard-driven event creation process, robust recurring event logic, and deep integration with Discord roles.

## Features

- **Interactive Event Wizard**: Create complex events step-by-step using modern Discord Components V2.
- **Lobby Mode**: Enable dynamic queuing for events without fixed start times. Automatically manages waitlists and fill notifications.
- **Recurring Events**: Support for Daily, Weekly, Monthly, and custom weekday recurrences with automatic series management.
- **Attendance Manager**: Premium administrative interface to track who actually showed up at the event.
- **Reliability Audits**: Track member reliability with automated no-show statistics and server-wide leaderboards.
- **Dynamic RSVP System**: Professional interaction-based layouts for accepting, declining, or marking tentative status.
- **Advanced Slot Management**: Role-specific limits (e.g., Tank, Heal, DPS) and intelligent waiting list handling.
- **Smart Notifications**: Multi-stage reminders via Pings or DMs and automatic temporary role assignment.
- **Full Localization**: Complete support for Hungarian (HU) and English (EN) languages.
- **Master Console**: Centralized visual interface for all guild-wide settings and defaults.

## Technology Stack

- **Language**: Python 3.10+
- **Library**: discord.py (v2.5+ with Components V2 support)
- **Database**: PostgreSQL (via asyncpg for high performance)
- **Time Handling**: Centralized timezone management with python-dateutil.
- **UI Architecture**: Custom LayoutView system optimized for Discord's latest UI protocol.

## Getting Started

### 1. Requirements
- Python 3.10 or higher
- PostgreSQL 13+
- Discord Bot Token with Message Content and Member Intents

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

### 4. Running the Bot
```powershell
python main.py
```

## Commands

### General User Commands
- /event create: Start the interactive creation wizard.
- /event list: Show all active events in the server.
- /event search: Find specific events by ID or title.

### Administrative Commands
- /attendance manage: Track presence and no-shows for recent events.
- /admin check: Performance reliability audits for specific events or all-time stats.
- /event edit: Visually modify active events or series.
- /server setup: Access the server configuration hub.
- /emoji setup: Create and manage custom button and icon sets.

---
*Created by Nexus Team*
