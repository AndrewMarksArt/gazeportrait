#!/usr/bin/env bash
# Extract all frames from a video file.
# Usage: ./extract-frames.sh input.mp4 [output_dir]

set -euo pipefail

INPUT="${1:?Usage: extract-frames.sh <video> [output_dir]}"
OUTDIR="${2:-frames}"

mkdir -p "$OUTDIR"
ffmpeg -i "$INPUT" -vf fps=30 "$OUTDIR/%04d.png"

COUNT=$(ls -1 "$OUTDIR"/*.png 2>/dev/null | wc -l | tr -d ' ')
echo "extracted $COUNT frames to $OUTDIR/"
