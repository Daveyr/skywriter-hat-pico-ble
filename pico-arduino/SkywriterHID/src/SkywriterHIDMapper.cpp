// SkywriterHIDMapper.cpp — the pointer model of specs/hid_mapping.md §3
// (fix item P3.12, target AC-MAP-01). See the header for the contract.

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

namespace {
// Deterministic round-half-away-from-zero: report deltas are whole cursor
// units, and everything after the point stays in the accumulator so
// movement is never lost (§3 rule 6 — deltas accumulate, never dropped).
inline long round_half_away(float v) {
  return v >= 0.0f ? static_cast<long>(v + 0.5f)
                   : static_cast<long>(v - 0.5f);
}

// §6 default mapping profile — the BUTTON rows (fix item P3.13):
//   touch(center) hold → left; tap(center) → left; doubletap(center) → left
//   double-click; tap(east) → right; tap(west) → middle.
// Deliberately absent here, owned by other fix items:
//   - touch(north/south) hold → auto-scroll (needs the §5 wheel; P3.15),
//   - tap(north/south) → keyboard Page Up/Down (P3.15),
//   - doubletap(east/west) → nothing, reserved by §6 (documented with P3.15).
// -1 = no button row for this zone/kind.
int button_for(SensorZone zone, TouchKind kind) {
  switch (kind) {
    case TOUCH_HOLD:
      return zone == ZONE_CENTER ? static_cast<int>(HID_BUTTON_LEFT) : -1;
    case TOUCH_TAP:
      switch (zone) {
        case ZONE_CENTER: return static_cast<int>(HID_BUTTON_LEFT);
        case ZONE_EAST:   return static_cast<int>(HID_BUTTON_RIGHT);
        case ZONE_WEST:   return static_cast<int>(HID_BUTTON_MIDDLE);
        default:          return -1;
      }
    case TOUCH_DOUBLETAP:
      return zone == ZONE_CENTER ? static_cast<int>(HID_BUTTON_LEFT) : -1;
  }
  return -1;
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
  const int button = button_for(zone, kind);

  if (kind == TOUCH_HOLD) {
    // §2: the touch bit repeats in every frame while the finger is on the
    // electrode. Track the recency for release-by-silence whatever the §6
    // mapping says (every zone, pressed or not).
    last_touch_ms_[zone] = now_ms;
    if (button < 0) {
      // No §6 holdbutton row for this zone: nothing to press (auto-scroll
      // lands with P3.15); its recency is still tracked above.
      return;
    }
    if (held_[zone]) {
      return;  // §4: press-once — repeats do not re-trigger the press
    }
    // §6: touch(center) hold → left button down (multi-button: each zone
    // has fully independent press state, §4).
    held_[zone] = true;
    sink_.mouseButton(static_cast<uint8_t>(button), true);
    return;
  }

  // §4: tap(zone) → press + release of TAP_CLICK_MS; doubletap(zone) → two
  // of those clicks. The click is driven as one completed sink action, so
  // a tap/doubletap never leaves a button held and its press/release never
  // straddle a coalesced period. Zones without a §6 row (doubletap
  // east/west reserved → nothing; tap(north/south) keyboard rows, P3.15)
  // fall through silently.
  if (button >= 0) {
    sink_.mouseClick(static_cast<uint8_t>(button),
                     kind == TOUCH_DOUBLETAP ? 2 : 1);
  }
}

void SkywriterHIDMapper::onGesture(uint8_t /*code*/, unsigned long /*now_ms*/) {
  // §6 gesture rows (media keys, volume) land with fix item P3.15 — the
  // garbage row (code 1 → nothing) and the reserved doubletap(east/west)
  // → nothing rows come with it.
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
    // button goes up immediately (whatever the touch silence says).
    release_all_buttons();
  }
  // §4 release is inferred: no touch frame for TOUCH_RELEASE_MS releases
  // the zone's held button. Each zone is independent, and an arriving
  // touch frame keeps refreshing its recency (onTouch) without pressing.
  for (int zone = 0; zone < kZoneCount; ++zone) {
    if (held_[zone] && now_ms - last_touch_ms_[zone] > TOUCH_RELEASE_MS) {
      held_[zone] = false;
      sink_.mouseButton(
          static_cast<uint8_t>(
              button_for(static_cast<SensorZone>(zone), TOUCH_HOLD)),
          false);
    }
  }
  attempt_report(now_ms, false);
}

void SkywriterHIDMapper::release_all_buttons() {
  for (int zone = 0; zone < kZoneCount; ++zone) {
    if (held_[zone]) {
      held_[zone] = false;
      sink_.mouseButton(
          static_cast<uint8_t>(
              button_for(static_cast<SensorZone>(zone), TOUCH_HOLD)),
          false);
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
