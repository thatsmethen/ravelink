#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${RAVELINK_TEST_INSTALLED_AU:-}" != 1 ]]; then
  echo 'Set RAVELINK_TEST_INSTALLED_AU=1 only on a host prepared for installed virtual-device acceptance.' >&2
  exit 2
fi
au_dir="${RAVELINK_AU_OUTPUT:-$PWD/build}"
mkdir -p "$au_dir"
rm -f "$au_dir/au-ready" "$au_dir/au-loopback.wav" "$au_dir/au-engine.json" "$au_dir/au-analysis.json" "$au_dir/au-exit-status.json"
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
# Preserve independent captured PCM even when the engine assertion fails.
engine_status=0; receiver_status=0; analysis_status=0
RAVELINK_AU_REPORT="$au_dir/au-engine.json" scripts/test.sh --skip-build --filter installedAudioUnitGainBypassAndRestoredState 2>&1 | tee "$au_dir/au-test.log" || engine_status=$?
wait "$receiver" || receiver_status=$?; receiver=''
python3 scripts/verify-au-loopback.py "$au_dir/au-loopback.wav" 2> "$au_dir/au-analysis.log" | tee "$au_dir/au-analysis.json" || analysis_status=$?
printf '{"engine":%s,"receiver":%s,"analysis":%s}\n' "$engine_status" "$receiver_status" "$analysis_status" > "$au_dir/au-exit-status.json"
if (( engine_status || receiver_status || analysis_status )); then
  cat "$au_dir/au-exit-status.json" >&2
  cat "$au_dir/au-analysis.log" >&2
  exit 1
fi
