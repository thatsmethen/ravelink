#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."
developer_dir="$(xcode-select -p)"
testing_frameworks="$developer_dir/Library/Developer/Frameworks"
args=(--disable-xctest)

# Some standalone Command Line Tools releases do not add their own Testing
# framework to SwiftPM's search paths. Full Xcode resolves it normally.
if [[ -d "$testing_frameworks/Testing.framework" ]]; then
  args+=(-Xswiftc -F -Xswiftc "$testing_frameworks")
  args+=(-Xlinker -F -Xlinker "$testing_frameworks")
  args+=(-Xlinker -rpath -Xlinker "$testing_frameworks")
  # This CLT distribution ships the Foundation overlay binary without its
  # Swift module. Disable automatic overlays for this test build only.
  if [[ ! -d "$testing_frameworks/_Testing_Foundation.framework/Modules" ]]; then
    args+=(-Xswiftc -Xfrontend -Xswiftc -disable-cross-import-overlays)
  fi
fi

exec swift test "${args[@]}" "$@"
