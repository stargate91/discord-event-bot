from utils.emoji_utils import parse_emoji_config

# Canonical Template IDs and their human-readable strings (6-column format)
# Format: Emoji | Label | List Label | Limit | Flags
ICON_SET_TEMPLATES = {
    "standard": {
        "id": "standard",
        "label_key": "TEMP_STANDARD", # "Alap (Igen / Nem)"
        "emoji": "",
        "text": "✅ | I'm coming | Coming | 0 | SPEY\n❓ | Maybe | Not sure | 0 | SEY\n❌ | Not coming | Not coming | 0 | SEY"
    },
    "mmo": {
        "id": "mmo",
        "label_key": "TEMP_MMO", # "Raid (Tank / Heal / DPS)"
        "emoji": "",
        "text": "🛡️ | Tank | Tanks | 0 | SPEY\n🏥 | Heal | Healers | 0 | SPEY\n🗡️ | DPS | DPSes | 0 | SPEY\n❓ | Maybe | Not sure | 0 | SEY\n❌ | Not coming | Not coming | 0 | SEY"
    },
    "survey": {
        "id": "survey",
        "label_key": "TEMP_SURVEY", # "Szavazás (👍 / 👎)"
        "emoji": "",
        "text": "👍 | Like | Liked it | 0 | SPEY\n👎 | Dislike | Disliked it | 0 | SPEY"
    },
    "teams": {
        "id": "teams",
        "label_key": "SET_TEAMS", # "Csapatok (🅰️, 🅱️, 👁️)"
        "emoji": "",
        "text": "🅰️ | Team A | Team A | 0 | SPBB\n🅱️ | Team B | Team B | 0 | SPBB\n👀 | I'll spectate | Spectators | 0 | SPBB\n❓ | Maybe | Unsure | 0 | SBB\n❌ | Not coming | Not coming | 0 | SBB"
    }
}

def get_template_data(template_id: str):
    """Returns the parsed JSON-ready dict for a given template."""
    tmpl = ICON_SET_TEMPLATES.get(template_id)
    if not tmpl:
        return None
    
    opts, pos_count = parse_emoji_config(tmpl["text"])
    
    KEY_MAP = {
        "im_coming": {"label_key": "BTN_ACCEPT", "list_label_key": "RSVP_ACCEPTED"},
        "maybe": {"label_key": "BTN_TENTATIVE", "list_label_key": "RSVP_TENTATIVE"},
        "not_coming": {"label_key": "BTN_DECLINE", "list_label_key": "RSVP_DECLINED"},
        "tank": {"list_label_key": "RSVP_TANK"},
        "heal": {"list_label_key": "RSVP_HEAL"},
        "dps": {"list_label_key": "RSVP_DPS"},
        "team_a": {"list_label_key": "RSVP_TEAM_A"},
        "team_b": {"list_label_key": "RSVP_TEAM_B"},
        "ill_spectate": {"list_label_key": "RSVP_SPECTATOR"},
    }
    for o in opts:
        km = KEY_MAP.get(o["id"])
        if km:
            if "label_key" in km: o["label_key"] = km["label_key"]
            if "list_label_key" in km: o["list_label_key"] = km["list_label_key"]

    return {
        "options": opts,
        "positive_count": pos_count,
        "buttons_per_row": 5,
        "show_mgmt": False
    }
