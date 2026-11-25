// Arduino.h — host-compilation shim for tests/cpp/host_decoder_main.cpp.
//
// Provides just enough of the Arduino core API for skywriter.cpp (the Pico
// W Arduino driver in arduino/Skywriter) to compile as a plain host program.
// Implementations live in arduino_shim.cpp.
//
// Since fix item P3.23 the GPIO calls are also RECORDED: the
// transfer-line-release behaviour of poll()'s every exit path is asserted
// from a host test (tests/test_driver_ts_pin.py) through
// tests/cpp/host_pin_release_main.cpp.

#ifndef HOST_ARDUINO_SHIM_H
#define HOST_ARDUINO_SHIM_H

#include <cstdint>
#include <cstddef>
#include <vector>

#define INPUT          0
#define OUTPUT         1
#define INPUT_PULLUP   2

#define LOW            0
#define HIGH           1

// One recorded GPIO call. kind 0 = pinMode(pin, value), kind 1 =
// digitalWrite(pin, value), kind 2 = delay(value ms) — pin unused.
struct PinAction {
  uint8_t kind;
  uint8_t pin;
  int value;
};

// Every pinMode/digitalWrite call since the last g_pin_actions_clear().
extern std::vector<PinAction> g_pin_actions;
void g_pin_actions_clear();

void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, uint8_t val);
int digitalRead(uint8_t pin);
void delay(unsigned long ms);

// Current state of the transfer ("fresh data waiting") pin. The decoder
// adapter sets it per frame: LOW so poll() enters the read branch.
extern int g_digital_read_value;

#endif
