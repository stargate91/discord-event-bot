# utils/emojis.py
"""Centralized Emoji Registry for the Nexus Event Bot with context decoupling."""

# --- Specialized / Static Icons ---
DROPDOWN_OPEN = "🔽"
DROPDOWN_CLOSED = "◀️"
LANG_HU = "🇭🇺"
LANG_EN = "🇺🇸"

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
