#!/bin/bash
# Explicit installed-driver acceptance on disposable CI hosts; does not install drivers.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${RAVELINK_TEST_DEVICE_SOAK:-}" != 1 ]]; then
  echo 'Set RAVELINK_TEST_DEVICE_SOAK=1 only on a host prepared for installed virtual-device acceptance.' >&2
  exit 2
fi
soak_dir="${RAVELINK_SOAK_OUTPUT:-$PWD/build}"
mkdir -p "$soak_dir"
rm -f "$soak_dir"/soak-{a,b,feeder}-ready "$soak_dir/soak-go"
rm -f "$soak_dir"/soak-{a,b}.wav "$soak_dir"/soak-{a,b,feeder,engine,analysis}.json
receiver_a=''; receiver_b=''; feeder=''
cleanup() {
  for process in "$receiver_a" "$receiver_b" "$feeder"; do
    if [[ -n "$process" ]]; then kill "$process" 2>/dev/null || true; fi
  done
  for process in "$receiver_a" "$receiver_b" "$feeder"; do
    if [[ -n "$process" ]]; then wait "$process" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT
python3 scripts/audio-soak-probe.py --mode record --uid "${RAVELINK_MATRIX_A_UID:-RaveLink.ci-mix-a_UID}" --seconds 60 --wav "$soak_dir/soak-a.wav" --report "$soak_dir/soak-a.json" --ready-file "$soak_dir/soak-a-ready" > "$soak_dir/soak-a.log" 2>&1 &
receiver_a=$!
python3 scripts/audio-soak-probe.py --mode record --uid "${RAVELINK_MATRIX_B_UID:-RaveLink.ci-mix-b_UID}" --seconds 60 --wav "$soak_dir/soak-b.wav" --report "$soak_dir/soak-b.json" --ready-file "$soak_dir/soak-b-ready" > "$soak_dir/soak-b.log" 2>&1 &
receiver_b=$!
python3 scripts/audio-soak-probe.py --mode feed --uid "${RAVELINK_SOAK_INPUT_UID:-RaveLink.ci-loopback_UID}" --seconds 35 --report "$soak_dir/soak-feeder.json" --ready-file "$soak_dir/soak-feeder-ready" --go-file "$soak_dir/soak-go" > "$soak_dir/soak-feeder.log" 2>&1 &
feeder=$!
for attempt in {1..30}; do
  if [[ -f "$soak_dir/soak-a-ready" && -f "$soak_dir/soak-b-ready" && -f "$soak_dir/soak-feeder-ready" ]]; then break; fi
  kill -0 "$receiver_a" && kill -0 "$receiver_b" && kill -0 "$feeder"
  sleep 1
done
test -f "$soak_dir/soak-a-ready" && test -f "$soak_dir/soak-b-ready" && test -f "$soak_dir/soak-feeder-ready"
RAVELINK_SOAK_GO_FILE="$soak_dir/soak-go" RAVELINK_SOAK_REPORT="$soak_dir/soak-engine.json" scripts/test.sh --skip-build --filter installedGroupedDeviceInputThirtySecondSoak 2>&1 | tee "$soak_dir/soak-test.log"
wait "$feeder"; feeder=''
wait "$receiver_a"; receiver_a=''
wait "$receiver_b"; receiver_b=''
python3 scripts/verify-device-soak.py "$soak_dir" | tee "$soak_dir/soak-analysis.json"
