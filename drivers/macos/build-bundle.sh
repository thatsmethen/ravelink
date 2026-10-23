#!/bin/sh
# Build a local bundle only. This script never installs or restarts audio services.
set -eu
driver_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$driver_dir/../.." && pwd)
target=${RAVELINK_HAL_TARGET:-$(rustc -vV | sed -n 's/^host: //p')}
case "$target" in aarch64-apple-darwin|x86_64-apple-darwin) ;; *) echo "A macOS Rust target is required" >&2; exit 1 ;; esac
output=${RAVELINK_HAL_OUTPUT:-"$repo_dir/dist/macos/RaveLink.driver"}
build_root=${CARGO_TARGET_DIR:-"$repo_dir/target"}
cd "$repo_dir"
cargo build -p ravelink-hal --release --target "$target"
mkdir -p "$output/Contents/MacOS" "$output/Contents/Resources"
cp "$build_root/$target/release/libravelink_hal.dylib" "$output/Contents/MacOS/RaveLinkHAL"
cp "$driver_dir/Info.plist" "$output/Contents/Info.plist"
/usr/bin/install_name_tool -id '@rpath/RaveLinkHAL' "$output/Contents/MacOS/RaveLinkHAL"
/usr/bin/plutil -lint "$output/Contents/Info.plist"
# Local ad-hoc signing by default; release signing must supply an authorized identity.
/usr/bin/codesign --force --sign "${RAVELINK_SIGN_IDENTITY:--}" "$output"
/usr/bin/codesign --verify --strict "$output"
printf '%s\n' "$output"
