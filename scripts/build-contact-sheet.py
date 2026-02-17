"""
Build a numbered contact sheet from extracted frames.
Use this to visually pick the usable range before building the final atlas.

Usage: python build-contact-sheet.py frames/ --cols 10 --out contact-sheet.jpg
"""

import argparse
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def main():
    parser = argparse.ArgumentParser(description="Build numbered contact sheet from frames")
    parser.add_argument("frames_dir", help="Directory containing extracted frame PNGs")
    parser.add_argument("--cols", type=int, default=10, help="Columns in contact sheet (default: 10)")
    parser.add_argument("--thumb", type=int, default=128, help="Thumbnail size in px (default: 128)")
    parser.add_argument("--out", default="contact-sheet.jpg", help="Output filename")
    args = parser.parse_args()

    frames = sorted(Path(args.frames_dir).glob("*.png"))
    if not frames:
        print(f"no PNGs found in {args.frames_dir}/")
        return

    cols = args.cols
    rows = math.ceil(len(frames) / cols)
    tw = args.thumb
    th = args.thumb

    sheet = Image.new("RGB", (cols * tw, rows * th), (0, 0, 0))
    draw = ImageDraw.Draw(sheet)

    for i, path in enumerate(frames):
        col = i % cols
        row = i // cols
        img = Image.open(path).resize((tw, th), Image.LANCZOS)
        sheet.paste(img, (col * tw, row * th))
        draw.text((col * tw + 4, row * th + 2), str(i), fill=(255, 255, 0))

    sheet.save(args.out, quality=90)
    print(f"contact sheet: {len(frames)} frames, {cols}x{rows} grid → {args.out}")

if __name__ == "__main__":
    main()
