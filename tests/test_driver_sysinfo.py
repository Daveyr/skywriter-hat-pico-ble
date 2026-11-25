'''The Arduino driver must surface the sensor's own health byte and its
AirWheel validity state publicly (fix_plan item P3.29).

In plain language: the sensor attaches a one-byte status report to every
data frame it sends — the SystemInfo byte (Interface.pdf §4.5 Table 4-10).
Besides the "this field is valid" bits it carries two HEALTH bits the
sensor fills in by itself: bit 4 = EnvironmentalNoise ("environmental
noise has been detected") and bit 5 = Clipping ("the ADCs are clipping").
Neither driver surfaced this byte before P3.29 — and the 2026-11-25
acceptance session's leading open question is exactly whether the sensor
is deaf to hover-range motion for a reason it might be reporting itself
(fix_plan P4.0 hypothesis (g)). The firmware's health line and per-event
evidence trace print this byte and its two decoded health bits from the
driver's public state `last_sysinfo`; the same item makes the AirWheel
validity flag and the raw free-running rotation counter public
(`airwheel_valid` / `airwheel_counter` — renamed from the private
`airwheel_counter_valid` / `lastrotation` so the evidence line can print
"was AirWheel valid at this event, and what did the counter say").

Test method: the real driver is compiled for the host behind the tests/cpp
shims (as in the replay harness) and driven through its genuine poll()
with crafted 26-byte sensor-data frames:

- a frame whose SystemInfo byte carries ONLY the two health bits (0x30 =
  noise + clipping) and whose output mask enables no field: nothing
  dispatches, but `last_sysinfo` must still equal 0x30 — the health report
  survives even when no payload field is valid;
- an AirWheel-valid frame establishes the baseline SILENTLY (the P3.4/P3.9
  rule) and sets `airwheel_valid` = 1 with the raw counter; a second valid
  frame with the counter advanced by 2 emits the +22.50-degree event and
  updates the counter; a frame without valid AirWheel data clears
  `airwheel_valid` (re-baseline on the next valid frame);
- a position-valid frame (SystemInfo bit 0) dispatches its move event and
  `last_sysinfo` reflects THAT frame's byte.

This test FAILED against the pre-P3.29 code: `last_sysinfo` /
`airwheel_valid` / `airwheel_counter` did not exist (the host program
could not even compile) — the sensor's health bits were discarded in
`handle_sensor_data` and the AirWheel validity state was private.
'''

import hashlib
import pathlib
import subprocess

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_CPP_DIR = _TEST_DIR / 'cpp'
_REPO_ROOT = _TEST_DIR.parents[0]
_DRIVER_DIR = _REPO_ROOT / 'arduino' / 'Skywriter'
_BUILD_DIR = _TEST_DIR / 'build'

_TIMEOUT_COMPILE = 300
_TIMEOUT_RUN = 30

_SOURCES = (_CPP_DIR / 'arduino_shim.cpp',
            _CPP_DIR / 'host_sysinfo_main.cpp',
            _DRIVER_DIR / 'skywriter.cpp')


def _run(script):
    '''Compile (hash-cached) and run the sysinfo host binary.

    Returns (events, states): the EV lines' token lists and the parsed
    STATE dicts, in order.'''
    fingerprint = hashlib.sha256()
    for path in _SOURCES + (_CPP_DIR / 'Arduino.h',
                            _CPP_DIR / 'Wire.h',
                            _DRIVER_DIR / 'skywriter.h'):
        fingerprint.update(path.read_bytes())
    binary = _BUILD_DIR / ('sysinfo-' + fingerprint.hexdigest()[:12])
    if not binary.exists():
        from .adapters_cpp import compiler_command
        _BUILD_DIR.mkdir(parents=True, exist_ok=True)
        cmd = compiler_command() + [
            '-I', str(_CPP_DIR),      # the shims shadow the real headers
            '-I', str(_DRIVER_DIR),   # "skywriter.h"
        ] + [str(src) for src in _SOURCES] + ['-o', str(binary)]
        proc = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT_COMPILE)
        if proc.returncode != 0:
            raise RuntimeError(
                'failed to compile the sysinfo host binary:\n'
                f"$ {' '.join(cmd)}\n"
                + proc.stdout.decode(errors='replace')
                + proc.stderr.decode(errors='replace'))
    stdin = ''.join(instruction + '\n' for instruction in script)
    proc = subprocess.run([str(binary)], input=stdin.encode('ascii'),
                          capture_output=True, timeout=_TIMEOUT_RUN)
    if proc.returncode != 0:
        raise RuntimeError(
            f'sysinfo host binary crashed (rc={proc.returncode}):\n'
            + proc.stderr.decode(errors='replace'))
    events, states = [], []
    for out_line in proc.stdout.decode().splitlines():
        if out_line.startswith('EV '):
            events.append(out_line.split())
        elif out_line.startswith('STATE '):
            fields = dict(part.split('=') for part in out_line.split()[1:])
            states.append({'sysinfo': int(fields['sysinfo']),
                           'aw_valid': int(fields['aw_valid']),
                           'aw_cnt': int(fields['aw_cnt'])})
    return events, states


def _frame(mask, sysinfo, airwheel=0x00, x=0, y=0, z=0):
    '''A 26-byte sensor-data frame (the classic full layout): Size, Flags,
    Sequence, identity 0x91, then the payload — DataOutputConfigMask (2
    bytes LE), TimeStamp, SystemInfo, DSPStatus (2), GestureInfo (4),
    TouchInfo (4), AirWheelInfo (2), XYZ (6).'''
    payload = bytearray(22)
    payload[0:2] = mask.to_bytes(2, 'little')
    payload[2] = 0x5D                    # TimeStamp (any value)
    payload[3] = sysinfo
    payload[14] = airwheel & 0xFF        # AirWheelInfo byte 0: the counter
    payload[16:18] = x.to_bytes(2, 'little')
    payload[18:20] = y.to_bytes(2, 'little')
    payload[20:22] = z.to_bytes(2, 'little')
    return bytes([0x1A, 0x08, 0x01, 0x91]) + bytes(payload)


NOISE_AND_CLIPPING = 0x10 | 0x20     # bit 4 EnvironmentalNoise, bit 5 Clipping
DSP_RUNNING = 0x80                   # bit 7
POSITION_VALID = 0x01                # bit 0
AIRWHEEL_VALID = 0x02                # bit 1


def test_health_bits_surface_even_when_nothing_dispatches():
    '''A frame whose SystemInfo byte carries the two health bits (noise +
    clipping) and whose output mask enables NO field must still leave
    `last_sysinfo` = 0x30: the sensor's own health report survives even
    when no payload field is valid — this is the reading the hover-deafness
    investigation (P4.0 hypothesis (g)) needs.'''
    events, states = _run(['FRAME ' + _frame(0x0000, NOISE_AND_CLIPPING).hex(),
                           'STATE'])
    assert events == [], 'a mask-0 frame dispatches nothing'
    assert states == [{'sysinfo': NOISE_AND_CLIPPING, 'aw_valid': 0,
                       'aw_cnt': 0}], states


def test_last_sysinfo_tracks_every_decoded_frame():
    '''`last_sysinfo` is per-frame state (like `last_gesture`): the latest
    decoded sensor-data frame's byte always wins, including through a
    frame that dispatches events.'''
    events, states = _run([
        'FRAME ' + _frame(0x0000, NOISE_AND_CLIPPING).hex(),
        'FRAME ' + _frame(0x0010, POSITION_VALID | DSP_RUNNING,
                          x=0x0102, y=0x0304, z=0x0506).hex(),
        'STATE'])
    # x/y/z decode little-endian: 0x0102 = 258, 0x0304 = 772, 0x0506 = 1286.
    assert events == ['EV MOVE 258 772 1286'.split()], events
    assert len(states) == 1 and states[0]['sysinfo'] == POSITION_VALID | \
        DSP_RUNNING, states


def test_airwheel_state_is_public_and_follows_validity():
    '''The AirWheel validity flag + raw counter are public state now:
    the first valid frame baselines SILENTLY with `airwheel_valid` = 1 and
    the raw counter, a second valid frame with the counter advanced by 2
    emits +22.50 degrees (2 × 11.25) and updates the counter, and a frame
    without valid AirWheel data clears the flag (re-baseline on the next
    valid frame — the Python driver's `_lastrotation = None` rule).'''
    events, states = _run([
        # Baseline frame: AirWheel valid (mask bit 3, SystemInfo bit 1),
        # counter 0x80 — silent, no event.
        'FRAME ' + _frame(0x0008, AIRWHEEL_VALID, airwheel=0x80).hex(),
        'STATE',
        # Second valid frame, counter +2 steps.
        'FRAME ' + _frame(0x0008, AIRWHEEL_VALID, airwheel=0x82).hex(),
        'STATE',
        # AirWheel invalid again (SystemInfo bit 1 clear): the flag clears.
        'FRAME ' + _frame(0x0000, DSP_RUNNING).hex(),
        'STATE'])
    assert events == ['EV AIRWHEEL 22.50'.split()], events
    assert len(states) == 3
    assert states[0] == {'sysinfo': AIRWHEEL_VALID, 'aw_valid': 1,
                         'aw_cnt': 0x80}, states[0]
    assert states[1] == {'sysinfo': AIRWHEEL_VALID, 'aw_valid': 1,
                         'aw_cnt': 0x82}, states[1]
    assert states[2] == {'sysinfo': DSP_RUNNING, 'aw_valid': 0,
                         'aw_cnt': 0x82}, states[2]
