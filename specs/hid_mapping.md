# Sensor Events → HID Mapping

**Status:** accepted for implementation (Phase 3 targets this document)
**Verification:** fixture-replay tests against `specs/fixtures/manifest.json`
(in-container) and hardware probe scenarios (outer loop).

## 1. Goal

Define exactly how MGC3130 GestIC sensor events become HID reports, so the
Skywriter behaves predictably as a pointer + media controller on any HID host.

### Why this contract exists

The GestIC sensor emits five independent data streams at 200 Hz; HID hosts
expect discrete, edge-triggered semantics (button down/up, signed deltas). The
gaps between them — press/release detection, counter wraparound, re-acquisition
after the hand leaves the sensing field — are where device feel is won or lost.
This document fixes those semantics so they can be tested against recorded
frames instead of re-tuned by hand on every change.

## 2. Canonical sensor event model

Frames are decoded per `specs/README.md` (framing) and Interface.pdf §4.5. The
canonical events (this is the vocabulary used in `fixtures/manifest.json`):

| Event | Source field | Canonical values |
|---|---|---|
| `position(x, y, z)` | `xyzPosition`, when `SystemInfo` PositionValid | 16-bit unsigned, 0–65535 per axis; origin = South-West corner at the sensor surface; z = height above surface |
| `gesture(code, class, edge)` | `GestureInfo`, when code ≠ 0 | code: 1 garbage, 2 flick W→E, 3 flick E→W, 4 flick S→N, 5 flick N→S, 6 circle CW, 7 circle CCW; class: 1 flick, 2 circle; edge: edge-flick flag (bit 16) |
| `touch(zone)` | `TouchInfo` bits 0–4 | zone: south, west, north, east, center |
| `tap(zone)` | `TouchInfo` bits 5–9 | same zones |
| `doubletap(zone)` | `TouchInfo` bits 10–14 | same zones |
| `airwheel(degrees)` | `AirWheelInfo`, when `SystemInfo` AirWheelValid | signed rotation delta; +360 = one clockwise revolution |
| `system_status(msg_id, error)` | `System_Status` (0x15) control frame | msg_id = the acknowledged control command (e.g. 0xA2 = 170); error = 16-bit little-endian error code, 0 = applied (Interface.pdf §3.6 Table 3-8). No HID output. |
| `firmware_info(fw_valid, version)` | `Fw_Version_Info` (0x83) control frame | fw_valid = FwValid byte (only 0xAA = valid, §4.3 Table 4-6); version = NUL-stripped version string, only carried for a valid report (nothing is emitted for invalid). No HID output. |

Payload offsets for the pinned mask `0x001F`: gesture word at payload 6, touch
word at 10, airwheel byte at 14, xyz at 16/18/20 (little-endian 16-bit).

### Semantics the decoder must honour

- **Touch fields are level-ish:** the touch bit repeats in every frame while the
  finger is on the electrode (see the vendor trace in Table A-3: touch center
  repeats with a resetting counter). Tap/doubletap bits are one-shot.
- **Touch counter** (bits 16–23) = approach time × 5 ms; informational only for
  HID purposes.
- **AirWheel wrap:** the counter is a free-running 8-bit byte (0–255) and 32
  increments ≈ 1 revolution (Interface.pdf Table 4-10), so it wraps 255→0
  while counting clockwise. Delta = **signed 8-bit difference** of consecutive
  counters: `d = ((cur - last + 128) % 256) - 128` steps, degrees =
  `d * 11.25`. A crossing of 255→0 is +1 step, not −255. (Side effect of
  signed 8-bit arithmetic: any per-frame change above 128 steps reads as
  counter-clockwise — physically implausible within one 5 ms frame, so
  shortest-path is always correct.) The **first AirWheel-valid frame after
  driver start or after any stretch of AirWheel-invalid frames is a silent
  baseline**: the counter is free-running, so it cannot be read against a
  stale reference — that frame only records the reference and emits nothing.
  (Fixed in both drivers 2026-11-05: the Python driver
  `library/skywriter/__init__.py` and the Arduino driver
  `arduino/Skywriter/skywriter.cpp` both implement the signed 8-bit
  difference and the silent first-frame baseline.)
- **Gesture in-progress frames** (`GestureInfo` bit 31 set, code 0) produce no
  event. Code 1 (garbage) produces a `gesture(1, …)` event which the mapping
  table maps to *nothing*.
- **All set touch bits** in a frame produce their events; a frame may carry
  touch + position + airwheel simultaneously and all must be processed.
  (Both drivers were fixed here 2026-11-05, fix item P3.10 / former deviation
  D4: the Arduino driver used to `return` after the first touch bit — which
  also skipped the AirWheel decode of the same frame — and the Python driver
  used to `break` out of the touch loop after the first bit. Fixture
  `touch_two_zones` / F23 hard-asserts a two-touch frame on both drivers.)
- **Sensor sampling:** frames arrive every 5 ms while the hand is tracked
  (Interface.pdf §3.6.4).

## 3. Pointer model (position → mouse)

Let `pos` be the canonical 0–65535 position, x/y.

1. **Normalization:** float position = `raw / 65536.0` (this matches the
   Python driver's `_round_to = 4` output; the Arduino driver's raw uint16 is
   the canonical form — the HID layer works in raw units).
2. **Deltas:** `dx = (x_n - x_{n-1}) * GAIN`, `dy = (y_n - y_{n-1}) * GAIN`
   with `GAIN` a single tunable constant (initial value: 1/256 — full field
   width ≈ 256 cursor-widths; hardware loop tunes it and records the final
   value here).
3. **Sign:** +x = East = cursor right; +y = North = cursor **up** on screen
   (HID y grows upward; hosts flip as needed — do not pre-flip).
4. **Re-acquisition (jump rejection):** if `|dx|` or `|dy|` exceeds
   `JUMP_THRESHOLD` (initial: 8192 raw units ≈ 1/8 field width) or position was
   invalid in the previous frame, the delta is **discarded** and the position
   becomes the new baseline. This prevents the cursor flying across the screen
   when the hand re-enters the field.
5. **Lift-off gating:** tracking is active only while PositionValid is set. On
   lift-off (position invalid for > 100 ms) all held buttons are released
   (see §4) and the next valid position re-baselines per rule 4. z is *not*
   used for speed scaling in the default profile (kept simple and predictable);
   it is reserved for a future "height sensitivity" feature.
6. **Cadence:** position frames are coalesced into at most one mouse report per
   BLE connection interval; at most 200 reports/s. Deltas accumulate across
   coalesced frames — never dropped. The engine's cadence constant is
   `REPORT_INTERVAL_MS` (initial: 15 ms — the slowest common BLE HID
   connection interval, so the pointer rate never falls below the ≥ 60 Hz
   floor of AC-BLE-04; the firmware may tighten it towards the live
   connection interval, fix item P3.18, and the hardware loop tunes final
   values per P4.5).

## 4. Touch semantics (buttons)

The sensor has no explicit "release" event, so release is inferred:

- `touch(zone)` frame seen → **press** (first frame only; repeats do not
  re-press).
- No touch frame for `TOUCH_RELEASE_MS` (initial: 200 ms = 40 missed 5 ms
  frames) → **release**.
- A press while another zone is held is allowed (multi-button); each zone has
  independent press state.
- `tap(zone)` → press + release (`TAP_CLICK_MS`, initial: 50 ms) — it never
  leaves a button held.
- `doubletap(zone)` → two taps separated by `TAP_CLICK_MS`.
- Any explicit release trigger (lift-off, disconnect) releases all held buttons
  immediately.

## 5. Airwheel semantics (scroll)

- One sensor step (11.25°) = one wheel notch = `MouseBLE.move(0, 0, ±1)`.
- Clockwise (positive degrees) = scroll **up** (away from user), matching
  conventional "rotate a physical wheel forward" feel; configurable via
  `AIRWHEEL_INVERT`.
- Fractional steps accumulate; e.g. two consecutive 45° deltas (4 steps each)
  = 8 notches total. Accumulator resets on lift-off.
- Airwheel deltas are emitted immediately (not coalesced) — scroll feel is
  latency-sensitive.

## 6. Default mapping profile

The complete default profile. Every row is a single table entry in the
implementation (one source of truth for config overrides — see §7).

| Sensor event | HID output | Rationale |
|---|---|---|
| `position` delta | Relative mouse movement (§3) | Core pointing behaviour |
| `airwheel(+)` / `airwheel(-)` | Scroll up / scroll down (mouse wheel) | Natural rotary affordance |
| `touch(center)` hold | Left button down/up (§4) | Primary click = the prominent center electrode |
| `tap(center)` | Left click | Tap-to-click (touchpad convention) |
| `doubletap(center)` | Double click | Touchpad convention |
| `tap(east)` | Right click | Secondary click on the dominant-hand side |
| `tap(west)` | Middle click | Tertiary click |
| `touch(north)` hold | Auto-scroll up: wheel −1 notch per 100 ms while held | Hold-to-scroll without occupying the airwheel |
| `touch(south)` hold | Auto-scroll down: wheel +1 notch per 100 ms while held | As above |
| `tap(north)` | Keyboard `Page Up` | Document navigation |
| `tap(south)` | Keyboard `Page Down` | Document navigation |
| `doubletap(north)` | Consumer `Scan Next Track` | Media |
| `doubletap(south)` | Consumer `Scan Previous Track` | Media |
| `gesture(2 … flick W→E)` | Consumer `Scan Next Track` | Big horizontal flick = track skip |
| `gesture(3 … flick E→W)` | Consumer `Scan Previous Track` | As above |
| `gesture(4 … flick S→N)` | Consumer `Volume Increment` (repeats per event) | Big vertical flick = volume |
| `gesture(5 … flick N→S)` | Consumer `Volume Decrement` | As above |
| `gesture(6 … circle CW)` | Consumer `Volume Increment` | Only emitted when AirWheel is **disabled** (see note) |
| `gesture(7 … circle CCW)` | Consumer `Volume Decrement` | As above |
| `gesture(1 … garbage)` | *nothing* | Garbage model = unintentional motion |
| `doubletap(east)` / `doubletap(west)` | *nothing* (reserved) | Deliberately unmapped to avoid accidental triggers |

**Circle/AirWheel exclusivity (hardware constraint):** the GestIC library only
recognizes circles when AirWheel is disabled (Interface.pdf Table 4-10 and the
vendor trace "Circle Gesture not recognized because AirWheel is On" in Table
A-3). The default profile enables AirWheel (it is the better scroll
affordance), so circle rows are dormant unless `AIRWHEEL_ENABLED` is turned
off. This is a sensor constraint, not an implementation choice.

**HID report channels:** pointer = mouse report; clicks/wheel = mouse report;
`Page Up`/`Page Down` = keyboard report; media/volume = consumer-control report
(`KeyboardBLE.sendConsumerReport`, usages: Next Track `0x00B5`, Previous Track
`0x00B6`, Volume Inc `0x00E9`, Volume Dec `0x00EA`).

**Event priority:** if a single frame yields several events (e.g. touch +
position), all are processed per §2. If gestures and touches arrive in the same
5 ms window they are independent — no arbitration needed.

## 7. Configuration model

The mapping table of §6 **is** the implementation: one static table mapping
`(event kind, value)` → HID action, with tunables (`GAIN`, `JUMP_THRESHOLD`,
`TOUCH_RELEASE_MS`, `TAP_CLICK_MS`, `AIRWHEEL_INVERT`, `AIRWHEEL_ENABLED`,
`REPORT_INTERVAL_MS`, `LIFT_OFF_MS`) as named constants in the same place. No
second copy of the mapping may exist (any Python port consumes this same
document). The single implementation is the `SkywriterHID` mapping engine in
`pico-arduino/SkywriterHID/src/` — the full table is live there (pointer
model since P3.12; the §4 touch semantics and §6 button rows since P3.13;
the §5 AirWheel rows since P3.14; the remaining §6 rows — tap Page Up /
Page Down, doubletap media track-skip, hold auto-scroll, the flick/circle
consumer rows, and the deliberate garbage/reserved → nothing rows — since
P3.15). A future config
channel (e.g. BLE characteristic) may expose the tunables; not required by
this spec.

## 8. Acceptance criteria

Fixture names refer to `fixtures/manifest.json`.

| ID | Criterion | Fixtures / method |
|---|---|---|
| AC-MAP-01 | Position frames produce relative movement with correct sign and magnitude; jump rejection and re-baseline work; lift-off re-baselines; move reports coalesce to ≤ one per connection interval with deltas accumulated. | F01, F19 (jump), `pointer_move` (deltas + cadence), `pointer_lift_off_rebaseline` (lift-off), probe |
| AC-MAP-02 | Touch press → button down on first frame; repeats don't re-trigger; release after `TOUCH_RELEASE_MS` without frames. | F07, F08 (sequence), F18 |
| AC-MAP-03 | Tap = 50 ms click; doubletap = two clicks; zone → button per §6. | F09, F10 |
| AC-MAP-04 | Airwheel emits 11.25°-quantized notches, signed correctly, and **survives counter wrap** (255→0 is +1 step, not −255). | F11–F15 (sequences) |
| AC-MAP-05 | Gestures map per §6; garbage and in-progress frames emit nothing; edge-flick flag is carried in the canonical event. | F02–F06 |
| AC-MAP-06 | A frame carrying touch + airwheel + position produces **all** corresponding outputs. | F18 |
| AC-MAP-07 | Lift-off releases all buttons and resets the pointer baseline and airwheel accumulator. | probe + F07/F08 sequence (release by silence) |
| AC-MAP-08 | Media/consumer actions appear on the consumer-control report; keyboard actions on the keyboard report; nothing is emitted on the wrong report. | `hw/ble_hid_probe.py` |
| AC-MAP-09 | All AC-MAP-01…06 pass against the **Python** decoder and the **Arduino** decoder with identical canonical events (parity), modulo the deviations tracked in `specs/README.md` (which must be fixed to close this criterion). | fixture replay both drivers |
