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
rails, pull-up resistors, supply voltage), so it is no longer the leading
suspect, though it is not ruled out. The cause is not yet known. Some failures
are code faults the loop can fix; the rest needs a person at the board.

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
| External pull-up resistors | Soldered on the veroboard, each between 3V3 and its signal's rail. Measured 2026-11-17 with power off: SDA 4.69 kΩ, SCL 4.67 kΩ, TRFR 10.00 kΩ, RESET 10.00 kΩ. PASS: the measured values match the fitted values | P4.0a H3 |
| Sensor-end 3V3 reading | 3.3 V at the end of the supply wire. PASS | P4.0a T1 |
| Serial log, session 3 | PARTIAL: captured after boot, so the boot lines are missing. Shows repeated sensor firmware messages (section 7) | P4.0a T3 |
| `hid-recorder` or `evtest` on the laptop, session 3 | NOT RUN | P4.0a T4 |
| Health counters (P3.22) | Not implemented; no counter data exists | P4.0a T5 |
| Flex test (T6) | PARTIAL: flex done by hand, joints not recorded, no counters in the flashed build. Repeated sensor firmware messages seen; timing against the flex unknown (section 7) | P4.0a T6 |

## 4. Failures and what to do with each

- **F1 — Page Up and Page Down type letters (P3.21).** Code fault. The loop
  fixes it. The plan records that the usage numbers are wrong: Page Up is 75
  and Page Down is 78 in the USB keyboard table (both the spec and the mapper
  use 78 and 79). Fix code and specs together. Confirm in the spec before
  changing it.
- **F2 — no input reaches the laptop since session 3 (P4.0a).** Not solvable by
  code alone. The wiring is no longer the leading suspect: the static checks
  (pins, bridges, rails, supply voltage, pull-up resistors) all pass. It is not
  eliminated, because solder joint quality (cold or cracked joints) and the
  sensor's signal behaviour cannot be shown by a static test. Other causes,
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
- **F6 — repeated sensor firmware messages (session 3 flex, 2026-11-17).** Not a
  confirmed code fault. The sensor's firmware message repeats (section 7). That
  points at the sensor link: either the sensor is restarting, or the Pico is
  reading the same stalled message again. Locate it with the flex test and the
  P3.22 counters before changing code. P3.23 covers the stall case.

## 5. Human steps before the next hardware loop

Steps 1 and 2 of the earlier list have passed (see section 3). Steps:

1. DONE 2026-11-17: pull-up resistance measured with the multimeter, board
   powered off. SDA to 3V3: 4.69 kΩ. SCL to 3V3: 4.67 kΩ. TRFR to 3V3: 10.00 kΩ.
   RESET to 3V3: 10.00 kΩ.
2. After the loop lands P3.22 and P3.23, flash the diagnostic build from the
   `pico-arduino` folder with `./flash.sh SkywriterController`. Plain
   `./flash.sh` fails, because it looks for a sketch named `pico-arduino`.
3. Keep the serial monitor running from power-on (T3). Record a full log.
4. Run `hid-recorder` or `evtest` on the laptop (T4). Record one still hand, one
   slow swipe, and one tap per zone.
5. Read the counters (T5) and run the flex test (T6). Record which joint, if
   any, changes the counters.
6. Write the results back into this file, or a new one, before the next loop.

## 6. Answers from 2026-11-17

The user's answers to the open questions:

- Multimeter reference: the black probe was on 3V3. TRFR read exactly 0 V
  difference, and SDA, SCL and RESET read near 0 V difference. So every line
  sits at about 3.3 V, which is the idle high state.
- Each signal reaches its intended Pico pin (SDA GP4, SCL GP5, TS GP9, RESET
  GP10), and there is no solder bridging.
- Pull-up resistors are soldered on the veroboard, each between 3V3 and its
  signal's rail. Measured with the board powered off: SDA 4.69 kΩ, SCL 4.67 kΩ,
  TRFR 10.00 kΩ, RESET 10.00 kΩ. The SDA and SCL values match the 4.7 kΩ fitted;
  the TRFR and RESET values match the 10 kΩ fitted. Section 5, step 1 has the
  record.
- The 3.3 V reading at the sensor end of the supply wire is 3.3 V.
- The "N" and "select all": the hand was on the sensor's north side, and the
  "select all" looked like Ctrl+A when the fingers were at the sensor's edges.
  The cause is not known. It is recorded as F5.

## 7. Flex test evidence (session 3, 2026-11-17)

**Build flashed:** the current `SkywriterController` (before P3.22 and P3.23).
It has no health counters, so this flex test can only be judged from the serial
log and the laptop's behaviour.

**Flex performed:** by hand, described by the user as "a good flex". The joints
and wires flexed are not recorded. The user's fingers may have been near the
sensor during the flex, so any gesture-related input in this period is not
clean evidence.

**Serial capture:** `arduino-cli monitor -p /dev/ttyACM0 -c baudrate=115200`,
started after the board had booted. Boot lines (`SKYWRITER-HID boot`,
`sensor_ok`, `hid_started`) are missing. The log has no timestamps.

Lines captured, in order:
- `SKYSTATE waiting_for_host` (repeated).
- `SKYSTATE pace report_interval_ms=45`, then `SKYSTATE pace report_interval_ms=15`.
- Pairs of `SKYSTATE ble_resync battery=100 neutral_report` and
  `SKYSTATE ble_connected`. No `ble_dropped` line. The earlier full capture had
  four pairs; the latest excerpt has two.
- `SKYWRITER-HID sensor_firmware valid=0xAA version=1.1.18;p:HillstarV01;...`.
  The earlier full capture had one copy. The latest excerpt has **eight copies**,
  all identical, after the connection pairs. None of the sensor's motion data is
  printed, because the sketch does not print it.

**Laptop behaviour (not in the log):** an "N" and a "select all" were seen on
the laptop. Their timing against the flex and the serial log is not recorded.

**What the firmware message means (from `arduino/Skywriter/skywriter.cpp`
lines 66–69 and 100–123):** the sketch prints this line each time a poll reads
a firmware-info frame (identity byte 0x83). The sensor should send it once at
start-up. Eight copies mean one of two things, neither confirmed:
- the sensor restarted several times (each restart sends the message again),
  pointing at the supply, the reset line (GPIO 10) or a brownout (H4, H5); or
- the Pico re-read the same message because the sensor stopped moving on to new
  data (a stall), pointing at the transfer-line handling (H1, fixed by P3.23)
  or a bad joint on the transfer or data lines.

**Open, needed to decide between them:**
- Did the copies start during the flex, or after it? Not recorded.
- Did the laptop's Bluetooth link drop at any point? Not recorded.
- Which joints and wires were flexed, and in what order? Not recorded.
- Timestamped capture of a repeat test (for example with pyserial, which the P4.1
  probe plans to use). Not done.
- With P3.22 flashed: a restart gives a small count of firmware messages, one per
  restart. A stall gives the firmware count climbing at the read rate (hundreds
  per second) while the motion count stops. Not yet possible.

## 8. Must not be done by the loop

- Do not change the wiring, flash the board, or use `arduino-cli upload`.
- Do not mark any P4 item as passed. P4.0a stays open until the human steps
  above are recorded.
- Do not edit `datasheets/` or `firmware/fw.py`.
- Do not delete `READY_FOR_HW` by hand. `ralph.sh` removes it on its next start,
  once this file exists.
