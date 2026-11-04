# PROMPT.md — mission for each Ralph loop iteration

You are one iteration of an autonomous development loop. Follow the protocol
below, then end your turn. Do not work ahead of your assigned item.

## Mission

Enable the Pimoroni Skywriter 3D gesture sensor (a circuit board that detects
hand movements in the air) to work as a wireless controller for computers,
phones and tablets. A Raspberry Pi Pico W (a small microcontroller board with
Bluetooth built in) reads the sensor and presents itself to the host device as
a standard Bluetooth Low Energy (BLE — a low-power wireless standard) Human
Interface Device (HID — the standard protocol behind mice, keyboards and
gamepads). Hand gestures then move a pointer, click, scroll and control media,
with no special driver software needed on the host.

Implementation order (per AGENTS.md "To build"):

1. Arduino C++ firmware for Pico/Pico W in `pico-arduino/` — the main deliverable.
2. Python port in `pico-python/` — only once the Arduino implementation is
   passing its acceptance criteria.

Acceptance = the `AC-*` criteria in `specs/ble_hid.md` and `specs/hid_mapping.md`
are verified. `specs/fixtures/` holds recorded sensor data so most behaviour
can be tested without hardware.

## Iteration protocol

1. Read `AGENTS.md` (project rules) and `fix_plan.md` (the work ledger).
2. If `HW_REPORT.md` exists in the repository root, it holds results from
   physical hardware testing: fix its reported failures first, record the
   outcome in `fix_plan.md`, then remove `HW_REPORT.md`.
3. Take the first open work item in `fix_plan.md` and complete it **fully**.
   No stubs, no placeholders, no TODO-shaped pretend work.
4. Run `bash run_tests.sh`. It must pass. Fix any failure you caused. Known
   pre-existing failures are tracked in `fix_plan.md` — either fix them too if
   the fix is small, or leave them with a precise note of why.
5. Update `fix_plan.md`: move completed items to the Done section (with the
   commit hash), and add anything you discovered — bugs, wrong specs, missing
   tests — as new work items.
6. Commit everything (`git add -A && git commit`). The commit message must be
   readable by someone who does not know electronics: spell out every acronym
   and initialism on first use (e.g. I2C (Inter-Integrated Circuit — the
   two-wire bus between the Pico and the sensor)), and state what changed and
   why in plain language before the technical detail.

## Stop conditions

End the iteration by writing exactly ONE marker file in the repository root
(markers are gitignored — never commit them):

- `DONE` — every item in `fix_plan.md` is finished, `bash run_tests.sh` passes,
  and the acceptance criteria that can be checked without hardware are
  verified. Include a short summary of the overall result.
- `READY_FOR_HW` — the next step needs physical hardware (flashing the Pico W,
  Bluetooth pairing, gesture feel). Write exactly what must be tested and the
  pass/fail judgement for each; the outer hardware loop will run the tests and
  produce `HW_REPORT.md`.

If neither applies, just commit and end the iteration.

## Rules

- Never modify `datasheets/` or `firmware/fw.py` (see AGENTS.md).
- Reuse existing protocol constants and structures (AGENTS.md "Conventions").
- Specs win over code: if code disagrees with `specs/`, fix the code — unless
  the spec itself is wrong, in which case record a spec bug in `fix_plan.md`.
