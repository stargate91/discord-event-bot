"""
Report en.json keys not referenced in Python source (heuristic).

Includes dynamic uses: SEL_REC_*, PRESENCE_TYPE_*, KEY_* from i18n.CATEGORIES,
and label_key / list_label_key strings from utils/templates.py (read-only scan).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def collect_py_blob():
    parts = []
    for p in ROOT.rglob("*.py"):
        if "venv" in p.parts or ".venv" in p.parts:
            continue
        try:
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    return "\n".join(parts)


def collect_template_keys():
    p = ROOT / "utils" / "templates.py"
    if not p.exists():
        return set()
    text = p.read_text(encoding="utf-8", errors="replace")
    keys = set(re.findall(r'"(?:label_key|list_label_key)"\s*:\s*"([A-Z0-9_]+)"', text))
    return keys


def implied_keys_from_categories():
    from utils.i18n import CATEGORIES

    out = set()
    for _cat, keys in CATEGORIES.items():
        for k in keys:
            out.add(f"KEY_{k}")
            out.add(k)
    return out


def main():
    with open(ROOT / "locales" / "en.json", encoding="utf-8") as f:
        all_keys = sorted(json.load(f).keys())

    py_blob = collect_py_blob()
    tmpl_keys = collect_template_keys()

    try:
        cat_keys = implied_keys_from_categories()
    except Exception:
        cat_keys = set()

    def quoted_in_py(k: str) -> bool:
        return f'"{k}"' in py_blob or f"'{k}'" in py_blob

    used = set()
    for k in all_keys:
        if quoted_in_py(k):
            used.add(k)
            continue
        if k in tmpl_keys:
            used.add(k)
            continue
        if k in cat_keys:
            used.add(k)
            continue
        if k.startswith("SEL_REC_") and 'SEL_REC_' in py_blob:
            used.add(k)
            continue
        if k.startswith("PRESENCE_TYPE_") and "PRESENCE_TYPE_" in py_blob:
            used.add(k)
            continue

    unused = [k for k in all_keys if k not in used]

    print(f"en.json keys: {len(all_keys)}")
    print(f"Used (quoted in .py, template label_key, CATEGORIES, or dynamic prefix): {len(used)}")
    print(f"Unused / dead keys: {len(unused)}")
    for k in unused:
        print(k)


if __name__ == "__main__":
    main()
