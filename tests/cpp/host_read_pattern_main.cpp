// host_read_pattern_main.cpp — host program for the driver read-pattern
// and unknown-frame-snapshot tests (fix_plan items P3.25 + P3.24).
//
// It drives the REAL Arduino driver (arduino/Skywriter/skywriter.cpp)
// through its genuine poll() code path and prints, for every poll:
//   * the Wire (I2C two-wire bus) requests it issued — the quantity asked
//     and the bytes the "sensor" actually served (recorded by the shim);
//   * the driver's public health counters (cumulative — the tests compare
//     before/after deltas);
//   * the public unknown-frame snapshot (first 8 frame bytes + the byte
//     count the reads actually returned), as colon-separated hex;
//   * whether the poll ended with the transfer (TS) line released and its
//     pull-up restored (the P3.23 rule, asserted here for the NEW exit
//     paths P3.25 adds: corrupt Size, incomplete frame).
//
// Input protocol (one instruction per line, mirroring
// host_pin_release_main.cpp):
//
//   FRAME <hex>   transfer line low, this hex frame queued on the Wire
//                 shim → one poll()
//   SHORT         transfer line low, nothing on the bus → one poll()
//
// Output: one line per instruction, key=value tokens:
//
//   POLL reqs=26,32,32,32,10 served=26,32,32,32,10 polls=1 ts=1 short=0
//        sensor=0 status=0 fw=1 other=0 snap=84:00:01:83:aa:63:80:e6
//        read=132 released=1
//
// (reqs/served are the requests of THIS poll only; counters are
// cumulative since program start.)

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

// Did this poll end with the P3.23 release pair (line driven HIGH, then
// left as an input with its pull-up)? The recorded pin actions of THIS
// poll must end with exactly that pair.
static int ended_released() {
  if (g_pin_actions.size() < 2) return 0;
  const PinAction& wr = g_pin_actions[g_pin_actions.size() - 2];
  const PinAction& md = g_pin_actions[g_pin_actions.size() - 1];
  return (wr.kind == 1 && wr.value == 1 && md.kind == 0 &&
          md.value == INPUT_PULLUP) ? 1 : 0;
}

int main() {
  // Reset pin 17, transfer pin 27 — the same constants the other host
  // driver programs use.
  Skywriter.begin(27, 17);

  char line[8192];
  uint8_t frame[255];
  while (fgets(line, sizeof(line), stdin)) {
    char token[16];
    if (sscanf(line, "%15s", token) != 1) continue;
    g_request_actions_clear();
    g_pin_actions_clear();
    if (strcmp(token, "FRAME") == 0) {
      size_t n = 0;
      if (!decode_hex(line + 6, frame, sizeof(frame), n)) {
        fprintf(stderr, "bad FRAME line: %s", line);
        return 2;
      }
      Wire.set_frame(frame, n);
      g_digital_read_value = 0;  // xfer pin LOW: the sensor signals a frame
      Skywriter.poll();
    } else if (strcmp(token, "SHORT") == 0) {
      Wire.set_frame(frame, 0);  // the bus answers nothing at all
      g_digital_read_value = 0;
      Skywriter.poll();
    } else {
      fprintf(stderr, "unrecognised instruction: %s", line);
      return 2;
    }
    g_digital_read_value = 1;

    printf("POLL reqs=");
    for (size_t i = 0; i < g_request_actions.size(); i++) {
      printf("%s%u", i ? "," : "",
             static_cast<unsigned>(g_request_actions[i].qty));
    }
    printf(" served=");
    for (size_t i = 0; i < g_request_actions.size(); i++) {
      printf("%s%u", i ? "," : "",
             static_cast<unsigned>(g_request_actions[i].served));
    }
    printf(" polls=%lu ts=%lu short=%lu sensor=%lu status=%lu fw=%lu other=%lu",
           Skywriter.polls, Skywriter.ts_low_polls, Skywriter.short_reads,
           Skywriter.frames_sensor_data, Skywriter.frames_status,
           Skywriter.frames_firmware, Skywriter.frames_other);
    printf(" snap=");
    for (unsigned char i = 0; i < 8; i++) {
      printf("%s%02x", i ? ":" : "", Skywriter.other_snapshot[i]);
    }
    printf(" read=%u released=%d\n",
           static_cast<unsigned>(Skywriter.other_snapshot_read),
           ended_released());
    fflush(stdout);
  }
  return 0;
}
