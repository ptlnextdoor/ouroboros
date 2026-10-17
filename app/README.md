# FORGE.app

Native macOS launcher for the FORGE demo. A Swift + WKWebView shell (no Xcode
project) that wraps the live agent-loop UI in a real app window with its own Dock
icon, a vibrant source-list sidebar, and an edge-to-edge web content pane.

This is a secondary launcher. The primary surface is the live UI served by
`ui/serve.py`; FORGE.app just hosts it in a native window and manages the server.

## What it does

- Window titled **FORGE**, dark appearance, 1600x1000 default (resizable, min 1120x720).
- `NSSplitViewController` with a `.sidebar` material source list:
  - **New part**: a goal field + Forge button. The text is matched to the closest
    `br` task and launched as `python -m forge.loop --task <id> --playbook playbook/v2.md --budget 1.0`,
    then the live loop is shown.
  - **Live loop**: `http://localhost:8008/`
  - **SQ-2 showcase**: `http://localhost:8008/ui/sq2/`
  - **Replay**: `http://localhost:8008/?replay=ui/fixture/br02&speed=8` (offline)
- Starts `ui/serve.py` on launch if port 8008 is free; stops it (and any running
  forge.loop job) on quit. If the port is already serving, it attaches instead of
  starting a second server, and leaves that server running on quit.

## Build

```sh
./app/build.sh
```

`swiftc` compiles `Sources/main.swift` straight into `FORGE.app/Contents/MacOS/FORGE`,
assembles the bundle and `Info.plist`, renders the icon (`make_icon.py` ->
`iconutil`), and ad-hoc codesigns. Override Python with `PY=/path/to/python3 ./app/build.sh`.
Force an icon rebuild with `REBUILD_ICON=1 ./app/build.sh`.

Requires: `swiftc` (ships with Xcode or the Command Line Tools), `iconutil`,
and a Python with Pillow for the icon (`/opt/miniconda3/bin/python3` by default).

## Run

```sh
open app/FORGE.app
# or, for logs in the terminal:
./app/FORGE.app/Contents/MacOS/FORGE
```

The repo root and Python path are baked into `Info.plist` at build time
(`FORGERepoRoot`, `FORGEPython`), with a fallback that walks up from the bundle
to find `ui/serve.py`.

## Files

- `Sources/main.swift` - the whole app (shell, sidebar, process manager).
- `build.sh` - build + bundle + sign.
- `make_icon.py` - renders `FORGE.icns` from the UI palette.
- `shots/` - verification screenshots at 1600x1000 and 1440x900.

Build intermediates (`FORGE.app/`, `FORGE.icns`, `icon.iconset/`, `icon_1024.png`)
are gitignored; `build.sh` regenerates them.
