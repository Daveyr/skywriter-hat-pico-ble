'''Direct SkywriterHIDMapper unit tests for the §4 touch semantics
(fix_plan item P3.13), the §5 AirWheel semantics (fix_plan item P3.14), the
§6 keyboard/media/hold-auto-scroll rows (fix_plan item P3.15) and the P3.18
live connection-interval report pacing.

Some timing behaviours cannot live in the fixture corpus: the Python driver
rate-limits repeat touch callbacks by design (default 4 Hz = one dispatch
per 250 ms per zone), so a scenario replaying touch frames closer together
than that would make the Python and Arduino decoders' canonical streams
diverge in a way the cross-driver parity machinery cannot honestly
attribute — the *corpus* touch scenarios therefore keep ≥ 250 ms gaps, and
the sub-250 ms behaviours (repeat-inert presses, exact release/lift-off
tick timing) are pinned here against the mapper alone. The mapper is the
exact source the firmware links (`pico-arduino/SkywriterHID`); the tests
drive it at call granularity through the host unit binary in
`tests/cpp/host_mapper_unit_main.cpp` (built with the same compiler
resolution as the replay adapters — g++/c++ → zig → ziglang wheel).

Spec: `specs/hid_mapping.md` §4 + §6 rows, targets AC-MAP-02, AC-MAP-03 and
the release half of AC-MAP-07; the AirWheel section pins §5 (AC-MAP-04);
the P3.15 section pins the tap(north/south) keyboard rows, the
doubletap(north/south) media rows, the reserved doubletap(east/west)
silence and the §6 hold auto-scroll cadence (AC-MAP-05/06's §6 side; the
gesture→consumer rows themselves are replay-asserted end-to-end through
the fixture scenarios, which the firmware chain serves). Timing uses the
engine's own named constants (TOUCH_RELEASE_MS 200, TAP_CLICK_MS 50,
LIFT_OFF_MS 100, AIRWHEEL_NOTCH_DEGREES 11.25, AUTO_SCROLL_INTERVAL_MS
100), so a hardware-tune change (P4.5) auto-propagates into the arithmetic
below where it matters; scripts are written in terms of the threshold
semantics, not magic tick numbers, wherever possible.
'''

import hashlib
import pathlib
import subprocess

from . import hid_grammar

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_ENGINE_DIR = _TEST_DIR.parent / 'pico-arduino' / 'SkywriterHID' / 'src'
_BUILD_DIR = _TEST_DIR / 'build'

_TIMEOUT_COMPILE = 300
_TIMEOUT_RUN = 30


def _run(script):
    '''Build (hash-cached) and run the mapper unit binary on a script.

    ``script`` is a list of (instruction, time) pairs — the pairs' times are
    the payload of one "instruction <ms>" line each. Returns the HID record
    dicts parsed from stdout (same shapes as the mapping adapter's).
    '''
    fingerprint = hashlib.sha256()
    for path in (_TEST_DIR / 'cpp' / 'host_mapper_unit_main.cpp',
                 _ENGINE_DIR / 'SkywriterHIDMapper.cpp',
                 _ENGINE_DIR / 'SkywriterHIDMapper.h'):
        fingerprint.update(path.read_bytes())
        fingerprint.update(b'\n')
    binary = _BUILD_DIR / ('mapper_unit-' + fingerprint.hexdigest()[:12])
    if not binary.exists():
        from .adapters_cpp import compiler_command
        _BUILD_DIR.mkdir(parents=True, exist_ok=True)
        cmd = compiler_command() + [
            '-I', str(_ENGINE_DIR),
            str(_TEST_DIR / 'cpp' / 'host_mapper_unit_main.cpp'),
            str(_ENGINE_DIR / 'SkywriterHIDMapper.cpp'),
            '-o', str(binary),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT_COMPILE)
        if proc.returncode != 0:
            raise RuntimeError(
                'failed to compile the mapper unit test binary:\n'
                f"$ {' '.join(cmd)}\n"
                + proc.stdout.decode(errors='replace')
                + proc.stderr.decode(errors='replace'))
    stdin = ''.join(f'{instruction} {time}\n' for instruction, time in script)
    proc = subprocess.run([str(binary)], input=stdin.encode('ascii'),
                          capture_output=True, timeout=_TIMEOUT_RUN)
    if proc.returncode != 0:
        raise RuntimeError(
            f'mapper unit binary crashed (rc={proc.returncode}):\n'
            + proc.stderr.decode(errors='replace'))
    return [line for line in proc.stdout.decode().splitlines() if line]


def _button(button, state):
    return f'HID BUTTON {button} {state}'


def _click(button, count):
    # click_ms is the engine's own TAP_CLICK_MS; the record asserts it too.
    return f'HID CLICK {button} {count} {hid_grammar.CLICK_MS}'


# ------------------------------------------------------- release timing ----

def test_first_touch_presses_exactly_once_and_release_by_silence():
    '''§4 press-once: the first touch frame presses; tick-only silence past
    TOUCH_RELEASE_MS releases exactly once (no double release).'''
    records = _run([
        ('TOUCH center hold', 0),
        # Silence with no touch frames; first tick strictly past the
        # threshold releases (200 ms window → release at 205 on the 5 ms grid).
        ('TICK', 200),
        ('TICK', 205),
        ('TICK', 500),
    ])
    assert records == [_button('left', 'down'), _button('left', 'up')], records


def test_repeat_touch_frames_do_not_re_press():
    '''§4 repeats do not re-trigger: touch frames arriving inside the release
    window refresh the recency only. (The corpus cannot carry this timing —
    see the module docstring.)'''
    records = _run([
        ('TOUCH center hold', 0),      # press
        ('TICK', 50),
        ('TOUCH center hold', 50),     # repeat → refresh only, no re-press
        ('TOUCH center hold', 100),    # repeat again — still no re-press
        ('TOUCH center hold', 195),    # last repeat inside the window
        ('TICK', 395),                 # 195 + 200 = silence exactly at edge
        ('TICK', 405),                 # strictly past → release
    ])
    assert records == [_button('left', 'down'), _button('left', 'up')], records


def test_releasing_by_silence_re_arms_a_later_touch():
    '''§4: after an inferred release, a new touch frame presses again (fresh
    acquisition) and its own silence releases it again.'''
    records = _run([
        ('TOUCH center hold', 0),      # press
        ('TICK', 205),                 # release by silence
        ('TOUCH center hold', 210),    # re-acquisition → press again
        ('TICK', 420),                 # release again
    ])
    assert records == [
        _button('left', 'down'),
        _button('left', 'up'),
        _button('left', 'down'),
        _button('left', 'up'),
    ], records


# ------------------------------------------------- lift-off (AC-MAP-07) ----

def test_lift_off_releases_held_button_immediately():
    '''§4 explicit release trigger: when the position stream goes silent for
    longer than LIFT_OFF_MS, a held button is released at that very tick —
    even though its own touch silence has not elapsed.'''
    records = _run([
        ('TOUCH center hold', 0),        # press
        ('POSITION 500 1000', 10),       # valid position (first → baseline)
        ('TICK', 50),                    # 40 ms of position silence: held
        ('TICK', 110),                   # exactly LIFT_OFF_MS: still held
        ('TICK', 115),                   # strictly past → lift-off release
        ('TOUCH center hold', 120),      # state was cleared → can re-press
    ])
    assert records == [
        _button('left', 'down'),
        _button('left', 'up'),
        _button('left', 'down'),
    ], records


def test_lift_off_without_prior_position_never_fires():
    '''The lift-off transition requires a previous valid position: with
    touch-only play the release is purely the touch-silence rule's job, and
    periodic touch repeats keep the button held for arbitrarily long.'''
    records = _run([
        ('TOUCH center hold', 0),      # press
        ('TICK', 100),
        ('TOUCH center hold', 105),    # keep the touch "fresh" (a held finger)
        ('TICK', 200),
        ('TOUCH center hold', 205),
        ('TICK', 300),                 # past LIFT_OFF_MS of overall playtime:
        ('TOUCH center hold', 305),    # no position ever seen → no lift-off
        # The last repeat's own silence has not elapsed at the finish.
        ('FIN', 310),
    ])
    assert records == [_button('left', 'down')], records

# ------------------------------------------- tap / doubletap (AC-MAP-03) ---


def test_tap_is_one_click_and_leaves_nothing_held():
    records = _run([
        ('TOUCH center tap', 0),
        ('TICK', 1000),                # nothing extra may appear afterwards
    ])
    assert records == [_click('left', 1)], records


def test_doubletap_is_two_clicks_and_leaves_nothing_held():
    records = _run([
        ('TOUCH center doubletap', 0),
        ('TICK', 1000),
    ])
    assert records == [_click('left', 2)], records


def test_tap_zone_button_mapping_per_section6():
    '''§6 rows: tap(east) → right, tap(west) → middle, tap(center) → left.'''
    records = _run([
        ('TOUCH center tap', 0),
        ('TOUCH east tap', 5),
        ('TOUCH west tap', 10),
    ])
    assert records == [
        _click('left', 1),
        _click('right', 1),
        _click('middle', 1),
    ], records


# -------------------------------------------- multi-zone state (§4/§6) ----

def test_zones_track_press_state_independently():
    '''§4 multi-button: each zone has independent press state. Only
    touch(center) has a §6 hold button (the east/west/north/south holds map
    to auto-scroll with P3.15), so independent release is asserted on the
    center hold while a west hold is simultaneously tracked.'''
    records = _run([
        ('TOUCH center hold', 0),       # left down
        ('TOUCH west hold', 5),         # no §6 hold button for west
        ('TICK', 210),                  # center released by its own silence
        ('TICK', 300),
    ])
    assert records == [_button('left', 'down'), _button('left', 'up')], records


def test_non_button_zones_produce_nothing_on_reserved_cells():
    '''§6 reserved/no-row cells emit nothing: touch(east)/touch(west) holds
    have no §6 hold row (recency-only, §4), and doubletap(east/west) are
    the reserved → *nothing* rows (P3.15: "deliberately unmapped to avoid
    accidental triggers").'''
    records = _run([
        ('TOUCH east hold', 0),
        ('TOUCH west doubletap', 5),
        ('TICK', 1000),
    ])
    assert records == [], records


# ------------------------------------ §6 tap/doubletap keyboard + media rows
# (fix_plan P3.15 — the rows the P3.13 engine deliberately left silent)

def _key(usage):
    return f'HID KEY {usage}'


def _consume(usage):
    return f'HID CONSUME {usage}'


def test_tap_north_south_are_page_up_page_down():
    '''§6 rows: tap(north) → keyboard Page Up, tap(south) → Page Down
    (usage 0x4E = 78 / 0x4F = 79, on the keyboard report — hid_grammar
    pins the usage↔key correspondence; _key carries the raw usage).'''
    records = _run([
        ('TOUCH north tap', 0),
        ('TOUCH south tap', 5),
        ('TICK', 1000),
    ])
    assert records == [
        _key(78),   # HID_USAGE_PAGE_UP
        _key(79),   # HID_USAGE_PAGE_DOWN
    ], records


def test_doubletap_north_south_are_media_track_skip():
    '''§6 rows: doubletap(north) → Consumer Scan Next Track (0x00B5 = 181),
    doubletap(south) → Scan Previous Track (0x00B6 = 182).'''
    records = _run([
        ('TOUCH north doubletap', 0),
        ('TOUCH south doubletap', 5),
        ('TICK', 1000),
    ])
    assert records == [
        _consume(181),   # HID_USAGE_CONSUMER_NEXT_TRACK
        _consume(182),   # HID_USAGE_CONSUMER_PREV_TRACK
    ], records


def test_reserved_doubletap_east_west_stay_silent():
    '''§6 reserved cells: doubletap(east) and doubletap(west) deliberately
    map to nothing (kept pinned beside the now-live rows so the remap to a
    real action cannot sneak in untested).'''
    records = _run([
        ('TOUCH east doubletap', 0),
        ('TOUCH west doubletap', 5),
        ('TICK', 1000),
    ])
    assert records == [], records


# ---------------------------------- §6 hold auto-scroll (touch north/south) —

def test_touch_north_hold_auto_scrolls_one_down_notch_per_interval():
    '''§6 "touch(north) hold → Auto-scroll up: wheel −1 notch per 100 ms
    while held". The wheel delta is §6's own literal −1 (the row is written
    as a wheel value, deliberately distinct from the §5 convention). The
    first notch fires at the hold start, then one per the interval.'''
    records = _run([
        ('TOUCH north hold', 0),    # hold starts: notch #1 immediately
        ('TICK', 95),
        ('TICK', 100),              # first interval due exactly at 100 (>=)
        ('TICK', 150),
        ('TOUCH north hold', 190),  # repeat frame: no re-scroll, no re-press
        ('TICK', 200),              # second interval at 200
        # The hold ends (silence > TOUCH_RELEASE_MS: release at 390+).
        ('TICK', 300),
        ('TICK', 405),              # strictly past 190+200 → released;
        ('TICK', 1000),             # no further notches ever
    ])
    assert records == [_wheel(-1), _wheel(-1), _wheel(-1), _wheel(-1)], records


def test_touch_south_hold_auto_scrolls_one_up_notch_per_interval():
    '''§6 "touch(south) hold → Auto-scroll down: wheel +1 notch per 100 ms
    while held" — the opposite-signed twin of the north row. Repeat touch
    frames keep the hold fresh past the release window.'''
    records = _run([
        ('TOUCH south hold', 0),    # hold starts: notch #1 immediately
        ('TICK', 100),              # interval due exactly at 100 (>=)
        ('TOUCH south hold', 105),  # repeat frame: refresh only
        ('TICK', 205),              # next interval due; hold not stale
        ('TOUCH south hold', 210),  # refresh again
        ('TICK', 315),              # interval due again (315−205 ≥ 100)
        ('TICK', 420),              # 420−210 = 210 > TOUCH_RELEASE_MS →
                                    # the hold releases; no notch after it
        ('TICK', 1000),
    ])
    assert records == [_wheel(1), _wheel(1), _wheel(1), _wheel(1)], records


def test_hold_auto_scroll_stops_after_release_by_silence():
    '''§6 "while held": the scrolling stops exactly with the hold's
    inferred release — a notch that becomes due on the very tick the hold
    is silence-released is suppressed (release is evaluated first), and
    the hold can be re-acquired for a fresh scroll session.'''
    records = _run([
        ('TOUCH north hold', 0),    # notch 1
        ('TICK', 205),              # > TOUCH_RELEASE_MS of silence → release;
                                    # the interval-due notch is suppressed
        ('TICK', 1000),             # nothing ever again
    ])
    assert records == [_wheel(-1)], records

    released_then_reheld = _run([
        ('TOUCH north hold', 0),    # notch 1
        ('TICK', 100),              # notch 2 (interval due)
        ('TICK', 205),              # > TOUCH_RELEASE_MS of silence → release
        ('TOUCH north hold', 210),  # re-acquisition: fresh session
        ('TICK', 310),              # its interval notch
    ])
    assert released_then_reheld == [
        _wheel(-1), _wheel(-1), _wheel(-1), _wheel(-1),
    ], released_then_reheld


def test_hold_auto_scroll_needs_the_hold_row_zones_only():
    '''The engine's §4 recency tracking does not scroll zones without a §6
    hold auto-scroll row: center (button hold) and east/west (rowless)
    produce no wheel output at any interval — center only shows its button
    press and its own later silence-release.'''
    records = _run([
        ('TOUCH center hold', 0),
        ('TOUCH east hold', 5),
        ('TOUCH west hold', 10),
        ('TICK', 115),              # any interval due: no scroll rows held
        ('TICK', 215),              # center released by its own silence
        ('TICK', 500),
    ])
    assert records == [
        _button('left', 'down'),
        _button('left', 'up'),
    ], records


def test_hold_auto_scroll_stops_on_lift_off():
    '''§6 hold auto-scroll rides on §4 hold state, so the lift-off
    explicit-release trigger (§4, AC-MAP-07) must end it: a notch that
    becomes due on the very tick lift-off fires is suppressed (the
    explicit trigger runs first), and only a re-engaged hold scrolls
    again.'''
    records = _run([
        ('POSITION 500 1000', 0),   # tracking starts (silent baseline)
        ('TOUCH north hold', 5),    # hold starts → immediate notch #1
        ('TICK', 105),              # interval due (105−5 ≥ 100) AND lift-off
                                    # fires (pos silent > LIFT_OFF_MS): both
                                    # on this tick — release wins, silent
        ('TICK', 205),              # due interval after lift-off: silent
        ('TOUCH north hold', 210),  # can re-engage after the release
        ('TICK', 310),              # its interval notch
    ])
    assert records == [_wheel(-1), _wheel(-1), _wheel(-1)], records


# ---------------------------------- §6 BLE disconnect (specs/ble_hid.md §6,
# fix_plan P3.17): the public disconnect() entry the firmware's link-loss
# path calls. The release half mirrors the lift-off trigger; the drop half
# (unsent movement, wheel accumulator) is what the firmware cannot do for
# the engine.

def test_disconnect_releases_held_button_and_re_enables_re_press():
    '''§6: on link loss the held hold-row goes up through the sink
    immediately (its own touch-silence window is irrelevant), the zone's
    engage state is cleared so the next connection can press again, and
    nothing is released twice.'''
    records = _run([
        ('TOUCH center hold', 0),        # press (left down)
        ('POSITION 500 1000', 5),        # tracking active (silent baseline)
        ('TICK', 50),                    # touch still fresh: held
        ('DISCONNECT', 60),              # link loss → release now
        ('TICK', 400),                   # long unconnected silence: no
                                         # duplicate release, no lift-off
                                         # residue
        ('TOUCH center hold', 410),      # after reconnect: can press again
    ])
    assert records == [
        _button('left', 'down'),
        _button('left', 'up'),
        _button('left', 'down'),
    ], records


def test_disconnect_ends_hold_auto_scroll():
    '''§6: the auto-scroll hold rows clear on disconnect like any other
    hold — the interval due at later ticks is silent, and a hold engaged
    after the (re)connect fires its fresh immediate notch again.'''
    records = _run([
        ('TOUCH north hold', 0),   # hold start → immediate notch #1
        ('DISCONNECT', 10),        # link loss → hold cleared
        ('TICK', 200),             # interval due: silent
        ('TOUCH north hold', 210), # after reconnect: fresh session
        ('TICK', 215),             # (its next interval notch is later)
    ])
    assert records == [_wheel(-1), _wheel(-1)], records


def test_disconnect_discards_unsent_pointer_movement():
    '''§6 "Unconnected: sensor events are dropped, not queued": pointer
    movement that never got a move report is DROPPED at disconnect, not
    flushed at the next connect — after reconnect the first real movement
    is measured from the fresh baseline alone, with no stale delta attached.
    (contrast: a flush here would fold the 2.45-unit stale pending into the
    fresh 4-unit move and emit `MOVE 6 6`.)'''
    records = _run([
        ('POSITION 500 1000', 0),    # tracking starts (silent baseline)
        ('POSITION 1128 1496', 10),  # +628/+496 raw × GAIN → 2.453/1.938
                                     # pending; inside the 15 ms report
                                     # interval → never reported
        ('DISCONNECT', 12),          # the pending movement dies here
        ('POSITION 400 600', 400),   # fresh session: silent re-baseline
        ('POSITION 1424 1624', 405), # fresh delta +1024 each = exactly 4.0
                                     # cursor units (more than the 15 ms
                                     # interval since the last report)
        ('FIN', 410),                # nothing else may flush afterwards
    ])
    assert records == ['HID MOVE 4 4'], records


def test_disconnect_rebaselines_position_like_lift_off():
    '''§3 rule 4 through the wireless life cycle: the first valid position
    after a disconnect silently becomes the baseline — no cursor flight
    measured across the gap, and jump rejection is not provoked by the
    reconnect (the position after reconnect may arrive at a completely
    different spot).'''
    records = _run([
        ('POSITION 500 1000', 0),      # active session, baseline set
        ('DISCONNECT', 10),            # link loss
        ('POSITION 10000 25000', 400), # reconnect: a wholly different spot
                                       # (raw delta > JUMP_THRESHOLD would
                                       # have been jump-dropped — instead
                                       # it must be a silent baseline)
        ('POSITION 10256 25256', 405), # then a small real move: +1,+1
        ('TICK', 500),
    ])
    assert records == ['HID MOVE 1 1'], records


def test_disconnect_clears_the_wheel_accumulator():
    '''§5's lift-off reset through the §6 life cycle: a fractional wheel
    notch pending from before a link loss must not leak into the rotation
    stream of the next session.'''
    records = _run([
        ('POSITION 500 1000', 0),  # tracking starts (silent baseline)
        ('AIRWHEEL 5.625', 5),     # half a notch pending
        ('DISCONNECT', 10),        # accumulator cleared
        ('AIRWHEEL 5.625', 400),   # fresh session: half a notch again
        ('TICK', 500),             # proves the two halves never combined
    ])
    assert records == [], records


# -------------------------------------------- airwheel (§5 / AC-MAP-04) ----
# The rotation deltas arrive per-frame from the driver already quantized to
# whole 11.25° steps (the counter's signed 8-bit difference × 11.25). These
# tests therefore pin the mapper side of the contract: notch conversion,
# sign, fractional accumulation, immediate emission and the lift-off reset
# — in half-notches where a fractional point has to be proved.

def _wheel(notches):
    return f'HID WHEEL {notches}'


def test_one_sensor_step_is_one_notch_up():
    '''§5: one 11.25° step = one wheel notch; clockwise (positive) =
    scroll up (away from the user).'''
    records = _run([
        ('AIRWHEEL 11.25', 0),
        ('TICK', 1000),
    ])
    assert records == [_wheel(1)], records


def test_counter_clockwise_scroll_is_negative_notches():
    '''§5 sign: counter-clockwise (negative) degrees = scroll down, i.e.
    negative wheel notches — 45° = four steps = −4 notches.'''
    records = _run([('AIRWHEEL -45', 0)])
    assert records == [_wheel(-4)], records


def test_full_quarter_turn_emits_all_its_notches_at_once():
    '''§5: a +90° delta (8 steps, `airwheel_quarter_turn_cw`'s event shape)
    goes out as ONE wheel report of 8 notches, not eight separate ones.'''
    records = _run([('AIRWHEEL 90', 0)])
    assert records == [_wheel(8)], records


def test_fractional_notches_accumulate_until_a_whole_notch():
    '''§5: fractional steps accumulate — a half-notch delta reports nothing,
    and the next half completes the notch (exactly one report total).'''
    records = _run([
        ('AIRWHEEL 5.625', 0),   # half a notch: pending, no wheel report
        ('TICK', 100),           # (also proves pending ≠ emitted late by tick)
        ('AIRWHEEL 5.625', 105), # completes the notch: exactly one report
        ('TICK', 1000),
    ])
    assert records == [_wheel(1)], records


def test_fraction_remainder_survives_across_events():
    '''§5 never-lost principle: 16.875° = 1.5 notches emits the whole part
    (1) immediately and keeps 0.5 pending; a further half-notch completes
    the second full notch. The 22.5° total is exactly two notches.'''
    records = _run([
        ('AIRWHEEL 16.875', 0),  # 1.5 notches → WHEEL 1, remainder 0.5
        ('AIRWHEEL 5.625', 5),   # +0.5 → completes the second notch
        ('TICK', 1000),
    ])
    assert records == [_wheel(1), _wheel(1)], records


def test_wheel_deltas_are_emitted_immediately_not_coalesced():
    '''§5: wheel deltas are emitted immediately (scroll feel is
    latency-sensitive — deliberately NOT coalesced like move reports): two
    deltas arriving INSIDE one move-report interval (REPORT_INTERVAL_MS)
    still produce two wheel reports.'''
    records = _run([
        ('AIRWHEEL 11.25', 0),
        ('AIRWHEEL 11.25', 2),   # 2 ms < REPORT_INTERVAL_MS (15 ms)
    ])
    assert records == [_wheel(1), _wheel(1)], records


def test_lift_off_resets_the_wheel_accumulator():
    '''§5: the accumulator resets on lift-off, so no pending fraction leaks
    into the next rotation gesture. Contrast pair: the same two half-notch
    deltas combine into one notch when no lift-off ever happens (no
    position seen — §3 rule 5's lift-off needs a prior valid position).'''
    after_lift_off = _run([
        ('POSITION 500 1000', 0),   # tracking starts (silent baseline)
        ('AIRWHEEL 5.625', 5),      # half a notch pending
        ('TICK', 120),              # > LIFT_OFF_MS past the position → lift-off
        ('AIRWHEEL 5.625', 125),    # fresh accumulator: half a notch again
        ('TICK', 400),              # proves the two halves never combined
    ])
    assert after_lift_off == [], after_lift_off

    without_lift_off = _run([
        ('AIRWHEEL 5.625', 0),   # no position ever → no lift-off transition
        ('AIRWHEEL 5.625', 5),   # → the two halves combine into one notch
        ('TICK', 400),
    ])
    assert without_lift_off == [_wheel(1)], without_lift_off


# ------------------------------------------- P3.18: live connection pace ---
# (specs/ble_hid.md §7 "Report coalescing" / hid_mapping.md §3 rule 6: move
# reports may be coalesced to the connection interval — the firmware
# re-targets the engine's cadence at the *negotiated* interval, P3.18.)
#
# Timeline arithmetic (GAIN = 1/256, so +256 raw = +1.0 cursor unit per
# frame): positions every 5 ms, right after a fresh baseline. The engine
# initialises last_report_ms_ = 0, so the first attempt that is
# `>= pace` past t=0 drains; afterwards the clock is the last report's.
# Every test also recomputes the §3 rule 6 conservation property: the sum
# of reported deltas equals exactly the number of position frames times
# 1 unit — coalescing re-times, never drops.

_PACE_FRAMES = [
    # baseline (silent, sets prev), then +1 cursor unit every 5 ms
    ('POSITION 100 100', 0),
    ('POSITION 356 100', 5),
    ('POSITION 612 100', 10),
    ('POSITION 868 100', 15),
    ('POSITION 1124 100', 20),
]


def test_pace_faster_than_default_emits_sooner_movement_conserved():
    '''A tight live interval (e.g. the LE minimum 7.5 ms → 8 ms pace) lets
    the already-accumulated movement out at every interval boundary instead
    of the 15 ms default — total movement is exactly conserved.'''
    script = [('PACE 8', 1)] + _PACE_FRAMES + [('TICK', 22)]
    records = [r for r in _run(script) if r.startswith('HID ')]
    # t=5:  5 − 0 < 8  → pending 1
    # t=10: 10 − 0 >= 8 → MOVE 2; last = 10
    # t=15: 15 − 10 = 5 < 8 → pending 1
    # t=20: 20 − 10 = 10 >= 8 → MOVE 2 (pending 1 + 1)
    assert records == ['HID MOVE 2 0', 'HID MOVE 2 0'], records
    assert sum(int(r.split()[2]) for r in records) == 4, records  # 4 frames


def test_pace_slower_than_default_coalesces_more_movement_conserved():
    '''A slow live interval (e.g. a 30 ms host policy) further coalesces the
    movement into one report — again without dropping anything (the
    deltas accumulate across the longer silence, §3 rule 6).'''
    script = [('PACE 30', 1)] + _PACE_FRAMES + [('TICK', 31)]
    records = [r for r in _run(script) if r.startswith('HID ')]
    # nothing fires inside the 21 ms of frames (all < 30 past t=0); the
    # t=31 tick drains all four accumulated units at once.
    assert records == ['HID MOVE 4 0'], records


def test_pace_change_never_loses_pending_movement():
    '''Changing the pace with movement pending leaves the accumulator
    untouched: the movement goes out on the next admissible attempt, same
    total as with a single pace all along.'''
    script = [
        ('POSITION 100 100', 0),
        ('POSITION 356 100', 5),   # pending 1 (5 < 15, still on the default)
        # mid-stream pace change — tightens like a host re-negotiating the
        # connection interval during a gesture
        ('PACE 8', 6),
        ('POSITION 612 100', 11),  # 11 − 0 >= 8 → MOVE 2
        ('POSITION 868 100', 16),  # 16 − 11 = 5 < 8 → pending 1
        ('TICK', 19),              # 19 − 11 = 8 → MOVE 1
    ]
    records = [r for r in _run(script) if r.startswith('HID ')]
    assert records == [('HID MOVE 2 0'), ('HID MOVE 1 0')], records


def test_sub_millisecond_pace_is_clamped_to_one_ms():
    '''set_report_interval_ms clamps values below 1 ms to 1 ms (the
    engine's cadence is whole milliseconds; no real LE interval is
    sub-millisecond). The applied value is returned as the PACE record.'''
    records = _run([('PACE 0', 0)])
    assert records == ['PACE 1'], records

    records = _run([('PACE 7', 0)])
    assert records == ['PACE 7'], records
