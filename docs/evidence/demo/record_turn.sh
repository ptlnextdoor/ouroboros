#!/bin/bash
# Record one live FORGE Studio turn beside Fusion. Hides every other app, tiles the two windows,
# starts a screen recording, types the mission into Studio, records until the turn finishes.
OUT=/Users/aayu/Workspace/developer/recursive-agents-hack/docs/evidence/demo/demo_live_turn.mov
GOAL="design a supersonic jet for fast medical delivery: carry 2 kg, break Mach 1 for 5 s, under 25 kg, Boom Prize rules"
SECS=${1:-165}

osascript <<EOF
tell application "System Events"
  set visible of (every process whose visible is true and name is not "FORGEStudio" and name is not "Autodesk Fusion") to false
  tell process "Autodesk Fusion"
    set frontmost to true
    set position of window 1 to {0, 38}
    set size of window 1 to {1000, 944}
  end tell
  tell process "FORGEStudio"
    set frontmost to true
    set position of window 1 to {1000, 38}
    set size of window 1 to {512, 944}
  end tell
end tell
EOF
sleep 1
screencapture -v -V "$SECS" -x "$OUT" &
REC=$!
sleep 3
osascript <<EOF
tell application "System Events" to tell process "FORGEStudio"
  set frontmost to true
  click (first button of window 1 whose description contains "New") 
end tell
EOF
sleep 1
osascript <<EOF
tell application "System Events" to tell process "FORGEStudio"
  set frontmost to true
  keystroke "$GOAL"
  delay 0.5
  key code 36
end tell
EOF
wait $REC
echo "recorded $OUT"
