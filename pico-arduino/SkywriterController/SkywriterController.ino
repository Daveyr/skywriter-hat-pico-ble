/*
  SkywriterController.ino — Pico W firmware: the Skywriter 3D gesture sensor
  becomes a wireless controller for any computer, phone or tablet.

  What this firmware does, in plain language:

  * The Skywriter board (an MGC3130 gesture sensor) is read over I2C
    (Inter-Integrated Circuit — the two-wire bus between the Pico W and the
    sensor) using the shared `Skywriter` driver library (arduino/Skywriter).
  * Each sensor event (hand position, touch/tap, gestures, rotation) is
    translated by the `SkywriterHIDMapper` library (pico-arduino/SkywriterHID)
    into standard computer-interface actions: moving the pointer, mouse
    buttons, scroll wheel, keyboard keys (Page Up / Down) and media keys.
  * Those actions are reported over Bluetooth Low Energy (BLE — the
    low-power radio standard) as a Human Interface Device (HID — the standard
    protocol behind mice, keyboards and gamepads). The host device needs no
    custom driver or software: it pairs with the Pico W exactly as it pairs
    with a mouse.
  * On the console: mount the Pico W via its USB serial port and you can
    watch `SKYSTATE` lines describing bring-up progress (the hardware probe
    P4.1 asserts on these lines).

  Radio profile: specs/ble_hid.md §3–§4. This sketch implements:
  - AC-BLE-01 — the device advertises as `Skywriter HID` (the name is
    `SKYWRITER_DEVICE_NAME` below) with a HID-class appearance value.
  - AC-BLE-02 — ONE composite HID device (pointer + keyboard + media keys in
    a single HID Report Map), started with exactly ONE `startHID`.
  - AC-BLE-03 (software side) — pairing needs no sketch code: the core's
    Security Manager auto-confirms the "Just Works" pairing and the
    numeric-comparison variant, and requests bonding; the battery + device
    information services come from the same stack (see §5 note below).
  - AC-BLE-07 (software side) — the connection life cycle of §6: sensor
    events are dropped while no host is connected, every held button/scroll
    state is released on link loss (via the mapper's `disconnect()`), and
    one neutral report resyncs the host on (re)connect.
  - AC-BLE-04 (button half) — press/release transitions go out as soon as
    they happen through the pulse queue; move-report pacing is P3.18.

  Connection life cycle (specs/ble_hid.md §6, P3.17): the Bluetooth stack's
  callbacks do nothing but record the state change and restart advertising
  — see the important note at on_ble_opened() about why they must not send
  HID reports themselves. All other life-cycle work (battery refresh, the
  neutral resync report, dropping the mapping-engine's held state) happens
  in loop().

  Pairing and bonding (specs/ble_hid.md §5): pairing is entirely inside the
  Bluetooth stack (Just Works auto-confirmed, numeric comparison
  auto-confirmed, bonding requested at startHID). Bond persistence
  (AC-BLE-06): the Security Manager stores paired bonds in the
  core's FLASH-BACKED device database (`le_device_db_tlv.c`, 16 entries),
  wired up at boot by the core's own Bluetooth initialisation into a
  dedicated 8 KiB flash section (`__bluetooth_tlv`) appended after this
  firmware image — no sketch code touches it. Verified at the code level
  (P3.17b, against core 6.3.1); AC-BLE-06 remains the hardware gate
  (P4.3) that must prove a paired host reconnects without re-pairing
  across a real power cycle.

  Battery (specs/ble_hid.md §8): the Pico W is USB-powered, so the battery
  service starts at 100 % (startHID's default battery=100) and is refreshed
  to 100 % at connect time directly through `PicoBluetoothBLEHID.setBattery`
  — NOT `MouseBLE.setBattery()`, which is unusable here (`MouseBLE_`'s own
  enable flag is never set by the core, not even by its own `begin()`, so
  that wrapper silently does nothing).

  Wiring (Pico W → Skywriter board): GP4 = SDA, GP5 = SCL (the default I2C
  bus of the arduino-pico core), GP9 = TRFR/TS (data-ready / transfer line),
  GP10 = RESET. Keep the default USB CDC (Communications Device Class — the
  USB serial port) stack enabled so flash.sh's 1200-baud reset still works.
*/

#include <PicoBluetoothBLEHID.h>
#include <MouseBLE.h>
#include <KeyboardBLE.h>
#include <skywriter.h>          // the shared sensor driver: arduino/Skywriter
#include <SkywriterHIDMapper.h> // the mapping engine: pico-arduino/SkywriterHID

// ---------------------------------------------------------------------------
// Device identity (specs/ble_hid.md §4 / AC-BLE-01)
// ---------------------------------------------------------------------------

// The name both the advertisement and the Bluetooth device-name attribute
// carry. `KeyboardBLE.begin(localName, hidName)` fills both slots with it.
static const char SKYWRITER_DEVICE_NAME[] = "Skywriter HID";

// ---------------------------------------------------------------------------
// Wiring constants
// ---------------------------------------------------------------------------

static const unsigned char SKYWRITER_PIN_TS = 9;    // sensor data-ready/transfer
static const unsigned char SKYWRITER_PIN_RESET = 10; // sensor reset

// ---------------------------------------------------------------------------
// Sensor bring-up (specs/ble_hid.md §6 Boot row + the P3.8 note)
//
// The stock `Skywriter.begin()` only pulses the sensor's reset line; the
// pristine upstream library does NOT configure the sensor (AGENTS.md gotcha,
// deviation D8 keeps that claim true on purpose — sensor bring-up belongs to
// the firmware). So the firmware sends the four Set_Runtime_Parameter
// commands itself, exactly like the Python driver's `setup()`
// (library/skywriter/__init__.py):
//
//   * every command is the 0x10 control write followed by EXACTLY 15 payload
//     bytes (SW_SET_RUNTIME_PAYLOAD_SIZE) — never a 16-step copy loop over a
//     15-element array (that was the removed deviation D2),
//   * every command is acknowledged with a System_Status frame (0x15), which
//     the firmware waits for before sending the next one (the Python driver
//     raises on a missing/failed ack — the firmware denies boot afterwards).
// ---------------------------------------------------------------------------

static const unsigned char SW_CONTROL_WRITE = 0x10;
static const unsigned char SW_SET_RUNTIME_PAYLOAD_SIZE = 15;

// The four Set_Runtime_Parameter (0xA2 = 170) payload blocks, verbatim from
// the Python driver (same frame layout comment style):
//                     Size   Flags  Seq   ID?     Command        Reserved    Argument 0                Argument 1
// Command and Arguments are little-endian (LSByte first), so 1 = 0x01 0x00 ...

// 1. Enable AirWheel (the rotation counter): needs 0x20 in Argument 0 AND 1.
static const unsigned char RUNTIME_ENABLE_AIRWHEEL[SW_SET_RUNTIME_PAYLOAD_SIZE] = {
  0x00, 0x00, 0xA2,   0x90, 0x00,   0x00, 0x00,
  0x20, 0x00, 0x00, 0x00,
  0x20, 0x00, 0x00, 0x00 };

// 2. Enable all gestures and X/Y/Z position data (0 = garbage, 1-4 = flicks,
//    5-6 = circles).
static const unsigned char RUNTIME_ENABLE_GESTURES[SW_SET_RUNTIME_PAYLOAD_SIZE] = {
  0x00, 0x00, 0xA2,   0x85, 0x00,   0x00, 0x00,
  0x7F, 0x00, 0x00, 0x00,
  0x7F, 0x00, 0x00, 0x00 };

// 3. Enable all data output (bit 0 = DSP status, 1 = gesture, 2 = touch,
//    3 = AirWheel, 4 = position).
static const unsigned char RUNTIME_ENABLE_DATA_OUTPUT[SW_SET_RUNTIME_PAYLOAD_SIZE] = {
  0x00, 0x00, 0xA2,   0xA0, 0x00,   0x00, 0x00,
  0x1F, 0x00, 0x00, 0x00,
  0x1F, 0x00, 0x00, 0x00 };

// 4. Disable auto-calibration (the Python driver's default).
static const unsigned char RUNTIME_DISABLE_AUTO_CALIBRATION[SW_SET_RUNTIME_PAYLOAD_SIZE] = {
  0x00, 0x00, 0xA2,   0x80, 0x00,   0x00, 0x00,
  0x00, 0x00, 0x00, 0x00,
  0x1F, 0x00, 0x00, 0x00 };

// Wait for the sensor's System_Status acknowledge of `msg_id`, exactly like
// the Python driver's `get_status()`: up to 10 attempts, 1 ms apart, each
// pulling the TS line low, clocking a 26-byte header frame through I2C,
// releasing TS, and checking the frame identifies as System_Status (0x15,
// byte 3) acknowledging the given MsgID (byte 4 = the first payload byte).
static bool sensor_wait_system_status(unsigned char msg_id) {
  for (int attempt = 0; attempt < 10; attempt++) {
    delay(1);
    pinMode(SKYWRITER_PIN_TS, OUTPUT);
    digitalWrite(SKYWRITER_PIN_TS, LOW);

    bool ok = false;
    if (Wire.requestFrom(SW_ADDR, (unsigned char)26) >= 5) {
      Wire.read();  // byte 0: Size (already clocked past)
      Wire.read();  // byte 1: Flags
      Wire.read();  // byte 2: Sequence
      unsigned char ident = Wire.read();  // byte 3: message identity
      unsigned char field = Wire.read();  // byte 4: first payload byte
      ok = (ident == SW_SYSTEM_STATUS) && (field == msg_id);
    }
    // Drain any remaining bytes so the bus starts clean next attempt.
    while (Wire.available()) Wire.read();

    digitalWrite(SKYWRITER_PIN_TS, HIGH);
    pinMode(SKYWRITER_PIN_TS, INPUT);
    if (ok) return true;
  }
  return false;
}

// Write one Set_Runtime_Parameter command (0xa2) and wait for its ack.
static bool sensor_send_runtime_command(
    const unsigned char payload[SW_SET_RUNTIME_PAYLOAD_SIZE]) {
  Wire.beginTransmission(SW_ADDR);
  Wire.write(SW_CONTROL_WRITE);  // the Python driver's 0x10 control byte
  // EXACTLY 15 payload bytes — see the bring-up comment above (deviation D2).
  for (unsigned char i = 0; i < SW_SET_RUNTIME_PAYLOAD_SIZE; i++) {
    Wire.write(payload[i]);
  }
  if (Wire.endTransmission() != 0) return false;
  return sensor_wait_system_status(SW_SET_RUNTIME);
}

static void configure_sensor() {
  static const unsigned char* commands[] = {
    RUNTIME_ENABLE_AIRWHEEL,
    RUNTIME_ENABLE_GESTURES,
    RUNTIME_ENABLE_DATA_OUTPUT,
    RUNTIME_DISABLE_AUTO_CALIBRATION,
  };

  for (unsigned int i = 0; i < sizeof(commands) / sizeof(commands[0]); i++) {
    if (!sensor_send_runtime_command(commands[i])) {
      // The Python driver raises here; a headless controller denies boot
      // instead, loudly, so the serial probe (P4.1) sees exactly why.
      Serial.print("SKYSTATE sensor_config_failed cmd_index=");
      Serial.println(i);
      for (;;) { delay(1000); }
    }
  }
  Serial.println("SKYSTATE sensor_ok");
}

// ---------------------------------------------------------------------------
// The HID actions → BLE HID bridge
//
// The mapping engine (`SkywriterHIDMapper`) calls the sink's methods; the
// sink forwards them to the Bluetooth HID stack (`MouseBLE`, `KeyboardBLE`)
// following the spike findings in specs/ble_hid.md §3:
//   * BOTH libraries must be linked (their `__BLEInstallMouse` /
//     `__BLEInstallKeyboard` hooks merge their descriptors into ONE Report
//     Map inside `__SetupHIDreportmap`).
//   * Calling BOTH `begin()` methods would start the HID transport TWICE
//     (`startHID` runs inside either `begin()`), so setup() runs exactly one
//     of them — AC-BLE-02.
// ---------------------------------------------------------------------------

// One-shot HID pulses: taps, doubletaps, keyboard keys and media keys are
// press → wait → release sequences that must never be coalesced away
// (specs/ble_hid.md §7, AC-BLE-04). The loop() drains them, so no click ever
// blocks the sensor loop.
//
// NOTE: every sketch-level function's signature stays in primitive types
// (uint8_t, not the enum below, no PendingPulse&) — the Arduino builder
// hoists function prototypes above the type definitions in the resulting
// sketch, so a user-typed parameter would fail to compile.
enum PulseKind : uint8_t {
  PULSE_BUTTON = 0,  // press/release of p.button (MOUSE_* bits)
  PULSE_KEY,         // press/release of p.usage (keyboard usage code)
  PULSE_CONSUMER,    // press/release of p.usage (consumer-control usage code)
};

struct PendingPulse {
  uint8_t kind;    // PULSE_* above
  bool down;
  unsigned long due_ms;
  uint8_t button;  // MOUSE_LEFT / MOUSE_MIDDLE / MOUSE_RIGHT bits
  uint16_t usage;  // keyboard (uint8) or consumer (uint16) usage code
};

static const unsigned int PULSE_QUEUE_SIZE = 16;
static PendingPulse pulse_queue[PULSE_QUEUE_SIZE];
static unsigned int pulse_count = 0;

static void pulse_enqueue(uint8_t kind, bool down, unsigned long due_ms,
                          uint8_t button, uint16_t usage) {
  if (pulse_count == PULSE_QUEUE_SIZE) {
    // Defensive: cannot happen with the mapping profile's realistic event
    // rates (a full 2×-click doubletap uses 4 slots). Surface it loudly on
    // the serial console instead of dropping a HID transition silently.
    Serial.println("SKYSTATE error pulse_queue_full transition_dropped");
    return;
  }
  PendingPulse& p = pulse_queue[pulse_count++];
  p.kind = kind;
  p.down = down;
  p.due_ms = due_ms;
  p.button = button;
  p.usage = usage;
}

static void pulse_fire(uint8_t kind, bool down, uint8_t button,
                       uint16_t usage) {
  switch (kind) {
    case PULSE_BUTTON:
      if (down) MouseBLE.press(button);
      else MouseBLE.release(button);
      break;
    case PULSE_KEY:
      if (down) KeyboardBLE.press((uint8_t)usage);
      else KeyboardBLE.release((uint8_t)usage);
      break;
    case PULSE_CONSUMER:
      if (down) KeyboardBLE.consumerPress(usage);
      else KeyboardBLE.consumerRelease();
      break;
  }
}

static void pulses_tick(unsigned long now_ms) {
  while (pulse_count > 0) {
    PendingPulse& head = pulse_queue[0];
    if ((long)(head.due_ms - now_ms) > 0) break;  // earliest pulse not due yet
    pulse_fire(head.kind, head.down, head.button, head.usage);
    for (unsigned int i = 1; i < pulse_count; i++) {
      pulse_queue[i - 1] = pulse_queue[i];
    }
    pulse_count--;
  }
}

// §6 "Unconnected": not only are sensor events dropped, their scheduled
// HID transitions must not survive the link either — a tap whose 50 ms
// release pulse fell into a link loss must not be delivered to the NEXT
// connection. The disconnect drain in loop() clears the queue; queued
// entries never fired carry no radio-reachable state.
static void pulses_clear() {
  pulse_count = 0;
}

class BLEHIDSink : public HIDMapperSink {
 public:
  // §3: relative pointer movement. The BLE HID mouse report carries one
  // signed byte (−127..127) per axis. The mapper already gates movement to
  // one report per REPORT_INTERVAL_MS, but a coalesced total may exceed the
  // one-byte range in a burst, so the sink clamps what the radio takes per
  // report and RETAINS the remainder for the next report — movement is never
  // dropped (specs/hid_mapping.md §3 rule: deltas never dropped).
  void mouseMove(int16_t dx, int16_t dy) override {
    carry_x_ += dx;
    carry_y_ += dy;
    MouseBLE.move(drain_carry(carry_x_), drain_carry(carry_y_), 0);
  }

  // §4: hold-state button transitions (touch(center) hold = left button).
  // The mouse's own button bits persist, so every later pointer report
  // carries the held state — the host state machine stays in step (§3).
  void mouseButton(uint8_t button, bool down) override {
    if (down) MouseBLE.press(hid_button_bits(button));
    else MouseBLE.release(hid_button_bits(button));
  }

  // §5: wheel notches, emitted immediately by the mapper (scroll is
  // latency-sensitive — deliberately never coalesced, unlike §3 moves).
  void mouseWheel(int8_t notches) override {
    MouseBLE.move(0, 0, notches);
  }

  // §4: a completed tap/double-tap click: TAP_CLICK_MS pressed, TAP_CLICK_MS
  // gap, next press — scheduled as pulses above, never blocking the sensor
  // loop, never leaving a button held (§4: "never straddle a coalesced
  // period" — the two phases are separate reports).
  void mouseClick(uint8_t button, uint8_t count) override {
    unsigned long now = millis();
    uint8_t bits = hid_button_bits(button);
    for (uint8_t c = 0; c < count; c++) {
      unsigned long start =
          now + (unsigned long)c * 2 * SkywriterHIDMapper::TAP_CLICK_MS;
      pulse_enqueue(PULSE_BUTTON, true, start, bits, 0);
      pulse_enqueue(PULSE_BUTTON, false,
                    start + SkywriterHIDMapper::TAP_CLICK_MS, bits, 0);
    }
  }

  // §6: keyboard keys (tap(north) → Page Up 78, tap(south) → Page Down 79):
  // one press + release pair per tap event, with the same click timing as
  // the pointer taps.
  void keyboardPress(uint8_t usage) override {
    pulse_enqueue(PULSE_KEY, true, millis(), 0, usage);
    pulse_enqueue(PULSE_KEY, false,
                  millis() + SkywriterHIDMapper::TAP_CLICK_MS, 0, usage);
  }

  // §6: consumer-control (media) keys — one press per gesture event
  // ("repeats per event"): volume up/down, track next/previous. Same
  // press→release pairing so the host sees a clean key click.
  void consumerPress(uint16_t usage) override {
    pulse_enqueue(PULSE_CONSUMER, true, millis(), 0, usage);
    pulse_enqueue(PULSE_CONSUMER, false,
                  millis() + SkywriterHIDMapper::TAP_CLICK_MS, 0, usage);
  }

 private:
  // The HID button bits the MouseBLE class understands (§6 row order:
  // center = left, west = middle, east = right).
  static uint8_t hid_button_bits(uint8_t button) {
    switch (button) {
      case HID_BUTTON_MIDDLE: return MOUSE_MIDDLE;
      case HID_BUTTON_RIGHT:  return MOUSE_RIGHT;
      default:                return MOUSE_LEFT;
    }
  }

  static int8_t drain_carry(int32_t& carry) {
    if (carry > 127) {
      carry -= 127;
      return 127;
    }
    if (carry < -127) {
      carry += 127;
      return -127;
    }
    int8_t out = (int8_t)carry;
    carry = 0;
    return out;
  }

  // Remainder of pointer movement clamped away from the int8 report fields,
  // waiting for the next report (comment at mouseMove).
  int32_t carry_x_ = 0;
  int32_t carry_y_ = 0;
};

static BLEHIDSink hid_sink;
static SkywriterHIDMapper mapper(hid_sink);

// ---------------------------------------------------------------------------
// Sensor callbacks → the mapping engine
// ---------------------------------------------------------------------------

// The driver's touch codes (skywriter.h SW_DOUBLETAP_*/SW_TAP_*/SW_TOUCH_*,
// values 0..14) run in families of five, ordered center, east, north, west,
// south; the engine's SensorZone numbers run south, west, north, east,
// center. Family 0 = doubletap, 1 = tap, 2 = touch-hold.
static SensorZone zone_for_touch_code(unsigned char code) {
  static const SensorZone by_offset[5] = {
    ZONE_CENTER, ZONE_EAST, ZONE_NORTH, ZONE_WEST, ZONE_SOUTH };
  return by_offset[code % 5];
}

static TouchKind kind_for_touch_code(unsigned char code) {
  if (code < 5) return TOUCH_DOUBLETAP;
  if (code < 10) return TOUCH_TAP;
  return TOUCH_HOLD;
}

// ---------------------------------------------------------------------------
// Connection life cycle state (specs/ble_hid.md §6, P3.17)
//
// The Bluetooth callbacks fire from inside the Bluetooth stack's own
// run-loop context. Calling the HID send API from that context is exactly
// the kind of call `PicoBluetoothBLEHID.send()` cannot honour there: it
// busy-waits on the stack's own send-completion round trip, which needs
// that same context to progress — a send from a callback would deadlock.
// The callbacks therefore only record the state change (and restart
// advertising, the one BTstack operation that IS safe and canonical from a
// packet handler); all HID-visible life-cycle work runs in loop().
// ---------------------------------------------------------------------------

// Set by on_ble_opened (fires when the host enables HID input reports),
// drained once in loop(): battery refresh + neutral resync report.
static volatile bool ble_connect_event = false;
// Set by on_ble_closed (fires on link loss), drained once in loop():
// release-all through mapper.disconnect(), pulse-queue clear, keyboard
// clear.
static volatile bool ble_disconnect_event = false;
// One-per-link-loss serial notice for the hardware probe (AC-BLE-07):
// "sensor events are now being dropped" — set at boot and on link loss,
// cleared at connect, printed by the first suppressed event frame.
static volatile bool ble_drop_notice_needed = true;

// §6 "Connected": the host consumes reports only while the link exists.
// The same read also backs "Unconnected: sensor events are dropped, not
// queued" — the sensor callbacks below early-return on it.
static bool ble_link_open() {
  return PicoBluetoothBLEHID.connected();
}

// Printed once per unconnected period by the first suppressed sensor
// frame — the hardware probe's evidence line that events are genuinely
// dropped (AC-BLE-07), not accumulated and replayed.
static void sensor_drop_notice() {
  if (ble_drop_notice_needed) {
    ble_drop_notice_needed = false;
    Serial.println("SKYSTATE sensor_events_dropping_unconnected");
  }
}

static void on_sensor_xyz(unsigned int x, unsigned int y, unsigned int z) {
  if (!ble_link_open()) {
    sensor_drop_notice();
    return;  // §6 Unconnected: dropped, not queued
  }
  mapper.onPosition((uint16_t)x, (uint16_t)y, (uint16_t)z, millis());
}

static void on_sensor_touch(unsigned char code) {
  if (!ble_link_open()) {
    sensor_drop_notice();
    return;
  }
  mapper.onTouch(zone_for_touch_code(code), kind_for_touch_code(code),
                 millis());
}

static void on_sensor_gesture(unsigned char gesture) {
  if (!ble_link_open()) {
    sensor_drop_notice();
    return;
  }
  mapper.onGesture(gesture, millis());
}

static void on_sensor_airwheel(float degrees) {
  if (!ble_link_open()) {
    sensor_drop_notice();
    return;
  }
  mapper.onAirwheel(degrees, millis());
}

// System_Status acknowledges that arrive during normal operation (after
// bring-up) are surfaced on the serial console — useful evidence lines for
// the hardware probe (spec ble_hid.md §6).
static void on_sensor_status(unsigned char msg_id, unsigned int error) {
  Serial.print("SKYWRITER-HID sensor_status msg_id=0x");
  Serial.print(msg_id, HEX);
  Serial.print(" error=0x");
  Serial.println(error, HEX);
}

static void on_sensor_firmware_version(unsigned char fw_valid,
                                       const char* version) {
  Serial.print("SKYWRITER-HID sensor_firmware valid=0x");
  Serial.print(fw_valid, HEX);
  Serial.print(" version=");
  Serial.println(version);
}

// BLE link state (specs/ble_hid.md §6 — the hardware probe asserts on
// these lines). Callback-context rules: see the life-cycle block above —
// these handlers only set flags (and restart advertising, safe from a
// packet handler); the drains in loop() do all the HID-visible work.
static void on_ble_opened(uint8_t type, uint16_t channel, uint8_t* packet,
                          uint16_t size) {
  (void)type; (void)channel; (void)packet; (void)size;
  ble_connect_event = true;
}

static void on_ble_closed(uint8_t type, uint16_t channel, uint8_t* packet,
                          uint16_t size) {
  (void)type; (void)channel; (void)packet; (void)size;
  // AC-BLE-05: return to advertising within 5 s of a link loss — restart
  // it HERE, inside the stack's own context (the canonical BTstack place;
  // the addressable data and parameters were set at startHID). No send() /
  // report call allowed in this context — the flag below schedules the
  // state teardown in loop().
  gap_advertisements_enable(1);
  ble_drop_notice_needed = true;
  ble_disconnect_event = true;
}

// ---------------------------------------------------------------------------
// Bring-up and the main loop
// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  Serial.println("SKYWRITER-HID boot");

  // 1. Sensor stack first (specs/ble_hid.md §6 Boot row). `Skywriter.begin`
  //    only resets the sensor; the runtime configuration is ours.
  Skywriter.begin(SKYWRITER_PIN_TS, SKYWRITER_PIN_RESET);
  configure_sensor();

  // 2. Route every decoded sensor event into the mapping engine.
  Skywriter.onXYZ(on_sensor_xyz);
  Skywriter.onTouch(on_sensor_touch);
  Skywriter.onGesture(on_sensor_gesture);
  Skywriter.onAirwheel(on_sensor_airwheel);
  Skywriter.onSystemStatus(on_sensor_status);
  Skywriter.onFirmwareVersion(on_sensor_firmware_version);

  // 3. Now the radio. The link callbacks are registered BEFORE begin() —
  //    afterwards `startHID` powers the radio on and a host that connects
  //    during bring-up would otherwise fire into unregistered callbacks.
  //    (Each handler only sets a flag; loop() does the HID-visible work.)
  PicoBluetoothBLEHID.setOpenedCB(on_ble_opened);
  PicoBluetoothBLEHID.setClosedCB(on_ble_closed);

  // 4. Exactly ONE begin() — KeyboardBLE's — so `startHID` runs exactly
  //    once (AC-BLE-02). Because both MouseBLE and KeyboardBLE libraries
  //    are linked in, `__SetupHIDreportmap` merges pointer, keyboard AND
  //    consumer-control descriptors into the single Report Map
  //    (AC-BLE-02), and `__BLEGetAppearance()` (used inside that begin)
  //    advertises HID-class semantics for the composite device (AC-BLE-01).
  //    The Battery Service starts at 100 % through startHID's default
  //    (specs/ble_hid.md §8) and is refreshed to 100 % at connect time in
  //    loop() (AC-BLE-03).
  KeyboardBLE.begin(SKYWRITER_DEVICE_NAME, SKYWRITER_DEVICE_NAME);
  Serial.print("SKYSTATE hid_started name=");
  Serial.print(SKYWRITER_DEVICE_NAME);
  Serial.print(" appearance=0x");
  Serial.println(__BLEGetAppearance(), HEX);

  // 5. The mouse half's `begin()` was deliberately skipped (it would have
  //    started the HID transport twice). The only other state `begin()`
  //    would have initialised is the mouse base class's public enable bit —
  //    without it every press/release is silently ignored — so set that one
  //    bit directly (static up-cast: the bit lives on HID_Mouse).
  HID_Mouse& mouse_base = MouseBLE;
  mouse_base._running = true;
}

void loop() {
  unsigned long now = millis();

  // ---- life-cycle drains (specs/ble_hid.md §6) must run BEFORE the new
  // sensor events of this iteration reach the engine, so the mapper is
  // always in a clean "fresh session" state when its inputs arrive.

  if (ble_disconnect_event) {
    ble_disconnect_event = false;
    // 1. The mapping engine forgets the whole session: held buttons/scroll
    //    rows released (mapper.disconnect), unsent movement dropped, wheel
    //    accumulator cleared, next position re-baselines (§6 Unconnected,
    //    AC-BLE-07's no-stale-replay half).
    mapper.disconnect(now);
    // 2. Sketch-side state the engine does not know about: scheduled
    //    tap/media pulses die with the link (pulses_clear) and the
    //    Bluetooth wrappers' own latched state is zeroed so the neutral
    //    resync report below really is neutral — MOUSE_ALL releases every
    //    mouse button bit, KeyboardBLE.releaseAll() clears the latched
    //    keyboard report (both no-op when nothing was held).
    pulses_clear();
    MouseBLE.release(MOUSE_ALL);
    KeyboardBLE.releaseAll();
    Serial.println("SKYSTATE ble_dropped");
    Serial.println("SKYSTATE ble_advertising");
  }

  if (ble_connect_event) {
    ble_connect_event = false;
    ble_drop_notice_needed = false;
    // §8: battery reported 100 % at connect — through PicoBluetoothBLEHID
    // directly (see the battery note in the file header; MouseBLE's
    // battery wrapper is unusable).
    PicoBluetoothBLEHID.setBattery(100);
    // §6/AC-BLE-07: the neutral resync report, once per (re)connect — no
    // buttons (the wrapper's latched state was cleared above), zero
    // deltas, zero wheel. `MouseBLE.move(0, 0, 0)` always emits (its
    // zero-suppression lives in the mapper, not here), so hosts see a
    // whole-state report that wipes any button state they kept from the
    // previous link. A consumer (media) key whose 50 ms release pulse fell
    // into the link loss is wiped host-side by the zero consumer report.
    KeyboardBLE.consumerRelease();
    MouseBLE.move(0, 0, 0);
    Serial.println("SKYSTATE ble_resync battery=100 neutral_report");
    Serial.println("SKYSTATE ble_connected");
  }

  // Every polled sensor frame dispatches into the mapping engine... (the
  // callbacks drop events while no host is connected, §6 Unconnected).
  Skywriter.poll();
  // ...and the engine's timing work (lift-off gating, release-by-silence,
  // coalesced report cadence, hold auto-scroll) runs every loop iteration,
  // driven by the millis() clock.
  mapper.tick(now);
  pulses_tick(now);
}
