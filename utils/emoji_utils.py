import unicodedata
import re

def slugify(text: str) -> str:
    """Converts a string to a safe ASCII slug (lowercase, underscores, no accents)."""
    # Normalize to NFD to separate accents (e.g. á -> a + ´)
    text = unicodedata.normalize('NFD', text)
    # Filter out non-ASCII characters (accents)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    # Lowercase and replace anything non-alphanumeric with underscores
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    # Remove leading/trailing underscores
    return text.strip('_')

def parse_emoji_config(text_value: str):
    """Parses a text block into a list of option dicts.
    Format: Emoji | Label | List | Limit | Flags
    Returns (new_opts, positive_count)
    """
    new_opts = []
    positive_count = 0
    lines = text_value.strip().split("\n")
    color_map = {"G": "success", "R": "danger", "B": "primary", "Y": "secondary"}
    
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line: continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2: 
            raise ValueError(f"Line {i}: Too few columns (need at least Emoji | Label)")
        
        emoji = parts[0]
        btn_label = parts[1]
        list_label = parts[2] if len(parts) > 2 and parts[2] else btn_label
        oid = slugify(btn_label)
        
        limit = 0
        if len(parts) > 3:
            try:
                limit = int(parts[3])
            except (ValueError, TypeError):
                limit = 0
            
        flags = parts[4].upper() if len(parts) > 4 else "SPB"
        show_in_list = "S" in flags
        is_positive = "P" in flags
        if is_positive: positive_count += 1
        
        style = "emoji" if "E" in flags else ("label" if "T" in flags else "both")
        btn_color = "secondary"
        for code, name in color_map.items():
            if code in flags: btn_color = name; break
            
        new_opts.append({
            "id": oid, "emoji": emoji, "label": btn_label, "list_label": list_label,
            "max_slots": limit, "button_style": style, "button_color": btn_color,
            "show_in_list": show_in_list, "positive": is_positive
        })
        
    return new_opts, positive_count

def resolve_placeholders(text: str) -> str:
    """Replaces all {PLACEHOLDERS} in a string with their centralized registry values."""
    if not text or "{" not in text:
        return text
    
    try:
        from utils.emojis import get_all_emojis
        registry = get_all_emojis()
        
        def replace(match):
            key = match.group(1).upper()
            return registry.get(key, match.group(0)) # Fallback to original text if key not found
        
        import re
        return re.sub(r"\{([a-zA-Z0-9\_]+)\}", replace, text)
    except Exception:
        return text
def split_emoji(label: str):
    import discord
    import re
    emoji_obj = None
    m = re.match(r'^(<a?:[a-zA-Z0-9_]+:[0-9]+>)\s*', label)
    if m:
        raw = m.group(1)
        label = label[m.end():]
        try:
            emoji_obj = discord.PartialEmoji.from_str(raw)
        except Exception:
            pass
    if not emoji_obj and not m:
        um = re.match(r'^([\U00002600-\U0001FFFF]+)\s*', label)
        if um:
            emoji_obj = um.group(1)
            label = label[um.end():]
    return emoji_obj, label

def make_select_option(label: str, **kwargs):
    """Create a discord.SelectOption, auto-extracting any leading custom emoji
    from *label* into the separate ``emoji`` kwarg so Discord renders it
    properly (SelectOption.label is plain-text only).

    Usage::

        make_select_option(label=t("COLOR_DEFAULT", ...), value="0x40C4FF")
    """
    import discord
    import re

    emoji_obj = kwargs.pop("emoji", None)
    # Match leading Discord custom emoji: <:name:id> or <a:name:id>
    m = re.match(r'^(<a?:[a-zA-Z0-9_]+:[0-9]+>)\s*', label)
    if m and not emoji_obj:
        raw = m.group(1)
        label = label[m.end():]  # strip emoji from visible label
        try:
            emoji_obj = discord.PartialEmoji.from_str(raw)
        except Exception:
            pass

    # Also handle leading standard unicode emoji (single char / multi-code-point)
    if not emoji_obj and not m:
        um = re.match(r'^([\U00002600-\U0001FFFF]+)\s*', label)
        if um:
            emoji_obj = um.group(1)
            label = label[um.end():]

    return discord.SelectOption(label=label[:100], emoji=emoji_obj, **kwargs)


def to_emoji(emoji_str: str):
    """Converts a string to a discord.PartialEmoji if it matches custom emoji format, 
    resolves {PLACEHOLDERS} from the registry, otherwise returns original."""
    if not emoji_str:
        return None
    emoji_str = str(emoji_str).strip()

    # Dynamic Placeholder Resolution
    if emoji_str.startswith("{") and emoji_str.endswith("}"):
        try:
            from utils.emojis import get_all_emojis
            registry = get_all_emojis()
            key = emoji_str[1:-1].upper()
            if key in registry:
                return registry[key]
        except Exception:
            pass

    # Check for Discord custom emoji format: <:name:id> or <a:name:id>
    import discord
    import re
    if re.match(r'^<(a?):[a-zA-Z0-9\_]+:[0-9]+>$', emoji_str):
        try:
            return discord.PartialEmoji.from_str(emoji_str)
        except Exception:
            return emoji_str
    return emoji_str
