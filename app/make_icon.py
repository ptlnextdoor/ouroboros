#!/usr/bin/env python3
"""Render the FORGE app icon.

Dark rounded-square tile with a green->blue gradient "F" glyph, matching the
UI palette (bg #07090d, accent #5cc8ff, ok #2fe08a). Emits a 1024px master PNG;
build.sh turns the .iconset into FORGE.icns via iconutil.
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ISET = os.path.join(HERE, "icon.iconset")
os.makedirs(ISET, exist_ok=True)

S = 1024
# macOS icons leave a margin; glyph tile is ~82% of canvas, centered.
MARGIN = int(S * 0.09)
TILE = S - 2 * MARGIN
RADIUS = int(TILE * 0.225)

ACC = (0x5c, 0xc8, 0xff)   # blue
OK = (0x2f, 0xe0, 0x8a)    # green


def rrect_mask(w, h, r):
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return m


def vgrad(w, h, top, bot):
    g = Image.new("RGB", (w, h))
    px = g.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    for x in range(1, w):
        for y in range(h):
            px[x, y] = px[0, y]
    return g


def diag_grad(w, h, c0, c1):
    g = Image.new("RGB", (w, h))
    px = g.load()
    for y in range(h):
        for x in range(w):
            t = (x + y) / max(1, (w + h - 2))
            px[x, y] = tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
    return g


def main():
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # dark tile background (subtle top->bottom panel gradient)
    tile = vgrad(TILE, TILE, (0x12, 0x1a, 0x26), (0x07, 0x09, 0x0d)).convert("RGBA")
    mask = rrect_mask(TILE, TILE, RADIUS)
    tile.putalpha(mask)

    # hairline inner border
    bd = ImageDraw.Draw(tile)
    bd.rounded_rectangle([2, 2, TILE - 3, TILE - 3], radius=RADIUS - 1,
                         outline=(0x2a, 0x3a, 0x52, 255), width=3)

    canvas.alpha_composite(tile, (MARGIN, MARGIN))

    # gradient glyph "F" drawn on its own layer, masked by the letter shape
    glyph = diag_grad(S, S, OK, ACC).convert("RGBA")
    letter = Image.new("L", (S, S), 0)
    ld = ImageDraw.Draw(letter)

    font = None
    for path in [
        "/System/Library/Fonts/SFNSRounded.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ]:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, int(TILE * 0.72))
                break
            except Exception:
                pass

    if font is not None:
        bbox = ld.textbbox((0, 0), "F", font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (S - tw) // 2 - bbox[0]
        y = (S - th) // 2 - bbox[1] - int(S * 0.01)
        ld.text((x, y), "F", font=font, fill=255)
    else:
        # fallback: draw a blocky F from rectangles
        bw = int(TILE * 0.16)
        x0 = MARGIN + int(TILE * 0.30)
        y0 = MARGIN + int(TILE * 0.18)
        y1 = MARGIN + TILE - int(TILE * 0.18)
        ld.rectangle([x0, y0, x0 + bw, y1], fill=255)
        ld.rectangle([x0, y0, x0 + int(TILE * 0.42), y0 + bw], fill=255)
        ld.rectangle([x0, (y0 + y1) // 2 - bw // 2, x0 + int(TILE * 0.34),
                      (y0 + y1) // 2 + bw // 2], fill=255)

    glyph.putalpha(letter)
    # clip the glyph to the tile so nothing spills past rounded corners
    tilemask_full = Image.new("L", (S, S), 0)
    tilemask_full.paste(mask, (MARGIN, MARGIN))
    gl = glyph.copy()
    ga = gl.getchannel("A")
    from PIL import ImageChops
    gl.putalpha(ImageChops.multiply(ga, tilemask_full))
    canvas.alpha_composite(gl)

    master = os.path.join(HERE, "icon_1024.png")
    canvas.save(master)

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for sz in sizes:
        im = canvas.resize((sz, sz), Image.LANCZOS)
        if sz <= 512:
            im.save(os.path.join(ISET, f"icon_{sz}x{sz}.png"))
        # retina @2x variants
        if sz in (16, 32, 128, 256, 512):
            im2 = canvas.resize((sz * 2, sz * 2), Image.LANCZOS)
            im2.save(os.path.join(ISET, f"icon_{sz}x{sz}@2x.png"))
    print("icon master + iconset written")


if __name__ == "__main__":
    main()
