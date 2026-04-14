import os
import glob
from PIL import Image, ImageDraw

def is_near(c1, c2, tol=30):
    """Check if two colors are within a Euclidean distance tolerance in RGB."""
    return sum((a-b)**2 for a, b in zip(c1[:3], c2[:3])) < tol**2

def fix_icon(image_path, output_path):
    img = Image.open(image_path).convert("RGBA")
    width, height = img.size
    pixels = img.load()
    
    # 1. Automatikus háttérszín felismerés a sarkokból
    corners = [pixels[0,0], pixels[width-1, 0], pixels[0, height-1], pixels[width-1, height-1]]
    # Kiválasztjuk a leggyakoribb színt vagy az (0,0) pontot alapnak
    bg_color = corners[0] 
    
    # 2. Maszk készítése: minden, ami "háttérszín" vagy átlátszó, az 255-ös lesz
    mask = Image.new("L", (width, height), 0)
    for y in range(height):
        for x in range(width):
            c = pixels[x, y]
            if c[3] == 0 or is_near(c, bg_color):
                mask.putpixel((x, y), 255)
    
    # 3. Külső "űr" kifestése a maszkban (floodfill a sarkokból)
    # Ha a sarok 255, akkor onnan indulva mindent 128-ra festünk
    for start_pos in [(0,0), (width-1, 0), (0, height-1), (width-1, height-1)]:
        if mask.getpixel(start_pos) == 255:
            ImageDraw.floodfill(mask, start_pos, 128)
            
    # 4. Visszaírás a képre
    for y in range(height):
        for x in range(width):
            m_val = mask.getpixel((x, y))
            if m_val == 255: # BELSŐ LYUK -> Fekete
                pixels[x, y] = (0, 0, 0, 255)
            elif m_val == 128: # KÜLSŐ HÁTTÉR -> Átlátszó
                pixels[x, y] = (0, 0, 0, 0)
            # 0 esetén (ikon maga) marad az eredeti pixel
                
    img.save(output_path)
    print(f"Javítva (fekete lyukak + átlátszó háttér): {output_path}")

os.makedirs("fixed_icons_black", exist_ok=True)
for f in glob.glob("*.png"):
    # Ne dolgozzuk fel a már javítottakat, ha véletlenül ott vannak
    if "fixed_icons" in f: continue 
    fix_icon(f, os.path.join("fixed_icons_black", f))
