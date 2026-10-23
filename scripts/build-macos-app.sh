#!/bin/sh
set -eu
root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root_dir"
profile=${RAVELINK_BUILD_PROFILE:-release}
case "$profile" in
    release) cargo build --locked -p ravelink-app --release ;;
    debug) cargo build --locked -p ravelink-app ;;
    *) echo 'RAVELINK_BUILD_PROFILE must be release or debug' >&2; exit 1 ;;
esac
bundle="$root_dir/dist/macos/RaveLink Rust.app"
mkdir -p "$bundle/Contents/MacOS" "$bundle/Contents/Resources"
cp "${CARGO_TARGET_DIR:-target}/$profile/ravelink-app" "$bundle/Contents/MacOS/"
cp packaging/macos/Info.plist "$bundle/Contents/Info.plist"
cp LICENSE "$bundle/Contents/Resources/RaveLink-LICENSE.txt"
cp THIRD-PARTY-NOTICES.txt "$bundle/Contents/Resources/"
mkdir -p "$bundle/Contents/Resources/Rust-runtime-notices"
cp docs/third-party-licenses/rust-1.91.1/* "$bundle/Contents/Resources/Rust-runtime-notices/"
codesign --force --sign "${RAVELINK_SIGN_IDENTITY:--}" "$bundle"
codesign --verify --strict "$bundle"
printf '%s\n' "$bundle"
