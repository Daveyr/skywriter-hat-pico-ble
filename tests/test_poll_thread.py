'''Regression pins for the poll thread's I2C error grace (fix_plan P3.11d).

Before P3.11d the background polling thread (AsyncWorker.run) treated any
``False`` return from ``_do_poll`` as "abort looping", and ``_do_poll``
returned ``False`` on the FIRST I2C (Inter-Integrated Circuit — the two-wire
bus between the host and the sensor) read error. The driver's documented
grace — "up to 10 consecutive I2C errors are tolerated, then raise" — was
unreachable: the thread died silently after a single transient bus error.
The fixture-replay harness never noticed because it drives the ``_handle_*``
decoders directly, bypassing the thread.

Decided here (and in the driver): an I/O error is ONE bad poll cycle — the
consecutive-error counter tracks the grace and ``_do_poll`` returns ``True``
so the loop retries on the next tick; past the grace the exception raises and
the thread dies with a visible traceback (a persistently dead bus is a
hardware fault, not a state to hide). Hardware stays mocked: no real bus is
touched.
'''

import threading
import time
from unittest import mock

from tests import fixtures
from tests.adapters_python import import_skywriter


def _wired_sky(monkeypatch=None, error_calls=0, frame=None):
    '''Wire the skywriter module to a fake bus + GPIO mock.

    The bus raises IOError for the first ``error_calls`` reads, then answers
    every read with ``frame``. The GPIO mock reports the transfer (TS) pin
    low so every poll performs a read. Returns ``(sky, bus, gpio)``; the
    module's ``i2c``/``GPIO`` are swapped in via monkeypatch (auto-restored),
    or assigned directly when no monkeypatch was passed (the caller must
    restore — the thread tests do).
    '''
    sky = import_skywriter()
    shared_frame = list(frame)

    class FlakyBus:

        def __init__(self):
            self.errors_left = error_calls
            self.calls = []

        def read_i2c_block_data(self, addr, register, count):
            self.calls.append((addr, register, count))
            if self.errors_left > 0:
                self.errors_left -= 1
                raise IOError('simulated bus fault')
            return shared_frame

    bus = FlakyBus()

    gpio = mock.Mock()
    gpio.input.return_value = 0          # transfer pin low: a frame waits

    if monkeypatch is not None:
        monkeypatch.setattr(sky, 'i2c', bus)
        monkeypatch.setattr(sky, 'GPIO', gpio)
    else:
        sky.i2c = bus
        sky.GPIO = gpio
    return sky, bus, gpio


def test_first_i2c_error_returns_true_and_keeps_polling(monkeypatch):
    '''THE pin the fix item asks for: the FIRST error must not kill the
    loop. ``_do_poll`` returns True (AsyncWorker keeps looping) and the grace
    counter records one failure.'''
    frame = fixtures.load_frame('F01_position_only')
    sky, bus, _gpio = _wired_sky(monkeypatch, 1, frame)
    monkeypatch.setattr(time, 'sleep', lambda *_: None)
    monkeypatch.setattr(sky, 'io_error_count', 0)

    assert sky._do_poll() is True
    assert sky.io_error_count == 1
    assert bus.calls                       # the failed read was attempted


def test_grace_survives_ten_consecutive_errors_then_raises(monkeypatch):
    '''Ten consecutive errors stay inside the grace (each poll returns
    True); the 11th consecutive error raises the documented exception.'''
    frame = fixtures.load_frame('F01_position_only')
    sky, bus, _gpio = _wired_sky(monkeypatch, 99, frame)
    monkeypatch.setattr(time, 'sleep', lambda *_: None)
    monkeypatch.setattr(sky, 'io_error_count', 0)

    for i in range(10):
        assert sky._do_poll() is True, f'error #{i + 1} must stay in grace'
        assert sky.io_error_count == i + 1

    try:
        sky._do_poll()
    except Exception as e:
        assert '10 consecutive I2C IO errors' in str(e)
    else:
        raise AssertionError('the 11th consecutive error must raise')
    assert sky.io_error_count == 11


def test_successful_read_resets_the_error_grace(monkeypatch):
    '''Any successful read zeroes the grace counter: errors scattered across
    successful frames never accumulate into the raise.'''
    frame = fixtures.load_frame('F01_position_only')
    sky, bus, _gpio = _wired_sky(monkeypatch, 99, frame)
    monkeypatch.setattr(time, 'sleep', lambda *_: None)
    monkeypatch.setattr(sky, 'io_error_count', 0)

    for _ in range(10):
        assert sky._do_poll() is True
    assert sky.io_error_count == 10

    # ...a healthy read happens here: the counter is back at zero.
    bus.errors_left = 0
    assert sky._do_poll() is True
    assert sky.io_error_count == 0

    # ...and a fresh batch of errors climbs from zero again, so it never
    # reaches the raise inside the grace either.
    for _ in range(10):
        bus.errors_left = 1
        assert sky._do_poll() is True
    assert sky.io_error_count == 10


def test_i2c_error_during_a_long_frame_returns_true_and_skips_dispatch(
        monkeypatch):
    '''A mid-frame error (first 26 bytes of a 132-byte Fw_Version_Info frame
    read, continuation read then fails) is the same one bad cycle: True, no
    half-frame dispatch, and the grace counter advances.'''
    frame = fixtures.load_frame('F17_fw_version_valid')

    sky = import_skywriter()
    monkeypatch.setattr(time, 'sleep', lambda *_: None)
    monkeypatch.setattr(sky, 'io_error_count', 0)

    class StreamBus:
        '''Streams the fixture frame, then raises on the continuation.'''

        def __init__(self):
            self.first = list(frame[:26])
            self.calls = []

        def read_i2c_block_data(self, addr, register, count):
            self.calls.append((addr, register, count))
            if len(self.calls) == 1:
                return self.first
            raise IOError('simulated mid-frame bus fault')

    bus = StreamBus()
    monkeypatch.setattr(sky, 'i2c', bus)
    gpio = mock.Mock()
    gpio.input.return_value = 0
    monkeypatch.setattr(sky, 'GPIO', gpio)

    seen = []
    saved = sky._handle_firmware_info
    sky._handle_firmware_info = lambda data: seen.append(list(data))
    try:
        assert sky._do_poll() is True
    finally:
        sky._handle_firmware_info = saved

    assert sky.io_error_count == 1
    assert seen == []          # a half-read frame never reaches a decoder
    assert bus.calls == [(sky.SW_ADDR, 0x00, 26), (sky.SW_ADDR, 0x00, 32)]


def test_i2c_error_releases_the_transfer_pin(monkeypatch):
    '''An error exit path must release the sensor's buffer: the transfer
    (TS) pin ends the cycle pulled-up-as-input, exactly like a good poll
    cycle (the release is now a finally).'''
    frame = fixtures.load_frame('F01_position_only')
    sky, bus, gpio = _wired_sky(monkeypatch, 99, frame)
    monkeypatch.setattr(time, 'sleep', lambda *_: None)
    monkeypatch.setattr(sky, 'io_error_count', 0)

    assert sky._do_poll() is True          # error #1: inside the grace

    released = [
        c for c in gpio.setup.call_args_list
        if c.args[:2] == (sky.SW_XFER_PIN, sky.GPIO.IN)
    ]
    assert released, 'the transfer pin was never released after the error'
    assert released[-1].kwargs.get('pull_up_down') == sky.GPIO.PUD_UP


def test_background_thread_survives_a_transient_i2c_error():
    '''End-to-end through the REAL thread: a bus that fails its first three
    reads and then delivers F01 must leave the worker alive with the frame
    dispatched — the pre-fix behaviour ended the thread on error #1, and F01
    never arrived.'''
    frame = fixtures.load_frame('F01_position_only')
    sky, bus, _gpio = _wired_sky(error_calls=3, frame=frame)
    saved_i2c, saved_gpio = sky.i2c, sky.GPIO
    try:
        seen = []
        saved_handler = sky._handle_sensor_data
        sky._handle_sensor_data = lambda data: seen.append(list(data))
        try:
            worker = sky.AsyncWorker(sky._do_poll)
            worker.start()
            try:
                # Wait (bounded) until the frame is dispatched — the thread
                # must have retried through the three simulated errors.
                deadline = time.monotonic() + 10.0
                while time.monotonic() < deadline and not seen:
                    time.sleep(0.01)
                assert seen, 'F01 never dispatched — the thread died?'
                assert bus.errors_left == 0

                # The decisive assertion: STILL alive after the errors.
                assert worker.alive() is True
            finally:
                worker.stop_event.set()
                worker.join(2.0)
            assert not worker.alive()

            assert seen[0] == list(frame[4:])
        finally:
            sky._handle_sensor_data = saved_handler
    finally:
        sky.i2c, sky.GPIO = saved_i2c, saved_gpio


def test_grace_exhaustion_kills_the_thread_visibly():
    '''Documented decision: past the grace the raise kills the worker thread
    with a real unhandled exception — never a silently stopped loop. Pinned
    via threading.excepthook so the visibility guarantee holds on any
    runtime.'''
    frame = fixtures.load_frame('F01_position_only')
    sky, bus, _gpio = _wired_sky(error_calls=99, frame=frame)
    saved_i2c, saved_gpio = sky.i2c, sky.GPIO
    hook_events = []
    old_hook = threading.excepthook

    def capture_hook(args):
        hook_events.append(args)

    threading.excepthook = capture_hook
    try:
        worker = sky.AsyncWorker(sky._do_poll)
        worker.start()
        try:
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline and not hook_events:
                time.sleep(0.01)
        finally:
            worker.stop_event.set()
            worker.join(2.0)

        assert len(hook_events) == 1, (
            'grace exhaustion must die VISIBLY via an unhandled exception')
        assert issubclass(hook_events[0].exc_type, Exception)
        assert '10 consecutive I2C IO errors' in str(hook_events[0].exc_value)

        # The thread is dead, and that is the intended end state: callers
        # stop a worker cleanly via stop_event/stop() — the granularity the
        # grace itself preserves for transient errors.
        assert not worker.alive()
    finally:
        threading.excepthook = old_hook
        sky.i2c, sky.GPIO = saved_i2c, saved_gpio
