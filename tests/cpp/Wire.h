// Wire.h — host-compilation shim for the Arduino Wire (I2C two-wire bus)
// library, used together with tests/cpp/host_decoder_main.cpp.
//
// One replay frame at a time is queued via set_frame(); requestFrom() then
// serves at most `qty` of those bytes from index 0, exactly like the real
// controller would after requesting `qty` bytes from the sensor.

#ifndef HOST_WIRE_SHIM_H
#define HOST_WIRE_SHIM_H

#include <cstdint>
#include <cstddef>

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
