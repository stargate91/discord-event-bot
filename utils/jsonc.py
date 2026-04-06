import json
import re

def load_jsonc(filepath):
    """Load a JSON file that may contain // comments."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    # Remove // comments (but not inside strings)
    content = re.sub(r'(?<!:)//.*', '', content)
    # Remove trailing commas before } or ]
    content = re.sub(r',\s*([}\]])', r'\1', content)
    return json.loads(content)
