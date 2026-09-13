#!/usr/bin/env bash
# Burn pane labels and the marker legend into a simulation rollout render.
#
#   ./tools/label-sim-rollout.sh sim_rollout.mp4 sim-rollout-01
#
# The raw render is a 1280x480 side-by-side: onboard camera left, external
# camera right. Both panes show a black sky across the top, which is where
# the text goes. Text is outlined rather than boxed — a translucent box
# dims the markers whenever one passes behind it.
#
# Marker colors, matched to the renderer:
#   green   observed ball position
#   magenta predicted ball position
#   the ball itself is ground truth
set -euo pipefail

SRC="${1:-sim_rollout.mp4}"
NAME="${2:-sim-rollout-01}"
OUT="static/vids/sim/$NAME.mp4"
POSTER="static/img/posters/$NAME.jpg"

B="/System/Library/Fonts/Supplemental/Arial Bold.ttf"
R="/System/Library/Fonts/Supplemental/Arial.ttf"
S="borderw=2:bordercolor=black@0.85"

VF="drawtext=fontfile='$B':text='Onboard Camera':x=20:y=14:fontsize=22:fontcolor=white:$S,\
drawtext=fontfile='$B':text='External Camera':x=660:y=14:fontsize=22:fontcolor=white:$S,\
drawtext=fontfile='$R':text='Observed position':x=20:y=52:fontsize=16:fontcolor=0x33FF33:$S,\
drawtext=fontfile='$R':text='Predicted position':x=20:y=74:fontsize=16:fontcolor=0xFF66FF:$S,\
drawtext=fontfile='$R':text='Ground truth (the ball)':x=20:y=96:fontsize=16:fontcolor=white:$S"

mkdir -p static/vids/sim
ffmpeg -y -i "$SRC" -vf "$VF" \
  -c:v libx264 -preset slow -crf 20 -profile:v high -pix_fmt yuv420p \
  -an -movflags +faststart "$OUT"

ffmpeg -y -ss 9 -i "$OUT" -frames:v 1 -q:v 3 "$POSTER"

ls -lh "$OUT" "$POSTER"
