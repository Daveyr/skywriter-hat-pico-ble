# fix_plan.md — work ledger for the Ralph development loop

This file is the loop's shared memory and the single planning source of truth.
`PROMPT.md` tells the agent to work the first open item here each iteration.

## How to use this file (agents)

1. Work items are grouped by phase, in intended order. Take the **first open
   item** in the earliest phase.
2. Complete items fully — no placeholders. Verify with `bash run_tests.sh` or the
   verification named in the item.
3. When an item is done and verified, **move it to the Done section** at the
   bottom with its commit hash. Do not leave checked boxes in the phase lists.
4. Anything you discover that is wrong, missing or risky — in any area, even
   outside your current item — becomes a **new item** here (and known defects
   that contradict `specs/` also get a row in `specs/README.md`'s deviation
   table; that table is the source of truth for defects, this file for work).
5. Commit messages must be readable without electronics knowledge: expand
   every acronym on first use, state what changed and why in plain language
   first (AGENTS.md "Conventions").

## How to run the loop

From the host (same flags as `run_sandbox.sh`, but the trailing
`opencode --auto` is replaced by `bash ralph.sh`):

```bash
docker run -it --rm \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --pids-limit 512 --memory 8g \
  --env-file /home/user/.config/skywriter-sandbox.env \
  -v "$PWD:/workspace" \
  -v "$PWD/.git/config:/workspace/.git/config:ro" \
  -v "$PWD/.git/hooks:/workspace/.git/hooks:ro" \
  -v skywriter-opencode:/home/dev/.local/share/opencode \
  -v skywriter-arduino:/home/dev/.arduino15 \
  -v "$HOME/.gitconfig:/home/dev/.gitconfig:ro" \
  -v "$HOME/.ssh/known_hosts:/home/dev/.ssh/known_hosts:ro" \
  -v "$HOME/.ssh/skywriter_deploy_key:/home/dev/.ssh/id_ed25519:ro" \
  skywriter-dev bash ralph.sh
```

- Model: pinned to `opencode-go/glm-5.3-flash` (2026-11-04 decision — small
  and fast enough for the long iterations, cheap enough for a 40-item loop).
  Override with `RALPH_MODEL=<model> [-e RALPH_MODEL=…]`. A reasoning variant
  can be forced with `RALPH_MODEL=opencode-go/glm-5.3-flash#high`.
- Budgets: `RALPH_MAX_ITER` (40), `RALPH_MAX_HOURS` (6),
  `RALPH_MAX_CONSECUTIVE_FAILURES` (5) — set as `-e VAR=value` on docker run.
- Iteration logs land in `logs/` (gitignored). Stop markers `DONE` /
  `READY_FOR_HW` are gitignored; the loop watches for them. Marker protocol:
  stale markers handle themselves — `READY_FOR_HW` is cleared by `ralph.sh`
  on its next start once `HW_REPORT.md` (the hardware test results) exists;
  a stale `DONE` blocks restart on purpose (delete it manually to rerun).
- `run_sandbox.sh` stays as the interactive (human-in-the-loop) entrypoint.

## Status snapshot (2026-11-04)

- **Phase 0 done**: repository clean, sandbox image `skywriter-dev` built,
  model auth in `skywriter-sandbox.env`, deploy key push works.
- **Phase 1 done** (commit `1c0b12a`): `specs/` contains the acceptance
  specs — `README.md` (framing + deviation ledger D1–D8), `ble_hid.md`
  (wireless radio profile, `AC-BLE-01…08`), `hid_mapping.md`
  (gesture→controller mapping, `AC-MAP-01…09`), `fixtures/` (19 recorded /
  constructed sensor frames + `manifest.json` expectations).
- **Spec revision in this commit (build-mode corrections)**:
  - AirWheel wrap corrected to the **signed 8-bit** difference (counter
    wraps 255→0; 32 counts ≈ 1 revolution — verified directly against
    `datasheets/Interface.pdf` Table 4-10 wording). Updated
    `hid_mapping.md` §2, `AC-MAP-04`, deviation row D3, and re-authored
    fixture F14 (counter now 0xFE; file name keeps the stale `1e` label —
    see `manifest.json` notes) so the wrap-crossing test is unambiguous.
  - Fixture provenance relabelled honestly: only F16 is verbatim vendor
    bytes; F02/F07/F08/F09 are *vendor-derived* (vendor values repacked
    into our frame).
  - F01 `hid` expectation corrected to match `hid_mapping.md` §3 rule 4:
    the first valid position sets the baseline and emits no movement.
- **Phase 2 bootstrapped** (commit `065a27f`): `PROMPT.md`, `ralph.sh`,
  `run_tests.sh` exist; remaining items below. Loop model pinned (see
  "How to run the loop"); marker protocol now self-clearing.
- **Baseline test run (2026-11-04, host)**: fixture corpus green; Python unit
  tests red (W5); `SkywriterInterrupt` example compiles green; `NeoPaint` and
  `SkyPainter` examples red — missing `Adafruit NeoPixel` library (W6).
  Update (this commit): W6 is now verified green — see the W6 item.
  Update (2026-11-05, W5 commit): W5 is verified green too; every check in
  `bash run_tests.sh` passes.
  Update (2026-11-05, P3.1 commit): the replay tests are no longer
  "skipped, not a failure" — `tests/` exists and all 11 harness meta-tests
  pass; `bash run_tests.sh` remains green end-to-end (4/4 checks).
  Update (2026-11-05, P3.2 commit): manifest expectations are now
  machine-checkable (`tests/canonical.py` + `tests/hid_grammar.py`); all 18
  pytest tests pass (11 harness meta-tests + 7 spec/assertion tests);
  deviation tolerances in the manifest are self-arming against the
  `specs/README.md` ledger (new row D9); `run_tests.sh` still green 4/4.
  Update (2026-11-05, P3.4 commit): deviation D3 is closed for the Python
  driver (signed 8-bit AirWheel counter difference + silent re-baseline
  after a gap — the ledger row now covers only the Arduino side, pending
  P3.9), and the airwheel-baseline question P3.14a is settled together
  with it; new fixture frame F20 re-baselines the
  `touch_with_position_and_airwheel` scenario. 22 pytest tests green;
  `run_tests.sh` 4/4.
  Update (2026-11-05, P3.5b commit): deviation D10 is closed — circle
  gestures (wire codes 6/7) now dispatch from the Python driver via a new
  `circle(direction)` decorator; new fixture frames F21/F22 give the corpus
  its first AirWheel-disabled output mask (bit 3 off). 22 pytest tests;
  `run_tests.sh` 4/4.
  Update (2026-11-05, P3.6 commit): deviation D6 is closed — firmware
  version reports are valid only when `FwValid == 0xAA`; undefined status
  values now raise instead of printing garbage as a version string. 29
  pytest tests; `run_tests.sh` 4/4.
  Update (2026-11-05, P3.7 commit): deviation D7 is closed for the Python
  driver —GestureInfo is decoded as a full 32-bit word and gesture events
  carry the class and edge-flick attributes (in-progress frames still emit
  nothing); the keys_pending annotations narrowed to `cpp`, the ledger row
  to Arduino only. 29 pytest tests; `run_tests.sh` 4/4.
  Update (2026-11-05, P3.8 commit): deviation D2 turned out to be already
  resolved — commit `c6aecc7` (the pre-loop revert of `arduino/Skywriter/` to
  the pristine upstream originals) removed the `setRuntimeParam` code the row
  described, so the row is gone from the ledger without a code change; the
  P3.16 firmware item now carries the 15-byte sensor-configuration caution so
  the off-by-one cannot be reintroduced, and the P3.19 item records the
  post-revert D8 context (AGENTS.md's gotchas are currently accurate).
  Update (2026-11-05, P3.9 commit): deviation D3 is closed — the Arduino
  driver now has the same signed 8-bit AirWheel counter difference and
  silent first-frame baseline as the Python driver (P3.4), so the
  `airwheel_wrap` scenario hard-asserts its +45° event on **both** drivers
  with no tolerance left (the `omit_pending` D3 annotation is gone from
  `specs/fixtures/manifest.json` and the D3 row is gone from
  `specs/README.md`). 29 pytest tests; `run_tests.sh` green 4/4.
   Update (2026-11-05, P3.10 commit): deviation D4 is closed — every set
   touch bit now dispatches on **both** drivers (the Arduino touch `return`
   and the Python touch `break` are gone; the Arduino driver decodes
   AirWheel in the same frame again; the Python repeat-limiter now tracks
   last firing per zone so same-frame zones don't suppress each other), the
   `touch_with_position_and_airwheel` scenario hard-asserts its +90°
   airwheel event on both drivers, new fixture F23 (`touch_two_zones`
   scenario) covers a two-touch frame. The D4 row is gone from
   `specs/README.md`. 30 pytest tests; `run_tests.sh` green 4/4.
- **Script invocation**: run the scripts as `bash ralph.sh` /
  `bash run_tests.sh` — their executable bit could not be set in this
  environment (`chmod` is blocked); run `chmod +x ralph.sh run_tests.sh`
  manually if you prefer `./`-style invocation.
- Stack decision is settled (verified inside the sandbox image): the Pico W
  arduino core 6.3.1 ships the Bluetooth HID libraries we need
  (`HID_Bluetooth`/`PicoBluetoothBLEHID`, `MouseBLE`, `KeyboardBLE`).
- **Phase 5 language/platform confirmed (2026-11-04, docs verified —
  re-verify on hardware at P5.0)**: Raspberry Pi officially ships
  **MicroPython** for the Pico W, and MicroPython for the Pico W supports
  Bluetooth LE (BLE) natively via the `bluetooth` module (peripheral role and
  GATT server included, merged upstream; see raspberrypi.com "New
  functionality: Bluetooth for Pico W"). Known gaps to respect: there is no
  ready-made HID (Human Interface Device) host profile in MicroPython — the
  HID-over-GATT service must be hand-built — and upstream reports mention a
  ~512-byte attribute-table limit that a composite HID report map may push.
  So `pico-python/` targets MicroPython, and P5.0 gates the build on hardware.
- Hardware notes for Phase 4: the Pico W must be plugged into the **host**
  (the container has no USB access by design); the host currently lacks
  `pyserial` and `bleak` (install when starting Phase 4); a Bluetooth radio
  is present on the host.

---

## Phase 2 — Ralph loop harness

- [x] W1 `PROMPT.md` — mission, iteration protocol, stop markers `DONE` /
      `READY_FOR_HW`, non-specialist commit-message rule.
- [x] W2 `ralph.sh` — loop driver: iteration/time budgets, per-iteration logs,
      marker detection, automatic git snapshot for uncommitted work, final
      push.
- [x] W3 `run_tests.sh` — single test entrypoint: fixture corpus integrity,
      Python unit tests, fixture replay tests (auto-detected once `tests/`
      exists), firmware compile check for every sketch.
- [x] W4 `.gitignore` — loop markers (`DONE`, `READY_FOR_HW`) and `logs/`
      ignored so they never pollute commits.
- [x] W2b `ralph.sh` — model pinned to `opencode-go/glm-5.3-flash`
      (`RALPH_MODEL` overridable) and stale-marker protocol (this commit).
- [x] W6 Make `bash run_tests.sh` fully green — firmware compiles: done and
      verified 2026-11-04. `Adafruit NeoPixel` 1.15.5 installed into the
      `skywriter-arduino` volume (`~/.arduino15/libraries/`), and the
      Dockerfile sets `ARDUINO_DIRECTORIES_USER=/home/dev/.arduino15` (the
      user directory root — arduino-cli appends the `libraries/` segment
      itself, so pointing it at the libraries folder creates a wrong nested
      folder). Verified: `bash run_tests.sh` firmware-compile check now
      passes for all example sketches. Host note: if `run_tests.sh` is run
      on the host (not in the container), the host also needs
      `arduino-cli lib install "Adafruit NeoPixel"`.
- [x] W7 Dry-run the loop: `RALPH_MAX_ITER=1 docker run … skywriter-dev
      bash ralph.sh` — confirm the agent commits, logs land in `logs/`, marker
      files stop the loop. Fix any friction found.

## Phase 3 — Implementation (order is deliberate: test harness first)

Per AGENTS.md "To build": Pico/Pico W firmware lives in `pico-arduino/`.
Library fixes to the existing driver go to `arduino/Skywriter/` (the shared
library both use). Python driver fixes go to `library/`.

### 3a — Replay harness (must exist before decoder/fix items)

- [x] P3.1 → done, moved to the Done section below.
- [x] P3.2 → done, moved to the Done section below.

### 3b — Python driver defects (`library/skywriter/__init__.py`) — one per item

- [x] P3.3 → done, moved to the Done section below.
- [x] P3.5 → done, moved to the Done section below.
- [x] P3.5b → done, moved to the Done section below.
- [x] P3.6 → done, moved to the Done section below.
- [x] P3.7 → done, moved to the Done section below.

### 3c — Arduino driver defects (`arduino/Skywriter/skywriter.cpp`) — one per item

- [x] P3.8 → done, moved to the Done section below.
- [x] P3.9 → done, moved to the Done section below.
- [x] P3.10 → done, moved to the Done section below.
- [ ] P3.11 Deviation D7 — same gesture-attribute fix as P3.7.
- [ ] P3.11b Deviation D9 — surface control-frame results as canonical
      events (discovered by P3.2): Python `_handle_status_info` /
      `_handle_firmware_info` parse their payload and emit a record the
      harness adapter can capture (System_Status: Set_Runtime id + error
      code; Fw_Version: FwValid flag + NUL-stripped version string — validity
      semantics itself is P3.6/D6), and Arduino `poll()` cases `0x15`/`0x83`
      call new optional callbacks (`onSystemStatus`, `onFirmwareVersion`).
      Then, in the same commit: remove the D9 row from `specs/README.md` and
      drop the `omit_pending` annotations on the `status_ack` /
      `fw_version_valid` scenarios in `specs/fixtures/manifest.json` — the
      realization checks re-arm the assertions automatically (see
      `tests/README.md`, "Canonical grammar").

### 3d — Mapping engine (`pico-arduino/`, verifiable with fixtures)

- [ ] P3.12 Pointer model per `specs/hid_mapping.md` §3: normalization,
      GAIN, sign, jump rejection + re-baseline, lift-off gating, report
      cadence. Target `AC-MAP-01` (fixtures F01, F19).
- [ ] P3.13 Touch semantics per §4: press-once/repeat-inert, release after
      `TOUCH_RELEASE_MS`, tap/doubletap click semantics, multi-button per
      zone. Target `AC-MAP-02`, `AC-MAP-03`, `AC-MAP-07` release part
      (fixtures F07, F08, F09, F10, F18).
- [ ] P3.14 Airwheel semantics per §5: 11.25°-quantized notches, sign,
      accumulator. Target `AC-MAP-04` wrap survivor (fixtures F11–F15).
      (Baseline rule settled by P3.14a — see the Done section.)
- [ ] P3.15 Full §6 default mapping table as the single implementation table
      ("the table IS the implementation"), incl. garbage → nothing, reserved
      doubletap east/west → nothing, and media/consumer rows. Target
      `AC-MAP-05`, `AC-MAP-06`.
- [ ] P3.15b Fixture-corpus gap fill (discovered by P3.2): the corpus has no
      scenario that exercises actual pointer movement (F01, then a second
      valid *moderately different* position → a real mouse delta), nor any
      fixture for several §6 rows: `touch(north/south)` hold auto-scroll,
      `tap(east/west/north/south)` right-click + middle-click + Page Up /
      Page Down rows, `doubletap(east/west)` reserved (nothing) rows, and
      S→N/N→S volume flicks. Add frames per `specs/fixtures/README.md`
      ("Adding fixtures") with structured expectations; needed for the
      P3.12–P3.15 assertions and `AC-MAP-01`, `AC-MAP-02`, `AC-MAP-03`,
      `AC-MAP-08`.

### 3e — BLE HID firmware (`pico-arduino/`) — software written here, verified
in Phase 4 on hardware

- [ ] P3.16 Firmware sketch: sensor stack + composite Bluetooth LE HID device
      bring-up per `specs/ble_hid.md` §3–4 — link `MouseBLE` + `KeyboardBLE`
      and call exactly **one** `begin()`, device name `Skywriter HID`,
      HID-class appearance. Target `AC-BLE-01`, `AC-BLE-02` (composite
      Report Map). Compiles in-container; RF behaviour verified in Phase 4.
      (Sensor bring-up note from P3.8: the firmware's sensor stack must send
      the four Set_Runtime_Parameter (`0xA2`) configuration commands itself —
      the pristine stock `arduino/Skywriter` library does not configure the
      sensor. Each command is the `0x10` control-setup byte on the I2C
      (Inter-Integrated Circuit) write followed by **exactly 15 payload
      bytes** (the same payload the Python `setup()` writes), never a
      16-step copy loop over a 15-element array — that off-by-one was the
      removed deviation D2.)
- [ ] P3.17 Firmware sketch: pairing, battery, and lifecycle wiring per
      `specs/ble_hid.md` §5, §6, §8 — battery reported 100 % at connect,
      drop reports while unconnected, neutral resync report on (re)connect,
      back to advertising on link loss. Target `AC-BLE-03`, `AC-BLE-07`
      (verified in Phase 4).
- [ ] P3.18 Firmware sketch: performance provisions per `specs/ble_hid.md`
      §7 — report pacing to the connection interval with delta accumulation,
      button/press transitions never coalesced away. Target `AC-BLE-04`
      (verified in Phase 4).
- [ ] P3.19 Truth-check the AGENTS.md gotchas (deviation D8): verify the
      "`begin()` does not send `SW_SET_RUNTIME`" claim against current code
      and fix the doc if stale; re-check `poll()` `INPUT` vs
      `INPUT_PULLUP`. (Context discovered by P3.8: commit `c6aecc7` — the
      pre-loop revert of `arduino/Skywriter/` to the pristine upstream
      library — removed the four runtime-parameter commands from `begin()`,
      so both AGENTS.md gotcha claims are currently *accurate* (`begin()`
      sends no `SW_SET_RUNTIME`, `poll()` still resets the pin mode to
      `INPUT`); the stale side is the D8 ledger row itself, which claims the
      gotcha is outdated. P3.19 should resolve D8 on the
      specs/README.md/doc side, not by re-adding configuration code — sensor
      bring-up belongs to the P3.16 firmware.)
- [ ] P3.20 Gate: when 3a–3e are done and everything left needs the Pico W on
      a desk, write `READY_FOR_HW` listing exactly the Phase 4 tests and
      their pass/fail criteria.

## Phase 4 — Outer hardware loop (host-side; container cannot verify)

The container can *write* these files but only the host can *run* them. Each
item names what needs the Pico W plugged in.

- [ ] P4.1 `hw/serial_probe.py` (host, needs `pyserial`): flash a test sketch
      via `pico-arduino/flash.sh`, capture the USB serial port, assert boot
      banner, sensor frame streaming and framing.
- [ ] P4.2 `hw/ble_hid_probe.py` (host, needs `bleak` + the host's Bluetooth
      radio): automate scan/GATT/pairing/services — target `AC-BLE-01`,
      `AC-BLE-02`, `AC-BLE-03`.
- [ ] P4.3 `hw/ble_hid_probe.py` lifecycle part: latency/report-rate/
      reconnect/bond — `AC-BLE-04`, `AC-BLE-05`, `AC-BLE-06`, `AC-BLE-07`.
      Bond persistence (`AC-BLE-06`) answers `ble_hid.md` §5 open question 1.
- [ ] P4.4 Outer loop driver `ralph_hw.sh` + `HW_REPORT.md` protocol: run the
      inner loop until `READY_FOR_HW`, flash + probe, write `HW_REPORT.md`
      (pass/fail + captured logs), commit; `ralph.sh` clears `READY_FOR_HW`
      on its next start once `HW_REPORT.md` exists.
- [ ] P4.5 Manual checks: `AC-BLE-08` multi-OS smoke test and gesture feel
      tuning (`GAIN`, `JUMP_THRESHOLD`, `TOUCH_RELEASE_MS` — record final
      values back into `specs/hid_mapping.md` §3).
- [ ] P4.6 Capture real sensor frames on hardware and reconcile every fixture
      not marked `vendor`; specifically confirm the AirWheel counter
      behaviour (does a real capture cross 255→0 as the signed 8-bit model
      predicts, and do real counters reach ≥ 32 within one spin?) and
      re-author F14/F15 if reality disagrees.

## Phase 5 — MicroPython port (folder: `pico-python/`)

Platform verified from documentation (2026-11-04): Raspberry Pi's official
MicroPython for the Pico W supports Bluetooth LE via the `bluetooth` module.
See the status snapshot for the known gaps (hand-built HID service, ~512-byte
attribute table limit).

- [ ] P5.0 **GATE — verify on hardware before any build**: flash the current
      Raspberry Pi MicroPython image, confirm `import bluetooth` works on the
      Pico W and the version installed, and probe the attribute-table size /
      parsed HID report-map limit. If the gap list makes HID-over-GATT
      impractical on this firmware version, record a spec deviation and stop
      here (the Arduino implementation is the primary deliverable).
- [ ] P5.1 Port the Arduino implementation to MicroPython in `pico-python/`
      per AGENTS.md "To build", using the same specs as the contract
      (`I2C` transport via `machine.SoftI2C`/`I2C`, `bluetooth` BLE stack).
- [ ] P5.2 Parity tests: the same fixtures must produce the same canonical
      events and controller outputs as the Arduino implementation
      (`AC-MAP-09` applies to the port too — reuse `tests/` P3.1's
      driver-agnostic harness with a MicroPython-decoder adapter).

## Done

- P3.9 — Deviation D3 closed: the **Arduino** driver now wraps the AirWheel
  (rotation) counter the same way the Python driver has since P3.4 (commit
  `885475f`), so both drivers emit identical events across the 255→0
  counter wrap AC-MAP-09 requires. Parts:
  - `arduino/Skywriter/skywriter.cpp` airwheel branch rewritten as the
    Python reference: the counter is a free-running 8-bit byte, so the first
    AirWheel-valid frame after driver start or after any stretch of
    AirWheel-invalid frames is a **silent baseline** (`airwheel_counter_valid`
    flag — the C++ stand-in for the Python `_lastrotation = None` sentinel;
    cleared again by every frame without valid AirWheel data), and
    consecutive frames compare with the **signed 8-bit difference**
    `d = ((cur - last + 128) % 256) - 128` steps × 11.25° (the old
    unsigned `(cur - last) / 32.0` arithmetic read a 255→0 wrap as a full
    -252-step reversal that the `|delta| < 0.5` guard then silently dropped).
    Degree accumulation (`rotation`) mirrors the Python driver exactly:
    float degrees, emitted only when non-zero, accumulated and clamped to
    0…1000.
  - `skywriter.h`: `onAirwheel` callback signature `void (*)(int)` →
    `void (*)(float)` and `int rotation` → `float rotation = 0.0f`. Why the
    public-signature change is part of the parity fix: one sensor step is
    exactly 11.25°, so whole-integer degrees cannot represent a 1-step delta
    (the Python driver's float degrees are the canonical form in
    hid_mapping.md §2; an int-carrying callback would truncate 11.25° → 11°
    and break AC-MAP-09 the moment any fixture carries an odd step count).
    No shipped example passes a real handler (NeoPaint's is commented out)
    and all three example sketches still compile.
  - Replay harness: `tests/cpp/host_decoder_main.cpp` prints the float
    degrees (`EV AIRWHEEL %%.2f` — exact for 11.25°-quantized values) and
    `tests/adapters_cpp.py` parses them as floats, so the C++ canonical
    `airwheel` records now match the Python driver's float degrees within
    the suite's 1e-6 tolerance. Fresh state: one fresh process per scenario
    already gives fresh decoder state, and the shim's docstring now notes
    explicitly that the new baseline flag + `rotation` start pristine — the
    C++ counterpart of the Python adapter's explicit
    `sky.rotation = 0.0; sky._lastrotation = None` reset.
  - Spec/manifest/ledger closure (self-arming flip): the `omit_pending` D3
    annotation dropped from the `airwheel_wrap` scenario in
    `specs/fixtures/manifest.json` — its +45° expectation is now a hard
    assertion on **both** drivers; D3 row removed from
    `specs/README.md`; hid_mapping.md §2 parenthetical now records the fix
    in both drivers; the open-deviation enumerations updated in
    `tests/README.md` and the docstrings of `tests/test_harness.py` /
    `tests/test_scenarios.py` (now "D4, D7–D9").
  - Verified against the compiled host decoder: F14 (counter 0xFE) is a
    silent baseline, F15 (0x02) yields `EV AIRWHEEL 45.00` exactly once.
  `bash run_tests.sh` green 4/4; 29 pytest tests (same count — the
  `airwheel_wrap` tolerance hardened into an assertion, no test added).
- P3.8 — Deviation D2 closed as *already resolved* (commit `4eea275`): the
  out-of-bounds `setRuntimeParam` write described by the row does not exist in
  the current tree, so there was nothing in the code to change. How the
  discrepancy arose: the offending code (the four `Set_Runtime_Parameter`
  (`0xA2`) configuration commands with 15-element arrays copied into a
  16-step transmission loop over the I2C (Inter-Integrated Circuit) bus) was
  introduced in commit `e781528` (pre-loop host adaptation of the shared
  Arduino library) and removed again by commit `c6aecc7` ("restore master
  branch examples. keep examples as clean originals" — the pre–Phase 2 revert
  of `arduino/Skywriter/` to the pristine upstream library); the acceptance
  specs were committed at `1c0b12a` while the adapted library was still in the
  tree, which is where the D2 evidence ("15 initializers vs loop bound 16",
  verified verbatim at `e781528`) came from. Verification against the current
  tree: no `setRuntimeParam`/`cmdAirWheel` anywhere in `arduino/`,
  `pico-arduino/`, `library/`, `tests/`; the C++ driver's only per-index
  write loops are safely bounded (touch bit scan over a 16-bit word; `poll()`
  payload read capped by the 32-byte I2C request into `command_buffer[32]`,
  terminator at index ≤ 28). The row was removed from `specs/README.md`
  (the harness's `tests/deviations.py` treats every remaining row as live and
  open, so a void row would poison the single source of truth);
  `tests/README.md`'s enumeration gained the closure note; the open-deviation
  docstring lists in `test_harness.py` / `test_scenarios.py` became
  "D3, D4, D7–D9". No fixture annotation referenced D2, so nothing needed
  re-arming. The functional residue was re-homed, not lost: sensor
  configuration now belongs to the P3.16 firmware's sensor stack (exact
  15-byte payload caution added there, guarding the old 16-vs-15 bound), and
  P3.19 records the same history (post-revert, the AGENTS.md "begin() does
  not send SW_SET_RUNTIME" gotcha is accurate again; the stale side is the D8
  ledger row). `bash run_tests.sh` green 4/4; 29 pytest tests.
- P3.7 — Deviation D7 closed for the **Python** driver (commit `deb1c0b`):
  gesture attributes now travel with every gesture event, and the ledger row
  narrows to the Arduino driver alone (fix item P3.11 closes it there).
  `library/skywriter/__init__.py` now decodes the full 32-bit little-endian
  GestureInfo word in `_handle_sensor_data` (Interface.pdf §4.5 Table 4-10)
  and exposes the attributes as module state right before dispatching the
  flick/garbage/circle callbacks, for handlers to read like the x/y/z
  position values: `gesture` = code, bits 0–7 (this global existed before
  but was never actually written — the dispatch loop's local of the same
  name shadowed it; the loop variable is renamed), `gesture_class` =
  bits 12–15 (0 none/garbage, 1 flick, 2 circle), `gesture_edge` =
  bit 16 (the edge-flick flag). Recognition-in-progress frames
  (bit 31, code 0) still emit nothing — already the code-0 behaviour and
  hard-asserted by the `gesture_in_progress` scenario (spec §2 sentence
  verified, no code change needed). Manifest: the keys_pending annotations
  on the six gesture scenarios narrowed to `drivers: ["cpp"]`, which makes
  the Python class/edge values hard assertions — verified: flicks carry
  class 1 / edge false, garbage class 0, circles class 2, and the edge-flick
  fixture F04 (word 03 10 01 00) carries edge **true**; F02's reserved bit
  17 stays ignored. Harness: `tests/adapters_python.py` snapshots the three
  globals onto every gesture record and resets them per replay;
  `tests/canonical.py` emits code/class/edge from the records (the code
  now comes from the driver's wire decode, not from the callback identity —
  the FLICK_CODES/CIRCLE_CODES name→code maps became redundant and were
  removed); `tests/test_harness.py`'s flick pin asserts the new record
  shape. Wrong class/edge values fail the compare for either driver;
  absence is tolerated historically only for `cpp` while D7 stands.
  `bash run_tests.sh` green 4/4; 29 pytest tests (same count — the existing
  assertions tightened, no test added).
- P3.6 — Deviation D6 closed (commit `1164b91`): `_handle_firmware_info` in
  `library/skywriter/__init__.py` now treats **only** `FwValid == 0xAA` as a
  valid firmware-version report. Previously every status byte other than the
  two known failure values (0x00 empty, 0x0A invalid image / failed update)
  was silently accepted — a corrupted or unexpected value such as 0x55 would
  have been read as working firmware and 120 arbitrary bytes printed as a
  "version string". Fixed per Interface.pdf §4.3 Table 4-6 (the datasheet
  defines exactly those three values): 0xAA accepted (the version string is
  only read then), 0x00 / 0x0A keep their existing error messages, undefined
  values raise "Unknown GestIC Library status (FwValid 0x..)". Verified by
  new `tests/test_firmware_info.py` — 7 parametrized tests: the recorded
  F17 fixture payload (0xAA) is accepted, both defined failures raise their
  documented errors, and undefined values 0x01 / 0x55 / 0xAB / 0xFF raise.
  Ledger: D6 row removed from `specs/README.md`; F17's manifest note and
  `tests/README.md` updated. `bash run_tests.sh` green 4/4; 29 pytest tests
  (22 + 7). No open deviations reference this handler; P3.11b still owns
  surfacing the control frame as a canonical record (NUL-stripped version
  string included).
- P3.5b — Deviation D10 closed (commit `a716598`): the Python driver no
  longer silently discards circle gestures. `library/skywriter/__init__.py`
  now dispatches wire codes 6/7 from `_handle_sensor_data` to a handler
  registered through the new `@skywriter.circle()` decorator (the direction
  arrives as the string `'clockwise'` / `'counter-clockwise'`; the previously
  dead `_on_circle = {}` registry became a single callable like
  `_on_garbage`). `library/test.py` registers a circle handler too, proving
  the decorator triggers the full setup() handshake. Sensor constraint noted
  on the decorator: the GestIC library recognizes circles only with AirWheel
  disabled (Interface.pdf §4.5 Table 4-10 and the Table A-3 vendor trace
  "Circle Gesture not recognized because AirWheel is On"), and the default
  setup() enables AirWheel — so circle events are dormant in the default
  configuration; the §6 volume rows stay with the mapping engine (P3.15).
  Fixture corpus: new frames `F21_circle_cw.hex` / `F22_circle_ccw.hex`
  (vendor-pattern provenance — the Table A-3 circle trace itself shows a
  code-0 word because AirWheel was on in that session, so the recognized
  words `06 20 00 00` / `07 20 00 00` are constructed from the Table 4-10
  GestureInfo encoding: bits 0–7 = code, bits 12–15 = class 2) with
  scenarios `circle_clockwise` / `circle_counter_clockwise`. These are the
  first frames with the AirWheel-disabled output mask (`0x0003`, bit 3 off);
  fields before AirWheelInfo keep their fixed offsets, so the decoders'
  indexing stays valid — documented in `specs/fixtures/README.md` ("Shorter
  frames"). Manifest expectations hard-assert `{"event": "gesture",
  "code": 6|7}` on **both** drivers (the C++ driver already dispatched
  circles via `onGesture(code)`; `tests/canonical.py` gained a
  `CIRCLE_CODES` mapping for the Python adapter's direction strings), with
  class/edge still gated by D7. Ledger: D10 row removed from
  `specs/README.md`. `bash run_tests.sh` green 4/4; 22 pytest tests.
- P3.5 — Deviation D5 closed (commit `3cdac11`): `_handle_sensor_data` in
  `library/skywriter/__init__.py` now dispatches the registered `garbage()`
  callback (as `callable(_on_garbage)`, mirroring the flick dispatch) when
  the sensor reports gesture wire code 1. Previously the branch matched
  code 1 in the `gestures` list and then dropped it — the only dispatched
  kind was `flick` — so a handler registered via the `@skywriter.garbage()`
  decorator could never run. Verified end-to-end by feeding the recorded
  frame `F06_garbage_gesture.hex` through the real `_handle_sensor_data`
  with a registered capture callback (it fired exactly once). Manifest:
  the `garbage_gesture` scenario dropped its `omit_pending D5` annotation,
  so its `{"event": "gesture", "code": 1}` expectation is now hard-asserted
  on Python with no tolerance left (class/edge remain gated by D7).
  Ledger: D5 row removed from `specs/README.md`. `bash run_tests.sh`
  green 4/4; 22 pytest tests. Discovered while closing D5: circle gestures
  (codes 6/7) are silently discarded the same way and the `_on_circle`
  registry is dead code — recorded as deviation D10 + work item P3.5b.
- P3.4 — Deviation D3 closed for the **Python** driver (commit `885475f`):
  `library/skywriter/__init__.py` now computes the AirWheel rotation delta
  as a signed 8-bit difference,
  `d = ((cur - last + 128) % 256) - 128` steps × 11.25°, so the counter
  wrap 255→0 counts as +1 step (previously the unsigned `(cur - last)/32`
  produced −255 steps across a wrap, which the old `|delta| < 0.5` guard
  silently dropped — one full spin elegantly vanished). The decoder also
  re-baselines silently: `_lastrotation` starts as `None` and is reset to
  `None` on any frame without valid AirWheel data, so the first valid
  frame after a gap only records the reference (a hand re-entering the
  field cannot be read against a stale counter). Verified against the
  self-arming corpus: `airwheel_wrap` (F14/F15) now hard-asserts +45° on
  Python, `airwheel_quarter_turn_cw` and `touch_with_position_and_airwheel`
  unchanged. `omit_pending` on `airwheel_wrap` narrowed to `["cpp"]`; the
  D3 ledger row in `specs/README.md` narrowed to the Arduino driver
  (P3.9 will close it the same way; its item text now spells out the
  steps).
- P3.14a — Airwheel baseline rule settled (commit `885475f`, together
  with P3.4 it was entangled: the settled rule is what makes the P3.4
  acceptance test green). Decision: **the first AirWheel-valid frame
  after driver start, or after any stretch of AirWheel-invalid frames,
  is a silent baseline** — the counter is free-running, so a fresh frame
  cannot be read against a stale reference. Contract sentence added to
  `specs/hid_mapping.md` §2 (build-mode correction; the two manifest
  expectations that motivated this item now agree). Fixture corpus: new
  frame `F20_airwheel_baseline00.hex` (counter 0x00, synthetic) is
  prepended to the `touch_with_position_and_airwheel` scenario so F18's
  +90° expectation survives the rule; manifest emission noted and its
  scenario notes updated.
- P3.3 — Deviation D1 closed (commit `c09981f`): `_do_poll()` in
  `library/skywriter/__init__.py` now strips the 4-byte frame header (size,
  flags, sequence, message ID) before dispatching, so
  `_handle_sensor_data` / `_handle_status_info` / `_handle_firmware_info`
  receive exactly the payload their field offsets assume. Before the fix
  every decoded value was read 4 bytes into the header (positions from the
  size/flags words, gestures from the timestamp, …) — the regression from
  commit `e7e2399` (removal of the old `data.pop(0)` header-stripping).
  Why the whole fixture suite had been blind to it: the replay adapters feed
  the payload directly and never exercise `_do_poll`. Hence the new
  `tests/test_do_poll.py`: it drives the driver's real `_do_poll()` code
  path with recorded fixture frames (F01 sensor data, F16 status ack, F17
  fw version) and pins the payload-dispatch contract, plus an end-to-end
  position-decode check (F01 → x/y/z move callback values). Ledger row D1
  removed from `specs/README.md`; stale D1 references updated in
  `specs/fixtures/manifest.json`, `tests/README.md`,
  `tests/adapters_python.py`, `tests/test_harness.py` and
  `tests/test_scenarios.py`. `bash run_tests.sh` green 4/4; pytest corpus
  now 22 tests.
- P3.1 — fixture-replay harness skeleton landed (this commit): `tests/` is a
  pytest package picked up automatically by `run_tests.sh`'s existing
  `fixture_replay` check. Parts (see `tests/README.md` for the full map):
  - `runner.py` — driver-agnostic runner: manifest scenario → frames replayed
    in order into a **fresh decoder state**; `time_gap_ms` is applied on a
    **VirtualClock** (`virtual_clock.py`) with zero wall-clock sleeping, once
    between consecutive frames and once after the last frame so a later
    mapping adapter can evaluate timed outcomes (release-by-silence).
  - `adapters_python.py` — Python driver adapter: imports
    `library/skywriter/__init__.py` with mocked hardware (same verification as
    `library/test.py`), registers capture handlers on the driver's own
    callback globals (bypassing `setup()` so no bus thread starts), mirrors
    `_do_poll`'s message-ID dispatch and feeds the **payload** (frame minus
    the 4-byte header) per the manifest convention, then records whatever the
    decoder emits. The driver's wall-clock `millis()` is redirected onto the
    VirtualClock so touch repeat-limiting is simulated time.
  - `adapters_cpp.py` + `cpp/` — C++ decoder adapter: the *real* Arduino
    driver (`arduino/Skywriter/skywriter.cpp`) compiled as a host program
    behind minimal `Arduino.h`/`Wire.h` shims (`tests/cpp/`), driven through
    its genuine `poll()` code path once per fed frame. One process per
    scenario keeps decoder state fresh; the binary is hash-cached in
    `tests/build/` (matches the existing `build/` .gitignore rule) so
    repeated runs don't recompile.
  - `test_harness.py` — 11 meta-tests: manifest/frame integrity, every
    scenario replays on both adapters, fresh-state identity on reruns,
    simulated-gap accounting, VirtualClock non-sleeping, plus today-true
    plumbing pins (F01 position values on both drivers, flick W→E dispatch,
    tap dispatch). Assertions deliberately cover only behaviour that already
    matches the spec — per-scenario spec assertions (AC-MAP-01…06) land with
    P3.2 + the decoder fixes P3.3–P3.11, keeping `run_tests.sh` green while
    each fix flips one more expectation from unchecked to verified.
- Environment note discovered by P3.1 (this commit): the Alpine container has
  **no host C++ compiler and no sudo/root** (`g++`, `clang++`, apk tools all
  absent — only the ARM cross-compiler inside the rp2040 arduino core is
  shipped, which cannot build host binaries). Resolved without root:
  `pip install --user --break-system-packages ziglang` — the `ziglang` PyPI
  wheel is a complete C++ toolchain (`python3 -m ziglang c++ …`) and works on
  this musl image (verified: compiled a test binary, exit code checked).
  `tests/adapters_cpp.py` resolves the compiler as `g++`/`c++` → `zig` on
  PATH → `python3 -m ziglang c++`, and fails loudly with install instructions
  if none is found (never a silent skip). The Dockerfile now also installs
  `g++ musl-dev` for future image rebuilds; **not yet verified by an actual
  image rebuild** (docker is host-only) — spread this verification to the
  next host-side docker-touching session. The pip ziglang install is
  user-local and dies with the current container; until the image is
  rebuilt, a fresh container needs the `pip install` above before
  `run_tests.sh`.
- P3.2 — structured expectation grammar landed (this commit).
  `specs/fixtures/manifest.json` bumped to schema `skywriter-fixtures/v2`:
  every scenario's `expect.canonical` is now an event list in the
  `tests/canonical.py` grammar (the canonical sensor-event model of
  `specs/hid_mapping.md` §2, plus the two control messages), and
  `expect.hid` is the scenario's controller output as `tests/hid_grammar.py`
  records (mouse move/button/wheel/click, keyboard Page Up/Down, consumer
  media usage IDs). Prose remains only in `note`/`desc` fields — nothing in
  the manifest is matched free-text any more. Parts:
  - `tests/deviations.py` — parses the "Known driver deviations" table in
    `specs/README.md` (single source of truth) so test code and fixture
    annotations never second-guess which deviations are open, or for which
    driver.
  - `tests/canonical.py` — native-records → canonical-event converters for
    both adapters, the documented value tolerances (±4 raw sensor units for
    the Python driver's 4-decimal rounding — the only tolerated
    representation difference in the whole suite), expectation compare with
    `omit_pending` / `keys_pending` deviation gating, mirrored
    *realization* checks, and cross-driver parity diffing (AC-MAP-09).
  - `tests/hid_grammar.py` — schema for the HID outcome records per
    `specs/hid_mapping.md` §3–§6, validated for every scenario now; the
    replay-assertion of those records arms with the mapping-engine items
    P3.12–P3.15 (the manifest is their machine-readable acceptance data).
  - `tests/test_scenarios.py` — 7 new tests: manifest lint (structured
    schema, annotation ↔ ledger consistency incl. affected-driver
    cross-checks), per-scenario × per-driver canonical expectation compare,
    deviation-realization checks (an annotated omission must really happen —
    a fix that lands without removing the specs/README.md row fails with
    exact instructions), HID-record well-formedness, and per-scenario
    cross-driver parity with one-sided omissions attributable only to
    exactly-that-driver annotations. With the 11 P3.1 meta-tests: 18 pytest
    tests green; `bash run_tests.sh` passes 4/4 checks.
  - Self-arming mechanism (the point of the whole exercise): the known-red
    decoder defects are encoded as *tolerances tied to the ledger*, never as
    weakened expectations — e.g. the `garbage_gesture` scenario tolerates the
    Python driver omitting the garbage event only while D5 stands and
    *asserts* the omission still reproduces; when P3.5 lands and the D5 row
    is removed, the same scenario hard-asserts the event with no weakening
    left anywhere (only the row + annotation removal, which the lint forces).
  - Ledger addition (discovered during migration): **D9** — neither driver
    surfaces `System_Status` (`0x15`) / `Fw_Version_Info` (`0x83`) control
    frames as records, so the `status_ack` / `fw_version_valid` scenario
    expectations are annotated pending D9. New fix item: P3.11b.
  - Discovered, recorded as work items: **P3.14a** — the `airwheel_wrap`
    (first-frame-silent baseline at F14) and `touch_with_position_and_airwheel`
    (F18 counter 0x08 → +90° from a fresh state) expectations imply
    contradictory airwheel baseline rules; settle before P3.14. **P3.15b** —
    fixture-corpus gaps: no real pointer-movement scenario, no auto-scroll /
    edge-and-keyboard-area / vertical-flick fixtures. Also: the v1 prose
    "mouse delta" on F18 is superseded by a spec-correct structured record —
    per `hid_mapping.md` §3 rule 4 a single first valid position only sets
    the cursor baseline (manifest note reflects this).
  - Environment note: this container still has the user-local `ziglang`
    C++ toolchain from P3.1 (used by the host-decoder adapter); a fresh
    container needs `pip install --user --break-system-packages ziglang`
    again until the image rebuild is verified host-side.
- Phase 0 — repository hygiene: clean tree, sandbox image + loop volumes
  ready, model subscriptions visible to the agent.
- Phase 1 — acceptance specs written and committed (`1c0b12a`):
  `specs/README.md`, `specs/ble_hid.md`, `specs/hid_mapping.md`,
  `specs/fixtures/` (19 frames + `manifest.json`, all validated: size bytes
  consistent, references resolve).
- Phase 2 harness files W1–W4 (commit `065a27f`): `PROMPT.md`, `ralph.sh`,
  `run_tests.sh`, `.gitignore` entries.
- Loop-harness corrections (this commit): model pinned to
  `opencode-go/glm-5.3-flash`; stale-stop-marker protocol in `ralph.sh`;
  control-volume fix for arduino-cli library installs in the Dockerfile;
  spec/build-mode corrections listed in the status snapshot.
- W6 — firmware-compile check fully green (2026-11-04): `Adafruit NeoPixel`
  1.15.5 installed into the `skywriter-arduino` volume,
  `ARDUINO_DIRECTORIES_USER=/home/dev/.arduino15` verified in the container
  (note: it points at the user directory root; arduino-cli appends
  `libraries/`). Host needs its own library install if tests run there.
- W5 — Python unit tests fully green (this commit): `library/test.py` now
  uses `unittest.mock` from the standard library (the third-party `mock`
  import is gone), and the fake I2C bus answers the driver's startup
  handshake with the recorded `specs/fixtures/F16_status_ack_a2.hex`
  acknowledge frame, so the fixture directory stays the single source of
  truth. The test stays strictly offline: it additionally asserts that
  `setup()` writes the four sensor-configuration commands, reads the status
  frame back four times, starts the background polling thread and stops it
  cleanly, and that the `@skywriter.airwheel()` / `@skywriter.move()`
  callbacks register. `bash run_tests.sh` is now green end-to-end.
  Discovered while writing it (recorded here for whoever patches the test
  next): with mocked module tables, `import RPi.GPIO as GPIO` binds the
  child attribute of the fake `RPi` parent module — the parent mock must
  carry the same object as `sys.modules['RPi.GPIO']`, or the driver's module
  level `GPIO.RPI_REVISION` check silently sees a fresh unmatched Mock and
  picks the wrong I2C bus number.
- `run_tests.sh` comment for the Python unit test updated to reflect green
  status (W5 row removed; details live here).
- W7 — loop dry-run verified (this commit). Note on how: `docker run` cannot
  be executed *from inside* the container (docker is a host tool), so the
  raw `RALPH_MAX_ITER=1 docker run` command was exercised in two halves:
  - Live half, already observable from inside: the loop is running these very
    iterations — agent commits land (`0847dc2` made by iteration 001) and the
    per-iteration logs land in `logs/ralph-N01-*.log`.
  - Mechanism half, verified by driving `bash ralph.sh` itself against a fake
    `opencode` agent directory in a throwaway git clone (`/tmp/w7-dryrun`),
    with `RALPH_MAX_ITER` budget: (a) uncommitted agent work triggers the
    automatic snapshot commit; (b) a `DONE` marker stops the loop after one
    iteration of a 5-iteration budget; (c) `READY_FOR_HW` stops the loop, and
    on restart with `HW_REPORT.md` present the marker is consumed and the
    loop continues; (d) a stale `DONE` at start exits immediately without
    running the agent; (e) a failing `git push` is tolerated with a clear
    message. No friction found; no script changes needed.
- W7b (host note, non-blocking): the loop is currently running on local
  branch `ralph-dry-run` (checked out from `pico-ble` by the host just
  before the dry-run iterations), so the end-of-run `git push` fails with
  "no upstream branch" and commits stay only on the bind mount. Nothing to
  fix in `ralph.sh` (`git push` failure is already tolerated); the host
  should either merge `ralph-dry-run` into `pico-ble` when the dry-run
  phase is complete, or run
  `git push --set-upstream origin ralph-dry-run` once.
- P3.1 — fixture-replay harness skeleton landed (this commit): `tests/` is a
  pytest package picked up automatically by `run_tests.sh`'s existing
  `fixture_replay` check. Parts (see `tests/README.md` for the full map):
  - `runner.py` — driver-agnostic runner: manifest scenario → frames replayed
    in order into a **fresh decoder state**; `time_gap_ms` is applied on a
    **VirtualClock** (`virtual_clock.py`) with zero wall-clock sleeping, once
    between consecutive frames and once after the last frame so a later
    mapping adapter can evaluate timed outcomes (release-by-silence).
  - `adapters_python.py` — Python driver adapter: imports
    `library/skywriter/__init__.py` with mocked hardware (same verification as
    `library/test.py`), registers capture handlers on the driver's own
    callback globals (bypassing `setup()` so no bus thread starts), mirrors
    `_do_poll`'s message-ID dispatch and feeds the **payload** (frame minus
    the 4-byte header) per the manifest convention, then records whatever the
    decoder emits. The driver's wall-clock `millis()` is redirected onto the
    VirtualClock so touch repeat-limiting is simulated time.
  - `adapters_cpp.py` + `cpp/` — C++ decoder adapter: the *real* Arduino
    driver (`arduino/Skywriter/skywriter.cpp`) compiled as a host program
    behind minimal `Arduino.h`/`Wire.h` shims (`tests/cpp/`), driven through
    its genuine `poll()` code path once per fed frame. One process per
    scenario keeps decoder state fresh; the binary is hash-cached in
    `tests/build/` (gitignored) so repeated runs don't recompile.
  - `test_harness.py` — 11 meta-tests: manifest/frame integrity, every
    scenario replays on both adapters, fresh-state identity on reruns,
    simulated-gap accounting, VirtualClock non-sleeping, plus today-true
    plumbing pins (F01 position values on both drivers, flick W→E dispatch,
    tap dispatch). Assertions deliberately cover only behaviour that already
    matches the spec — per-scenario spec assertions (AC-MAP-01…06) land with
    P3.2 + the decoder fixes P3.3–P3.11, keeping `run_tests.sh` red→green
    per fix, never red-by-design.
- Environment note discovered by P3.1 (this commit): the Alpine container has
  **no host C++ compiler and no sudo/root** (`g++`, `clang++`, apk tools all
  absent — only the ARM cross-compiler inside the rp2040 arduino core is
  shipped, which cannot build host binaries). Resolved without root:
  `pip install --user --break-system-packages ziglang` — the `ziglang` PyPI
  wheel is a complete C++ toolchain (`python3 -m ziglang c++ …`) and works on
  this musl image (verified: compiled a test binary, exit code checked).
  `tests/adapters_cpp.py` resolves the compiler as `g++`/`c++` → `zig` on
  PATH → `python3 -m ziglang c++`, and fails loudly with install instructions
  if none is found (never a silent skip). The Dockerfile now also installs
  `g++ musl-dev` for future image rebuilds; **not yet verified by an actual
  image rebuild** (docker is host-only) — spread this verification to the
  next host-side docker-touching session. The pip ziglang install is
  user-local and dies with the current container; until the image is
  rebuilt, a fresh container needs the `pip install` above before
  `run_tests.sh`.
