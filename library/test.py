'''Offline unit test for the skywriter driver.

Every piece of hardware is faked in memory:

- I2C (Inter-Integrated Circuit -- the two-wire bus this driver talks to the
  sensor over) is faked via the ``smbus`` module mock.  It answers the driver's
  status handshake with the ``SET_RUNTIME_PARAMETER`` acknowledge frame
  recorded in ``specs/fixtures/F16_status_ack_a2.hex``, so the fixture
  directory stays the single source of truth for what the sensor returns.
- GPIO (General-Purpose Input/Output pins) are faked via the ``RPi`` /
  ``RPi.GPIO`` module mocks; the transfer pin reads HIGH (idle), so the
  background polling thread has no sensor data to fetch.

The test asserts that ``setup()`` completes the full handshake and that event
callbacks register cleanly.  No I2C bus and no network are touched: this runs
anywhere Python runs.
'''

import os
import sys
import unittest
from unittest import mock

# Fixture directory shared with the acceptance specs / replay tests.
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', 'specs', 'fixtures')


def load_fixture(name):
    '''Load a recorded sensor frame from specs/fixtures as a 26-byte list.

    The driver always reads 26 bytes over I2C, so recorded frames are
    zero-padded up to that length.
    '''
    path = os.path.join(FIXTURES, name)
    raw = bytes.fromhex(''.join(open(path).read().split()))
    return list(raw) + [0] * (26 - len(raw))


# The sensor's acknowledge frame for the SET_RUNTIME_PARAMETER command:
# header says "16 bytes, id 0x15 (system status), confirming command 0xA2".
STATUS_ACK_A2 = load_fixture('F16_status_ack_a2.hex')


def make_gpio_mock():
    gpio = mock.Mock()
    # Pretend this is a revision-3 board (picks the correct I2C bus number).
    gpio.RPI_REVISION = 3
    # Transfer pin reads HIGH, i.e. "no fresh data waiting" while idle.
    gpio.input.return_value = 1
    return gpio


class TestSetupHandshake(unittest.TestCase):
    '''The driver must complete its startup handshake against fake hardware.'''

    def setUp(self):
        # Re-import skywriter fresh so each test sees pristine module globals.
        sys.modules.pop('skywriter', None)
        gpio = make_gpio_mock()
        rpi = mock.Mock()
        rpi.GPIO = gpio  # `import RPi.GPIO` resolves against the parent mock
        sys.modules['RPi'] = rpi
        sys.modules['RPi.GPIO'] = gpio
        smbus = mock.Mock()
        smbus.SMBus.return_value.read_i2c_block_data.return_value = \
            STATUS_ACK_A2
        sys.modules['smbus'] = smbus
        self.smbus = smbus

        import skywriter
        self.sky = skywriter

    def test_setup_completes_and_registers_callbacks(self):
        @self.sky.airwheel()
        def on_airwheel(delta):  # noqa: ARG001 - signature must match driver
            pass

        @self.sky.move()
        def on_move(x, y, z):  # noqa: ARG001 - signature must match driver
            pass

        @self.sky.circle()
        def on_circle(direction):  # noqa: ARG001 - signature must match driver
            pass

        # Decorating triggered setup() exactly once; it must not raise.
        self.assertTrue(self.sky._is_setup)

        # One bus object for one I2C bus.
        self.smbus.SMBus.assert_called_once_with(1)
        bus = self.smbus.SMBus.return_value

        # Four SET_RUNTIME_PARAMETER commands are written to configure the
        # sensor (AirWheel, gestures, data outputs, auto-calibration off).
        self.assertEqual(bus.write_i2c_block_data.call_count, 4)
        for call in bus.write_i2c_block_data.call_args_list:
            address, register, _payload = call.args
            self.assertEqual(address, self.sky.SW_ADDR)   # the sensor: 0x42
            self.assertEqual(register, 0x10)              # command-write register

        # Every status read was answered by the recorded acknowledge frame.
        self.assertEqual(bus.read_i2c_block_data.call_count, 4)
        for call in bus.read_i2c_block_data.call_args_list:
            address, register, length = call.args
            self.assertEqual(address, self.sky.SW_ADDR)
            self.assertEqual(register, 0x00)
            self.assertEqual(length, 26)
        self.assertEqual(bus.read_i2c_block_data.return_value, STATUS_ACK_A2)
        self.assertEqual(STATUS_ACK_A2[3], 0x15,
                         'fixture must be a system-status frame')
        self.assertEqual(STATUS_ACK_A2[4], 0xA2,
                         'fixture must acknowledge a runtime-parameter command')

        # The background polling thread is alive and eventually stops cleanly
        # (the registered handlers below must not exercise it: transfer pin
        # reads HIGH so no sensor frames are fetched).
        self.assertIsNotNone(self.sky._worker)
        self.assertTrue(self.sky._worker.alive())
        self.sky._stop_poll()
        self.assertIsNone(self.sky._worker)

        # Callbacks registered where setup() could see them.
        self.assertTrue(callable(self.sky._on_airwheel))
        self.assertTrue(callable(self.sky._on_move))
        self.assertTrue(callable(self.sky._on_circle))


if __name__ == '__main__':
    unittest.main()
