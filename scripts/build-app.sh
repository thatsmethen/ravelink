#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
configuration="${CONFIGURATION:-release}"
swift build -c "$configuration" --product RaveLink
swift build -c "$configuration" --product RaveLinkEngine
swift build -c "$configuration" --product RaveLinkPluginHost
binary_dir="$(swift build -c "$configuration" --show-bin-path)"
mkdir -p "$PWD/build"
staging_dir="$(mktemp -d "$PWD/build/.ravelink-app.XXXXXX")"
trap 'rm -rf "$staging_dir"' EXIT
app_dir="$staging_dir/RaveLink.app"
mkdir -p "$app_dir/Contents/MacOS" "$app_dir/Contents/Resources" "$app_dir/Contents/Helpers"
cp "$binary_dir/RaveLink" "$app_dir/Contents/MacOS/RaveLink"
cp "$binary_dir/RaveLinkEngine" "$app_dir/Contents/MacOS/RaveLinkEngine"
cp "$binary_dir/RaveLinkPluginHost" "$app_dir/Contents/Helpers/RaveLinkPluginHost"
swift scripts/make-icon.swift build/AppIcon.iconset
iconutil -c icns build/AppIcon.iconset -o "$app_dir/Contents/Resources/AppIcon.icns"
cp Resources/Info.plist "$app_dir/Contents/Info.plist"
cp LICENSE "$app_dir/Contents/Resources/LICENSE"
signing_flags=(--force --options runtime --sign "${SIGNING_IDENTITY:--}")
if [[ -n "${SIGNING_IDENTITY:-}" ]]; then signing_flags+=(--timestamp); fi
codesign "${signing_flags[@]}" --entitlements Resources/Engine.entitlements "$app_dir/Contents/MacOS/RaveLinkEngine"
codesign "${signing_flags[@]}" --entitlements Resources/PluginHost.entitlements "$app_dir/Contents/Helpers/RaveLinkPluginHost"
codesign "${signing_flags[@]}" --entitlements Resources/App.entitlements "$app_dir"
codesign --verify --deep --strict "$app_dir"
# Publish the verified bundle by renaming, without truncating executables that
# a running development app may still have mapped.
destination="$PWD/build/RaveLink.app"
if [[ -e "$destination" ]]; then mv "$destination" "$staging_dir/previous.app"; fi
if ! mv "$app_dir" "$destination"; then
  if [[ -e "$staging_dir/previous.app" ]]; then mv "$staging_dir/previous.app" "$destination"; fi
  exit 1
fi
echo "$destination"
