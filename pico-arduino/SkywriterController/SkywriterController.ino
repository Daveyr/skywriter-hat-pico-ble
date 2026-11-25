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
    P4.1 asserts on these lines). Since fix item P3.22 a `SKYSTATE health`
    status line prints every 2 s with the driver's I2C read counters (short
    reads and transfer-line-low polls as shares of all polls), frames by
    message type, dispatched/dropped sensor events, HID reports by kind and
    Bluetooth connects/disconnects — the hardware gate P4.0a's main
    instrument. Since fix item P3.24 the health line also prints the
    latest undispatched frame's first 8 bytes and actual read count
    (`other_snap=` / `other_read=`) — the evidence that names what the
    "other" frames contain. And since fix item P3.25 the driver reads
    exactly the classic 26-byte sensor frame first and only fetches more
    when the frame's own Size field says the message is longer (never the
    old single 132-byte over-read that desynchronised the sensor's
    message framing). Since fix item P3.26 a failed sensor configuration
    can never deny boot: the radio always starts, the configuration
    retries from loop() forever with one evidence line per failed
    attempt, and the health line carries the outcome (`sensor_cfg=`,
    `cfg_attempts=`) — a sensor hiccup at boot used to leave the device
    invisible to every host (hardware session 5's cold-boot captures).
    And since fix item P3.27 the Bluetooth connect drain (battery refresh
    + neutral resync report) runs once per LINK: the stack reports one
    connection as several "opened" events (one per report-channel
    subscription write), a per-link latch keeps the drain to a single run,
    and the health line's `ble conn=` counts links, not subscription
    writes. And since fix item P3.28 the `SKYSTATE ble_dropped` line names
    WHY the Bluetooth link ended — the radio's own disconnection reason
    code (e.g. 0x06 = a stale pairing after a reflash, 0x08 = the
    connection watchdog gave up, 0x13 = the host ended the link) — the
    evidence session 5's bounce investigation had to fix host-side without.
    And since fix item P3.29 the health line also carries the sensor's own
    health report (`sysinfo=0xNN noise= clip=` — the SystemInfo byte of
    the latest sensor frame, whose bit 4 EnvironmentalNoise and bit 5
    Clipping may name the hover-deafness cause directly), and an optional
    compile-time-gated per-event evidence trace (`SKYTRACE` lines: one
    compact line per dispatched sensor event with its kind, touch
    code/zone/family, position values, gesture code/class/edge, wheel
    degrees, the AirWheel validity flag + raw counter and the raw
    SystemInfo byte) — off by default so the 200 Hz position path stays
    quiet; enable it for acceptance-run builds with
    SKYWRITER_EVENT_TRACE=1 ./pico-arduino/flash.sh pico-arduino/SkywriterController.

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
  - AC-BLE-04 — the performance rules of §7 (P3.18): press/release
    transitions go out as soon as they happen through the pulse queue
    (never coalesced away), and move reports are paced at the LIVE BLE
    connection interval: the HCI connection watcher below reads the
    interval the host actually negotiated, asks the host to keep it inside
    the 7.5–15 ms window the ≥ 60 Hz pointer-rate floor needs, and
    reprograms the mapping engine's report cadence (move reports only;
    wheel/keyboard/media events are emitted immediately —
    latency-sensitive).

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
//     raises on a missing/failed ack).
//
// P3.26 — a failed acknowledgment is EVIDENCE and a RETRY, never a boot
// denial. The original design denied boot here (a forever
// `sensor_config_failed` loop before the radio started), and hardware
// session 5's cold-boot captures (F12) showed what that does: the sensor
// missed one acknowledgment, and the whole device stayed invisible —
// no radio, no advertisement, nothing for a host to see. Since the supply
// fix (F16) the acknowledgments are reliable, but the design lesson stands:
// a sensor hiccup must never silence the device. The rules now are:
//   * setup() runs ONE whole-sequence attempt (bounded — the healthy path
//     keeps the familiar boot order, `sensor_ok` before `hid_started`);
//   * loop()'s retry tick reruns the WHOLE sequence forever until it
//     completes, each failed attempt printing its own evidence line
//     (attempt number, failing command, elapsed time);
//   * the radio starts regardless of the sensor's state, and the health
//     line carries the configuration outcome (`sensor_cfg=`, `cfg_attempts=`).
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

    // Release the transfer line with its pull-up restored (fix item
    // P3.23, hypothesis H2 — same rule as the driver's poll() release):
    // a loose or disconnected TS wire must read consistently high.
    digitalWrite(SKYWRITER_PIN_TS, HIGH);
    pinMode(SKYWRITER_PIN_TS, INPUT_PULLUP);
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

// One whole four-command configuration pass. Returns -1 when every command
// was acknowledged, or the 0-based index of the command whose acknowledgment
// never arrived (the F12 evidence named cmd_index=0 and cmd_index=1).
static int configure_sensor_attempt() {
  static const unsigned char* commands[] = {
    RUNTIME_ENABLE_AIRWHEEL,
    RUNTIME_ENABLE_GESTURES,
    RUNTIME_ENABLE_DATA_OUTPUT,
    RUNTIME_DISABLE_AUTO_CALIBRATION,
  };

  for (unsigned int i = 0; i < sizeof(commands) / sizeof(commands[0]); i++) {
    if (!sensor_send_runtime_command(commands[i])) {
      return (int)i;
    }
  }
  return -1;
}

// --- P3.26 configuration life cycle: attempt once at boot, retry forever ---
//
// While the configuration is incomplete the device is UP (radio advertising,
// pairing, life cycle) but DEAF (no sensor events yet) — the health line
// shows both halves of that state.

static bool sensor_configured = false;
static unsigned long sensor_config_attempts = 0;   // whole-sequence attempts
static unsigned long sensor_config_attempt_start_ms = 0;
static unsigned long sensor_config_next_attempt_ms = 0;

// Breathing room between whole-sequence retries: each failed attempt already
// spent up to ~10 × 4 ack windows on the bus; a short pause keeps the retry
// cadence readable in a capture and gives a recovering sensor time to settle.
static const unsigned long SENSOR_CONFIG_RETRY_INTERVAL_MS = 200;

// The success line keeps the serial probe's `SKYSTATE sensor_ok` token and
// names how many whole-sequence attempts it took and how long the successful
// attempt ran — the "how long did the sensor take" instrument F12 asked for.
static void sensor_config_report_success() {
  sensor_configured = true;
  Serial.print("SKYSTATE sensor_ok attempts=");
  Serial.print(sensor_config_attempts);
  Serial.print(" took_ms=");
  Serial.println(millis() - sensor_config_attempt_start_ms);
}

static void sensor_config_report_failure(unsigned long attempt,
                                         int failed_index) {
  Serial.print("SKYSTATE sensor_config_retry attempt=");
  Serial.print(attempt);
  Serial.print(" cmd_index=");
  Serial.print(failed_index);
  Serial.print(" elapsed_ms=");
  Serial.println(millis() - sensor_config_attempt_start_ms);
}

// setup(): one bounded whole-sequence attempt. The healthy path (the only
// path since the supply fix) finishes here, keeping the familiar boot order;
// a failure is recorded and the boot CONTINUES — the radio starts below.
static void sensor_config_first_attempt() {
  sensor_config_attempts = 1;
  sensor_config_attempt_start_ms = millis();
  int failed = configure_sensor_attempt();
  if (failed < 0) {
    sensor_config_report_success();
    return;
  }
  sensor_config_report_failure(sensor_config_attempts, failed);
  sensor_config_next_attempt_ms =
      millis() + SENSOR_CONFIG_RETRY_INTERVAL_MS;
}

// loop(): rerun the WHOLE four-command sequence (never resume from the failed
// command — F12's captures failed on cmd_index=0 AND cmd_index=1, so a
// part-way stop would leave the sensor half-configured) until it completes.
static void sensor_config_retry_tick(unsigned long now_ms) {
  if (sensor_configured) return;
  if ((long)(now_ms - sensor_config_next_attempt_ms) < 0) return;

  sensor_config_attempts++;
  sensor_config_attempt_start_ms = now_ms;
  int failed = configure_sensor_attempt();
  if (failed < 0) {
    sensor_config_report_success();
    return;
  }
  sensor_config_report_failure(sensor_config_attempts, failed);
  sensor_config_next_attempt_ms = now_ms + SENSOR_CONFIG_RETRY_INTERVAL_MS;
}

// ---------------------------------------------------------------------------
// Health counters (fix item P3.22; the instrument the hardware gate P4.0a
// needs — with no oscilloscope or logic analyser, these counters are the
// only view of the transfer line and the failed reads over time)
//
// The sensor-side read counters (polls, transfer-line-low polls, short
// reads, frames by message type) live in the shared driver library as
// public state (`Skywriter.polls` etc. — see arduino/Skywriter/skywriter.h),
// so the examples keep compiling. The sketch owns the event/report/link
// counters below. The 200 Hz sensor path only increments counters; it
// never prints — the status line prints once every HEALTH_INTERVAL_MS
// from loop().
// ---------------------------------------------------------------------------

static const unsigned long HEALTH_INTERVAL_MS = 2000;
static unsigned long health_last_ms = 0;

// Sensor events, as dispatched into the mapping engine (after the
// unconnected drop gate) and as dropped while unconnected.
static unsigned long ev_position = 0;
static unsigned long ev_touch = 0;
static unsigned long ev_gesture = 0;
static unsigned long ev_airwheel = 0;
static unsigned long ev_dropped = 0;

// HID reports sent, by kind — counted at the radio call sites (the real
// sends: MouseBLE / KeyboardBLE), not at the mapper's abstract calls.
// pointer = mouse move reports; button = press/release transitions (taps'
// scheduled pulses included, so a click counts 2); wheel = scroll notches;
// key = keyboard press/release transitions; media = consumer-control
// press/release transitions.
static unsigned long hid_pointer = 0;
static unsigned long hid_button = 0;
static unsigned long hid_wheel = 0;
static unsigned long hid_key = 0;
static unsigned long hid_media = 0;

// Bluetooth link life cycle counters.
static unsigned long ble_connects = 0;
static unsigned long ble_disconnects = 0;

static void print_health_status(unsigned long now_ms) {
  Serial.print("SKYSTATE health uptime_ms=");
  Serial.print(now_ms);
  // P3.26: the sensor configuration's outcome — the device reports a deaf
  // sensor and a working radio on the same line instead of denying boot.
  Serial.print(" sensor_cfg=");
  Serial.print(sensor_configured ? 1 : 0);
  Serial.print(" cfg_attempts=");
  Serial.print(sensor_config_attempts);
  // Shares are printed so they are visible without arithmetic (P4.0a T5).
  // A division by zero is impossible once polls > 0; a 0 poll count (never
  // reached in a live loop) prints 0.00%.
  float poll_div = (Skywriter.polls > 0) ? (float)Skywriter.polls : 1.0f;
  Serial.print(" polls=");
  Serial.print(Skywriter.polls);
  Serial.print(" ts_low=");
  Serial.print(Skywriter.ts_low_polls);
  Serial.print('(');
  Serial.print(100.0f * (float)Skywriter.ts_low_polls / poll_div, 2);
  Serial.print("%) short_reads=");
  Serial.print(Skywriter.short_reads);
  Serial.print('(');
  Serial.print(100.0f * (float)Skywriter.short_reads / poll_div, 2);
  Serial.print("%) frames sensor=");
  Serial.print(Skywriter.frames_sensor_data);
  Serial.print(" status=");
  Serial.print(Skywriter.frames_status);
  Serial.print(" fw=");
  Serial.print(Skywriter.frames_firmware);
  Serial.print(" other=");
  Serial.print(Skywriter.frames_other);
  // P3.24: the latest undispatched frame's content — the evidence that
  // names WHAT the "other" frames are. A 0x91 identity visible at a
  // shifted offset = the sensor's message framing is misaligned (the
  // over-read fault, P4.0a H7); all 0x00 = the bus answers padding on
  // reads with nothing queued (then hunt a transfer-line short);
  // all 0xFF = a wedged slave (power-cycle the sensor); a known identity
  // with the read count under the promised Size = an incomplete read.
  // Zeros with other=0 mean no such frame has been seen since boot.
  Serial.print(" other_snap=");
  for (unsigned char i = 0; i < 8; i++) {
    if (i) Serial.print(':');
    if (Skywriter.other_snapshot[i] < 0x10) Serial.print('0');
    Serial.print(Skywriter.other_snapshot[i], HEX);
  }
  Serial.print(" other_read=");
  Serial.print(Skywriter.other_snapshot_read);
  // P3.29: the sensor's own health report — the RAW SystemInfo byte of
  // the last decoded sensor-data frame plus its two health bits decoded.
  // Always on (unlike the gated SKYTRACE lines): a once-per-2 s print
  // cannot flood anything, and these bits may name the hover-deafness
  // cause directly (P4.0 hypothesis (g)) — noise=1 (bit 4,
  // EnvironmentalNoise) means the sensor detected environmental noise;
  // clip=1 (bit 5, Clipping) means its ADCs are clipping. 0x00 with
  // frames sensor=0 means no sensor frame has been decoded yet.
  Serial.print(" sysinfo=0x");
  if (Skywriter.last_sysinfo < 0x10) Serial.print('0');
  Serial.print(Skywriter.last_sysinfo, HEX);
  Serial.print(" noise=");
  Serial.print((Skywriter.last_sysinfo & 0x10) ? 1 : 0);
  Serial.print(" clip=");
  Serial.print((Skywriter.last_sysinfo & 0x20) ? 1 : 0);
  Serial.print(" events pos=");
  Serial.print(ev_position);
  Serial.print(" touch=");
  Serial.print(ev_touch);
  Serial.print(" gest=");
  Serial.print(ev_gesture);
  Serial.print(" wheel=");
  Serial.print(ev_airwheel);
  Serial.print(" dropped=");
  Serial.print(ev_dropped);
  Serial.print(" hid pointer=");
  Serial.print(hid_pointer);
  Serial.print(" button=");
  Serial.print(hid_button);
  Serial.print(" wheel=");
  Serial.print(hid_wheel);
  Serial.print(" key=");
  Serial.print(hid_key);
  Serial.print(" media=");
  Serial.print(hid_media);
  Serial.print(" ble conn=");
  Serial.print(ble_connects);
  Serial.print(" disc=");
  Serial.println(ble_disconnects);
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

// One keyboard usage code must be sent to the Bluetooth keyboard library in
// the core's NON-PRINTING range: `KeyboardBLE.press(uint8_t)` treats values
// 0-127 as ASCII characters (raw Page Up usage 78 typed the letter "N" —
// hardware session 1, fix item P3.21) and values 136 and up as non-printing
// keys, subtracting 136 to get the usage. The core's own key table confirms
// the offset: KEY_PAGE_UP = 0xD3 = 136 + 75, KEY_PAGE_DOWN = 0xD6 = 136 + 78.
// Every keyboard press AND release goes through this conversion — never send
// a raw §6 usage to press()/release().
static const uint8_t KEYBOARD_NON_PRINTING_OFFSET = 136;

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
      hid_button++;
      if (down) MouseBLE.press(button);
      else MouseBLE.release(button);
      break;
    case PULSE_KEY:
      // The mapper hands over the RAW USB usage (75 = Page Up, 78 = Page
      // Down, P3.21); the non-printing-range conversion happens HERE, once,
      // for both press and release — a raw usage would be typed as a letter.
      hid_key++;
      if (down) KeyboardBLE.press((uint8_t)(usage + KEYBOARD_NON_PRINTING_OFFSET));
      else KeyboardBLE.release((uint8_t)(usage + KEYBOARD_NON_PRINTING_OFFSET));
      break;
    case PULSE_CONSUMER:
      hid_media++;
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
    hid_pointer++;
    MouseBLE.move(drain_carry(carry_x_), drain_carry(carry_y_), 0);
  }

  // §4: hold-state button transitions (touch(center) hold = left button).
  // The mouse's own button bits persist, so every later pointer report
  // carries the held state — the host state machine stays in step (§3).
  void mouseButton(uint8_t button, bool down) override {
    hid_button++;
    if (down) MouseBLE.press(hid_button_bits(button));
    else MouseBLE.release(hid_button_bits(button));
  }

  // §5: wheel notches, emitted immediately by the mapper (scroll is
  // latency-sensitive — deliberately never coalesced, unlike §3 moves).
  void mouseWheel(int8_t notches) override {
    hid_wheel++;
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

  // §6: keyboard keys (tap(north) → Page Up 75, tap(south) → Page Down 78 —
  // corrected from 78/79 by P3.21): one press + release pair per tap event,
  // with the same click timing as the pointer taps. The usage stays RAW
  // here; pulse_fire applies the core's non-printing range offset.
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
// P3.29: the per-event evidence trace — compile-time gated, OFF by default
//
// The health line's aggregate counters proved which CHANNELS are alive,
// but the 2026-11-25 acceptance session hit two questions they cannot
// answer: which ZONE a tap landed in (every tap produced button clicks and
// none produced the Page Up / Down keys — the counters cannot say whether
// the sensor never sent a north/south touch code or sent one that was
// mishandled), and whether a rotation attempt ever produced AirWheel-valid
// data at all (`events wheel=0` through both attempts). This trace prints
// one compact serial line per DISPATCHED sensor event:
//
//   SKYTRACE pos x=.. y=.. z=..          a valid position event
//   SKYTRACE touch code=7 zone=north family=tap ...
//   SKYTRACE gest code=4 class=1 edge=0 ...
//   SKYTRACE wheel deg=+22.50 ...        a rotation delta
//
// Every line ends with the per-frame context the counters cannot show:
//   aw_valid= / aw_cnt= — the driver's AirWheel validity flag and the raw
//     free-running rotation counter of the last AirWheel-valid frame
//     (Interface.pdf Table 4-10: 32 counts = 1 revolution, wraps 255->0);
//   sys= — the RAW SystemInfo byte (sensor-data payload byte 3) of the
//     frame the event came from, plus its two health bits DECODED:
//     noise= (bit 4, EnvironmentalNoise — the sensor detected
//     environmental noise) and clip= (bit 5, Clipping — the sensor's ADCs
//     are clipping). Neither driver surfaced these bits before P3.29;
//     they may name the hover-deafness cause directly (P4.0 hypothesis
//     (g)), and the always-on health line prints them too.
//
// OFF by default: at full rate the 200 Hz position path would flood the
// USB CDC (Communications Device Class — the USB serial port) console.
// Enable it for an acceptance-run build with
//   SKYWRITER_EVENT_TRACE=1 ./pico-arduino/flash.sh pico-arduino/SkywriterController
// (flash.sh forwards the value as a -D compiler flag), or by flipping the
// default below to 1. Even when enabled, position lines are RATE-LIMITED
// to one per TRACE_POSITION_INTERVAL_MS (a readable sample of the hover
// path); touch/gesture/wheel events are rare and print every one.
// ---------------------------------------------------------------------------

#ifndef SKYWRITER_EVENT_TRACE
#define SKYWRITER_EVENT_TRACE 0
#endif

#if SKYWRITER_EVENT_TRACE

// One position trace line per this interval (≈ 20 lines/s) — the enabled
// trace stays readable while still sampling the hover path.
static const unsigned long TRACE_POSITION_INTERVAL_MS = 50;
static unsigned long trace_last_position_ms = 0;

// Names for the trace line: the driver's touch code (0..14) maps onto the
// engine's zone and family (zone_for_touch_code / kind_for_touch_code
// above); the names are what the acceptance run greps for.
static const char* trace_zone_name(SensorZone zone) {
  switch (zone) {
    case ZONE_NORTH: return "north";
    case ZONE_SOUTH: return "south";
    case ZONE_EAST:  return "east";
    case ZONE_WEST:  return "west";
    default:         return "center";
  }
}

static const char* trace_family_name(TouchKind kind) {
  switch (kind) {
    case TOUCH_TAP:       return "tap";
    case TOUCH_DOUBLETAP: return "doubletap";
    default:              return "hold";
  }
}

// The shared per-frame context every trace line ends with: the AirWheel
// validity flag + raw counter and the RAW SystemInfo byte with its two
// health bits decoded (see the section comment above).
static void trace_context() {
  Serial.print(" aw_valid=");
  Serial.print(Skywriter.airwheel_valid ? 1 : 0);
  Serial.print(" aw_cnt=0x");
  if (Skywriter.airwheel_counter < 0x10) Serial.print('0');
  Serial.print(Skywriter.airwheel_counter, HEX);
  Serial.print(" sys=0x");
  if (Skywriter.last_sysinfo < 0x10) Serial.print('0');
  Serial.print(Skywriter.last_sysinfo, HEX);
  // The sensor's own health bits (Interface.pdf Table 4-10): bit 4 =
  // EnvironmentalNoise, bit 5 = Clipping.
  Serial.print(" noise=");
  Serial.print((Skywriter.last_sysinfo & 0x10) ? 1 : 0);
  Serial.print(" clip=");
  Serial.print((Skywriter.last_sysinfo & 0x20) ? 1 : 0);
}

static void trace_position(unsigned int x, unsigned int y, unsigned int z) {
  unsigned long now = millis();
  if ((long)(now - trace_last_position_ms) < TRACE_POSITION_INTERVAL_MS) {
    return;  // rate-limited: a readable sample, not a 200 Hz flood
  }
  trace_last_position_ms = now;
  Serial.print("SKYTRACE pos x=");
  Serial.print(x);
  Serial.print(" y=");
  Serial.print(y);
  Serial.print(" z=");
  Serial.print(z);
  trace_context();
  Serial.println();
}

static void trace_touch(unsigned char code) {
  Serial.print("SKYTRACE touch code=");
  Serial.print(code);
  Serial.print(" zone=");
  Serial.print(trace_zone_name(zone_for_touch_code(code)));
  Serial.print(" family=");
  Serial.print(trace_family_name(kind_for_touch_code(code)));
  trace_context();
  Serial.println();
}

static void trace_gesture(unsigned char code) {
  Serial.print("SKYTRACE gest code=");
  Serial.print(code);
  Serial.print(" class=");
  Serial.print(Skywriter.last_gesture_class);
  Serial.print(" edge=");
  Serial.print(Skywriter.last_gesture_edge ? 1 : 0);
  trace_context();
  Serial.println();
}

static void trace_airwheel(float degrees) {
  Serial.print("SKYTRACE wheel deg=");
  Serial.print(degrees, 2);
  trace_context();
  Serial.println();
}

#endif  // SKYWRITER_EVENT_TRACE


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

// Set by on_ble_opened (fires when the host enables HID input reports —
// once per link since P3.27's latch, see the latch comment below),
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

// P3.27: the connect drain is LATCHED PER LINK. The Bluetooth stack fires
// the opened callback once per notification-enable write — the host writes
// one enable switch per report channel (four to five per connection,
// hardware session 5's btmon capture) — not once per link. Without the
// latch, one link drained four to five times: four battery notifications,
// four neutral-report pairs, and a health line counting `ble conn=5` with
// `disc=0` for a SINGLE link. The drain is a once-per-link action
// (specs/ble_hid.md §6 "once", §8), so this latch gates the arming: set on
// the FIRST opened event of a link, cleared on the closed event, so the
// health line's `ble conn=` counts real links. It is cleared only in the
// closed callback — the closed event precedes any later link by
// definition, so a next connection can always arm its own drain.
static volatile bool ble_connect_drain_latched = false;

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
    ev_dropped++;
    sensor_drop_notice();
    return;  // §6 Unconnected: dropped, not queued
  }
  ev_position++;
  mapper.onPosition((uint16_t)x, (uint16_t)y, (uint16_t)z, millis());
#if SKYWRITER_EVENT_TRACE
  trace_position(x, y, z);
#endif
}

static void on_sensor_touch(unsigned char code) {
  if (!ble_link_open()) {
    ev_dropped++;
    sensor_drop_notice();
    return;
  }
  ev_touch++;
  mapper.onTouch(zone_for_touch_code(code), kind_for_touch_code(code),
                 millis());
#if SKYWRITER_EVENT_TRACE
  trace_touch(code);
#endif
}

static void on_sensor_gesture(unsigned char gesture) {
  if (!ble_link_open()) {
    ev_dropped++;
    sensor_drop_notice();
    return;
  }
  ev_gesture++;
  mapper.onGesture(gesture, millis());
#if SKYWRITER_EVENT_TRACE
  trace_gesture(gesture);
#endif
}

static void on_sensor_airwheel(float degrees) {
  if (!ble_link_open()) {
    ev_dropped++;
    sensor_drop_notice();
    return;
  }
  ev_airwheel++;
  mapper.onAirwheel(degrees, millis());
#if SKYWRITER_EVENT_TRACE
  trace_airwheel(degrees);
#endif
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
  // P3.27: only the link's FIRST subscription write arms the drain — the
  // remaining enable writes belong to the same link (latch comment above).
  if (ble_connect_drain_latched) return;
  ble_connect_drain_latched = true;
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
  // P3.27: the link is gone — its drain latch resets, so the NEXT link
  // arms and drains exactly once (latch comment above).
  ble_connect_drain_latched = false;
  ble_drop_notice_needed = true;
  ble_disconnect_event = true;
}

// ---------------------------------------------------------------------------
// §7 performance / AC-BLE-04 (P3.18): move reports paced at the LIVE
// connection interval
//
// Report coalescing (specs/ble_hid.md §7): move reports may be coalesced to
// the connection interval — that is exactly the mapping engine's cadence
// gate (hid_mapping.md §3 rule 6) — so the engine's pace must be the
// interval the host actually negotiated, not a fixed guess. The pointer
// rate must stay ≥ 60 reports/s (interval ≤ ~16.7 ms), and its 200 Hz
// sensor input (one frame every 5 ms) is fully accumulated in the engine
// meanwhile, so re-pacing never drops movement.
//
// How the live interval is learned: the sketch adds its own small BTstack
// HCI event handler alongside the wrapper's — BTstack supports any number of
// event handlers. The two LE (Low Energy) subevents carrying the connection
// parameters are decoded; everything else is filtered away in one branch.
//   * HCI_SUBEVENT_LE_CONNECTION_COMPLETE — a host connected; the event
//     names the connection interval it chose (unit: 1.25 ms).
//   * HCI_SUBEVENT_LE_CONNECTION_UPDATE_COMPLETE — the host changed the
//     parameters later (hosts do this during pairing/bonding).
// Handlers stay flag-only (same context rule as on_ble_opened above): the
// negotiated interval is stored and loop() reprograms the engine.
//
// P3.28: the same handler also decodes the HCI Disconnection Complete
// event — the radio-level record of a link ending, carrying the standard
// reason code for WHY it ended. The wrapper's "closed" callback fires on
// this same event (see PicoBluetoothBLEHID's packetHandler), and BTstack
// dispatches event handlers in registration order, so this handler —
// registered before the radio starts — stores the reason BEFORE
// on_ble_closed arms the disconnect drain that prints it. The reason code
// is what names a link loss from the device side: hardware session 5's
// post-reflash bounce was fixed host-side before its reason was ever
// captured (the btmon trace recorded the successful pairing instead), so
// every future loss names itself: 0x06 PIN or Key Missing = a stale
// pairing (e.g. a reflash orphaned the Pico's stored bond while the host
// kept hers), 0x08 Connection Timeout = the connection watchdog decided
// the peer was gone, 0x13 Remote User Terminated Connection = the HOST
// ended the link, 0x16 Connection Terminated By Local Host = this side
// ended it. Like P3.24's unknown-frame snapshot, the stored reason is
// latest-wins: it is never reset, so the next health line still shows
// what the last loss was.
//
// Additionally, on connection the sketch ASKS the host to keep the
// interval inside [7.5, 15] ms (units: 6..12 × 1.25 ms) — the window that
// keeps the ≥ 60 Hz pointer-rate floor of AC-BLE-04 possible even if the
// host's policy would have chosen something slower (a request the host may
// decline; the stack sends it as a standard connection-parameter update,
// no HID send involved, safe from the radio context like
// gap_advertisements_enable above).
// ---------------------------------------------------------------------------

// [7.5, 15] ms, in 1.25 ms units — AC-BLE-04's ≥ 60 Hz floor; a request
// towards the faster end also serves §7's 200 Hz target where the host
// allows it.
static const uint16_t PACE_MIN_INTERVAL_UNITS = 6;   // 7.5 ms
static const uint16_t PACE_MAX_INTERVAL_UNITS = 12;  // 15 ms
// Supervision timeout for the request (unit: 10 ms): 480 ms, comfortably
// above the LE requirement of 2 × (1 + latency) × max interval = 30 ms.
static const uint16_t PACE_SUPERVISION_TIMEOUT_UNITS = 48;

// The registration struct must live forever (BTstack links handlers into
// its own list) — static at sketch scope.
static btstack_packet_callback_registration_t hci_event_registration;

// Set from the stack context when a negotiated interval is pending; the
// interval itself is a uint16 read that stays whole across the contexts
// (single byte-multiples — no torn-read hazard).
static volatile bool ble_pace_dirty = false;
static volatile uint16_t ble_pace_units = 0;

// P3.28: the reason the last Bluetooth link ended, as the radio itself
// reported it. Both are written only from the stack's callback context
// (hence volatile), latest-wins, and printed by loop()'s disconnect drain
// on the `SKYSTATE ble_dropped` line — the device-side answer to "why did
// the link drop?" that session 5's report could not give.
static volatile bool ble_drop_reason_seen = false;
static volatile uint8_t ble_drop_reason = 0;

// Human-readable name for an HCI error code. The codes that matter for
// this project's diagnosis are named; anything else answers "unknown" —
// never an empty or misleading name.
static const char* ble_drop_reason_name(uint8_t reason) {
  switch (reason) {
    case 0x06: return "key_missing";            // PIN or Key Missing —
                                                // stale pairing (reflash)
    case 0x08: return "connection_timeout";     // Connection Timeout —
                                                // supervision watchdog
    case 0x13: return "remote_user_terminated"; // the HOST ended the link
    case 0x16: return "local_host_terminated";  // THIS side ended the link
    case 0x22: return "ll_response_timeout";    // peer stopped answering
    case 0x3e: return "connection_failed_establish";
    default:   return "unknown";
  }
}

static void on_hci_event(uint8_t packet_type, uint16_t channel,
                         uint8_t* packet, uint16_t size) {
  if (packet_type != HCI_EVENT_PACKET || packet == nullptr) return;
  switch (hci_event_packet_get_type(packet)) {
    case HCI_EVENT_LE_META:
      switch (hci_event_le_meta_get_subevent_code(packet)) {
        case HCI_SUBEVENT_LE_CONNECTION_COMPLETE: {
          if (hci_subevent_le_connection_complete_get_status(packet) !=
              ERROR_CODE_SUCCESS) {
            return;  // a failed connection attempt carries no interval to use
          }
          uint16_t interval =
              hci_subevent_le_connection_complete_get_conn_interval(packet);
          if (interval == 0) return;
          ble_pace_units = interval;
          ble_pace_dirty = true;
          // §7/AC-BLE-04: ask for the fast window (may be declined; see the
          // section comment). No HID send API involved — stack request only.
          gap_request_connection_parameter_update(
              hci_subevent_le_connection_complete_get_connection_handle(
                  packet),
              PACE_MIN_INTERVAL_UNITS, PACE_MAX_INTERVAL_UNITS, 0,
              PACE_SUPERVISION_TIMEOUT_UNITS);
          return;
        }
        case HCI_SUBEVENT_LE_CONNECTION_UPDATE_COMPLETE: {
          if (hci_subevent_le_connection_update_complete_get_status(packet) !=
              ERROR_CODE_SUCCESS) {
            return;  // the host declined the parameters — the old pace stands
          }
          uint16_t interval =
              hci_subevent_le_connection_update_complete_get_conn_interval(
                  packet);
          if (interval == 0) return;
          ble_pace_units = interval;
          ble_pace_dirty = true;
          return;
        }
        default:
          return;  // every other LE subevent is irrelevant to report pacing
      }
    case HCI_EVENT_DISCONNECTION_COMPLETE:
      // P3.28: store WHY the radio ended the link (see the section
      // comment). Loop()'s disconnect drain prints it — this context
      // only records.
      ble_drop_reason =
          hci_event_disconnection_complete_get_reason(packet);
      ble_drop_reason_seen = true;
      return;
    default:
      return;  // every other event type is irrelevant to this handler
  }
}

// ---------------------------------------------------------------------------
// Bring-up and the main loop
// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  Serial.println("SKYWRITER-HID boot");

  // 1. Sensor stack first (specs/ble_hid.md §6 Boot row). `Skywriter.begin`
  //    resets the sensor with the reference timing (100 ms hold + 500 ms
  //    settle, P3.26 part 2 — the old 10/50 ms left cold-boot
  //    acknowledgments to chance); the runtime configuration is ours: ONE
  //    bounded attempt here. A failed attempt is evidence and a retry from
  //    loop() — NEVER a boot denial (P3.26: the old forever-deny made the
  //    whole device invisible, hardware session 5's F12).
  Skywriter.begin(SKYWRITER_PIN_TS, SKYWRITER_PIN_RESET);
  sensor_config_first_attempt();

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

  //    The §7 (AC-BLE-04 / P3.18) HCI event handler joins them: it watches
  //    the LE connection parameters (the interval move reports are paced
  //    at). Registered before the radio starts, exactly like the two
  //    callbacks above — BTstack stores the static registration struct and
  //    this sketch runs only one begin().
  hci_event_registration.callback = &on_hci_event;
  hci_add_event_handler(&hci_event_registration);

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

  // §7 / AC-BLE-04 (P3.18): apply a negotiated connection interval to the
  // engine's move-report cadence — first drain of the loop, so the pace is
  // current before any of this iteration's sensor events. Units are
  // 1.25 ms; convert rounded to nearest whole ms (a pace of 0 could only
  // mean a bogus event: clamp to 1 ms defensively). Handler-context rule:
  // the pace change happens HERE (loop context), not in on_hci_event.
  if (ble_pace_dirty) {
    ble_pace_dirty = false;
    unsigned long pace_ms =
        (static_cast<unsigned long>(ble_pace_units) * 5u + 2u) / 4u;
    if (pace_ms == 0) pace_ms = 1;
    mapper.set_report_interval_ms(pace_ms);
    Serial.print("SKYSTATE pace report_interval_ms=");
    Serial.println(pace_ms);
  }

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
    // 3. The report pace returns to the spec's default constant (§3 rule
    //    6, REPORT_INTERVAL_MS): each new host negotiates its own interval,
    //    re-captured by the HCI watcher on the next connection.
    pulses_clear();
    mapper.set_report_interval_ms(SkywriterHIDMapper::REPORT_INTERVAL_MS);
    MouseBLE.release(MOUSE_ALL);
    KeyboardBLE.releaseAll();
    ble_disconnects++;
    // P3.28: the dropped line names WHY the radio ended the link — the
    // HCI reason code the event handler stored (zero-padded hex, plus the
    // human-readable name), latest-wins like P3.24's snapshot. If no
    // disconnection-complete event was ever seen (defensive — a link loss
    // always produces one), the line says so instead of printing a fake
    // 0x00.
    Serial.print("SKYSTATE ble_dropped reason=");
    if (ble_drop_reason_seen) {
      Serial.print("0x");
      if (ble_drop_reason < 0x10) Serial.print('0');
      Serial.print(ble_drop_reason, HEX);
      Serial.print(' ');
      Serial.print(ble_drop_reason_name(ble_drop_reason));
    } else {
      Serial.print("none no_hci_disconnection_event");
    }
    Serial.println();
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
    ble_connects++;
    Serial.println("SKYSTATE ble_resync battery=100 neutral_report");
    Serial.println("SKYSTATE ble_connected");
  }

  // Repeated while no host is connected, so a serial monitor opened after
  // boot still sees the state (the boot lines are not replayed).
  static unsigned long last_waiting_ms = 0;
  if (!ble_link_open() && now - last_waiting_ms >= 5000) {
    last_waiting_ms = now;
    Serial.println("SKYSTATE waiting_for_host");
  }

  // P3.26: the sensor configuration retries here until it completes — the
  // radio and the life-cycle drains above never depend on it. While the
  // retry is running, poll() stays off for two reasons: a poll could steal
  // the System_Status acknowledgment frame a waiting configuration command
  // is parked on (both read the same sensor buffer over I2C), and an
  // unconfigured sensor's padding reads would pollute the frame counters
  // the health line reports.
  sensor_config_retry_tick(now);

  // Every polled sensor frame dispatches into the mapping engine... (the
  // callbacks drop events while no host is connected, §6 Unconnected) —
  // and polling starts only once the sensor is configured (P3.26, above).
  if (sensor_configured) {
    Skywriter.poll();
  }
  // ...and the engine's timing work (lift-off gating, release-by-silence,
  // coalesced report cadence, hold auto-scroll) runs every loop iteration,
  // driven by the millis() clock.
  mapper.tick(now);
  pulses_tick(now);

  // Health status line, once every HEALTH_INTERVAL_MS (fix item P3.22):
  // the counters the hardware gate P4.0a reads off the serial console —
  // short reads and transfer-line-low polls as shares of all polls (no
  // arithmetic needed), frames by message type, dispatched/dropped sensor
  // events, HID reports by kind, link connects/disconnects, uptime (a
  // board reset shows as uptime dropping back to zero).
  if (now - health_last_ms >= HEALTH_INTERVAL_MS) {
    health_last_ms = now;
    print_health_status(now);
  }
}
