# Skywriter Pico W BLE HID — Specifications

This directory is the **acceptance source of truth** for turning the Skywriter HAT
(MGC3130 GestIC sensor) into a Pico W–based BLE HID controller. The Ralph
development loop treats every `AC-*` identifier here as a pass/fail gate: work is
complete when the acceptance criteria in these documents are verified.

## Documents

| Document | Contents |
|---|---|
| [ble_hid.md](ble_hid.md) | BLE HID (HOGP) profile: stack decision, GATT layout, pairing, connection lifecycle, performance. |
| [hid_mapping.md](hid_mapping.md) | Sensor-event model and the gesture → HID mapping (the default "profile"), pointer/touch/airwheel semantics. |
| [fixtures/](fixtures/) | Replayable MGC3130 wire frames with expected decode results (`manifest.json`). |

## Why specs first

Hardware validation is slow (flash + physical gestures + BLE probing, minutes per
cycle) and the sensor's behaviour is defined by a 57-page vendor protocol
document, not by our code. Pinning the wire format and the event → HID contract
up front lets the in-container loop verify decoder and report-generation logic
against fixed frames (`specs/fixtures/`), so the scarce hardware cycles are spent
only on what genuinely needs a device: RF, pairing, latency, and feel.

## Source of truth and provenance

- Protocol facts come from `datasheets/Interface.pdf` (MGC3130 GestIC Library
  Interface Description, DS40001718C) and are cited by section/table.
- Every fixture records its provenance in `fixtures/manifest.json`:
  `vendor` (verbatim from Interface.pdf) or `synthetic` (constructed to a cited
  table's layout). Fixtures marked `synthetic` are pending confirmation against
  real captures in the outer hardware loop.
- When these specs disagree with driver code, **the spec wins**; the code is
  wrong. Deviations are tracked below until fixed.

## MGC3130 message framing (summary)

Reference: Interface.pdf §3.2–3.4. Every message is 4–255 bytes, exchanged as
one I2C frame:

```
Header (4 bytes)                  Payload (message-ID dependent)
size   flags  seq   ID            elements, little-endian
1 B    1 B    1 B   1 B           ...
```

- `size` — complete message size in bytes **including the header**
  (e.g. `0x18` = 24-byte message).
- `flags` — reserved (vendor examples use `0x08`).
- `seq` — increments per message from the MGC3130; ignored in host→device
  messages.
- `ID` — message ID. IDs in use: `0x91` Sensor_Data_Output, `0x15`
  System_Status, `0x83` Fw_Version_Info, `0xA2` Set_Runtime_Parameter,
  `0x06` Request_Message (§3.1).
- Payload elements are **little-endian** (§3.4).

Sensor_Data_Output (`0x91`) payload layout (§4.5, Table 4-10):
`DataOutputConfigMask`(2) `TimeStamp`(1) `SystemInfo`(1) then, present only
when the corresponding mask bit is set and **in this order**:
`DSPStatus`(2, bit 0) `GestureInfo`(4, bit 1) `TouchInfo`(4, bit 2)
`AirWheelInfo`(2, bit 3) `xyzPosition`(6, bit 4) `NoisePower`(4, bit 5)
`CICData`/`SDData` (bits 11/12). Fixed payload offsets (gesture at 6, touch at
10, airwheel at 14, xyz at 16) are **only valid when the mask is `0x001F`**
(all of DSP+gesture+touch+airwheel+xyz enabled). Decoders must check the mask
before indexing.

Key field facts (cited in `hid_mapping.md` where used):

- `SystemInfo` bit 0 = PositionValid, bit 1 = AirWheelValid, bit 7 = DSPRunning.
- `GestureInfo` bits 0–7 = gesture code (0 none, 1 garbage, 2–5 flicks,
  6/7 circles), bits 12–15 = gesture class, bit 16 = edge flick, bit 31 =
  recognition in progress.
- `TouchInfo` bits 0–14 = touch/tap/doubletap electrodes, bits 16–23 = touch
  counter (× 5 ms approach time).
- `AirWheelInfo` byte 0 = free-running 8-bit rotation counter (0–255, wraps
  255→0); 32 increments ≈ 1 full rotation.
- `xyzPosition` = three 16-bit LE values, range 0–65535 each; origin is the
  lower-left (South-West) corner at the sensor surface.

## Known driver deviations (found 2026-11-04)

These are implementation defects relative to the spec above. They are listed
here so tests and the loop can be written against spec behaviour; each must be
fixed in the drivers (Phase 2/3) and then removed from this table.

The table is **empty as of 2026-11-05 (fix item P3.19)** — every row recorded
here has been resolved and removed. `tests/deviations.py` treats every
remaining row as live and open, so a void row would poison the single source
of truth; a row is removed in the same change that closes it (the D2/D8
convention). Closure history for the documentation-only rows:

- **D8 (closed 2026-11-05, P3.19)** — the row claimed the `AGENTS.md` gotcha
  "`begin()` does not send `SW_SET_RUNTIME`" was stale. Truth-check against
  the current tree found the opposite: the gotcha is **accurate** —
  `arduino/Skywriter/skywriter.cpp`'s `begin()` sends no Set_Runtime_Parameter
  (0xA2, the sensor-configuration command) traffic at all (only GPIO setup and
  the reset pulse; sensor bring-up belongs to the `SkywriterController`
  firmware, P3.16), and `poll()` still resets the transfer pin (TS) to plain
  `INPUT` at the end of each transfer. The stale side was the ledger row
  itself, so the fix is this removal plus keeping the gotcha correct in
  `AGENTS.md` (its Python line references were re-checked and refreshed).
  Like D2, no fixture annotation referenced D8, so nothing needed re-arming
  (the `tests/deviations.py` realization checks are vacuously green with an
  empty table).
