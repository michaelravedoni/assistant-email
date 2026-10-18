"""Génère les icônes : app (PNG + .icns) et barre de menus (modèle noir sur transparent). Nécessite Pillow."""
import struct
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "assistant_email" / "assets"
S = 4  # suréchantillonnage


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return m


def gradient(size, top, bottom):
    g = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return g.resize((size, size))


def sparkle(draw, cx, cy, r, fill):
    pts = []
    import math
    for i in range(8):
        ang = math.pi / 4 * i - math.pi / 2
        rad = r if i % 2 == 0 else r * 0.28
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=fill)


def app_icon(size=1024):
    big = size * S
    # grille macOS : carré arrondi de 824/1024 centré
    m = int(big * 100 / 1024)
    inner = big - 2 * m
    base = gradient(inner, (84, 160, 255), (10, 84, 214)).convert("RGBA")
    mask = rounded_mask(inner, int(inner * 0.2237))
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    # ombre
    shadow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 90), (m, m + int(big * 0.012)), mask)
    from PIL import ImageFilter
    shadow = shadow.filter(ImageFilter.GaussianBlur(big * 0.012))
    tile = Image.alpha_composite(tile, shadow)
    base.putalpha(mask)
    tile.alpha_composite(base, (m, m))
    d = ImageDraw.Draw(tile)
    # enveloppe
    ew, eh = int(inner * 0.62), int(inner * 0.44)
    ex, ey = (big - ew) // 2, int(big * 0.5 - eh * 0.45)
    env = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ed = ImageDraw.Draw(env)
    ed.rounded_rectangle((ex, ey, ex + ew, ey + eh), radius=int(inner * 0.045), fill=(255, 255, 255, 255))
    lw = int(inner * 0.022)
    ed.line([(ex + lw, ey + lw * 1.5), (big // 2, ey + eh * 0.58), (ex + ew - lw, ey + lw * 1.5)],
            fill=(10, 84, 214, 255), width=lw, joint="curve")
    tile.alpha_composite(env)
    # étincelle (l'IA)
    sparkle(d, ex + ew - int(inner * 0.05), ey - int(inner * 0.01), int(inner * 0.15), (255, 214, 64, 255))
    sparkle(d, ex + ew + int(inner * 0.03), ey + int(inner * 0.13), int(inner * 0.06), (255, 255, 255, 255))
    return tile.resize((size, size), Image.LANCZOS)


def menubar_icon(px):
    big = px * 8
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w, h = int(big * 0.84), int(big * 0.58)
    x, y = int(big * 0.04), int(big * 0.26)
    lw = max(2, int(big * 0.085))
    d.rounded_rectangle((x, y, x + w, y + h), radius=int(big * 0.1), outline=(0, 0, 0, 255), width=lw)
    d.line([(x + lw, y + lw * 1.1), (x + w / 2, y + h * 0.58), (x + w - lw, y + lw * 1.1)], fill=(0, 0, 0, 255), width=lw, joint="curve")
    sparkle(d, int(big * 0.86), int(big * 0.2), int(big * 0.2), (0, 0, 0, 255))
    return img.resize((px, px), Image.LANCZOS)


def write_icns(img, path):
    chunks = []
    for typ, px in (("ic07", 128), ("ic08", 256), ("ic09", 512), ("ic10", 1024),
                    ("ic11", 32), ("ic12", 64), ("ic13", 256), ("ic14", 512)):
        buf = BytesIO()
        img.resize((px, px), Image.LANCZOS).save(buf, "PNG")
        chunks.append(typ.encode() + struct.pack(">I", len(buf.getvalue()) + 8) + buf.getvalue())
    body = b"".join(chunks)
    Path(path).write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    icon = app_icon(1024)
    icon.save(OUT / "icone.png")
    write_icns(icon, OUT / "icone.icns")
    menubar_icon(18).save(OUT / "barre_menus.png")
    menubar_icon(36).save(OUT / "barre_menus@2x.png")
    print("ok", sys.argv[0])
