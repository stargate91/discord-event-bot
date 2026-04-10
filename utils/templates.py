from utils.emoji_utils import parse_emoji_config

# Canonical Template IDs and their human-readable strings (6-column format)
# Format: Emoji | Label | List Label | Limit | Flags
ICON_SET_TEMPLATES = {
    "basic": {
        "id": "basic",
        "label_key": "TEMP_BASIC", # "Alap (Igen / Nem)"
        "emoji": "✅",
        "text": "✅ | Résztveszek | Résztvevők | 0 | SPBG\n❓ | Talán | Bizonytalan | 0 | SB\n❌ | Nem jövök | - | 0 | ER"
    },
    "raid": {
        "id": "raid",
        "label_key": "TEMP_RAID", # "Raid (Tank / Heal / DPS)"
        "emoji": "⚔️",
        "text": "🛡️ | Tank | Tankok | 2 | SPBG\n🏥 | Heal | Healerek | 4 | SPBG\n🗡️ | DPS | DPS-ek | 10 | SPBG\n❓ | Tartalék | Tartalékok | 0 | SB\n❌ | Nem jövök | - | 0 | ER"
    },
    "survey": {
        "id": "survey",
        "label_key": "TEMP_SURVEY", # "Szavazás (👍 / 👎)"
        "emoji": "📊",
        "text": "👍 | Szuper | Szerintük jó | 0 | SPBG\n👎 | Rossz | Szerintük rossz | 0 | ER"
    },
    "teams": {
        "id": "teams",
        "label_key": "SET_TEAMS", # "Csapatok (🅰️, 🅱️, 👁️)"
        "emoji": "🚩",
        "text": "🅰️ | A Csapat | A Csapat | 0 | SPBG\n🅱️ | B Csapat | B Csapat | 0 | SPBG\n👁️ | Néző | Nézők | 0 | SB"
    }
}

def get_template_data(template_id: str):
    """Returns the parsed JSON-ready dict for a given template."""
    tmpl = ICON_SET_TEMPLATES.get(template_id)
    if not tmpl:
        return None
    
    opts, pos_count = parse_emoji_config(tmpl["text"])
    return {
        "options": opts,
        "positive_count": pos_count,
        "buttons_per_row": 5,
        "show_mgmt": True
    }
