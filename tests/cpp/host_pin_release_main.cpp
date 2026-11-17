// host_pin_release_main.cpp — host program for the transfer-line release
// test (fix_plan item P3.23).
//
// It drives the REAL Arduino driver (arduino/Skywriter/skywriter.cpp) through
// its genuine poll() code path — including the failed-read path (fewer than
// 4 header bytes arrive, the H1 early-return) — and prints every GPIO
// (General-Purpose Input/Output) call the driver made, as recorded by the
// tests/cpp shims. The pytest file tests/test_driver_ts_pin.py asserts the
// transfer (TS) line ends RELEASED, with its pull-up restored, on both the
// normal path and the failed-read path.
//
// Input protocol (one instruction per line):
//
//   RESET         call _SkyWriter::begin() (pin setup + sensor reset pulse),
//                 then clear the recorded actions
//   SHORT         transfer line low, empty I2C answer (0 bytes < the 4-byte
//                 header) → poll() takes the failed-read path
//   FRAME <hex>   transfer line low, this hex frame on the Wire shim →
//                 poll() takes the normal read path
//   DUMP          print the recorded actions since the last RESET:
//                 "MODE <pin> <value>" / "WRITE <pin> <value>"

#include <cstdio>
#include <cstring>
#include <cstdlib>
#include "skywriter.h"
#include "Arduino.h"
#include "Wire.h"

static int hexval(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

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
  Skywriter.begin(27, 17);  // reset pin 17, transfer pin 27 (decoder adapter's)

  char line[8192];
  uint8_t frame[255];
  while (fgets(line, sizeof(line), stdin)) {
    char token[16];
    if (sscanf(line, "%15s", token) != 1) continue;
    if (strcmp(token, "RESET") == 0) {
      g_pin_actions_clear();
    } else if (strcmp(token, "SHORT") == 0) {
      Wire.set_frame(frame, 0);   // the bus answers nothing at all
      g_digital_read_value = 0;   // xfer pin LOW: the sensor signals a frame
      Skywriter.poll();
      g_digital_read_value = 1;
    } else if (strcmp(token, "FRAME") == 0) {
      size_t n = 0;
      if (!decode_hex(line + 6, frame, sizeof(frame), n)) {
        fprintf(stderr, "bad FRAME line: %s", line);
        return 2;
      }
      Wire.set_frame(frame, n);
      g_digital_read_value = 0;
      Skywriter.poll();
      g_digital_read_value = 1;
    } else if (strcmp(token, "DUMP") == 0) {
      for (const PinAction& a : g_pin_actions) {
        printf("%s %u %d\n", a.kind == 0 ? "MODE" : "WRITE",
               static_cast<unsigned>(a.pin), a.value);
      }
      fflush(stdout);
    } else {
      fprintf(stderr, "unrecognised instruction: %s", line);
      return 2;
    }
  }
  return 0;
}
