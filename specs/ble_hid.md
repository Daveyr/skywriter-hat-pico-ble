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

Implementation note (P3.26, 2026-11-25): "initialize the sensor stack
first" is a bounded step, never a gate — the sensor configuration sends
its commands once in `setup()` and, if an acknowledgment is missed,
retries the WHOLE sequence from `loop()` forever while the radio and the
Bluetooth life cycle run regardless. The old permanent boot deny (the
radio never starting until the sensor acknowledged every command) made
the whole device invisible on the cold boots of hardware session 5
(findings F12/F13, recorded in `fix_plan.md`) and is forbidden by this
note. Every
failed attempt prints its own serial evidence line
(`SKYSTATE sensor_config_retry attempt= cmd_index= elapsed_ms=`), the
success line names the attempts and duration (`SKYSTATE sensor_ok
attempts= took_ms=`), and the health line carries the outcome
(`sensor_cfg=`, `cfg_attempts=`). Sensor polling starts only once the
configuration completes, so a poll cannot steal an acknowledgment frame
a waiting command is parked on.
| Connected | Send Input Reports only while the host has enabled them. |
| Link loss | Return to advertising within 5 s (`AC-BLE-05`). Report state to the serial console (`hw/serial_probe.py` asserts on these lines). |
| Unconnected | Sensor events are **dropped**, not queued — HID describes current state, and stale reports replayed on reconnect would be wrong. On (re)connect, send the neutral report (no buttons, zero deltas) once to resync host state (`AC-BLE-07`). |

Implementation note (P3.27, 2026-11-25): the Bluetooth stack fires the
wrapper's "opened" callback once per notification-enable write — the host
writes one enable switch per report channel, four to five per connection —
not once per link. The connect drain of the rows above (the battery
refresh, the neutral resync report — "once" per (re)connect, §8) is
therefore **latched per link** in the firmware: the latch is set on the
first opened event of a link and cleared on the closed event, so one link
drains exactly once and the health line's `ble conn=` counts real links.
Hardware session 5's btmon capture recorded the unlatched shape this note
forbids: one link, four battery notifications, four neutral-report pairs,
`conn=5 disc=0`.

Implementation note (P3.28, 2026-11-25): the Link-loss row's console
evidence names its cause — the `SKYSTATE ble_dropped` line carries the
HCI (Host Controller Interface, the radio-level event channel)
disconnection reason code the radio itself reported (`reason=0xNN` plus a
human-readable name, e.g. 0x06 key_missing = a stale pairing after a
reflash orphaned the bond, 0x08 connection_timeout = the supervision
watchdog, 0x13 remote_user_terminated = the host ended the link, 0x16
local_host_terminated = this side ended it). The sketch's own BTstack HCI
event handler decodes the Disconnection Complete event and stores the
code (volatile, latest-wins, never reset — the twin of P3.24's
unknown-frame snapshot); loop()'s disconnect drain prints it. If no such
event was ever seen the line prints `reason=none` instead of a fake 0x00.
Hardware session 5's post-reflash bounce was root-caused host-side before
its reason code was ever captured; this note makes every future link loss
self-naming from the device side.

Implementation note (P3.29, 2026-11-25): the console evidence gained a
per-event trace and the sensor's own health bits. The `SKYTRACE` lines
(one compact line per dispatched sensor event — kind, touch code /
zone / family, position values, gesture code / class / edge, wheel
degrees, plus the AirWheel validity flag + raw free-running counter and
the RAW SystemInfo byte of the frame the event came from, with its two
health bits decoded: `noise=` = bit 4 EnvironmentalNoise, `clip=` = bit 5
Clipping, neither driver surfacing these before P3.29) are
compile-time gated, OFF by default because the 200 Hz position path
would flood the serial port at full rate. Enable them for an
acceptance-run build with `SKYWRITER_EVENT_TRACE=1 ./pico-arduino/flash.sh …`
(flash.sh forwards the switch as a `-D` compiler definition via
`--build-property`; the property slot was corrected to
`compiler.cpp.extra_flags` by the P3.31 note below — `build.extra_flags`
is the board's own flag slot and must never be overridden), and
position lines are
rate-limited to one per 50 ms even when enabled (touch / gesture / wheel
events are rare and print every one). The always-on health line now also
carries `sysinfo=0xNN noise= clip=` — the latest sensor-data frame's
SystemInfo byte and its two health bits — so the sensor's own health
report is visible in every build (P4.0's hover-deafness hypothesis (g)).
The Raspberry Pi Python driver surfaces the same byte for the sensor's
native-platform cross-check (P3.30, 2026-11-25): every decoded
sensor-data frame records the raw SystemInfo byte as the
`skywriter.sysinfo` module state (the twin of the Arduino driver's
`last_sysinfo`, set on every frame before the validity branches), so a
registered handler — or the cross-check session — reads the health bits
alongside the event arguments with no new hardware access.

Implementation note (P3.31, 2026-11-26): the fourth bring-up command's
label is corrected and its payload is now experiment-selectable. The
datasheet's bit semantics for dspCalOpMode (Interface.pdf §4.4.5.3,
runtime parameter ID 0x80) are INVERTED from the comment both drivers
carried: a bit CLEARED (0) in Argument0 ENABLES its auto-calibration
feature, a bit SET (1) DISABLES it, and Argument1 is the mask of the
Argument0 bits to apply — so the legacy payload (Argument0 = 0x00, mask
0x1F) actually ENABLES all five masked features (start-up,
gesture-triggered, negative, idle and invalidity-value calibration; the
AFA bit 5 sits outside the mask and keeps the chip default), and
auto-calibration has been fully ON in every build so far. The comment
correction is comments-only (both drivers keep sending the legacy bytes
by default); the genuine disable is a compile-time EXPERIMENT variant of
the firmware, OFF by default: `SKYWRITER_CAL_DISABLE=1` sends
Argument0 = 0x1F / mask = 0x1F (all five masked features off — the
vendor's own Appendix A "Disable" example also clears bit 5/AFA as
0x3F/0x3F; the experiment deliberately changes only the five bits the
legacy command already masked) and `SKYWRITER_CAL_DISABLE_IDLE=1` sends
Argument0 bit 3 / mask bit 3 (idle calibration only, the fallback if the
full disable misbehaves). flash.sh forwards either knob and they combine
with the acceptance trace switch
(`SKYWRITER_EVENT_TRACE=1 SKYWRITER_CAL_DISABLE=1 ./pico-arduino/flash.sh …`)
— all requested `-D` definitions fold into ONE space-separated
`compiler.cpp.extra_flags` value, because repeated same-key
`--build-property` values are last-one-wins in arduino-cli, and because
`build.extra_flags` is the BOARD'S OWN flag slot (boards.txt gives the
Pico W `-DPICO_CYW43_SUPPORTED=1` through it): overriding that slot —
the mechanism P3.29 originally used — compiles the core WITHOUT the
WiFi/Bluetooth driver while arduino-cli caches the broken core archive
per FQBN, after which every build of that FQBN fails with
`undefined reference to init_cyw43_wifi` until the core cache entry is
deleted (verified 2026-11-26 in a fresh container; the host had survived
it latently because its core cache had been built by a property-free
build first). The serial console names the active variant as
`cal=` on both the `SKYSTATE sensor_ok` boot line and the repeating
health line (`legacy_all_enabled` / `disable_all` / `disable_idle`), so
a capture can never mistake the experiment build for the default —
hardware session 6 (findings F19/F23) found the sensor's Clipping health
bit set from the FIRST data frame of every fresh boot while supply,
mounting and baseline drift are eliminated, which leaves the
auto-calibration suite (idle calibration continuously re-adjusting the
electrode baselines) as the one untested vendor mechanism that can rail
the receiver. Hardware judgement for the experiment (next reflash,
forget + re-pair on the host first): PASS = the health line's `clip=`
clears and hover produces position frames; FAIL = `clip=1` still set,
which leaves the damaged-board hypothesis (the blocked Raspberry Pi
cross-check, F24).

Implementation note (P3.32, 2026-11-28): hardware round 7 (findings
F25–F28) ran the first two rungs on the bench and BOTH FAILED their
criteria — with `cal=disable_all` confirmed running, the fresh boot's
FIRST data frame still reported `sysinfo=0xA0 clip=1`, and the slow
palm descent's 41 frames (touch/gesture only, position still zero)
carried `clip=1` too; `cal=disable_idle` showed the same first-frame
verdict (its own hover produced zero frames — one trial, but the boot
frame decides the FAIL either way). Auto-calibration — any single
masked feature or the whole suite — is ELIMINATED as the cause of the
boot-time receiver saturation: the Clipping bit is present before any
calibration feature could run. The ladder therefore gained its third
rung as part of the experiment set: `SKYWRITER_CAL_DISABLE_AFA=1`
sends the vendor's own canonical disable (Argument0 = 0x3F, mask =
0x3F — six bits: the five masked features plus bit 5, calibration
triggered by AFA, the adaptive filter; the vendor's Appendix A
"Disable" fixed command), named `cal=disable_afa` on the serial lines
and ignored when a lower-rung knob is set. PASS/FAIL unchanged (PASS =
a live frame shows `clip=0` and position events appear, monitor
attached BEFORE the palm descent so the per-frame evidence is
captured); if this rung also fails, the code-side ladder is EXHAUSTED
and the remaining hypotheses are the damaged board and the blocked
Raspberry Pi cross-check (F24).

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
