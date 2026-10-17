#!/usr/bin/env bash
# Build "FORGE Studio.app" -- a native macOS WKWebView shell for the Studio demo.
# No Xcode project: swiftc compiles Sources/main.swift straight into the bundle.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
APP="$HERE/FORGE Studio.app"
PY="${PY:-/opt/miniconda3/bin/python3}"

echo "==> repo:   $REPO"
echo "==> python: $PY"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>FORGE Studio</string>
  <key>CFBundleDisplayName</key><string>FORGE Studio</string>
  <key>CFBundleIdentifier</key><string>dev.recursive.forge.studio</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>FORGEStudio</string>
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

echo "==> compiling main.swift"
swiftc -O \
  -framework Cocoa -framework WebKit \
  -o "$APP/Contents/MacOS/FORGEStudio" \
  "$HERE/Sources/main.swift"

echo "==> codesigning (ad-hoc)"
codesign --force --deep --sign - "$APP" 2>/dev/null || \
  echo "   (codesign skipped: $? -- app still runs locally)"

touch "$APP"
echo "==> built $APP"
echo "    run:  open '$APP'   (or '$APP/Contents/MacOS/FORGEStudio' for logs)"
