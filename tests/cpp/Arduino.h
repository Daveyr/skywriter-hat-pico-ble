// Arduino.h — host-compilation shim for tests/cpp/host_decoder_main.cpp.
//
// Provides just enough of the Arduino core API for skywriter.cpp (the Pico
// W Arduino driver in arduino/Skywriter) to compile as a plain host program.
// Implementations live in arduino_shim.cpp.

#ifndef HOST_ARDUINO_SHIM_H
#define HOST_ARDUINO_SHIM_H

#include <cstdint>
#include <cstddef>

#define INPUT          0
#define OUTPUT         1
#define INPUT_PULLUP   2

#define LOW            0
#define HIGH           1

void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, uint8_t val);
int digitalRead(uint8_t pin);
void delay(unsigned long ms);

// Current state of the transfer ("fresh data waiting") pin. The decoder
// adapter sets it per frame: LOW so poll() enters the read branch.
extern int g_digital_read_value;

#endif
