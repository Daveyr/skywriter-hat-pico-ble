// host_mapper_unit_main.cpp — a *direct* SkywriterHIDMapper unit test
// program (fix_plan item P3.13). The fixture corpus cannot carry every
// touch-timing behaviour: the Python driver rate-limits repeat touch
// callbacks by design (default 4 Hz = one fire per 250 ms per zone), so a
// scenario whose touch frames arrive closer than 250 ms would make the two
// decoders' canonical streams diverge in a way the parity machinery cannot
// attribute honestly. The repeat-inert press and the release/lift-off
// timings therefore get pinned here, against the mapper alone — the exact
// source the firmware links, driven at mapper call granularity:
//
//   stdin instructions (one per line, times are simulated milliseconds):
//     TOUCH <zone> <kind> <ms>   mapper.onTouch(zone, kind, ms)
//         zone: south|west|north|east|center
//         kind: hold|tap|doubletap
//     POSITION <x> <y> <ms>      mapper.onPosition(x, y, z=0, ms)
//     AIRWHEEL <degrees> <ms>    mapper.onAirwheel(degrees, ms)
//     DISCONNECT <ms>            mapper.disconnect(ms) (P3.17: the BLE
//                                link-loss path of specs/ble_hid.md §6)
//     TICK <ms>                  mapper.tick(ms)
//     FIN <ms>                   mapper.finish(ms)
//
//   stdout: the same `HID ...` records as host_mapping_main.cpp (the
//   tests/hid_grammar.py shapes), so both harness sides share one grammar.
//
// One process per replay keeps mapper state fresh, like the other adapters.

#include <cstdio>
#include <cstring>
#include <cstdlib>
#include "SkywriterHIDMapper.h"

static SkywriterHIDMapper* g_mapper = nullptr;

// ---- mapper sink → stdout records (same shapes as host_mapping_main) ------

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

static int zone_name(const char* text, SensorZone& zone) {
  if (strcmp(text, "south") == 0) { zone = ZONE_SOUTH; return 1; }
  if (strcmp(text, "west") == 0)  { zone = ZONE_WEST;  return 1; }
  if (strcmp(text, "north") == 0) { zone = ZONE_NORTH; return 1; }
  if (strcmp(text, "east") == 0)  { zone = ZONE_EAST;  return 1; }
  if (strcmp(text, "center") == 0){ zone = ZONE_CENTER; return 1; }
  return 0;
}

static int kind_name(const char* text, TouchKind& kind) {
  if (strcmp(text, "hold") == 0)      { kind = TOUCH_HOLD; return 1; }
  if (strcmp(text, "tap") == 0)       { kind = TOUCH_TAP; return 1; }
  if (strcmp(text, "doubletap") == 0) { kind = TOUCH_DOUBLETAP; return 1; }
  return 0;
}

int main() {
  StdoutMapperSink sink;
  SkywriterHIDMapper mapper(sink);
  g_mapper = &mapper;

  static char line[256];
  while (fgets(line, sizeof(line), stdin)) {
    char token[16];
    unsigned long t = 0;
    if (sscanf(line, "%15s", token) != 1) continue;
    if (strcmp(token, "TOUCH") == 0) {
      char zone_text[16], kind_text[16];
      SensorZone zone;
      TouchKind kind;
      if (sscanf(line, "%*15s %15s %15s %lu", zone_text, kind_text, &t) != 3 ||
          !zone_name(zone_text, zone) || !kind_name(kind_text, kind)) {
        fprintf(stderr, "bad TOUCH line: %s", line);
        return 2;
      }
      mapper.onTouch(zone, kind, t);
    } else if (strcmp(token, "POSITION") == 0) {
      unsigned long x = 0, y = 0;
      if (sscanf(line, "%*15s %lu %lu %lu", &x, &y, &t) != 3) {
        fprintf(stderr, "bad POSITION line: %s", line);
        return 2;
      }
      mapper.onPosition(static_cast<uint16_t>(x), static_cast<uint16_t>(y),
                        0, t);
    } else if (strcmp(token, "AIRWHEEL") == 0) {
      float degrees = 0.0f;
      if (sscanf(line, "%*15s %f %lu", &degrees, &t) != 2) {
        fprintf(stderr, "bad AIRWHEEL line: %s", line);
        return 2;
      }
      mapper.onAirwheel(degrees, t);
    } else if (strcmp(token, "DISCONNECT") == 0) {
      if (sscanf(line, "%*15s %lu", &t) != 1) {
        fprintf(stderr, "bad DISCONNECT line: %s", line);
        return 2;
      }
      mapper.disconnect(t);
    } else if (strcmp(token, "TICK") == 0) {
      if (sscanf(line, "%*15s %lu", &t) != 1) {
        fprintf(stderr, "bad TICK line: %s", line);
        return 2;
      }
      mapper.tick(t);
    } else if (strcmp(token, "FIN") == 0) {
      if (sscanf(line, "%*15s %lu", &t) != 1) {
        fprintf(stderr, "bad FIN line: %s", line);
        return 2;
      }
      mapper.finish(t);
    } else {
      fprintf(stderr, "unrecognised instruction: %s", line);
      return 2;
    }
    fflush(stdout);
  }
  return 0;
}
