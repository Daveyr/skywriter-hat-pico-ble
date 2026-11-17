// arduino_shim.cpp — implementation of the host-compilation Arduino/Wire
// shims declared in Arduino.h / Wire.h (see those files for the why).

#include "Arduino.h"
#include "Wire.h"

int g_digital_read_value = 1;

std::vector<PinAction> g_pin_actions;

void g_pin_actions_clear() {
  g_pin_actions.clear();
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
  cursor_ = 0;
  served_ = (qty < len_) ? qty : static_cast<uint8_t>(len_);
  return served_;
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
