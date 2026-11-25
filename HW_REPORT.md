# HW_REPORT.md — hardware round 5 (2026-11-19/24, RESOLVED)

The P4.4 protocol's record for this hardware round: what ran, each
finding's verdict (F-numbers continue from round 4's F1–F7), the captured
evidence, the root cause, and the human's next steps. The work ledger
(`fix_plan.md`) carries the follow-up items this round opened —
P3.26–P3.28 in its new §3g — and the updated item evidence. **The round
is CLOSED (2026-11-24): the supply fault was found and fixed (F16) —
the sensor streams on Pico power alone, the pairing bond is officially
verified (F11), and the gesture acceptance run is unblocked.**

## What ran

- Firmware: build `2267497` — P3.24's unknown-frame snapshot
  (`other_snap=`/`other_read=` on the health line) plus P3.25's sized
  reads (exactly 26 bytes first, continuations only when the frame's own
  Size field says so) — flashed with `pico-arduino/flash.sh`.
- Instruments: the `SKYSTATE` serial console (T3/T5), `btmon` on the
  Linux/BlueZ laptop (the radio-side trace), and a multimeter.
- Note: the reflash itself is part of the story — it orphaned the
  laptop's stored pairing (F9) and left the sensor warm (which is why
  post-flash boots always passed the gate that F12 later failed on cold
  boots).
- Post-round bench follow-up (2026-11-20, pre-solder, same build, NO
  reflash): a pin-by-pin multimeter survey (VCC, RESET, SDA, SCL, TRFR
  against GND) with the Pico running, plus a check of the pull-up
  resistor values against the MGC3130 datasheet (DS40001667C) and the
  GestIC interface guide (DS40001718C). Recorded as F14 — which also
  corrects a board fact: the Skywriter is the 6-pin version, not the
  Raspberry Pi HAT (see the rewritten step 4 in the next steps).
- Bench-power-supply experiment (2026-11-23, same build, NO reflash): a
  bench supply feeding 3V3 and GND on the veroboard rails, toggled
  off/on without touching the circuit, one fixed measurement point on
  the veroboard — plus a btmon capture of the laptop's Bluetooth being
  turned off and on, and a health capture on the supply-fed rail.
  Recorded as F15 (and F11's official pass).
- The fix (2026-11-24, same build, NO reflash): the part-broken
  solid-core 3V3 feed wire replaced with stranded wire, followed by a
  health capture on Pico power alone. Recorded as F16.

## Findings

### F8 — the T5 rerun of the P3.24/P3.25 build: ANSWERED — H7 refuted

**Verdict: the over-read theory is refuted; the reads were never the
fault.**

Captured (every 2 s health line, steady from the first poll):

```
ts_low=100.00% short_reads=0(0.00%) frames sensor=0 status=0 fw=0
other=100% other_snap=00:00:00:00:00:00:00:00 other_read=26
```

Every read completes (26 of 26 bytes) and the content is all zero — the
signature table's "padding on empty reads" branch: the sensor
acknowledges its I2C (Inter-Integrated Circuit, the two-wire sensor
bus) address and serves empty padding because it has nothing queued.
Not a misaligned 0x91 (H7's picture), not an all-0xFF wedged slave.
P3.25's sized reads stay as correct read hygiene; the desynchronisation
H7 described never existed.

### F9 — the post-reflash connect/disconnect bounce: ROOT-CAUSED, RESOLVED host-side

**Verdict: fixed by forgetting + re-pairing on the laptop; the cause is
recorded.**

With the laptop still holding the 2026-11-08 pairing and the Pico
reflashed several times since, the laptop auto-reconnected and died at
the security step before ever subscribing to the HID (Human Interface
Device) reports:

- Serial: `SKYSTATE pace report_interval_ms=15` → `ble_dropped` →
  `ble_advertising` cycling at ~1.4 real link losses per second (the
  sketch's own counter: disc 1 → 34 over 24 s) with ZERO
  `ble_connected` lines (`ble conn=0` on every health line — the host
  never enabled the HID reports).
- Laptop: the device appeared and disappeared continuously in the UI;
  manual attempts reported `Connection Failed:
  le-connection-abort-by-local` (the host giving up on a device that
  was not answering).

After forgetting the device and pairing fresh, the link held: one
connection, `conn=5 disc=0` over 30 s (the "5" is F10's finding, not
five links). Leading mechanism (not byte-proven): the core's bond store
lives in a flash section appended after the firmware image, so a
reflash that changes the image size orphans the Pico's stored pairing
while the laptop keeps hers. The failing link's reason code was never
captured (the fix was applied first) — P3.28 adds the device-side
reason line so the next one names itself.

**Operational caveat for every future round: after each reflash,
expect to re-pair on the host.**

### F10 — the fresh-pairing btmon capture: PASS (the round's radio evidence)

**Verdict: the radio profile works end-to-end on air.**

One capture, from advertisement to subscription:

- Advertisement: name `Skywriter HID`, HID service UUID 0x1812, HID
  appearance 0x03C0 (AC-BLE-01 content).
- Connection at 45 ms; the sketch's own connection-parameter request
  ([7.5, 15] ms, supervision 480 ms) ACCEPTED → the link settled at
  15.00 ms — P3.18's pacing machinery verified on air (the radio proof
  behind the `pace report_interval_ms=15` serial line).
- GATT (the Bluetooth service database) enumeration: Generic Access,
  Battery, Device Information, ONE HID service with five Report
  characteristics (four input with notify, one output), Report Map
  (171 bytes, read successfully), Protocol Mode, Boot Keyboard/Mouse,
  HID Information, HID Control Point (AC-BLE-02 structure).
- Pairing: SMP (Security Manager Protocol — the Bluetooth pairing
  handshake) Just Works, encryption enabled, keys distributed and
  stored on BOTH sides (the bond).
- Battery notifications: 0x64 = 100 %. The neutral resync reports (the
  all-zero mouse and media reports) went out on air.
- **F4's duplicate-connect mystery solved here**: the host subscribes
  by writing one enable switch per report channel — four to five
  writes per connection — and the core fires the opened callback on
  EACH. The capture shows four battery notifications and four
  neutral-report pairs on ONE link. Sessions 2/4's "five
  `ble_connected`, zero `ble_dropped`" was one link with five
  subscription writes. Cosmetic fix queued: P3.27.

### F11 — AC-BLE-06 (bond survives a power cycle): PROBABLE PASS

**Verdict: the bond works; the official capture is pending.**

On a cold boot whose sensor gate passed, the laptop auto-connected by
itself — no re-pairing, no interaction (the user watched it happen;
conn=5, disc=0). The earlier "power cycling does not work" attempts
were confounded: they ran against boots that never came up (F12), so
they never tested the bond at all. To make it official: one more
gate-passing cold boot, laptop untouched, btmon running —
`LE Start Encryption` with the stored key (no SMP Pairing Request) is
the pass signature.

Update (2026-11-23): **OFFICIAL PASS.** The predicted capture exists:
with the laptop's Bluetooth turned off and on and nothing else touched,
btmon shows the link coming back as `LE Start Encryption` carrying the
stored long-term key, `Encryption Change: Enabled with AES-CCM`, and
no SMP Pairing Request anywhere in the trace — the exact pass
signature named above, followed by the full re-subscription sequence.
The bond survives host power cycles; F9's caveat (re-pair after a
REFLASH) is a different mechanism and still stands.

### F12 — the cold-boot invisible-device fault: ROOT-CAUSED (the sensor-acknowledge boot gate)

**Verdict: the boot gate on a starving sensor makes the whole device
invisible; the fix is queued as P3.26.**

Three consecutive cold boots, serial monitor attached:

1. `SKYSTATE sensor_config_failed cmd_index=0` repeating forever — the
   first configuration command was never acknowledged; the radio never
   started; invisible to the laptop.
2. `SKYSTATE sensor_config_failed cmd_index=1` — the first command
   passed, the second was lost: the margin is per-command, not one
   power-on threshold (a single longer wait would not have saved this
   boot — the fix must retry the whole sequence).
3. Full clean boot (`hid_started`, `pace`, `ble_connected` ×5,
   `disc=0`) — the laptop auto-connected (F11's probable pass).

The scan capture confirms the invisible boots directly: two other BLE
(Bluetooth Low Energy) devices visible (Samsung, BIGGERFIVE), zero
advertisements from the Pico. The asymmetry with post-flash boots
(which always passed) is explained by F13: after a soft reset the
starving sensor's capacitors stay charged; after a full unplug they
discharge and the acknowledge window is a coin toss.

### F13 — ROOT CAUSE (sensor side): the Skywriter board is starving at ~1.9 V

**Verdict: measured; one fault explains every sensor-side observation in
this ledger since the veroboard rewiring.**

Localization first: with the Pico running and the Skywriter UNPLUGGED
from its pin header, TRFR floats to 3.3 V through its 10 kΩ pull-up —
the Pico/veroboard segment is healthy, and H3's short-on-veroboard
variant is ELIMINATED. The pull-down arrives with the sensor board
(15.4 mV plugged in, session 4's T1 reading).

Then the multimeter, everything plugged in and running:

| Measurement | Reading | Meaning |
|---|---|---|
| Skywriter VCC to GND | **1.871 V** | the sensor is fed ~1.9 V, not 3.3 V |
| Skywriter GND to Pico GND | **0 V** | ground is solid |
| Skywriter VCC to Pico 3V3OUT | **−1.463 V** | the supply path drops ~1.46 V |

The drop lives in the supply path — Pico pin 36 → wire → veroboard
trace → pin-header contact → Skywriter VCC. The MGC3130 runs its
digital core at scavenged voltage (hence the intermittent boot
acknowledgements, F12) but cannot run its sensing engine (hence no
data frames: the all-zero padding, F8) and drags its data-ready line
low (hence TRFR at 15.4 mV). It also explains the passing 2026-11-17
static check — 3.3 V was measured at the supply wire's end, not on the
Skywriter itself — and the intermittency since the veroboard move (a
marginal contact that varies with handling). The Pico-side pin mapping
was re-confirmed and matches the sketch: TRFR GP9 (physical pin 12),
RESET GP10 (pin 14), 3V3OUT pin 36, GND pin 38.

### F14 — the pre-solder pin survey + datasheet check (2026-11-20): CONSISTENT — the prognosis holds, the pull-ups are exonerated and fit for purpose

**Verdict: every reading matches the starving-chip picture (F13); the
pull-up resistors are neither the fault nor wrong-valued; no second
fault is hiding in the wiring; and one board fact is corrected — the
Skywriter is the 6-pin version (3V3, GND, SDA, SCL, TRFR, RESET), NOT
the Raspberry Pi HAT (Hardware Attached on Top, the full-size Pi
add-on board).**

The survey: Pico running, sensor plugged in, multimeter between each
Skywriter pin and GND.

| Pin | Reading | A healthy board shows | Verdict |
|---|---|---|---|
| VCC | 1.87 V | 3.14–3.47 V (datasheet: 3.3 V ±5 %) | fault unchanged — the contact is still bad |
| RESET | 3.16 V (high) | ~3.3 V (the sketch drives it high) | chip NOT held in reset; the 0.17 V deficit is current trickling into the starving chip |
| SDA | 2.0 V | ~3.3 V idle | brown-out signature (below) |
| SCL | 2.0 V | ~3.3 V idle | brown-out signature |
| TRFR | 197 mV (low) | pulsed low briefly per data frame | held low by the dying chip (matches session 4's 15.4 mV) |

What the numbers say:

- **RESET at 3.16 V quietly settles two things.** The driver code
  drives RESET high as a push-pull output after its boot pulse, and
  the starved chip's reset input (MCLR, Master Clear, active-low) is
  drawing a small current into its collapsing internal circuits —
  that is the 0.17 V deficit (the split between the Pico's output
  driver and the socket's RESET contact cannot be separated from one
  reading, and does not matter). First: 3.16 V is far above the
  chip's high-level threshold, so the chip is running, not held in
  reset — which cross-checks the I2C behaviour (it still acknowledges
  its address; a reset-held chip would do neither that nor hold TRFR
  low). Second: the line sits near the HEALTHY 3.3 V rail, not near
  the sensor's starved 1.87 V — bench proof that the pull-ups and the
  Pico-side wiring are on the right side of the bad contact.
- **SDA/SCL at 2.0 V is what a starved chip does to its bus — two
  effects overlapping, both the chip's fault.** The meter averages a
  bus that never idles: TRFR stuck low makes the sketch believe data
  is always waiting, so it polls continuously (~2.5 ms per 26-byte
  read of all-zero content), and a multimeter reads the average of
  that toggling. And when the lines try to rise between transactions,
  a chip whose own supply is 1.87 V cannot let its pins sit above
  roughly its internal rail plus a protection-diode drop (~2.4 V) —
  the pins leak current into the chip instead. A healthy idle bus
  reads ~3.3 V on both lines; a shorted one reads ~0 V; 2.0 V is a
  bus dragged down by its slave. This again eliminates the
  veroboard-short theory (H3) — a short cannot produce 2.0 V.
- **TRFR at 197 mV matches the earlier 15.4 mV** — "solidly low" both
  times: part chip (the dying sensor asserts data-available
  permanently), part Pico (the sketch pulls the transfer line low
  during every read it performs, per the driver code).
- **New insight — the chip is being "phantom fed" through its signal
  pins.** The readings imply close to 1 mA pushed into the chip
  through the pull-ups: TRFR (3.33 − 0.2) / 10 kΩ ≈ 0.31 mA, SDA and
  SCL each (3.33 − 2.0) / 4.7 kΩ ≈ 0.28 mA, plus the trickle into
  RESET. Plausibly part of why the half-fed chip still manages boot
  acknowledgements at 1.87 V. Two consequences: the socket's signal
  positions are carrying current through the same possibly-worn strip
  (one more argument for re-seating/reflowing the whole socket, not
  just the 3V3 pin), and the board should not be left running in this
  state for long stretches between repair attempts — pins sitting
  ~1.4 V above the chip's own supply are outside its ratings.

The datasheet check of the resistor values. Three of the four lines
are electrically open-drain (the pin can only pull the line low — a
pull-up resistor is mandatory), and the datasheet names values:

| Line | Bench value | Datasheet says (DS40001667C) | Verdict |
|---|---|---|---|
| TRFR (the datasheet's TS) | 10 kΩ | "requires a pull-up resistor of typically 10 kΩ, from TS to VDD" (§6.6.2; the pin table repeats it) | exact match |
| RESET (MCLR) | 10 kΩ | "requires external 10 kΩ pull-up" (pin table, pin 24) | exact match — mandatory, not optional |
| SDA | 4.7 kΩ | "typically 1.8 kΩ (for a maximum bus load capacitance of 200 pF)" (§6.6.1) | qualified pass |
| SCL | 4.7 kΩ | same as SDA | qualified pass |

The 4.7 kΩ values are compliant for this bus: Microchip sizes its
1.8 kΩ for a worst-case 200 pF bus, while the standard-speed
(100 kHz) rise-time budget of 1000 ns allows up to ~96 pF with
4.7 kΩ — and the veroboard + short wires + 6-pin module is
realistically 30–60 pF. Both drivers run the bus at 100 kHz (the
Arduino driver's `Wire.begin()` uses the core default — no
`setClock()` call exists in the repo; the reference Python SMBus is
100 kHz too). One condition to remember: if the bus is ever moved to
400 kHz (the chip supports up to that, per the interface guide), swap
SDA/SCL to the datasheet's 1.8 kΩ.

And the direct answer to "could the pull-ups be draining the 3V3
rail?" — no, three independent proofs:

1. The measurements themselves: sensor VCC (1.871 V) + the drop
   (1.463 V) = 3.334 V — the Pico's rail is at full voltage. A
   drained rail sags at the source; this one does not; the loss is
   entirely between Pico pin 36 and the sensor's VCC pin.
2. Magnitude: all four lines pegged low simultaneously would draw
   ~2.1 mA against the Pico's 300 mA regulator budget (0.7 %) — and
   in reality only TRFR is being held low.
3. Topology: the 1.463 V drop lives across the VCC pin-header
   contact, and only the sensor's own operating current flows through
   that contact — the pull-ups sit on the veroboard and their current
   returns via the signal and GND pins, never through VCC. The drop
   is the sensor's current × the contact's resistance: at the
   datasheet's Processing-mode figure of 20 mA typical (Table 4-1),
   the contact is ≥ ~73 Ω — a worn spring or oxide film where a
   healthy socket is milliohms, and probably higher still, since a
   starved chip draws less than the full 20 mA.

No new work items from this survey: everything it found is consistent
with F13, and the fixes already queued (P3.26–P3.28) cover the
firmware side. The board-version correction changes only the bench
options — next-steps step 4 below is rewritten for the single 3V3 pin.

### F15 — the bench-power-supply experiment (2026-11-23): the feed path is convicted; the Pico's current capability is exonerated

**Verdict: with a bench supply holding the veroboard 3V3 rail up, the
sensor works; switching it off — nothing touched — starves the same
fixed measurement point; switching it on restores it. This convicts the
Pico's FEED path, acquits the Pico's regulator, and re-localises the
drop upstream of the header contact (correcting F13's lean).**

The controlled experiment: a bench supply feeding 3V3 and GND on the
veroboard rails (in parallel with the Pico's own feed), one fixed
measurement point on the veroboard between the sensor and the Pico:

| Bench supply | Same point reads | Device |
|---|---|---|
| ON (even a milliamp-scale limit) | 3.3 V | discovered immediately, reconnects, gestures recorded |
| OFF (no touching, no re-seating) | 1.87 V | the symptoms return |

- **"Insufficient current from the Pico" is ruled out, three ways.**
  (1) The Pico's own 3V3OUT pin measured ~3.33 V WHILE the sensor
  starved (F13's 1.871 + 1.463) — a regulator that cannot supply the
  current sags at its own pin; this one held full voltage under load.
  (2) The sensor needs ~20 mA in active-sensing mode (datasheet
  Table 4-1) against a regulator specified for roughly 300 mA.
  (3) Session 1's history: the same Pico fed a streaming sensor before
  the veroboard rewiring.
- **The off/on flip never implied "not a wiring fault".** A bad
  connection does not need touching to be in or out of circuit: with
  the supply ON, a stiff source holds the rail and the bad feed carries
  almost nothing; OFF, the bad feed is the only source and the rail
  collapses back to the 1.87 V brown-out equilibrium (the
  intersection of the feed's load line with the starved chip's
  behaviour — which is why the same voltage recurs). "Even down to
  milliamps" also fits: a healthy sensor IDLES at 110–200 µA
  (self-wake-up mode, Table 4-1) and only bursts to ~20 mA while
  actively sensing.
- **Correction to F13/F14:** the starved reading is ON THE VEROBOARD
  RAIL itself — upstream of the pin-header contact — so the header
  contact is exonerated (F13 leaned toward it; the fault is in the
  Pico→veroboard feed segment). F14's inference that the rail must
  have sat above ~2.4 V (from the SDA/SCL averages) was over-clever
  multimeter forensics; the rail was at ~1.87 V all along.

Also captured this session: the AC-BLE-06 official pass (F11's update
above) and a health capture on the supply-fed rail showing the sensor
fully alive (ts_low 0.00 %, frames and events flowing, the link
surviving a laptop Bluetooth off/on at conn=10 disc=1).

### F16 — ROOT CAUSE CONFIRMED AND FIXED (2026-11-24): the part-broken solid-core 3V3 feed wire

**Verdict: the wire from Pico 3V3OUT to the veroboard was partly broken
inside its insulation; replaced with stranded wire; the sensor streams
on Pico power alone. The round's sensor-side saga is CLOSED.**

The decisive bench test: the old solid-core wire read a healthy 3.3 V
with NO load (a multimeter's ~10 MΩ input draws ~0.3 µA — no drop
across a high-resistance break), but ANY load collapsed it — a 330 Ω
resistor across 3V3-to-GND (~10 mA) dragged the rail to 0 V. That is
the classic signature of a high-resistance series fault, and it
quantifies the break: at the sensor's ~20 mA the same break settled
at the 1.87 V brown-out equilibrium F13 measured. The wire is replaced
with new stranded-core wire.

Post-fix health capture (Pico power alone, bench supply removed, same
firmware build `2267497`, uptime 234–266 s, user tapping and
scrolling):

- `ts_low=0.00 %` (was 100 %) — the data-ready line idles high and
  pulses only when data waits; `short_reads=0(0.00 %)`.
- `frames sensor` 229 → 427 over 32 s while gesturing; `events`
  pos=83, touch 497 → 680, gest=1; `dropped=0`; `ble conn=5 disc=0`
  (one link, five subscription writes — P3.27's known semantics).
- Every HID (Human Interface Device) report kind reaching the laptop
  and climbing: `button` 336 → 690, `wheel` 121 → 139 (the §6
  touch-hold auto-scroll rows), `key` 16 → 32 (Page Up/Down taps),
  `media` 4 → 10 (doubletap track skips).
- **The transfer accounting is exact**: first line
  `ts_low 244 = frames sensor 229 + other 15`; last line
  `ts_low 448 = frames sensor 427 + other 21` — every data-ready pulse
  became exactly one dispatched frame, nothing missed, nothing
  spurious. The P3.24/P3.25 read machinery is proven on real data.
- The `other` trickle (~0.2/s, all-zero 26-byte reads, snapshot
  unchanged) is noise at this rate — occasional empty reads while the
  sensor refreshes its buffer; no action.
- Carried to the acceptance run, not faults: `events pos=83` with
  `hid pointer=0` — the hand was still, and the mapper only reports
  MOVEMENT (a deliberate moving hover must confirm pointer reports);
  AirWheel events remain zero (untested — the wheel reports above are
  the auto-scroll rows, not rotation).

## Resolution (2026-11-24) and what remains

The supply fault is FIXED (F16): the part-broken solid-core 3V3 feed
wire is replaced with stranded wire and the sensor streams on Pico
power alone. The bench steps previously listed here were superseded by
F15's re-localisation (the header contact was never the fault) and
F16's fix — the reflow/Pi-HAT options (old steps 3–4) never applied
and were never executed; the T5 rerun (old step 5) is done (F16's
capture); the Raspberry Pi cross-check (old step 6) is not needed.

What remains is the P4.0 gesture acceptance run (NO reflash needed —
keep the current build and the laptop's fresh pairing), serial monitor
plus the laptop-side capture (`evtest` or `hid-recorder` — the
T4-style evidence P4.0's diagnosis wants):

1. **Hover-move**: hold a hand a few centimetres above the sensor and
   move it slowly — expect `events pos` AND `hid pointer` climbing
   together, the cursor smooth, in the correct direction and axis.
   This is the first thing to confirm (today's capture has position
   events but zero pointer reports — a still hand).
2. **Taps per zone**: center → left click, east → right, west →
   middle, north → Page Up, south → Page Down (no letters — the
   P3.21 fix), doubletap north/south → track skip.
3. **AirWheel**: rotate a finger steadily over the center — expect
   `events wheel` climbing (zero so far — untested; the wheel reports
   captured today are the touch-hold auto-scroll rows, not rotation).
4. **Flicks**: expect `key`/`media` reports (already counting).
5. If convenient, capture the AC-BLE-04 latency evidence in the same
   session (hand movement vs cursor movement timestamps).

## Work items this round opened (fix_plan.md §3g)

- **P3.26** — the boot gate must never make the device invisible:
  retry the sensor configuration until success, use the reference reset
  timing (100 ms hold + 500 ms settle), start the radio regardless of
  sensor state, report sensor health on the health line.
- **P3.27** — the connect drain runs once per link (the opened callback
  fires once per subscription write): latch it; make `ble conn=` count
  real connections. Closes F4's mystery for good.
- **P3.28** — `SKYSTATE ble_dropped reason=0xNN`: the device-side link
  loss reason code, so the next bounce names itself without btmon.

No further items were opened by the round's closing captures
(2026-11-23/24): everything observed is expected behaviour or already
covered by P4.0 (the acceptance run) and P4.3 (whose AC-BLE-06 part is
now an official pass).
