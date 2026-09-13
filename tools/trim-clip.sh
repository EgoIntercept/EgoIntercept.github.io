#!/usr/bin/env bash
# Trim a clip to a new start/end and refresh its poster.
#
#   ./tools/trim-clip.sh <source> <start> <end> <output.mp4> [poster-time]
#
# Example — keep 1.0s to 3.5s of the first onboard capture:
#   ./tools/trim-clip.sh media/vids/onboard/onboard_view1.mp4 1.0 3.5 \
#       static/vids/onboard-view-01.mp4
#
# Always cut from the archived ORIGINAL under media/, never from the copy in
# static/ — re-trimming an already-trimmed clip stacks generation loss, and
# once you have overwritten the served file the original extent is gone.
#
# start/end are seconds on the SOURCE timeline (both -ss and -to sit before
# -i, so neither is relative to the other). Fractions are fine: 1.4, 0:02.75.
#
# This re-encodes rather than stream-copying. The onboard captures carry a
# single keyframe at t=0 and sim_rollout only four, so -c copy could not cut
# anywhere but those points — it would silently snap your cut backwards or
# open on a frozen frame. crf 18 is visually lossless at this size.
#
# The poster is regenerated at the midpoint of the new clip unless you pass a
# time (relative to the TRIMMED clip). A stale poster is the usual way a trim
# goes wrong: the old one is often grabbed from a moment you just cut away.
set -euo pipefail

[ $# -ge 4 ] || { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

SRC="$1"; START="$2"; END="$3"; OUT="$4"
POSTER="static/img/posters/$(basename "${OUT%.mp4}").jpg"

[ -f "$SRC" ] || { echo "no such source: $SRC" >&2; exit 1; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

ffmpeg -v error -y -ss "$START" -to "$END" -i "$SRC" \
  -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
  -an -movflags +faststart "$TMP/out.mp4"

DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0:nk=1 "$TMP/out.mp4")
[ "${DUR%%.*}" -ge 0 ] 2>/dev/null || { echo "trim produced nothing — check start/end" >&2; exit 1; }

PT="${5:-$(python3 -c "print(f'{$DUR/2:.3f}')")}"
ffmpeg -v error -y -ss "$PT" -i "$TMP/out.mp4" -frames:v 1 -q:v 3 "$TMP/poster.jpg"

mkdir -p "$(dirname "$OUT")" "$(dirname "$POSTER")"
mv "$TMP/out.mp4" "$OUT"; mv "$TMP/poster.jpg" "$POSTER"

echo "$OUT"
ffprobe -v error -show_entries format=duration -show_entries stream=width,height,nb_frames \
  -of default=nw=1 "$OUT" | sed 's/^/  /'
echo "  poster at ${PT}s -> $POSTER"
