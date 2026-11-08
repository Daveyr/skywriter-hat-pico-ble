// SkywriterHIDMapper.h — sensor events → HID actions.
//
// This is the implementation of `specs/hid_mapping.md`: the Pico W firmware
// feeds the mapper the canonical sensor events its Skywriter driver decodes
// (the event vocabulary of `specs/hid_mapping.md` §2), and the mapper turns
// them into the HID actions of §3–§6 through a HIDMapperSink the caller
// supplies (in the firmware that sink reports to the Bluetooth HID stack; in
// the fixture-replay tests it prints the `tests/hid_grammar.py` records).
//
// The pointer model (§3, AC-MAP-01), the touch semantics (§4, AC-MAP-02 /
// AC-MAP-03 / the release half of AC-MAP-07) and the AirWheel semantics
// (§5, AC-MAP-04) are fully implemented here — normalization, GAIN, sign,
// jump rejection + re-baseline, lift-off gating, report cadence,
// press-once/repeat-inert holds, release-by-silence, tap/doubletap clicks,
// the §6 button rows, and the wheel-notch conversion, sign, fractional
// accumulator and lift-off reset of the rotation (scroll) stream.
//
// The FULL §6 default mapping profile is implemented here since P3.15: the
// §6 table below is the one implementation table the spec requires (§7 "the
// table IS the implementation") — every (event, value) → HID action row of
// hid_mapping.md §6 lives in SkywriterHIDMapper.cpp's row lookup helpers
// (each row cited by line), and no second copy of the mapping exists. Rows
// that map an event to *nothing* by design are equally table rows:
// gesture code 1 (garbage), the reserved doubletap(east/west), and the
// control frames' "No HID output" (§2).

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
// east = right. (Used by the §6 touch-row helpers below.)
enum HIDButton : uint8_t {
  HID_BUTTON_LEFT = 0,
  HID_BUTTON_MIDDLE = 1,
  HID_BUTTON_RIGHT = 2,
};

// USB HID usage codes for the keyboard rows of §6 (Page Up / Page Down):
// Page Up = 0x4E (78), Page Down = 0x4F (79). (The §6 keyboard rows use
// these from the §6 table below.)
static const uint8_t HID_USAGE_PAGE_UP = 78;
static const uint8_t HID_USAGE_PAGE_DOWN = 79;

// USB HID usage codes for the consumer-control (media) rows of §6,
// decimal: Scan Next Track = 0x00B5 (181), Scan Previous Track =
// 0x00B6 (182), Volume Increment = 0x00E9 (233), Volume Decrement =
// 0x00EA (234). The flick/circle/media rows below map onto these.
static const uint16_t HID_USAGE_CONSUMER_NEXT_TRACK = 181;
static const uint16_t HID_USAGE_CONSUMER_PREV_TRACK = 182;
static const uint16_t HID_USAGE_CONSUMER_VOLUME_UP = 233;
static const uint16_t HID_USAGE_CONSUMER_VOLUME_DOWN = 234;

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
  // AC-BLE-04 even on the slowest host. The pace is also a runtime property
  // (set_report_interval_ms below): the firmware (P3.18) re-targets it at
  // the LIVE connection interval its host negotiated — the named constant
  // stays the initial value and the fallback, never a second copy of the
  // mapping. Deltas accumulate while held, so coalescing never drops
  // movement.
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
  // §5: one sensor AirWheel step (11.25 degrees of rotation, per the
  // datasheet's 32-steps-per-revolution counter, Interface.pdf Table 4-10)
  // maps to exactly one wheel notch. Datasheet-derived, NOT a tunable —
  // it is the sensor's own quantization, not a feel parameter.
  static const float AIRWHEEL_NOTCH_DEGREES;
  // §6 hold auto-scroll cadence (initial 100 ms): while touch(north) or
  // touch(south) is held, one wheel notch is emitted per this interval —
  // §6's own row timing ("wheel −1 notch per 100 ms while held"), cited
  // next to the row helper in the .cpp. Not a §7 tunable: the §7 tunable
  // list is fixed by the spec, and the hardware loop's P4.5 tuning only
  // records final values for the tunables it contains.
  static const unsigned long AUTO_SCROLL_INTERVAL_MS;

  explicit SkywriterHIDMapper(HIDMapperSink& sink) : sink_(sink) {
    // §3 rule 6: the pace starts at the spec's named constant
    // (REPORT_INTERVAL_MS); the firmware may re-target the live
    // connection interval at runtime (P3.18, set_report_interval_ms).
    report_interval_ms_ = REPORT_INTERVAL_MS;
  }

  // ---- canonical sensor event inputs (§2), all carrying arrival time ----

  // position(x, y, z) with PositionValid — raw 0..65535 sensor units.
  // z is deliberately unused by the default profile (§3 rule 5: reserved for
  // a future height-sensitivity feature).
  void onPosition(uint16_t x, uint16_t y, uint16_t z, unsigned long now_ms);

  // touch/tap/doubletap(zone) — §4 semantics (press-once/repeat-inert,
  // release-by-silence via tick(), tap/doubletap clicks) plus the full §6
  // touch-row table: touch(center) hold → left button, touch(north) hold →
  // auto-scroll up (wheel −1 per interval), touch(south) hold → auto-scroll
  // down (wheel +1 per interval), tap(center/east/west) → left/right/middle
  // clicks, tap(north) → keyboard Page Up, tap(south) → Page Down,
  // doubletap(center) → left ×2, doubletap(north/south) → media next /
  // previous track; doubletap(east/west) reserved → nothing.
  void onTouch(SensorZone zone, TouchKind kind, unsigned long now_ms);

  // gesture(code, class, edge) — only the code feeds the §6 table: the
  // horizontal flicks are track-skip media keys, the vertical flicks and
  // circles are volume keys, and garbage (code 1) maps to nothing (§6).
  // The class/edge attributes carry no row of their own.
  void onGesture(uint8_t code, unsigned long now_ms);

  // airwheel(degrees) — signed rotation delta of this frame (positive =
  // clockwise). §5 semantics (live since P3.14): converted to wheel notches
  // at AIRWHEEL_NOTCH_DEGREES per notch, AIRWHEEL_INVERT flips the sign,
  // fractional notches accumulate in wheel_acc_ so movement is never lost,
  // whole notches are emitted IMMEDIATELY (scroll is latency-sensitive —
  // deliberately not coalesced, unlike move reports), and the accumulator
  // resets on lift-off (tick()).
  void onAirwheel(float degrees, unsigned long now_ms);

  // ---- time ----

  // P3.18 (specs/ble_hid.md §7 / hid_mapping.md §3 rule 6): re-target the
  // move-report cadence at the LIVE BLE connection interval the host
  // negotiated. Section 7: move reports may be coalesced to the connection
  // interval (button/press transitions must never be coalesced away — the
  // click/press paths never route through this cadence), and the pointer
  // rate must stay ≥ 60 Hz (≤ 16.7 ms per report). The firmware records the
  // negotiated interval from the Bluetooth stack and passes it here; any
  // value below 1 ms is clamped to 1 ms (the engine reports in whole
  // milliseconds). The named REPORT_INTERVAL_MS constant is both the
  // initial and the disconnect-reset value. Movement is ALWAYS fully
  // accumulated in pending_dx_/dy_ before this cadence filters the
  // emission, so a faster or slower pace re-times the reports but never
  // drops or distorts the total movement (§3 rule 6's "never dropped").
  void set_report_interval_ms(unsigned long interval_ms);

  // The currently programmed move-report pace in ms (for tests / evidence).
  unsigned long report_interval_ms() const { return report_interval_ms_; }

  // Advance the clock without events (the firmware's idle-loop call); also
  // evaluates lift-off gating and releases a due coalesced move report.
  void tick(unsigned long now_ms);

  // Shutdown / final flush (the harness's finish hook): emits any still
  // pending accumulated movement immediately so nothing is lost.
  void finish(unsigned long now_ms);

  // BLE disconnect (specs/ble_hid.md §6, fix_plan item P3.17): the radio
  // link went down. Every held hold-row (buttons and auto-scroll) is
  // released immediately through the sink, un-sent pointer movement is
  // DROPPED (the §6 "Unconnected" row: sensor events are dropped, not
  // queued, so state approximating "now" must not replay on the new link),
  // the AirWheel accumulator clears (the lift-off reset of §5), and the
  // next valid position silently re-baselines (§3 rule 4 — the disconnect
  // is the lift-off of the wireless session). The firmware's disconnect
  // path calls this once per link loss; the sink may then go silent — a
  // release for a button the radio can no longer tell the host about is
  // still the correct *local* state, and the host-side residue is wiped by
  // the firmware's neutral resync report on (re)connect (AC-BLE-07).
  void disconnect(unsigned long now_ms);

 private:
  void attempt_report(unsigned long now_ms, bool force);
  // §4 explicit-release trigger (lift-off; the BLE life-cycle's public
  // disconnect() funnels through this): every held hold-row
  // (buttons and auto-scroll) goes up/clears immediately, in zone order.
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
  // §3 rule 6 / P3.18: the live move-report pace. Set in the constructor
  // below to the named REPORT_INTERVAL_MS constant; the firmware re-targets
  // it at the host's negotiated BLE connection interval
  // (set_report_interval_ms) and resets it to the constant in the
  // disconnect path. Delta accumulation is independent of this value —
  // only the emission moments move.
  unsigned long report_interval_ms_;

  // AirWheel state (§5, P3.14): fractional wheel notch carry-over. The
  // accumulator holds whole+fractional notches; the whole part is drained
  // on every airwheel event (immediate emission), the fraction carries to
  // the next event. Reset on lift-off (§5: "Accumulator resets on
  // lift-off") — in tick(), mirroring the touch release.
  float wheel_acc_ = 0.0f;

  // Touch state (§4): the sensor has no release event, so each zone tracks
  // its own press state. held_ is only ever set for zones whose §6 hold row
  // maps to something (center: a button; north/south: hold auto-scroll);
  // last_touch_ms_ is tracked for every zone so repeats refresh the recency
  // whatever the mapping says.
  static const int kZoneCount = 5;   // south, west, north, east, center
  bool held_[kZoneCount] = {};       // zone's hold row is currently engaged
  unsigned long last_touch_ms_[kZoneCount] = {};  // last touch frame seen
  // §6 auto-scroll cadence state: when the zone's hold row began emitting
  // (press time — the first notch is immediate), so tick() can pace one
  // notch per AUTO_SCROLL_INTERVAL_MS while the hold lasts.
  unsigned long last_autoscroll_ms_[kZoneCount] = {};
};

#endif  // SKYWRITER_HID_MAPPER_H
