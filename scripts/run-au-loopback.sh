#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${RAVELINK_TEST_INSTALLED_AU:-}" != 1 ]]; then
  echo 'Set RAVELINK_TEST_INSTALLED_AU=1 only on a host prepared for installed virtual-device acceptance.' >&2
  exit 2
fi
au_dir="${RAVELINK_AU_OUTPUT:-$PWD/build}"
mkdir -p "$au_dir"
rm -f "$au_dir/au-ready" "$au_dir/au-loopback.wav" "$au_dir/au-engine.json" "$au_dir/au-analysis.json"
receiver=''
cleanup() {
  if [[ -n "$receiver" ]]; then
    kill "$receiver" 2>/dev/null || true
    wait "$receiver" 2>/dev/null || true
  fi
}
trap cleanup EXIT
python3 scripts/audio-device-probe.py --uid "${RAVELINK_AU_DEVICE_UID:-RaveLink.ci-loopback_UID}" --capture-seconds 40 --wav "$au_dir/au-loopback.wav" --ready-file "$au_dir/au-ready" --timeout 55 > "$au_dir/au-receiver.log" 2>&1 &
receiver=$!
for attempt in {1..15}; do
  if [[ -f "$au_dir/au-ready" ]]; then break; fi
  kill -0 "$receiver"
  sleep 1
done
test -f "$au_dir/au-ready"
RAVELINK_AU_REPORT="$au_dir/au-engine.json" scripts/test.sh --skip-build --filter installedAudioUnitGainBypassAndRestoredState 2>&1 | tee "$au_dir/au-test.log"
wait "$receiver"; receiver=''
python3 scripts/verify-au-loopback.py "$au_dir/au-loopback.wav" | tee "$au_dir/au-analysis.json"
