#!/usr/bin/env bash
# Compile against extracted, original Microsoft SDK/WDK declarations only.
set -euo pipefail
repo="$(cd "$(dirname "$0")/../../.." && pwd)"
: "${RAVELINK_WDK_ROOT:?Point to the extracted Microsoft.Windows.WDK.x64 package}"
: "${RAVELINK_SDK_ROOT:?Point to the extracted Microsoft.Windows.SDK.CPP package}"
clang_bin="${CXX:-clang++}"
version=10.0.26100.0
"$clang_bin" --target=x86_64-pc-windows-msvc -fsyntax-only -fms-extensions \
  -fms-compatibility -std=c++17 -D_AMD64_=1 -D_WIN64 \
  -D_WIN32_WINNT=0x0a00 -DNTDDI_VERSION=0x0A00000C \
  -isystem "$RAVELINK_WDK_ROOT/c/Include/$version/km" \
  -isystem "$RAVELINK_WDK_ROOT/c/Include/$version/km/crt" \
  -isystem "$RAVELINK_SDK_ROOT/c/Include/$version/shared" \
  -isystem "$RAVELINK_SDK_ROOT/c/Include/$version/ucrt" \
  "$repo/drivers/windows/tests/abi-check.cpp"
