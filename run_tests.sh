#!/usr/bin/env bash
# run_tests.sh — the single test command for humans, the Ralph loop and the
# outer hardware loop.
#
# Why one entrypoint: everyone must judge "green" by the same standard. A check
# that cannot pass yet is never silently skipped — it is tracked in
# fix_plan.md.
#
# Exit code 0 = all checks pass. Non-zero = at least one required check failed.

set -uo pipefail
cd "$(dirname "$0")"

failures=0

check() {
  local name=$1; shift
  echo
  echo "=== $name"
  if "$@"; then
    echo "--- PASS: $name"
  else
    echo "--- FAIL: $name" >&2
    failures=$((failures + 1))
  fi
}

# 1. Fixture corpus integrity: the recorded sensor frames in specs/fixtures
# must stay loadable and internally consistent (size byte = message length,
# manifest references resolve). This is the test data every other test uses.
fixture_corpus() {
  python3 - <<'EOF'
import json, sys
base = 'specs/fixtures'
m = json.load(open(f'{base}/manifest.json'))
bad = 0
for name, meta in m['frames'].items():
    try:
        frame = bytes.fromhex(open(f"{base}/{meta['file']}").read().strip())
    except Exception as e:
        print(f'{name}: cannot load: {e}')
        bad += 1
        continue
    if frame[0] != len(frame):
        print(f'{name}: size byte 0x{frame[0]:02x} != {len(frame)} bytes')
        bad += 1
for s in m['scenarios']:
    for ref in s['frames']:
        if ref not in m['frames']:
            print(f"scenario {s['name']}: unknown frame {ref}")
            bad += 1
sys.exit(1 if bad else 0)
EOF
}

# 2. Python driver unit tests (mocked hardware — no real I2C allowed).
# Offline: the fake I2C bus answers the startup handshake with the recorded
# specs/fixtures/F16_status_ack_a2.hex frame (W5).
library_unit() {
  (cd library && python3 test.py)
}

# 3. Replay tests: decoder and gesture-to-HID mapping tests driven by
# specs/fixtures. Picked up automatically once Phase 3 adds tests/.
fixture_replay() {
  if [ -d tests ] && ls tests/test_*.py >/dev/null 2>&1; then
    python3 -m pytest -q tests/
  else
    echo "no tests/ yet — fixture replay tests are fix_plan.md item P3.3 (skipped, not a failure)"
    return 0
  fi
}

# 4. Firmware compiles: every sketch folder (directory containing a .ino)
# must build for the Pico W (Raspberry Pi's wireless microcontroller board).
# Build output goes to a temporary directory so the flash-tool-managed
# build/ folders are never touched.
sketch_compile() {
  if ! command -v arduino-cli >/dev/null 2>&1; then
    echo "arduino-cli not installed — compile check skipped (the dev container provides it)"
    return 0
  fi
  local out rc=0 sketch dir
  out=$(mktemp -d)
  while IFS= read -r sketch; do
    dir=$(dirname "$sketch")
    echo "compiling $dir"
    arduino-cli compile -b rp2040:rp2040:rpipicow --output-dir "$out/$(basename "$dir")" "$dir" || rc=1
  done < <(find pico-arduino arduino -name '*.ino' -not -path '*/build/*' 2>/dev/null)
  rm -rf "$out"
  return $rc
}

check "fixture corpus integrity" fixture_corpus
check "python driver unit tests" library_unit
check "fixture replay tests" fixture_replay
check "firmware compiles for Pico W" sketch_compile

echo
if [ "$failures" -eq 0 ]; then
  echo "ALL TESTS PASSED"
else
  echo "$failures CHECK(S) FAILED — known-red items and their fixes are tracked in fix_plan.md" >&2
fi
exit $((failures > 0))
