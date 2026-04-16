# utils/emojis.py
"""Centralized Emoji Registry for the Nexus Event Bot with context decoupling."""

# --- Core Status Icons ---
SUCCESS = "<:checkfilledcircledualgreenwhite:1493922385613815828>"
ERROR = "<:xfilledcircledualredwhite:1493920874011820114>"
WARNING = "<:warningfilledcircledualyellowbla:1493932991192502295>"
INFO = "<:infofilledcircledualbluewhite:1493932987966816296>"
PING = "<:pingfilledcircledualmagentawhite:1493932989317386320>"

# --- UI / Navigation ---
SYNC = "🔄"
DROPDOWN_OPEN = "🔽"
DROPDOWN_CLOSED = "◀️"
LANG_HU = "🇭🇺"
LANG_EN = "🇺🇸"
BACK = "⬅️"
FORWARD = "➡️"

# --- Common Items ---
CALENDAR = "📅"
CROWN = "👑"
SPARKLES = "✨"
GLOBE = "<:buttonglobe:1493863327321821205>"
BELL = "<:titleping:1493846908907683870>"
COUNTDOWN = "🕒"
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
TEMP_STD_YES = "<:templatesaccepted:1493965288407040172>"
TEMP_STD_MAYBE = "<:templatesmaybe:1493965290051076307>"
TEMP_STD_NO = "<:templatedeclined:1493965286817140797>"

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
