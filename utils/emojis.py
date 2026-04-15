# utils/emojis.py
"""Centralized Emoji Registry for the Nexus Event Bot with context decoupling."""

# --- Core Status Icons ---
SUCCESS = "<:statussuccess:1493841535559663747>"
ERROR = "<:statuserror:1493833100382310430>"
WARNING = "<:statuswarning:1493835074196607006>"
INFO = "<:statusinfo:1493836039284850708>"
PING = "<:statusping:1493844918496395264>"

# --- UI / Navigation ---
BACK = "⬅️"
FORWARD = "➡️"
CROSS = "❌"
HELP = "❔"
SYNC = "🔄"
DROPDOWN_OPEN = "🔽"
DROPDOWN_CLOSED = "◀️"
LANG_HU = "🇭🇺"
LANG_EN = "🇺🇸"

# --- Common Items ---
GEAR = "⚙️"
GLOBE = "🌐"
BELL = "<:titleping:1493846908907683870>"
SHIELD = "🛡️"

# --- Recurrence Icons ---
REC_DAILY = "📅"
REC_WEEKLY = "🗓️"
REC_MONTHLY = "📊"
REC_BIWEEKLY = "⏳"
REC_WEEKDAYS = "💼"
REC_WEEKENDS = "🎉"
REC_CUSTOM = "⚙️"
REC_RELATIVE = "🕒"

# --- Template-Specific RSVP Icons ---
TEMP_STD_YES = "✅"
TEMP_STD_MAYBE = "❓"
TEMP_STD_NO = "❌"

TEMP_MMO_TANK = "🛡️"
TEMP_MMO_HEAL = "🏥"
TEMP_MMO_DPS = "🗡️"
TEMP_MMO_MAYBE = "❓"
TEMP_MMO_NO = "❌"

TEMP_SURVEY_LIKE = "👍"
TEMP_SURVEY_DISLIKE = "👎"

TEMP_TEAM_A = "🅰️"
TEMP_TEAM_B = "🅱️"
TEMP_TEAM_SPECTATE = "👀"
TEMP_TEAM_MAYBE = "❓"
TEMP_TEAM_NO = "❌"

def get_all_emojis():
    """Returns a dictionary of all uppercase constants defined in this module."""
    return {k: v for k, v in globals().items() if k.isupper() and isinstance(v, str)}
