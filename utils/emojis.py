# utils/emojis.py
"""Centralized Emoji Registry for the Nexus Event Bot."""

# Common Status Indicators
SUCCESS = "✅"
ERROR = "❌"
INFO = "💡"
WARNING = "⚠️"

# UI Elements & Navigation
DROPDOWN_OPEN = "🔽"
DROPDOWN_CLOSED = "◀️"
GEAR = "⚙️"
GLOBE = "🌐"
PEOPLE = "👥"
CLONE = "👯"
ADD = "➕"
CLOCK = "⏰"
TIME = "🕒"
LIST = "📋"
WIZARD = "✨"
DRAFT = "📝"
SHIELD = "🛡️"
BELL = "🔔"
PING = "📢"
SYNC = "🔄"
CROSS = "✖️"
HELP = "❓"
TOOLS = "🛠️"
PRESENCE = "🎮"
PIN = "📌"
WAIT = "⏳"
CALENDAR = "📅"
GEM = "💎"
CRYSTAL = "🔮"
STAR = "⭐"
HERB = "🌿"
FLOWER = "🌸"
PALETTE = "🎨"
TROPHY = "🏆"
HEADPHONES = "🎧"
EYES = "👀"
BOT = "🤖"
SATELLITE = "🛰️"
EDIT = "✏️"
DELETE = "🗑️"
BACK = "◀️"
FORWARD = "▶️"
PRESENT = "✅"
NOSHOW = "❌"
NAVPAGE = "📄"
LANG_HU = "🇭🇺"
LANG_EN = "🇺🇸"
PACKAGE = "📦"
TV = "📺"

# Template-Specific RSVP Icons
# Standard
TEMP_STD_YES = "✅"
TEMP_STD_MAYBE = "❓"
TEMP_STD_NO = "❌"

# MMO
TEMP_MMO_TANK = "🛡️"
TEMP_MMO_HEAL = "🏥"
TEMP_MMO_DPS = "🗡️"
TEMP_MMO_MAYBE = "❓"
TEMP_MMO_NO = "❌"

# Survey
TEMP_SURVEY_LIKE = "👍"
TEMP_SURVEY_DISLIKE = "👎"

# Teams
TEMP_TEAM_A = "🅰️"
TEMP_TEAM_B = "🅱️"
TEMP_TEAM_SPECTATE = "👀"
TEMP_TEAM_MAYBE = "❓"
TEMP_TEAM_NO = "❌"

# Recurrence Types
REC_DAILY = "📅"
REC_WEEKLY = "🗓️"
REC_MONTHLY = "📊"
REC_BIWEEKLY = "🔄"
REC_WEEKDAYS = "🏢"
REC_WEEKENDS = "🏖️"
REC_CUSTOM = "⚙️"
REC_RELATIVE = "📆"

def get_all_emojis():
    """Returns a dictionary of all uppercase constants defined in this module."""
    return {k: v for k, v in globals().items() if k.isupper() and isinstance(v, str)}
