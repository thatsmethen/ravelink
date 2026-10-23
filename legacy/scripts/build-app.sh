#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
configuration="${CONFIGURATION:-release}"
mkdir -p "$PWD/build"
staging_dir="$(mktemp -d "$PWD/build/.ravelink-app.XXXXXX")"
trap 'rm -rf "$staging_dir"' EXIT
case "${APP_ARCHITECTURES:-native}" in
  native) architectures=("$(uname -m)") ;;
  arm64|x86_64) architectures=("$APP_ARCHITECTURES") ;;
  universal) architectures=(arm64 x86_64) ;;
  *) echo 'APP_ARCHITECTURES must be native, arm64, x86_64, or universal.' >&2; exit 2 ;;
esac
python3 scripts/app-build-info.py --root "$PWD" prepare \
  --version "${APP_VERSION:-}" --build-number "${APP_BUILD_NUMBER:-}" \
  --configuration "$configuration" --architectures "${architectures[@]}" \
  --record "$staging_dir/build-info.json"
binary_dirs=()
for architecture in "${architectures[@]}"; do
  build_args=(-c "$configuration")
  # Preserve the ordinary development cache for native builds. Explicit slices
  # have independent caches so packaging does not replace test executables.
  if [[ "${APP_ARCHITECTURES:-native}" != native ]]; then
    build_args+=(--arch "$architecture" --scratch-path "$PWD/build/swift-$architecture")
  fi
  swift build "${build_args[@]}" --product RaveLink
  swift build "${build_args[@]}" --product RaveLinkEngine
  swift build "${build_args[@]}" --product RaveLinkPluginHost
  binary_dirs+=("$(swift build "${build_args[@]}" --show-bin-path)")
done
app_dir="$staging_dir/RaveLink.app"
mkdir -p "$app_dir/Contents/MacOS" "$app_dir/Contents/Resources" "$app_dir/Contents/Helpers"
for product in RaveLink RaveLinkEngine RaveLinkPluginHost; do
  product_dir="$app_dir/Contents/MacOS"
  if [[ "$product" == RaveLinkPluginHost ]]; then product_dir="$app_dir/Contents/Helpers"; fi
  inputs=()
  for binary_dir in "${binary_dirs[@]}"; do inputs+=("$binary_dir/$product"); done
  if [[ ${#inputs[@]} -eq 1 ]]; then cp "${inputs[0]}" "$product_dir/$product"
  else lipo -create "${inputs[@]}" -output "$product_dir/$product"; fi
  lipo "$product_dir/$product" -verify_arch "${architectures[@]}"
done
swift scripts/make-icon.swift build/AppIcon.iconset
iconutil -c icns build/AppIcon.iconset -o "$app_dir/Contents/Resources/AppIcon.icns"
cp Resources/Info.plist "$app_dir/Contents/Info.plist"
cp LICENSE "$app_dir/Contents/Resources/LICENSE"
python3 scripts/app-build-info.py --root "$PWD" finish \
  --record "$staging_dir/build-info.json" --app "$app_dir"
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
