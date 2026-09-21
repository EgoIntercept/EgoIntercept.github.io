#!/usr/bin/env bash
# Burn "Onboard Camera" / "External Camera" plates onto a side-by-side capture,
# optionally dropping a middle depth pane first.
#
#   ./tools/label-two-pane.sh <source> <output.mp4> [--drop-middle]
#
# Example — the emergent framing clip, whose source is fpv | depth | external:
#   ./tools/label-two-pane.sh "media/vids/emergent/F_catch2_fpv_depth_external (1).mp4" \
#       static/vids/emergent-framing-01.mp4 --drop-middle
#
# Panes are assumed 640x480 each: 1920 wide for three, 1280 for two.
#
# Labels sit on a translucent plate rather than being outlined, because these
# captures are lit rooms — white text on a white wall needs the plate. The
# simulation rollout does the opposite (tools/label-sim-rollout.sh): its panes
# are black sky, where a plate would dim the markers passing behind it.
#
# NOTE for zsh: the filtergraph must not end with an unbraced "$VAR[v]" —
# zsh reads [v] as an array subscript and silently swallows the output label,
# leaving ffmpeg to complain that label 'v' does not exist. Use "${VAR}[v]".
set -euo pipefail

[ $# -ge 2 ] || { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

SRC="$1"; OUT="$2"; MODE="${3:-}"
POSTER="static/img/posters/$(basename "${OUT%.mp4}").jpg"
[ -f "$SRC" ] || { echo "no such source: $SRC" >&2; exit 1; }

FONT="/System/Library/Fonts/Supplemental/Arial Bold.ttf"
PLATE="box=1:boxcolor=black@0.55:boxborderw=9:fontsize=22:fontcolor=white"

if [ "$MODE" = "--drop-middle" ]; then
  PRE="[0:v]crop=640:480:0:0[l];[0:v]crop=640:480:1280:0[r];[l][r]hstack=2[s]"
else
  PRE="[0:v]null[s]"
fi

GRAPH="$PRE;[s]drawtext=fontfile='$FONT':text='Onboard Camera':x=20:y=16:${PLATE},drawtext=fontfile='$FONT':text='External Camera':x=660:y=16:${PLATE}[v]"

mkdir -p "$(dirname "$OUT")" "$(dirname "$POSTER")"
ffmpeg -y -i "$SRC" -filter_complex "$GRAPH" -map "[v]" \
  -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -an \
  -movflags +faststart "$OUT"

DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0:nk=1 "$OUT")
PT=$(python3 -c "print(f'{$DUR*0.63:.3f}')")
ffmpeg -v error -y -ss "$PT" -i "$OUT" -frames:v 1 -q:v 3 "$POSTER"

echo "$OUT"
ffprobe -v error -show_entries stream=width,height,nb_frames \
  -show_entries format=duration -of default=nw=1 "$OUT" | sed 's/^/  /'
echo "  poster at ${PT}s -> $POSTER"
