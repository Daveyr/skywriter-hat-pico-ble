// host_reset_timing_main.cpp — host program for the sensor-reset timing
// test (fix_plan item P3.26, part 2).
//
// It calls the REAL Arduino driver's begin() (arduino/Skywriter/skywriter.cpp)
// and prints every GPIO and delay event from process start, in the order the
// driver made them, as recorded by the tests/cpp shims. The pytest file
// tests/test_driver_reset_timing.py asserts the reference timing the Python
// driver's reset() uses (library/skywriter/__init__.py, whose comment cites
// the datasheet's 200 ms boot delay): reset LOW → hold 100 ms → release →
// settle 500 ms. The former 10 ms hold + 50 ms settle left cold-boot
// sensor acknowledgments to chance (hardware session 5's F12 captures).

#include "skywriter.h"
#include "Arduino.h"

int main() {
  g_pin_actions_clear();
  Skywriter.begin(27, 17);  // reset pin 17, transfer pin 27 (decoder adapter's)
  for (const PinAction& a : g_pin_actions) {
    if (a.kind == 0) {
      printf("MODE %u %d\n", static_cast<unsigned>(a.pin), a.value);
    } else if (a.kind == 1) {
      printf("WRITE %u %d\n", static_cast<unsigned>(a.pin), a.value);
    } else {
      printf("DELAY %d\n", a.value);
    }
  }
  fflush(stdout);
  return 0;
}
