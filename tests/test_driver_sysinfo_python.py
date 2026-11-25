'''The Raspberry Pi Python driver must surface the sensor's own health
byte publicly (fix_plan item P3.30 — the Python twin of the Arduino
driver's tests/test_driver_sysinfo.py, P3.29).

In plain language: the sensor attaches a one-byte status report to every
data frame it sends — the SystemInfo byte (Interface.pdf §4.5 Table 4-10).
Besides the "this field is valid" bits (bit 0 PositionValid, bit 1
AirWheelValid, bit 7 DSPRunning) it carries two HEALTH bits the sensor
fills in by itself: bit 4 = EnvironmentalNoise ("environmental noise has
been detected") and bit 5 = Clipping ("the ADCs are clipping"). The
Arduino driver records the raw byte as public state (`last_sysinfo`)
since P3.29 and the Pico W firmware prints it; the Python driver used to
discard it. The P4.0 acceptance run's hypothesis (iii) may need the
Raspberry Pi cross-check on the sensor's native platform, and that
session must see the same evidence surface: the raw byte recorded per
decoded sensor-data frame as module state (`skywriter.sysinfo`), set on
EVERY frame BEFORE the validity branches so the health report survives
even when no payload field is valid — handlers read it alongside their
own arguments, like x/y/z.

Test method (the P3.11c fixture pattern, as in tests/test_do_poll.py):
the driver's REAL ``_do_poll()`` runs against a mocked I2C bus
(Inter-Integrated Circuit — the two-wire bus between the host and the
sensor) that answers with crafted 26-byte sensor-data frames, and a
mocked GPIO (General-Purpose Input/Output) transfer pin that reads low
so the poll actually performs the read. No hardware is touched.

These tests FAILED against the pre-P3.30 code: the ``sysinfo`` module
global did not exist (the byte was read into the local ``d_sysinfo`` and
dropped at the end of ``_handle_sensor_data``).
'''

from unittest import mock

import pytest

from tests import fixtures
from tests.adapters_python import import_skywriter


# SystemInfo byte health bits (Interface.pdf §4.5, Table 4-10).
NOISE_AND_CLIPPING = 0x10 | 0x20   # bit 4 EnvironmentalNoise, bit 5 Clipping
DSP_RUNNING = 0x80                 # bit 7
POSITION_VALID = 0x01              # bit 0
AIRWHEEL_VALID = 0x02              # bit 1


def _sensor_frame(mask, sysinfo, airwheel=0x00, x=0, y=0, z=0):
    '''A 26-byte sensor-data frame (the classic full layout): Size, Flags,
    Sequence, identity 0x91, then the payload — DataOutputConfigMask (2
    bytes LE), TimeStamp, SystemInfo, DSPStatus (2), GestureInfo (4),
    TouchInfo (4), AirWheelInfo (2), XYZ (6). The same layout the C++
    twin's ``_frame()`` helper builds.'''
    payload = bytearray(22)
    payload[0:2] = mask.to_bytes(2, 'little')
    payload[2] = 0x5D                    # TimeStamp (any value)
    payload[3] = sysinfo
    payload[14] = airwheel & 0xFF        # AirWheelInfo byte 0: the counter
    payload[16:18] = x.to_bytes(2, 'little')
    payload[18:20] = y.to_bytes(2, 'little')
    payload[20:22] = z.to_bytes(2, 'little')
    return bytes([0x1A, 0x08, 0x01, 0x91]) + bytes(payload)


@pytest.fixture()
def sky():
    return import_skywriter()


@pytest.fixture()
def capture_events(sky):
    '''Capture handlers on the driver's (private) callback globals, as the
    replay adapter does. Returns a dict of lists, one per event kind.'''
    captured = {'move': [], 'airwheel': [], 'touch': [], 'gesture': []}

    saved = (sky._on_move, sky._on_airwheel, sky._on_flick,
             sky._on_garbage, sky._on_circle, sky._on_touch,
             sky._on_touch_repeat, sky._on_touch_last)

    sky._on_move = lambda x, y, z: captured['move'].append((x, y, z))
    sky._on_airwheel = lambda degrees: captured['airwheel'].append(degrees)
    sky._on_flick = lambda src, dst: captured['gesture'].append(('flick', src, dst))
    sky._on_garbage = lambda: captured['gesture'].append(('garbage',))
    sky._on_circle = lambda direction: captured['gesture'].append(('circle', direction))
    sky._on_touch = {kind: {'all': (lambda zone, k=kind: captured['touch'].append((k, zone)))}
                     for kind in ('touch', 'tap', 'doubletap')}
    sky._on_touch_repeat = {kind: {'all': 4} for kind in ('touch', 'tap', 'doubletap')}
    sky._on_touch_last = {}

    yield captured

    (sky._on_move, sky._on_airwheel, sky._on_flick,
     sky._on_garbage, sky._on_circle, sky._on_touch,
     sky._on_touch_repeat, sky._on_touch_last) = saved


def _poll_once_with_frame(sky, frame):
    '''Run the driver's real ``_do_poll()`` exactly once against a mocked
    bus serving ``frame`` (mirrors tests/test_do_poll.py's helper).'''
    saved_i2c, saved_gpio = sky.i2c, sky.GPIO

    fake_bus = mock.Mock()
    fake_bus.read_i2c_block_data.return_value = list(frame)
    sky.i2c = fake_bus

    gpio = mock.Mock()            # fresh mock: never touches other tests' state
    gpio.input.return_value = 0   # transfer pin low: a frame is waiting
    sky.GPIO = gpio

    try:
        assert sky._do_poll() is True
    finally:
        sky.i2c = saved_i2c
        sky.GPIO = saved_gpio


@mock.patch('time.sleep')  # keep the poll loop wall-clock-free
def test_health_bits_surface_even_when_nothing_dispatches(_sleep, sky,
                                                          capture_events):
    '''A frame whose SystemInfo byte carries the two health bits (noise +
    clipping) and whose output mask enables NO field must still leave
    `skywriter.sysinfo` = 0x30: the sensor's own health report survives
    even when no payload field is valid — this is the reading the
    hover-deafness cross-check (P4.0 hypothesis (iii)) needs.'''
    sky.sysinfo = 0
    _poll_once_with_frame(sky, _sensor_frame(0x0000, NOISE_AND_CLIPPING))

    for kind, events in capture_events.items():
        assert events == [], f'a mask-0 frame dispatches nothing ({kind})'
    assert sky.sysinfo == NOISE_AND_CLIPPING


@mock.patch('time.sleep')
def test_sysinfo_tracks_the_latest_decoded_frame(_sleep, sky, capture_events):
    '''`sysinfo` is per-frame state (like `gesture`): the latest decoded
    sensor-data frame's byte always wins, including through a frame that
    dispatches events. The dispatching frame here is the RECORDED fixture
    F01 (position x=500, y=1000, z=200), whose own SystemInfo byte is
    0x81 = PositionValid | DSPRunning.'''
    sky.sysinfo = 0
    _poll_once_with_frame(sky, _sensor_frame(0x0000, NOISE_AND_CLIPPING))
    assert sky.sysinfo == NOISE_AND_CLIPPING

    frame = fixtures.load_frame('F01_position_only')
    assert frame[7] == POSITION_VALID | DSP_RUNNING   # the fixture's own byte

    _poll_once_with_frame(sky, frame)
    assert capture_events['move'] == [(
        round(500 / 65536.0, sky._round_to),
        round(1000 / 65536.0, sky._round_to),
        round(200 / 65536.0, sky._round_to),
    )]
    assert sky.sysinfo == POSITION_VALID | DSP_RUNNING


@mock.patch('time.sleep')
def test_airwheel_baseline_still_records_the_raw_byte(_sleep, sky,
                                                      capture_events):
    '''The first AirWheel-valid frame baselines the rotation counter
    SILENTLY (the P3.4/P3.9 rule) — and its SystemInfo byte (bit 1
    AirWheelValid) must still be recorded: the cross-check session reads
    "was AirWheel valid at this frame" next to the rotation state.'''
    sky.sysinfo = 0
    _poll_once_with_frame(
        sky, _sensor_frame(0x0008, AIRWHEEL_VALID, airwheel=0x80))

    assert capture_events['airwheel'] == [], \
        'the baseline frame emits no rotation event'
    assert sky.sysinfo == AIRWHEEL_VALID


@mock.patch('time.sleep')
def test_handlers_read_sysinfo_alongside_their_arguments(_sleep, sky,
                                                         capture_events):
    '''The exposure contract: a registered handler reads the raw byte
    DURING the callback, exactly like x/y/z — the cross-check session's
    `@skywriter.move()` handler logs the sensor's health bits per event
    with no new hardware access.'''
    sky.sysinfo = 0
    seen_during_callback = []

    real_handler = sky._on_move

    def handler(x, y, z):
        seen_during_callback.append(sky.sysinfo)
        real_handler(x, y, z)

    sky._on_move = handler
    _poll_once_with_frame(sky, fixtures.load_frame('F01_position_only'))

    assert capture_events['move'], 'the fixture dispatches its move event'
    assert seen_during_callback == [POSITION_VALID | DSP_RUNNING]
