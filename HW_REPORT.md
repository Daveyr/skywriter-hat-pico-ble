# HW_REPORT.md — hardware results for the next Ralph loop

Written by a person on the host after hardware sessions 1–3 (2026-11-08 to
2026-11-17). The loop reads this file first (PROMPT.md, protocol step 2): fix
the failures listed in section 4 that code can fix, record each outcome in
`fix_plan.md`, then remove this file. Do not mark any Phase 4 item as passed
from this report.

Plain-language summary: the Skywriter sensor is wired to a Raspberry Pi Pico W
(a small board with Bluetooth). The Pico W connects to a laptop as a Bluetooth
keyboard and mouse. The laptop pairs with it, but since the wires were moved
from a breadboard to a soldered board (veroboard), almost no input reaches the
laptop. The wiring now checks out on every static test so far (pins, bridges,
rails, pull-up resistors, supply voltage). The cause is not yet known. Some
failures are code faults the loop can fix; the rest needs a person at the board.

## 1. What the loop should do

1. Work the open items in fix_plan.md in order: W8, then P3.21 (keyboard codes
   for Page Up and Page Down), P3.22 (health counters in the sketch), and
   P3.23 (always release the sensor's transfer line on every read path).
   Each needs its own offline test, as fix_plan.md describes.
2. Stop at P4.0a, which needs the board. The loop should end with
   `READY_FOR_HW`. That is the expected result, not a failure.
3. Record the outcome of every row in section 4 in fix_plan.md before removing
   this file, so the facts survive once it is deleted.

## 2. Sessions

- **Session 1 (2026-11-08):** the sensor was detected on the I2C bus (the
  two-wire bus between the Pico and the sensor). The name `Skywriter HID`
  appeared in the Bluetooth scan. A Linux laptop paired. The laptop responded
  to the sensor, but the pointer moved haphazardly. Taps typed letters instead
  of Page Up and Page Down. No serial capture file exists for this session.
- **Session 2 (2026-11-09):** serial monitor capture (the Pico's text output
  over USB). Seen: `SKYWRITER-HID sensor_firmware valid=0xAA version=1.1.18`,
  the link connected with `pace report_interval_ms=15`, and `ble_resync` and
  `ble_connected` each printed twice with no `ble_dropped` between them. Single
  and double clicks appeared to work. The monitor was attached after boot, so
  the boot lines are missing.
- **Session 3 (2026-11-16 to 2026-11-17):** all sensor-to-Pico wires were moved
  from the breadboard to veroboard, and the wires were secured. The exact date
  was not recorded. The Bluetooth link comes up (battery and signal strength
  show on the laptop) and the serial monitor shows no error, but no pointer
  movement, click, tap, scroll, key or media key reaches the laptop. On
  2026-11-17 an "N" appeared in a text box after a north tap, and a "select
  all" happened at the same moment. Unplugging the Pico changed nothing. The
  firmware has not been reflashed since session 2.

## 3. Results

Each row is a test or observation, its result, and the plan item it belongs to.

| Test or observation | Result | Plan item |
|---|---|---|
| Sensor detected on I2C (session 1) | PASS (partial: no capture file) | P4.1 |
| `Skywriter HID` visible in Bluetooth scan (session 1) | PASS (partial: "exactly one instance" not checked) | AC-BLE-01 |
| Linux laptop pairs (session 1) | PASS (partial: battery and device information not checked) | AC-BLE-03 |
| Pointer movement (session 1) | FAIL: haphazard, incoherent | P4.0 |
| Single and double clicks (session 2) | Observed working, informal, no log | P4.0 |
| Duplicate `ble_connected` with no `ble_dropped` (session 2) | OPEN: silent drop, reset, or second connection? | P4.3 |
| Page Up and Page Down keys (session 1) | FAIL: typed letters | P3.21 |
| Taps typed "N" after a north tap (2026-11-17) | FAIL: same fault as P3.21 (raw usage 78 typed as N) | P3.21 |
| Any input reaching the laptop after the veroboard move (session 3) | FAIL: none seen | P4.0a |
| Unplug and replug of the Pico (session 3) | No change | P4.0a |
| "Select all" during the "N" event (2026-11-17) | OBSERVED: the user's hand was on the sensor's north side, and "select all" looked like Ctrl+A when fingers were at the sensor's edges. Cause not known | P4.0a, P3.21 |
| Rail readings, SDA, SCL, RESET, powered, probe on 3V3 | Near 0 V difference: each line sits at about 3.3 V (healthy idle). PASS | P4.0a T1 |
| Transfer line (TRFR, GPIO 9), powered, probe on 3V3 | Exactly 0 V difference: line at 3.3 V (idle high). PASS. Not checked for brief dips (multimeter averages) | P4.0a T1 |
| Continuity check, unpowered, rail to rail | No bridging between rails. PASS | P4.0a T0 |
| Sensor supply on pin 36 (3V3 OUT) | Confirmed from the Raspberry Pi Pico W pinout. PASS | P4.0a T0 |
| Each signal reaches its intended Pico pin (SDA GP4, SCL GP5, TS GP9, RESET GP10) | PASS: continuity through the wires to the correct GPIO | P4.0a T0 |
| Bridges between signal wires | PASS: no solder bridging | P4.0a T0 |
| External pull-up resistors (nominal values from the user, not measured) | Soldered resistors: 4.7 kΩ on SDA and SCL; 10 kΩ on TRFR and RESET. Location to confirm (see section 6) | P4.0a H3 |
| Sensor-end 3V3 reading | 3.3 V at the end of the supply wire. PASS | P4.0a T1 |
| Full serial log, session 3 | NOT CAPTURED | P4.0a T3 |
| `hid-recorder` or `evtest` on the laptop, session 3 | NOT RUN | P4.0a T4 |
| Health counters (P3.22) | Not implemented; no counter data exists | P4.0a T5 |
| Flex test (T6) | Not run; needs P3.22 flashed | P4.0a T6 |

## 4. Failures and what to do with each

- **F1 — Page Up and Page Down type letters (P3.21).** Code fault. The loop
  fixes it. The plan records that the usage numbers are wrong: Page Up is 75
  and Page Down is 78 in the USB keyboard table (both the spec and the mapper
  use 78 and 79). Fix code and specs together. Confirm in the spec before
  changing it.
- **F2 — no input reaches the laptop since session 3 (P4.0a).** Not solvable by
  code alone. The wiring checks so far (pins, bridges, rails, supply voltage,
  pull-up resistors) all pass, so the wiring fault is less likely than it was
  on 2026-11-17. Still open: solder joint quality (cold or cracked joints do
  not show on a static test) and the sensor's signal behaviour. Other causes,
  listed in fix_plan.md P4.0a: the transfer line left low after a failed read
  (H1), the sensor restarting (H4), the Pico resetting (H5), or events dropped
  while unconnected (H6). The loop does the code parts: P3.22 (counters) and
  P3.23 (the transfer line is always released). P3.23 reopens the pull-up
  decision from P3.19. Record the decision in fix_plan.md.
- **F3 — haphazard pointer (P4.0, session 1).** Blocked by F2. Do not retune
  `GAIN` or `JUMP_THRESHOLD`; the plan says this is not a tuning problem.
- **F4 — duplicate connect lines (P4.3, session 2).** Open. Check the next serial
  log before changing connection handling.
- **F5 — "select all" (2026-11-17).** Observed with the hand on the sensor's
  north side and fingers at its edges. It looked like Ctrl+A. Record this as a
  symptom. Hypothesis for the loop to check, not a finding: the key report the
  firmware sends may carry a modifier bit (Ctrl) or a stuck key. Check how the
  keyboard report is built before guessing further.

## 5. Human steps before the next hardware loop

Steps 1 and 2 of the earlier list have passed (see section 3). Remaining:

1. Power off. Multimeter, resistance: SDA to 3V3 and SCL to 3V3 should read
   about 4.7 kΩ; TRFR and RESET to 3V3 about 10 kΩ. Measure at the veroboard
   pads, so the reading includes the joints. Record the measured values.
2. After the loop lands P3.22 and P3.23, flash the diagnostic build from the
   `pico-arduino` folder with `./flash.sh SkywriterController`. Plain
   `./flash.sh` fails, because it looks for a sketch named `pico-arduino`.
3. Keep the serial monitor running from power-on (T3). Record a full log.
4. Run `hid-recorder` or `evtest` on the laptop (T4). Record one still hand, one
   slow swipe, and one tap per zone.
5. Read the counters (T5) and run the flex test (T6). Record which joint, if
   any, changes the counters.
6. Write the results back into this file, or a new one, before the next loop.

## 6. Open items from the 2026-11-17 answers

- The pull-up resistor values are nominal (from the user's description), not
  measured. Step 1 of section 5 measures them.
- The user wrote the resistors are "soldered to the breadboard". Confirm they
  are soldered on the veroboard and connected to the same wires. If they are
  still on the breadboard, they are not in the circuit, and the pull-up check
  in section 3 must be redone.

## 7. Must not be done by the loop

- Do not change the wiring, flash the board, or use `arduino-cli upload`.
- Do not mark any P4 item as passed. P4.0a stays open until the human steps
  above are recorded.
- Do not edit `datasheets/` or `firmware/fw.py`.
- Do not delete `READY_FOR_HW` by hand. `ralph.sh` removes it on its next start,
  once this file exists.
