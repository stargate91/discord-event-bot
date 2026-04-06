import json
import re

def load_jsonc(filepath):
    """Load a JSON file that may contain // comments.
    Handles // inside strings (like URLs) correctly."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    cleaned_lines = []
    for line in lines:
        # Walk through the line character by character
        # to find // that are NOT inside a string
        result = []
        in_string = False
        escape = False
        i = 0
        while i < len(line):
            ch = line[i]
            if escape:
                result.append(ch)
                escape = False
                i += 1
                continue
            if ch == '\\' and in_string:
                result.append(ch)
                escape = True
                i += 1
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                i += 1
                continue
            if not in_string and ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
                # Found a comment outside a string, skip rest of line
                break
            result.append(ch)
            i += 1
        cleaned_lines.append(''.join(result))
    
    content = '\n'.join(cleaned_lines)
    # Remove trailing commas before } or ]
    content = re.sub(r',\s*([}\]])', r'\1', content)
    return json.loads(content)
