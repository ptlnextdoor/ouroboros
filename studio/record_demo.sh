#!/usr/bin/env bash
# Record the autonomous SQ-2 demo: Fusion left, FORGE right, agent builds then reshapes SQ-2.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-/tmp/forge_demo_raw.mov}"
SECS="${2:-48}"
pkill -x FORGEStudio; sleep 1
FORGE_QUERY="${FORGE_QUERY:-?auto=1&build=1}" nohup "$HERE/FORGE Studio.app/Contents/MacOS/FORGEStudio" >/tmp/forgeapp.log 2>&1 &
sleep 2
osascript "$HERE/tile_sq2.applescript"
osascript -e 'tell application "System Events" to tell process "Autodesk Fusion" to set position of (first window whose name contains "Autodesk Fusion") to {-250, 25}'
rm -f "$OUT"
ffmpeg -hide_banner -loglevel error -f avfoundation -capture_cursor 0 -framerate 30 -pixel_format uyvy422 -i "2:none" \
  -t "$SECS" -vf "scale=1920:-2" -c:v h264_videotoolbox -b:v 16M "$OUT" </dev/null
echo "$OUT"
