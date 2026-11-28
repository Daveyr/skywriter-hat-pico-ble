'''The Arduino driver must release the sensor's transfer line on EVERY
poll() exit path (fix_plan item P3.23).

In plain language: the sensor signals "new data is waiting" by pulling its
transfer-request pin (TS / TRFR) low; the driver answers by holding that line
low itself while it clocks the data through the I2C (Inter-Integrated
Circuit — the two-wire bus between the Pico and the sensor) bus, and must let
go of the line afterwards so the sensor's data buffers unlock for the next
cycle. The Raspberry Pi Python driver had exactly this defect class and got
the fix in P3.11d (release moved into a try/finally); the Arduino driver's
poll() still took an early `return` when a read produced fewer than the
4 header bytes — leaving the line held LOW forever. With TS pinned low the
sensor's buffers stay locked, no new data ever arrives, and the controller
looks alive (Bluetooth up, serial quiet) while producing no input at all —
the leading candidate behind hardware session 3's total input loss
(fix_plan P4.0a, hypothesis H1).

The second half of the fix (hypothesis H2, reopening the P3.19 pin-mode
decision): the release must also RESTORE the pin's internal pull-up — the
Python driver's release sets the pull-up (library/skywriter/__init__.py,
`GPIO.setup(..., GPIO.IN, pull_up_down=GPIO.PUD_UP)`) — so a loose or
disconnected TS wire reads consistently high instead of at random (a random
low read would trigger the very failed-read path above).

Test method: the real driver is compiled for the host behind the tests/cpp
shims (as in the replay harness), driven through its genuine poll() on both
paths — a normal frame and an empty (failed) read — and every GPIO call is
recorded by the shims (tests/cpp/Arduino.h). Each poll must END with the
release pair: the line driven high one last time, then the pin left as an
input WITH the pull-up. This test FAILED against the pre-P3.23 code (the
failed-read path returned without any release call) and must stay green.
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
            _CPP_DIR / 'host_pin_release_main.cpp',
            _DRIVER_DIR / 'skywriter.cpp')

# Pin numbers exactly as the host driver programs use them (the decoder
# adapter's constants): transfer (TS) pin 27, reset pin 17.
XFER_PIN = 27
MODE_INPUT_PULLUP = 2  # Arduino INPUT_PULLUP
WRITE = 'WRITE'
MODE = 'MODE'


def _run(script):
    '''Compile (hash-cached) and run the pin-release host binary.'''
    fingerprint = hashlib.sha256()
    for path in _SOURCES + (_CPP_DIR / 'Arduino.h',
                            _CPP_DIR / 'Wire.h',
                            _DRIVER_DIR / 'skywriter.h'):
        fingerprint.update(path.read_bytes())
    binary = _BUILD_DIR / ('pin_release-' + fingerprint.hexdigest()[:12])
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
                'failed to compile the pin-release host binary:\n'
                f"$ {' '.join(cmd)}\n"
                + proc.stdout.decode(errors='replace')
                + proc.stderr.decode(errors='replace'))
    stdin = ''.join(instruction + '\n' for instruction in script)
    proc = subprocess.run([str(binary)], input=stdin.encode('ascii'),
                          capture_output=True, timeout=_TIMEOUT_RUN)
    if proc.returncode != 0:
        raise RuntimeError(
            f'pin-release host binary crashed (rc={proc.returncode}):\n'
            + proc.stderr.decode(errors='replace'))
    actions = []
    for line in proc.stdout.decode().splitlines():
        kind, pin, value = line.split()
        actions.append((kind, int(pin), int(value)))
    return actions


def _release_tail(actions):
    '''The release pair a poll() must end with, as (kind, pin, value)
    tuples: the line driven HIGH one last time, then the pin left as an
    input with its pull-up restored.'''
    return [(WRITE, XFER_PIN, 1), (MODE, XFER_PIN, MODE_INPUT_PULLUP)]


# A minimal valid 26-byte sensor-data frame: the recorded F01 fixture
# (specs/fixtures/F01_position_only.hex, mask 0x001F) — the normal read
# path needs a whole header + payload to dispatch.
_F01 = '1a 08 01 91 1f 00 5d 81 00 73 00 00 00 00 00 00 00 00 00 00 f4 01 e8 03 c8 00'


def test_failed_read_still_releases_the_transfer_line():
    '''H1: a poll whose read returns fewer than the 4 header bytes — the
    early-return path — must end with the same release pair as the normal
    path. This is the test that FAILED on the pre-P3.23 code.'''
    actions = _run(['RESET', 'SHORT', 'DUMP'])
    assert actions, 'the failed read must still touch the transfer line'
    assert actions[-2:] == _release_tail(actions), (
        f'the failed-read path must release the transfer line with its '
        f'pull-up restored, got tail: {actions[-4:]}')


def test_normal_read_releases_the_transfer_line_with_pullup():
    '''The normal path keeps its release, now WITH the pull-up restored
    (H2: a floating or disconnected TS wire must read consistently high,
    as the Python driver's release does).'''
    actions = _run(['RESET', 'FRAME ' + _F01, 'DUMP'])
    assert actions[-2:] == _release_tail(actions), (
        f'the normal path must release the transfer line with its pull-up '
        f'restored, got tail: {actions[-4:]}')


def test_failed_then_normal_reads_each_release():
    '''Repeating failed reads (the session-3 shape: the line would stay low
    forever without the fix) never strands the release: every poll ends
    released, so the next cycle can start.'''
    actions = _run(['RESET', 'SHORT', 'SHORT', 'SHORT',
                    'FRAME ' + _F01, 'DUMP'])
    # Three failed polls and one normal poll: each contributes its release
    # pair; the failed polls have no dispatch before theirs.
    releases = [tuple(a) for a in actions
                if a == _release_tail(actions)[0] or
                a == _release_tail(actions)[1]]
    # 4 polls × 2 release calls each.
    assert len(releases) == 8, (
        f'each of the four polls must end with the two release calls, '
        f'found {len(releases)}: {actions}')
    # And the final state is released with the pull-up.
    assert actions[-2:] == _release_tail(actions), actions[-4:]
