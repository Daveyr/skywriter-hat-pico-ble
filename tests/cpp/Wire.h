// Wire.h — host-compilation shim for the Arduino Wire (I2C two-wire bus)
// library, used together with the tests/cpp host driver programs.
//
// One replay frame at a time is queued via set_frame(); requestFrom() then
// serves the queued bytes. Since fix item P3.25 the shim models the
// sensor-side continuation contract the driver relies on: the "sensor"
// CONTINUES serving its buffer across the separate reads of one asserted
// transfer (the same model the Python driver's sized reads use, P3.11c) —
// each requestFrom() serves the next `qty` bytes from the current position,
// and set_frame()/clear_frame() rewind it (a new message starts at byte 0).
// (Before P3.25 the driver issued a single large request per transfer, so
// every request starting at byte 0 was an equivalent simplification.)
//
// Since fix item P3.25 every requestFrom() call is also RECORDED in
// g_request_actions (mirroring the GPIO action log in Arduino.h), so host
// tests can assert the driver's read pattern — a 26-byte request first,
// continuations only for frames longer than that — through the genuine
// poll() code path (tests/test_driver_read_pattern.py).

#ifndef HOST_WIRE_SHIM_H
#define HOST_WIRE_SHIM_H

#include <cstdint>
#include <cstddef>
#include <vector>

// One recorded I2C read request: qty = bytes the driver asked for,
// served = bytes the queued "sensor" buffer actually returned (the
// requestFrom() return value the driver's snapshot records).
struct RequestAction {
  uint8_t qty;
  uint8_t served;
};

// Every Wire.requestFrom() call since the last g_request_actions_clear().
extern std::vector<RequestAction> g_request_actions;
void g_request_actions_clear();

class WireClass {
 public:
  void begin();
  uint8_t requestFrom(uint8_t addr, uint8_t qty);
  uint8_t available();
  int read();

  // Test hooks (not part of the Arduino API).
  void set_frame(const uint8_t *bytes, size_t len);
  void clear_frame();

 private:
  uint8_t buf_[255];
  size_t len_ = 0, cursor_ = 0;
  uint8_t served_ = 0;
};

extern WireClass Wire;

#endif
