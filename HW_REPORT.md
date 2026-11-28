# HW_REPORT.md — hardware round 7 (2026-11-28): the P3.31 genuine-disable experiment

Run by a person on the host (not by the loop). Build: the P3.31
experiment variant `cal=disable_all` — the sensor's five automatic
self-tuning features genuinely switched OFF for the first time
(calibration command Argument0 = 0x1F, mask = 0x1F; the legacy payload
cleared every bit, which ENABLES the features) — flashed with

```bash
SKYWRITER_EVENT_TRACE=1 SKYWRITER_CAL_DISABLE=1 \
  ./pico-arduino/flash.sh pico-arduino/SkywriterController
```

followed by forget + re-pair on the laptop (the standing reflash
caveat). Bench unchanged from round 6: free-air mount on the
non-conductive mat, supply verified 3.3 V at the sensor's own pins.

Findings continue the ledger's F-numbering (F19–F24 were round 6;
F25–F27 are this round).

## F25 — the experiment build is genuinely running

Fresh boot:

```
SKYSTATE sensor_ok attempts=1 took_ms=29 cal=disable_all
SKYSTATE hid_started name=Skywriter HID appearance=0x3C0
SKYSTATE pace report_interval_ms=15
SKYSTATE ble_resync battery=100 neutral_report
SKYSTATE ble_connected
```

`cal=disable_all` on the boot line AND on every repeating health line —
P3.31's late-attach safeguard doing its job; the run cannot be mistaken
for the default build. Exactly one `ble_resync` + `ble_connected` pair,
`ble conn=1 disc=0` throughout the whole session — the once-per-link
connect behaviour (P3.27) holds on hardware again. `sensor_ok
attempts=1` at 29 ms — the boot gate healthy.

## F26 — FAIL for the disable-all rung: Clipping still set from the
FIRST frame of a fresh boot, with self-tuning genuinely off

The first health line (uptime 2 s, no hand near the sensor, the boot
frame the only one received — `frames sensor=1`):

```
SKYSTATE health uptime_ms=2000 ... frames sensor=1 ... sysinfo=0xA0
noise=0 clip=1 events pos=0 touch=0 ...
```

With all five auto-calibration features genuinely disabled, the fresh
boot's first data frame still reports the sensor's health byte as
0xA0 — the healthy 0x80 baseline plus bit 5, Clipping ("the ADCs
[analog-to-digital converters, the sensor's receiver] are clipping",
Interface.pdf Table 4-10). EnvironmentalNoise (bit 4) reads 0 — the
sensor continues to blame itself, not ambient noise.

Meaning: the P3.31 hypothesis — that the legacy payload's accidental
ENABLE of the self-tuning suite (in particular idle calibration
poisoning the electrode baselines) is what rails the receiver — is
REFUTED. The saturation exists at boot before any calibration feature
could run, and turning the whole suite off does not clear it.
The disable-all rung of the P3.31 experiment ladder fails.

## F27 — the slow palm hover: frames arrive, decode as touch/gesture
only, still zero position — and the last hover frame still carries
clip=1

Palm lowered very slowly to almost touching distance, then raised.
Monitor capture from uptime 212 s (after the descent — the hover's own
per-event SKYTRACE lines were not captured; see the capture note
below). Every line is frozen at the hover's totals:

```
SKYSTATE health uptime_ms=212000 ... polls=44486099 ts_low=41(0.00%)
short_reads=0(0.00%) frames sensor=41 ... sysinfo=0xA0 noise=0
clip=1 events pos=0 touch=52 gest=2 wheel=0 dropped=0 hid pointer=0
button=60 wheel=12 key=12 media=4 ble conn=1 disc=0
```

- Frames DID arrive during the hover: `frames sensor=41`, `ts_low=41`
  (up from 1 at boot). The transfer line asserted 40 times during the
  descent — the sensor is not silent at close range.
- But they decode as touch and gesture only: `events touch=52 gest=2`,
  and the HID (Human Interface Device) chain forwarded them as
  button=60, wheel=12, key=12, media=4 — the touch-channel spillover
  pattern of F22, reaching the laptop — while `pos=0`, `hid
  pointer=0`: still ZERO position frames. PositionValid (bit 0) has
  still never been set in any frame on any build; the pointer
  channel's input does not exist on this bench.
- The Clipping bit persisted on the hover's own frames: at rest the
  sensor sends nothing, so every idle health line repeats the LAST
  received frame's health byte — and that is `sysinfo=0xA0 clip=1`,
  i.e. the final frame of the palm descent still reported saturated
  receivers.

## Verdict against the P3.31 PASS/FAIL criteria

FAIL. "clip=1 still set on every frame" — boot frame and hover frames
alike — with `cal=disable_all` confirmed running. Per the ledger's
ladder, the next rung is the idle-only variant, then the
vendor-canonical 0x3F variant, after which only the damaged-board
hypothesis and the blocked Raspberry Pi cross-check (F24) remain.

## Capture note for the next round

This round's pasted log missed the hover itself: all captured lines
are post-hover idle repeats of frozen counters. For the next variant,
attach the monitor BEFORE the palm descent and keep it running through
it, so the run records the per-event SKYTRACE lines and live health
lines (per-frame `sysinfo=`) during the hover — the direct evidence of
whether ANY frame during the descent shows clip=0.

## Next steps (hardware loop, in order)

1. **Idle-only variant** (no reflash-order change, the ladder's next
   rung): flash
   `SKYWRITER_EVENT_TRACE=1 SKYWRITER_CAL_DISABLE_IDLE=1
   ./pico-arduino/flash.sh pico-arduino/SkywriterController`,
   forget + re-pair, confirm the boot line says `cal=disable_idle`,
   then repeat the slow palm hover WITH the monitor attached. This
   keeps the other four self-tuning features active while disabling
   only idle-tuning — narrowing whether any single feature, or the
   suite's absence as a whole, changes the boot/hover behaviour.
2. **Still clip=1 on both variants** → the vendor-canonical 0x3F
   payload (six bits — also disabling calibration triggered by the
   adaptive filter): the last code-side rung.
3. **Still clip=1 after 0x3F** → the code-side ladder is exhausted;
   the damaged-board hypothesis stands and the F24 Raspberry Pi
   cross-check (blocked: no Pi to hand) is the decisive discriminator.
4. **Cheap no-reflash probes, any time on the current pairing**:
   the boot-intermittency power-cycle probe (two or three fresh boots
   watching the first health lines for ANY boot showing the healthy
   `sysinfo=0x80` — a clean boot relocates the fault to boot-time
   initialisation), and the west-zone small-fingertip rerun from
   round 6's list.
