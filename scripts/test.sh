#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."
developer_dir="$(xcode-select -p)"
testing_frameworks="$developer_dir/Library/Developer/Frameworks"
args=(--disable-xctest)

# Keep ordinary local tests on SwiftPM's debug default. CI can select one
# configuration for compilation and every later --skip-build acceptance run.
if [[ -n "${RAVELINK_TEST_CONFIGURATION:-}" ]]; then
  case "$RAVELINK_TEST_CONFIGURATION" in
    debug|release) args+=(--configuration "$RAVELINK_TEST_CONFIGURATION") ;;
    *) echo 'RAVELINK_TEST_CONFIGURATION must be debug or release.' >&2; exit 2 ;;
  esac
fi

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
