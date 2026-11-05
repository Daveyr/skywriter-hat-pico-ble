// SkywriterHIDMapper.h — sensor events → HID actions.
//
// This is the implementation of `specs/hid_mapping.md`: the Pico W firmware
// feeds the mapper the canonical sensor events its Skywriter driver decodes
// (the event vocabulary of `specs/hid_mapping.md` §2), and the mapper turns
// them into the HID actions of §3–§6 through a HIDMapperSink the caller
// supplies (in the firmware that sink reports to the Bluetooth HID stack; in
// the fixture-replay tests it prints the `tests/hid_grammar.py` records).
//
// The pointer model (§3, AC-MAP-01) and the touch semantics (§4, AC-MAP-02 /
// AC-MAP-03 / the release half of AC-MAP-07) are fully implemented here —
// normalization, GAIN, sign, jump rejection + re-baseline, lift-off gating,
// report cadence, press-once/repeat-inert holds, release-by-silence,
// tap/doubletap clicks and the §6 button rows. AirWheel semantics (§5) and
// the remaining §6 mapping-table rows (media/consumer, keyboard, hold
// auto-scroll) land with fix items P3.14–P3.15: the mapper already accepts
// those kinds of events and maps them to nothing until then (an
// accepted-and-dropped event, deliberately silent — not a wrong output).

#ifndef SKYWRITER_HID_MAPPER_H
#define SKYWRITER_HID_MAPPER_H

#include <cstdint>

// Touch zones, canonical order as tolerated in specs/hid_mapping.md §2
// (south, west, north, east, center — the electrodes around the board edges).
enum SensorZone : uint8_t {
  ZONE_SOUTH = 0,
  ZONE_WEST = 1,
  ZONE_NORTH = 2,
  ZONE_EAST = 3,
  ZONE_CENTER = 4,
};

// The three touch-bit families of TouchInfo (Interface.pdf §4.5 Table 4-10:
// bits 0-4 touch, 5-9 tap, 10-14 doubletap).
enum TouchKind : uint8_t {
  TOUCH_HOLD = 0,      // the touch bit is currently on (level-ish, §2)
  TOUCH_TAP = 1,       // one-shot tap bit
  TOUCH_DOUBLETAP = 2, // one-shot doubletap bit
};

// Physical HID buttons in §6 order: center = left (primary), west = middle,
// east = right. (§4/P3.13 will use these the §6-zone mapping rows.)
enum HIDButton : uint8_t {
  HID_BUTTON_LEFT = 0,
  HID_BUTTON_MIDDLE = 1,
  HID_BUTTON_RIGHT = 2,
};

// USB HID usage codes for the keyboard rows of §6 (Page Up / Page Down):
// Page Up = 0x4E (78), Page Down = 0x4F (79). (used from P3.13/P3.15 on.)
static const uint8_t HID_USAGE_PAGE_UP = 78;
static const uint8_t HID_USAGE_PAGE_DOWN = 79;

// Where the HID actions go. One sink method per report-channel action of
// `specs/hid_mapping.md` §3–§6 — the firmware sink will call MouseBLE /
// KeyboardBLE; the replay harness prints records for tests/hid_grammar.py.
class HIDMapperSink {
 public:
  virtual ~HIDMapperSink() {}

  // §3: relative mouse movement, in whole cursor units (GAIN-scaled,
  // fully accumulated; the fractional remainder is retained inside the
  // mapper for the next report so movement is never lost).
  virtual void mouseMove(int16_t dx, int16_t dy) = 0;

  // §4: a button press or release ("left" / "middle" / "right", see
  // HIDButton). Never combined: each transition is its own report.
  virtual void mouseButton(uint8_t button, bool down) = 0;

  // §5: mouse-wheel notches, + = scroll up (away from the user).
  virtual void mouseWheel(int8_t notches) = 0;

  // §4: a completed press+release (count clicks of TAP_CLICK_MS each) —
  // tap-to-click / double-click as a single abstract action; the click's
  // press and release must never straddle a coalesced period.
  virtual void mouseClick(uint8_t button, uint8_t count) = 0;

  // §6: a keyboard-report press (usage 78 = Page Up, 79 = Page Down).
  virtual void keyboardPress(uint8_t usage) = 0;

  // §6: a consumer-control report press (usage e.g. 0x00B5 = 181 next track).
  virtual void consumerPress(uint16_t usage) = 0;
};

// The mapping engine itself. All times are milliseconds, passed in by the
// caller (the firmware loop calls tick(now) continuously; the replay harness
// drives the same code with its VirtualClock). No millis() calls here, so the
// exact same source runs on the Pico W and in the host tests.
class SkywriterHIDMapper {
 public:
  // The tunables of `specs/hid_mapping.md` §3–§7, as named constants in the
  // one place the spec names them (§7: "the mapping table IS the
  // implementation"). The hardware loop (fix item P4.5) tunes them and
  // records the final values back into the spec.
  // GAIN: δ = Δraw * GAIN (§3 rule 2, initial 1/256 — one full sensor field
  //   width ≈ 256 cursor-widths of travel).
  static const float GAIN;
  // Jump rejection threshold in raw sensor units (§3 rule 4, initial 8192 ≈
  // 1/8 of the field width).
  static const int JUMP_THRESHOLD;
  // Lift-off: a valid position was not seen for this long → tracking paused
  // (§3 rule 5, initial 100 ms).
  static const unsigned long LIFT_OFF_MS;
  // Report cadence: at most one mouse-move report per connection interval
  // (§3 rule 6). Initial 15 ms — the slowest common BLE HID connection
  // interval, so the pointer rate never drops under the 60 Hz floor of
  // AC-BLE-04 even on the slowest host; the firmware (P3.18) may tighten it
  // towards the live connection interval. Deltas accumulate while held, so
  // coalescing never drops movement.
  static const unsigned long REPORT_INTERVAL_MS;
  // §4 touch release: no touch frame for this long releases the held button
  // (initial 200 ms = 40 missed 5 ms frames). The time is compared with `>`
  // (strictly), so a frame at exactly the threshold still counts as held.
  static const unsigned long TOUCH_RELEASE_MS;
  // §4 click length for tap/doubletap clicks (initial 50 ms).
  static const unsigned long TAP_CLICK_MS;
  // §5 AirWheel scroll direction override (false: clockwise = scroll up).
  static const bool AIRWHEEL_INVERT;
  // §6 note: the default profile enables AirWheel (circle rows stay dormant).
  static const bool AIRWHEEL_ENABLED;

  explicit SkywriterHIDMapper(HIDMapperSink& sink) : sink_(sink) {}

  // ---- canonical sensor event inputs (§2), all carrying arrival time ----

  // position(x, y, z) with PositionValid — raw 0..65535 sensor units.
  // z is deliberately unused by the default profile (§3 rule 5: reserved for
  // a future height-sensitivity feature).
  void onPosition(uint16_t x, uint16_t y, uint16_t z, unsigned long now_ms);

  // touch/tap/doubletap(zone) — §4 semantics (press-once/repeat-inert,
  // release-by-silence via tick(), tap/doubletap clicks) plus the §6 button
  // rows: touch(center) hold → left, tap(center) → left, doubletap(center)
  // → left ×2, tap(east) → right, tap(west) → middle.
  void onTouch(SensorZone zone, TouchKind kind, unsigned long now_ms);

  // gesture(code, class, edge) — only the code is needed by §6. Rows land
  // with P3.15; garbage (code 1) maps to nothing there.
  void onGesture(uint8_t code, unsigned long now_ms);

  // airwheel(degrees) — signed rotation delta of this frame. §5 semantics
  // (notches, accumulator, invert) land with P3.14.
  void onAirwheel(float degrees, unsigned long now_ms);

  // ---- time ----

  // Advance the clock without events (the firmware's idle-loop call); also
  // evaluates lift-off gating and releases a due coalesced move report.
  void tick(unsigned long now_ms);

  // Shutdown / final flush (the harness's finish hook): emits any still
  // pending accumulated movement immediately so nothing is lost.
  void finish(unsigned long now_ms);

 private:
  void attempt_report(unsigned long now_ms, bool force);
  // §4 explicit-release trigger (lift-off; a future disconnect path would
  // call the same via a public wrapper when the firmware needs it, P3.17):
  // every held button goes up immediately, in zone order.
  void release_all_buttons();

  HIDMapperSink& sink_;

  // Pointer model state (§3):
  bool have_prev_ = false;           // tracking: prev_ is a valid baseline
  uint16_t prev_x_ = 0;              // last valid raw position
  uint16_t prev_y_ = 0;
  unsigned long last_position_ms_ = 0;   // when the last valid position came
  float pending_dx_ = 0.0f;          // accumulated, not-yet-reported movement
  float pending_dy_ = 0.0f;          // (float: fractional GAIN carry-over)
  unsigned long last_report_ms_ = 0;     // when the last move report went out

  // Touch state (§4): the sensor has no release event, so each zone tracks
  // its own press state. held_ is only ever set for zones that have a §6
  // hold button (currently center); last_touch_ms_ is tracked for every
  // zone so repeats refresh the recency whatever the mapping says.
  static const int kZoneCount = 5;   // south, west, north, east, center
  bool held_[kZoneCount] = {};       // zone's button is currently down
  unsigned long last_touch_ms_[kZoneCount] = {};  // last touch frame seen
};

#endif  // SKYWRITER_HID_MAPPER_H
