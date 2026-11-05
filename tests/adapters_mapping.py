'''Mapping-engine adapter for the replay harness (fix_plan P3.12).

Chains the *complete* firmware signal chain behind the fixture replay:

    fixture frames → the real C++/Arduino Skywriter driver → canonical
    sensor events → SkywriterHIDMapper (pico-arduino/SkywriterHID, the same
    source the firmware sketch will link) → HID output records
    (tests/hid_grammar.py).

All of that runs inside one host binary (`tests/cpp/host_mapping_main.cpp`),
built with the same Arduino/Wire shims as the decoder adapter, so decoder and
mapper state are exactly the on-device originals. One process is spawned per
replayed scenario (fresh state, like adapters_cpp).

Timeline: the manifest gives per-scenario ``time_gap_ms``; when a
scenario does not set one, the sensor's own 5 ms frame cadence
(hid_mapping.md §2, "frames arrive every 5 ms while the hand is tracked") is
the gap. The adapter walks the virtual clock in ≤5 ms steps and, at each
step, sends a ``TICK <t>`` instruction (mapper.tick evaluates lift-off
gating and releases due move reports), interleaved with the ``FRAME <hex>``
instructions at the frames' arrival times — the same shape the firmware loop
will run at.
'''

import hashlib
import pathlib
import subprocess

from .adapters import ReplayAdapter
from .adapters_cpp import compiler_command

_THIS_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[0]
_CPP_DIR = _THIS_DIR / 'cpp'
_DRIVER_DIR = _REPO_ROOT / 'arduino' / 'Skywriter'
_ENGINE_DIR = _REPO_ROOT / 'pico-arduino' / 'SkywriterHID' / 'src'
_BUILD_DIR = _THIS_DIR / 'build'

_SOURCES = (_CPP_DIR / 'arduino_shim.cpp',
            _CPP_DIR / 'host_mapping_main.cpp',
            _DRIVER_DIR / 'skywriter.cpp',
            _ENGINE_DIR / 'SkywriterHIDMapper.cpp')
_HEADERS = (_CPP_DIR / 'Arduino.h',
            _CPP_DIR / 'Wire.h',
            _DRIVER_DIR / 'skywriter.h',
            _ENGINE_DIR / 'SkywriterHIDMapper.h')

_TIMEOUT_COMPILE = 300
_TIMEOUT_RUN = 30

# Sensor sampling: frames arrive every 5 ms while the hand is tracked
# (hid_mapping.md §2). The adapter's tick granularity matches it, so
# time-dependent engine behaviour (report cadence, lift-off gating) is
# exercised at the sensor's own resolution.
FRAME_PERIOD_MS = 5

_KEYBOARD_KEY_BY_USAGE = {78: 'page_up', 79: 'page_down'}


def build_host_mapping():
    '''Compile tests/cpp + driver + SkywriterHIDMapper for the host.'''
    fingerprint = hashlib.sha256()
    fingerprint.update('compiler='.encode() + compiler_command()[0].encode()
                       + b'\n')
    for path in _SOURCES + _HEADERS:
        fingerprint.update(path.read_bytes())
    binary = _BUILD_DIR / ('host_mapping-' + fingerprint.hexdigest()[:12])

    if binary.exists():
        return binary

    _BUILD_DIR.mkdir(parents=True, exist_ok=True)
    cmd = compiler_command() + [
        '-I', str(_CPP_DIR),        # Arduino/Wire shims shadow the real ones
        '-I', str(_DRIVER_DIR),     # "skywriter.h"
        '-I', str(_ENGINE_DIR),     # "SkywriterHIDMapper.h"
    ] + [str(src) for src in _SOURCES] + ['-o', str(binary)]
    proc = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT_COMPILE)
    if proc.returncode != 0:
        raise RuntimeError(
            'failed to compile the host mapping adapter:\n'
            f"$ {' '.join(cmd)}\n"
            + proc.stdout.decode(errors='replace')
            + proc.stderr.decode(errors='replace'))
    return binary


class MappingAdapter(ReplayAdapter):
    name = 'cpp_mapping'

    def begin(self, clock):  # fresh mapper state = one fresh process
        self._binary = build_host_mapping()

    def replay_frames(self, frames, clock, gap_ms):
        self.begin(clock)
        stage = 0.0
        instructions = []

        def advance(delta_ms):
            '''Walk the clock in ≤FRAME_PERIOD_MS steps, TICKing each step.'''
            nonlocal stage
            while delta_ms > 0:
                step = min(FRAME_PERIOD_MS, delta_ms)
                stage += step
                delta_ms -= step
                instructions.append(f'TICK {int(round(stage))}')

        for index, frame in enumerate(frames):
            if index:
                advance(gap_ms if gap_ms else FRAME_PERIOD_MS)
            instructions.append('FRAME ' + frame.hex())
        # The runner semantics: one more advance after the last frame, so
        # time-dependent expectations (release-by-silence, pending reports)
        # can be evaluated before FIN.
        advance(gap_ms if gap_ms else FRAME_PERIOD_MS)
        instructions.append(f'FIN {int(round(stage))}')

        stdin = ''.join(instruction + '\n' for instruction in instructions)
        proc = subprocess.run(
            [str(self._binary)], input=stdin.encode('ascii'),
            capture_output=True, timeout=_TIMEOUT_RUN)
        if proc.returncode != 0:
            raise RuntimeError(
                f'host mapping adapter crashed (rc={proc.returncode}):\n'
                + proc.stderr.decode(errors='replace'))
        return [self._parse(line)
                for line in proc.stdout.decode().splitlines()
                if line.startswith('HID ')]

    def feed(self, frame, clock):  # pragma: no cover - unreachable by design
        raise NotImplementedError(
            'MappingAdapter must be driven via replay_frames (one process '
            'per scenario keeps decoder + mapper state coherent)')

    @staticmethod
    def _parse(line):
        parts = line.split()
        if parts[1] == 'MOVE':
            return {'channel': 'mouse', 'action': 'move',
                    'dx': int(parts[2]), 'dy': int(parts[3])}
        if parts[1] == 'BUTTON':
            return {'channel': 'mouse', 'action': 'button',
                    'button': parts[2], 'state': parts[3]}
        if parts[1] == 'WHEEL':
            return {'channel': 'mouse', 'action': 'wheel',
                    'notches': int(parts[2])}
        if parts[1] == 'CLICK':
            return {'channel': 'mouse', 'action': 'click',
                    'button': parts[2], 'count': int(parts[3]),
                    'click_ms': int(parts[4])}
        if parts[1] == 'KEY':
            usage = int(parts[2])
            return {'channel': 'keyboard', 'action': 'press',
                    'key': _KEYBOARD_KEY_BY_USAGE[usage],
                    'usage': usage}
        if parts[1] == 'CONSUME':
            return {'channel': 'consumer', 'action': 'press',
                    'usage': int(parts[2])}
        raise ValueError(f'unrecognised HID line: {line!r}')

    def finish(self, clock):
        return []
