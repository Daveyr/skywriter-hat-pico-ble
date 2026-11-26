# HW_REPORT.md — hardware round 6 (2026-11-26): P4.0 acceptance, free-air bench

Run by a person on the host (not by the loop). Build: the acceptance
variant of the current tree — the P3.26–P3.30 firmware flashed
2026-11-25 with `SKYWRITER_EVENT_TRACE=1 ./pico-arduino/flash.sh
pico-arduino/SkywriterController`, followed by forget + re-pair on the
laptop (the standing reflash caveat). The Bluetooth link held through
every capture this round (`ble conn=1 disc=0`), and the fresh boot shows
exactly ONE `ble_resync` + `ble_connected` pair per link — P3.27's
per-link drain verified on hardware.

Bench: the Skywriter isolated ~6 cm of wire from the veroboard, perched
on a non-conductive cutting mat, wires running away from the board. The
sensor is destined for an enclosure, so this is as electrically quiet as
its bench will ever be. Supply re-measured 2026-11-26: 3.3 V at the
sensor's own pins.

Findings continue the ledger's F-numbering (F17/F18 were the 2026-11-25
acceptance sessions; F19–F24 are this round's).

## Boot verification (fresh power-up, 2026-11-26)

```
SKYSTATE sensor_ok attempts=1 took_ms=29
SKYSTATE hid_started name=Skywriter HID appearance=0x3C0
SKYSTATE pace report_interval_ms=15
SKYSTATE ble_resync battery=100 neutral_report
SKYSTATE ble_connected
```

`sensor_ok attempts=1` at 29 ms — the P3.26 boot gate healthy. Then the
first health line (uptime 2 s), with NO hand near the sensor:

```
SKYSTATE health uptime_ms=2000 sensor_cfg=1 cfg_attempts=1 polls=104823
ts_low=1(0.00%) short_reads=0(0.00%) frames sensor=1 ... sysinfo=0xA0
noise=0 clip=1 events pos=0 touch=0 ...
```

## F19 — the Clipping health bit is set on every frame ever captured,
including the FIRST frame of a fresh boot

Every health line and every SKYTRACE line on the instrumented builds
carries `sysinfo=0xA0` (or `0xB0` during touches): DSP running +
Clipping — never the healthy-at-rest `0x80`. Meaning verified against
the vendor's datasheet (Interface.pdf Table 4-10, bit 5: "Clipping, if
set indicates that the ADCs are clipping" — the analog-to-digital
converters, the sensor's receiver, are saturated). PositionValid
(bit 0) has never been set in ANY frame on ANY capture — the pointer
channel's input does not exist on this bench.

Honest caveat: at rest the sensor sends no frames, so an idle health
line shows the LAST received frame's value — but every frame that has
ever arrived on any boot (boot, close hover, touch) has carried
clip=1, and the fresh boot's first data frame (captured above) already
has it.

## F20 — free-air isolation changed nothing (mounting/environment
eliminated)

Still palm at close hover range: ZERO frames (ts_low, frames and events
all frozen). Slow rotating palm very close without touching: frames
arrive but decode as centre touch only (`SKYTRACE touch code=10
zone=center family=hold`, clip=1) — never position. The sensor's own
EnvironmentalNoise bit reads 0 during the hover attempts — the sensor
blames itself (clipping), not ambient noise.

## F21 — supply verified good at the sensor's own pins

3.3 V measured VCC-to-GND on the Skywriter after the re-mount — the
2026-11-19 starvation class of fault (the part-broken feed wire, F16)
is eliminated on the current bench.

## F22 — first end-to-end acceptance passes: Page Up / Page Down and
the zone orientation; west anomaly

The serial-monitor terminal displays the laptop's received keystrokes
as escape codes: `^[[5~` (Page Up) appears only after north taps,
`^[[6~` (Page Down) only after south taps, never after east/west/centre
touches (those send mouse/consumer reports, not keyboard). Direct
end-to-end evidence of the whole chain: finger → sensor → Pico decode →
mapping table → BLE (Bluetooth Low Energy) HID (Human Interface Device)
keyboard report → laptop operating system → the focused window. No
letters typed anywhere — the P3.21 no-letters fix holds on hardware.

Zone orientation CONFIRMED: touching centre, north, east, south in
order produced exactly those zones, all three families each
(tap/hold/doubletap), including the first-ever north doubletap capture
(code=2). The WEST touches produced ONLY centre codes — no west line at
all in that block (west fired fine on 2026-11-25, so either the finger
missed the few-millimetre west electrode or the zone is marginal). One
deliberate small-fingertip west rerun pending.

Touch-channel spillover continues (P4.5 tuning material): edge touches
interleave centre holds — the 2026-11-26 touch exercise sent
button=174, wheel=25, key=12, media=8 while the user was only pointing
at edges.

## F23 — fresh-boot drift discriminator: REFUTED

The "works fresh then fades" baseline-drift pattern (P4.0 hypothesis
(ii)) has no healthy period to start from: the fresh boot's FIRST data
frame already carries clip=1. Additionally the premise "auto-calibration
is disabled" is FALSE — the "disable auto-calibration" payload both
drivers send (Argument0 = 0x00, mask 0x1F) actually ENABLES all five
auto-calibration features per the datasheet's own bit semantics
(Interface.pdf §4.4.5.3 dspCalOpMode: a bit CLEARED in Argument0
enables the feature; only a bit SET disables it). The command's comment
has been mislabelling it all along. Hypothesis (ii) is dead on both
counts; the semantics discovery is recorded as work item P3.31 in the
ledger. The one observed working window (2026-11-24 boot: pos=83 for
~4 minutes, pre-instrumentation build `2267497`) keeps a boot-dependent
intermittency alive as a possibility.

## F24 — the Raspberry Pi cross-check is BLOCKED (no Pi to hand)

It remains the decisive test between "damaged board" and "Pico-side
setup": seat the Skywriter on a real Raspberry Pi, run this repo's
stock Python driver printing `skywriter.sysinfo` per event (P3.30's
instrument) during the same hover exercises. Blocked until a Pi is
available.

## Next steps (hardware loop, in order)

1. **P3.31 experiment build** (once the inner loop lands it): flash the
   genuine auto-calibration-DISABLE build (Argument0 = 0x1F, mask 0x1F),
   forget + re-pair, then watch whether `clip=` clears and hover
   returns. Rationale: with supply, mounting and drift eliminated, the
   one untested vendor mechanism is the auto-calibration suite that the
   current (mislabelled) payload leaves fully ON — idle calibration
   continuously adjusts the electrode baselines, and a poisoned baseline
   rails the receiver, which is exactly what the Clipping bit reports.
   The 2026-11-24 four-minute position window fits: start-up calibration
   good, idle calibration poisoning it later.
2. **West-zone rerun** on the current pairing (no reflash needed): one
   deliberate small-fingertip touch dead centre of the west edge.
3. **Boot-intermittency probe** (cheap, no reflash): two or three more
   power cycles watching the first health lines — does ANY boot show
   `sysinfo=0x80` at rest? A clean boot would relocate the fault to
   boot-time calibration.
4. **After enclosure**: rerun the palm sweep and the clip check — the
   enclosure changes the sensing field's environment again (thin plastic
   is fine; keep metal away from the sensing face).
5. **When a Pi is available**: the F24 cross-check.
