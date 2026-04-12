import json
import os
import database

# Default fallback language from config
DEFAULT_LANG = "en"
try:
    from utils.jsonc import load_jsonc
    config_data = load_jsonc('config.json')
    DEFAULT_LANG = config_data.get("language", "en")
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

def t(translation_key: str, guild_id=None, use_template_lang=False, **kwargs):
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
        text = cache["overrides"].get(translation_key)
        
        pref_lang = cache.get("lang", DEFAULT_LANG)
        if use_template_lang and "settings" in cache:
            tpl_lang = cache["settings"].get("template_language", "default")
            if tpl_lang != "default":
                pref_lang = tpl_lang

    # 2. If no override, try the preferred language file
    if text is None:
        lang_dict = ALL_MESSAGES.get(pref_lang, ALL_MESSAGES.get(DEFAULT_LANG, {}))
        text = lang_dict.get(translation_key)

    # 3. Fallback to default language if not found in preferred
    if text is None and pref_lang != DEFAULT_LANG:
        text = ALL_MESSAGES.get(DEFAULT_LANG, {}).get(translation_key)

    # 4. Final fallback to key
    if text is None:
        text = translation_key
    
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text

# Essential Templates for the Notification Wizard
CATEGORIES = {
    "Notifications": [
        "MSG_DEFAULT_PROMO",
        "MSG_PROMOTED_DEFAULT",
        "MSG_WAITLIST_HINT",
        "MSG_REM_DESC",
        "MSG_EVENT_CANCELLED",
        "MSG_EVENT_POSTPONED"
    ]
