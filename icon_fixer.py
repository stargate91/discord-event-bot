import os
import glob
from PIL import Image, ImageDraw

def fix_icon(image_path, output_path):
    img = Image.open(image_path).convert("RGBA")
    width, height = img.size
    pixels = img.load()
    
    # Készítünk egy maszkot az átlátszó részekről
    mask = Image.new("L", (width, height), 0)
    for y in range(height):
        for x in range(width):
            if pixels[x, y][3] == 0: # Ha teljesen átlátszó
                mask.putpixel((x, y), 255)
                
    # A legszéléről indulva "kifestjük" a külső átlátszó teret (128-as értékre)
    ImageDraw.floodfill(mask, (0, 0), 128)
    ImageDraw.floodfill(mask, (width-1, 0), 128)
    ImageDraw.floodfill(mask, (0, height-1), 128)
    ImageDraw.floodfill(mask, (width-1, height-1), 128)
    
    # Visszaírjuk a képet:
    # Ami 255 maradt a maszkban, az a belső "lyuk", azt kifehérítjük!
    # A dobozt a saját színében, a külső űrt pedig átlátszóan hagyjuk.
    for y in range(height):
        for x in range(width):
            if mask.getpixel((x, y)) == 255:
                pixels[x, y] = (255, 255, 255, 255) # Kifehérítjük a belső lyukat
                
    img.save(output_path)
    print(f"Javítva (színek megtartva): {output_path}")

os.makedirs("fixed_icons", exist_ok=True)
for f in glob.glob("*.png"):
    fix_icon(f, os.path.join("fixed_icons", f))
