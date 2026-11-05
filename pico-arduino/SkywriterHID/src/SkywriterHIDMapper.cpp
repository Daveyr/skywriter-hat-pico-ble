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

namespace {
// Deterministic round-half-away-from-zero: report deltas are whole cursor
// units, and everything after the point stays in the accumulator so
// movement is never lost (§3 rule 6 — deltas accumulate, never dropped).
inline long round_half_away(float v) {
  return v >= 0.0f ? static_cast<long>(v + 0.5f)
                   : static_cast<long>(v - 0.5f);
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

void SkywriterHIDMapper::onTouch(SensorZone /*zone*/, TouchKind /*kind*/,
                                 unsigned long /*now_ms*/) {
  // §4 semantics (press-once/repeat-inert, release after TOUCH_RELEASE_MS,
  // tap/doubletap clicks) land with fix item P3.13 — event accepted, no
  // output yet. §6's button/auto-scroll rows map from the same input.
}

void SkywriterHIDMapper::onGesture(uint8_t /*code*/, unsigned long /*now_ms*/) {
  // §6 gesture rows (media keys, volume) land with fix item P3.15 — the
  // garbage row (code 1 → nothing) and the reserved doubletap(east/west)
  // → nothing rows come with it.
}

void SkywriterHIDMapper::onAirwheel(float /*degrees*/,
                                    unsigned long /*now_ms*/) {
  // §5 semantics (one 11.25° step = one wheel notch, sign, accumulator,
  // lift-off reset) land with fix item P3.14.
}

void SkywriterHIDMapper::tick(unsigned long now_ms) {
  // §3 rule 5: lift-off gating. PositionValid is implicit in the event
  // stream (the driver only reports valid positions), so "invalid for more
  // than LIFT_OFF_MS" reads as a silence: no valid position within the
  // window pauses tracking. The next valid position re-baselines (rule 4),
  // and lift-off also releases held buttons (§4) — that half lands with
  // P3.13. AC-MAP-07's pointer-baseline reset is this.
  if (have_prev_ && now_ms - last_position_ms_ > LIFT_OFF_MS) {
    have_prev_ = false;
  }
  attempt_report(now_ms, false);
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
