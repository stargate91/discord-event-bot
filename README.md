# Nexus - Discord Event Management Bot

Nexus is a professional-grade Discord event scheduling and management bot designed for gaming communities, e-sports organizations, and corporate servers. It provides a robust, interactive experience for creating, managing, and auditing events with deep Discord role integration.

## Key Features

### Advanced Event Lifecycle
- Interactive Creation Wizard: A step-by-step guided process for creating single, lobby-based, or recurring series events using modern Discord UI components.
- Lobby Mode: Dynamic queuing system for events without fixed start times, featuring automatic waitlist management and fill notifications.
- Recurring Logic: Automated management for daily, weekly, and monthly event series, including custom weekday patterns.

### Participant Management
- Role-Based RSVP: Support for multi-role signups (e.g., Tank, Heal, DPS) with individual slot limits and overflow handling.
- Intelligent Waitlists: Automatically moves users from waitlists to active slots when space becomes available.
- Attendance Tracking: Dedicated administrative interface for marking presence and managing no-shows following event completion.

### Administration and Analytics
- Reliability Audits: Comprehensive tracking of member reliability with automated statistic generation and audit logs.
- Message Customization: A dedicated Message Wizard for overriding default bot notifications with guild-specific templates and variables.
- Server Console: A centralized hub for managing server-wide defaults, notification types, and permissions.
- Icon Set Management: System to create and manage custom icon and button sets for a premium server-specific feel.

### Data and Integration
- Export Capabilities: Generate CSV files for Google Sheets import or ICS files for integration with Google Calendar, Outlook, and Apple Calendar.
- Multi-Locale Support: Full localization for English and Hungarian languages.
- V2 UI Architecture: Utilizes a consolidated container system with clear visual separators for enhanced readability.

## Technical Overview

- Core: Python 3.10+ utilizing the discord.py library.
- Database: High-performance PostgreSQL backend with asynchronous connection pooling.
- Design: Component-based architecture focused on visual hierarchy and user experience.
- Localization: Dynamic i18n system with per-guild overrides.

## Commands

### User Commands
- /event create: Initialize the interactive event creation wizard.
- /event list: Display all active and upcoming events.
- /event search: Search for specific events by identifier or title.
- /event my-events: View a personalized list of organized and joined events.

### Administrative Commands
- /server setup: Access the global configuration dashboard.
- /attendance manage: Audit participant presence for recent events.
- /admin check: Perform reliability audits on specific members or event series.
- /emoji setup: Configure server-wide icon and button themes.
- /message wizard: Customize automated bot notifications and templates.

---
Created by Nexus Team
