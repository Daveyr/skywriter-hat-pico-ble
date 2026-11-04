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

- Budgets: `RALPH_MAX_ITER` (40), `RALPH_MAX_HOURS` (6),
  `RALPH_MAX_CONSECUTIVE_FAILURES` (5) — set as `-e VAR=value` on docker run.
- Iteration logs land in `logs/` (gitignored). Stop markers `DONE` /
  `READY_FOR_HW` are gitignored; the loop watches for them.
- `run_sandbox.sh` stays as the interactive (human-in-the-loop) entrypoint.

## Status snapshot (2026-11-04)

- **Phase 0 done**: repository clean, sandbox image `skywriter-dev` built,
  model auth in `skywriter-sandbox.env`, deploy key push works.
- **Phase 1 done** (commit `1c0b12a`): `specs/` contains the acceptance
  specs — `README.md` (framing + deviation ledger D1–D8), `ble_hid.md`
  (wireless radio profile, `AC-BLE-01…08`), `hid_mapping.md`
  (gesture→controller mapping, `AC-MAP-01…09`), `fixtures/` (19 recorded /
  constructed sensor frames + `manifest.json` expectations).
- **Phase 2 bootstrapped by this commit**: `PROMPT.md`, `ralph.sh`,
  `run_tests.sh` exist; remaining items below.
- **Baseline test run (2026-11-04, host)**: fixture corpus green; Python unit
  tests red (W5); `SkywriterInterrupt` example compiles green; `NeoPaint` and
  `SkyPainter` examples red — missing `Adafruit NeoPixel` library (W6).
- **Script invocation**: run the scripts as `bash ralph.sh` /
  `bash run_tests.sh` — their executable bit could not be set in this
  environment (`chmod` is blocked); run `chmod +x ralph.sh run_tests.sh`
  manually if you prefer `./`-style invocation.
- Stack decision is settled (verified inside the sandbox image): the Pico W
  Arduino core 6.3.1 ships the Bluetooth HID libraries we need
  (`HID_Bluetooth`/`PicoBluetoothBLEHID`, `MouseBLE`, `KeyboardBLE`).
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
- [ ] W5 Make `bash run_tests.sh` fully green — Python unit tests:
      `library/test.py` fails at import (`import mock` — a third-party
      package, missing on the host) and would then fail inside `setup()` →
      `get_status(0xA2)` (`RuntimeError` on the unconfigured mock — see
      AGENTS.md Gotchas). Fix properly: use `unittest.mock` from the standard
      library (one source, works everywhere) and make the mocked SMBus answer
      the status handshake with the `specs/fixtures/F16_status_ack_a2.hex`
      frame (single source of truth). Keep the test strictly offline
      (no I2C, no network).
- [ ] W6 Make `bash run_tests.sh` fully green — firmware compiles: example
      sketches `arduino/Skywriter/examples/NeoPaint` and `SkyPainter` fail
      because the third-party `Adafruit NeoPixel` library is not installed
      (`arduino-cli lib install "Adafruit NeoPixel"` on the host and in the
      container's toolchain volume). `SkywriterInterrupt` already compiles
      clean.
- [ ] W7 Dry-run the loop: `RALPH_MAX_ITER=1 docker run … skywriter-dev
      bash ralph.sh` — confirm the agent commits, logs land in `logs/`, marker
      files stop the loop. Fix any friction found.

## Phase 3 — Arduino implementation (folder: `pico-arduino/`)

Per AGENTS.md "To build": Pico/Pico W firmware lives in `pico-arduino/`.
Library fixes to the existing driver go to `arduino/Skywriter/` (the shared
library both use).

- [ ] P3.1 Fix Arduino driver deviations in `arduino/Skywriter/skywriter.cpp`:
      D2 (out-of-bounds byte written in `setRuntimeParam`), D3 (airwheel
      counter wrap), D4 (touch decode early-returns and drops other fields),
      D7 (gesture class/edge/in-progress attributes dropped). Verify with
      `specs/fixtures/`.
- [ ] P3.2 Fix Python driver deviations in `library/skywriter/__init__.py`:
      D1 (off-by-4 header regression, commit `e7e2399`), D3, D5 (garbage
      gesture handler never called), D6 (`FwValid` must equal `0xAA` to be
      valid), D7. Keep behaviour identical to the Arduino side.
- [ ] P3.3 Replay test harness `tests/`: drive both decoders from
      `specs/fixtures/manifest.json`, assert the canonical events. Closes
      `AC-MAP-09`; `run_tests.sh` picks it up automatically.
- [ ] P3.4 BLE HID firmware sketch in `pico-arduino/` per `specs/ble_hid.md`:
      composite mouse+keyboard+consumer device (link `MouseBLE` +
      `KeyboardBLE`, call exactly one `begin()`), pairing, battery service,
      advertise/reconnect lifecycle, neutral resync report. Target
      `AC-BLE-01…03`, `AC-BLE-07`.
- [ ] P3.5 Gesture→HID mapping engine per `specs/hid_mapping.md` §6 (the
      mapping table IS the implementation — one table, tunable constants
      alongside). Target `AC-MAP-01…08`.
- [ ] P3.6 Performance targets from `specs/ble_hid.md` §7 that are provable in
      firmware (report pacing, no coalescing of button transitions). When
      firmware-side work is done and only hardware checks remain, write
      `READY_FOR_HW`.
- [ ] P3.7 Keep `AGENTS.md` truthful: the Gotcha "`begin()` does not send
      `SW_SET_RUNTIME`" is stale (deviation D8); verify against the code and
      fix the doc.

## Phase 4 — Outer hardware loop (host-side; container stays hardware-free)

- [ ] P4.1 `hw/serial_probe.py` (host, needs `pyserial`): flash a test sketch
      via `pico-arduino/flash.sh`, capture the USB serial port, assert boot
      banner, sensor frame streaming and framing.
- [ ] P4.2 `hw/ble_hid_probe.py` (host, needs `bleak` + the host's Bluetooth
      radio): automate `AC-BLE-01…07` (scan, pairing, services, report
      receipt, latency, reconnect, bond persistence).
- [ ] P4.3 Outer loop driver `ralph_hw.sh` + `HW_REPORT.md` protocol: run the
      inner loop until `READY_FOR_HW`, flash + probe, write `HW_REPORT.md`
      (pass/fail + captured logs), commit, and let the next inner iteration
      fix what it reports.
- [ ] P4.4 Manual checks: `AC-BLE-08` multi-OS smoke test and gesture feel
      tuning (`GAIN`, `JUMP_THRESHOLD`, `TOUCH_RELEASE_MS` — record final
      values back into `specs/hid_mapping.md` §3).
- [ ] P4.5 Capture real sensor frames on hardware and reconcile every fixture
      marked `synthetic` in `specs/fixtures/manifest.json`.

## Phase 5 — Python port (folder: `pico-python/`)

- [ ] P5.1 Port the Arduino implementation to Python for Pico/Pico W in
      `pico-python/` per AGENTS.md "To build", using the same specs as the
      contract.
- [ ] P5.2 Parity tests: the same fixtures must produce the same canonical
      events and controller outputs as the Arduino implementation
      (`AC-MAP-09` applies to the port too).

## Done

- Phase 0 — repository hygiene: clean tree, sandbox image + loop volumes
  ready, model subscriptions visible to the agent.
- Phase 1 — acceptance specs written and committed (`1c0b12a`):
  `specs/README.md`, `specs/ble_hid.md`, `specs/hid_mapping.md`,
  `specs/fixtures/` (19 frames + `manifest.json`, all validated: size bytes
  consistent, references resolve).
- Phase 2 harness files W1–W4 (this commit): `PROMPT.md`, `ralph.sh`,
  `run_tests.sh`, `.gitignore` entries.
