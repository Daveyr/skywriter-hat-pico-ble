'''Direct SkywriterHIDMapper unit tests for the §4 touch semantics
(fix_plan item P3.13) and the §5 AirWheel semantics (fix_plan item P3.14).

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

Spec: `specs/hid_mapping.md` §4 + §6 button rows, targets AC-MAP-02,
AC-MAP-03 and the release half of AC-MAP-07; the AirWheel section pins §5
(AC-MAP-04). Timing uses the engine's own
named constants (TOUCH_RELEASE_MS 200, TAP_CLICK_MS 50, LIFT_OFF_MS 100,
AIRWHEEL_NOTCH_DEGREES 11.25), so a hardware-tune change (P4.5)
auto-propagates into the arithmetic below
where it matters; scripts are written in terms of the threshold semantics,
not magic tick numbers, wherever possible.
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


def test_non_button_zones_produce_nothing():
    '''Zones whose §6 row is not a button emit nothing yet: touch(east/west)
    hold and doubletap(east/west) (reserved → nothing). tap(north/south)
    keys and the holds' auto-scroll land with P3.15 — deliberately not
    asserted silent here, so this file never goes stale against the spec.'''
    records = _run([
        ('TOUCH east hold', 0),
        ('TOUCH west doubletap', 5),
        ('TICK', 1000),
    ])
    assert records == [], records


# --------------------------------------------- airwheel (§5 / AC-MAP-04) ----
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
