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
   `specs/README.md`. 29 pytest tests; `run_tests.sh` green 4/4.
   Update (2026-11-05, P3.11 commit): deviation D7 is closed — the Arduino
   driver now decodes the full 32-bit GestureInfo word, so every gesture
   expectation (code + class + edge-flick flag) is a hard assertion on both
   drivers; the `keys_pending` annotations and the D7 ledger row are gone.
   29 pytest tests; `run_tests.sh` green 4/4.
   Update (2026-11-05, P3.11b commit): deviation D9 is closed — the
   System_Status (0x15) and Fw_Version_Info (0x83) control frames are
   canonical events (`system_status` / `firmware_info`) on both drivers, the
   `status_ack` / `fw_version_valid` expectations are hard assertions with
   the `omit_pending` annotations gone (and the stale `msg_id: 170` value
   corrected to the datasheet's 0xA2 = 162 in the act), and the Arduino
   `poll()` now reads whole frames (132-byte requests) so the 120-byte
   version string arrives complete. 30 pytest tests; `run_tests.sh` 4/4.
   Update (2026-11-05, P3.11c commit): the Raspberry Pi Python driver now
   sizes its I2C reads from the frame's Size field — long control frames
   (132-byte Fw_Version_Info) are fetched in chunked continuation reads
   instead of being truncated at the fixed 26-byte read; 4 new `_do_poll`
   pins, 34 pytest tests; `run_tests.sh` 4/4. New open item P3.11d (the
   polling thread stops on the first I2C error).
   Update (2026-11-05, P3.11d commit `8d4081d`): the background poll
   thread no longer stops on the first I2C error — the documented
   10-error grace actually works now, past it the raise ends the thread
   with a visible traceback (the design decision is recorded in the Done
   entry), and the transfer (TS) pin release moved into a `try/finally`.
   Closed as the last 3c item; 41 pytest tests; `run_tests.sh` 4/4.
   Update (2026-11-05, P3.12 commit `13f1698`): the mapping engine exists
   (`pico-arduino/SkywriterHID/`) and its pointer model —
   normalization/`GAIN`, sign, jump rejection + re-baseline, lift-off
   gating, report cadence — is replay-asserted end-to-end through the real
   C++ driver (the whole firmware signal chain in one host binary); new
   fixtures F24/F25 + scenarios `pointer_move` (one coalesced +11/−2 move,
   exercising GAIN, sign and cadence) and `pointer_lift_off_rebaseline`
   (150 ms silence → fresh baseline, no cursor flight); `expect.hid` is
   now a hard assertion for the eight armed scenarios, with the
   touch/AirWheel/gesture scenarios attributed to P3.13–P3.15 by a lint.
   Update (2026-11-05, P3.13 commit `3c3e1de`): the touch semantics are
   live — see the P3.13 Done entry; 54 pytest tests; `run_tests.sh` 4/4.
   Update (2026-11-05, P3.14 commit `95ad4c2`): the §5 AirWheel semantics
   are live in the mapping engine — 11.25°-quantized scroll notches, sign,
   fractional accumulator, immediate un-coalesced emission, lift-off
   reset; the three AirWheel scenarios are hard-asserted end-to-end
   (AC-MAP-04 + the touch+position+airwheel row of AC-MAP-06); see the
   P3.14 Done entry. 61 pytest tests; `run_tests.sh` 4/4.
   Update (2026-11-05, P3.15 commit `5dab347`): the FULL §6 default
   mapping profile is live in the mapping engine as the single
   implementation table — flick/circle consumer rows, tap(north/south)
   keyboard Page Up/Down, doubletap(north/south) media track-skip, the
   reserved/garbage → nothing rows pinned silent, and the §6 hold
   auto-scroll (touch(north/south) → wheel −1/+1 notch per 100 ms while
   held, first notch at hold start); every fixture scenario is now
   replay-asserted on the engine (MAPPING_ENGINE_PENDING empty), the five
   gesture scenarios armed (AC-MAP-05 closed offline). 69 pytest tests;
   `run_tests.sh` 4/4.
   Update (2026-11-05, P3.16 commit `f5c8316`): the first firmware sketch
   exists — `pico-arduino/SkywriterController/` brings up the sensor stack
   (the four Set_Runtime_Parameter configuration commands sent by the
   firmware itself, 15 payload bytes each) and starts the composite BLE HID
   device (one `begin()`, device name `Skywriter HID`, HID-class
   appearance; AC-BLE-01/02 software side, static-pinned by 13 new
   source-level tests in `tests/test_firmware_sketch.py`) — the RF checks
   stay with Phase 4. New build truth recorded: BLE HID sketches need the
   arduino-pico core's `ipbtstack=ipv4btcble` ("IPv4 + Bluetooth") build
   option or the BTstack (Bluetooth) libraries are not linked at all —
   `flash.sh` and `run_tests.sh` now pass that FQBN variant and AGENTS.md's
   Environment section documents it; the Dockerfile additionally symlinks
   the `SkywriterHID` engine library into the Arduino user directory.
   82 pytest tests; `run_tests.sh` 4/4.
   Update (2026-11-05, P3.17 commit `445d843`): the connection
   life cycle is wired (§5/§6/§8, AC-BLE-03/07 software side) — battery
   refreshed to 100 % at connect through `PicoBluetoothBLEHID.setBattery`
   directly (the `MouseBLE.setBattery` wrapper is confirmed unusable),
   one neutral resync report per (re)connect, held buttons/scroll/media
   state released on link loss through a new public
   `SkywriterHIDMapper::disconnect()`, sensor events dropped while
   unconnected with a probe-evidence serial line, and advertising
   restarted inside the link-loss callback. Design constraint recorded:
   the Bluetooth stack's callbacks must never call the HID send API (its
   send busy-waits on the stack's own context — a send from a callback
   deadlocks); life-cycle work runs in loop(). Code-level bond-store
   truth for AC-BLE-06 established against core 6.3.1 — RAM-only (see the
   new item P3.17b). 95 pytest tests (82 + 13); `run_tests.sh` 4/4.
   Update (2026-11-05, P3.17b commit): the P3.17 RAM-only bond-store
   conclusion was WRONG — verified against the prebuilt core libraries
   and the shipped build config that the Bluetooth Security Manager uses
   the FLASH-BACKED device database (`le_device_db_tlv.c`, 16 persistent
   bond entries, wired at boot into a dedicated 8 KiB flash section
   appended after the firmware image), so no re-pair limitation needs
   documenting and no flash store needs wiring; the sketch comment,
   `specs/ble_hid.md` §5/§10 and the source-level pin were corrected, and
   P4.3's AC-BLE-06 check now verifies the expectation "reconnect WITHOUT
   re-pairing" on hardware.
   Update (2026-11-05, P3.18 commit `721e6b1`): move-report pacing is
    live: the engine's cadence is a runtime value re-targeted at the
    host's negotiated BLE connection interval (an HCI-tracked LE
    connection watcher; a [7.5, 15] ms connection-parameter request keeps
    the ≥ 60 Hz floor of AC-BLE-04 reachable; the disconnect drain resets
    it to the spec constant), and 4 new `PACE`-instruction mapper unit
    tests + 4 new source-level sketch pins assert the pacing and the
    never-lost delta accumulation. 103 pytest tests; `run_tests.sh` 4/4.
    The Phase-4 gates this item leaves open: AC-BLE-04's radio truth
    (≥ 60 Hz / < 100 ms end-to-end, P4.3) and open question 3 of
    `ble_hid.md` §10 (send-blocking behaviour on slow connection
    intervals — the measured pace and the host's parameter decision are
    what that probe must answer).
   Update (2026-11-05, P3.19 + P3.20 commits): deviation D8 is closed —
   the last open row — and the deviation ledger table is EMPTY: the
   AGENTS.md gotchas ("begin() sends no SW_SET_RUNTIME"; poll() resets
   the transfer pin to INPUT) are TRUE of the current tree, so the
   stale side was the ledger row itself and it was removed with a
   closure note (the Python gotcha's line references were refreshed to
   96/344); `bash run_tests.sh` stays green 4/4 with the empty table
   (no fixture annotation ever referenced D8, so nothing re-armed).
   With every Phase-3 item done, the P3.20 gate fired: the
   `READY_FOR_HW` marker is written in the repository root listing
   precisely the Phase-4 tests (P4.1–P4.6) and their pass/fail
   criteria — the outer hardware loop takes over from here.
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
- [x] P3.11 → done, moved to the Done section below.
- [x] P3.11b → done, moved to the Done section below.
- [x] P3.11c → done, moved to the Done section below.
- [x] P3.11d → done, moved to the Done section below.

### 3d — Mapping engine (`pico-arduino/`, verifiable with fixtures)

- [x] P3.12 → done, moved to the Done section below.
- [x] P3.13 → done, moved to the Done section below.
- [x] P3.14 → done, moved to the Done section below.
- [x] P3.15 → done, moved to the Done section below.
- [x] P3.15b → done, moved to the Done section below.

### 3e — BLE HID firmware (`pico-arduino/`) — software written here, verified
in Phase 4 on hardware

- [x] P3.16 → done, moved to the Done section below.
- [x] P3.17 → done, moved to the Done section below.
- [x] P3.17b → done, moved to the Done section below (resolved: no wiring
      needed and no deviation exists — the core's bond store IS
      flash-backed; the P3.17 RAM-only assumption came from the wrong
      config file).
- [x] P3.18 → done, moved to the Done section below.
- [x] P3.19 → done, moved to the Done section below.
- [x] P3.20 → done, moved to the Done section below (the `READY_FOR_HW`
      marker's Phase-4 test list is the ledger for the outer loop).

## Phase 4 — Outer hardware loop (host-side; container cannot verify)

The container can *write* these files but only the host can *run* them. Each
item names what needs the Pico W plugged in.

- [ ] P4.1 `hw/serial_probe.py` (host, needs `pyserial`): flash a test sketch
      via `pico-arduino/flash.sh`, capture the USB serial port, assert boot
      banner, sensor frame streaming and framing. Hardware-check notes:
      (P3.11b) the shared Arduino library's `poll()` now issues 132-byte I2C
      reads (its former 32-byte request truncated the firmware-version
      frame); the interface guide only promises that reading a whole message
      works, so confirm on hardware that sensor-frame streaming is unaffected
      when the host clocks more bytes than the current frame contains.
      (P3.11c) the Raspberry Pi Python driver now sizes its reads from the
      frame's Size field and fetches frames longer than the first 26-byte
      read with chunked continuation reads (26 + 32 + 32 + 32 + 10 for the
      132-byte Fw_Version_Info frame) while the transfer (TS) line is still
      asserted — confirm on a real sensor that the I2C buffer really
      continues across separate read transactions of one asserted transfer
      (the fixture replay only proves the driver-side arithmetic), and that
      the RPi Linux SMBus 32-byte single-call cap is respected.
- [ ] P4.2 `hw/ble_hid_probe.py` (host, needs `bleak` + the host's Bluetooth
      radio): automate scan/GATT/pairing/services — target `AC-BLE-01`,
      `AC-BLE-02`, `AC-BLE-03`.
- [ ] P4.3 `hw/ble_hid_probe.py` lifecycle part: latency/report-rate/
      reconnect/bond — `AC-BLE-04`, `AC-BLE-05`, `AC-BLE-06`, `AC-BLE-07`.
      Bond persistence (`AC-BLE-06`) answers `ble_hid.md` §5 open question 1.
      2026-11-05 P3.17b expectation note: the Core's bond store is verified
      FLASH-BACKED at the code level (see the P3.17b Done entry), so the
      probe should EXPECT "bonded host reconnects after a Pico W power
      cycle WITHOUT re-pairing" to PASS; record a spec-deviation row only
      if the radio behaves otherwise.
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

- P3.20 — the hardware gate fired (this commit): with 3a–3e complete and
  every remaining Phase-3 item closed, the `READY_FOR_HW` marker is written
  in the repository root (gitignored, never committed) listing exactly what
  the outer hardware loop (Phase 4, P4.1–P4.6) must test and each test's
  pass/fail criteria: the serial bring-up and framing probe (boot banner
  `SKYSTATE hid_started`/`sensor_ok`, 200 Hz streaming, the P3.11b 132-byte
  whole-frame reads and the P3.11c chunked-continuation reads on a real
  bus), the Bluetooth scan/GATT/pairing probe for AC-BLE-01/02/03, the
  life-cycle probe for AC-BLE-04 (latency < 100 ms, ≥ 60 reports/s, exact
  button transitions, `SKYSTATE pace` evidence), AC-BLE-05 (advertising
  within 5 s of link loss), AC-BLE-06 (bonded host reconnects after a power
  cycle WITHOUT re-pairing — expected PASS per the P3.17b flash-backed
  bond-store truth), AC-BLE-07 (events dropped while unconnected, one
  neutral resync on connect), the §10 open-question-3 send-block probe, the
  `ralph_hw.sh`/`HW_REPORT.md` protocol (P4.4), the manual multi-OS smoke +
  feel-tuning with the values recorded back into `hid_mapping.md` §3 (P4.5,
  AC-BLE-08), and real-frame reconciliation of the non-vendor fixtures with
  the AirWheel wrap question (P4.6). Nothing further is doable without the
  Pico W on a desk — end of this iteration set.
- P3.19 — deviation D8 closed and the deviation ledger is now EMPTY (commit
  `18ee099`). In plain language: the project's developer notes ("gotchas")
  had been flagged by the tracking ledger as possibly out of date — the
  ledger row claimed the Arduino driver's `begin()` DID send the sensor's
  four configuration commands at startup. The truth-check proved the notes
  are correct as written, so the ledger row itself was the stale side: the
  fix is documentation only, no code behaviour changed and nothing needed
  re-arming (no fixture expectation ever referenced D8). Parts:
  - **Verified against the current tree**: `arduino/Skywriter/skywriter.cpp`
    `begin()` (lines 4–17) sends no Set_Runtime_Parameter (0xA2) traffic at
    all — only GPIO (General-Purpose Input/Output) setup for the sensor's
    transfer-request pin (INPUT_PULLUP) and reset pin, plus the reset pulse;
    sensor bring-up lives in the `SkywriterController` firmware sketch
    (P3.16, four exact 15-payload-byte commands with acknowledge polling) —
    exactly how the gotcha now reads. And `poll()` still resets the transfer
    pin to plain `INPUT` at the end of every transfer (line 74), the gotcha's
    second (still valid) claim. Decision recorded: the pin-mode quirk stays
    as documented upstream behaviour — no spec text pins a pin mode, so this
    is not a deviation, only a note.
  - The Python gotcha's substance also holds (`_on_airwheel` starts as an
    empty list and is checked with `callable()`); only its line references
    had drifted — refreshed to 96 and 344 with a dated truth-check note.
  - `specs/README.md`: the D8 row is removed; the table is empty since
    2026-11-05 with a closure-history note explaining the row-vs-truth
    reversal (same shape as D2's closure: a pre-loop commit — `c6aecc7` —
    removed the code the row originally described) and the void-row
    convention (`tests/deviations.py` treats every remaining row as live,
    so a resolved row must be deleted in the same change that closes it).
  - `tests/README.md`, `tests/deviations.py` docstring,
    `tests/test_harness.py` and `tests/test_scenarios.py` docstrings: the
    D8 enumerations dropped/rewritten (D8 was documentation-only, so no
    manifest annotation was ever attached — the annotation lint is vacuously
    green with an empty table, verified).
  Verified: `bash run_tests.sh` green 4/4; 103 pytest tests (same count).

- P3.18 — the §7 performance provisions are live in the firmware (commit
  `721e6b1`): move reports are paced at the LIVE BLE connection interval,
  with delta accumulation and never-coalesced button transitions, the
  software half of AC-BLE-04 (`specs/ble_hid.md` §7; the radio truth —
  ≥ 60 reports/s sustained and < 100 ms end-to-end on a real phone/PC —
  stays with the Phase-4 probe P4.3). In plain language: the Pico W now
  finds out how often its paired computer actually listens (hosts agree on
  a listening rhythm — the connection interval — when they connect), asks
  the computer to keep that rhythm fast enough for smooth cursor movement
  (7.5–15 ms), and re-times exactly the cursor-update stream to that
  rhythm. The sensor readings arriving faster than the radio can send
  (200 per second from the sensor) are summed up continuously, so
  re-timing the send moments never loses or distorts movement; clicks,
  scroll, keyboard and media actions are unaffected — they are delivered
  immediately, never merged.
  - `SkywriterHIDMapper.{h,cpp}`: the report cadence (`REPORT_INTERVAL_MS`,
    hid_mapping.md §3 rule 6) is now a runtime value
    `report_interval_ms_` created from the named constant (the constant
    stays the initial value AND the fallback — no second copy of the
    mapping), with public `set_report_interval_ms()` (values < 1 ms
    clamped to 1 ms; pending deltas survive any pace change untouched —
    a pace change re-times emission, never drops) and a
    `report_interval_ms()` getter; `attempt_report()` gates on the live
    value. The wheel/keyboard/consumer paths deliberately never route
    through this cadence (§5's "emitted immediately" rule; the pulse
    queue likewise) — button/press transitions cannot be coalesced away.
  - `SkywriterController.ino`: a sketch-owned BTstack (the board's
    Bluetooth software) HCI event handler — registered BEFORE the radio
    starts, alongside the wrapper's opened/closed callbacks — decodes
    `HCI_SUBEVENT_LE_CONNECTION_COMPLETE` (the interval a host chooses at
    connect, unit 1.25 ms; failed/completed-with-status-0 events guarded)
    and later re-negotiations (`HCI_SUBEVENT_LE_CONNECTION_UPDATE_COMPLETE`),
    store-and-flag only (the established radio-context rule: no HID calls
    from the stack's context). loop() applies the interval (unit × 1.25 ms
    rounded to nearest, < 1 ms clamped) into
    `mapper.set_report_interval_ms()` and prints
    `SKYSTATE pace report_interval_ms=N` — the evidence line the P4.3
    probe reads. On connection the sketch also calls
    `gap_request_connection_parameter_update()` asking for [7.5, 15] ms
    (units 6..12 of 1.25 ms; supervision timeout 480 ms ≥ the LE rule of
    2 × (1 + latency) × max interval): a standard parameter request the
    host may decline, aimed at AC-BLE-04's ≥ 60 Hz floor (a slower host
    policy would otherwise make the floor unreachable — there is no faster
    sending than the interval allows). The disconnect drain resets the
    pace to the spec's REPORT_INTERVAL_MS so each new host is re-captured
    cleanly. New build-free truth used: `hci_add_event_handler()` accepts
    additional sketch handlers safely before the stack is powered (the
    registration struct is static) — `PicoBluetoothBLEHID` keeps its own
    handler; the wrapper's opened callback does not expose the interval.
  - Tests: host binary gained the `PACE <ms>` instruction (asserts the
    clamped applied value as a `PACE <ms>` record) and 4 new mapper unit
    tests (faster-than-default pace emits sooner with movement exactly
    conserved; slower pace coalesces into one report, conserved again;
    a mid-stream pace change like a host re-negotiating mid-gesture loses
    no pending movement; the < 1 ms clamp) — recomputing AC-MAP-01's
    "coalesce, never drop" conservation (Σ reported deltas == Σ frames) at
    each pace. `tests/test_firmware_sketch.py` gained 4 source pins
    (live-interval wiring incl. decode getters + registration-before-radio
    + no mapper touch in the handler; the 6..12-unit parameter request;
    the `SKYSTATE pace` line; the disconnect reset).
  - Spec/doc truth updated: `ble_hid.md` §7 gained the implementation note
    (live interval, immediate non-move emissions, open question 3 still the
    probe's), `hid_mapping.md` §3 rule 6 records the runtime property, the
    header/namespace comments in both sources cite P3.18, and
    `tests/README.md`'s parts table tracks the new instructions/pins.
  - Honest scope note: the HCI watcher is verified at the source-compile
    and logic level here; whether a real host keeps the interval inside
    the requested window (and whether send() ever busy-waits badly —
    §10 open question 3) is exactly what P4.3's timestamped probe measures.
  Verified: `bash run_tests.sh` green 4/4; 103 pytest tests (95 + 8);
  `pico-arduino/SkywriterController` compiles for the Pico W (22 % flash /
  34 % RAM — unchanged, the handler is small).

- P3.17b — the pairing-bond persistence question is resolved (commit
  `<HASH>`), and the resolution **refutes** P3.17's RAM-only assumption — a
  genuinely wrong belief in the ledger that the hardware loop was about to
  inherit. In plain language: when a phone or computer "pairs" (establishes
  a trusted wireless relationship) with the controller and later pairs
  again or reconnects, the controller must remember its side of the
  relationship. If it forgets at every power cycle, the host has to go
  through pairing again each time. P3.17 believed this core forgets
  (RAM-only memory); P3.17b verified it does NOT — pairings are saved into
  the Pico W's non-volatile flash memory, so a paired host reconnects
  without re-pairing after a power cycle. No code change was needed: the
  belief itself was the defect, so the fix is documentation and test pins
  in step with the verified truth, all recorded below.
  - How the wrong belief arose: P3.17 read the Security Manager's device
    db facts from `pico-sdk/lib/btstack/port/arduino/btstack_config.h`
    (the config of BTstack's legacy port for Arduino boards with an
    EXTERNAL Bluetooth module — `MAX_NR_LE_DEVICE_DB_ENTRIES = 1`, no
    `NVM_NUM_DEVICE_DB_ENTRIES`, i.e. RAM-only with a single entry). That
    file is not on the Pico W build's include path at all (`platform_inc.
    txt` uses `-iwithprefixbefore/include`), which resolves the
    `$CORE/include/btstack_config.h` shipped specifically for the Pico W
    builds — exactly the file the argument needed but never opened.
  - The verified facts, level by level (all checked against the shipped
    prebuilt core libraries with `arm-none-eabi-nm/ar` and the core's
    source files): (a) the shipped Pico W config defines BOTH
    `NVM_NUM_DEVICE_DB_ENTRIES 16` and `MAX_NR_LE_DEVICE_DB_ENTRIES 16`;
    (b) with `NVM_NUM_DEVICE_DB_ENTRIES` defined, `le_device_db_memory.c`
    (the RAM store) compiles to NOTHING (`#ifndef`-gated body) and
    `le_device_db_tlv.c` (the flash-backed store) is the only linked
    implementation — no `#error` is ever hit; (c) the linked object's
    compiled state is `entry_map` 16 bytes → all 16 bond slots live;
    (d) the arduino build menu the sketch uses (`ipbtstack=ipv4btcble` —
    the "IPv4 + Bluetooth" option) defines `CYW43_ENABLE_BLUETOOTH=1`, so
    the boot-time variant initialisation chain `initVariant()` →
    `init_cyw43_wifi()` → `cyw43_arch_init_with_country()` →
    `cyw43_arch_init()` → `btstack_cyw43_init()` → `setup_tlv()` →
    `le_device_db_tlv_configure()` wires the flash store into the
    Security Manager BEFORE the sketch's `startHID` ever runs; (e) the
    flash store lands in the arduino core's own 8 KiB flash section
    `__bluetooth_tlv` (two 4 KiB erase banks, kept out of the firmware
    image by the ordinary flash layout — `#if 0` static asserts in the
    core's `sdkoverride/btstack_flash_bank.cpp`); (f) on pairing
    completion `le_device_db_encryption_set` calls
    `le_device_db_tlv_store`, so the Long-Term Key (the shared secret a
    bond is made of) is written to flash at pair time.
  - Things updated in this act (no behaviour change): the sketch's
    "KNOWN LIMITATION" pairing comment → the flash-backed truth with the
    AC-BLE-06 hardware gate kept; `specs/ble_hid.md` §5 bonding bullet →
    the code-level truth with citations, and §10 open question 1 →
    resolved (2026-11-05); the source-level pin
    `test_pairing_needs_no_sketch_code_and_bond_store_truth_is_documented`
    (renamed from `..._bond_limit_is_documented`) now asserts
    "FLASH-BACKED" instead of "RAM only"; the P3.17 Done entry got a
    correction pointer; P4.3 got the expectation note (the probe should
    expect no-re-pair PASS; record a deviation row only if the radio
    contradicts it).
  - Honest scope note: everything above is verified at the CODE level —
    the radio-level proof (pair on a real host, power-cycle the Pico W,
    reconnect without re-pairing) stays with AC-BLE-06 / P4.3 exactly as
    the spec's verification column assigns it. `ble_hid.md` §5 wording
    says so explicitly.
  Verified: `bash run_tests.sh` green 4/4 (see fix_plan snapshot); 95
  pytest tests (same count — one pin's asserted text changed, no test
  added); `pico-arduino/SkywriterController` compiles for the Pico W.

- P3.17 — the BLE (Bluetooth Low Energy) connection life cycle is wired
  into the firmware sketch (commit `445d843`): `specs/ble_hid.md` §5, §6, §8
  (targets AC-BLE-03 / AC-BLE-07 software side; their radio truth stays
  with the Phase-4 probes P4.2/P4.3). In plain language: the controller
  now behaves correctly through the whole life of its wireless connection
  — telling the host its battery level, putting itself in a clean state
  when the connection drops, and introducing itself with a known-state
  report when it comes back. Parts:
  - **Battery (§8, AC-BLE-03 software side)**: 100 % at boot (unchanged,
    `startHID`'s default) and refreshed to 100 % at every connect —
    through `PicoBluetoothBLEHID.setBattery(100)` called directly; the
    `MouseBLE.setBattery()` wrapper is confirmed unusable (the core never
    sets `MouseBLE_::_running`, not even in its own `begin()`).
  - **Neutral resync (§6 (re)connect row, AC-BLE-07)**: on connect the
    sketch sends exactly one report in which nothing is held and nothing
    moves (`MouseBLE.move(0, 0, 0)` — `MouseBLE_::move` always emits, its
    zero-suppression lives in the mapper, not here, which is exactly why
    it is the right vehicle) plus a zero consumer-control (media-key)
    report to wipe a media key whose release pulse fell into the link
    loss. Serial line `SKYSTATE ble_resync battery=100 neutral_report`.
  - **Release-all on link loss (§6 + the P3.13 note)**: the mapper
    gained the public `SkywriterHIDMapper::disconnect(now_ms)` — held
    hold-rows (buttons and auto-scroll) go up through the sink
    immediately via the existing private `release_all_buttons()`,
    un-sent pointer movement is DROPPED (never replayed onto the new
    link), the AirWheel (scroll) accumulator clears, and the next valid
    position silently re-baselines (the wireless-session equivalent of
    §3 rule 4's lift-off re-baseline). 5 new mapper unit tests pin all
    four effects through a new `DISCONNECT` instruction in
    `tests/cpp/host_mapper_unit_main.cpp`. The sketch's disconnect drain
    additionally clears its own side state the engine cannot see: the
    scheduled tap/media pulse queue (`pulses_clear()` — a tap whose 50 ms
    release fell into the link loss must not be delivered to the NEXT
    connection), and the Bluetooth wrappers' latched mouse button bits
    (`MouseBLE.release(MOUSE_ALL)`) and keyboard report
    (`KeyboardBLE.releaseAll()`) so the resync report really is neutral.
  - **Events dropped while unconnected (§6 Unconnected row, AC-BLE-07)**:
    all four sensor→mapper callbacks gate on `PicoBluetoothBLEHID.
    connected()` and drop the event; the first suppressed frame prints
    `SKYSTATE sensor_events_dropping_unconnected` once per link loss —
    the hardware probe's evidence that events are dropped, not queued.
  - **Callback-context deadlock rule (design constraint, pinned)**: the
    Bluetooth stack's open/close callbacks run inside the stack's own
    run-loop context; `PicoBluetoothBLEHID.send()` busy-waits on that
    same context's send-completion round trip, so a send from a callback
    would deadlock. The handlers therefore only set flags — plus the
    advertising restart (`gap_advertisements_enable(1)`), the one
    BTstack call that is canonical from a packet handler (AC-BLE-05's
    ≤ 5 s: met immediately). All HID-visible life-cycle work drains in
    `loop()`, before the iteration's sensor events reach the engine.
    Pinned by `test_callbacks_are_flag_only_no_hid_send_from_the_
    radio_context` (8 new source-level tests in
    `tests/test_firmware_sketch.py`).
  - **Bring-up ordering**: the open/close callbacks are now registered
    BEFORE `KeyboardBLE.begin()` powers the radio on (a host connecting
    during bring-up no longer fires into unregistered callbacks); the
    sensor stack, event wiring and radio bring-up order are unchanged.
  - **Pairing/bonding documentation (§5)**: the sketch records that
    pairing needs no firmware code (the core's Security Manager
    auto-confirms Just Works and numeric comparison and requests
    bonding) together with the code-level bond-store truth discovered
    while wiring this item: the core's bond database is the RAM store
    (`le_device_db_memory.c`; the flash-backed `le_device_db_tlv.c`
    `#error`s without a `btstack_config.h` define the arduino port never
    sets) — so hosts re-pair after a Pico W power cycle on this core
    version. AC-BLE-06 verifies on hardware; the decision persists-vs-
    deviates is new fix item **P3.17b**. **CORRECTED by P3.17b
    (2026-11-05): the RAM-only conclusion was built on the wrong config
    file — the Pico W build config (`include/btstack_config.h`) DOES
    define `NVM_NUM_DEVICE_DB_ENTRIES 16`, the flash-backed store IS the
    linked implementation and IS wired at boot; see the P3.17b Done
    entry. The sketch comment and the source-level pin were updated to
    the flash-backed truth in that act.**
  - Honest scope note: `ble_link_open()` reads the stack's connection
    flag from the Arduino loop context without a lock — a 16-bit flag
    read torn between contexts is not a realistic hazard on this core,
    but the RF truth of every §5/§6/§8 rule above is deferred to
    P4.2/P4.3 exactly as the spec's verification column assigns it.
  Verified: `bash run_tests.sh` green 4/4; 95 pytest tests (82 + 13);
  `pico-arduino/SkywriterController` compiles for the Pico W (22 % flash
  / 34 % RAM).

- P3.16 — the FIRST Pico W firmware sketch exists and compiles for the
  board (commit `f5c8316`): `pico-arduino/SkywriterController/
  SkywriterController.ino` combines the sensor stack bring-up with the
  composite BLE HID device of `specs/ble_hid.md` §3–§4 (targets
  AC-BLE-01 / AC-BLE-02, software side; the RF checks stay with Phase 4).
  In plain language: the sketch is the missing wire between the gesture
  sensor and the outside world — it configures the sensor, reads its
  events, translates them with the existing mapping engine, and speaks
  the standard wireless-peripheral language so hosts pair with it like a
  mouse. Parts:
  - **Sensor bring-up lives in the firmware** (the P3.8 note): the stock
    `Skywriter.begin()` pulses only the reset line, so the sketch sends
    the four Set_Runtime_Parameter (0xA2) configuration commands itself —
    each the 0x10 control write followed by EXACTLY 15 payload bytes
    (`SW_SET_RUNTIME_PAYLOAD_SIZE`-bounded copy loop, never the removed
    deviation D2's 16-step over-run). Every command waits for the
    sensor's System_Status acknowledge (0x15 frame carrying the MsgID —
    the Python `get_status()` pattern: 10 tries, 1 ms apart, TS-low read
    of the 26-byte header); a failure prints `SKYSTATE
    sensor_config_failed cmd_index=N` and denies boot (the Python driver
    raises — a headless controller refuses instead), success prints
    `SKYSTATE sensor_ok`.
  - **Composite device with exactly one begin()** (AC-BLE-02): both
    `MouseBLE` and `KeyboardBLE` libraries are linked and used, so
    `__SetupHIDreportmap` merges pointer + keyboard + consumer-control
    descriptors into ONE HID Report Map, but only `KeyboardBLE.begin()`
    runs (each library's `begin()` would call `startHID` twice). The
    skipped mouse `begin()`'s only needed side effect — the public
    `HID_Mouse::_running` enable bit, without which every press/release
    is silently ignored — is set directly via a base up-cast, with the
    double-start reasoning in a comment; `tests/test_firmware_sketch.py`
    pins that both the call quantity and the comment survive.
  - **Identity / battery** (AC-BLE-01, §8): advertisement and HID
    attribute name both `Skywriter HID` (`SKYWRITER_DEVICE_NAME` fills
    both `begin()` slots); appearance comes from `__BLEGetAppearance()`
    inside that begin (printed onto the console as `SKYSTATE
    hid_started name=... appearance=0x...`); the Battery Service starts
    at 100 % through `startHID`'s default (§8's connect-time refresh is
    P3.17).
  - **Firmware house-style warning for the next sketch**: the Arduino
    builder hoists sketch-level function prototypes ABOVE the type
    definitions in the generated file, so a parameter typed with a
    sketch-local enum/struct fails to compile — every sketch-level
    signature stays in primitive types (documented next to the pulse
    queue).
  - **Event path wired end-to-end**: all four sensor streams (position,
    touch/tap/doubletap, gesture, AirWheel) route into
    `SkywriterHIDMapper`, whose `tick()` runs every loop iteration from
    `millis()` (the engine accepts caller-supplied time only). Touch
    codes 0–14 map to zones via one table (families of five ordered
    center/east/north/west/south; family 0 doubletap, 1 tap, 2 hold).
    The mapper's HID calls go through the sketch's sink: pointer moves
    clamp into the int8 BLE report field with a retained remainder
    (movement never dropped), wheel deltas emit immediately, and
    clicks/keys/media go through a 16-slot timed press/release pulse
    queue so no transition is ever coalesced away (§7/AC-BLE-04
    semantics).
  - **Build-truth discovery** (recorded in AGENTS.md Environment +
    `flash.sh` + `run_tests.sh`): the BLE HID sketches DO NOT BUILD with
    the plain FQBN — the arduino-pico core links its BTstack (Bluetooth)
    libraries only under the "IPv4 + Bluetooth" build menu
    (`ipbtstack=ipv4btcble`); a plain build fails the
    `_needsbt.h` static assert ("This library needs Bluetooth enabled").
    Both build entry points now compile with
    `rp2040:rp2040:rpipicow:ipbtstack=ipv4btcble` and `arduino-cli
    compile` lines in AGENTS.md were updated too.
  - **Toolchain wiring**: the Dockerfile now symlinks
    `pico-arduino/SkywriterHID` into the Arduino user library directory
    (the symlink is live in the `skywriter-arduino` volume) so the
    sketch resolves the mapping-engine library the same way it already
    resolved `Skywriter`. Sketch compiles at 22 % flash / 34 % RAM.
  - **New tests**: `tests/test_firmware_sketch.py` (13 static pins —
    device name, single begin, both libraries linked, battery comment,
    the four byte-exact runtime payloads, the 15-byte copy bound,
    acknowledgment handling, all-CODE touch mapping table, mapper
    wiring, serial state lines) + a `tests/README.md` parts-table row.
    After Phase-4 hardware contact, RF truth belongs to the probes
    (P4.2/P4.3); these pins only fail fast on software regressions.
  - **API note recorded on P3.17**: `MouseBLE.setBattery()` is unusable
    (`MouseBLE_::_running` is never set by the core, not even by its own
    `begin()`) — P3.17's battery-at-connect must call
    `PicoBluetoothBLEHID.setBattery()` directly.
  Verified: `bash run_tests.sh` green 4/4; 82 pytest tests (69 + 13).

- P3.15b — the fixture corpus now covers every remaining §6 row the ledger
  item listed (commit `86b19fd`). The pointer-movement half of the item
  (F01 → a second *moderately different* valid position → a real mouse
  delta) was already closed offline by P3.12 (frames F24/F25, scenarios
  `pointer_move` / `pointer_lift_off_rebaseline`), so this item covered the
  §6-row gaps:
  - **Tap rows on real frames**: F26 tap(east) → right click, F27 tap(west)
    → middle click, F28 tap(north) → keyboard Page Up (usage 78), F29
    tap(south) → Page Down (usage 79) — one `tap_<zone>` scenario each,
    click records carrying the TAP_CLICK_MS = 50 rule; the keyboard
    scenarios double as the offline "nothing on the wrong report" pin for
    the keyboard channel [AC-MAP-03, AC-MAP-08].
  - **Reserved doubletap rows**: F30 (bit 13, east) + F31 (bit 11, west) in
    one `doubletap_east_west_reserved` scenario — the doubletap events are
    hard-asserted on BOTH decoders (different zones, so the Python driver's
    per-zone touch repeat limiter cannot suppress the second frame even at
    the default 5 ms replay gap) and `expect.hid` pins the deliberate
    silence (already mapper-pinned by P3.15's unit tests) [AC-MAP-08].
  - **Vertical volume flicks**: F32 flick S→N (GestureInfo word
    `04 10 00 00`) → consumer Volume Increment 233, F33 flick N→S
    (`05 10 00 00`) → Volume Decrement 234 — `flick_south_north` /
    `flick_north_south` [AC-MAP-05, AC-MAP-08].
  - **Hold auto-scroll on real touch frames**: F34 touch(north) (bit 2,
    counter 9) + F35 touch(south) (bit 0) with `time_gap_ms: 350` — each
    replayed hold emits its hold-start notch then interval notches at
    exactly t=100 and t=200 ms (the 200 ms tick still counts as held,
    TOUCH_RELEASE_MS is strict), the release fires strictly past 200 ms
    (t=205) and stops scrolling: exactly three `wheel −1` (north) / `+1`
    (south) records each [AC-MAP-08; §6 row literals, not §5 convention].
  - Arm flip: all seven new scenarios are in `MAPPING_ENGINE_ARMED`
    (`tests/test_scenarios.py`) and hard-asserted end-to-end through the
    real C++ driver → SkywriterHIDMapper chain; manifest gained a dated
    P3.15b revision note; `specs/hid_mapping.md` §8's AC-MAP-03/05/08
    fixture lists updated to cite the new fixtures/scenarios.
  Verified: `bash run_tests.sh` green 4/4; 69 pytest tests (same test-
  function count — the suite counts functions; the 9 new scenarios assert
  inside the existing per-scenario tests; scenario count 20 → 29, frames
  25 → 35).

- P3.15 — the FULL §6 default mapping profile is live in the mapping engine
  as the single implementation table (commit `5dab347`). Everything
  `specs/hid_mapping.md` §6 documents now happens in
  `pico-arduino/SkywriterHID/src/SkywriterHIDMapper.{h,cpp}`, one
  row-cited lookup helper per event kind (each row quotes its spec line):
  - **Gesture → consumer rows** (`onGesture`, AC-MAP-05): code 2 → Scan
    Next Track 0x00B5, 3 → Scan Previous Track 0x00B6, 4 → Volume
    Increment 0x00E9, 5 → Volume Decrement 0x00EA, 6/7 → Volume Inc/Dec
    (the circle rows — mapped unconditionally because §6 explicitly makes
    their dormancy a *sensor constraint*, not an implementation choice),
    code 1 → the garbage → *nothing* row, unknown codes → nothing. One
    consumer-report press per gesture event ("repeats per event"), emitted
    immediately and un-coalesced like wheel deltas. The consumer USage
    codes became named constants next to the existing Page Up/Down ones.
  - **Keyboard rows**: tap(north) → Page Up usage 78, tap(south) → Page
    Down usage 79 via the new `keyboardPress` sink path (the sink already
    had `keyboardPress`/`consumerPress` from P3.2's harness — the engine
    now drives them).
  - **Media tap rows**: doubletap(north) → Next Track, doubletap(south) →
    Previous Track; doubletap(east/west) stay the reserved → *nothing*
    rows, now pinned silent by a dedicated unit test (their old
    "whatever P3.15 decides" docstring is gone).
  - **Hold auto-scroll rows**: touch(north) hold → wheel −1 notch,
    touch(south) hold → wheel +1 notch, one per the new
    `AUTO_SCROLL_INTERVAL_MS = 100` constant (§6's own row timing — not a
    §7 tunable, the §7 list is fixed by the spec). Engine decisions
    recorded here: (a) the FIRST notch emits immediately at hold start
    ("while held" reads as the hold itself producing scrolls —
    responsive; a future north/south hold fixture must expect it; noted in
    `specs/fixtures/manifest.json`'s dated revision notes); (b) the row's
    wheel values are §6's own literals — north auto-scroll emits NEGATIVE
    notches, deliberately distinct from §5's clockwise-positive
    convention, copied verbatim; (c) the interval is paced in `tick()`
    after the release loop, so a hold silence-released on this very tick
    never scrolls again, and §4's lift-off trigger ends scrolling the
    same way it releases held buttons (release_all_buttons now speaks the
    hold-row view, not its previous assume-a-button view).
  - **Table consolidation (§7 "the table IS the implementation")**: the
    per-kind row helpers (`hold_action_for`, `tap_click_button_for`,
    `tap_key_usage_for`, `doubletap_click_button_for`,
    `doubletap_consumer_usage_for`, `gesture_consumer_usage_for`) carry
    every §6 cell, each next to a comment quoting the row — the old
    button-only `button_for` is gone; held_ now records engaged hold rows
    generally (button OR auto-scroll) instead of assuming a button.
  - Arm flip: the five gesture scenarios (`flick_west_east`,
    `flick_east_west`, `edge_flick_east_west`, `circle_clockwise`,
    `circle_counter_clockwise`) are hard-asserted end-to-end through the
    real driver → engine chain; `MAPPING_ENGINE_PENDING` is empty since
    every corpus scenario is now armed (the garbage/always-silent
    scenarios stay armed as silence pins); a dated revision note was
    added to the manifest; docstrings/README/spec §7 updated to say the
    §6 table is complete.
  - New pins: 8 direct mapper unit tests in `tests/test_mapper_unit.py`
    (north/south keyboard taps, north/south media doubletaps, reserved
    east/west silence, north/south auto-scroll cadence + sign, stop at
    release-by-silence, stop at lift-off with the same-tick
    release-wins contrast, and rowless zones never scroll). Plus an
    `arduino-cli` RP2040 Pico W smoke sketch including the mapper compiles
    clean (throwaway, deleted).
  Verified: `bash run_tests.sh` green 4/4; 69 pytest tests (61 + 8).

- P3.14 — the §5 AirWheel semantics are live in the mapping engine (commit
  `95ad4c2`). The rotation (scroll) stream of `specs/hid_mapping.md` §5
  (AC-MAP-04, the touch+position+airwheel row of AC-MAP-06) lands in
  `pico-arduino/SkywriterHID/src/SkywriterHIDMapper.{h,cpp}`:
  - `onAirwheel(degrees, now)` converts the frame's signed rotation delta
    to wheel notches at the new named constant `AIRWHEEL_NOTCH_DEGREES =
    11.25` (one sensor counter step = 11.25° = one wheel notch — the
    counter's own 32-steps-per-revolution quantization, Interface.pdf
    Table 4-10; deliberately a documented datasheet constant, NOT one of
    the §7 tunables: it is the sensor's resolution, not a feel parameter).
    Positive (clockwise) = scroll up; `AIRWHEEL_INVERT` flips the sign
    when configured. `AIRWHEEL_ENABLED == false` keeps the wheel rows
    dormant (the sensor then reports circle gestures instead — the
    hardware constraint of §6's note).
  - Fractional notches accumulate in new state `wheel_acc_` (float); the
    whole part is emitted **immediately** via `sink_.mouseWheel()` —
    deliberately NOT routed through `attempt_report()`, because §5 makes
    scroll latency-sensitive and only move reports coalesce. Truncation
    toward zero keeps the remainder's sign in the accumulator (same
    never-lose-movement principle as the pointer's pending deltas; the §5
    "two 45° deltas = 8 notches total" example is exact here). Emission is
    clamped into the sink's `int8_t` wheel field (realistic per-event
    deltas are ≤ 32 steps; anything absurd drains on later events, lost
    nothing).
  - Lift-off reset (§5 "Accumulator resets on lift-off"): `tick()`'s
    existing lift-off transition (`have_prev_` true→false) now also clears
    `wheel_acc_` — mirroring the release of held buttons in the same
    branch.
  - Pinned three ways: (a) the corpus scenarios
    `airwheel_quarter_turn_cw` (two +90° events → two +8-notch wheel
    reports), `airwheel_wrap` (counter wrap → +4 notches, the D3-closed
    decoder behaviour flowing through) and
    `touch_with_position_and_airwheel` (button down + wheel 8 + position
    baseline from ONE frame) are now hard-asserted end-to-end through the
    real driver → real engine chain (armed in `MAPPING_ENGINE_ARMED`);
    (b) 7 new direct mapper unit tests in `tests/test_mapper_unit.py`
    (via a new `AIRWHEEL <degrees> <ms>` instruction in
    `tests/cpp/host_mapper_unit_main.cpp`) pin half-notch accumulation,
    remainder survival across events, un-coalesced emission inside one
    move-report interval, and the lift-off reset (with the contrast pair
    proving the reset's effect); (c) an `arduino-cli` RP2040 Pico W smoke
    sketch including the mapper compiles clean (throwaway, deleted).
  - `tests/README.md`, `tests/hid_grammar.py` and the
    `MAPPING_ENGINE_ARMED`/`MAPPING_ENGINE_PENDING` docstrings updated
    (P3.15 keeps the remaining five gesture scenarios).
  Verified: `bash run_tests.sh` green 4/4; 61 pytest tests (54 + 7).

- P3.13 — the §4 touch semantics are live in the mapping engine and the
  §6 button rows are implemented (commit `3c3e1de`). The engine now turns
  touch electrode events into the HID actions of `specs/hid_mapping.md`
  §4 (AC-MAP-02, AC-MAP-03, and the button half of AC-MAP-07):
  - `pico-arduino/SkywriterHID/src/SkywriterHIDMapper.{h,cpp}`: per-zone
    press state (`held_` / `last_touch_ms_` for all five zones) — press on
    the first touch frame only (repeats refresh the recency, never
    re-press), release inferred per tick when a zone has been silent for
    `TOUCH_RELEASE_MS` (200) longer (strict `>`, matching the lift-off
    rule's style), lift-off (position silence > `LIFT_OFF_MS`) releases
    every held button immediately via a new private
    `release_all_buttons()`. Tap/doubletap → `sink.mouseClick(button,
    1|2)`, one completed press+release each, never leaving a button held.
    The §6 button table (anonymous-namespace `button_for`): touch(center)
    hold → left, tap(center) → left, doubletap(center) → left ×2,
    tap(east) → right, tap(west) → middle; the rows owned by later items
    (north/south hold auto-scroll and their keyboard taps → P3.15;
    reserved doubletap(east/west) → nothing) emit nothing deliberately.
  - **Manifest re-authoring** (build-mode correction, documented in the
    manifest): `touch_press_and_release`'s `expect.hid` was one down/up
    pair with the prose "the F08 repeat must NOT re-press" — but its 250 ms
    simulated gap EXCEEDS `TOUCH_RELEASE_MS` (200 ms), so the spec-correct
    rule releases by silence at tick 205 ms and F08's frame at 250 ms is a
    fresh acquisition (not a repeat), pressing again and releasing again
    at 455 ms: the expectation is now the exact four records. The old
    prose considered only a post-scenario release evaluation, which
    contradicts §4's per-tick rule.
  - **Repeat-inertness has no home in the fixture corpus**: any two touch
    frames under 250 ms apart make the Python driver's repeat limiter
    (default 4 Hz, a decorator feature — by design) drop the second event
    while the C++ driver's dispatches it, so the canonical streams would
    diverge with no honestly-annotatable ledger row. That behaviour is
    pinned instead by direct mapper unit tests: new
    `tests/test_mapper_unit.py` (10 tests) + host binary
    `tests/cpp/host_mapper_unit_main.cpp` (drives the mapper at call
    granularity — TOUCH/POSITION/TICK/FIN — printing the same HID records;
    built via the same compiler resolution as the replay adapters). Covered
    there: press-once + release-by-silence (incl. the strict-threshold
    edge), repeat-inertness inside the window, re-acquisition after an
    inferred release, lift-off (incl. "exactly LIFT_OFF_MS still held" and
    "no position ever → lift-off never fires"), tap/doubletap click
    counts, the §6 zone→button table, zone-independence, and the
    non-button zones' silence.
  - Arm flip: the four touch scenarios (`touch_press_and_release`,
    `touch_two_zones`, `tap_center`, `doubletap_center`) are hard-asserted
    end-to-end on the mapping adapter; `touch_with_position_and_airwheel`
    is re-attributed to P3.14 alone (its button half is now live).
    Also verified by an `arduino-cli` RP2040-target smoke sketch including
    the mapper (throwaway, deleted after the run).
  Verified: `bash run_tests.sh` green 4/4; 54 pytest tests (44 + 10).

- P3.12 — the mapping engine exists and its pointer model is fully
  implemented and machine-asserted (commit `13f1698`). Specs rule out a
  second copy of the mapping (hid_mapping.md §7), so the engine is ONE set
  of source files — `pico-arduino/SkywriterHID/src/SkywriterHIDMapper.*`
  (an Arduino-style library so the P3.16 firmware sketch links it) — fed
  by every decoder's canonical events.
  - The engine: `SkywriterHIDMapper` consumes canonical events (§2
    vocabulary) with explicit arrival times (no `millis()` — the same
    source runs on the Pico W and in the harness) and emits HID actions
    through a `HIDMapperSink` (firmware → MouseBLE/KeyboardBLE wrapper;
    harness → `hid_grammar` records). The §7 tunables live as named
    constants in the header: `GAIN` 1/256, `JUMP_THRESHOLD` 8192,
    `LIFT_OFF_MS` 100, `REPORT_INTERVAL_MS` 15 (initial; documented in
    hid_mapping.md §3 rule 6 — the slowest common BLE HID connection
    interval, so ≥60 Hz stays true on the slowest host; the firmware may
    tighten it to the live interval, P3.18), `TOUCH_RELEASE_MS` 200,
    `TAP_CLICK_MS` 50, `AIRWHEEL_INVERT` false, `AIRWHEEL_ENABLED` true.
  - Pointer model (§3, AC-MAP-01) complete: first valid position (after
    start, a lift-off or a jump) is a silent baseline; per-frame raw
    deltas beyond ±8192 are discarded and re-baseline; deltas × GAIN
    accumulate (float carry), +y north = cursor up, no pre-flip; move
    reports coalesce to one per `REPORT_INTERVAL_MS` with deltas never
    dropped; `finish()` flushes (shutdown = nothing lost). touch/tap/
    doubletap, gesture and airwheel events are accepted and deliberately
    silent until P3.13–P3.15 fill their §6 rows (each branch carries its
    owning item).
  - The harness: `tests/cpp/host_mapping_main.cpp` + `tests/adapters_mapping.py`
    (adapter key `cpp_mapping`) chain the real C++ driver through the
    engine in one host binary — the firmware signal chain exactly —
    driven by `TICK <ms>` / `FRAME <hex>` / `FIN <ms>` instructions on a
    ≤5 ms timeline (the sensor's 5 ms frame cadence when a scenario sets
    no `time_gap_ms`), so cadence and lift-off run on simulated time.
  - Fixture corpus: frames `F24_position_move` (+2560/−512 raw from F01,
    a moderate normal-tracking delta) and `F25_position_move_next` (+256
    = one GAIN unit); scenarios `pointer_move` ([F01,F24,F25] → exactly
    ONE coalesced `move dx=11 dy=-2` record — sign, magnitude and the §3
    rule 6 cadence assertion at once) and `pointer_lift_off_rebaseline`
    ([F01,F24] with `time_gap_ms: 150` > `LIFT_OFF_MS` → F24 re-baselines,
    nothing emitted; AC-MAP-07's baseline-reset half).
  - Test arm: `test_scenario_hid_expectation_on_the_mapping_engine` makes
    `expect.hid` a hard, ordered assertion for `MAPPING_ENGINE_ARMED` —
    the four pointer scenarios plus garbage_gesture / gesture_in_progress
    / status_ack / fw_version_valid (events that §6 maps to nothing must
    provably stay silent on the HID side). `MAPPING_ENGINE_PENDING`
    attributes the remaining scenarios to P3.13/P3.14/P3.15, and the
    arm-coverage lint forces every new scenario to be classified.
  - Scope decision (recorded for the following items): the HID replay
    chain currently runs the **C++ driver → engine** only — the engine is
    one implementation by spec, and decoder-level parity AC-MAP-09 is
    already asserted on both drivers; the MicroPython port re-uses this
    same engine via canonical events in P5.2.
  Verified: `bash run_tests.sh` green 4/4; 44 pytest tests (41 + 3 new:
  arm coverage lint, pending-attribution lint, per-scenario HID compare);
  plus a throwaway `arduino-cli` smoke sketch including
  `SkywriterHIDMapper.h` compiles clean for the RP2040 Pico W target
  (`--library pico-arduino/SkywriterHID`).

- P3.11d — the poll thread no longer dies on the FIRST I2C error (commit
  `8d4081d`): `library/skywriter/__init__.py`'s two `except IOError` handlers
  in `_do_poll()` now delegate to a new shared `_poll_i2c_error()` helper —
  it increments the consecutive-error counter and returns `True` while the
  grace holds, so `AsyncWorker.run()`'s "`False` means abort" contract keeps
  looping (one error was ONE bad cycle, not a stop order), and past 10
  consecutive failures it raises the existing documented exception — so the
  dead thread announces itself with a traceback instead of vanishing.
  Explicit design decision (the open question in the item): stopping a
  persistently dead-bus worker via the raise, NOT via
  `stop_event.set()` from inside `_do_poll` — a visible traceback beats both
  a silent death and a second race-prone shutdown path, clean
  `stop()`/`_stop_poll()` shutdown stays the caller's facility, and nothing
  else reads `stop_event` from the poll path. Also hardened: the transfer
  (TS) release moved into a `try/finally`, so an error exit no longer leaves
  the sensor's data buffers pinned (previously a mid-transfer error kept the
  transfer line driven low forever). Typo fixes on the way out: the very old
  "encoutered nore than 10" message now says "encountered more than 10".
  Tests: new `tests/test_poll_thread.py` — 7 pins (first error returns True,
  10-in-grace vs 11th raising, success resets the grace, mid-frame error
  skips dispatch, error releases the TS pin pulled-up-as-input, a real
  `AsyncWorker` thread survives three simulated failures and still
  dispatches the fixture frame, and grace exhaustion dies visibly via
  `threading.excepthook`). Verified: `bash run_tests.sh` green 4/4; 41
  pytest tests (34 + 7).

- P3.11c — size-aware frame reads landed (commit `a0a497a`): the Raspberry Pi
  Python driver's `_do_poll()` no longer drops long control frames. Before,
  every poll read a fixed 26 bytes per I2C transaction, so a real
  Fw_Version_Info report (0x83, Interface.pdf §3.5.1, 132 bytes at the wire)
  could never arrive complete — `_handle_firmware_info` saw only the first ~22
  payload characters of the 120-byte NUL-padded version field, with no NUL
  terminator. Parts:
  - `library/skywriter/__init__.py`: the poll now sizes its reads from the
    frame's **Size field** (frame byte 0, the total message length INCLUDING
    the 4-byte header, per Interface.pdf §3.3; §2.3 note 1 recommends exactly
    this). The first read stays 26 bytes (the classic full-layout sensor
    frame stays a single read; nothing changes in the 200 Hz hot path), and
    when the Size field announces a longer message the remainder is fetched
    with chunked continuation reads while the transfer (TS) pin is still
    asserted — chunked at 32 bytes because the Linux SMBus helper cannot
    request more per call (kernel `I2C_SMBUS_BLOCK_MAX`), so a complete
    132-byte frame arrives as 26 + 32 + 32 + 32 + 10. Dispatch now happens
    only for complete, non-corrupt frames (Size < 4 is skipped) and passes
    the decoder exactly the Size-field byte range minus the header
    (continuing the P3.3 off-by-four contract); bus padding or over-answering
    beyond the Size field never reaches a decoder. New module constants
    `SW_MAX_MESSAGE_SIZE = 255` (protocol cap, §3.2) and
    `SW_I2C_READ_CHUNK = 32` (SMBus cap).
  - `tests/test_do_poll.py`: 4 new pins (34 pytest tests now) — the exact
    five-read chase sequence against a streaming fake bus (F17 arrives
    complete, payload = the full header-stripped frame), the
    empty-continuation case drops the partial frame without dispatching,
    padding/mocked over-answer never spills past the Size field, and a
    corrupt Size (< 4) dispatches nothing while the poll thread stays alive.
  - Hardware side: whether the real sensor continues its I2C buffer across
    the separate read transactions of one asserted transfer is the one claim
    this fix cannot verify offline — recorded onto fix item P4.1 so the
    outer hardware loop checks it (the Arduino driver's whole-frame single
    read, P3.11b, is unaffected).
  - Discovered while working here (new fix item **P3.11d**): the
    `AsyncWorker` polling thread treats the first `False` from `_do_poll` as
    "stop looping", so the driver's "10 consecutive I2C errors" grace counter
    can never be reached and one transient bus error silently ends event
    polling. Not fixed in this commit (thread-lifecycle design choice,
    hardware-adjacent); P3.11d holds the precise analysis and fix sketch.
  Verified: 34 pytest tests green (30 + 4); `bash run_tests.sh` green 4/4
  (fixture corpus, library unit tests, replay suite, all three example
  sketches compile).

- P3.11b — Deviation D9 closed (commit `d1db8f3`): the two control frames
  beside Sensor_Data_Output are surfaced as canonical events on BOTH drivers,
  and the `status_ack` / `fw_version_valid` scenarios are hard assertions
  with no tolerance left (their `omit_pending` annotations are gone, the D9
  row is gone from `specs/README.md`). Parts:
  - **System_Status (0x15)** — the sensor's acknowledge to a control command,
    decoded per Interface.pdf §4.1 / §3.6 Table 3-8 (payload: MsgID,
    MaxCmdSize, 16-bit little-endian ErrorCode). Canonical
    `{"event": "system_status", "msg_id", "error"}`:
    - `library/skywriter/__init__.py`: `_handle_status_info` now parses the
      real payload (it was `pass`) — module state `system_status` /
      `system_status_error` set, optional callback `_on_system_status` called
      with `(msg_id, error)`, plus the new public decorator
      `system_status()` (same `setup()`-on-register pattern as flick etc.).
    - `arduino/Skywriter/skywriter.cpp`: the `0x15` `poll()` case (was
      "// Unimplemented") calls the new private `handle_status_info`, which
      dispatches the new optional public callback
      `onSystemStatus(void (*)(unsigned char, unsigned int))` (registered via
      `Skywriter.onSystemStatus(...)`), the C++ counterpart of the
      decorator.
  - **Fw_Version_Info (0x83)** — the sensor's firmware-version report
    (Interface.pdf §4.3). Canonical
    `{"event": "firmware_info", "fw_valid", "version"}`, **version
    NUL-stripped** (the 120-byte field is NUL-padded; the canonical record
    carries exactly the readable string), and only FwValid == 0xAA emits —
    the Python driver raises for every other value (the D6 rule, P3.6), so
    emitting nothing invalid keeps AC-MAP-09 parity:
    - `library/skywriter/__init__.py`: `_handle_firmware_info` strips at the
      first NUL instead of printing raw padding bytes; module state
      `fw_valid` / `fw_version` set for every report, callback
      `_on_firmware_version` fired for valid ones, plus the new public
      decorator `fw_version()`.
    - `arduino/Skywriter/skywriter.cpp`: the `0x83` case calls the new
      private `handle_firmware_info` (validity gate at 0xAA, NUL-stripped
      copy of the version field bounded by `SW_FW_VERSION_FIELD_SIZE`),
      dispatching the new `onFirmwareVersion(void (*)(unsigned char,
      const char*))`.
  - **Whole-frame reads on the Arduino driver** (a defect the new assertion
    exposed): `poll()` used to request only 32 bytes per read, truncating the
    132-byte Fw_Version_Info frame to ~20 characters of version string — it
    could never have satisfied the fixture. It now requests
    `SW_MAX_FRAME_SIZE` (new `skywriter.h` constant, 132 bytes = the longest
    sensor message, §3.5.2) in one read, and the payload copy loop is bounded
    by the buffer size (the old loop trusted the read length exactly filling
    the 32-byte `command_buffer` — a hazard that must not return now that the
    request is larger). Real-hardware verification of the larger request is
    folded into P4.1.
  - **Harness**: `tests/cpp/host_decoder_main.cpp` registers both callbacks
    and prints `EV SYSTEMSTATUS <msg_id> <error>` and
    `EV FWVERSION <fw_valid> <version string>`; `tests/adapters_cpp.py`
    parses them (the version string **contains a literal space** — the ISO
    build timestamp "2013/11/08 13:03:00" — so it is parsed as the remainder
    of the line, never as one whitespace token); `tests/adapters_python.py`
    captures `system_status` records from the callback and `firmware_info`
    records from the callback with `fw_valid` snapshotted from the driver's
    module state (the same globals-snapshot trick the gesture records use);
    `tests/canonical.py` gained `canonicalize_control_record` feeding both
    converters. Fresh-state reset extended with the four new Python state
    variables.
  - **Spec-data bug found and fixed in the act** (the previously-never-checked
    expectation was wrong): the `status_ack` manifest entry claimed
    `msg_id: 170`, but that decimal belongs to `0xAA` (the FwValid byte); the
    datasheet decodes it as `0xA2 = 162` (Table 3-8). Corrected to 162 with
    the note explaining exactly how the stale value arose. Also:
    `specs/hid_mapping.md` §2's canonical-event table now lists both control
    events (the machine-readable grammar was already in `tests/canonical.py`).
  - **Doc/docstring hygiene**: `tests/test_firmware_info.py`'s stale F17 size
    claim fixed (132 bytes, not 24) and two new pins added (valid report sets
    `fw_valid`/`fw_version` state + fires the handler with the NUL-stripped
    string — the adapter's snapshot dependency); `tests/README.md` and the
    `test_harness.py` / `test_scenarios.py` docstrings no longer list D9 as
    open (D8 remains).
  - Verified: 30 pytest tests green (29 + 1 callback pin);
    `bash run_tests.sh` green 4/4 (fixture corpus, library unit tests, replay
    suite, all three example sketches compile with the modified library).
- P3.11 — Deviation D7 closed (commit `32076e1`): the **Arduino** driver now
  decodes the full 32-bit GestureInfo word in exactly the way the Python
  driver has since P3.7, so both drivers carry the gesture attributes and
  AC-MAP-09 parity holds with no tolerance left on gesture events. Parts:
  - `arduino/Skywriter/skywriter.cpp` gesture branch: assembles the full
    32-bit little-endian GestureInfo word (Interface.pdf §4.5 Table 4-10)
    instead of reading byte 0 — code = bits 0–7, class = bits 12–15
    (0 garbage, 1 flick, 2 circle), edge = bit 16 — and stores
    `last_gesture_class` (unsigned char) / `last_gesture_edge` (bool) as
    **public state alongside `last_gesture`** (the C++ counterpart of the
    Python driver's `gesture` / `gesture_class` / `gesture_edge` globals;
    naming follows the existing `last_gesture`/`last_touch` convention),
    set **before** `handle_gesture` dispatch. Recognition-in-progress
    frames (bit 31, code 0) still emit nothing — the unchanged code>0 gate
    already covers hid_mapping.md §2's requirement.
  - `skywriter.h`: the two new public members with the Interface.pdf
    citation. Deliberate design note: attributes are public state, not new
    callback parameters — `onGesture(void (*)(unsigned char))` is
    unchanged, so the two shipped example sketches (NeoPaint, SkyPainter)
    register their handlers unchanged and still compile (verified by the
    firmware-compile check on all three).
  - Harness: `tests/cpp/host_decoder_main.cpp` prints
    `EV GESTURE <code> <class> <edge>` from inside its `on_gesture`
    callback (the attributes are set before dispatch, so the snapshot
    trick is exact — the same technique the Python adapter uses on the
    driver's globals); `tests/adapters_cpp.py` parses the record with
    class/edge; `tests/canonical.py`'s cpp converter now emits the same
    code/class/edge shape as the Python converter (the docstring's
    `keys_pending` example updated: D7 was the mechanism's last user).
  - Self-arming flip: the six `keys_pending D7` annotations dropped from
    `specs/fixtures/manifest.json` (flick_west_east, flick_east_west,
    edge_flick_east_west, garbage_gesture, circle_clockwise,
    circle_counter_clockwise) — code/class/edge are now hard assertions on
    BOTH drivers; D7 row removed from `specs/README.md`; revision note
    added to the manifest notes; the open-deviation enumerations updated in
    `tests/README.md`, the docstrings of `tests/test_harness.py` /
    `tests/test_scenarios.py` (now "D8, D9") and `tests/adapters_python.py`.
  - Verified against the recompiled host decoder: F02 → code 2 / class 1 /
    edge false, F04 → edge **true**, F06 → code 1 / class 0, F21/F22 →
    class 2; the `test_cpp_adapter_flick_dispatch` plumbing pin asserts the
    full record shape.
- P3.10 — Deviation D4 closed (commit `fc0853e`): **every set touch bit in a
  frame now produces its event on both drivers**, and the frame's remaining
  fields are still decoded in the same pass. Per `hid_mapping.md` §2 ("all
  set touch bits in a frame produce their events; a frame may carry touch +
  position + airwheel simultaneously and all must be processed"):
  - `arduino/Skywriter/skywriter.cpp` touch branch: the early `return` after
    the first (highest-bit) match is gone — the existing highest-bit-first
    scan (`comp = 1 << 14`, code order per skywriter.h `SW_*`) now dispatches
    `handle_touch` for every set bit and falls through to the AirWheel
    decode below, so the touch frames no longer eat their own airwheel
    events (the `touch_with_position_and_airwheel` scenario was pinning
    exactly that lost +90° event as `omit_pending D4/cpp`).
  - `library/skywriter/__init__.py` touch loop: the `break` after the first
    matching action is gone — all set bits dispatch. Why the Python side is
    in this fix although the D4 row said "Arduino": the spec sentence is
    driver-agnostic and AC-MAP-09 parity needs both (see the F23 fixture
    below); the Python variant of the defect only dropped the extra touch
    bits (the rest of the frame was already processed), which is why it
    never got its own row.
  - Python repeat-limiter repair the above forced: the "last fired"
    timestamp of an `'all'`-position subscription is now kept **per zone**
    (`_on_touch_last[kind][zone]`), mirroring how the exact-zone branch keys
    it. It was a single `_on_touch_last[kind]['all']` slot — harmless while
    the loop dispatched at most one touch per frame (one shared slot = one
    update per frame), but with every-set-bit dispatch two exact-simultaneous
    zones suppressed each other inside the same frame (second zone hit the
    shared 250 ms window). Rate-limit behaviour for a single held finger is
    unchanged (the `touch_press_and_release` F07/F08 250 ms gap replay
    asserts that).
  - Fixture corpus: new frame `F23_touch_two_zones.hex` (mask 0x001F,
    TouchInfo word `12 00 00 00` = Center bit 4 + West bit 1 — synthetic,
    Interface.pdf Table 4-10 layout) with scenario `touch_two_zones`;
    canonical expectations hard-assert `touch:center` then `touch:west` on
    BOTH drivers (scan order = highest bit first; parity compare is
    order-insensitive anyway), `expect.hid` pins
    left-button-down for the center hold (touch(west) hold has no §6 row —
    only tap(west) maps to middle click); the button record arms with the
    mapping engine (P3.13).
  - Self-arming flip: D4 row removed from `specs/README.md`; the
    `omit_pending {D4, cpp}` annotation dropped from the
    `touch_with_position_and_airwheel` airwheel event — it is now a hard
    assertion on both drivers; the open-deviation enumerations updated in
    `specs/hid_mapping.md` §2, `tests/README.md`, `tests/test_scenarios.py`
    and `tests/test_harness.py` (now "D7–D9").
  `bash run_tests.sh` green 4/4; 29 pytest tests (the suite counts
  per-driver test functions, so the added scenario pins assertions without
  changing the count).
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
