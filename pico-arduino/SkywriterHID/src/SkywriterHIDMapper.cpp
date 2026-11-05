// SkywriterHIDMapper.cpp — the full sensor-event → HID mapping engine of
// specs/hid_mapping.md §3–§6 (P3.12 pointer model, P3.13 touch semantics,
// P3.14 AirWheel scroll, P3.15 the complete §6 default mapping profile).
// The §6 table lives in the row helpers below; see the header contract.

#include "SkywriterHIDMapper.h"

// §7: the tunables as named constants, in the one place.
const float SkywriterHIDMapper::GAIN = 1.0f / 256.0f;
const int SkywriterHIDMapper::JUMP_THRESHOLD = 8192;
const unsigned long SkywriterHIDMapper::LIFT_OFF_MS = 100;
const unsigned long SkywriterHIDMapper::REPORT_INTERVAL_MS = 15;
const unsigned long SkywriterHIDMapper::TOUCH_RELEASE_MS = 200;
const unsigned long SkywriterHIDMapper::TAP_CLICK_MS = 50;
const bool SkywriterHIDMapper::AIRWHEEL_INVERT = false;
const bool SkywriterHIDMapper::AIRWHEEL_ENABLED = true;
// §5: one 11.25° sensor step = one wheel notch (datasheet constant, see
// the header note — not a tunable feel parameter).
const float SkywriterHIDMapper::AIRWHEEL_NOTCH_DEGREES = 11.25f;

// §6: one wheel notch per AUTO_SCROLL_INTERVAL_MS while the hold lasts,
// row-cited in hold_action_for below.
const unsigned long SkywriterHIDMapper::AUTO_SCROLL_INTERVAL_MS = 100;

namespace {
// Deterministic round-half-away-from-zero: report deltas are whole cursor
// units, and everything after the point stays in the accumulator so
// movement is never lost (§3 rule 6 — deltas accumulate, never dropped).
inline long round_half_away(float v) {
  return v >= 0.0f ? static_cast<long>(v + 0.5f)
                   : static_cast<long>(v - 0.5f);
}

// ---- THE §6 DEFAULT MAPPING PROFILE (hid_mapping.md §6, fix item P3.15) --
//
// §7: "the mapping table of §6 IS the implementation; one static table
// mapping (event kind, value) → HID action". What follows is that one
// table, in row order, one lookup helper per event kind — no second copy
// exists anywhere (a config override only ever edits these rows).
//
// Touch rows: every TouchInfo (zone, kind) cell of the table.
//   hold:   center → left button; north → auto-scroll (wheel −1/interval);
//           south → auto-scroll (wheel +1/interval); west/east → no row
//           (recency is still tracked for §4 semantics).
//   tap:    center → left click; east → right click; west → middle click;
//           north → keyboard Page Up; south → keyboard Page Down.
//   dbltap: center → left double-click; north → media Scan Next Track;
//           south → media Scan Previous Track; east/west → reserved
//           → nothing (deliberate §6 row, not a gap).

// A hold row's action: button = a physical HID button held down (−1 none),
// wheel = the per-interval auto-scroll notch direction (0 none).
struct HoldAction {
  int button;  // HIDButton or −1
  int wheel;   // −1 / 0 / +1 notches per AUTO_SCROLL_INTERVAL_MS
};

constexpr int NO_BUTTON = -1;
constexpr int NO_SCROLL = 0;
constexpr int NOT_A_ROW = -1;
constexpr int NO_USAGE = -1;

HoldAction hold_action_for(SensorZone zone) {
  switch (zone) {
    case ZONE_CENTER:
      // §6 "touch(center) hold → Left button down/up (§4)".
      return {static_cast<int>(HID_BUTTON_LEFT), NO_SCROLL};
    case ZONE_NORTH:
      // §6 "touch(north) hold → Auto-scroll up: wheel −1 notch per 100 ms
      // while held" (the wheel sign is §6's own literal: north auto-scroll
      // emits NEGATIVE notches, distinct from §5's clockwise-positive
      // convention — the row is written as the spec's wheel delta).
      return {NO_BUTTON, -1};
    case ZONE_SOUTH:
      // §6 "touch(south) hold → Auto-scroll down: wheel +1 notch per 100 ms
      // while held".
      return {NO_BUTTON, +1};
    default:
      // No §6 hold row for west/east — §4 press/release state still tracked
      // by the engine so a future row or firmware override plugs in.
      return {NO_BUTTON, NO_SCROLL};
  }
}

// §6 tap rows: the mouse-click cells; −1 where the row is a keyboard row
// or none.
int tap_click_button_for(SensorZone zone) {
  switch (zone) {
    case ZONE_CENTER:
      // §6 "tap(center) → Left click".
      return static_cast<int>(HID_BUTTON_LEFT);
    case ZONE_EAST:
      // §6 "tap(east) → Right click".
      return static_cast<int>(HID_BUTTON_RIGHT);
    case ZONE_WEST:
      // §6 "tap(west) → Middle click".
      return static_cast<int>(HID_BUTTON_MIDDLE);
    default:
      return NOT_A_ROW;  // north/south → keyboard rows below; others none
  }
}

// §6 keyboard rows: "tap(north) → Keyboard Page Up",
// "tap(south) → Keyboard Page Down"; −1 where the row is a click or none.
int tap_key_usage_for(SensorZone zone) {
  switch (zone) {
    case ZONE_NORTH: return HID_USAGE_PAGE_UP;    // §6 row
    case ZONE_SOUTH: return HID_USAGE_PAGE_DOWN;  // §6 row
    default:         return NOT_A_ROW;
  }
}

// §6 doubletap rows — the click cell ("doubletap(center) → Double click"
// = two left clicks); −1 where the row is media or reserved- nothing.
int doubletap_click_button_for(SensorZone zone) {
  return zone == ZONE_CENTER
             ? static_cast<int>(HID_BUTTON_LEFT)  // §6 row
             : NOT_A_ROW;  // north/south → media rows below; east/west
                           // "doubletap(east)/doubletap(west) → nothing
                           // (reserved)"
}

// §6 doubletap rows — the media cells; −1 where the row is a click or the
// reserved do-nothing cells (east/west).
int doubletap_consumer_usage_for(SensorZone zone) {
  switch (zone) {
    case ZONE_SOUTH: return HID_USAGE_CONSUMER_PREV_TRACK;  // §6 row
    case ZONE_NORTH: return HID_USAGE_CONSUMER_NEXT_TRACK;  // §6 row
    default:         return NOT_A_ROW;
  }
}

// §6 gesture rows ("gesture(2 … flick W→E)" etc., read by Wire code):
//   code 2 → Scan Next Track, code 3 → Scan Previous Track,
//   code 4 → Volume Increment (repeats per event), code 5 → Volume Decrement,
//   code 6 → Volume Increment, code 7 → Volume Decrement (circle rows —
//   dormant on hardware while AirWheel is enabled, the sensor-constraint
//   note of §6; the mapper maps them whenever the sensor emits a circle
//   code, because §6 makes that a sensor constraint, not an implementation
//   choice), code 1 → garbage → *nothing*, and any unknown code → nothing.
int gesture_consumer_usage_for(uint8_t code) {
  switch (code) {
    case 2: return HID_USAGE_CONSUMER_NEXT_TRACK;   // flick W→E
    case 3: return HID_USAGE_CONSUMER_PREV_TRACK;   // flick E→W
    case 4: return HID_USAGE_CONSUMER_VOLUME_UP;    // flick S→N
    case 5: return HID_USAGE_CONSUMER_VOLUME_DOWN;  // flick N→S
    case 6: return HID_USAGE_CONSUMER_VOLUME_UP;    // circle CW
    case 7: return HID_USAGE_CONSUMER_VOLUME_DOWN;  // circle CCW
    default: return NO_USAGE;                       // garbage + unknowns
  }
}
}  // namespace

void SkywriterHIDMapper::onPosition(uint16_t x, uint16_t y, uint16_t /*z*/,
                                    unsigned long now_ms) {
  // z is unused by the default profile (§3 rule 5) — argument documented,
  // value ignored on purpose.
  last_position_ms_ = now_ms;

  if (!have_prev_) {
    // §3 rule 4: the first valid position (after start, after lift-off or
    // after a jump) silently becomes the baseline — no movement emitted.
    have_prev_ = true;
    prev_x_ = x;
    prev_y_ = y;
    return;
  }

  // §3 rule 2: deltas in raw units, then normalized by GAIN. Sink gets
  // whole units; the fractional remainder stays pending.
  int32_t dx_raw = static_cast<int32_t>(x) - static_cast<int32_t>(prev_x_);
  int32_t dy_raw = static_cast<int32_t>(y) - static_cast<int32_t>(prev_y_);
  prev_x_ = x;
  prev_y_ = y;

  if (dx_raw > JUMP_THRESHOLD || -dx_raw > JUMP_THRESHOLD ||
      dy_raw > JUMP_THRESHOLD || -dy_raw > JUMP_THRESHOLD) {
    // §3 rule 4: jump rejection — discard this delta, the new position
    // becomes the fresh baseline (prev_* already updated).
    return;
  }

  pending_dx_ += static_cast<float>(dx_raw) * GAIN;
  pending_dy_ += static_cast<float>(dy_raw) * GAIN;
  attempt_report(now_ms, false);
}

void SkywriterHIDMapper::onTouch(SensorZone zone, TouchKind kind,
                                  unsigned long now_ms) {
  if (kind == TOUCH_HOLD) {
    // §2: the touch bit repeats in every frame while the finger is on the
    // electrode. Track the recency for release-by-silence whatever the §6
    // mapping says (every zone, pressed or not).
    last_touch_ms_[zone] = now_ms;
    const HoldAction action = hold_action_for(zone);
    if (action.button < 0 && action.wheel == NO_SCROLL) {
      // No §6 hold row for this zone: nothing to engage; its §4 recency
      // was still tracked above.
      return;
    }
    if (held_[zone]) {
      return;  // §4: press-once — repeats do not re-trigger the engage
    }
    // §6 hold row: touch(center) → left button down (multi-button: each
    // zone has fully independent press state, §4); touch(north/south) →
    // hold auto-scroll begins. Deliberate engine decision (engine note,
    // recorded in the P3.15 ledger entry): the FIRST auto-scroll notch is
    // emitted immediately at hold start ("while held" reads as the hold
    // itself producing scrolls), then one notch per AUTO_SCROLL_INTERVAL_MS
    // from tick(). held_ records the engaged hold; the interval clock
    // starts at the press.
    held_[zone] = true;
    last_autoscroll_ms_[zone] = now_ms;
    if (action.button >= 0) {
      sink_.mouseButton(static_cast<uint8_t>(action.button), true);
    } else {
      sink_.mouseWheel(static_cast<int8_t>(action.wheel));
    }
    return;
  }

  // §4: tap(zone) → press + release of TAP_CLICK_MS; doubletap(zone) → two
  // of those clicks. The click is driven as one completed sink action, so
  // a tap/doubletap never leaves a button held and its press/release never
  // straddle a coalesced period. The §6 table's non-click cells dispatch
  // through their own report channel (tap(north/south) → keyboard, media
  // doubletap rows → consumer); rows mapped to *nothing* (doubletap
  // east/west reserved) fall through silently.
  const int button = kind == TOUCH_TAP ? tap_click_button_for(zone)
                                       : doubletap_click_button_for(zone);
  if (button >= 0) {
    sink_.mouseClick(static_cast<uint8_t>(button),
                     kind == TOUCH_DOUBLETAP ? 2 : 1);
    return;
  }
  const int usage = kind == TOUCH_TAP ? tap_key_usage_for(zone)
                                      : doubletap_consumer_usage_for(zone);
  if (usage >= 0) {
    if (kind == TOUCH_TAP) {
      sink_.keyboardPress(static_cast<uint8_t>(usage));  // §6 keyboard rows
    } else {
      sink_.consumerPress(static_cast<uint16_t>(usage));  // §6 media rows
    }
  }
}

void SkywriterHIDMapper::onGesture(uint8_t code, unsigned long now_ms) {
  // §6 gesture rows (fix item P3.15, target AC-MAP-05): one consumer-report
  // press per gesture event (the §6 "repeats per event" note — no repeat
  // limiting here, one event is one media action). The time argument is
  // unused: consumer presses are emitted immediately, un-coalesced, like
  // wheel deltas (§5's latency principle). garbage (code 1) is the §6
  // "gesture(1 … garbage) → nothing" row: an accepted-and-dropped event,
  // deliberately silent.
  (void)now_ms;
  const int usage = gesture_consumer_usage_for(code);
  if (usage >= 0) {
    sink_.consumerPress(static_cast<uint16_t>(usage));
  }
}

void SkywriterHIDMapper::onAirwheel(float degrees, unsigned long /*now_ms*/) {
  // §5 AirWheel semantics (fix item P3.14, target AC-MAP-04). The time
  // argument is unused: wheel deltas are emitted immediately, un-coalesced
  // (scroll feel is latency-sensitive), so no timer matters here — an
  // event's notches go straight to the sink.
  if (!AIRWHEEL_ENABLED) {
    // §6 note: with AirWheel disabled the sensor produces circle gestures
    // instead of counter data (hardware constraint, Interface.pdf
    // Table 4-10); the wheel rows are dormant by configuration.
    return;
  }

  // §5: whole step quantization. One sensor step (AIRWHEEL_NOTCH_DEGREES
  // of rotation, the counter's own resolution) = one wheel notch; positive
  // (clockwise) degrees scroll up. AIRWHEEL_INVERT is the configuration
  // override for the direction convention.
  float notches_f = degrees / AIRWHEEL_NOTCH_DEGREES;
  if (AIRWHEEL_INVERT) {
    notches_f = -notches_f;
  }

  // §5: fractional steps accumulate — fractional remainder stays in
  // wheel_acc_, the whole part goes out now. Truncation toward zero keeps
  // the remainder's sign with the accumulator (same never-lost principle
  // as the pointer's pending deltas).
  wheel_acc_ += notches_f;
  long notches = static_cast<long>(wheel_acc_);
  if (notches == 0) {
    return;  // less than one full notch: nothing a wheel report could say
  }
  wheel_acc_ -= static_cast<float>(notches);

  // The sink carries int8_t (the HID wheel field's own signed range —
  // realistic per-event deltas are ≤ 32 steps of the counter). Anything
  // beyond that range keeps accumulating and drains on later events, so
  // even absurd input loses nothing.
  if (notches > 127) notches = 127;
  if (notches < -128) notches = -128;
  sink_.mouseWheel(static_cast<int8_t>(notches));
}

void SkywriterHIDMapper::tick(unsigned long now_ms) {
  // §3 rule 5: lift-off gating. PositionValid is implicit in the event
  // stream (the driver only reports valid positions), so "invalid for more
  // than LIFT_OFF_MS" reads as a silence: no valid position within the
  // window pauses tracking. The next valid position re-baselines (rule 4).
  // AC-MAP-07's pointer-baseline reset is this.
  if (have_prev_ && now_ms - last_position_ms_ > LIFT_OFF_MS) {
    have_prev_ = false;
    // §5: the AirWheel accumulator resets on lift-off — a fractional
    // notch pending from the moment the hand left the field must not leak
    // into the next rotation gesture.
    wheel_acc_ = 0.0f;
    // §4 explicit-release trigger: the hand left the field, so every held
    // hold-row (button or auto-scroll) goes up/clears immediately
    // (whatever the touch silence says).
    release_all_buttons();
  }
  // §4 release is inferred: no touch frame for TOUCH_RELEASE_MS releases
  // the zone's engage. Each zone is independent, and an arriving touch
  // frame keeps refreshing its recency (onTouch) without re-engaging.
  for (int zone = 0; zone < kZoneCount; ++zone) {
    if (held_[zone] && now_ms - last_touch_ms_[zone] > TOUCH_RELEASE_MS) {
      held_[zone] = false;
      // §6: only the button hold rows carry an "up" transition; the
      // auto-scroll rows have no button state to release — the hold's
      // end IS the scrolling stopping (below).
      const HoldAction action =
          hold_action_for(static_cast<SensorZone>(zone));
      if (action.button >= 0) {
        sink_.mouseButton(static_cast<uint8_t>(action.button), false);
      }
    }
  }
  // §6 hold auto-scroll rows (fix item P3.15): while touch(north) or
  // touch(south) is held, one wheel notch per AUTO_SCROLL_INTERVAL_MS,
  // emitted immediately and un-coalesced (scroll feel is latency-sensitive,
  // the §5 emission principle). The interval clocks from the hold start
  // (onTouch), so notch #1 was already the press-time emission. Checked
  // after the release loop, so a hold released by silence on this very
  // tick never scrolls again. Both rows may engage at once (independent
  // zones, §4) — the deltas then alternate, §6 needs no arbitration.
  for (int zone = 0; zone < kZoneCount; ++zone) {
    const HoldAction action = hold_action_for(static_cast<SensorZone>(zone));
    if (held_[zone] && action.wheel != NO_SCROLL &&
        now_ms - last_autoscroll_ms_[zone] >= AUTO_SCROLL_INTERVAL_MS) {
      last_autoscroll_ms_[zone] = now_ms;
      sink_.mouseWheel(static_cast<int8_t>(action.wheel));
    }
  }
  attempt_report(now_ms, false);
}

void SkywriterHIDMapper::disconnect(unsigned long now_ms) {
  // specs/ble_hid.md §6, fix_plan item P3.17. The BLE link is gone; put the
  // engine into the "fresh session" state exactly as §6's Unconnected row
  // and §3 rule 4 demand:
  //   1. every held hold-row goes up through the sink right away — the
  //      up-transitions are legitimate protocol statements (a later button
  //      state is reported whole in every mouse report anyway, and a host
  //      that missed them is cleared by the firmware's neutral resync
  //      report on the next connect, AC-BLE-07);
  //   2. pointer movement that never got a report (pending_dx_/dy_) is
  //      DROPPED, not flushed — reports while unconnected are dropped and
  //      a reconnecting host must not see unsent movement from the old
  //      link replayed;
  //   3. the AirWheel accumulator clears (same rationale as §5's lift-off
  //      reset: a fractional notch pending from before the gap must not
  //      leak into the next rotation gesture);
  //   4. the next valid position silently re-baselines (have_prev_ = false,
  //      §3 rule 4 — the wireless-session equivalent of lift-off), so a
  //      hand tracked at a different spot after reconnect cannot produce
  //      one giant stale-delta cursor flight or trip jump rejection by
  //      accident.
  (void)now_ms;
  release_all_buttons();
  pending_dx_ = 0.0f;
  pending_dy_ = 0.0f;
  wheel_acc_ = 0.0f;
  have_prev_ = false;
}

void SkywriterHIDMapper::release_all_buttons() {
  for (int zone = 0; zone < kZoneCount; ++zone) {
    if (held_[zone]) {
      held_[zone] = false;
      // §6: releases broadcast only for the button hold rows; clearing an
      // auto-scroll hold is silent (its scroll cadence just stops — the
      // loop above is its only emission site).
      const HoldAction action =
          hold_action_for(static_cast<SensorZone>(zone));
      if (action.button >= 0) {
        sink_.mouseButton(static_cast<uint8_t>(action.button), false);
      }
    }
  }
}

void SkywriterHIDMapper::finish(unsigned long now_ms) {
  tick(now_ms);
  // Nothing must be lost at shutdown (§3 rule 6): flush regardless of the
  // interval.
  attempt_report(now_ms, true);
}

void SkywriterHIDMapper::attempt_report(unsigned long now_ms, bool force) {
  if (!force && now_ms - last_report_ms_ < REPORT_INTERVAL_MS) {
    return;  // §3 rule 6: at most one move report per connection interval
  }
  long dx = round_half_away(pending_dx_);
  long dy = round_half_away(pending_dy_);
  if (dx == 0 && dy == 0) {
    return;  // a zero report carries no information — drop, keep the clock
  }
  sink_.mouseMove(static_cast<int16_t>(dx), static_cast<int16_t>(dy));
  pending_dx_ -= static_cast<float>(dx);
  pending_dy_ -= static_cast<float>(dy);
  last_report_ms_ = now_ms;
}
