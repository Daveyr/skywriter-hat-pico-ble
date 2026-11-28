# HW_REPORT.md — hardware round 7 (2026-11-28): the P3.31 genuine-disable experiment — BOTH rungs

Run by a person on the host (not by the loop). Two builds were flashed
and tested this round, from a fresh power cycle each:

1. `cal=disable_all` — the sensor's five automatic self-tuning
   features genuinely switched OFF for the first time (calibration
   command Argument0 = 0x1F, mask = 0x1F; the legacy payload cleared
   every bit, which ENABLES the features):
   ```bash
   SKYWRITER_EVENT_TRACE=1 SKYWRITER_CAL_DISABLE=1 \
     ./pico-arduino/flash.sh pico-arduino/SkywriterController
   ```
2. `cal=disable_idle` — the ladder's second rung: only idle-tuning
   disabled, the other four features active (Argument0 = 0x08,
   mask = 0x1F):
   ```bash
   SKYWRITER_EVENT_TRACE=1 SKYWRITER_CAL_DISABLE_IDLE=1 \
     ./pico-arduino/flash.sh pico-arduino/SkywriterController
   ```

Each flash was followed by forget + re-pair on the laptop (the
standing reflash caveat). Bench unchanged from round 6: free-air mount
on the non-conductive mat, supply verified 3.3 V at the sensor's own
pins.

Findings continue the ledger's F-numbering (F19–F24 were round 6;
F25–F28 are this round).

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

FAIL for the disable-all rung. "clip=1 still set on every frame" — boot
frame and hover frames alike — with `cal=disable_all` confirmed
running.

## F28 — FAIL for the idle-only rung too: same Clipping bit at boot,
and this build produced ZERO frames during the palm hover

The second rung, flashed fresh and power-cycled. Boot line and every
health line name the variant (`cal=disable_idle` — confirmed running,
not a mistaken reflash of rung 1):

```
SKYSTATE health uptime_ms=2000 ... cal=disable_idle ... ts_low=1(0.00%)
frames sensor=1 ... sysinfo=0xA0 noise=0 clip=1 events pos=0 touch=0
gest=0 wheel=0 ... ble conn=0 disc=0
```

- **Same boot verdict**: the fresh boot's FIRST data frame (the only
  one at that point — `frames sensor=1`) still carries
  `sysinfo=0xA0 clip=1` — with idle-tuning off and the other four
  features active. The Clipping bit is present at boot on this rung
  too.
- **The palm descent and hover happened within the captured window
  (uptime 2–14 s) and produced ZERO frames**: `ts_low` stayed at 1,
  `frames sensor` stayed at 1, and every event counter stayed at 0
  through every line. The sensor asserted its transfer line exactly
  once (the boot frame) and never again — no touch, no gesture,
  nothing reached the laptop.
- Contrast with rung 1 (disable_all), whose slow descent produced 41
  frames decoding as touch/gesture. Honest caveats on that contrast:
  round 6's F20 showed the LEGACY build (all five features ON) also
  produces zero frames for a still palm at close hover, so
  zero-frames is not new behaviour for this sensor; and each rung has
  one trial only, so the 41-vs-0 difference is a single observation,
  not a measured effect. What is NOT in doubt is the FAIL criterion:
  every frame this build ever received carried clip=1.

## Verdict (both rungs) and the ladder's state

BOTH rungs FAIL their criteria: "clip=1 still set on every frame" on
`cal=disable_all` AND on `cal=disable_idle`, from the first frame of a
fresh boot on each. Auto-calibration — any single masked feature or
the whole suite — is ELIMINATED as the cause of the boot-time
receiver saturation. Disabling it in every available combination
does not clear the Clipping bit, and PositionValid (bit 0) has still
never been set in any frame on any build.

Per the ledger's ladder, the next rung is the vendor-canonical
`0x3F` payload (six bits — also disabling calibration triggered by
the AFA, the adaptive filter: Argument0 = 0x3F, mask = 0x3F, the
vendor's own Appendix A "Disable" fixed command). **That rung does
not exist as a buildable variant yet** — only the two rungs above
are compile-time switches; 0x3F is documented in the sketch's command
comment only. Landing it is a code change for the inner loop.

## Capture note for the next round

This round's pasted log missed the hover itself: all captured lines
are post-hover idle repeats of frozen counters. For the next variant,
attach the monitor BEFORE the palm descent and keep it running through
it, so the run records the per-event SKYTRACE lines and live health
lines (per-frame `sysinfo=`) during the hover — the direct evidence of
whether ANY frame during the descent shows clip=0.

## Next steps (in order)

1. **Run the inner loop** (`bash ralph.sh`) so it consumes this
   report: both code-side rungs of the P3.31 ladder have FAILED on
   hardware, and the ladder's next rung — the vendor-canonical
   `0x3F` variant — needs a code change to become a flashable build
   (`SKYWRITER_CAL_DISABLE_AFA=1` or equivalent, per the sketch's
   existing comment: Argument0 = 0x3F, mask = 0x3F). The loop should
   also fold this round's elimination into the ledger: auto-calibration
   is dead as the Clipping explanation.
2. **Flash and test the 0x3F variant when the loop lands it**: fresh
   power cycle, forget + re-pair, monitor attached BEFORE the palm
   descent, then the same slow palm descent and hover. PASS/FAIL
   criteria unchanged: PASS = a live frame shows `clip=0` and
   position events appear; FAIL = clip=1 persists.
3. **Still clip=1 after 0x3F** → the code-side ladder is EXHAUSTED;
   the damaged-board hypothesis stands and the F24 Raspberry Pi
   cross-check (blocked: no Pi to hand) is the decisive discriminator.
4. **Cheap no-reflash probes, any time on the current pairing**:
   the boot-intermittency power-cycle probe (two or three more fresh
   boots watching the first health lines for ANY boot showing the
   healthy `sysinfo=0x80` — a clean boot relocates the fault to
   boot-time initialisation; note this round added two more boots,
   both clip=1 from the first frame), and the west-zone
   small-fingertip rerun from round 6's list.
