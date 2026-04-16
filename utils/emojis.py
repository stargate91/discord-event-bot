# utils/emojis.py
"""Centralized Emoji Registry for the Nexus Event Bot with context decoupling."""

# --- Core Status Icons ---
SUCCESS = "<:checkfilledcircle:1494217224951693415>"
ERROR = "<:xfilledcircle:1494217327481327708>"
WARNING = "<:warningfilledcircle:1494217458087624767>"
INFO = "<:infofilledcircle:1494217550807044198>"
PING = "<:bellfilledcircle:1494217650782474292>"

# --- UI / Navigation ---
SYNC = "<:arrowsclockwiseoutlined:1494217806282096811>"
DROPDOWN_OPEN = "<:arrowdownfilled:1494218548074123324>"
DROPDOWN_CLOSED = "<:arrowleftfilled:1494218478456930384>"
LANG_HU = "🇭🇺"
LANG_EN = "🇺🇸"
BACK = "<:chevronleftfilled:1494218659017527328>"
FORWARD = "<:chevronrightfilled:1494218707944214628>"

# --- Common Items ---
CALENDAR = "<:calendaroutlined:1494218780883161179>"
CROWN = "<:crownoutlined:1494218840945463307>"
SPARKLES = "<:useroutlined:1494218939012485232>"
GLOBE = "<:globefilled:1494219004263272478>"
BELL = "<:bellcolorful:1494220079506788512>"
COUNTDOWN = "<:timeroutlined:1494220240584708189>"
SHIELD = "🛡️"
INDICATOR = "🔹"
PREVIEW = "<:magnifyingglassoutlined:1494220361246576671>"
IDEA = "<:infooutlined:1494220433673814016>"

# --- Recurrence Icons ---
REC_DAILY = ""
REC_WEEKLY = ""
REC_MONTHLY = ""
REC_BIWEEKLY = ""
REC_WEEKDAYS = ""
REC_WEEKENDS = ""
REC_CUSTOM = ""
REC_RELATIVE = ""

# --- Template-Specific RSVP Icons ---
TEMP_STD_YES = "<:standardtemplateaccepted:1494220669897150564>"
TEMP_STD_MAYBE = "<:standardtemplatemaybe:1494220672661192845>"
TEMP_STD_NO = "<:standardtemplatedeclined:1494220671319019602>"

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
