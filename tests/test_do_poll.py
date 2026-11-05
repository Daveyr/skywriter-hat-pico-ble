'''Regression pins for ``_do_poll``'s frame handling (fix_plan P3.3, D1).

Deviation D1 was an off-by-four regression in the Python driver: ``_do_poll``
read a 26-byte frame (4-byte header + 22-byte payload) and passed the *whole
frame* to the ``_handle_*`` decoders, which index payload offsets from 0 —
so every decoded field was shifted by 4 bytes into the header. The fix strips
the header at dispatch, matching the Arduino driver (whose ``poll()`` copies
the payload into ``command_buffer`` and hands exactly that to
``handle_sensor_data``) and the replay adapters (which feed the payload
directly and therefore never saw the bug).

These tests drive the driver's **real** ``_do_poll()`` code path so the
dispatch contract stays pinned forever, using recorded fixture frames from
``specs/fixtures/``. Hardware is mocked (no real I2C bus is touched).

Size-aware reads (fix_plan P3.11c) are pinned here too: the first poll read
asks 26 bytes, and any frame whose Size field (frame byte 0, the total
message length *including* its 4-byte header, Interface.pdf §3.3/§2.3) is
longer is fetched with chunked continuation reads while the transfer (TS)
pin stays asserted.
'''

from unittest import mock

import pytest

from tests import fixtures
from tests.adapters_python import import_skywriter


@pytest.fixture()
def sky():
    return import_skywriter()


def _poll_once_with_frame(sky, frame):
    '''Run the driver's real ``_do_poll()`` exactly once.

    The I2C bus (Inter-Integrated Circuit — the two-wire bus between the
    host and the sensor) is a mock that answers the one read with the given
    fixture frame, and the transfer pin reads low so the poll actually
    performs the read. Original module state is restored afterwards so
    replay tests sharing this module are unaffected.
    '''
    saved_i2c, saved_gpio = sky.i2c, sky.GPIO

    fake_bus = mock.Mock()
    fake_bus.read_i2c_block_data.return_value = list(frame)
    sky.i2c = fake_bus

    gpio = mock.Mock()          # fresh mock: never touches other tests' state
    gpio.input.return_value = 0  # transfer pin low: a frame is waiting
    sky.GPIO = gpio

    try:
        assert sky._do_poll() is True
    finally:
        sky.i2c = saved_i2c
        sky.GPIO = saved_gpio


@pytest.mark.parametrize('frame_name,handler_name', [
    ('F01_position_only', '_handle_sensor_data'),
    ('F16_status_ack_a2', '_handle_status_info'),
    ('F17_fw_version_valid', '_handle_firmware_info'),
])
def test_do_poll_strips_the_header_before_dispatch(sky, frame_name, handler_name):
    '''Each ``_handle_*`` decoder must receive exactly the payload — the frame
    minus its 4-byte header (size, flags, sequence, message ID) — no matter
    which of the three dispatched message types it is.'''
    frame = fixtures.load_frame(frame_name)

    seen = []
    saved = getattr(sky, handler_name)
    setattr(sky, handler_name, lambda data: seen.append(list(data)))
    try:
        _poll_once_with_frame(sky, frame)
    finally:
        setattr(sky, handler_name, saved)

    assert seen == [list(frame[4:])]


def test_do_poll_move_callback_sees_payload_positions(sky):
    '''End to end through the *real* decode path: fixture F01 (position x=500,
    y=1000, z=200 in raw 16-bit sensor units) must produce a move callback
    with those exact values scaled per the Python driver's representation
    (raw / 65536, rounded to 4 decimals). Under D1 this produced values read
    out of the header bytes instead.'''
    frame = fixtures.load_frame('F01_position_only')
    manifest = fixtures.load_manifest()
    (position,) = [e for e in fixtures.scenario(manifest, 'position_track')
                   ['expect']['canonical'] if e['event'] == 'position']

    moves = []
    saved = sky._on_move
    sky._on_move = lambda x, y, z: moves.append((x, y, z))
    try:
        _poll_once_with_frame(sky, frame)
    finally:
        sky._on_move = saved

    assert moves == [(
        round(position['x'] / 65536.0, sky._round_to),
        round(position['y'] / 65536.0, sky._round_to),
        round(position['z'] / 65536.0, sky._round_to),
    )]


class StreamBus:
    '''Fake I2C bus that streams one frame across consecutive reads.

    Models the sensor's behaviour for one asserted transfer (the transfer
    pin held low): each ``read_i2c_block_data`` call continues where the
    previous one stopped and returns up to the requested byte count. Every
    call is recorded so tests can pin the exact read sequence.
    '''

    def __init__(self, stream):
        self.stream = list(stream)
        self.pos = 0
        self.calls = []

    def read_i2c_block_data(self, addr, register, count):
        self.calls.append((addr, register, count))
        chunk = self.stream[self.pos:self.pos + count]
        self.pos += len(chunk)
        return chunk


@mock.patch('time.sleep')  # keep the poll loop wall-clock-free
def test_do_poll_chases_frames_longer_than_the_first_read(_sleep, sky):
    '''A frame whose Size field exceeds the first 26-byte read must be
    completed by chunked continuation reads (≤ 32 bytes each, the kernel
    SMBus cap) and then dispatched as the full size-bounded payload.

    Fixture F17 (Fw_Version_Info, Size = 0x84 = 132 bytes) arrives as
    26 + 32 + 32 + 32 + 10 across five reads; before P3.11c the driver
    dispatched only the first 26 bytes' worth of payload, cutting the
    120-byte version field short.'''
    frame = fixtures.load_frame('F17_fw_version_valid')
    assert frame[0] == 132 and len(frame) == 132

    bus = StreamBus(frame)
    saved_i2c, saved_gpio = sky.i2c, sky.GPIO
    sky.i2c = bus
    gpio = mock.Mock()
    gpio.input.return_value = 0   # transfer pin low: a frame is waiting
    sky.GPIO = gpio

    seen = []
    saved = sky._handle_firmware_info
    sky._handle_firmware_info = lambda data: seen.append(list(data))
    try:
        assert sky._do_poll() is True
    finally:
        sky.i2c, sky.GPIO = saved_i2c, saved_gpio
        sky._handle_firmware_info = saved

    # The read sequence is exactly the datasheet-recommended size chase:
    # header-sized probe read first, then the remainder in kernel-capped
    # chunks, with the last chunk asking exactly what the frame still lacks.
    assert bus.calls == [
        (sky.SW_ADDR, 0x00, 26),
        (sky.SW_ADDR, 0x00, 32),
        (sky.SW_ADDR, 0x00, 32),
        (sky.SW_ADDR, 0x00, 32),
        (sky.SW_ADDR, 0x00, 10),
    ]
    # The decoder received the FULL 132-byte frame's payload (header
    # stripped), not the truncated 22 bytes the fixed-size read could see.
    assert seen == [list(frame[4:])]


@mock.patch('time.sleep')
def test_do_poll_drops_an_incomplete_frame_instead_of_decoding_half(_sleep, sky):
    '''If the continuation reads come back empty (the buffer gave nothing
    more), the partial frame is skipped entirely — no handler must see a
    half-read message — and the poll still completes cleanly.'''
    frame = fixtures.load_frame('F17_fw_version_valid')
    bus = StreamBus(frame[:26])   # the bus only ever serves the first read

    saved_i2c, saved_gpio = sky.i2c, sky.GPIO
    sky.i2c = bus
    gpio = mock.Mock()
    gpio.input.return_value = 0
    sky.GPIO = gpio

    seen = []
    saved = sky._handle_firmware_info
    sky._handle_firmware_info = lambda data: seen.append(list(data))
    try:
        assert sky._do_poll() is True
    finally:
        sky.i2c, sky.GPIO = saved_i2c, saved_gpio
        sky._handle_firmware_info = saved

    assert bus.calls == [(sky.SW_ADDR, 0x00, 26), (sky.SW_ADDR, 0x00, 32)]
    assert seen == []


@mock.patch('time.sleep')
def test_do_poll_never_keeps_bytes_beyond_the_size_field(_sleep, sky):
    '''A bus that answers more than the requested count (the real sensor
    pads its reads; a mock may over-answer) must not leak padding into the
    payload: dispatch is bounded by the Size field.'''
    frame = fixtures.load_frame('F01_position_only')
    assert frame[0] == len(frame) == 26

    # Two junk bytes beyond the frame end on every answer.
    saved_i2c, saved_gpio = sky.i2c, sky.GPIO
    fake_bus = mock.Mock()
    fake_bus.read_i2c_block_data.return_value = list(frame) + [0xBB, 0xBB]
    sky.i2c = fake_bus
    gpio = mock.Mock()
    gpio.input.return_value = 0
    sky.GPIO = gpio

    seen = []
    saved = sky._handle_sensor_data
    sky._handle_sensor_data = lambda data: seen.append(list(data))
    try:
        assert sky._do_poll() is True
    finally:
        sky.i2c, sky.GPIO = saved_i2c, saved_gpio
        sky._handle_sensor_data = saved

    # Size field 26 == the fetched byte count twice over: no continuation
    # reads were needed, and the payload is exactly the frame's 22 payload
    # bytes — the 0xBB padding never reaches any decoder.
    assert fake_bus.read_i2c_block_data.call_count == 1
    assert seen == [list(frame[4:])]


@mock.patch('time.sleep')
def test_do_poll_skips_a_corrupt_size_field(_sleep, sky):
    '''A Size field under 4 (smaller than the mandatory header, Interface.pdf
    §3.3) is corrupt: no decoder sees it, and the poll completes cleanly so
    the background thread keeps running.'''
    frame = fixtures.load_frame('F01_position_only')
    corrupt = list(frame)
    corrupt[0] = 2   # Size says "2 bytes" — smaller than the 4-byte header

    saved_i2c, saved_gpio = sky.i2c, sky.GPIO
    fake_bus = mock.Mock()
    fake_bus.read_i2c_block_data.return_value = corrupt
    sky.i2c = fake_bus
    gpio = mock.Mock()
    gpio.input.return_value = 0
    sky.GPIO = gpio

    seen = []
    saved = sky._handle_sensor_data
    sky._handle_sensor_data = lambda data: seen.append(list(data))
    try:
        assert sky._do_poll() is True
    finally:
        sky.i2c, sky.GPIO = saved_i2c, saved_gpio
        sky._handle_sensor_data = saved

    # One read, no continuation chase, no dispatch.
    assert fake_bus.read_i2c_block_data.call_count == 1
    assert seen == []
