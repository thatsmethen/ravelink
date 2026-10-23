#!/bin/bash
# Opt-in acceptance using named installed virtual devices on a disposable host.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${RAVELINK_TEST_SOUND_CHECK:-}" != 1 ]]; then
  echo 'Set RAVELINK_TEST_SOUND_CHECK=1 only on a host prepared for installed virtual-device acceptance.' >&2
  exit 2
fi
check_dir="${RAVELINK_SOUND_CHECK_OUTPUT:-$PWD/build}"
mkdir -p "$check_dir"
rm -f "$check_dir"/sound-check-{output,guard}-ready "$check_dir"/sound-check-{output,guard}.wav
rm -f "$check_dir"/sound-check-{engine,analysis,exit-status}.json
output_pid=''; guard_pid=''
cleanup() {
  for process in "$output_pid" "$guard_pid"; do
    if [[ -n "$process" ]]; then kill "$process" 2>/dev/null || true; fi
  done
  for process in "$output_pid" "$guard_pid"; do
    if [[ -n "$process" ]]; then wait "$process" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT
python3 scripts/audio-device-probe.py --uid "${RAVELINK_SOUND_CHECK_UID:-RaveLink.ci-mix-a_UID}" --capture-seconds 24 --wav "$check_dir/sound-check-output.wav" --ready-file "$check_dir/sound-check-output-ready" --timeout 45 > "$check_dir/sound-check-output.log" 2>&1 &
output_pid=$!
python3 scripts/audio-device-probe.py --uid "${RAVELINK_SOUND_CHECK_GUARD_UID:-RaveLink.ci-mix-b_UID}" --capture-seconds 24 --wav "$check_dir/sound-check-guard.wav" --ready-file "$check_dir/sound-check-guard-ready" --timeout 45 > "$check_dir/sound-check-guard.log" 2>&1 &
guard_pid=$!
for attempt in {1..15}; do
  if [[ -f "$check_dir/sound-check-output-ready" && -f "$check_dir/sound-check-guard-ready" ]]; then break; fi
  kill -0 "$output_pid" && kill -0 "$guard_pid"
  sleep 1
done
test -f "$check_dir/sound-check-output-ready" && test -f "$check_dir/sound-check-guard-ready"
engine_status=0; output_status=0; guard_status=0; analysis_status=0
RAVELINK_SOUND_CHECK_REPORT="$check_dir/sound-check-engine.json" scripts/test.sh --skip-build --filter installedSoundCheckDryRecordLoopGainAndSilence 2>&1 | tee "$check_dir/sound-check-test.log" || engine_status=$?
wait "$output_pid" || output_status=$?; output_pid=''
wait "$guard_pid" || guard_status=$?; guard_pid=''
python3 scripts/verify-sound-check.py "$check_dir" 2> "$check_dir/sound-check-analysis.log" | tee "$check_dir/sound-check-analysis.json" || analysis_status=$?
printf '{"engine":%s,"output":%s,"guard":%s,"analysis":%s}\n' \
  "$engine_status" "$output_status" "$guard_status" "$analysis_status" > "$check_dir/sound-check-exit-status.json"
if (( engine_status || output_status || guard_status || analysis_status )); then
  cat "$check_dir/sound-check-exit-status.json" >&2
  cat "$check_dir/sound-check-analysis.log" >&2
  exit 1
fi
