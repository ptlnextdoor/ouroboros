#!/bin/bash
# One-shot demo take. Hides every app except Fusion + FORGE Studio, frames the jet, starts the
# screen recording, starts a REAL turn in Studio (its own JS sends the mission), and drives the
# live Fusion camera (orbit, skin on/off) during the turn. Then stops and writes the .mov.
set -u
R=/Users/aayu/Workspace/developer/recursive-agents-hack
OUT=$R/docs/evidence/demo/demo_take.mov
SECS=${1:-150}
PY=/opt/miniconda3/bin/python3

osascript <<'EOF'
tell application "System Events"
  set visible of (every process whose visible is true and name is not "FORGE Studio" and name is not "Fusion") to false
  tell process "Fusion"
    set frontmost to true
    set position of (first window whose name contains "MJ1") to {0, 33}
    set size of (first window whose name contains "MJ1") to {990, 949}
  end tell
  tell process "FORGE Studio"
    set frontmost to true
    set position of window 1 to {990, 33}
    set size of window 1 to {522, 949}
  end tell
end tell
EOF

cd "$R"
$PY - <<'EOF'
import sys; sys.path.insert(0, ".")
from studio import fusion
fusion._exec('''import json, adsk.core
app = adsk.core.Application.get()
for pid in ("Browser", "AnimationTimeline"):
    p = app.userInterface.palettes.itemById(pid)
    if p: p.isVisible = False
for i in range(app.documents.count):
    d = app.documents.item(i)
    if d.name.startswith("MJ1"): d.activate(); break
vp = app.activeViewport
cam = vp.camera
cam.isSmoothTransition = False
cam.viewOrientation = adsk.core.ViewOrientations.IsoTopRightViewOrientation
vp.camera = cam
vp.fit()
json.dumps({"ok": True})''', 40.0)
EOF

screencapture -v -V "$SECS" -x "$OUT" &
REC=$!
sleep 2
# start the real turn from inside Studio: reload with ?auto=<goal>, its JS calls go()
osascript <<'EOF'
tell application "System Events" to tell process "FORGE Studio" to set frontmost to true
EOF
curl -s -X POST "http://127.0.0.1:8010/auto" >/dev/null 2>&1 || true
$PY "$R/studio/director.py" $((SECS - 10)) >/tmp/director.log 2>&1 &
wait $REC
echo "wrote $OUT"
