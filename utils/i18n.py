import json
import os

LANG = "hu"
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config_data = json.load(f)
        LANG = config_data.get("language", "hu")
except Exception:
    pass

TRANSLATIONS = {}

lang_file = f"locales/{LANG}.json"
if os.path.exists(lang_file):
    with open(lang_file, "r", encoding="utf-8") as f:
        TRANSLATIONS = json.load(f)

def t(key: str, **kwargs):
    text = TRANSLATIONS.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
