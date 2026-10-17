#!/bin/bash
# Stage setup for the LIVE demo. Run once, ~30 s before you present:
#   bash studio/stage.sh
# It restarts FORGE Studio (one server), tiles Fusion (left) + Studio (right), frames MJ-1,
# and leaves the composer empty and ready. Then on stage: click the jet chip, press Enter.
# Optional: `bash studio/stage.sh orbit` also orbits the live Fusion camera for 120 s.
R=/Users/aayu/Workspace/developer/recursive-agents-hack
PY=/opt/miniconda3/bin/python3
cd "$R"

pkill -f "FORGE Studio.app/Contents/MacOS/FORGEStudio" 2>/dev/null
pkill -f "studio/server.py" 2>/dev/null
pkill -f "studio/director.py" 2>/dev/null
sleep 2
"$R/studio/FORGE Studio.app/Contents/MacOS/FORGEStudio" >/tmp/studio_app.log 2>&1 &
sleep 5
P=$(pgrep -n FORGEStudio)

osascript <<EOF
tell application "System Events"
  set visible of (every process whose visible is true and name is not "Fusion" and unix id is not $P) to false
  tell process "Fusion"
    set frontmost to true
    set position of (first window whose name contains "MJ1") to {0, 33}
  end tell
  tell (first process whose unix id is $P)
    set frontmost to true
    set position of window 1 to {990, 33}
    set size of window 1 to {522, 949}
  end tell
end tell
EOF

$PY - <<'EOF'
import sys; sys.path.insert(0, ".")
from studio import fusion
fusion._exec('''import json, adsk.core, adsk.fusion
app = adsk.core.Application.get()
for i in range(app.documents.count):
    d = app.documents.item(i)
    if d.name.startswith("MJ1"): d.activate(); break
for pid in ("Browser",):
    p = app.userInterface.palettes.itemById(pid)
    if p: p.isVisible = False
vp = app.activeViewport
cam = vp.camera; cam.isSmoothTransition = False
cam.viewOrientation = adsk.core.ViewOrientations.IsoTopRightViewOrientation
vp.camera = cam; vp.fit()
json.dumps({})''', 40.0)
print("stage ready: Fusion MJ-1 left, FORGE Studio right. Click the jet chip, press Enter.")
EOF

if [ "${1:-}" = "orbit" ]; then
  $PY studio/director.py 120 >/tmp/director.log 2>&1 &
  echo "orbiting Fusion camera for 120 s"
fi
