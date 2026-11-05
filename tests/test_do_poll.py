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
