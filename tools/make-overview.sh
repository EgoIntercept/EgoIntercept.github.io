#!/usr/bin/env bash
# Build the headline overview video from the raw supplementary capture.
#
#   ./tools/make-overview.sh IcraSupplement.mov
#
# The raw .mov is ~200 MB and is not committed (see .gitignore). This script
# plays it back at 2x, re-encodes to H.264/AAC so browsers can stream it, and
# writes the poster frame the page shows before playback.
#
# Source is 30 fps, so 2x lands on 60 fps and every original frame is kept.
set -euo pipefail

SRC="${1:-IcraSupplement.mov}"
OUT="static/vids/overview-2x.mp4"
POSTER="static/img/posters/overview-2x.jpg"

ffmpeg -y -i "$SRC" \
  -filter_complex "[0:v]setpts=0.5*PTS,fps=60[v];[0:a]atempo=2.0[a]" \
  -map "[v]" -map "[a]" \
  -c:v libx264 -preset medium -crf 23 -profile:v high -level 4.2 -pix_fmt yuv420p \
  -maxrate 6M -bufsize 12M \
  -c:a aac -b:a 128k -ac 2 \
  -movflags +faststart \
  "$OUT"

# Poster: the title card, one second in.
ffmpeg -y -ss 1 -i "$OUT" -frames:v 1 -q:v 3 "$POSTER"

ls -lh "$OUT" "$POSTER"
