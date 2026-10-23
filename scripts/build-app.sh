#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
configuration="${CONFIGURATION:-release}"
swift build -c "$configuration" --product RaveLink
swift build -c "$configuration" --product RaveLinkPluginHost
binary_dir="$(swift build -c "$configuration" --show-bin-path)"
app_dir="$PWD/build/RaveLink.app"
mkdir -p "$app_dir/Contents/MacOS" "$app_dir/Contents/Resources" "$app_dir/Contents/Helpers"
cp "$binary_dir/RaveLink" "$app_dir/Contents/MacOS/RaveLink"
cp "$binary_dir/RaveLinkPluginHost" "$app_dir/Contents/Helpers/RaveLinkPluginHost"
swift scripts/make-icon.swift build/AppIcon.iconset
iconutil -c icns build/AppIcon.iconset -o "$app_dir/Contents/Resources/AppIcon.icns"
cp Resources/Info.plist "$app_dir/Contents/Info.plist"
cp LICENSE "$app_dir/Contents/Resources/LICENSE"
if [[ -n "${SIGNING_IDENTITY:-}" ]]; then
  codesign --force --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$app_dir/Contents/Helpers/RaveLinkPluginHost"
  codesign --force --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$app_dir"
else
  codesign --force --sign - "$app_dir/Contents/Helpers/RaveLinkPluginHost"
  codesign --force --sign - "$app_dir"
fi
codesign --verify --deep --strict "$app_dir"
echo "$app_dir"
