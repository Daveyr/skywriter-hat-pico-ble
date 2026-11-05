# Fixture-replay test harness (fix_plan P3.1 + P3.2)

Feeds the recorded sensor frames in `specs/fixtures/` through the decoders and
asserts on what they produce — without any hardware. Discovered automatically
by `bash run_tests.sh` (`python3 -m pytest -q tests/`).

## Parts

| File | Role |
|---|---|
| `fixtures.py` | Loads `specs/fixtures/manifest.json` and the `.hex` frame files (header included, as read over the wire). |
| `virtual_clock.py` | Simulated millisecond clock: `time_gap_ms` is *advanced*, never slept. |
| `adapters.py` | The adapter contract (fresh state, per-frame feed, finish hook) and the registry. |
| `adapters_python.py` | Wraps the Raspberry Pi driver (`library/skywriter/__init__.py`) with mocked hardware (same pattern as `library/test.py`); mirrors `_do_poll`'s ID dispatch and feeds the **payload** (frame minus 4-byte header) per the manifest convention. Its wall-clock `millis()` is redirected onto the VirtualClock. |
| `adapters_cpp.py` + `cpp/` | Compiles the real Arduino driver (`arduino/Skywriter/skywriter.cpp`) for the host behind minimal `Arduino.h`/`Wire.h` shims, then drives its genuine `poll()` path once per fed frame. One process per scenario keeps decoder state fresh. Compiler resolution: `g++`/`c++` → `zig c++` (PATH) → `pip install --user --break-system-packages ziglang` fallback (the container has no system compiler and no sudo). |
| `runner.py` | Driver-agnostic replay runner: scenario → frames in order → fresh adapter state → records. |
| `deviations.py` | Reads the "Known driver deviations" table from `specs/README.md` (the single source of truth) and answers "is `Dn` open, and for which driver?". |
| `canonical.py` | The structured canonical sensor-event grammar (P3.2): native decoder records → canonical events; matching with the documented tolerances; per-scenario `omit_pending`/`keys_pending` deviation gating; cross-driver parity diffing. |
| `hid_grammar.py` | The structured HID outcome-record grammar (P3.2): mouse/keyboard/consumer report records per `specs/hid_mapping.md` §3–§6, validated for every scenario. |
| `test_harness.py` | 11 meta-tests: manifest/frame integrity, every scenario replays on both adapters, fresh-state identity on reruns, simulated-gap accounting, VirtualClock non-sleeping, plus today-true plumbing pins (F01 position values on both drivers, flick W→E dispatch, tap dispatch). |
| `test_scenarios.py` | Spec assertions per scenario (P3.2): manifest lint (structured schema, pending annotations resolve to open spec-ledger rows), canonical expectation compare per driver, deviation-realization checks, HID outcome well-formedness, and cross-driver parity (AC-MAP-09). |

## Canonical grammar (P3.2)

`tests/canonical.py` documents the full vocabulary (the event model of
`specs/hid_mapping.md` §2 plus the two control messages). The manifest's
`expect.canonical` expresses expectations in exactly that grammar. Two meta
annotations let known-open driver defects be tolerated *explicitly and
temporarily*:

- `omit_pending: {deviation, drivers}` — the listed drivers may omit the event
  while that `specs/README.md` deviation row is open;
- `keys_pending: {deviation, keys, drivers}` — the listed drivers may leave
  those keys out (attributes a driver still discards; e.g. D7's gesture
  class/edge on the Arduino driver — the Python side supplies them since
  P3.7).

Both are **self-arming**: `test_scenarios.py` lints every annotation against
the specs/README.md ledger (a closed row forces dropping the annotation), and a
realization check fails if a fix makes an annotated omission stop reproducing
without the ledger being updated. The `specs/README.md` deviation rows — D2
(Arduino buffer overrun), D3 (airwheel wrap, Arduino side), D4 (touch
early-return), D7 (gesture attributes, Arduino side), D8 (stale
AGENTS.md gotcha) and D9 (control-frame events) — are therefore each guaranteed
to flip its annotation to a hard assertion in the same change that closes it.
(D6, firmware validity, was closed 2026-11-05 without needing a fixture
annotation: `_handle_firmware_info`'s now-spec-correct FwValid handling is
pinned directly in `tests/test_firmware_info.py`. D7's Python half was closed
2026-11-05 the same way — the Python gesture events now carry class/edge and
the `keys_pending` annotations cover only `cpp`.)

Values: positions are raw 16-bit sensor units — the Python driver's ±4-unit
rounding (it rounds to 4 decimals of raw/65536) is the only tolerated
representation difference in the whole suite.

## HID outcome records (P3.2)

`expect.hid` per scenario pins the expected controller output in the
`tests/hid_grammar.py` grammar (mouse move/button/wheel/click, keyboard
Page Up/Down, consumer media usages). Well-formedness is validated now; the
replay-assertion of these records arms with the mapping-engine items
P3.12–P3.15, which target exactly these scenarios — the manifest is their
machine-readable acceptance data.

## Scope note for the loop

The P3.1 meta-tests and the P3.2 expectation tests together keep `run_tests.sh`
green while each decoder fix (P3.3–P3.11) flips one more tolerance from
"pending deviation" to a full assertion — red→green per fix, never
red-by-design.
