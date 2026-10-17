#!/usr/bin/env bash
# Build app/FORGE.app -- a native macOS WKWebView shell for the FORGE demo.
# No Xcode project: swiftc compiles Sources/main.swift straight into the bundle.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
APP="$HERE/FORGE.app"
PY="${PY:-/opt/miniconda3/bin/python3}"

echo "==> repo:   $REPO"
echo "==> python: $PY"

# 1. icon (idempotent; regenerates iconset + icns)
if [ ! -f "$HERE/FORGE.icns" ] || [ "${REBUILD_ICON:-0}" = "1" ]; then
  echo "==> rendering icon"
  "$PY" "$HERE/make_icon.py"
  iconutil -c icns "$HERE/icon.iconset" -o "$HERE/FORGE.icns"
fi

# 2. bundle skeleton
echo "==> assembling bundle"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# 3. Info.plist (dark window, regular app, no bundled nib)
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>FORGE</string>
  <key>CFBundleDisplayName</key><string>FORGE</string>
  <key>CFBundleIdentifier</key><string>dev.recursive.forge</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>FORGE</string>
  <key>CFBundleIconFile</key><string>FORGE</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSPrincipalClass</key><string>NSApplication</string>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <key>FORGERepoRoot</key><string>$REPO</string>
  <key>FORGEPython</key><string>$PY</string>
</dict>
</plist>
PLIST

# 4. icon into Resources
cp "$HERE/FORGE.icns" "$APP/Contents/Resources/FORGE.icns"

# 5. compile
echo "==> compiling main.swift"
swiftc -O \
  -framework Cocoa -framework WebKit \
  -o "$APP/Contents/MacOS/FORGE" \
  "$HERE/Sources/main.swift"

# 6. ad-hoc codesign so WKWebView + networking behave
echo "==> codesigning (ad-hoc)"
codesign --force --deep --sign - "$APP" 2>/dev/null || \
  echo "   (codesign skipped: $? -- app still runs locally)"

# refresh Finder/Dock icon cache for this bundle
touch "$APP"

echo "==> built $APP"
echo "    run:  open '$APP'   (or ./app/FORGE.app/Contents/MacOS/FORGE for logs)"
