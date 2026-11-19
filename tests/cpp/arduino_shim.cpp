// arduino_shim.cpp — implementation of the host-compilation Arduino/Wire
// shims declared in Arduino.h / Wire.h (see those files for the why).

#include "Arduino.h"
#include "Wire.h"

int g_digital_read_value = 1;

std::vector<PinAction> g_pin_actions;

void g_pin_actions_clear() {
  g_pin_actions.clear();
}

std::vector<RequestAction> g_request_actions;

void g_request_actions_clear() {
  g_request_actions.clear();
}

void pinMode(uint8_t pin, uint8_t mode) {
  g_pin_actions.push_back({0, pin, mode});
}
void digitalWrite(uint8_t pin, uint8_t val) {
  g_pin_actions.push_back({1, pin, val});
}
int digitalRead(uint8_t) {
  return g_digital_read_value;
}
void delay(unsigned long) {}

void WireClass::begin() {
  len_ = cursor_ = served_ = 0;
}

uint8_t WireClass::requestFrom(uint8_t, uint8_t qty) {
  // The "sensor" continues serving its buffer across the reads of one
  // asserted transfer (the P3.11c/P3.25 continuation model): this request
  // serves the next `qty` bytes from the current position. `cursor_` only
  // advances through read() (bytes the driver actually consumed), while
  // `served_` marks the readable end of this request — exactly the
  // available()/read() shape the real Wire API presents after a request.
  size_t remaining = (len_ > cursor_) ? len_ - cursor_ : 0;
  uint8_t served = (qty < remaining) ? qty : static_cast<uint8_t>(remaining);
  served_ = static_cast<uint8_t>(cursor_ + served);
  g_request_actions.push_back({qty, served});
  return served;
}

uint8_t WireClass::available() {
  return static_cast<uint8_t>(served_ - cursor_);
}

int WireClass::read() {
  return (cursor_ < served_) ? static_cast<int>(buf_[cursor_++]) : -1;
}

void WireClass::set_frame(const uint8_t *bytes, size_t len) {
  len_ = (len < sizeof(buf_)) ? len : sizeof(buf_);
  for (size_t i = 0; i < len_; i++) buf_[i] = bytes[i];
  cursor_ = served_ = 0;
}

void WireClass::clear_frame() {
  len_ = cursor_ = served_ = 0;
}

WireClass Wire;
