// host_sysinfo_main.cpp — host program for the SystemInfo / AirWheel-state
// test (fix_plan item P3.29).
//
// It drives the REAL Arduino driver (arduino/Skywriter/skywriter.cpp) through
// its genuine poll() code path with crafted 26-byte sensor-data frames and
// prints, on demand, the driver's public state that the firmware's health
// line and per-event evidence trace print:
//
//   STATE sysinfo=NN aw_valid=b aw_cnt=NN
//
//     sysinfo  — `last_sysinfo`, the RAW SystemInfo byte (sensor-data
//                payload byte 3) of the last frame the driver decoded.
//                Interface.pdf Table 4-10: bit 0 PositionValid, bit 1
//                AirWheelValid, bit 4 EnvironmentalNoise (the sensor
//                reports environmental noise — the health bit P4.0's
//                hover-deafness hypothesis (g) needs), bit 5 Clipping
//                (the sensor's ADCs are clipping), bit 7 DSPRunning.
//     aw_valid — the AirWheel validity flag (the C++ counterpart of the
//                Python driver's `_lastrotation = None` sentinel): true
//                once a frame with valid AirWheel data set the baseline,
//                false again after any frame without valid AirWheel data.
//     aw_cnt   — `airwheel_counter`, the raw free-running 8-bit rotation
//                counter of the last AirWheel-valid frame (32 counts = 1
//                revolution, wraps 255->0).
//
// Dispatched events print as EV lines exactly like host_decoder_main.cpp
// (subset: move + airwheel), so the tests can also assert the SILENT
// AirWheel baseline (the first valid frame after a gap emits nothing).
//
// Input protocol (one instruction per line):
//   FRAME <hex>   queue this frame on the Wire shim, poll() once
//   STATE         print the public state line described above

#include <cstdio>
#include <cstring>
#include "skywriter.h"
#include "Arduino.h"
#include "Wire.h"

static void on_xyz(unsigned int x, unsigned int y, unsigned int z) {
  printf("EV MOVE %u %u %u\n", x, y, z);
}

static void on_airwheel(float degrees) {
  printf("EV AIRWHEEL %.2f\n", degrees);
}

static int hexval(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'a' + 5) return c - 'a' + 10;
  if (c >= 'A' && c <= 'A' + 5) return c - 'A' + 10;
  return -1;
}

int main() {
  Skywriter.onXYZ(on_xyz);
  Skywriter.onAirwheel(on_airwheel);
  // Reset pin 17, transfer pin 27 — the decoder adapter's constants.
  Skywriter.begin(27, 17);

  char line[4096];
  uint8_t frame[255];
  while (fgets(line, sizeof(line), stdin)) {
    char token[16];
    if (sscanf(line, "%15s", token) != 1) continue;
    if (strcmp(token, "STATE") == 0) {
      printf("STATE sysinfo=%u aw_valid=%d aw_cnt=%u\n",
             static_cast<unsigned>(Skywriter.last_sysinfo),
             Skywriter.airwheel_valid ? 1 : 0,
             static_cast<unsigned>(Skywriter.airwheel_counter));
      fflush(stdout);
      continue;
    }
    if (strcmp(token, "FRAME") != 0) {
      fprintf(stderr, "unrecognised instruction: %s", line);
      return 2;
    }
    size_t n = 0;
    const char* p = line + 6;
    while (*p && *p != '\n' && *p != '\r') {
      while (*p && hexval(*p) < 0) p++;
      if (!*p || *p == '\n' || *p == '\r') break;
      int hi = hexval(*p), lo = hexval(*(p + 1));
      if (hi < 0 || lo < 0) {
        fprintf(stderr, "bad FRAME hex: %s", line);
        return 2;
      }
      if (n < sizeof(frame)) frame[n++] = static_cast<uint8_t>((hi << 4) | lo);
      p += 2;
    }
    Wire.set_frame(frame, n);
    g_digital_read_value = 0;   // xfer pin LOW: fresh frame is waiting
    Skywriter.poll();
    g_digital_read_value = 1;
    fflush(stdout);
  }
  return 0;
}
