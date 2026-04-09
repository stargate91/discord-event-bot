import re
import unicodedata

def slugify(text):
    """
    Converts to lowercase, removes non-word characters (alphanumerics and underscores)
    and converts spaces to hyphens. Also strips leading and trailing whitespace.
    Handles accents by converting to their ASCII equivalents.
    """
    # 1. Normalize to NFKD to separate accents from base characters
    text = unicodedata.normalize('NFKD', str(text))
    
    # 2. Encode to ASCII and ignore characters that can't be converted (accents)
    text = text.encode('ascii', 'ignore').decode('ascii')
    
    # 3. Lowercase
    text = text.lower()
    
    # 4. Remove everything that isn't a word character or a space/hyphen
    text = re.sub(r'[^\w\s-]', '', text)
    
    # 5. Replace whitespace and underscores with single hyphens
    text = re.sub(r'[-\s_]+', '-', text).strip('-')
    
    return text
