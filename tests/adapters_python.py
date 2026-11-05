'''Python-driver adapter for the replay harness (fix_plan P3.1).

Wraps the Raspberry Pi driver in ``library/skywriter/__init__.py``. Hardware
(RPi.GPIO, smbus) is mocked exactly like ``library/test.py`` so no real bus is
touched; the background polling thread is never started because we bypass
``setup()`` and register the capture handlers on the driver's (private) module
globals directly — the same globals its public decorators write.

Frame handling mirrors ``_do_poll()``'s dispatch: header ``ID`` decides which
``_handle_*`` function receives the **payload** (frame minus the 4-byte
header). Note the manifest expects exactly this payload slicing (deviation D1
is about ``_do_poll`` passing the *full* frame; feeding the payload here keeps
the harness on the documented contract).

The driver's wall-clock ``millis()`` is pointed at the replay session's
VirtualClock so touch repeat-limiting is simulated time, not real time.
'''

import sys
from unittest import mock

from .adapters import ReplayAdapter

_LIBRARY_DIR = (
    __import__('pathlib').Path(__file__).resolve().parents[1] / 'library'
)

_sky = None


def import_skywriter():
    '''Import library/skywriter with every hardware dependency mocked.

    Mirrors the import in library/test.py: the parent ``RPi`` mock must carry
    the same object as ``sys.modules['RPi.GPIO']`` (see the W5 note in
    fix_plan.md) and the I2C bus ("SMBus") mock is created but unused because
    the harness never calls ``setup()``.
    '''
    global _sky
    if _sky is not None:
        return _sky

    gpio = mock.Mock()
    gpio.RPI_REVISION = 3          # revision-3 board → the secondary bus
    rpi = mock.Mock()
    rpi.GPIO = gpio
    sys.modules['RPi'] = rpi
    sys.modules['RPi.GPIO'] = gpio
    sys.modules['smbus'] = mock.Mock()

    if _LIBRARY_DIR not in sys.path:  # pragma: no branch - idempotent
        sys.path.insert(0, str(_LIBRARY_DIR))
    import skywriter  # noqa: E402 - deliberately late, after the mocks
    _sky = skywriter
    return _sky


class PythonDriverAdapter(ReplayAdapter):
    name = 'python'

    def begin(self, clock):
        sky = import_skywriter()
        self.sky = sky

        # Fresh decoder state: every module-level variable the decoder reads
        # or accumulates into, set to its pristine default.
        sky.x = sky.y = sky.z = 0.0
        sky.rotation = 0.0
        sky._lastrotation = 0.0
        sky.gesture = 0
        sky.io_error_count = 0
        sky._on_touch_last = {}

        self.records = []
        self._clock = clock

        # Simulated time: the driver asks for wall-clock milliseconds when it
        # rate-limits repeat touch callbacks; give it the virtual clock.
        sky.millis = lambda: int(round(clock.now_ms))

        # Capture handlers in the driver's own callback vocabulary.
        sky._on_move = lambda x, y, z: self.records.append(
            {'kind': 'move', 'x': x, 'y': y, 'z': z})
        sky._on_flick = lambda src, dst: self.records.append(
            {'kind': 'flick', 'from': src, 'to': dst})
        sky._on_garbage = lambda: self.records.append({'kind': 'garbage'})
        sky._on_airwheel = lambda degrees: self.records.append(
            {'kind': 'airwheel', 'degrees': degrees})

        sky._on_touch = {
            kind: {'all': self._capture(kind)} for kind in ('touch', 'tap', 'doubletap')}
        sky._on_touch_repeat = {
            kind: {'all': 4} for kind in ('touch', 'tap', 'doubletap')}

    def _capture(self, kind):
        def handler(zone):
            self.records.append({'kind': kind, 'zone': zone})
        return handler

    def feed(self, frame, clock):
        before = len(self.records)
        payload = list(frame[4:])           # strip the 4-byte header
        ident = frame[3]
        if ident == self.sky.SW_SENSOR_DATA:
            self.sky._handle_sensor_data(payload)
        elif ident == self.sky.SW_SYSTEM_STATUS:
            self.sky._handle_status_info(payload)
        elif ident == self.sky.SW_FW_VERSION:
            self.sky._handle_firmware_info(payload)
        # other message IDs: ignore, like _do_poll's else-branch
        return self.records[before:]

    def finish(self, clock):
        return []
