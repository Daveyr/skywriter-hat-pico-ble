// host_decoder_main.cpp — the Arduino Skywriter driver
// (arduino/Skywriter/skywriter.cpp) compiled as a plain host program for the
// fixture-replay harness (fix_plan item P3.1).
//
// What it does: reads one hex-encoded I2C frame per line from stdin, queues
// it on the Wire (two-wire bus) shim, and calls _SkyWriter::poll() once —
// i.e. the real driver code path (xfer pin low → header parse → handler). All
// of the driver's callbacks print one event line per emission:
//
//   EV MOVE <x> <y> <z>       onXYZ, raw 16-bit position values
//   EV GESTURE <code> <class> <edge>
//                             onGesture, with the GestureInfo attributes the
//                             driver decodes from the full 32-bit word (P3.11):
//                             code per skywriter.h (1 garbage, 2-5 flicks,
//                             6-7 circles), class = GestureInfo bits 12-15
//                             (0 garbage, 1 flick, 2 circle), edge = bit 16
//                             (0/1 edge-flick flag). The driver keeps them
//                             as public state (last_gesture_class /
//                             last_gesture_edge), the C++ counterpart of the
//                             Python driver's `gesture_class`/`gesture_edge`
//                             globals, and they are set before dispatch.
//   EV TOUCH <code>           onTouch, code per skywriter.h (see below)
//   EV AIRWHEEL <degrees>     onAirwheel, rotation delta in degrees
//                             (float — one sensor step = 11.25 degrees)
//   EV SYSTEMSTATUS <msg_id> <error>
//                             onSystemStatus, the System_Status (0x15)
//                             acknowledge: the control command being
//                             acknowledged (e.g. 170 = Set_Runtime_Parameter
//                             0xA2) and its 16-bit error code (0 = applied)
//                             — Interface.pdf §3.6 Table 3-8 (P3.11b)
//   EV FWVERSION <fw_valid> <version>
//                             onFirmwareVersion, the Fw_Version_Info (0x83)
//                             report's FwValid byte and NUL-stripped version
//                             string; only valid (0xAA) reports are emitted.
//                             The version string is ';'-separated ASCII but
//                             CONTAINS a space (ISO build timestamp), so the
//                             adapter must parse it as the remainder of the
//                             line. (Interface.pdf §4.3, P3.11b)
//
// Touch codes (skywriter.h constants, lowest code = highest bit scanned):
//   0 doubletap center · 1 doubletap east · 2 doubletap north
//   3 doubletap west · 4 doubletap south · 5 tap center · 6 tap east
//   7 tap north · 8 tap west · 9 tap south · 10 touch center
//   11 touch east · 12 touch north · 13 touch west · 14 touch south
//
// One process per replayed scenario, so decoder state (last gesture, wheel
// counter, …) is naturally fresh each run — in particular the AirWheel
// baseline (`airwheel_counter_valid` = the C++ counterpart of the Python
// driver's `_lastrotation = None` sentinel) and the accumulated
// `rotation` degrees start at their pristine defaults, the same fresh state
// the Python adapter resets explicitly in its `begin()`.

#include <cstdio>
#include <cstring>
#include "skywriter.h"
#include "Arduino.h"
#include "Wire.h"

static void on_xyz(unsigned int x, unsigned int y, unsigned int z) {
  printf("EV MOVE %u %u %u\n", x, y, z);
}

static void on_touch(unsigned char code) {
  printf("EV TOUCH %u\n", static_cast<unsigned>(code));
}

static void on_gesture(unsigned char code) {
  // The driver's gesture attributes (last_gesture_class /
  // last_gesture_edge, decoded from the full 32-bit GestureInfo word) are
  // set before the dispatch, so reading them inside this callback snapshots
  // the attributes of exactly the gesture being reported — the same trick
  // the Python adapter uses on the driver's module globals (deviation D7's
  // Arduino half closed with P3.11).
  printf("EV GESTURE %u %u %d\n", static_cast<unsigned>(code),
         static_cast<unsigned>(Skywriter.last_gesture_class),
         Skywriter.last_gesture_edge ? 1 : 0);
}

static void on_airwheel(float degrees) {
  // Two decimals: degrees come quantized to 11.25-degree sensor steps, so
  // quarters are the finest value the driver can emit (%.2f is exact for
  // them).
  printf("EV AIRWHEEL %.2f\n", degrees);
}

static void on_system_status(unsigned char msg_id, unsigned int error) {
  printf("EV SYSTEMSTATUS %u %u\n", static_cast<unsigned>(msg_id),
         static_cast<unsigned>(error));
}

static void on_firmware_version(unsigned char fw_valid, const char* version) {
  // %s prints the version string verbatim: it is ';'-separated ASCII but
  // contains a space (the ISO build timestamp), so the adapter must treat
  // everything after "EV FWVERSION <fw_valid> " as the string.
  printf("EV FWVERSION %u %s\n", static_cast<unsigned>(fw_valid), version);
}

static int hexval(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

int main() {
  Skywriter.onXYZ(on_xyz);
  Skywriter.onTouch(on_touch);
  Skywriter.onGesture(on_gesture);
  Skywriter.onAirwheel(on_airwheel);
  Skywriter.onSystemStatus(on_system_status);
  Skywriter.onFirmwareVersion(on_firmware_version);
  // Reset pin 17, transfer pin 27 — the same constants the Raspberry Pi
  // Python driver uses (skywriter.py SW_RESET_PIN / SW_XFER_PIN).
  Skywriter.begin(27, 17);

  char line[2048];
  uint8_t frame[255];
  while (fgets(line, sizeof(line), stdin)) {
    size_t n = 0;
    size_t len = strlen(line);
    size_t i = 0;
    while (i + 1 < len) {
      // skip separators/whitespace between hex pairs
      while (i < len && hexval(line[i]) < 0) i++;
      if (i + 1 >= len) break;
      int hi = hexval(line[i]), lo = hexval(line[i + 1]);
      if (hi < 0 || lo < 0) break;
      if (n < sizeof(frame)) frame[n++] = static_cast<uint8_t>((hi << 4) | lo);
      i += 2;
    }
    if (n == 0) continue;

    Wire.set_frame(frame, n);
    g_digital_read_value = 0;   // xfer pin LOW: fresh frame is waiting
    Skywriter.poll();
    g_digital_read_value = 1;
    fflush(stdout);
  }
  return 0;
}
