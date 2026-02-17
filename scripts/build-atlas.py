"""
Build the final sprite atlas from a selected range of frames.

Usage:
  python build-atlas.py frames/ --start 120 --end 270 --count 49 --cols 7 --out atlas.jpg

Evenly samples --count frames between --start and --end.
"""

import argparse
import math
from pathlib import Path
from PIL import Image

def main():
    parser = argparse.ArgumentParser(description="Build sprite atlas from frame range")
    parser.add_argument("frames_dir", help="Directory containing extracted frame PNGs")
    parser.add_argument("--start", type=int, required=True, help="First frame index")
    parser.add_argument("--end", type=int, default=None, help="Last frame index (default: start + count)")
    parser.add_argument("--count", type=int, default=49, help="Number of frames to sample (default: 49)")
    parser.add_argument("--cols", type=int, default=7, help="Atlas columns (default: 7)")
    parser.add_argument("--size", default="256x256", help="Frame size WxH in px (default: 256x256)")
    parser.add_argument("--reverse", action="store_true", help="Reverse frame order (flip gaze direction)")
    parser.add_argument("--out", default="atlas.jpg", help="Output filename")
    args = parser.parse_args()

    fw, fh = [int(x) for x in args.size.split("x")]
    cols = args.cols
    rows = math.ceil(args.count / cols)

    frames = sorted(Path(args.frames_dir).glob("*.png"))
    end = args.end if args.end is not None else args.start + args.count

    # Evenly sample across the range
    range_size = end - args.start
    if range_size <= args.count:
        selected = frames[args.start:end]
    else:
        indices = [args.start + int(i * (range_size - 1) / (args.count - 1)) for i in range(args.count)]
        selected = [frames[i] for i in indices if i < len(frames)]

    if args.reverse:
        selected = list(reversed(selected))

    if len(selected) < args.count:
        print(f"warning: only {len(selected)} frames available")

    atlas = Image.new("RGB", (cols * fw, rows * fh), (0, 0, 0))

    for i, path in enumerate(selected):
        col = i % cols
        row = i // cols
        img = Image.open(path).resize((fw, fh), Image.LANCZOS)
        atlas.paste(img, (col * fw, row * fh))

    atlas.save(args.out, quality=92)
    step = f" (every {range_size // args.count} frames)" if range_size > args.count else ""
    print(f"atlas: {len(selected)} frames from {args.start}-{end}{step}, {cols}x{rows} grid, {fw}x{fh}px → {args.out}")

if __name__ == "__main__":
    main()
