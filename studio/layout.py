"""Tile the two demo windows: Fusion 360 on the left, FORGE Studio on the right.

Uses System Events AppleScript so it works on whatever is on screen without
any accessibility plumbing of our own. The Studio window is the frontmost
window of the FORGE Studio app (the Swift shell) if present, else we only move
Fusion and report that.
"""
import subprocess

# Fusion on the left ~70 %, Studio on the right ~30 % of the main screen.
_SCRIPT = r'''
set leftFrac to 0.70
tell application "Finder" to set b to bounds of window of desktop
set screenW to item 3 of b
set screenH to item 4 of b
set menuBar to 25
set splitX to round (screenW * leftFrac)

set moved to {}

tell application "System Events"
    -- Fusion 360 left
    set fusionProc to ""
    repeat with p in (every process whose background only is false)
        if name of p contains "Fusion" then set fusionProc to name of p
    end repeat
    if fusionProc is not "" then
        tell process fusionProc
            if (count of windows) > 0 then
                set position of window 1 to {0, menuBar}
                set size of window 1 to {splitX, screenH - menuBar}
                set end of moved to "Fusion"
            end if
        end tell
    end if

    -- FORGE Studio right
    repeat with p in (every process whose background only is false)
        set pn to name of p
        if pn contains "FORGE Studio" or pn is "FORGE Studio" then
            tell process pn
                if (count of windows) > 0 then
                    set position of window 1 to {splitX, menuBar}
                    set size of window 1 to {screenW - splitX, screenH - menuBar}
                    set end of moved to "Studio"
                end if
            end tell
        end if
    end repeat
end tell

return moved as string
'''


def tile():
    """Run the tile AppleScript. Returns a short status string."""
    r = subprocess.run(["osascript", "-e", _SCRIPT], capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "osascript failed").strip()[:300])
    moved = (r.stdout or "").strip()
    return f"tiled: {moved or 'nothing found to move'}"


if __name__ == "__main__":
    print(tile())
