'''C++ decoder adapter for the replay harness (fix_plan P3.1).

Compiles the real Arduino driver (``arduino/Skywriter/skywriter.cpp``, the same
source that runs on the Pico W) for the host, behind the minimal Arduino/Wire
shims in ``tests/cpp/``, and drives its genuine ``poll()`` code path —
xfer pin low, Wire header parse, private ``handle_sensor_data`` — once per
replayed frame.

Because decoder state lives in a separate process, one process is spawned per
replayed scenario (``replay_frames`` override); its stdout ``EV`` lines are
parsed into native records:

- ``{"kind": "move", "x"|..|...: int}``      raw 16-bit position values
- ``{"kind": "touch_code", "code": int}``   Arduino touch code (see skywriter.h)
- ``{"kind": "gesture", "code": int, "class": int, "edge": bool}``
                                             gesture code (1 garbage, 2-5
                                             flicks, 6-7 circles) with the
                                             GestureInfo attributes decoded
                                             from the full 32-bit word (P3.11,
                                             closing the Arduino half of
                                             deviation D7): class = bits 12-15
                                             (0 garbage, 1 flick, 2 circle),
                                             edge = bit 16 edge-flick flag
- ``{"kind": "airwheel", "degrees": float}`` rotation delta in degrees
                                             (quantized to 11.25-degree
                                             sensor steps)

The host has no system C++ compiler in this container (Alpine, no sudo), so
the compiler is resolved as: ``g++``/``c++`` on PATH → ``zig c++`` on PATH →
``python3 -m ziglang c++`` (the ``ziglang`` PyPI wheel is itself a full C++
toolchain; installed with ``pip install --user --break-system-packages ziglang``).
The compiled binary is cached in ``tests/build/`` keyed by a hash of the
shim + driver sources, so repeated runs do not recompile.
'''

import hashlib
import pathlib
import shutil
import subprocess
import sys

from .adapters import ReplayAdapter

_THIS_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[0]
_CPP_DIR = _THIS_DIR / 'cpp'
_DRIVER_DIR = _REPO_ROOT / 'arduino' / 'Skywriter'
_BUILD_DIR = _THIS_DIR / 'build'

_SOURCES = (_CPP_DIR / 'arduino_shim.cpp',
            _CPP_DIR / 'host_decoder_main.cpp',
            _DRIVER_DIR / 'skywriter.cpp')
_HEADERS = (_CPP_DIR / 'Arduino.h',
            _CPP_DIR / 'Wire.h',
            _DRIVER_DIR / 'skywriter.h')

_TIMEOUT_COMPILE = 300   # first compile on a cold zig install can be slow
_TIMEOUT_RUN = 30


def compiler_command():
    '''Find a host C++ compiler, most-system-like first (see module docstring).'''
    cxx = shutil.which('g++') or shutil.which('c++')
    if cxx:
        return [cxx]
    if shutil.which('zig'):
        return ['zig', 'c++']
    zig = subprocess.run(
        [sys.executable, '-m', 'ziglang', 'version'],
        capture_output=True) if _HAS_ZIGLANG() else None
    if zig and zig.returncode == 0:
        return [sys.executable, '-m', 'ziglang', 'c++']
    raise RuntimeError(
        'no host C++ compiler found for the tests/cpp replay decoder; '
        'install one with: pip install --user --break-system-packages ziglang '
        "(a g++/c++ on PATH is preferred when available) — see tests/"
        'adapters_cpp.py docstring')


def _HAS_ZIGLANG():
    try:
        import ziglang  # noqa: F401
        return True
    except ImportError:
        return False


def build_host_decoder():
    '''Compile tests/cpp + the Arduino driver for the host (hash-cached).'''
    fingerprint = hashlib.sha256()
    fingerprint.update('compiler='.encode() + compiler_command()[0].encode()
                       + b'\n')
    for path in _SOURCES + _HEADERS:
        fingerprint.update(path.read_bytes())
    binary = _BUILD_DIR / ('host_decoder-' + fingerprint.hexdigest()[:12])

    if binary.exists():
        return binary

    _BUILD_DIR.mkdir(parents=True, exist_ok=True)
    cmd = compiler_command() + [
        '-I', str(_CPP_DIR),      # shims shadow <Arduino.h> and <Wire.h>
        '-I', str(_DRIVER_DIR),   # "skywriter.h"
    ] + [str(src) for src in _SOURCES] + ['-o', str(binary)]
    proc = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT_COMPILE)
    if proc.returncode != 0:
        raise RuntimeError(
            'failed to compile the host decoder adapter:\n'
            f"$ {' '.join(cmd)}\n"
            + proc.stdout.decode(errors='replace')
            + proc.stderr.decode(errors='replace'))
    return binary


class CppDecoderAdapter(ReplayAdapter):
    name = 'cpp'

    def __init__(self):
        self._binary = None

    def begin(self, clock):
        # Compile once per session (fresh runs recompile only if a source
        # changed — the binary path carries the source fingerprint).
        self._binary = build_host_decoder()

    def replay_frames(self, frames, clock, gap_ms):
        self.begin(clock)
        if gap_ms:
            # The frame decoder itself has no timed behaviour, so simulated
            # gaps between frames change nothing here; timed expectations
            # (release-by-silence, auto-scroll cadence) are evaluated by the
            # clock-aware mapping-engine adapters added from fix_plan P3.13.
            pass
        stdin = ''.join(f.hex() + '\n' for f in frames)
        proc = subprocess.run(
            [str(self._binary)], input=stdin.encode('ascii'),
            capture_output=True, timeout=_TIMEOUT_RUN)
        if proc.returncode != 0:
            raise RuntimeError(
                f'host decoder crashed (rc={proc.returncode}):\n'
                + proc.stderr.decode(errors='replace'))
        return [self._parse(line)
                for line in proc.stdout.decode().splitlines()
                if line.startswith('EV ')]

    def feed(self, frame, clock):  # pragma: no cover - unreachable by design
        raise NotImplementedError(
            'CppDecoderAdapter must be driven via replay_frames (one process '
            'per scenario keeps decoder state coherent)')

    @staticmethod
    def _parse(line):
        parts = line.split()
        kind = parts[1].lower()
        if kind == 'move':
            return {'kind': 'move', 'x': int(parts[2]), 'y': int(parts[3]),
                    'z': int(parts[4])}
        if kind == 'touch':
            # The C++ driver reports Arduino touch codes (skywriter.h), so the
            # record name differs from the Python adapter's named zones.
            return {'kind': 'touch_code', 'code': int(parts[2])}
        if kind == 'gesture':
            # `EV GESTURE <code> <class> <edge>` — the driver decodes the
            # full 32-bit GestureInfo word (P3.11; class is bits 12-15,
            # edge the bit-16 edge-flick flag, both printed by the host
            # decoder shim from the driver's public state).
            return {'kind': 'gesture', 'code': int(parts[2]),
                    'class': int(parts[3]), 'edge': bool(int(parts[4]))}
        if kind == 'airwheel':
            # %.2f printed degrees: exact for the 11.25-degree quantization
            # of the AirWheel decoder (and for the Python parity compare,
            # which tolerates 1e-6 float noise only).
            return {'kind': 'airwheel', 'degrees': float(parts[2])}
        raise ValueError(f'unrecognised EV line: {line!r}')

    def finish(self, clock):
        return []
