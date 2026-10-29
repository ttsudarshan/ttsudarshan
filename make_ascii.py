#!/usr/bin/env python3
"""
Turn a photo into ascii.txt for the card.

    pip install pillow
    python make_ascii.py me.jpg                # 104 columns wide (default)
    python make_ascii.py me.jpg --width 120    # wider / more detail
    python make_ascii.py me.jpg --invert       # flip light/dark (try both)
    python make_ascii.py me.jpg --contrast 1.6 # punchier
    python make_ascii.py me.jpg --equalize     # pull out more mid-tone detail
    python make_ascii.py me.png --invert -o ascii_dark.txt   # art for dark mode

Tips: a tightly cropped head-and-shoulders shot on a plain background works best.
A PNG with the background removed (transparent) is ideal: transparent pixels
always become blank, so the background stays empty with or without --invert.
You can hand-edit ascii.txt afterwards to clean up stray characters.
"""
import argparse
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

# light -> dense (dense chars draw as "ink")
RAMP = " .'`,:;-~+=*|lL$&%gM@"
CHAR_ASPECT = 2.05  # line height / char width of the art in the SVG (7.5px / ~3.6px)


def convert(path, width, invert, contrast, equalize=False):
    img = ImageOps.exif_transpose(Image.open(path))
    # transparent pixels (e.g. a background-removed PNG) always become spaces,
    # and only the visible subject is used to stretch the contrast
    mask = img.getchannel("A").point(lambda a: 255 if a >= 128 else 0) if "A" in img.getbands() else None
    img = img.convert("L")
    if equalize:
        img = ImageOps.equalize(img, mask=mask)
    else:
        img = ImageOps.autocontrast(img, cutoff=1, mask=mask)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    img = img.filter(ImageFilter.SHARPEN)
    rows = max(1, round(img.height / img.width * width / CHAR_ASPECT))
    img = img.resize((width, rows), Image.LANCZOS)
    px = img.load()
    alpha = mask.resize((width, rows), Image.LANCZOS).load() if mask else None
    out = []
    for y in range(rows):
        line = ""
        for x in range(width):
            if alpha and alpha[x, y] < 128:
                line += " "
                continue
            v = px[x, y] / 255
            if not invert:
                v = 1 - v            # dark pixel -> dense char
            line += RAMP[min(len(RAMP) - 1, int(v * len(RAMP)))]
        out.append(line.rstrip())
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--width", type=int, default=104)
    ap.add_argument("--invert", action="store_true")
    ap.add_argument("--contrast", type=float, default=1.3)
    ap.add_argument("--equalize", action="store_true", help="spread tones evenly (more face detail)")
    ap.add_argument("-o", "--out", default=str(Path(__file__).with_name("ascii.txt")))
    a = ap.parse_args()
    art = convert(a.image, a.width, a.invert, a.contrast, a.equalize)
    Path(a.out).write_text(art)
    print(art)
    print(f"-> {a.out} ({len(art.splitlines())} rows). Run `python card.py --demo` to preview.")
