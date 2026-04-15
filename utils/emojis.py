# utils/emojis.py
"""Centralized Emoji Registry for the Nexus Event Bot with context decoupling."""

# --- Core Status Icons ---
SUCCESS = "<:statussuccess:1493856972850856028>"
ERROR = "<:statuserror:1493861993742860318>"
WARNING = "<:statuswarning:1493856974088048692>"
INFO = "<:statusinfo:1493856969663189052>"
PING = "<:statusping:1493861847064121344>"

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
GLOBE = "<:buttonglobe:1493863327321821205>"
BELL = "<:titleping:1493846908907683870>"
SHIELD = "<:exampleemojiwizard:1493863833973035068>"

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
