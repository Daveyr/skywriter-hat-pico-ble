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
   Update (2026-11-08, hardware session 1 — run by a person on the host, not
   by the loop). Results reported so far:
   - Sensor bus: the gesture sensor is detected on the I2C (Inter-Integrated
     Circuit, the two-wire sensor bus). Partial P4.1 evidence only — the
     serial boot lines were reported as all present (sensor ready,
      HID started, pace line on connect), but no capture file exists yet and
      frame streaming is not recorded.
   - Bluetooth scan: `Skywriter HID` is listed. Partial AC-BLE-01 (name
     visible; "exactly one instance" not yet checked).
   - Pairing: a Linux (BlueZ) laptop paired successfully. Partial AC-BLE-03 (pairing only;
     battery at 100 % and the Device Information reads are not yet checked).
   - Use: the laptop reacted to the sensor, but the behaviour was haphazard.
     Reported symptoms: the cursor jumped or teleported, moved the wrong way
     or along the wrong axis, and keyboard and media keys fired. Keyboard
     presses also typed letters. Traced in the code: the Page Up and Page
     Down taps send the wrong key codes, which the keyboard driver types as
     letters — tracked as P3.21. The jumps, direction and media-key symptoms
     are the subject of the gate item P4.0. The device is NOT usable as a
     mouse yet.
   - Method: manual only (no scripts); the sketch was built and flashed with
      `pico-arduino/flash.sh`.
    - Not yet run: the AC-BLE-02 Report Map check (the laptop's device list was
      not checked, so "one device, mouse and keyboard" is unconfirmed), the
      power-cycle reconnect
     (AC-BLE-06), the latency and report-rate probe (AC-BLE-04), link-loss
     advertising (AC-BLE-05), the multi-OS smoke test (AC-BLE-08) and real-frame
     capture (P4.6). No `HW_REPORT.md` was written, so `READY_FOR_HW` stays in
     place.
    Update (2026-11-09, hardware session 2 — serial monitor capture, no code
    change). The monitor was attached after boot, so the boot lines are not in
    the log. Seen: `SKYWRITER-HID sensor_firmware valid=0xAA version=1.1.18`,
    the link connecting with `pace report_interval_ms=15`, and `ble_resync` /
    `ble_connected` printed twice with no `ble_dropped` between them (open, see
    P4.3). The user reported that only single and double clicks appeared to
    work.
    Update (2026-11-16, hardware session 3 — after the permanent rewiring; the
    rewiring date was not recorded). The wires were secured to stop loose
    connections, which is the only change reported. The Bluetooth link is up
    (the laptop shows battery level and signal strength) and the serial monitor
    shows no error, but NO input of any kind reaches the laptop: no pointer
    movement, click, tap, scroll, key or media key. Session 2 still had clicks
    working, so this is a total loss of input, not the haphazard behaviour of
    sessions 1–2. It blocks P4.0 and is logged as the first Phase-4 gate, P4.0a.
    No code was changed in this update.
   Update (2026-11-17, loop iteration after HW_REPORT.md — code commit
   `1c8bbb2`): the hardware report's code-fixable failures are closed, and
   `HW_REPORT.md` is removed (its facts are preserved here). Section 4 row
   outcomes:
   - **F1 (Page Up / Page Down typed letters, P3.21) — FIXED** by P3.21
     (commit `1c8bbb2`): usage constants corrected to the USB HID Usage
     Tables values (Page Up 0x4B = 75, Page Down 0x4E = 78; 0x4F = 79 is
     Right Arrow) in the spec §6 revision note, the mapper constants, the
     manifest and the harness grammar; and the firmware sink now sends
     keyboard usages in the Bluetooth keyboard library's non-printing
     range (usage + 136) on BOTH press and release — the raw usage 78
     that typed "N" can never reach the library again (two new source
     pins in `tests/test_firmware_sketch.py`; `tap_north`/`tap_south`
     manifest expectations now 75/78 and replay-asserted). On hardware:
     a north tap must give Page Up and a south tap Page Down with no
     letters (checked in P4.0 / P4.5).
   - **F2 (no input since session 3, P4.0a) — code parts landed**: P3.22
     (the `SKYSTATE health` counters line, the session's main instrument)
     and P3.23 (the transfer line is always released, with its pull-up
     restored — H1 and H2) are in commit `1c8bbb2` and ready to flash.
     The wiring (H3) is still not eliminated (joint quality / flexing),
     and H4/H5/H6 stay hardware questions. The human steps in the
     report's section 5 (flash `pico-arduino/SkywriterController` via
     `./flash.sh SkywriterController`, full boot log T3, `hid-recorder`/
     `evtest` T4, counters T5, flex T6) are the next hardware loop's work.
   - **F3 (haphazard pointer, P4.0) — still blocked by F2**, unchanged:
     do not retune `GAIN` or `JUMP_THRESHOLD` yet.
   - **F4 (duplicate connect lines, P4.3) — OPEN**, unchanged: check the
     next serial log (now with uptime + disconnect counters) before
     changing connection handling.
   - **F5 ("select all" ≈ Ctrl+A, 2026-11-17) — recorded, hypothesis
     narrowed in code**: the Bluetooth keyboard library's `press()` adds
     modifier bits ONLY through its ASCII path (Shift / AltGr from the
     layout table; there is no Ctrl path in `press()` at all), so the old
     raw-usage-78 call could produce "N" (+ Shift) but NEVER Ctrl+A.
     After P3.21 the raw path is gone entirely (`usage + 136` on every
     keyboard press/release — `KEY_PAGE_UP` 0xD3 = 136 + 75 in the core's
     own table). Consequence for the next session: with the P3.21 build
     flashed, a "select all" would have to come from somewhere other than
     this firmware's keyboard report (a stuck host-side state, another
     input device, or the mouse report misread) — if it recurs, check the
     laptop's device list first (T4's `evtest`/`hid-recorder` shows the
     device each event came from).
   - **F6 (repeated sensor firmware messages, session 3 flex) — now
     decidable**: with P3.22 flashed, a sensor restart gives a small
     firmware-frame count with a fresh `sensor_firmware` line each time
     (and uptime intact unless the Pico itself reset, H5); a stalled read
     gives the firmware-frame count climbing at the read rate while the
     sensor-data count stops — and P3.23 removes the one code defect
     (the line-left-low early return) that could produce such a stall.
    Update (2026-11-17, hardware session 3 follow-up — no code change). All
    sensor-to-Pico wires have moved from the breadboard to veroboard (made on or
    before 2026-11-16; exact date not recorded). Unplugging the Pico changed
    nothing, and the firmware has not been reflashed since session 2. Input has
    typically been absent since the first breadboard attempt, with two known
    exceptions: session 2's clicks, and an "N" that appeared in a text box on
    2026-11-17 (a north tap typed as the letter N — the P3.21 defect). So the
    fault is intermittent, not a total loss. The user also reported a "select
    all" at the same moment; its cause is not known. No oscilloscope or logic
    analyser is available, so the firmware counters (P3.22) become the main
    instrument. The revised diagnosis is in P4.0a.
    Update (2026-11-18, first `SKYSTATE health` capture — build `1c8bbb2`
    flashed and running). The counters delivered their verdict, and it is
    not any of H1–H6 as ranked. Captured readings (printed every 2 s;
    uptime 883–909 s; counts are cumulative since boot): polls=67390,
    ts_low=67390 (100.00 %), short_reads=0 (0.00 %), frames sensor=0
    status=0 fw=0 other=67390 (100 %), events pos/touch/gest/wheel all 0,
    dropped=0, ble conn=5, uptime continuous. What each reading proves:
    - short_reads=0 over ~69,000 reads: every read returned at least the
      4 header bytes, so the sensor acknowledges at 0x42 and serves bytes
      every time — power, wiring and the I2C (Inter-Integrated Circuit)
      bus electrically work. A dead, unpowered or hard-reset sensor
      would refuse to acknowledge and put short_reads at 100 % instead.
    - Boot passed (the health lines and `ble conn=5` can only print if
      configure_sensor() succeeded — it loops forever printing
      sensor_config_failed otherwise): all four runtime commands were
      acknowledged at this boot through the sketch's EXACTLY-26-byte
      acknowledge reads. The sensor returned well-formed frames at boot.
    - ts_low=100 % cumulative, from the first poll after boot: with the
      soldered 10 kΩ pull-up, a floating or loose wire reads HIGH, so
      the sensor is actively asserting data-ready — H2 ruled out, and
      the sensor is alive and wants to hand over frames.
    - frames other=100 % from the first poll: no read since boot produced
      a byte-3 message identity of 0x91/0x15/0x83. A configured sensor
      streams 0x91 continuously, so the frames it IS producing are not
      reaching the driver as valid frames — which also yields zero
      events with zero drops (H6's gate is downstream of decoding).
    Verdict: H1 eliminated (the failed-read path never ran — short_reads
    is 0 — and P3.23 releases the line on every path anyway); H2
    eliminated (the line is actively low, not floating); H5 eliminated
    (uptime continuous, no reset); H6 eliminated (nothing ever decoded
    to drop); H4 unlikely (a restarted sensor would idle the transfer
    line high, so ts_low would fall toward 0 % instead of holding 100 %,
    and no sensor_firmware line appeared); H3 not needed to explain the
    signature (the wires demonstrably carry working signals). New
    leading suspect: H7 below, with its evidence instrument P3.24 and
    its fix P3.25.
    Update (2026-11-19, T1 meter reading + boot capture from power-up).
    - T1 on the transfer (TS) line: with the hardware powered and the
      firmware running, TRFR to GND reads 15.4 mV, stable. That is
      effectively 0 V: with the soldered 10 kΩ pull-up to 3.3 V, a
      floating or loose wire reads near 3.3 V, so something on the line
      is actively pulling it to ground. Consistent with the sensor
      continuously asserting data-ready (H7's picture: it has frames to
      hand over that the over-read mangles) — but also consistent with a
      TS-to-GND short on the veroboard, which would freeze the sensor's
      message queue the same way (the sensor never sees the host's
      release edge). The meter cannot separate those two; the P3.24
      snapshot separates them (shifted 0x91 = H7's misalignment; all
      0x00 = padding on empty reads → then hunt the short).
      Discriminator available without code: with the Pico still running,
      disconnect the SENSOR end of the 3.3 V supply wire — a real short
      keeps TRFR at ~0 V, while a healthy line floats to ~3.3 V through
      the pull-up. Record which before re-soldering anything.
    - The boot capture is now on record from power-up (uptime 2 s first
      health line): `ble_resync`/`ble_connected` printed, no
      sensor_config_failed possible after that point (the sketch would
      never have reached the radio), confirming again that all four
      runtime commands were acknowledged at this boot. The health line
      repeats the 2026-11-18 signature from poll 1: ts_low=100 %,
      short_reads=0, frames other=100 %.
    - NEW evidence for P4.3/F4: five `ble_connected` events within the
      first 4 seconds of uptime (conn=1 → conn=5 across the first two
      health lines), with zero `ble_dropped` between them — the
      duplicate-connect behaviour the ledger flagged in session 2, now
      captured with clean timing. Record it in the P4.3 log analysis;
      do not change connection handling yet.
    Update (2026-11-19, loop iteration after HW_REPORT.md session 4 —
    code commit `2267497`): the report's one open failure is answered.
    - **F7 (no valid frames decode, other=100 % — P4.0a H7) — FIXED** by
      landing both §3f items in one change: P3.25 replaces the single
      132-byte I2C over-read with the Python driver's sized reads (read
      exactly 26 first; only a longer message — its own Size field says
      so — is fetched with bounded continuation reads; incomplete or
      corrupt-Size frames are never dispatched half-read), and P3.24
      adds the unknown-frame snapshot (first 8 frame bytes + the byte
      count the reads actually returned) that the health line prints as
      `other_snap=`/`other_read=`. The 132-byte Fw_Version_Info capture
      survives through the continuations (the F17 replay stays green),
      and the health line's transfer accounting now closes: short +
      sensor + status + fw + other = every transfer. See the P3.24 /
      P3.25 Done entries for the details and the red→green test
      evidence. On hardware: flash the new build and rerun T5 — the
      prediction is `frames sensor` climbing at roughly the poll rate,
      `other` near zero, and pointer/touch input reaching the laptop;
      if `other` persists, the snapshot content names the cause (its
      four signatures are in P4.0a's update below).
    - **F4/P4.3 note (five connect lines in 4 s, zero drops) — recorded,
      deferred** as the report itself defers it: the sensor-side fault is
      the gate; handle it when P4.3 runs.
    - **Report sections 5–6 (the host-side work) — moved to P4.0a's
      update below**: the supply-wire discriminator (with the Pico
      running, disconnect the SENSOR end of the 3.3 V supply wire — a
      real transfer-line-to-ground short keeps TRFR at ~0 V, a healthy
      line floats to ~3.3 V) and the next-run checklist (T5 re-capture
      from power-up, then the snapshot signatures, then the gesture
      acceptance run).
    - HW_REPORT.md is removed; its measured facts (counter captures,
      TRFR 15.4 mV, boot captures) were already recorded in the status
      snapshot entries above and stay there. 123 pytest tests;
      `run_tests.sh` 4/4; all four Pico W sketches compile (22 % flash /
      34 % RAM, unchanged).
    - No new work items discovered. One scope decision recorded in the
      P3.24 Done entry: the snapshot fires on every undispatched frame
      (a superset of the item's identity-only letter) because P3.25's
      Size validation would otherwise hide exactly the corrupt-Size
      frames H7 produces.
    Update (2026-11-19, hardware session 5 — findings recorded, NO code
    change this round: the human resolves the physical fault first). Three
    separate faults were root-caused on the bench, each with captured
    evidence; the round's full record is `HW_REPORT.md` (findings
    F8–F13). In plain language: the sensor was being fed about 1.9 V
    instead of 3.3 V, the laptop kept trying to reconnect with an
    outdated pairing key after every reflash, and on cold boots the
    device sometimes never started its radio at all because it waits for
    the half-fed sensor:
    - **The sensor-side root cause is FOUND AND MEASURED — the Skywriter
      board is starving.** With the Pico running and everything plugged
      in, the sensor's own supply pins read VCC-to-GND **1.871 V**
      (expected ~3.3 V), Skywriter-GND-to-Pico-GND **0 V** (ground
      solid), and Skywriter-VCC-to-Pico-3V3OUT **−1.463 V**: the supply
      path (Pico pin 36 → wire → veroboard trace → pin-header contact →
      Skywriter VCC) drops ~1.46 V and the MGC3130 runs at ~1.9 V. One
      starved chip explains every sensor-side fact in this ledger: the
      all-zero padding reads (a starved sensor queues no data frames),
      TRFR at 15.4 mV with the sensor plugged in and 3.3 V with it
      UNPLUGGED (an undervolted chip drags its data-ready line low; the
      Pico/veroboard segment is proven healthy — H3's short variant is
      ELIMINATED), the I2C (Inter-Integrated Circuit) acknowledgements
      still happening at boot (the digital core limps at low voltage),
      the cold-boot acknowledge failures (P3.26), and the intermittency
      since the veroboard move (a marginal contact that varies with
      handling). It also explains the passing 2026-11-17 static check:
      "3.3 V at the sensor end of the supply wire" was measured at the
      wire, not on the Skywriter itself — the drop lives across the
      pin-header contact.
    - **H7 is REFUTED on hardware.** The P3.24/P3.25 build's T5 rerun
      shows `other=100 %` with `other_snap=00:00:00:00:00:00:00:00` and
      `other_read=26` — reads complete, content all zero: "padding on
      empty reads", the signature table's own branch for a sensor with
      nothing queued, NOT misaligned framing. P3.25's sized reads stay
      as correct read hygiene; the desynchronisation they were blamed
      for never existed.
    - **The post-reflash Bluetooth bounce is root-caused and resolved
      host-side.** The laptop still held the 2026-11-08 pairing while
      the Pico had been reflashed several times, so every auto-reconnect
      died at the security step before the host subscribed to the HID
      (Human Interface Device) reports — serial showed `pace` lines
      (radio-level connections) at ~1.4 per second with ZERO
      `ble_connected` (`ble conn=0` on every health line). Forget +
      re-pair on the laptop stopped it; the link then held (conn=5,
      disc=0). Leading mechanism (not byte-proven): the core's bond
      store lives in a flash section appended after the firmware image,
      so a reflash that changes the image size orphans the Pico's
      stored pairing while the laptop keeps hers. Operational caveat
      for AC-BLE-06 and every future round: after each reflash, expect
      to re-pair on the host — and never run the bond-persistence test
      with a reflash in between.
    - Also captured this round: the full fresh-pairing btmon trace
      (radio evidence for AC-BLE-01/02 and P3.18's pacing machinery
      accepted on air at 15 ms), the duplicate-connect mystery SOLVED
      (the opened callback fires once per notification-enable write —
      P4.3's session-5 note), a PROBABLE PASS for AC-BLE-06, and the
      cold-boot invisible-device fault with two failure captures
      (P3.26). New items opened in §3g: P3.26 (the boot gate must
      never make the device invisible), P3.27 (the connect drain runs
      once per link, not once per subscription), P3.28 (`SKYSTATE
      ble_dropped reason=`).
    Update (2026-11-24, hardware round 5 RESOLVED — no code change; the
    round's `HW_REPORT.md` F15/F16 hold the record). The sensor-side
    saga is closed: the root cause was the solid-core wire feeding 3V3
    from the Pico to the veroboard — PART-BROKEN, reading 3.3 V
    unloaded but collapsing to 0 V under a 330 Ω (~10 mA) test load;
    at the sensor's ~20 mA the same break produced F13's 1.87 V
    brown-out equilibrium. Replaced with stranded wire 2026-11-24; the
    sensor now streams ON PICO POWER ALONE. The interim
    bench-power-supply experiment (2026-11-23) had already exonerated
    the Pico's regulator (its pin held ~3.33 V under load; 20 mA
    against a ~300 mA-class budget; session 1 streamed on the same
    regulator) and re-localised the drop upstream of the header (the
    veroboard rail read 1.87 V with the supply off, 3.3 V with it on,
    one fixed point, no touching — the header contact was never the
    fault, and the withdrawn "second 3V3 position" advice never
    applied: the board is the 6-pin version). Post-fix health capture:
    `ts_low=0.00 %`, `short_reads=0`, `frames sensor` climbing while
    gesturing, events pos/touch/gest counting, HID (Human Interface
    Device) button/wheel/key/media reports climbing, `dropped=0`,
    `ble conn=5 disc=0`, transfer accounting exact (`ts_low 244 =
    sensor 229 + other 15`). **AC-BLE-06 is an OFFICIAL PASS**
    (2026-11-23 btmon: `LE Start Encryption` with the stored key,
    `Encryption Change: Enabled with AES-CCM`, no SMP Pairing Request,
    after the laptop's Bluetooth off/on). P4.0a is closed (Done
    section) and P4.0 — the gesture acceptance run — is unblocked;
    the loop's next open items are §3g's P3.26–P3.28.
    Update (2026-11-25, loop iteration after HW_REPORT.md round 5): the
    report's record is consumed into this ledger and the file is removed
    (PROMPT.md protocol: facts live here, the file exists only between the
    hardware loop writing it and the inner loop consuming it). Outcome by
    finding: F8–F16 were already recorded here and in the Done entries
    (H7 refuted, the Bluetooth bounce root-caused host-side, the fresh-
    pairing radio evidence, AC-BLE-06's official pass, the supply starvation
    measured and fixed — the part-broken 3V3 feed wire, F16); F17/F18 are
    the 2026-11-25 acceptance sessions recorded in P4.0's item (still hand
    completely quiet — the "noisy sensor" hypothesis is dead for the still
    case and the host-facing output is event-driven; every close-range
    touch channel works end-to-end; hover-range motion produced NOTHING —
    hypotheses (i)–(iii) in P4.0; AirWheel verdict deferred behind hover
    detection; the pointer channel still awaits a moving-hover proof). No
    new code-fixable failure came out of the round that is not already a
    work item: the open items are P3.26 (closed this iteration), P3.27,
    P3.28 and P3.29. `bash run_tests.sh` green 4/4, 131 pytest tests; the
    SkywriterController sketch compiles at 22 % flash / 34 % RAM (unchanged).
     Update (2026-11-25, P3.27 commit `b5e5a49`): the connect drain is
     latched per link — the battery refresh + neutral resync report run
     ONCE per link (the stack's opened callback fires once per
     notification-enable write, four to five per connection), the latch
     clears on link loss so the next link drains again, and the health
     line's `ble conn=` counts real links instead of subscription
     writes. specs/ble_hid.md §6 gained the P3.27 implementation note;
     3 new source pins in tests/test_firmware_sketch.py (verified
     failing against the unlatched sketch first); 134 pytest tests;
     `run_tests.sh` green 4/4; the sketch compiles at 22 % flash / 34 %
     RAM (unchanged). On hardware (next reflash): expect exactly ONE
     battery notification + ONE neutral-report pair per connection in
     the btmon capture, and `ble conn=` incrementing by one per link —
     and remember the reflash/pairing caveat (re-pair on the laptop).
    Update (2026-11-25, P3.28 commit): the `SKYSTATE ble_dropped` line now
    names WHY the link dropped — the radio's own disconnection reason code
    plus a human-readable name (`reason=0x13 remote_user_terminated`,
    `reason=0x06 key_missing`, …) — and the `specs/ble_hid.md` §6 Link-loss
    row gained the matching implementation note. The remaining §3g item is
    P3.29; on hardware (next reflash): after any link loss, the dropped
    line itself says the cause — check it against btmon's own
    disconnection report and remember the re-pair-after-reflash caveat.
    Update (2026-11-25, P3.29 commit `672e128`): the per-event evidence
    line is live — the device-side instrument the acceptance session's
    two unanswerable questions asked for, plus the sensor's own health
    bits that neither driver had ever surfaced. What landed:
    - **SKYTRACE** — one compact serial line per DISPATCHED sensor
      event: `pos x= y= z=`, `touch code= zone= family=`,
      `gest code= class= edge=`, `wheel deg=`; every line ends with the
      per-frame context `aw_valid= aw_cnt= sys=0xNN noise= clip=` (the
      AirWheel validity flag + raw free-running counter, and the RAW
      SystemInfo byte with bit 4 EnvironmentalNoise and bit 5 Clipping
      decoded — the sensor's own health report, now public driver state
      `last_sysinfo`, set on EVERY frame before the validity branches so
      it survives even when no payload field is valid). Compile-time
      gated, OFF by default (the 200 Hz position path stays quiet);
      enabled for an acceptance-run build with
      `SKYWRITER_EVENT_TRACE=1 ./pico-arduino/flash.sh …` (flash.sh
      forwards it as `-DSKYWRITER_EVENT_TRACE=1` through
      `--build-property build.extra_flags=` — this arduino-cli 1.x has
      no `--build-flags` flag), position lines rate-limited to one per
      50 ms even when enabled. Verified on-target: the default Pico W
      build contains zero SKYTRACE strings, the traced build contains
      them (+536 bytes).
    - **The always-on health line** gained `sysinfo=0xNN noise= clip=`
      after `other_read=` — the latest sensor frame's SystemInfo byte
      and its two health bits, ungated, so the hover-deafness evidence
      (P4.0 hypothesis (g)) is visible in every build.
    - specs/ble_hid.md §6 gained the P3.29 implementation note; 9 new
      tests (6 sketch pins + the behavioural
      tests/test_driver_sysinfo.py host test through the real poll())
      verified failing first; 148 pytest tests; `run_tests.sh` green
      4/4; all four sketches compile.
    On hardware (next reflash): build with
    `SKYWRITER_EVENT_TRACE=1 ./pico-arduino/flash.sh
    pico-arduino/SkywriterController`, remember the re-pair-after-reflash
    caveat, then rerun the acceptance exercises — the SKYTRACE touch
    lines answer which ZONE every tap landed in, `aw_valid=`/`aw_cnt=`
    answer whether a rotation attempt ever produced AirWheel-valid data,
    and `noise=`/`clip=` on both the trace and the health line surface
    the sensor's environment health during the hover experiments. New
    open item P3.30 (the Raspberry Pi Python driver should surface the
    same SystemInfo byte for the P4.0 hypothesis (iii) cross-check).
    Update (2026-11-25, P3.30 commit `1f901f7`): the Raspberry Pi Python
    driver now surfaces the same SystemInfo health byte the Arduino side
    has printed since P3.29 — every decoded sensor-data frame records the
    raw byte as the `skywriter.sysinfo` module state, set before the
    validity branches so the bit 4 EnvironmentalNoise and bit 5 Clipping
    health bits survive frames where nothing else is valid; named bit
    constants (SW_SYS_POSITION/AIRWHEEL/NOISE/CLIPPING/DSP_RUNNING)
    replace the bare bit patterns in the two validity checks. The P4.0
    hypothesis (iii) Raspberry Pi cross-check can now read the same
    evidence on the sensor's native platform. 4 new offline tests
    (tests/test_driver_sysinfo_python.py, the Python twin of the C++
    test_driver_sysinfo.py) verified failing first; 152 pytest tests;
    `run_tests.sh` green 4/4; all four sketches compile unchanged.
    With P3.30 every §3 software item is done — the remaining open items
    are all Phase 4 (hardware) or Phase 5 (gated on hardware), so this
    iteration wrote the `READY_FOR_HW` marker for the P4.0 acceptance
    run.
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
- [x] W8 → done, moved to the Done section below.

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
- [x] P3.21 → done, moved to the Done section below.
- [x] P3.22 → done, moved to the Done section below.
- [x] P3.23 → done, moved to the Done section below.

### 3f — Post-counter items (opened 2026-11-18 from the first SKYSTATE
health capture; evidence and verdict in P4.0a's 2026-11-18 update,
new leading suspect H7)

- [x] P3.24 → done, moved to the Done section below.
- [x] P3.25 → done, moved to the Done section below.

### 3g — Post-supply items (opened 2026-11-19 from hardware session 5;
evidence and verdicts in P4.0a's and P4.3's session-5 updates and the
round's `HW_REPORT.md`)

- [x] P3.26 → done, moved to the Done section below.
- [x] P3.27 → done, moved to the Done section below (commit `b5e5a49`).
- [x] P3.28 → done, moved to the Done section below.

### 3h — Acceptance-run items (opened 2026-11-25 from the first P4.0
acceptance session; evidence in P4.0's 2026-11-25 update)

- [x] P3.29 → done, moved to the Done section below (commit `672e128`).
- [x] P3.30 → done, moved to the Done section below (commit `1f901f7`).

## Phase 4 — Outer hardware loop (host-side; container cannot verify)

The container can *write* these files but only the host can *run* them. Each
item names what needs the Pico W plugged in.

- [x] P4.0a → done, moved to the Done section below.
- [ ] P4.0 **GATE — haphazard pointer (first finding of hardware session 1,
      2026-11-08)**: the Skywriter pairs and reacts, but the cursor motion,
      clicks and scrolling seemed haphazard and incoherent, so it is not yet
      usable as a mouse. Blocks P4.5 (feel tuning) and the AC-BLE-08 smoke
      test. Needs a person at the board: the loop can prepare the capture
      tooling (P4.1) but cannot close this item alone.
      Update (2026-11-24): P4.0a is RESOLVED — the sensor streams and
      input reaches the laptop (the fault was physical: a part-broken
      solid-core 3V3 feed wire, replaced on the bench; see P4.0a's
      Done entry and `HW_REPORT.md` F16). This acceptance run is
      unblocked; run it on the current build with NO reflash (keeps
      the laptop's fresh pairing). Fold in the fresh counter
      observations: position events fire (pos=83) but
      `hid pointer=0` so far — the hand was still, so confirm pointer
      reports with a deliberate MOVING hover; AirWheel is untested
      (`events wheel=0` — the wheel reports seen come from the §6
      touch-hold auto-scroll rows); compare a sustained hover's frame
      rate against the ~200/s expectation.
      Acceptance session 1 (2026-11-25, current build `2267497`, ~9 h
      uptime, link held conn=5 disc=0 throughout — its longest run on
      record; the transfer accounting stayed exact the whole session,
      e.g. ts_low 506 = sensor 482 + other 24). Three exercises; the
      counters cannot separate the rotation and tapping exercises
      inside the active window, so their deltas are reported together:
      - **Still hand (30 s): completely quiet.** Zero data-ready
        pulses, zero frames, zero events, zero reports — no noise, no
        jitter, no stuck buttons. Hypothesis (a) is dead for the still
        case: a still (or absent) hand generates nothing at all. It
        also settles the frame-rate question: the host-facing output
        is EVENT-DRIVEN — the earlier "~200/s streaming" expectation
        described the sensor's internal sensing rate, not the bus
        (2026-11-24's activity bursts ran 5-20 frames/s; a still hand
        sends nothing).
      - **Rotation in the air + tapping all six edges (the active
        window): touch +24, button transitions +42, everything else
        FROZEN** — zero AirWheel events (`events wheel=0` still),
        zero wheel reports, zero keyboard events, zero media events,
        position events frozen at 83.
        - AirWheel: the sensor configuration is now verified against
          the vendor's own table — the sketch's AirWheel-enable
          payload (0xA2/0x90, args 0x20/0x20) is byte-identical to
          Interface.pdf's own "AirWheel Enable" command listing, and
          the data-output mask 0x1F includes bit 3 (AirWheel) and
          bit 4 (position). The datasheet's activation rule:
          "continuously performed circles inside the sensing area",
          recognized "after at least one quadrant of a circle". The
          touches firing during the attempt mean the fingers were in
          TOUCH range and the touch recognizer took over. Next
          technique: hover over the centre WITHOUT touching and
          rotate one full continuous circle — the goal is a rotation
          with `events touch` staying frozen. Interpretation note
          from the interface guide: while AirWheel is enabled and
          active the sensor disables position output, so frozen pos
          during a WORKING rotation is expected — frozen pos alone is
          not evidence of AirWheel.
        - Edge taps: no touch event with a north/south zone
          dispatched in ANY family — a north/south tap would send
          Page Up/Down (key), a hold would auto-scroll (wheel), a
          doubletap would track-skip (media); all three counters are
          frozen. The rows and the keyboard path are replay-proven
          (fixtures F28/F29 + the P3.21 fix), so the gap is upstream:
          the taps did not land (or did not classify) as north/south
          touches — the 6-pin Skywriter's edge zones are only
          millimetres wide, making missed taps the leading suspect,
          board orientation second. The aggregate counters cannot
          separate those: run the per-edge laptop-side check (one
          physical edge at a time, evtest or hid-recorder, note which
          action fires), and P3.29 adds the device-side per-event
          evidence line.
      - **The pointer is STILL the unproven channel** — no
        hover-MOVING exercise happened this session. It remains the
        top item: hold a hand a few centimetres up and move it;
        expect `events pos` AND `hid pointer` climbing together.
      Acceptance session 1, second exercise (2026-11-25, same boot,
      ~9.3 h uptime): **tight circles in both directions at various
      hover heights — and the sensor sent NOTHING: zero data-ready
      pulses in 40+ s** (ts_low, frames, touch and pos all frozen).
      This reframes the AirWheel question: the sensor is not
      registering hover-range presence AT ALL, so no recognition
      (AirWheel or otherwise) can even begin. The pattern across all
      sessions: touch-range activity always registers (700+ touch
      events); hover-range recognition has produced events exactly
      ONCE — the first ~4 minutes of the 2026-11-24 boot (pos=83 +
      gest=1, likely whole-hand motion) — never again in 10+ h; both
      deliberate hover exercises (rotation at touch range → touches;
      rotation at hover range → silence) produced zero position or
      gesture events. Hypotheses, in test order:
      - (i) **The tested motion is below the sensor's hover-detection
        envelope** — a fingertip making tight circles is a small
        target; the one working window was likely whole-hand
        movement. Discriminator: flat OPEN PALM, slow sweeps and
        circles at 2-10 cm — watch `events pos` (this doubles as the
        pointer test: expect `hid pointer` climbing too).
      - (ii) **Baseline drift with auto-calibration disabled** (the
        sketch sends the Python driver's default
        disable-auto-calibration command): long-range approach
        detection is the first function to go deaf when the baseline
        drifts while short-range touch keeps working — matching the
        observed pattern IF the palm test also fails. Discriminator:
        power-cycle the Pico (safe now — the supply is fixed and the
        bond survives power cycles, AC-BLE-06 officially passed;
        expect `sensor_ok` and the laptop reconnecting by itself),
        then IMMEDIATELY palm-sweep. Fresh-boot hover that works and
        later fades = drift → open a work item on the calibration
        default; fresh-boot hover that also fails = go to (iii).
      - (iii) **Environmental noise or a detection-limit problem in
        the sensor's environment/setup** — the sensor's own
        SystemInfo word carries EnvironmentalNoise (bit 4) and
        Clipping (bit 5) health bits that NEITHER driver currently
        surfaces (P3.29's evidence line will print them). If palm
        hover fails even fresh-booted, the Raspberry Pi cross-check
        with the stock Python driver (the sensor's native platform)
        decides our-config vs the sensor/board, with P3.29's event
        line and P4.6's real-frame capture as the instruments.
      AirWheel verdict is DEFERRED until hover detection works: both
      attempts so far never reached the recognizer (touch range → the
      touch recognizer took over; hover range → nothing was seen at
      all).
      Reported symptoms (session 1, Linux/BlueZ laptop): the cursor jumps or
      teleports; it moves the wrong way or along the wrong axis; keyboard and
      media keys fire. Clicks and scrolling were not listed as symptoms. The
      typed letters are a separate, code-traced defect (P3.21) and are not part
      of this diagnosis.
      Diagnosis order (evidence before changes — do not retune `GAIN` or
      `JUMP_THRESHOLD` until the measurements show whether noise is the cause):
      1. Serial evidence: capture the console from power-up through a 30 s
         hand-still period and a slow 30 s swipe. Confirm `SKYSTATE sensor_ok`,
         `hid_started`, the `pace report_interval_ms=` line on connect, and
         no `sensor_config_failed`.
      2. Sensor side: log the raw x/y/z values for the same two periods. Hand
         still: are values near zero (noise) or large? Hand moving: how many
         per-frame jumps exceed `JUMP_THRESHOLD` (8192 raw), and how many frames
         per second arrive (expected ~200)?
      3. Host side: count the mouse reports the laptop receives per second, and
         check cursor direction and axis per swipe, against the sensor log.
         Late or missing reports point at the connection-interval pacing (P3.18)
         or at dropped movement.
      4. Channel separation: repeat each gesture alone — pointer only, touch
         centre (a hold holds the left button, §6), tap, AirWheel rotation
         (scroll), flick (volume and track keys). Find which channel produces
         the unintended behaviour.
      Hypotheses to test, not assumptions: (a) sensor noise amplified by
      `GAIN` 1/256 and an 8192-unit `JUMP_THRESHOLD`; (b) an x/y sign or axis
      mismatch between sensor and mouse report; (c) an unintended touch hold
      or auto-scroll row firing during a swipe; (d) uneven report delivery
      from the connection-interval handling (P3.18); (e) a sensor
      configuration or frame-read problem (P3.11b/c, P3.16) corrupting
      positions; (f) spurious flick or circle gestures from sensor noise
      firing the track and volume keys (the media-key symptom — check with the
      channel-separation step: flicks alone, then a still hand);
      (g) hover-detection deafness — the sensor not registering
      hover-range presence at all (fingertip below the detection
      envelope, baseline drift with auto-calibration disabled, or
      environmental noise per the sensor's own SystemInfo bits) —
      added 2026-11-25, see the acceptance session notes (where (a)
      is already dead for the still-hand case).
      Closure: the cursor moves smoothly and in the expected direction; no
      clicks or scrolls happen unless a deliberate gesture is made; the cause
      is recorded in `HW_REPORT.md` with the captured logs. If the firmware
      contradicts an acceptance criterion (AC-MAP-01, AC-BLE-04), add the
      deviation row to `specs/README.md` in the same change that fixes it.
- [ ] P4.1 `hw/serial_probe.py` (host, needs `pyserial`): flash a test sketch
      via `pico-arduino/flash.sh`, capture the USB serial port, assert boot
      banner, sensor frame streaming and framing. Hardware-check notes:
      (P3.25, superseding the old P3.11b single-request note) the shared
      Arduino library's `poll()` now reads EXACTLY 26 bytes first and
      fetches a longer message with continuation reads bounded by the
      frame's own Size field while the transfer line is still asserted —
      the Python driver's P3.11c pattern, replacing the 132-byte request
      whose over-read was hardware session 4's leading suspect (P4.0a H7,
      `other=100 %` from the first poll). Confirm on hardware: sensor
      frames stream intact (the P4.0a T5 prediction — `frames sensor`
      climbing at roughly the poll rate, `other` near zero), and the
      sensor's I2C buffer really does continue across the separate read
      transactions of one asserted transfer (the fixture replay proves
      the driver-side arithmetic only; the 132-byte version frame must
      still arrive complete as 26 + 32 + 32 + 32 + 10).
      (P3.11c) the Raspberry Pi Python driver now sizes its reads from the
      frame's Size field and fetches frames longer than the first 26-byte
      read with chunked continuation reads (26 + 32 + 32 + 32 + 10 for the
      132-byte Fw_Version_Info frame) while the transfer (TS) line is still
      asserted — confirm on a real sensor that the I2C buffer really
      continues across separate read transactions of one asserted transfer
      (the fixture replay only proves the driver-side arithmetic), and that
      the RPi Linux SMBus 32-byte single-call cap is respected.
      Session 1 (2026-11-08): the sensor was detected on the I2C bus — partial
      evidence only. The serial boot lines were reported as all present, but
      no capture file exists yet, so the banner, frame streaming and
      whole-frame read checks are not yet recorded.
      Session 3 (2026-11-16): no sensor-frame evidence since the permanent
      rewiring; P4.0a T3 and T5 supply it.
- [ ] P4.2 `hw/ble_hid_probe.py` (host, needs `bleak` + the host's Bluetooth
      radio): automate scan/GATT/pairing/services — target `AC-BLE-01`,
      `AC-BLE-02`, `AC-BLE-03`.
      Session 1 (2026-11-08): the scan lists `Skywriter HID` (AC-BLE-01, name
      part only — "exactly one instance" not yet checked); pairing with a
      laptop succeeded (AC-BLE-03, pairing part only). Not yet checked: the
      single composite HID device and its Report Map (AC-BLE-02), and the
      Device Information reads and battery = 100 % (AC-BLE-03).
      Session 5 (2026-11-19): the fresh-pairing btmon capture is on
      record — the advertisement carries the name + HID service UUID +
      HID appearance (AC-BLE-01's content), and the GATT (the Bluetooth
      service database) enumeration shows ONE composite HID service with
      five Report characteristics (four input with notify, one output)
      plus a 171-byte Report Map, Boot Keyboard/Mouse, HID Information
      and Control Point (AC-BLE-02's structure evidence). The automated
      single-instance and Device Information reads still need this
      probe's own run (P4.3's session-5 note holds the pairing/battery
      evidence).
- [ ] P4.3 `hw/ble_hid_probe.py` lifecycle part: latency/report-rate/
      reconnect/bond — `AC-BLE-04`, `AC-BLE-05`, `AC-BLE-06`, `AC-BLE-07`.
      Bond persistence (`AC-BLE-06`) answers `ble_hid.md` §5 open question 1.
      2026-11-05 P3.17b expectation note: the Core's bond store is verified
      FLASH-BACKED at the code level (see the P3.17b Done entry), so the
      probe should EXPECT "bonded host reconnects after a Pico W power
      cycle WITHOUT re-pairing" to PASS; record a spec-deviation row only
      if the radio behaves otherwise.
      Session 1 (2026-11-08): not started. The power-cycle reconnect (AC-BLE-06)
      has not been tested; only one laptop pairing has been done.
      Session 2 (2026-11-09): the log showed `ble_resync` and `ble_connected`
      twice with no `ble_dropped` between. Open: a silent drop, a reset (P4.0a
      H5), or a second connection? Check the P4.0a T3 log before changing the
      connection handling. The same log began with `ble_dropped`,
      `ble_advertising` and `waiting_for_host`, so a link drop happened before
      the first visible connection.
      Session 4 (2026-11-19): the duplicate-connect behaviour is now captured
      with clean timing from power-up — five `ble_resync`/`ble_connected`
      pairs within the first 4 seconds of uptime (the sketch's connect
      counter goes conn=1 → conn=5 across the first two health lines) with
      ZERO `ble_dropped` between them, and uptime continuous (no reset, H5
      ruled out for these). So the Bluetooth stack is reporting several
      connection events in a row while the sketch sees no disconnect — see
      P4.0a's 2026-11-19 update. Analysis and any fix stay deferred: the
      sensor-side fault (H7) is the gate; handle this when P4.3 runs.
      Session 5 (2026-11-19): three findings, all captured.
      - **The post-reflash connect/disconnect bounce is root-caused and
        resolved host-side.** The laptop still held the 2026-11-08
        pairing while the Pico had been reflashed several times, so the
        laptop's auto-reconnect died at the security step before ever
        subscribing to the HID (Human Interface Device) reports —
        serial: `pace` lines (radio-level connections) at ~1.4/s,
        `ble_dropped`/`ble_advertising` pairs, ZERO `ble_connected`
        (`ble conn=0` on every health line); the laptop UI showed the
        device appearing and disappearing and manual attempts reported
        "le-connection-abort-by-local" (the host giving up on a device
        that was not answering). Forget + re-pair on the laptop stopped
        it; the link then held (conn=5, disc=0 across 30 s). Leading
        mechanism (not byte-proven): the core's bond store lives in a
        flash section appended after the firmware image, so a reflash
        that changes the image size orphans the Pico's stored pairing
        while the laptop keeps hers. **Operational caveat for AC-BLE-06
        and every future round: after each reflash, expect to re-pair
        on the host — never run the bond-persistence test with a
        reflash in between.** Honest evidence note: the failing link's
        HCI (Host Controller Interface) reason code was never captured
        (the fix was applied first); P3.28 adds the device-side reason
        line.
      - **The fresh-pairing btmon trace is on record — the round's
        radio evidence.** Advertisement: `Skywriter HID`, HID service
        UUID 0x1812, HID appearance (AC-BLE-01 content). Connection at
        45 ms, then the sketch's L2CAP connection-parameter request
        ([7.5, 15] ms, supervision 480 ms) ACCEPTED and applied →
        15.00 ms — P3.18's pacing machinery verified ON AIR (the radio
        proof behind the `pace report_interval_ms=15` line). GATT
        enumeration: Generic Access, Battery, Device Information, ONE
        HID service with five Report characteristics (four input with
        notify, one output), Report Map 171 bytes, Protocol Mode, Boot
        Keyboard/Mouse, HID Information, Control Point (AC-BLE-02
        structure). Pairing: SMP (Security Manager Protocol) Just Works
        → encryption enabled → keys distributed and stored on BOTH
        sides (the bond). Battery notifications read 0x64 = 100 %, and
        the neutral resync reports went out on air (AC-BLE-03's battery
        half, AC-BLE-07's resync half).
      - **F4/the duplicate-connect behaviour is SOLVED** — the mystery
        this item has carried since session 2. The core's opened
        callback fires once per notification-enable write, and the host
        writes four to five of them per connection (the report
        channels' enable switches); the btmon capture shows the
        sketch's connect drain (battery refresh + neutral resync)
        running after EACH write — four battery notifications and four
        neutral-report pairs on ONE link. So sessions 2 and 4's "five
        `ble_connected`, zero `ble_dropped`" was one link with five
        subscription writes, and session 5's `conn=5, disc=0` is the
        same thing. F4 is closed as EXPLAINED — no connection handling
        to change; the cosmetic fix is queued as P3.27 (latch the
        drain per link; LANDED 2026-11-25, commit `b5e5a49` — see the
        P3.27 Done entry).
      - **AC-BLE-06 (power-cycle bond persistence): PROBABLE PASS —
        the earlier failures were never the bond.** On a cold boot
        whose sensor gate passed, the laptop auto-connected BY ITSELF
        with no re-pairing (the user watched it happen; conn=5,
        disc=0). The earlier "power cycling does not work /
        abort-by-local / invisible in scans" attempts were all against
        boots that never came up — the sensor-acknowledge boot gate
        (P3.26's two `sensor_config_failed` captures; no radio
        started, no advertisements on air — the session-5 scan capture
        confirms it directly: two other devices visible, zero from the
        Pico). To make AC-BLE-06 official: one more gate-passing cold
        boot with the laptop untouched and btmon running —
        `LE Start Encryption` with the stored key (no SMP Pairing
        Request) is the pass signature.
        Update (2026-11-23): **AC-BLE-06 is an OFFICIAL PASS** — the
        exact predicted capture exists: with the laptop's Bluetooth
        turned off and on (laptop otherwise untouched, btmon running),
        the link came back as `LE Start Encryption` carrying the
        stored long-term key, `Encryption Change: Enabled with
        AES-CCM`, and NO SMP Pairing Request anywhere in the trace.
        The bond survives host power cycles; the re-pair caveat above
        applies to reflashes only. The same session's health capture
        showed the link surviving the off/on at conn=10 disc=1 (the
        drain counting per subscription write, P3.27's known
        semantics).
- [ ] P4.4 Outer loop driver `ralph_hw.sh` + `HW_REPORT.md` protocol: run the
      inner loop until `READY_FOR_HW`, flash + probe, write `HW_REPORT.md`
      (pass/fail + captured logs), commit; `ralph.sh` clears `READY_FOR_HW`
      on its next start once `HW_REPORT.md` exists. The file's life is
      exactly one round: the hardware loop writes it, the inner loop
      records the outcome here and REMOVES it (PROMPT.md protocol — done
      for round 5 on 2026-11-25).
      Note (2026-11-19): the `ff5d36f` retirement of `HW_REPORT.md` broke
      this handshake — `ralph.sh` refused to consume the `READY_FOR_HW`
      marker without the file. `HW_REPORT.md` is recreated with the session-4
      results (2026-11-18/19 counters, boot capture, TRFR voltage 15.4 mV;
      failures F7 → P3.24/P3.25). The file is part of the protocol and must
      be written for every hardware round; retiring it again would deadlock
      the inner loop the same way.
- [ ] P4.5 Manual checks: `AC-BLE-08` multi-OS smoke test and gesture feel
      tuning (`GAIN`, `JUMP_THRESHOLD`, `TOUCH_RELEASE_MS` — record final
      values back into `specs/hid_mapping.md` §3). Blocked by P4.0: tuning
      means nothing until the pointer moves coherently.
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

## Manual actions (human, not loop work)

The loop must skip this section. Each item needs a person or the host, so none
of them is a checkbox the loop can pick up:

- Attach the session-1 evidence: the serial console capture (the `SKYSTATE`
  lines, from power-up and during the haphazard use), the laptop's Bluetooth
  or mouse event log for the same period, and the laptop's operating system
  and Bluetooth stack. Needed for P4.0 and P4.1.
- On the Linux laptop, record the raw HID input from the Skywriter during a
  short session (for example `hid-recorder` from hid-tools, or `evtest` on the
  Skywriter's input device node), in three parts: a still hand, a slow swipe,
  and one tap per zone. Attach the output. This separates pointer, key and
  media reports for P4.0 step 3 and checks AC-BLE-02's composite report layout.
- Install the host tools for Phase 4: `pyserial` and `bleak` (see the Phase 4
  hardware notes in the status snapshot).
- Make the scripts executable on the host: `chmod +x ralph.sh run_tests.sh`
  (chmod is blocked in the container).
- Rebuild the `skywriter-dev` image on the host and confirm the C++ compiler
  install (`g++ musl-dev` in the Dockerfile) so `run_tests.sh` works in a fresh
  container without the manual `pip install --user ziglang` (P3.1 environment
  note). Retire the ziglang fallback only after that is verified.
- Resolve the `ralph-dry-run` branch (W7b): merge it into `pico-ble`, or run
  `git push --set-upstream origin ralph-dry-run` once.
- Session 3 checks (2026-11-16/17), in this order, without changing the wiring
  in between:
  1. T0: power off, multimeter continuity check of the veroboard, with the wire
     list and the bridge check. Confirm the sensor is supplied from pin 36.
  2. T1: power on, multimeter DC volts on SDA, SCL, TS and reset (and MIN/MAX on
     TS if the meter has it). Record every reading.
  3. T3: the full serial log, with the logger running when the board boots.
  4. T4: `hid-recorder` or `evtest` on the Linux laptop, during a still hand, one
     slow swipe and one tap per zone.
  5. After P3.22 and P3.23 are implemented, flash the diagnostic build with
     `pico-arduino/flash.sh`, keep the monitor running, then run T5 and T6.
  Steps 1 and 2 passed on 2026-11-17 (static checks, see the P4.0a answers
  above). Do not change the wiring again until steps 3 and 4 are recorded.
- Answers recorded 2026-11-17 (HW_REPORT.md section 6 holds the detail):
  - Multimeter reference: probe on 3V3. TRFR exactly 0 V difference (idle
    high); SDA, SCL and RESET near 0 V difference (idle high).
  - Each signal reaches its intended Pico pin; no solder bridges.
  - Pull-up resistors: soldered on the veroboard between 3V3 and each signal's
    rail. Measured 2026-11-17 with the board powered off: SDA 4.69 kΩ, SCL
    4.67 kΩ, TRFR 10.00 kΩ, RESET 10.00 kΩ.
  - Sensor-end supply: 3.3 V at the end of the supply wire (from pin 36).
  - The "N" and "select all": the hand was on the sensor's north side; the
    "select all" looked like Ctrl+A when the fingers were at the sensor's
    edges. The cause is not known. Hypothesis for P3.21: a modifier bit or a
    stuck key in the keyboard report.
- Session 5 bench steps (2026-11-19), in this order, NO reflash needed
  (keep the current build and the laptop's fresh pairing; fix the
  sensor's starving supply first, then re-test):
  1. Pico running, Skywriter plugged in: measure 3V3 at the
     veroboard-side of the header socket — expect ~3.3 V; this
     localises the ~1.46 V drop to the socket-to-pin contact.
  2. Re-seat the Skywriter in the pin header several times (contacts
     self-clean somewhat), then re-measure VCC on the Skywriter —
     expect ~3.3 V.
  3. Still sagging: reflow the 3V3 socket's solder joint on the
     veroboard, or clean/re-tension the contact.
  4. If that header position is simply worn: with power OFF, check
     continuity from the Skywriter's VCC pin to BOTH 3V3 header
     positions (1 and 17 — a Pi HAT usually ties both); if both
     connect, feed 3V3 at the other position and leave the worn one
     unused. Always from Pico pin 36 (3V3 OUT) — never the 5 V pin
     (pin 40).
  5. With a solid ~3.3 V at the Skywriter: rerun T5 from power-up. Pass
     looks like `SKYSTATE sensor_ok` at every boot, `frames sensor`
     climbing at ~200 per second, `other` near zero, and
     `events pos/touch/gest/wheel` counting while you gesture. Then
     the P4.0 acceptance run (pointer, taps, AirWheel, flicks) — the
     Bluetooth link already holds.
  6. If power is solid and frames still do not flow: cross-check the
     Skywriter on a real Raspberry Pi (its native platform) with the
     stock Python driver — streams on a Pi = our wiring; dead on a Pi
     too = a damaged board (P4.6's real-frame capture then doubles as
     the evidence).
- Outcome (2026-11-24): RESOLVED without executing steps 3–4. The true
  fault was UPSTREAM of the header: the solid-core feed wire from Pico
  pin 36 was part-broken — 3.3 V unloaded, 0 V under a 330 Ω (~10 mA)
  test load — proven by the 2026-11-23 bench-supply experiment (the
  veroboard rail itself read 1.87 V with the supply off and 3.3 V with
  it on, one fixed measurement point, no touching) and replaced with
  stranded-core wire on 2026-11-24. Step 4's Pi-HAT advice (pins 1 and
  17) never applied — the Skywriter is the 6-pin version with a single
  3V3 pin. Step 5's T5 rerun is done (the 2026-11-24 health capture,
  `HW_REPORT.md` F16); step 6's Raspberry Pi cross-check was not
  needed.
- Do not delete `READY_FOR_HW` by hand to restart the loop. The loop would pick
  P4.0a first, and P4.0a needs the board. The loop restarts only after
  `HW_REPORT.md` exists (P4.4).
  Update (2026-11-24): P4.0a is closed, so the loop's first open item
  is now §3g's P3.26 — the loop is safe to start whenever the firmware
  work is wanted; the acceptance run can proceed in parallel on the
  current build, and after P3.26–P3.28 land and are reflashed, expect
  to re-pair on the laptop.

## Done

- P3.30 — the Raspberry Pi Python driver surfaces the sensor's own
  health byte (commit `1f901f7`). In plain language: every data frame
  the sensor sends carries a one-byte status report (SystemInfo,
  Interface.pdf §4.5 Table 4-10); two of its bits are the sensor's own
  health report — bit 4 EnvironmentalNoise ("environmental noise has
  been detected") and bit 5 Clipping ("the ADCs are clipping"). P3.29
  made the Arduino driver record it as public state (`last_sysinfo`)
  and the firmware print it; the Python driver — the sensor's native
  platform, and the one the P4.0 hypothesis (iii) cross-check would run
  on — still discarded the byte. What landed:
  - **`skywriter.sysinfo`** — module state like `gesture`/x/y/z: the
    raw SystemInfo byte of the last decoded sensor-data frame, set on
    EVERY frame BEFORE the validity branches (the Arduino
    `last_sysinfo` rule), so the health report survives even when no
    payload field is valid. Handlers read it alongside their own
    arguments — the cross-check session's `@skywriter.move()` handler
    logs the health bits per event with no new hardware access.
  - **Named constants for the byte's fields** — SW_SYS_POSITION
    (bit 0), SW_SYS_AIRWHEEL (bit 1), SW_SYS_NOISE (bit 4),
    SW_SYS_CLIPPING (bit 5), SW_SYS_DSP_RUNNING (bit 7) — mirroring
    the Arduino driver's SW_SYS_POSITION/SW_SYS_AIRWHEEL; the two
    validity checks in `_handle_sensor_data` now use them instead of
    bare bit patterns.
  - The replay harness resets `sysinfo` per session (fresh decoder
    state), and `specs/ble_hid.md` §6's P3.29 note gained the P3.30
    cross-reference (both platforms now share the evidence surface).
  - Test-first discipline held: 4 new offline tests
    (tests/test_driver_sysinfo_python.py, the Python twin of
    tests/test_driver_sysinfo.py) drive the REAL `_do_poll()` against
    a mocked bus (the P3.11c fixture pattern): a mask-0 frame carrying
    only the noise+clipping bits (0x30) dispatches nothing yet records
    the byte; the recorded F01 fixture's own byte (0x81 =
    PositionValid|DSPRunning) wins over an earlier frame's; an
    AirWheel-valid frame records its bit while baselining silently; a
    handler reads the byte DURING its own callback. All 4 verified
    FAILING against the pre-change code first (`sysinfo` did not
    exist). 152 pytest tests; `bash run_tests.sh` green 4/4; all four
    sketches compile unchanged (22 % flash / 34 % RAM).
  - On hardware: no reflash is needed for THIS change (it lives in the
    Raspberry Pi driver, not the Pico W firmware) — it equips the P4.0
    hypothesis (iii) cross-check: run this repo's Python driver on a
    Raspberry Pi with the sensor HAT and read `skywriter.sysinfo`'s
    noise/clipping bits during the same hover exercises.
- P3.29 — the per-event evidence trace is live, and the sensor's own
  health bits are surfaced at last (commit `672e128`). In plain
  language: the two-second status line's counters can say WHICH channels
  fire, but the 2026-11-25 acceptance session hit two questions they
  cannot answer — which ZONE of the board a tap landed on (every tap
  made mouse clicks, none made the Page Up / Down keys, and the counters
  cannot distinguish "the sensor never sent a north/south code" from
  "it sent one and we mishandled it"), and whether a rotation attempt
  ever produced valid rotation data at all (`events wheel=0` through
  both attempts). This item landed the device-side instrument for both,
  plus a piece of evidence the sensor has been attaching to every frame
  all along that BOTH drivers threw away:
  - **SKYTRACE lines** (the sketch, `pico-arduino/
    SkywriterController.ino`): one compact serial line per DISPATCHED
    sensor event, printed by gated helper functions called after the
    mapper dispatch in each sensor callback (the 200 Hz hot path itself
    never prints — the P3.22 rule stands, and the existing
    no-Serial-in-callbacks pin is untouched). Formats:
    `SKYTRACE pos x=… y=… z=…`, `SKYTRACE touch code=7 zone=north
    family=tap …`, `SKYTRACE gest code=4 class=1 edge=0 …`,
    `SKYTRACE wheel deg=+22.50 …`; every line ends with the per-frame
    context `aw_valid= aw_cnt=0xNN sys=0xNN noise= clip=` — the
    AirWheel validity flag + the raw free-running counter (Interface.pdf
    Table 4-10: 32 counts = 1 revolution, wraps 255→0), and the RAW
    SystemInfo byte with its two health bits decoded: noise = bit 4
    EnvironmentalNoise, clip = bit 5 Clipping — the sensor's own report
    about its environment, the candidate evidence for P4.0's
    hover-deafness hypothesis (g).
  - **Compile-time gate, off by default**: `#ifndef
    SKYWRITER_EVENT_TRACE` defaults the macro to 0 (a `-D` can
    override); every trace print lives inside a
    `#if SKYWRITER_EVENT_TRACE` region, so a default build's binary
    contains zero SKYTRACE strings (verified on-target). Even when
    enabled, position lines are rate-limited to one per
    TRACE_POSITION_INTERVAL_MS = 50 ms; touch/gesture/wheel events are
    rare and print every one. Acceptance-run builds turn the trace on
    with `SKYWRITER_EVENT_TRACE=1 ./pico-arduino/flash.sh …` — flash.sh
    forwards it as `-DSKYWRITER_EVENT_TRACE=1` through
    `--build-property build.extra_flags=…` (the repo's arduino-cli 1.x
    has no `--build-flags` flag; the first flash.sh draft used it and
    was corrected).
  - **Driver public state** (`arduino/Skywriter/`): `last_sysinfo` —
    the raw SystemInfo byte, set on EVERY decoded sensor-data frame
    BEFORE the validity branches, so the health bits survive even when
    no payload field is valid (the former code discarded the byte
    outside the two validity checks); and the AirWheel state moved from
    private to public under the names the evidence line prints —
    `airwheel_valid` / `airwheel_counter` (renamed from
    `airwheel_counter_valid` / `lastrotation`; the baseline/re-baseline
    semantics are unchanged, all replay tests stay green).
  - **The always-on health line** gained `sysinfo=0xNN noise= clip=`
    after `other_read=` — ungated, because a once-per-2 s print cannot
    flood anything and the hover-deafness evidence must be visible in
    every build without a special flash.
  - Specs: `specs/ble_hid.md` §6 gained the P3.29 implementation note
    (the trace's fields, the gate, the enable path, the rate limit, the
    health-line fields). No deviation row — nothing in the specs
    contradicts this.
  - Test-first discipline held: 6 new source pins in
    tests/test_firmware_sketch.py (the 0-default gate with every
    SKYTRACE inside the guarded region; the item's fields on every line
    kind; the 50 ms rate limit as a named constant; the gated helper
    calls following the mapper dispatch with no direct Serial prints in
    the callbacks; the health line's sysinfo/noise/clip fields placed
    between the snapshot and the events; the flash.sh acceptance knob
    with the off default) and a new behavioural host test
    (tests/test_driver_sysinfo.py + tests/cpp/host_sysinfo_main.cpp
    driving the REAL driver through its genuine poll() with crafted
    26-byte frames: the 0x30 noise+clipping byte survives a frame that
    dispatches nothing, `last_sysinfo` tracks every decoded frame, the
    AirWheel baseline stays silent with the flag/counter public, +22.50
    degrees on a +2 counter step, the flag clears when validity drops)
    — all 9 verified FAILING against the pre-change code first (the
    health byte was discarded; the AirWheel state was private; the
    trace did not exist), pass now. 148 pytest tests; `bash
    run_tests.sh` green 4/4; all four sketches compile.
  - On hardware (next reflash): build the acceptance variant with
    `SKYWRITER_EVENT_TRACE=1 ./pico-arduino/flash.sh
    pico-arduino/SkywriterController` and remember the standing
    re-pair-after-reflash caveat; then the SKYTRACE touch lines answer
    the zone question, `aw_valid=`/`aw_cnt=` answer the rotation
    question, and `noise=`/`clip=` watch the sensor's environment
    during the hover experiments (P4.0's steps).
- P3.28 — the link-loss line names its own cause (this commit): the
  `SKYSTATE ble_dropped` serial line now carries the radio's own
  disconnection reason code plus a human-readable name —
  `SKYSTATE ble_dropped reason=0x13 remote_user_terminated` — the
  Bluetooth-side twin of P3.24's unknown-frame snapshot. In plain
  language: when the wireless link to the laptop dies, something decides
  to end it — the laptop's user turning Bluetooth off, a stale pairing
  key after a firmware reflash, a watchdog that decided the other end had
  vanished. The radio reports its decision with a standard two-digit
  code, and until now the device printed "dropped" without saying why.
  Hardware session 5's connect/disconnect bounce was root-caused and
  fixed host-side before its reason code was ever captured (the btmon
  trace recorded the successful pairing instead); P3.28 makes every
  future link loss self-naming from the device side.
  - Where the code comes from: the sketch's existing BTstack HCI (Host
    Controller Interface — the radio-level event channel) event handler
    gained a case for the Disconnection Complete event and stores the
    reason through the stack's own decoding helper
    (`hci_event_disconnection_complete_get_reason`) into volatile state
    (`ble_drop_reason` + `ble_drop_reason_seen`) — written only from the
    stack's callback context, latest-wins, never reset (the drain does
    not clear it, so the next health line still reflects the last loss).
    BTstack dispatches event handlers in registration order and the
    wrapper's closed callback fires ON this same event, so the reason is
    always stored before `on_ble_closed` arms the disconnect drain that
    prints it. The handler stays flag-only (no printing, no mapper calls
    — the context rule).
  - The line: loop()'s disconnect drain prints `SKYSTATE ble_dropped
    reason=0xNN <name>` with zero-padded hex and the name from a small
    helper covering the ledger's codes — 0x06 `key_missing` (stale
    pairing, the reflash-orphaned bond), 0x08 `connection_timeout` (the
    supervision watchdog), 0x13 `remote_user_terminated` (the HOST ended
    the link), 0x16 `local_host_terminated` (this side ended it), 0x22
    `ll_response_timeout`, 0x3e `connection_failed_establish`, anything
    else `unknown`. Defensively, if no disconnection event was ever seen
    the line prints `reason=none no_hci_disconnection_event` rather than
    a fake 0x00.
  - Specs: no deviation — `specs/ble_hid.md` §6's Link-loss row says
    "report state to the serial console"; the row gained the P3.28
    implementation note recording the line format and the latest-wins
    semantics.
  - Test-first discipline held: 5 new source pins in
    `tests/test_firmware_sketch.py` (the handler decodes the event
    through the stack helper and stores it flag-only; the volatile
    declaration + latest-wins no-reset; the dropped line carries the
    zero-padded reason and name from loop() ahead of the advertising
    line; the named codes 0x06/0x08/0x13/0x16 exist with an `unknown`
    fallback) all FAILED against the pre-P3.28 sketch, pass now. 139
    pytest tests; `bash run_tests.sh` green 4/4; the sketch compiles at
    22 % flash / 34 % RAM (unchanged). On hardware (next reflash): after
    any link loss, read the cause off the dropped line and cross-check
    it against btmon's own disconnection report — and remember the
    standing caveat: re-pair on the laptop after a reflash.
- P3.27 — the connect drain runs once per link, not once per
  subscription write (commit `b5e5a49`). In plain language: when a
  computer connects over Bluetooth Low Energy (BLE), it "subscribes" to
  each report channel (pointer, buttons, wheel, keyboard, media) by
  writing one small enable switch per channel — four or five writes per
  connection — and the Bluetooth library fires the sketch's "opened"
  callback after EACH write. The connect drain (battery refreshed to
  100 % + the one neutral report that wipes the host's stale button
  state) is a once-per-link action (specs/ble_hid.md §6 "once", §8), but
  unlatched it ran after every write: hardware session 5's btmon capture
  showed ONE link producing four battery notifications and four
  neutral-report pairs, with the health line counting `ble conn=5
  disc=0` for a single link (the same mechanism that produced sessions
  2 and 4's "five connects, zero drops" — F4, closed EXPLAINED).
  - The fix: a per-link latch `ble_connect_drain_latched` (volatile —
    the stack's callback context writes it): `on_ble_opened` arms the
    drain only on the link's FIRST opened event (guard → set → arm);
    `on_ble_closed` clears the latch — the closed event precedes any
    later link by definition, so the next connection always arms its own
    drain; `loop()` never touches the latch (a loop-side clear between
    two drains would reopen the storm).
  - Effect: the battery/resync work runs once per link and the health
    line's `ble conn=` counts real links — the number P4.3's life-cycle
    probe reads. Hardware expectation after the next reflash: exactly
    ONE battery notification + ONE neutral-report pair per connection
    in btmon, `ble conn=` incrementing by one per link (with the
    standing caveat: re-pair on the laptop after a reflash).
  - Specs: no deviation — the spec's "once" was already correct and the
    code was the wrong side; `ble_hid.md` §6 gained the P3.27
    implementation note recording the latch and the on-air evidence.
  - Test-first discipline held: 3 new source pins in
    `tests/test_firmware_sketch.py` (the guard/set/arm order in
    `on_ble_opened`, the single set/clear sites with loop() excluded,
    the volatile declaration + the WHY/evidence comment) FAILED against
    the unlatched sketch, pass now. 134 pytest tests; `run_tests.sh`
    green 4/4; the sketch compiles at 22 % flash / 34 % RAM (unchanged).
- P3.26 — the boot gate can never make the device invisible (commit
  `548e63b`): a failed sensor configuration is EVIDENCE and a RETRY,
  never a boot denial. In plain language: the controller used to refuse
  to start its Bluetooth radio until the gesture sensor acknowledged
  all four start-up settings — on a cold boot where the sensor missed
  one (hardware session 5's F12 captures: cmd_index=0 AND cmd_index=1
  on separate boots, the starving supply's doing), it printed an error
  line forever and stayed invisible to every host, which is why "power
  cycling does not work" was first misread as a pairing failure. The
  three parts of the item, as landed:
  - **Retry the whole sequence, forever, loudly.** `setup()` runs ONE
    bounded whole-sequence attempt (the healthy path keeps the familiar
    boot order, `SKYSTATE sensor_ok` before `hid_started`); a failure
    prints `SKYSTATE sensor_config_retry attempt=N cmd_index=K
    elapsed_ms=T` and boot CONTINUES. `loop()`'s
    `sensor_config_retry_tick()` reruns the WHOLE four-command sequence
    (never resumes from the failed command — F12's per-command margin
    makes a part-way stop a half-configured sensor) every
    `SENSOR_CONFIG_RETRY_INTERVAL_MS` = 200 ms until it completes;
    success prints `SKYSTATE sensor_ok attempts=N took_ms=T` (the
    probe's token survives, now with the recovery instrument F12 asked
    for). Design decision recorded: NO reset pulse between retry
    attempts — a mid-retry reset would add 600 ms per attempt and the
    transfer-line discipline (P3.23) plus the item's own reset-timing
    part already cover the recovery paths a reset would address; a
    sensor wedged beyond that needs a human power cycle, and the
    attempts-climbing evidence names it.
  - **Reference reset timing.** `arduino/Skywriter/skywriter.cpp`
    `begin()` now holds the reset line LOW 100 ms and gives the sensor
    500 ms to settle after release — the Python driver's `reset()`
    numbers, whose comment cites the datasheet's 200 ms boot delay;
    the old 10 ms hold / 50 ms settle were both under that figure
    (the timing lives in the shared library, which is what the sketch's
    bring-up calls).
  - **The radio starts regardless; the health line carries the
    outcome.** `setup()` proceeds to the Bluetooth bring-up whatever
    the attempt did; `print_health_status()` gained `sensor_cfg=0|1`
    and `cfg_attempts=N` right after uptime. While unconfigured,
    `Skywriter.poll()` stays off (decision recorded: a poll could steal
    the System_Status acknowledgment frame a waiting command is parked
    on — both read the same sensor buffer over I2C — and an
    unconfigured sensor's padding reads would pollute the frame
    counters); the BLE life-cycle drains and the health line keep
    running, so the device is UP but DEAF, visible on the health line.
  - Specs: `ble_hid.md` §6 Boot row gained the P3.26 implementation
    note (bounded step, never a gate; the evidence-line formats; the
    polling rule) — no deviation row, the spec and code were aligned in
    the same change.
  - Test-first discipline held: 7 new/updated source pins in
    `tests/test_firmware_sketch.py` FAILED against the old sketch (the
    deny-line pin, the deny-loop absence, the retry shape, the per-
    attempt evidence, the success line fields, the health-line fields,
    the poll gate), and the new behavioural test
    `tests/test_driver_reset_timing.py` FAILED with "delays recorded:
    [10, 50]" — the real driver's `begin()` compiled for the host
    behind the shims (which now record `delay()` calls in order, kind 2
    in the `PinAction` log; new host program
    `tests/cpp/host_reset_timing_main.cpp`), asserting the exact
    reset-LOW → 100 ms → reset-HIGH → 500 ms sequence. Green after:
    131 pytest tests; `bash run_tests.sh` 4/4; the sketch compiles at
    22 % flash / 34 % RAM (unchanged).
  - Environment note for future iterations: this container instance
    again had no host C++ compiler (`g++`/`zig` absent) — the
    documented fallback was installed with
    `pip install --user --break-system-packages ziglang` (the same
    step P3.1's environment note and the 2026-11-19 iteration needed;
    it is container-local state, not repo state).
- P4.0a — CLOSED (2026-11-24; no code change — resolved on the bench):
  the "no input reaches the laptop" gate is RESOLVED — the
  sensor-side fault was PHYSICAL, found and fixed. In plain language:
  the wire feeding 3.3 V from the Pico to the sensor's circuit board
  was partly broken inside its insulation — it read a healthy 3.3 V
  when nothing drew current, but any real load collapsed it (a 330 Ω
  test load dragged it to 0 V), so the gesture sensor browned out at
  ~1.9 V and never streamed. Replaced with stranded-core wire; the
  sensor now streams on Pico power alone.
  - The diagnostic march that got there (full evidence:
    `HW_REPORT.md` round 5, F8–F16): P3.22's health counters ruled
    out the silent-stall and float faults (H1/H2 closed by P3.23,
    commit `1c8bbb2`) and showed `other=100 %` from the first poll;
    H7 (the 132-byte over-read desynchronising framing) was REFUTED
    by P3.24's snapshot — reads complete with all-zero content:
    "padding on empty reads", a sensor with nothing queued (P3.25's
    sized reads stay as correct read hygiene, commit `2267497`);
    F13's multimeter pass measured the starvation (VCC-to-GND
    1.871 V, VCC-to-Pico-3V3OUT −1.463 V — the Pico's own pin
    healthy at ~3.33 V under load); F14's pin survey matched the
    brown-out picture and verified the pull-ups against the
    datasheet (10 kΩ TS/MCLR exact, 4.7 kΩ SDA/SCL compliant at our
    100 kHz bus — exonerated as any current drain by three
    independent proofs); F15's bench-supply experiment (supply on the
    veroboard rails: works; off: starves again at the same fixed
    point, no touching) exonerated the Pico's regulator and
    re-localised the drop upstream of the header; F16 is the wire
    break itself, its no-load/full-voltage + any-load/collapse test,
    the stranded-wire fix, and the post-fix capture.
  - Post-fix evidence (2026-11-24 health capture, Pico power alone):
    `ts_low=0.00 %`, `short_reads=0`, `frames sensor` climbing
    (229 → 427 over 32 s while gesturing), events pos/touch/gest
    counting, HID (Human Interface Device) button/wheel/key/media
    reports all climbing, `dropped=0`, `ble conn=5 disc=0`, and the
    transfer accounting exact (`ts_low 244 = frames sensor 229 +
    other 15`) — every data-ready pulse became exactly one dispatched
    frame. The `other` trickle (~0.2/s, all-zero reads) is noise.
  - Riding along: **AC-BLE-06 is an OFFICIAL PASS** (2026-11-23 btmon
    after the laptop's Bluetooth off/on: `LE Start Encryption` with
    the stored key, `Encryption Change: Enabled with AES-CCM`, no SMP
    Pairing Request) — see P4.3's update.
  - Corrections recorded at closure: the Skywriter is the 6-pin
    version (the withdrawn "second 3V3 position" advice never
    applied), and the 2026-11-19 lean toward the pin-header contact
    was wrong — the fault was in the Pico→veroboard feed wire.
  - Unblocked: P4.0 — the gesture acceptance run (pointer, taps,
    AirWheel, flicks, with the laptop-side evtest/hid-recorder
    capture). The counters show every channel alive; the run must
    confirm pointer reports on a MOVING hover (today: pos=83 events,
    `hid pointer=0` — a still hand) and exercise AirWheel
    (`events wheel=0` so far; the wheel reports seen come from the §6
    touch-hold auto-scroll rows).
- P3.25 — the Arduino driver reads the sensor the Python way: exactly 26
  bytes first, longer messages by their own Size field (commit `2267497`)
  — the H7 fix, hardware report session-4's failure F7. In plain
  language: the Pico used to ask the sensor for 132 bytes on every read
  while a normal message is 26 — clocking 106 bytes past the end of each
  message into undefined territory. If the sensor serves the start of the
  next queued message there, its internal read pointer ends up
  mid-frame and every later read starts inside a message, so the
  header's identity byte never lands on a known value again — exactly
  the other=100 %-from-the-first-poll / zero-events signature the
  2026-11-18 and 2026-11-19 captures showed, and the intermittent
  history (sessions 1–2's occasional valid frames = lucky realignment
  when a read drained the queue onto a boundary) fits the same story.
  Boot always passed because the acknowledge path reads exactly
  26 bytes. Parts (all in `arduino/Skywriter/`):
  - `poll()` requests EXACTLY `SW_FIRST_READ_SIZE` (26) bytes first; a
    frame whose Size field (byte 0, validated 4 ≤ size ≤ 132 — the
    longest real message; the protocol cap is 255 but no sensor message
    exceeds Fw_Version_Info's 132) announces a longer message is fetched
    with continuation reads capped at `SW_I2C_READ_CHUNK` (32) and
    bounded by the Size, while the transfer (TS) line is still asserted
    — the Python driver's P3.11c pattern; the 132-byte Fw_Version_Info
    frame arrives as 26 + 32 + 32 + 32 + 10. P3.11b's GOAL (the whole
    120-byte version string) survives through those continuations; its
    single-132-byte-request MECHANISM is what this item removed, and
    with it H7's over-read.
  - Dispatch only complete frames: a corrupt Size (under 4, above 132)
    or a continuation that serves nothing means the frame is skipped —
    never decoded half-read (the Python driver's empty-continuation
    rule). The payload copy is Size-bounded, so bus padding or an
    over-answering read never reaches a decoder (the same rule as
    P3.11c), and the receive buffer is drained after every transfer so
    the next requestFrom starts clean on every Wire implementation, not
    only the ones that reset it themselves.
  - The P3.23 release rule (transfer line let go, pull-up restored)
    stands on every exit path, including the two new ones (corrupt
    Size, incomplete frame) — pinned by the new tests.
  - Test-first discipline held: the Wire host shim
    (`tests/cpp/Wire.h` + `arduino_shim.cpp`) now models the sensor
    continuing its buffer across the reads of one asserted transfer
    (the P3.11c contract the sized reads rely on) and records every
    requestFrom call; the new host binary `tests/cpp/
    host_read_pattern_main.cpp` + `tests/test_driver_read_pattern.py`
    drive the REAL driver through its genuine `poll()` and pin the
    pattern: one 26-byte request for the classic frame (never the old
    132), no continuation for a 14-byte frame, the exact
    26,32,32,32,10 chase for the recorded 132-byte F17 fixture, no
    dispatch of incomplete or corrupt-Size frames, the release pair on
    every new exit path, and closed transfer accounting (short +
    sensor + status + fw + other = every transfer). Verified FAILING
    against the pre-P3.25 code first (8 of the 10 — the old single
    132-byte request, no continuations, no snapshot; the short-read and
    accounting cases were already true then and stayed green), green
    after the rewrite.
  - Honest scope note, as the item itself assigns: whether the real
    sensor continues its I2C buffer across the separate reads of one
    asserted transfer is a P4.1 hardware check against this build — the
    offline harness proves the driver-side arithmetic only (the same
    caveat the P3.11c entry recorded for the Python driver).
- P3.24 — the unknown-frame snapshot exists (commit `2267497`): whenever
  a transfer read a header but did NOT dispatch, the driver stores
  public state — the first 8 frame bytes (size, flags, sequence,
  identity + 4 payload bytes) and the byte count the reads actually
  returned (the `Wire.requestFrom` counts the old code ignored
  entirely) — and the firmware's health line prints them once per line
  as `other_snap=` (colon-separated zero-padded hex) and `other_read=`,
  right after the `other=` counter they explain. The 200 Hz hot path
  only stores; nothing prints inside `poll()`.
  - Scope decision recorded (a deliberate superset of the item's
    letter): the item says "when a frame's identity byte is not
    0x91/0x15/0x83" — written against the OLD read pattern, where
    every poll reached the identity switch. With P3.25's Size
    validation in place, an identity-only snapshot would be blind to
    corrupt-Size frames — exactly the frames H7 misalignment produces
    (a mid-frame Size byte is garbage too). The snapshot therefore
    fires on EVERY undispatched frame that produced a header: unknown
    identity, corrupt Size, or incomplete. Each self-identifies in the
    content, matching the item's predictions: a 0x91 identity visible
    at a SHIFTED offset = the mid-frame misalignment (H7); all 0x00 =
    the bus answers padding on reads with nothing queued (then hunt the
    transfer-line short — the HW report's supply-wire discriminator
    settles it); all 0xFF = a wedged slave (power-cycle the sensor and
    retest); a KNOWN identity with the read count under the promised
    Size = an incomplete read (the P4.1 continuation question).
  - `frames_other` counts them all, so the health line's accounting
    closes: short + sensor + status + fw + other = every transfer
    started — nothing silently disappears into an unnamed bucket, which
    is what made the 100 % "other" capture uninterpretable in the
    first place.
  - Pinned by `tests/test_driver_read_pattern.py` (snapshot content for
    each undispatched shape — shifted identity, all-zero padding,
    over-long Size, truncated frame; latest-wins; dispatched frames
    never touch it; short reads never touch it; the actual-read-count
    evidence) and `tests/test_firmware_sketch.py` (the health-line
    print: both fields, the zero-padded hex format, placement with the
    other= counter).
- W8 — ledger housekeeping done (commit `1c8bbb2`): (a) the P3.17b Done
  entry's "commit `<HASH>`" placeholder is now the real hash `5553de4`
  (the loop's automatic-snapshot commit, which carried the
  otherwise-uncommitted P3.17b work — found via `git log -S
  "FLASH-BACKED"`); (b) the duplicated P3.1 entry and "Environment note
  discovered by P3.1" at the bottom of the Done section were removed
  (one copy of each remains — the earlier copy, whose wording matches
  the current harness: `tests/build/` is covered by the tree-wide
  `build/` .gitignore rule); (c) verified no `<HASH>` placeholder
  remains in this file and `bash run_tests.sh` stayed green.
- P3.23 — the Arduino driver always releases the sensor's transfer line
  (commit `1c8bbb2`). In plain language: the sensor says "new data is
  waiting" by pulling its data-ready wire low; the driver holds that wire
  low while it clocks the data over the I2C bus, and MUST let go
  afterwards or the sensor's buffers stay locked — the sensor goes
  silent forever while the Bluetooth link and serial console look
  perfectly normal (the leading suspect for hardware session 3's total
  input loss, P4.0a hypothesis H1). The Python driver had exactly this
  defect and got the fix in P3.11d; the Arduino driver now has it too:
  the failed-read early return (fewer than the 4 header bytes) releases
  the transfer (TS) line before returning, instead of stranding it LOW.
  Second half (H2, the reopened P3.19 pin-mode decision — outcome
  recorded): the release now RESTORES the pin's internal pull-up on
  every exit path (`pinMode(xfer, INPUT_PULLUP)`, as the Python driver's
  release does), so a loose or disconnected TS wire reads consistently
  high instead of at random (a random low read would trigger the
  failed-read path continuously). The old plain-INPUT release is gone
  from both the driver and the sketch's acknowledge path; the AGENTS.md
  gotcha that documented the quirk was updated with a dated note.
  Test-first discipline held: the shims (`tests/cpp/Arduino.h` +
  `arduino_shim.cpp`) now RECORD every `pinMode`/`digitalWrite` call,
  the new host program `tests/cpp/host_pin_release_main.cpp` drives the
  REAL driver through its genuine `poll()` on both paths (normal F01
  frame; empty/failed read), and `tests/test_driver_ts_pin.py` asserts
  every poll ends with the release pair (line driven high, then
  INPUT_PULLUP) — verified FAILING on the pre-fix code (3 failures)
  and PASSING after. No public callbacks or frame decoding changed; all
  three shared examples still compile (run_tests.sh green 4/4).
  Decision note: no `specs/README.md` deviation row was added — no
  sentence in `specs/` pins the release pin mode (checked first). If
  P3.22 shows many short reads on hardware, a bounded retry inside
  `poll()` (as the boot path already has) becomes a separate item.
- P3.22 — the health counters are live (commit `1c8bbb2`), the hardware
  gate P4.0a's main instrument (with no oscilloscope or logic analyser,
  these counters are the only view of the transfer line and the failed
  reads over time):
  - **Shared library (`arduino/Skywriter/`) public state** (so the
    examples keep compiling): `polls` (every `poll()` call),
    `ts_low_polls` (polls where the data-ready line read LOW — a real
    transfer), `short_reads` (transfers whose read returned fewer than
    the 4 header bytes — the H1 path) and frames by message identity
    (`frames_sensor_data` 0x91, `frames_status` 0x15, `frames_firmware`
    0x83, `frames_other`). Increment only — the 200 Hz hot path never
    prints.
  - **Sketch counters** (`SkywriterController.ino`): dispatched sensor
    events (`ev_position`/`ev_touch`/`ev_gesture`/`ev_airwheel`, counted
    after the unconnected drop gate), `ev_dropped` (events dropped while
    unconnected — the H6 probe's number), HID reports by kind counted at
    the radio call sites (`hid_pointer`/`hid_button`/`hid_wheel`/
    `hid_key`/`hid_media` — a click counts 2 button transitions, the
    scheduled tap pulses included), and Bluetooth link life cycle
    (`ble_connects`/`ble_disconnects` — the F4 duplicate-connect
    question's number).
  - **The status line**: once every `HEALTH_INTERVAL_MS` = 2000 ms from
    `loop()`, one grep-friendly `SKYSTATE health` line with uptime (a
    board reset shows as uptime dropping to zero) and the two shares
    ALREADY DIVIDED OUT — short reads and TS-low polls as a percentage
    of all polls — per the P4.0a T5 requirement ("visible without
    arithmetic"). Restart-vs-stall is now decidable from the counter
    shapes (see the F6 outcome note in the status snapshot).
  - Pins: `test_health_status_line_printed_every_two_seconds` (every
    counter named in the line, the 2 s gate guards the print) and
    `test_the_200hz_sensor_path_never_prints` in
    `tests/test_firmware_sketch.py`. Verified: `bash run_tests.sh` green
    4/4; sketch compiles (22 % flash / 34 % RAM).
- P3.21 — taps no longer type letters (commit `1c8bbb2`): the two
  traced causes are both fixed, spec and code together.
  (1) **Wrong usage numbers**: the USB HID Usage Tables keyboard page
  gives Page Up = 0x4B (75) and Page Down = 0x4E (78); 0x4F (79) is
  Right Arrow. `HID_USAGE_PAGE_UP`/`HID_USAGE_PAGE_DOWN` in
  `SkywriterHIDMapper.h` are now 75/78 with the dated revision note
  (cross-checked against the core's key table: `KEY_PAGE_UP` 0xD3 =
  136 + 75, `KEY_PAGE_DOWN` 0xD6 = 136 + 78). Every place quoting
  78/79 was updated: `specs/hid_mapping.md` §6 (new keyboard-usage
  revision note — a spec-data bug, NOT a driver deviation, so no
  `specs/README.md` row), `specs/fixtures/manifest.json` (top note +
  `tap_north`/`tap_south` expectations now usage 75/78 with per-scenario
  notes), `tests/hid_grammar.py` (`KEYBOARD_KEYS` + docstring),
  `tests/adapters_mapping.py` (`_KEYBOARD_KEY_BY_USAGE`),
  `tests/test_mapper_unit.py`, `tests/cpp/host_mapping_main.cpp`.
  (2) **Wrong call path**: `pulse_fire()`'s keyboard case now sends
  `usage + KEYBOARD_NON_PRINTING_OFFSET` (136) to
  `KeyboardBLE.press()`/`release()` on BOTH press and release — the
  core treats values 0–127 as ASCII characters (usage 78 typed "N" on
  hardware, sessions 1 and 2026-11-17) and only 136+ as non-printing
  keys. The conversion happens exactly once (in `pulse_fire`; the sink's
  `keyboardPress` keeps the RAW usage — pinned), so the old raw path is
  unreachable. New pins: `test_keyboard_usages_corrected_to_75_and_78`
  and `test_no_raw_keyboard_usage_reaches_press_or_release` (asserts
  every keyboard call site applies the offset and the known-bad shapes
  cannot return). Side benefit for F5: `press()`'s ASCII path can only
  add Shift/AltGr modifiers — Ctrl+A was never producible from this
  path, and after this fix no raw usage reaches it at all. Verified:
  `bash run_tests.sh` green 4/4; 110 pytest tests.
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
  `5553de4` — the loop's automatic snapshot commit, which carried the
  otherwise-uncommitted P3.17b work), and the resolution **refutes** P3.17's
  RAM-only assumption — a
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
