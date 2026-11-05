// host_mapping_main.cpp — the fixture-replay harness's *mapping* host
// program (fix_plan item P3.12). It is the whole firmware signal chain in
// one binary:
//
//   stdin frames → the REAL Arduino driver (arduino/Skywriter/skywriter.cpp,
//   compiled with the tests/cpp shims exactly like the decoder adapter) →
//   canonical sensor events → SkywriterHIDMapper (pico-arduino/SkywriterHID,
//   the same source the firmware sketch will link) → HID action records on
//   stdout.
//
// Input protocol (one instruction per line, whitespace-separated tokens):
//
//   FRAME <hex>    put the hex-encoded I2C frame on the Wire shim (the
//                  xfer pin low, like a fresh frame waiting) and call
//                  _SkyWriter::poll() once. Driver callbacks feed the
//                  mapper at the current simulated time.
//   TICK <ms>      advance to simulated time <ms> and call mapper.tick().
//   FIN <ms>       advance to <ms> and call mapper.finish() (shutdown
//                  semantics: pending accumulated movement is flushed even
//                  if the report interval has not elapsed).
//
// Output records (one per line, mirroring tests/hid_grammar.py):
//
//   HID MOVE <dx> <dy>            mouse move, whole cursor units
//   HID BUTTON <left|middle|right> <down|up>
//   HID WHEEL <notches>           + = scroll up (away from the user)
//   HID CLICK <button> <count> <click_ms>
//   HID KEY <usage78|79>          keyboard press (Page Up 78 / Page Down 79)
//   HID CONSUME <usage>           consumer-control press (decimal USB usage)
//
// One process per replayed scenario keeps decoder state (touch bits, wheel
// counter) and mapper state (pointer baseline, accumulators) naturally
// fresh; the initial state is exactly the saver's, so a rerun yields a
// byte-identical record stream.

#include <cstdio>
#include <cstring>
#include <cstdlib>
#include "skywriter.h"
#include "SkywriterHIDMapper.h"
#include "Arduino.h"
#include "Wire.h"

// Simulated time is *input-driven* (TICK/FIN lines): the driver itself has
// no clock, and mapper state only changes in its own methods, which are
// handed the time explicitly.
static unsigned long g_now_ms = 0;

static SkywriterHIDMapper* g_mapper = nullptr;

// ---- mapper sink → stdout records (tests/hid_grammar.py shape) -------------

class StdoutMapperSink : public HIDMapperSink {
  static const char* button_name(uint8_t button) {
    switch (button) {
      case HID_BUTTON_LEFT: return "left";
      case HID_BUTTON_MIDDLE: return "middle";
      case HID_BUTTON_RIGHT: return "right";
    }
    return "?";
  }

 public:
  void mouseMove(int16_t dx, int16_t dy) override {
    printf("HID MOVE %d %d\n", static_cast<int>(dx), static_cast<int>(dy));
  }
  void mouseButton(uint8_t button, bool down) override {
    printf("HID BUTTON %s %s\n", button_name(button), down ? "down" : "up");
  }
  void mouseWheel(int8_t notches) override {
    printf("HID WHEEL %d\n", static_cast<int>(notches));
  }
  void mouseClick(uint8_t button, uint8_t count) override {
    // The click length is the mapper's own TAP_CLICK_MS (§4); the record
    // carries it so the harness asserts the spec value too.
    printf("HID CLICK %s %u %lu\n", button_name(button),
           static_cast<unsigned>(count),
           SkywriterHIDMapper::TAP_CLICK_MS);
  }
  void keyboardPress(uint8_t usage) override {
    printf("HID KEY %u\n", static_cast<unsigned>(usage));
  }
  void consumerPress(uint16_t usage) override {
    printf("HID CONSUME %u\n", static_cast<unsigned>(usage));
  }
};

// ---- driver callbacks → canonical events → mapper -------------------------

// The mapper's onTouch takes (zone, kind); the driver reports its
// skywriter.h touch codes (SW_*), so the canonical-decode table lives here
// in the adapter shim — the C++ counterpart of tests/canonical.py's
// TOUCH_CODES (lowest code = highest TouchInfo bit, Interface.pdf §4.5).
static const struct {
  unsigned char code;
  TouchKind kind;
  SensorZone zone;
} kTouchMap[] = {
    {0,  TOUCH_DOUBLETAP, ZONE_CENTER},
    {1,  TOUCH_DOUBLETAP, ZONE_EAST},
    {2,  TOUCH_DOUBLETAP, ZONE_NORTH},
    {3,  TOUCH_DOUBLETAP, ZONE_WEST},
    {4,  TOUCH_DOUBLETAP, ZONE_SOUTH},
    {5,  TOUCH_TAP,       ZONE_CENTER},
    {6,  TOUCH_TAP,       ZONE_EAST},
    {7,  TOUCH_TAP,       ZONE_NORTH},
    {8,  TOUCH_TAP,       ZONE_WEST},
    {9,  TOUCH_TAP,       ZONE_SOUTH},
    {10, TOUCH_HOLD,      ZONE_CENTER},
    {11, TOUCH_HOLD,      ZONE_EAST},
    {12, TOUCH_HOLD,      ZONE_NORTH},
    {13, TOUCH_HOLD,      ZONE_WEST},
    {14, TOUCH_HOLD,      ZONE_SOUTH},
};

static void on_xyz(unsigned int x, unsigned int y, unsigned int z) {
  g_mapper->onPosition(static_cast<uint16_t>(x), static_cast<uint16_t>(y),
                       static_cast<uint16_t>(z), g_now_ms);
}

static void on_touch(unsigned char code) {
  for (const auto& entry : kTouchMap) {
    if (entry.code == code) {
      g_mapper->onTouch(entry.zone, entry.kind, g_now_ms);
      return;
    }
  }
}

static void on_gesture(unsigned char code) {
  g_mapper->onGesture(static_cast<uint8_t>(code), g_now_ms);
}

static void on_airwheel(float degrees) {
  g_mapper->onAirwheel(degrees, g_now_ms);
}

// System_Status (0x15) / Fw_Version_Info (0x83) are control frames: no HID
// output (§2), so nothing is fed to the mapper.

// ---- input ---------------------------------------------------------------

static int hexval(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

// Decode one frame's hex (the harness checker accepts spaces like the
// decoder adapter does).
static bool decode_hex(const char* text, uint8_t* out, size_t cap, size_t& n) {
  n = 0;
  const char* p = text;
  while (*p && *p != '\n' && *p != '\r') {
    while (*p && (hexval(*p) < 0)) p++;
    if (!*p || *p == '\n' || *p == '\r') break;
    int hi = hexval(*p), lo = hexval(*(p + 1));
    if (hi < 0 || lo < 0) return false;
    if (n < cap) out[n++] = static_cast<uint8_t>((hi << 4) | lo);
    p += 2;
  }
  return true;
}

int main() {
  StdoutMapperSink sink;
  SkywriterHIDMapper mapper(sink);
  g_mapper = &mapper;

  Skywriter.onXYZ(on_xyz);
  Skywriter.onTouch(on_touch);
  Skywriter.onGesture(on_gesture);
  Skywriter.onAirwheel(on_airwheel);
  // Reset pin 17, transfer pin 27 — same constants as the decoder adapter.
  Skywriter.begin(27, 17);

  char line[8192];
  uint8_t frame[255];
  while (fgets(line, sizeof(line), stdin)) {
    char token[16];
    unsigned long time_arg = 0;
    int consumed = 0;
    if (sscanf(line, "%15s", token) != 1) continue;
    if (sscanf(line + (strlen(token)), "%lu %n", &time_arg, &consumed) < 1) {
      time_arg = 0;
    }
    if (strcmp(token, "FRAME") == 0) {
      size_t n = 0;
      if (!decode_hex(line + 6, frame, sizeof(frame), n)) {
        fprintf(stderr, "bad FRAME line: %s", line);
        return 2;
      }
      if (n == 0) continue;
      Wire.set_frame(frame, n);
      g_digital_read_value = 0;   // xfer pin LOW: fresh frame is waiting
      Skywriter.poll();
      g_digital_read_value = 1;
    } else if (strcmp(token, "TICK") == 0) {
      g_now_ms = time_arg;
      mapper.tick(g_now_ms);
    } else if (strcmp(token, "FIN") == 0) {
      g_now_ms = time_arg;
      mapper.finish(g_now_ms);
    } else {
      fprintf(stderr, "unrecognised instruction: %s", line);
      return 2;
    }
    fflush(stdout);
  }
  return 0;
}
