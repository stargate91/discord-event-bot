import json
import os
import database

# Default fallback language from config
DEFAULT_LANG = "hu"
try:
    from utils.jsonc import load_jsonc
    config_data = load_jsonc('config.json')
    DEFAULT_LANG = config_data.get("language", "hu")
except Exception:
    pass

# Load all available language files
ALL_MESSAGES = {} # {"hu": {...}, "en": {...}}
LOCALES_DIR = "locales"

if os.path.exists(LOCALES_DIR):
    for filename in os.listdir(LOCALES_DIR):
        if filename.endswith(".json"):
            lang_code = filename[:-5] # remove .json
            try:
                with open(os.path.join(LOCALES_DIR, filename), "r", encoding="utf-8") as f:
                    ALL_MESSAGES[lang_code] = json.load(f)
            except Exception as e:
                print(f"Error loading {filename}: {e}")

GUILD_CACHE = {} # {guild_id: {"overrides": {...}, "lang": "hu"}}

async def load_guild_translations(guild_id):
    """Fetch overrides and settings from DB and cache them."""
    gid_str = str(guild_id)
    
    overrides = await database.get_guild_translations(guild_id)
    settings = await database.get_all_guild_settings(guild_id)
    guild_lang = settings.get("language", DEFAULT_LANG)
    
    GUILD_CACHE[gid_str] = {
        "overrides": overrides,
        "settings": settings,
        "lang": guild_lang
    }
    return GUILD_CACHE[gid_str]

def t(key: str, guild_id=None, **kwargs):
    """
    Translates a key with multi-layer priority:
    1. Guild-specific override (DB)
    2. Guild-specific preferred language (JSON)
    3. Global default language (JSON)
    4. The key itself
    """
    text = None
    pref_lang = DEFAULT_LANG
    gid_str = str(guild_id) if guild_id else None

    # 1. Check Guild Cache for overrides and preferred language
    if gid_str and gid_str in GUILD_CACHE:
        cache = GUILD_CACHE[gid_str]
        text = cache["overrides"].get(key)
        pref_lang = cache.get("lang", DEFAULT_LANG)

    # 2. If no override, try the preferred language file
    if text is None:
        lang_dict = ALL_MESSAGES.get(pref_lang, ALL_MESSAGES.get(DEFAULT_LANG, {}))
        text = lang_dict.get(key)

    # 3. Fallback to default language if not found in preferred
    if text is None and pref_lang != DEFAULT_LANG:
        text = ALL_MESSAGES.get(DEFAULT_LANG, {}).get(key)

    # 4. Final fallback to key
    if text is None:
        text = key
    
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text

# Categories for the Message Wizard
CATEGORIES = {
    "Embed": [
        "BTN_ACCEPT", "BTN_DECLINE", "BTN_TENTATIVE", "EMBED_START_TIME", "EMBED_RECURRENCE",
        "EMBED_ACC", "EMBED_DEC", "EMBED_TEN", "EMBED_NONE", "EMBED_FOOTER", "EMBED_FULL",
        "EMBED_WAITLIST", "TAG_CANCELLED", "TAG_POSTPONED", "TAG_DELETED", "TAG_PAST",
        "RSVP_ACCEPTED", "RSVP_DECLINED", "RSVP_TENTATIVE", "RSVP_TANK", "RSVP_HEAL",
        "RSVP_DPS", "RSVP_TEAM_A", "RSVP_TEAM_B", "RSVP_SPECTATOR", "RSVP_ON_TIME",
        "RSVP_LATE", "RSVP_INTERIM"
    ],
    "Wizard": [
        "WIZARD_TITLE", "WIZARD_DESC", "WIZARD_STATUS_OK", "WIZARD_STATUS_WAIT",
        "BTN_STEP_1", "BTN_STEP_2", "BTN_STEP_3", "BTN_STEP_4", "BTN_SUBMIT",
        "BTN_SAVE_PREVIEW", "BTN_PUBLISH", "BTN_EDIT", "BTN_DELETE",
        "LBL_WIZ_CREATOR", "LBL_WIZ_NAME", "LBL_WIZ_TITLE", "LBL_WIZ_DESC",
        "LBL_WIZ_IMAGES", "LBL_WIZ_COLOR", "LBL_WIZ_MAX", "LBL_WIZ_PING",
        "LBL_WIZ_START", "LBL_WIZ_END", "SEL_REC_TYPE", "SEL_REC_NONE",
        "SEL_REC_DAILY", "SEL_REC_WEEKLY", "SEL_REC_MONTHLY", "SEL_TRIG_TYPE",
        "SEL_TRIG_BEFORE", "SEL_TRIG_AFTER_START", "SEL_TRIG_AFTER_END"
    ],
    "Errors": [
        "ERR_ADMIN_ONLY", "ERR_CHANNEL_ONLY", "ERR_DATE_FMT", "ERR_REC_FMT",
        "ERR_EV_NOT_FOUND", "ERR_EV_INACTIVE", "ERR_NO_PERM"
    ],
    "Success": [
        "MSG_EV_CREATED_EPHEMERAL", "MSG_EV_CREATED_PUBLIC", "MSG_REM_DESC",
        "MSG_REC_ALERT", "MSG_DRAFT_SAVED", "MSG_DRAFT_DELETED", "MSG_DRAFTS_CLEARED",
        "MSG_SAVED_PREVIEW", "MSG_STATUS_UPDATED", "MSG_EVENT_REMOVED",
        "MSG_KEY_SAVED", "MSG_RESET_SUCCESS"
    ]
}
