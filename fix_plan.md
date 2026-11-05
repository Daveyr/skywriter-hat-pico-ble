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
- [ ] W7 Dry-run the loop: `RALPH_MAX_ITER=1 docker run … skywriter-dev
      bash ralph.sh` — confirm the agent commits, logs land in `logs/`, marker
      files stop the loop. Fix any friction found.

## Phase 3 — Implementation (order is deliberate: test harness first)

Per AGENTS.md "To build": Pico/Pico W firmware lives in `pico-arduino/`.
Library fixes to the existing driver go to `arduino/Skywriter/` (the shared
library both use). Python driver fixes go to `library/`.

### 3a — Replay harness (must exist before decoder/fix items)

- [ ] P3.1 Replay test harness skeleton `tests/`: a driver-agnostic runner
      that loads `specs/fixtures/manifest.json`, plays each scenario's frames
      in order into a **fresh decoder state**, uses a **virtual clock** for
      `time_gap_ms` (no sleeping), and can feed the records to either the
      Python driver adapters or a C++ decoder compiled for the host. Picked
      up automatically by `run_tests.sh`.
- [ ] P3.2 Structured expectation grammar: replace the manifest's prose
      `expect` fields with a machine-checkable format (structured event list,
      e.g. `{"event": "airwheel", "degrees": +45}`, plus per-scenario HID
      outcome records) and migrate every scenario to it. Manifest-style prose
      stays only as comments. This is what makes the harness from P3.1 able
      to assert, instead of matching free-text like `move(0.0076, …)`.

### 3b — Python driver defects (`library/skywriter/__init__.py`) — one per item

- [ ] P3.3 Deviation D1 — off-by-4 header regression (commit `e7e2399`):
      slice the 4-byte header off before dispatch so payload offsets line up.
- [ ] P3.4 Deviation D3 — AirWheel wrap: signed 8-bit delta
      (`d = ((cur - last + 128) % 256) - 128` steps, degrees = `d * 11.25`)
      instead of `(cur - last)/32.0` with the `< 0.5` drop guard.
- [ ] P3.5 Deviation D5 — dispatch `_on_garbage` for gesture code 1 (today
      the gesture branch ignores it).
- [ ] P3.6 Deviation D6 — firmware version valid only when `FwValid == 0xAA`.
- [ ] P3.7 Deviation D7 — carry gesture attributes (class bits 12–15, edge
      flick bit 16, in-progress bit 31) into the decoded events.

### 3c — Arduino driver defects (`arduino/Skywriter/skywriter.cpp`) — one per item

- [ ] P3.8 Deviation D2 — `setRuntimeParam` writes one byte past the 15-byte
      command arrays (loop bound 16 vs. array length 15).
- [ ] P3.9 Deviation D3 — same signed 8-bit AirWheel wrap fix as P3.4.
- [ ] P3.10 Deviation D4 — touch decode early-`return`s after the first (and
      only highest-bit) touch; must process every set bit and continue
      decoding AirWheel/xyz in the same frame.
- [ ] P3.11 Deviation D7 — same gesture-attribute fix as P3.7.

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
- [ ] P3.15 Full §6 default mapping table as the single implementation table
      ("the table IS the implementation"), incl. garbage → nothing, reserved
      doubletap east/west → nothing, and media/consumer rows. Target
      `AC-MAP-05`, `AC-MAP-06`.

### 3e — BLE HID firmware (`pico-arduino/`) — software written here, verified
in Phase 4 on hardware

- [ ] P3.16 Firmware sketch: sensor stack + composite Bluetooth LE HID device
      bring-up per `specs/ble_hid.md` §3–4 — link `MouseBLE` + `KeyboardBLE`
      and call exactly **one** `begin()`, device name `Skywriter HID`,
      HID-class appearance. Target `AC-BLE-01`, `AC-BLE-02` (composite
      Report Map). Compiles in-container; RF behaviour verified in Phase 4.
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
      `INPUT_PULLUP`.
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
