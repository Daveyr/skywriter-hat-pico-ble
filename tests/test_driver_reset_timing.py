'''The Arduino driver's begin() must use the reference sensor-reset timing
(fix_plan item P3.26, part 2).

In plain language: the gesture sensor is woken by a pulse on its reset
wire — the line is pulled LOW (the chip held asleep), then released, and
the chip needs time to be fully awake before the first command over the
I2C (Inter-Integrated Circuit — the two-wire bus between the Pico and the
sensor) bus can be acknowledged. The Raspberry Pi Python driver — the
project's reference implementation — holds the line LOW for 100 ms and
waits 500 ms after release (its comment cites the datasheet's 200 ms boot
delay "plus change"). The Arduino driver held 10 ms and waited 50 ms —
both under the datasheet's own boot-delay figure, which left cold-boot
acknowledgments to chance: hardware session 5's F12 captures show cold
boots failing the first (and separately the second) sensor configuration
command, and the old boot gate turned that into an invisible device.

Test method: the real driver is compiled for the host behind the tests/cpp
shims and its genuine begin() is called once; the shims record every GPIO
and delay call in order. The sequence must be: transfer pin as input with
pull-up, reset pin as output, reset LOW, delay 100 ms, reset HIGH, delay
500 ms. This test FAILED against the pre-P3.26 code (delays 10 and 50).
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
            _CPP_DIR / 'host_reset_timing_main.cpp',
            _DRIVER_DIR / 'skywriter.cpp')

# Pin numbers exactly as the host driver programs use them (the decoder
# adapter's constants): transfer (TS) pin 27, reset pin 17.
XFER_PIN = 27
RESET_PIN = 17
MODE_INPUT_PULLUP = 2  # Arduino INPUT_PULLUP
MODE_OUTPUT = 1        # Arduino OUTPUT

# The reference timing, from the Python driver's reset()
# (library/skywriter/__init__.py — "Datasheet delay of 200ms plus change").
RESET_HOLD_MS = 100
RESET_SETTLE_MS = 500


def _run():
    '''Compile (hash-cached) and run the reset-timing host binary, returning
    the recorded events as tuples: ('MODE', pin, mode), ('WRITE', pin, value)
    or ('DELAY', ms).'''
    fingerprint = hashlib.sha256()
    for path in _SOURCES + (_CPP_DIR / 'Arduino.h',
                            _CPP_DIR / 'Wire.h',
                            _DRIVER_DIR / 'skywriter.h'):
        fingerprint.update(path.read_bytes())
    binary = _BUILD_DIR / ('reset_timing-' + fingerprint.hexdigest()[:12])
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
                'failed to compile the reset-timing host binary:\n'
                f"$ {' '.join(cmd)}\n"
                + proc.stdout.decode(errors='replace')
                + proc.stderr.decode(errors='replace'))
    proc = subprocess.run([str(binary)], capture_output=True,
                          timeout=_TIMEOUT_RUN)
    if proc.returncode != 0:
        raise RuntimeError(
            f'reset-timing host binary crashed (rc={proc.returncode}):\n'
            + proc.stderr.decode(errors='replace'))
    events = []
    for line in proc.stdout.decode().splitlines():
        parts = line.split()
        if parts[0] == 'DELAY':
            events.append(('DELAY', int(parts[1])))
        else:
            events.append((parts[0], int(parts[1]), int(parts[2])))
    return events


def test_begin_uses_the_reference_reset_timing():
    '''begin()'s reset pulse is the Python driver's reset() timing: the
    reset wire held LOW 100 ms, then released and given 500 ms to settle —
    never the old 10 ms / 50 ms that left cold-boot acknowledgments to
    chance (F12).'''
    events = _run()
    expected = [
        ('MODE', XFER_PIN, MODE_INPUT_PULLUP),
        ('MODE', RESET_PIN, MODE_OUTPUT),
        ('WRITE', RESET_PIN, 0),                  # reset asserted (LOW)
        ('DELAY', RESET_HOLD_MS),                 # the 100 ms hold
        ('WRITE', RESET_PIN, 1),                  # reset released (HIGH)
        ('DELAY', RESET_SETTLE_MS),               # the 500 ms settle
    ]
    assert events == expected, (
        f'begin() must reset the sensor with the reference timing '
        f'{expected}, got: {events}')


def test_the_old_short_reset_timing_is_gone():
    '''The 10 ms hold / 50 ms settle numbers must not survive anywhere in
    begin()'s recorded delays — a partial fix (one number changed) would
    still leave cold boots to chance.'''
    events = _run()
    delays = [e[1] for e in events if e[0] == 'DELAY']
    assert 10 not in delays and 50 not in delays, (
        f'the old reset timing (10 ms hold / 50 ms settle) must be gone, '
        f'delays recorded: {delays}')
