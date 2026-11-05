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
| `adapters_mapping.py` | The mapping-engine adapter (P3.12): chains the whole firmware signal chain in a second host binary — decoder shim → real driver → `SkywriterHIDMapper` (`pico-arduino/SkywriterHID`, the source the firmware links) → HID records. Driven by `TICK`/`FRAME`/`FIN` instructions on a ≤5 ms step timeline (the sensor's own frame cadence), so timed engine behaviour (report cadence, lift-off gating) runs exactly as on the loop hardware. One process per scenario keeps decoder + mapper state fresh. |
| `runner.py` | Driver-agnostic replay runner: scenario → frames in order → fresh adapter state → records. |
| `deviations.py` | Reads the "Known driver deviations" table from `specs/README.md` (the single source of truth) and answers "is `Dn` open, and for which driver?". |
| `canonical.py` | The structured canonical sensor-event grammar (P3.2): native decoder records → canonical events; matching with the documented tolerances; per-scenario `omit_pending`/`keys_pending` deviation gating; cross-driver parity diffing. |
| `hid_grammar.py` | The structured HID outcome-record grammar (P3.2): mouse/keyboard/consumer report records per `specs/hid_mapping.md` §3–§6, validated for every scenario. |
| `test_harness.py` | 11 meta-tests: manifest/frame integrity, every scenario replays on both adapters, fresh-state identity on reruns, simulated-gap accounting, VirtualClock non-sleeping, plus today-true plumbing pins (F01 position values on both drivers, flick W→E dispatch, tap dispatch). |
| `test_scenarios.py` | Spec assertions per scenario (P3.2): manifest lint (structured schema, pending annotations resolve to open spec-ledger rows), canonical expectation compare per driver, deviation-realization checks, HID outcome well-formedness, and cross-driver parity (AC-MAP-09). |
| `test_mapper_unit.py` | Direct mapper unit tests (P3.13): the §4 touch semantics the corpus cannot carry (repeat-inert presses, exact release/lift-off tick timing, tap/doubletap clicks, §6 button rows) asserted against `SkywriterHIDMapper` through a dedicated host binary (`tests/cpp/host_mapper_unit_main.cpp`). |
| `test_firmware_sketch.py` | Static pins on the BLE HID firmware sketch (P3.16): composite Report Map bring-up rules (`AC-BLE-01`/`02`: one `begin()`, device name, sensor-configuration commands) at source level; radio truth stays with the Phase-4 probes. |

## Canonical grammar (P3.2)

`tests/canonical.py` documents the full vocabulary (the event model of
`specs/hid_mapping.md` §2 plus the two control messages). The manifest's
`expect.canonical` expresses expectations in exactly that grammar. Two meta
annotations let known-open driver defects be tolerated *explicitly and
temporarily*:

- `omit_pending: {deviation, drivers}` — the listed drivers may omit the event
  while that `specs/README.md` deviation row is open;
- `keys_pending: {deviation, keys, drivers}` — the listed drivers may leave
  those keys out (attributes a driver still discards). Last user was D7's
  gesture class/edge gate on the Arduino driver (closed 2026-11-05 with P3.11,
  alongside the Python half closed with P3.7): both drivers now decode the
  full GestureInfo word, so gesture events carry code/class/edge equally and
  no annotation of this kind is open at the moment.

Both are **self-arming**: `test_scenarios.py` lints every annotation against
the specs/README.md ledger (a closed row forces dropping the annotation), and a
realization check fails if a fix makes an annotated omission stop reproducing
without the ledger being updated. The `specs/README.md` deviation rows —
D8 (stale
AGENTS.md gotcha) — is therefore guaranteed
to flip its annotation to a hard assertion in the same change that closes it.
(D9, the control-frame events `status_ack` / `fw_version_valid`, was closed
2026-11-05 the same way with fix item P3.11b: the Python and Arduino drivers
both surface `system_status` / `firmware_info` canonical events now — the
Arduino `poll()` also reads whole frames (132 bytes) so its 120-byte version
string arrives complete — and both scenario expectations are hard assertions
on both drivers with no tolerance left.) (D3, the Arduino AirWheel wrap, was
closed 2026-11-05 the same way: commit
P3.9 brought `skywriter.cpp` the Python driver's signed 8-bit counter
difference and silent first-frame baseline, so the `airwheel_wrap` scenario
now hard-asserts its +45° event on both drivers. D4, touch every-set-bit
dispatch + the Arduino early-return skipping the AirWheel field, was closed
2026-11-05 the same way (P3.10): the Python driver's touch `break` and the
Arduino driver's touch `return` are gone — every set touch bit dispatches on
both drivers, the Arduino driver decodes AirWheel in the same frame again, the
new `touch_two_zones` scenario (F23) hard-asserts a two-touch frame on both
drivers, and `touch_with_position_and_airwheel` hard-asserts its +90° airwheel
event on both drivers. D6, firmware validity, was closed 2026-11-05 without needing a fixture
annotation: `_handle_firmware_info`'s now-spec-correct FwValid handling is
pinned directly in `tests/test_firmware_info.py`. D7, gesture class
(bits 12-15) / edge-flick flag (bit 16), was closed 2026-11-05 the same way:
the Python driver (P3.7) and the Arduino driver (P3.11) both decode the full
32-bit GestureInfo word, and the six gesture scenarios now hard-assert
code/class/edge on both drivers. D2, the Arduino
Set_Runtime_Parameter out-of-bounds write past its 15-byte command payloads,
was closed 2026-11-05 without a fixture annotation either: commit `c6aecc7`
(the pre-loop revert of `arduino/Skywriter/` to the pristine upstream library)
removed the `setRuntimeParam` code the row described — the offending loop
existed only at commits `e781528`…`1c0b12a`, which is where the defect report
came from.)

Values: positions are raw 16-bit sensor units — the Python driver's ±4-unit
rounding (it rounds to 4 decimals of raw/65536) is the only tolerated
representation difference in the whole suite.

## HID outcome records (P3.2)

`expect.hid` per scenario pins the expected controller output in the
`tests/hid_grammar.py` grammar (mouse move/button/wheel/click, keyboard
Page Up/Down, consumer media usages). Well-formedness is
validated for every scenario; the scenarios in `MAPPING_ENGINE_ARMED`
(`tests/test_scenarios.py`)
are additionally **replay-asserted end-to-end** against `SkywriterHIDMapper`
through the mapping adapter — the pointer-model and always-silent scenarios
armed with P3.12, the touch scenarios with P3.13, the AirWheel scenarios
with P3.14, and the gesture/media scenarios with P3.15 (since P3.15 the
full §6 table is implemented in the engine, every manifest scenario is
armed, and `MAPPING_ENGINE_PENDING` is empty — it exists only as the
classification home for future scenarios the engine does not yet serve).
Behaviours the corpus cannot carry because of
the Python driver's by-design touch-repeat limiting (default 4 Hz — a repeat
touch frame under 250 ms would make the decoders' canonical streams diverge
undecoratably), such as repeat-inert presses and exact release/lift-off tick
timing, are pinned by the direct mapper unit tests in `test_mapper_unit.py`
against the same engine source the firmware links (which also carries the
§5 AirWheel pins: notch quantization, sign, fractional accumulation,
un-coalesced emission, lift-off reset, plus the §6 keyboard/media/hold
auto-scroll row pins).

## Scope note for the loop

The P3.1 meta-tests and the P3.2 expectation tests together keep `run_tests.sh`
green while each decoder fix (P3.3–P3.11) flips one more tolerance from
"pending deviation" to a full assertion — red→green per fix, never
red-by-design.
