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

| # | Driver | Deviation | Evidence |
|---|---|---|---|
| D2 | Arduino (`arduino/Skywriter/skywriter.cpp`) | `setRuntimeParam` loops `i < 16` over 15-byte command arrays: one out-of-bounds byte is written to I2C after the 16-byte message. | `cmdAirWheel[]` et al. have 15 initializers; loop bound is 16. |
| D3 | Arduino (`arduino/Skywriter/skywriter.cpp`) | AirWheel delta ignores the 8-bit counter wrap: `(cur - last) / 32.0` must be a signed modulo-256 (8-bit) difference, `d = ((cur - last + 128) % 256) - 128`, and the decoder must silently re-baseline on the first AirWheel-valid frame after a gap. Crossing 255→0 produces a large negative delta that is silently dropped (`|delta| < 0.5` guard). Python side fixed 2026-11-05 (signed delta + silent first-frame baseline, `library/skywriter/__init__.py`; hid_mapping.md §2 documents the baseline rule). | `skywriter.cpp` airwheel branch. |
| D4 | Arduino | Touch decode reports only the highest set bit and `return`s from `handle_sensor_data`, skipping AirWheel decode for that frame. Spec requires processing every set bit and continuing to the remaining fields. | `skywriter.cpp` touch loop, `return` at the first match. |
| D6 | Python | `_handle_firmware_info` treats any `FwValid` other than `0x00`/`0x0A` as valid. Spec (Interface.pdf §4.3) defines `0xAA` = valid, `0x00` = empty, `0x0A` = invalid. | `__init__.py` `_handle_firmware_info`. |
| D7 | Python + Arduino | Gesture attributes are discarded: gesture class (bits 12–15), edge-flick flag (bit 16), recognition-in-progress (bit 31). | Both decoders read only `GestureInfo` byte 0. |
| D8 | `AGENTS.md` | Gotcha "`begin()` does not send `SW_SET_RUNTIME`" is stale — `begin()` now sends the four runtime-parameter commands (mirroring Python `setup()`). The `poll()` `INPUT` vs `INPUT_PULLUP` note is still valid. | `skywriter.cpp` `begin()`. |
| D9 | Python + Arduino | Control-frame results are not surfaced as decoder events: `System_Status` (`0x15`, the acknowledge to a Set_Runtime_Parameter command) and `Fw_Version_Info` (`0x83`) produce no record (Python handlers ignore the payload; Arduino `poll()` cases are `// Unimplemented` no-ops). Structured fixture expectation for `status_ack` / `fw_version_valid` is therefore pending this deviation. (Found migrating fixtures to the machine-checkable grammar — fix item P3.11b.) | `tests/test_scenarios.py` realization check; `specs/fixtures/manifest.json` scenarios `status_ack`, `fw_version_valid`. |
| D10 | Python | Circle gestures (wire codes 6/7, clockwise/counter-clockwise) are silently dropped: the gesture branch in `_handle_sensor_data` matches codes 6/7 in the `gestures` list but dispatches only garbage/flick ("Discovered closing D5, 2026-11-05"). The `_on_circle` registry is dead code — nothing can even register into it (no `circle()` decorator exists). Spec `hid_mapping.md` §2 exposes codes 6/7 as gesture events; their §6 mapping rows (Consumer volume) are covered by P3.15. The return path also matters to the mapping engine because §6 makes circle rows live only when AirWheel is disabled (mask without bit 3) — no current fixture exercises that mask. | `_handle_sensor_data` gesture branch; `_on_circle` initialized (line 70) but never read. |
