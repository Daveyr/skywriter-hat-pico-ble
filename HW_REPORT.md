# HW_REPORT.md — hardware session 4 results (recreated 2026-11-19)

This file is the outer hardware loop's results report (P4.4 protocol).
The inner Ralph loop reads it first (PROMPT.md iteration step 2): fix the
failures reported here, record the outcome in `fix_plan.md`, then remove
this file.

It was briefly retired in commit `ff5d36f` (its facts were folded into
`fix_plan.md`), but the marker protocol still requires it — `ralph.sh`
refuses to consume the `READY_FOR_HW` marker without it — so it is
recreated here with the sessions that have happened since. Earlier
sessions (1–3, 2026-11-08 to 2026-11-17) stay recorded in `fix_plan.md`
under P4.0a; this report covers only what the P3.22 diagnostic build
measured.

## 1. What was tested, and how

- Build: the P3.22/P3.23 diagnostic firmware (commit `1c8bbb2`), flashed
  with `pico-arduino/flash.sh SkywriterController` onto the Pico W.
- Instrument: the `SKYSTATE health` counter line, printed every 2 s on
  the USB serial port (`arduino-cli monitor -c baudrate=115200`), plus a
  multimeter in DC volts mode.
- Dates: counters first captured 2026-11-18 (mid-run, uptime
  883–909 s); boot-from-power-up and the transfer-line voltage captured
  2026-11-19.

## 2. Measurements

### 2.1 Counter capture, 2026-11-18 (mid-run)

```
uptime_ms=883402 polls=67390 ts_low=67390(100.00%) short_reads=0(0.00%)
frames sensor=0 status=0 fw=0 other=67390 events pos=0 touch=0 gest=0
wheel=0 dropped=0 hid ... all 0 ble conn=5 disc=0
```

Steady across every 2 s line: polls ≈ 76/s, ts_low tracks polls exactly,
short_reads stays 0, `other` tracks polls exactly, all event counters 0,
uptime continuous.

### 2.2 Counter capture, 2026-11-19 (from power-up)

First health line at uptime 2012 ms, same signature from poll 1:
`ts_low=100.00% short_reads=0(0.00%) other=polls` at every line. Boot
itself passed (the radio only starts after all four sensor configuration
commands are acknowledged; the log shows `ble_connected`, so
`sensor_config_failed` cannot have happened).

### 2.3 Transfer (TS) line voltage, 2026-11-19

Multimeter, DC volts, TRFR pin to GND, hardware powered and firmware
running: **15.4 mV, stable**. With the soldered 10 kΩ pull-up to 3.3 V a
floating or loose wire would read near 3.3 V, so the line is being
actively held low.

## 3. Verdict rows

| Test | Result | Meaning |
| --- | --- | --- |
| Sensor power / bus alive | PASS | short_reads=0 over ~69k reads: the sensor acknowledges at I2C (Inter-Integrated Circuit) address 0x42 and serves bytes on every read |
| Boot bring-up (four runtime commands acknowledged) | PASS | twice, on both boots measured |
| Sensor data frames reaching the driver | **FAIL** | frames `other=100 %` from the first poll on both boots: no 0x91/0x15/0x83 message identity ever decoded; zero events as a consequence |
| Transfer line reads low every poll | observed | consistent with the sensor continuously asserting data-ready (it has frames to hand over) OR a TS-to-GND short on the veroboard; the meter reading (2.3) cannot separate the two |
| Pico W stability | PASS | uptime continuous, no resets during either capture |

## 4. Failures to fix first (inner loop: do these before anything else)

- **F7 — no valid frames decode (`other=100 %`), P4.0a hypothesis H7.**
  Leading suspect: the Arduino driver's single 132-byte I2C read
  over-reads past the 26-byte sensor frame and desynchronises the
  sensor's message framing. Two items are already open in `fix_plan.md`
  §3f, in this order:
  - **P3.24** — instrument the unknown frames (snapshot the first 8
    frame bytes + the read's actual byte count into public state; the
    health line prints it). Its content names the root cause: a
    shifted 0x91 confirms the misalignment; all 0x00 means the sensor
    pads empty reads (then hunt a TS-to-GND short); all 0xFF means a
    wedged slave (power-cycle and retest).
  - **P3.25** — port the Python driver's sized reads to the Arduino
    driver: read exactly 26 bytes first, then continuation reads sized
    from the frame's own Size field while the transfer line is still
    asserted; dispatch only complete frames.
- **P4.3 note (recorded, deferred):** five `ble_connected` events in
  the first 4 seconds of uptime with zero `ble_dropped` between them —
  the duplicate-connect oddity, now with clean timing evidence
  (fix_plan.md P4.3, session 4). Analysis waits until the sensor fault
  is fixed; do not change connection handling for it now.

## 5. Still to run on the host (no code needed)

- **Discriminator for the two live explanations of 2.3:** with the Pico
  still running, disconnect the SENSOR end of the 3.3 V supply wire — a
  real TS-to-GND short keeps TRFR at ~0 V; a healthy line floats to
  ~3.3 V through the pull-up. Record which before re-soldering
  anything.

## 6. What the next hardware run must check (after the P3.25 build)

1. Re-capture T5 from power-up. Pass = `frames sensor` climbing at
   roughly the poll rate (a configured sensor streams continuously — no
   hand over the board needed), `other` near zero, transfer-line-low
   share no longer pinned at a suspicious 100 % with empty frames.
2. If `other` persists, read the P3.24 snapshot content and use its
   signature (shifted 0x91 / 0x00 / 0xFF) to choose the next suspect.
3. Then gesture over the board: pointer, taps, AirWheel — the original
   P4.0 acceptance run.
