-- Fusion left half, FORGE Studio right half (demo layout)
tell application "Finder" to set b to bounds of window of desktop
set W to item 3 of b
set H to item 4 of b
set half to round (W / 2)
tell application "System Events"
  tell process "Autodesk Fusion"
    set n to count of windows
    repeat with i from 1 to n
      if name of window i contains "Autodesk Fusion" then
        set position of window i to {0, 25}
        set size of window i to {half, H - 25}
      end if
    end repeat
  end tell
  repeat with p in (every process whose name contains "FORGE")
    tell p
      if (count of windows) > 0 then
        set position of window 1 to {half, 25}
        set size of window 1 to {W - half, H - 25}
      end if
    end tell
  end repeat
end tell
