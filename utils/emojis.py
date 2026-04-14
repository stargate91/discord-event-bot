# utils/emojis.py
"""Centralized Emoji Registry for the Nexus Event Bot with context decoupling."""

# --- Helper for mass defining variations ---
def _expand(emoji):
    return {
        "base": emoji,
        "btn": emoji,
        "title": emoji,
        "msg": emoji,
        "lbl": emoji
    }

# --- Core Icons ---
# Format: CONCEPT_ROOT = "emoji"
# These are then expanded into specialized variants for context decoupling.

_CORE = {
    "SUCCESS": "✅",
    "ERROR": "❌",
    "INFO": "💡",
    "WARNING": "⚠️",
    "GEAR": "⚙️",
    "GLOBE": "🌐",
    "PEOPLE": "👥",
    "CLONE": "👯",
    "ADD": "➕",
    "CLOCK": "⏰",
    "TIME": "🕒",
    "LIST": "📋",
    "WIZARD": "✨",
    "DRAFT": "📝",
    "SHIELD": "🛡️",
    "BELL": "🔔",
    "PING": "📢",
    "SYNC": "🔄",
    "CROSS": "✖️",
    "HELP": "❓",
    "TOOLS": "🛠️",
    "PRESENCE": "🎮",
    "PIN": "📌",
    "WAIT": "⏳",
    "CALENDAR": "📅",
    "GEM": "💎",
    "CRYSTAL": "🔮",
    "STAR": "⭐",
    "HERB": "🌿",
    "FLOWER": "🌸",
    "PALETTE": "🎨",
    "TROPHY": "🏆",
    "HEADPHONES": "🎧",
    "EYES": "👀",
    "BOT": "🤖",
    "SATELLITE": "🛰️",
    "EDIT": "✏️",
    "DELETE": "🗑️",
    "BACK": "◀️",
    "FORWARD": "▶️",
    "PRESENT": "✅",
    "NOSHOW": "❌",
    "NAVPAGE": "📄",
    "PACKAGE": "📦",
    "TV": "📺",
    "REC_DAILY": "📅",
    "REC_WEEKLY": "🗓️",
    "REC_MONTHLY": "📊",
    "REC_BIWEEKLY": "🔄",
    "REC_WEEKDAYS": "🏢",
    "REC_WEEKENDS": "🏖️",
    "REC_CUSTOM": "⚙️",
    "REC_RELATIVE": "📆"
}

# Inject variations into the global namespace
# Pattern: CONCEPT (base), CONCEPT_BTN, CONCEPT_TITLE, CONCEPT_MSG, CONCEPT_LBL
for key, emoji in _CORE.items():
    globals()[key] = emoji
    globals()[f"{key}_BTN"] = emoji
    globals()[f"{key}_TITLE"] = emoji
    globals()[f"{key}_MSG"] = emoji
    globals()[f"{key}_LBL"] = emoji

# --- Context-Specific Overrides ---
# Ide írhatod azokat az emojikat, amiknél le akarod cserélni az alap _CORE ikont egy specifikus helyen.
# Például: Ha a SUCCESS_MSG máshogy nézzen ki, mint a SUCCESS_BTN.
_OVERRIDES = {
    "REC_MONTHLY_TITLE": "<:chartbarduotone:1493657119948538089>", # Custom Duotone Statisztika ikon
    "BOT_MSG": "<:robot:1493659538354733206>",
    "GLOBE_MSG": "<:globe:1493658134764584991>",
    "DRAFT_MSG": "<:notepencil:1493659536861564989>",
    "CALENDAR_MSG": "<:calendar:1493659532289904871>",
    "GEAR_MSG": "<:gear:1493659534005239920>",
    "SYNC_MSG": "<:arrowscounterclockwise:1493659531090202675>", # Frissítés / Szinkronizáció ikon
    "SUCCESS_MSG": "🟢", # Példa: Sima szövegben egy pötty
    "SUCCESS_LBL": "✨", # Példa: Címkénél egy csillag
}

# Felülírjuk az auto-generált alapokat a specifikus overrides-okkal
for key, emoji in _OVERRIDES.items():
    globals()[key] = emoji

# --- Specialized / Static Icons (No variations needed yet) ---
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
