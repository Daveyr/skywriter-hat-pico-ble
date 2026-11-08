# Sensor frame fixtures — replay corpus

Replayable MGC3130 wire frames with expected decode results, used to test the
Arduino and Python decoders and the HID mapping **without hardware** (see
`specs/README.md` for why this matters). The outer hardware loop later
re-validates a sample of these against the real sensor.

## Format

- Each fixture is a `.hex` file: one line, space-separated lowercase hex bytes,
  exactly the bytes of one I2C message (header included), as read by
  `read_i2c_block_data(0x42, 0x00, 26)` on the wire.
- `manifest.json` is the single source of truth for fixture metadata and
  expected results. Fixture files are pure data; expectations live only in the
  manifest (no duplication).
- Loading in Python:

  ```python
  frame = bytes.fromhex(open('F01_position_only.hex').read().strip())
  assert len(frame) == frame[0]  # size byte = total message size (incl. header)
  ```

- Sequences matter: several expectations (airwheel deltas, jump rejection,
  press/release) depend on previously fed frames. Play `scenarios[].frames` in
  listed order into a fresh decoder state.

## Naming

`F##_<event>[_<detail>].hex` — number is stable; rename nothing, add new
numbers. `F16`/`F17` are non-`0x91` control messages (System_Status,
Fw_Version_Info).

## Frame layout (mask 0x001F)

Sensor frames here use the pinned full layout `DataOutputConfigMask = 0x001F`
so every field is present at its fixed offset (see `specs/README.md`):

```
00-01  DataOutputConfigMask (LE)   1f 00
02     TimeStamp (200 Hz counter)
03     SystemInfo (bit0 PositionValid, bit1 AirWheelValid, bit7 DSPRunning)
04-05  DSPStatus        00 73   (calibration flags 0x00, Tx freq 115 kHz)
06-09  GestureInfo (LE u32): bits 0-7 code, 12-15 class, 16 edge flick, 31 in-progress
10-13  TouchInfo   (LE u32): bits 0-4 touch S/W/N/E/C, 5-9 tap, 10-14 doubletap,
                             16-23 touch counter (×5 ms)
14-15  AirWheelInfo: byte 0 = rotation counter (free-running 8-bit, 0-255, wraps
            255->0; 32 counts/rev), byte 1 reserved
16-21  xyzPosition: three LE u16 (x, y, z), 0-65535
```

Header: `size`(=total bytes incl. header) `flags`(0x08, per vendor examples)
`seq` `id`(`0x91` sensor, `0x15` status, `0x83` fw version).

### Shorter frames (mask without the AirWheel field)

`DataOutputConfigMask` decides which payload elements are present, in the
fixed element order of `specs/README.md`. `F21_circle_cw` / `F22_circle_ccw`
use mask `0x0003` (DSPStatus + GestureInfo — the AirWheel-disabled
configuration under which the sensor recognizes circles, `hid_mapping.md` §6
"Circle/AirWheel exclusivity"): only elements *before* AirWheelInfo are
present, so every fixed offset up to GestureInfo is unchanged and the
decoders' indexing stays valid. Elements that would shift when the AirWheel
field is absent (xyzPosition and after) do not appear in these frames — no
fixture yet exercises a mask that shifts them.

## Provenance

Each fixture's `source` field in the manifest is one of:

- **vendor** — verbatim from `datasheets/Interface.pdf` (cited table), bytes
  unchanged (currently F16 only); reserved bits are kept as the vendor wrote
  them, which doubles as a "reserved bits are ignored" test.
- **vendor-derived** — vendor field values cited from an Interface.pdf table,
  repacked into our standard 26-byte frame layout. Not byte-for-byte vendor.
- **vendor pattern** — the shape of a vendor trace row reconstructed with
  clean values.
- **synthetic** — constructed to the cited table's layout with clean values.
  All non-`vendor` fixtures are pending confirmation against real captures
  in the outer hardware loop.

## Time-dependent expectations

Release-after-silence (`TOUCH_RELEASE_MS`) and auto-scroll cadence are
wall-clock behaviours: scenarios that exercise them carry `time_gap_ms` and
describe the timed outcome in their `note` / `expect.hid` records. Replay
tests must simulate the gap (virtual clock) rather than sleep.

## Adding fixtures

1. Add the next `F##` `.hex` file.
2. Describe it in `manifest.json` (`frames`) with provenance.
3. Add or extend a `scenario` with structured expectations: `expect.canonical`
   in the `tests/canonical.py` grammar and `expect.hid` in the
   `tests/hid_grammar.py` grammar (see `tests/README.md`). Known driver
   deviations may only be tolerated via `omit_pending` / `keys_pending`
   annotations that reference an open row in `specs/README.md`'s ledger — not
   by silently writing weaker expectations. Expectations must match
   `specs/hid_mapping.md` §6 — if you find yourself writing a different
   expectation, the spec needs an update first (and that is a spec change to
   review, not a test to bend).
