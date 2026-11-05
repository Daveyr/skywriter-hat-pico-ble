# BLE HID Profile — Pico W Skywriter Controller

**Status:** accepted for implementation (Phase 3 targets this document)
**Verification:** `hw/ble_hid_probe.py` (host, automated), `hw/serial_probe.py`
diagnostics, plus a manual multi-OS smoke checklist (`AC-BLE-08`).

## 1. Goal

Make the Pico W advertise as a standard **Bluetooth LE HID device** (HOGP,
HID over GATT) that consumes Skywriter sensor events and emits standard HID
reports, so any BLE HID host (Linux/BlueZ, Windows, macOS, Android, iOS) can
use it as a pointer + media controller **without custom drivers or software**.

### Why this design

- The MGC3130 + Pico W combination already has the full sensor stack in this
  repo (I2C driver, event decode). The missing piece is transport; BLE HID is
  the only transport that works with phones and tablets as well as desktops.
- Standard HID reports (not a custom GATT service) are what make the device
  driver-free. A custom service would require per-host client software, which
  contradicts the goal.

## 2. Scope

**In scope:** BLE peripheral role, HID device profile (keyboard + mouse +
consumer control), pairing/bonding, connection management, battery service.
**Out of scope (explicit non-goals):** Bluetooth Classic HID
(`MouseBT`/`KeyboardBT`), USB HID (TinyUSB), BLE central role, WiFi
(coexistence with WiFi on the CYW43439 is out of scope), OTA firmware update,
absolute pointer mode.

## 3. Stack decision (spike results, 2026-11-04)

Verified against the **arduino-pico core 6.3.1** installed in the
`skywriter-arduino` Docker volume (`packages/rp2040/hardware/rp2040/6.3.1/libraries/`):

| Component | Provided by core | Role |
|---|---|---|
| `HID_Bluetooth` | yes (`PicoBluetoothBLEHID.h/.cpp`) | BTstack-based BLE HIDS device wrapper (`hids_device`, battery + device-info GATT servers) |
| `MouseBLE` | yes | Mouse HID report descriptor + `move(x, y, wheel)` / button API |
| `KeyboardBLE` | yes | Keyboard HID descriptor + `sendConsumerReport(uint16_t)` |
| `JoystickBLE` | yes | Not used (out of scope) |
| `BTstackLib`, `BLE` | yes | Available but not required at the application level |

**Decision:** build on `HID_Bluetooth`'s `PicoBluetoothBLEHID` via the
`MouseBLE` + `KeyboardBLE` composite mechanism. Key spike findings that shape
the implementation:

1. **Composite device = link both libraries, call one `begin()`.**
   `MouseBLE.cpp`/`KeyboardBLE.cpp` each register themselves through the
   weak-link hooks `__BLEInstallMouse` / `__BLEInstallKeyboard`, and
   `__SetupHIDreportmap(...)` merges every linked class into a single HID
   Report Map with distinct Report IDs. `PicoBluetoothBLEHID.startHID(...)`
   is then called **by whichever `begin()` runs** — calling both `begin()`
   methods starts the HID transport twice. The implementation must call
   exactly one `begin()` (requirement `AC-BLE-02`).
2. `startHID(localName, hidName, appearance, descriptor, size, battery)`
   takes the merged descriptor; appearance comes from `__BLEGetAppearance()`.
3. Pairing is handled inside the wrapper: `SM_EVENT_JUST_WORKS_REQUEST` is
   auto-confirmed and numeric-comparison is auto-confirmed.
4. Connection callbacks exist: `setOpenedCB`, `setClosedCB`,
   `setCanSendNowCB` (fired on `HIDS_SUBEVENT_INPUT_REPORT_ENABLE` etc.).
5. Battery service is built in (`battery_service_server`, `setBattery(lvl)`).

Not used deliberately: the standalone `BLE` (ArduinoBLE-compatible) library —
it does not provide a HID device profile — and `BluetoothHIDMaster` (that is a
HID *host*).

## 4. GATT layout requirements

The device shall expose (in addition to GAP/GATT):

| Service | Requirement |
|---|---|
| **HID Service (0x1812)** | Report Map = composite mouse + keyboard + consumer-control (as assembled by `__SetupHIDreportmap` from `MouseBLE` + `KeyboardBLE`). Report Protocol Mode. Input Reports enabled via notifications. HID Control Point present. |
| **Device Information (0x180A)** | Manufacturer `Pimoroni`, Model `Skywriter HAT`, PnP ID reflecting the RP2040/Pico W. |
| **Battery Service (0x180F)** | Present; see §8. |

Device identity:

- GAP device name: `Skywriter HID` (configurable constant; `AC-BLE-01`).
- Appearance: value returned by `__BLEGetAppearance()` for the linked classes;
  must advertise HID class semantics (`AC-BLE-01`).
- Advertising: connectable, undirected; includes the device name. Advertising
  starts at boot and whenever the link drops (`AC-BLE-05`).

## 5. Pairing, security, bonding

- Pairing method: Just Works (auto-confirmed by the wrapper), accepting the
  numeric-comparison variant when the host proposes it (`AC-BLE-03`).
- HID hosts commonly require an encrypted link before enabling HID report
  notifications; the device must not attempt to send Input Reports before the
  host enables them (respect `HIDS_SUBEVENT_INPUT_REPORT_ENABLE`).
- **Bonding:** a bonded host must reconnect without re-pairing after a
  power cycle of the Pico W (`AC-BLE-06`). Code-level truth (resolved by
  P3.17b against core 6.3.1, supersedes the spike's open question): the
  core's Security Manager bond store is the **flash-backed**
  `le_device_db_tlv.c` — the core's shipped build config
  (`include/btstack_config.h`) defines `NVM_NUM_DEVICE_DB_ENTRIES 16`
  (16 persistent bond entries, verified by the linked object's compiled
  `entry_map` symbol size of 16 bytes), the boot-time variant
  initialisation chain wires it up before any sketch code runs
  (`initVariant()` → `init_cyw43_wifi()` → `cyw43_arch_init_with_country()`
  → `cyw43_arch_init()` → `btstack_cyw43_init()` → `setup_tlv()` →
  `le_device_db_tlv_configure()`, all under the
  `ipbtstack=ipv4btcble` build menu), and the paired Long-Term Key is
  persisted on pairing completion (`le_device_db_encryption_set` →
  `le_device_db_tlv_store`) into a dedicated 8 KiB flash section
  (`__bluetooth_tlv`, two 4 KiB banks) appended after the firmware image.
  Flash persistence is asserted only at the code level here;
  `AC-BLE-06` remains the hardware gate that proves it on real radios
  (P4.3). If hardware contradicts the expectation, record a spec
  deviation row in `specs/README.md`.

## 6. Connection lifecycle

| State | Behaviour |
|---|---|
| Boot | Initialize sensor stack first, then BLE; start advertising. |
| Connected | Send Input Reports only while the host has enabled them. |
| Link loss | Return to advertising within 5 s (`AC-BLE-05`). Report state to the serial console (`hw/serial_probe.py` asserts on these lines). |
| Unconnected | Sensor events are **dropped**, not queued — HID describes current state, and stale reports replayed on reconnect would be wrong. On (re)connect, send the neutral report (no buttons, zero deltas) once to resync host state (`AC-BLE-07`). |

## 7. Performance

| Metric | Requirement | Verification |
|---|---|---|
| Gesture → report latency | < 100 ms end-to-end | `AC-BLE-04` (host-side timestamped probe) |
| Pointer report rate | ≥ 60 Hz sustained, target 200 Hz (sensor update rate is 200 Hz / 5 ms — Interface.pdf §3.6.4) | `AC-BLE-04` |
| Report coalescing | Move reports may be coalesced to the connection interval; button/press transitions must never be coalesced away | `AC-BLE-04` |

Implementation note (P3.18, 2026-11-05): the firmware requests the
[7.5, 15] ms interval window on connection (`gap_request_connection_
parameter_update`) and tracks every negotiated / re-negotiated interval
through its BTstack HCI event handler, reprogramming the engine's
move-report cadence to match — so "coalesced to the connection interval"
is the live value, not a fixed guess. Wheel/keyboard/media transitions are
emitted immediately, never coalesced. The RF truth of this row is still
the `AC-BLE-04` hardware probe; open question 3 below (send-blocking
behaviour) remains for that probe.
| Reconnect time | < 5 s advertising + host reconnect | `AC-BLE-05` |

## 8. Battery reporting

The Pico W is USB-powered in the target setup: report `100 %` at connect and on
query. `setBattery()` must be called at least once so the Battery Service
reports a sane value (`AC-BLE-03`).

## 9. Acceptance criteria

Each criterion is verified by the outer hardware loop unless marked manual.

| ID | Criterion | Verification |
|---|---|---|
| AC-BLE-01 | Device advertises as `Skywriter HID` with HID-class appearance; scan finds exactly one instance. | `hw/ble_hid_probe.py` scan |
| AC-BLE-02 | Single HID device with a composite Report Map containing mouse, keyboard and consumer-control reports; exactly one `begin()` is called at runtime (no double `startHID`). | probe GATT read of Report Map + serial log assert |
| AC-BLE-03 | Pairing completes (Just Works / numeric comparison); Device Information and Battery services readable; battery = 100 %. | `hw/ble_hid_probe.py` |
| AC-BLE-04 | Sensor event → HID Input Report latency < 100 ms; sustained pointer report rate ≥ 60 Hz under continuous `onXYZ` input; button transitions always delivered. | timestamped probe fed by the sensor test sketch |
| AC-BLE-05 | Link loss returns the device to advertising within 5 s; reconnect succeeds. | probe disconnect/reconnect cycle |
| AC-BLE-06 | Bonded host reconnects after Pico W power cycle **without re-pairing** (or a documented spec deviation exists). | probe with bond store on the host |
| AC-BLE-07 | Reports are dropped while unconnected; neutral resync report is sent on connect. | probe + serial log assert |
| AC-BLE-08 | Manual smoke: works as pointer + media keys on Linux, Windows, and Android. | manual checklist (record results in `HW_REPORT.md`) |

## 10. Open questions (resolve during implementation)

1. ~~Bond storage persistence on this core (§5)~~ — **resolved by P3.17b**
   (2026-11-05, code level): the Security Manager uses the **flash-backed**
   `le_device_db_tlv.c` store with 16 entries, wired at boot into the
   core's own 8 KiB flash section, so no on-flash store needs wiring and no
   re-pair deviation is expected. `AC-BLE-06` still verifies it on real
   hardware (P4.3).
2. Exact `__BLEGetAppearance()` value for the mouse+keyboard composite — read
   at runtime and record in `HW_REPORT.md`.
3. Whether `setCanSendNowCB` is needed to pace reports on slow connection
   intervals; probe `AC-BLE-04` will reveal send-blocking behaviour.
