#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="Gateway Dashboard"
APP_PATH="$HOME/Applications/$APP_NAME.app"
ICON_PATH="$ROOT/assets/GatewayDashboard.icns"
URL="${GATEWAY_DASHBOARD_URL:-http://127.0.0.1:8787}"

if [[ ! -f "$ICON_PATH" ]]; then
  "$ROOT/scripts/generate_icon.py" >/dev/null
fi

mkdir -p "$HOME/Applications"
rm -rf "$APP_PATH"

mkdir -p "$APP_PATH/Contents/MacOS" "$APP_PATH/Contents/Resources"

cat > "$APP_PATH/Contents/MacOS/gateway-dashboard-launcher" <<EOF
#!/bin/zsh
exec /usr/bin/open "$URL"
EOF
chmod +x "$APP_PATH/Contents/MacOS/gateway-dashboard-launcher"

cp "$ICON_PATH" "$APP_PATH/Contents/Resources/AppIcon.icns"

cat > "$APP_PATH/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>$APP_NAME</string>
  <key>CFBundleExecutable</key>
  <string>gateway-dashboard-launcher</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleIconName</key>
  <string>AppIcon</string>
  <key>CFBundleIdentifier</key>
  <string>com.georgek.gateway-dashboard</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>$APP_NAME</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>10.13</string>
  <key>LSUIElement</key>
  <false/>
</dict>
</plist>
EOF

touch "$APP_PATH"
echo "$APP_PATH"
