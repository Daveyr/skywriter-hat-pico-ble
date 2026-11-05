# Fixture-replay test harness (fix_plan P3.1)

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
| `test_harness.py` | Meta-tests: every scenario replays on both adapters, per-replay fresh state, simulated gaps, plus a few plumbing pins (position values, flick dispatch, tap dispatch) that hold true today. |

## Record shapes (native, pre-P3.2 canonicalization)

- Python driver: `{"kind": "move", "x/y/z": float}` (raw/65536 rounded to 4 dp),
  `{"kind": "flick", "from", "to"}` (zone names), `{"kind": "touch"|"tap"|"doubletap", "zone"}`,
  `{"kind": "garbage"}`, `{"kind": "airwheel", "degrees": float}`.
- C++ decoder: `{"kind": "move", "x/y/z": int}` (raw 16-bit),
  `{"kind": "touch_code", "code": 0-14}` (skywriter.h constants),
  `{"kind": "gesture", "code": 1-7}`, `{"kind": "airwheel", "degrees": int}`.

Cross-driver parity comparison (AC-MAP-09) needs the structured canonical
grammar from fix_plan P3.2 before these native shapes can be diffed.

## Scope note for the loop

Assertions here deliberately pin only behaviour that already matches the spec;
the known-red decoder deviations (D1–D8, `specs/README.md`) assert when their
fix items (P3.3–P3.11) land, so `run_tests.sh` stays honest (green = pass, red
= tracked in fix_plan.md).
