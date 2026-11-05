import atexit
import threading
import time
from sys import version_info

try:
    from smbus import SMBus
except ImportError:
    if version_info[0] < 3:
        raise ImportError("This library requires python-smbus\nInstall with: sudo apt-get install python-smbus")
    elif version_info[0] == 3:
        raise ImportError("This library requires python3-smbus\nInstall with: sudo apt-get install python3-smbus")

try:
    import RPi.GPIO as GPIO
except ImportError:
    raise ImportError("This library requires the RPi.GPIO module\nInstall with: sudo pip install RPi.GPIO")

__version__ = '0.0.9'

SW_ADDR = 0x42
SW_RESET_PIN = 17
SW_XFER_PIN = 27

SW_HEADER_SIZE = 4
# The Size field is a single byte counting the whole message INCLUDING this
# 4-byte header, and the GestIC protocol caps a message at 255 bytes
# (Interface.pdf §3.2) — so this is the upper bound of any size-aware read.
SW_MAX_MESSAGE_SIZE = 255
# The Raspberry Pi's Linux SMBus helper caps a single block read at 32 bytes
# (kernel I2C_SMBUS_BLOCK_MAX), so a frame longer than that must be fetched
# in chunked continuation reads.
SW_I2C_READ_CHUNK = 32

SW_DATA_DSP = 0b0000000000000001
SW_DATA_GESTURE = 0b0000000000000010
SW_DATA_TOUCH = 0b0000000000000100
SW_DATA_AIRWHEEL = 0b0000000000001000
SW_DATA_XYZ = 0b0000000000010000

SW_SYSTEM_STATUS = 0x15
SW_REQUEST_MSG = 0x06
SW_FW_VERSION = 0x83
SW_SET_RUNTIME = 0xA2
SW_SENSOR_DATA = 0x91

i2c_bus = 0
i2c = None

if GPIO.RPI_REVISION == 2 or GPIO.RPI_REVISION == 3:
    i2c_bus = 1


x = 0.0
y = 0.0
z = 0.0
rotation = 0.0
# AirWheel counter reference: None until the first frame with valid AirWheel
# data establishes the baseline (the counter is free-running — see notes in
# _handle_sensor_data).
_lastrotation = None
_round_to = 4
_enable_auto_calibration = False
_enable_events = True
_debug = False
gesture = 0
# Attributes of the most recently recognized gesture, decoded from the
# 32-bit GestureInfo word (Interface.pdf §4.5, Table 4-10). Handlers read
# these alongside their own arguments, like x/y/z:
#   gesture_class — gesture kind, GestureInfo bits 12–15
#                   (0 none/garbage, 1 flick, 2 circle)
#   gesture_edge  — edge-flick flag, GestureInfo bit 16
gesture_class = 0
gesture_edge = False

# Last received control frames, decoded per Interface.pdf (the sensor's
# datasheet): the System_Status acknowledge (§3.6 / Table 3-8) and the
# Fw_Version_Info report (§4.3, Table 4-5/4-6). Handlers read these alongside
# their own arguments, like x/y/z:
#   system_status       — the control message that was acknowledged
#                         (Set_Runtime_Parameter 0xA2 = 170, ...)
#   system_status_error — the acknowledge's 16-bit error code (0 = applied)
#   fw_valid            — FwValid status byte; only 0xAA is a valid library
#   fw_version          — the NUL-stripped version string (only meaningful
#                         for a valid report; empty otherwise)
system_status = 0
system_status_error = 0
fw_valid = 0
fw_version = ''

io_error_count = 0

_worker = None
_on_flick = None
_on_move = None
_on_airwheel = []
_on_touch = {}
_on_touch_repeat = {}
_on_touch_last = {}
_on_garbage = None
# Circle handler: single callable receiving the direction as a string
# ('clockwise' or 'counter-clockwise'), like the flick/garbage registries.
_on_circle = None
# Optional control-frame handlers (fix item P3.11b): the parsed System_Status
# acknowledge gets (msg_id, error); the valid Fw_Version_Info report gets the
# NUL-stripped version string. Module state (system_status, system_status_error,
# fw_valid, fw_version) carries the values alongside, like x/y/z.
_on_system_status = None
_on_firmware_version = None
_is_setup = False


def millis():
    return int(round(time.time() * 1000))


def reset():
    GPIO.output(SW_RESET_PIN, GPIO.LOW)
    time.sleep(.1)
    GPIO.output(SW_RESET_PIN, GPIO.HIGH)
    time.sleep(.5)  # Datasheet delay of 200ms plus change


def enable(status=True):
    global _enable_events
    _enable_events = status


class StoppableThread(threading.Thread):
    '''Basic stoppable thread wrapper

    Adds Event for stopping the execution loop
    and exiting cleanly.
    '''
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop_event = threading.Event()
        self.daemon = True

    def alive(self):
        try:
            return self.isAlive()
        except AttributeError:
            # Python >= 3.9
            return self.is_alive()

    def start(self):
        if not self.alive():
            self.stop_event.clear()
            threading.Thread.start(self)

    def stop(self):
        if self.alive():
            # set event to signal thread to terminate
            self.stop_event.set()
            # block calling thread until thread really has terminated
            self.join()


class AsyncWorker(StoppableThread):
    '''Basic thread wrapper class for asyncronously running functions

    Basic thread wrapper class for running functions
    asyncronously. Return False from your function
    to abort looping.
    '''
    def __init__(self, todo):
        StoppableThread.__init__(self)
        self.todo = todo

    def stop(self):
        self.stop_event.set()

    def run(self):
        while not self.stop_event.is_set():
            if not self.todo():
                self.stop_event.set()
                break


def _handle_sensor_data(data):
    global _lastrotation, rotation
    global gesture, gesture_class, gesture_edge

    d_configmask = data[0] | data[1] << 8
    # d_timestamp = data[2] (200hz, 8-bit counter, max ~1.25sec)
    d_sysinfo = data[3]

    # d_dspstatus = data[4:6]
    d_gesture = data[6:10]
    d_touch = data[10:14]
    d_airwheel = data[14:16]
    d_xyz = data[16:24]
    # d_noisepow = data[24:28]

    if d_configmask & SW_DATA_XYZ and d_sysinfo & 0b0000001:
        # We have xyz info, and it's valid
        x, y, z = (
            round((d_xyz[1] << 8 | d_xyz[0]) / 65536.0, _round_to),
            round((d_xyz[3] << 8 | d_xyz[2]) / 65536.0, _round_to),
            round((d_xyz[5] << 8 | d_xyz[4]) / 65536.0, _round_to)
        )
        if callable(_on_move):
            _on_move(x, y, z)

    if d_configmask & SW_DATA_GESTURE and not d_gesture[0] == 0:
        # We have a gesture!
        #
        # GestureInfo is a 32-bit little-endian word (Interface.pdf §4.5,
        # Table 4-10): bits 0-7 = gesture code (0 none, 1 garbage, 2-5
        # flicks, 6/7 circles), bits 12-15 = gesture class (1 flick,
        # 2 circle), bit 16 = edge-flick flag, bit 31 = recognition in
        # progress. A code of 0 -- which includes the sensor's
        # "recognition in progress" frames (word 00 00 00 80 in the vendor
        # trace) -- emits no event, exactly as hid_mapping.md §2 requires.
        gesture_word = (d_gesture[0]
                        | d_gesture[1] << 8
                        | d_gesture[2] << 16
                        | d_gesture[3] << 24)

        # Carry the decoded attributes into the events: they become module
        # state (like x/y/z) for the dispatched handler to read, and the
        # replay harness snapshots them onto every gesture record.
        gesture = gesture_word & 0xFF                 # bits 0-7: code
        gesture_class = (gesture_word >> 12) & 0xF    # bits 12-15
        gesture_edge = bool(gesture_word & 0x10000)   # bit 16

        gestures = [
            ('garbage', '', ''),
            ('flick', 'west', 'east'),
            ('flick', 'east', 'west'),
            ('flick', 'south', 'north'),
            ('flick', 'north', 'south'),
            ('circle', 'clockwise', ''),
            ('circle', 'counter-clockwise', '')
        ]
        for i, g in enumerate(gestures):
            if d_gesture[0] == i + 1:

                if g[0] == 'garbage' and callable(_on_garbage):
                    _on_garbage()

                if g[0] == 'flick' and callable(_on_flick):
                    _on_flick(g[1], g[2])

                if g[0] == 'circle' and callable(_on_circle):
                    _on_circle(g[1])

                break

    if d_configmask & SW_DATA_TOUCH:
        # We have a touch
        d_action = d_touch[1] << 8 | d_touch[0]

        # d_touchcount = d_touch[2] * 5 # Time to touch in ms
        actions = [
            ('touch', 'south'),
            ('touch', 'west'),
            ('touch', 'north'),
            ('touch', 'east'),
            ('touch', 'center'),
            ('tap', 'south'),
            ('tap', 'west'),
            ('tap', 'north'),
            ('tap', 'east'),
            ('tap', 'center'),
            ('doubletap', 'south'),
            ('doubletap', 'west'),
            ('doubletap', 'north'),
            ('doubletap', 'east'),
            ('doubletap', 'center')
        ]

        comp = 0b0000000000000001 << len(actions) - 1
        for action in reversed(actions):
            if d_action & comp:

                handle_touch = False

                if action[0] in _on_touch.keys() and action[1] in _on_touch[action[0]].keys():
                    if not action[0] in _on_touch_last.keys():
                        _on_touch_last[action[0]] = {}
                        handle_touch = True

                    if not action[1] in _on_touch_last[action[0]].keys():
                        _on_touch_last[action[0]][action[1]] = None
                        handle_touch = True

                    elif (millis() - _on_touch_last[action[0]][action[1]]) >= 1000.0 / _on_touch_repeat[action[0]][action[1]]:
                        handle_touch = True

                    if callable(_on_touch[action[0]][action[1]]) and handle_touch:
                        _on_touch[action[0]][action[1]]()
                        _on_touch_last[action[0]][action[1]] = millis()

                if action[0] in _on_touch.keys() and 'all' in _on_touch[action[0]].keys():
                    if not action[0] in _on_touch_last.keys():
                        _on_touch_last[action[0]] = {}
                        handle_touch = True

                    # The repeat limiter tracks the last firing PER ZONE: a
                    # frame may carry several set electrodes at once (every
                    # one dispatches — see the loop note), and two zones firing
                    # in the same frame must not suppress each other through a
                    # shared timestamp (P3.10; the shared 'all' slot was
                    # harmless only while the loop dispatched at most one
                    # action per frame).
                    if action[1] not in _on_touch_last[action[0]].keys():
                        _on_touch_last[action[0]][action[1]] = None
                        handle_touch = True

                    elif (millis() - _on_touch_last[action[0]][action[1]]) >= 1000.0 / _on_touch_repeat[action[0]]['all']:
                        handle_touch = True

                    if callable(_on_touch[action[0]]['all']) and handle_touch:
                        _on_touch[action[0]]['all'](action[1])
                        _on_touch_last[action[0]][action[1]] = millis()

                # No break: EVERY set touch bit dispatches (hid_mapping.md §2
                # "all set touch bits in a frame produce their events"; the
                # old `break` dropped every touch after the first — the
                # Python half of deviation D4, fix item P3.10).
            comp = comp >> 1

    if d_configmask & SW_DATA_AIRWHEEL and d_sysinfo & 0b00000010:
        # Airwheel
        # The sensor counts rotation with a free-running 8-bit counter that
        # wraps 255->0 (32 counts = one revolution, so 1 count = 11.25
        # degrees). A hand re-entering the sensing field finds the counter
        # at an arbitrary value, so the first valid frame after a gap in
        # AirWheel-valid data only establishes the baseline and emits
        # nothing.
        if _lastrotation is None:
            _lastrotation = d_airwheel[0]
        else:
            # Signed 8-bit difference: crossing 255->0 while counting
            # clockwise is +1 step, not -255.
            delta = ((d_airwheel[0] - _lastrotation + 128) % 256) - 128
            degrees = delta * 11.25

            # Delta is in degrees, with 32 counts = full 360 degree rotation
            # Positive numbers equal clockwise delta, negative are counter-clockwise
            if degrees != 0:
                if callable(_on_airwheel):
                    _on_airwheel(degrees)

                rotation += degrees

                if rotation < 0:
                    rotation = 0

                if rotation > 1000:
                    rotation = 1000

            _lastrotation = d_airwheel[0]
    else:
        # This frame carries no valid AirWheel data: the counter may have
        # free-run meanwhile, so re-baseline on the next valid frame.
        _lastrotation = None


def _handle_status_info(data):
    # System_Status (0x15) receive format (Interface.pdf §4.1; example in
    # §3.6, Table 3-8): payload byte 0 = MsgID (the control message being
    # acknowledged, e.g. Set_Runtime_Parameter 0xA2 = 170), byte 1 =
    # MaxCmdSize (informational), bytes 2-3 = ErrorCode little-endian
    # ("0" = the command was applied correctly).
    global system_status, system_status_error

    system_status = data[0]
    system_status_error = data[3] << 8 | data[2]

    if callable(_on_system_status):
        _on_system_status(system_status, system_status_error)


def _handle_firmware_info(data):
    print('Got firmware info')

    d_fw_valid = data[0]
    # d_hw_rev = data[1] | data[2] << 8
    # d_param_st = data[3]
    # d_loader_version = data[4:7]
    # d_fw_st = data[7]

    global fw_valid, fw_version

    # The FwValid state travels with every report; the version string is
    # only meaningful for a valid image (below). Fix item P3.11b: both are
    # also surfaced as module state (like x/y/z) for handlers to read, and
    # a registered `fw_version()` handler receives the NUL-stripped string.
    fw_valid = d_fw_valid
    fw_version = ''

    # Interface.pdf §4.3 (Table 4-6) defines exactly three FwValid values:
    # 0xAA = a valid GestIC Library is available, 0x00 = empty, 0x0A = an
    # invalid library was stored or the last firmware update failed. Only an
    # exact 0xAA counts as valid — any other value is undefined, and even a
    # "0x00-like" spelling such as 0x0A must not be read as valid firmware.
    if d_fw_valid == 0xAA:
        # The version string is only meaningful for a valid image: with an
        # empty or invalid library (or undefined values), those 120 bytes are
        # not a version string at all. The field is NUL-padded, so strip at
        # the first NUL (the canonical/decoder-level record carries exactly
        # the readable string).
        fw_version = ''.join(map(chr, data[8:])).split('\x00')[0]

        print(fw_version)

        if callable(_on_firmware_version):
            _on_firmware_version(fw_version)

    elif d_fw_valid == 0x00:
        raise Exception("No valid GestIC Library could be located")

    elif d_fw_valid == 0x0A:
        raise Exception("An invalid GestiIC Library was stored, or the last update failed")

    else:
        raise Exception("Unknown GestIC Library status (FwValid 0x%02X)" % d_fw_valid)


def _do_poll():
    global io_error_count

    time.sleep(0.001)

    if not _enable_events:
        return True

    if not GPIO.input(SW_XFER_PIN):
        '''
        Assert transfer line low to ensure
        MGC3130 doesn't update data buffers
        '''
        GPIO.setup(SW_XFER_PIN, GPIO.OUT, initial=GPIO.LOW)

        try:
            data = i2c.read_i2c_block_data(SW_ADDR, 0x00, 26)
            io_error_count = 0

        except IOError:
            io_error_count += 1
            if io_error_count > 10:
                raise Exception("Skywriter encoutered nore than 10 consecutive I2C IO errors!")
            return False

        # Size-aware frame reads (fix item P3.11c). The Size field (frame
        # byte 0, Interface.pdf §3.3) counts the whole message INCLUDING
        # this 4-byte header — e.g. 0x84 = 132 bytes for Fw_Version_Info
        # (§3.5.1) — and the protocol recommends sizing the read from it
        # (§2.3 note 1). The first read asks 26 bytes so the classic
        # full-layout sensor frame stays a single read; a longer message is
        # fetched with continuation reads while the transfer (TS) pin is
        # still asserted, chunked at 32 bytes because of the SMBus cap
        # above — a complete 132-byte frame therefore arrives as
        # 26 + 32 + 32 + 32 + 10. The sensor is expected to continue its
        # buffer across the reads of one asserted transfer; confirming that
        # continuation on real hardware is recorded in fix item P4.1.
        d_size = data[0]

        while 4 <= d_size <= SW_MAX_MESSAGE_SIZE and len(data) < d_size:
            try:
                rest = i2c.read_i2c_block_data(
                    SW_ADDR, 0x00, min(SW_I2C_READ_CHUNK, d_size - len(data)))
                io_error_count = 0

            except IOError:
                io_error_count += 1
                if io_error_count > 10:
                    raise Exception("Skywriter encoutered nore than 10 consecutive I2C IO errors!")
                return False

            if not rest:
                # The buffer gave nothing more: the frame cannot be
                # completed, so do not dispatch a half-read message.
                break

            # Never keep more than the Size field promises: a continuation
            # that answers beyond the message end (sensor padding, or a
            # mocked bus over-answering the request count) must not spill
            # into the payload dispatch below.
            data += rest[:d_size - len(data)]

        # d_flags = data[1]
        # d_seq = data[2]

        # Dispatch only complete frames, and dispatch them WITHOUT their
        # header: payload = the frame's Size-field byte range minus the
        # 4-byte header (size, flags, sequence, message ID), so the handlers
        # index payload offsets from 0 (the P3.3 off-by-four contract). A
        # Size field under 4 can only be corrupt, and a read that could not
        # be completed up to d_size is a partial frame: both are skipped for
        # this poll cycle instead of being decoded half-read, but the
        # transfer line is still released below.
        if d_size >= 4 and len(data) >= d_size:
            payload = data[SW_HEADER_SIZE:d_size]

            d_ident = data[3]

            if d_ident == 0x91:
                _handle_sensor_data(payload)

            elif d_ident == 0x15:
                _handle_status_info(payload)

            elif d_ident == 0x83:
                _handle_firmware_info(payload)

        GPIO.setup(SW_XFER_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    return True


def _start_poll():
    global _worker
    if _worker is None:
        _worker = AsyncWorker(_do_poll)
    _worker.start()


def _stop_poll():
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None


def flick(*args, **kwargs):
    '''Bind flick event'''

    setup()

    def register(handler):
        global _on_flick
        _on_flick = handler

    return register


def touch(*args, **kwargs):
    '''Bind touch event

    :param repeat_rate: Max number of times/second to fire the touch event
    :param position: Position of touch to watch- north, south, east, west, center
    '''
    global _on_touch, _on_touch_repeat

    setup()

    t_position = kwargs.get('position', 'all')
    t_repeat_rate = kwargs.get('repeat_rate', 4)

    if 'touch' not in _on_touch.keys():
        _on_touch['touch'] = {}
    if 'touch' not in _on_touch_repeat.keys():
        _on_touch_repeat['touch'] = {}

    def register(handler):
        global _on_touch, _on_touch_repeat
        _on_touch['touch'][t_position] = handler
        _on_touch_repeat['touch'][t_position] = t_repeat_rate

    return register


def tap(*args, **kwargs):
    '''Bind tap event

    :param repeat_rate: Max number of times/second to fire the touch event
    :param position: Position of tap to watch- north, south, east, west, center
    '''
    global _on_touch, _on_touch_repeat

    setup()

    t_position = kwargs.get('position', 'all')
    t_repeat_rate = kwargs.get('repeat_rate', 4)

    if 'tap' not in _on_touch.keys():
        _on_touch['tap'] = {}
    if 'tap' not in _on_touch_repeat.keys():
        _on_touch_repeat['tap'] = {}

    def register(handler):
        global _on_touch, _on_touch_repeat
        _on_touch['tap'][t_position] = handler
        _on_touch_repeat['tap'][t_position] = t_repeat_rate

    return register


def double_tap(*args, **kwargs):
    '''Bind double tap event

    :param repeat_rate: Max number of times/second to fire the double tap event
    :param position: Position of double tap to watch- north, south, east, west, center
    '''
    global _on_touch, _on_touch_repeat

    setup()

    t_position = kwargs.get('position', 'all')
    t_repeat_rate = kwargs.get('repeat_rate', 4)

    if 'doubletap' not in _on_touch.keys():
        _on_touch['doubletap'] = {}
    if 'doubletap' not in _on_touch_repeat.keys():
        _on_touch_repeat['doubletap'] = {}

    def register(handler):
        global _on_touch
        _on_touch['doubletap'][t_position] = handler
        _on_touch_repeat['doubletap'][t_position] = t_repeat_rate

    return register


def garbage():
    '''Bind an action to the "garbage" gesture

    A sort of grab-and-throw-away-garbage above the Skywriter
    '''

    setup()

    def register(handler):
        global _on_garbage
        _on_garbage = handler

    return register


def circle(*args, **kwargs):
    '''Bind an action to the circle gestures

    The handler receives the direction as a string:
    'clockwise' or 'counter-clockwise'.

    Note: the sensor only recognizes circles while its AirWheel feature is
    disabled (a free-standing "grab and twist" recognition mode); the default
    setup() enables AirWheel, so in that configuration no circle events arrive.
    '''

    setup()

    def register(handler):
        global _on_circle
        _on_circle = handler

    return register


def move():
    '''Bind an action to move

    The handler will receive x, y and z values
    describing the tracked finger in 3D space above
    the Skywriter.
    '''

    setup()

    def register(handler):
        global _on_move
        _on_move = handler

    return register


def airwheel():
    '''Bind an action to the "airhweel" gesture

    Point your finger at the Skywriter and spin it in a wheel
    The handler will receive a rotation delta in degrees
    '''

    setup()

    def register(handler):
        global _on_airwheel
        _on_airwheel = handler

    return register


def system_status():
    '''Bind an action to System_Status control messages (ID 0x15)

    The handler receives the acknowledged control message's ID and its
    16-bit error code: system_status(msg_id, error). msg_id is e.g.
    Set_Runtime_Parameter (0xA2 = 170), and error 0 means the control
    message was applied correctly (Interface.pdf §3.6 / Table 3-8).
    '''

    setup()

    def register(handler):
        global _on_system_status
        _on_system_status = handler

    return register


def fw_version():
    '''Bind an action to Fw_Version_Info control messages (ID 0x83)

    The handler receives the version string — only delivered when the
    sensor reports a valid GestIC library (FwValid 0xAA, Interface.pdf
    §4.3 Table 4-6). The last report's FwValid byte and NUL-stripped
    string are also available as the `fw_valid` / `fw_version` module
    state, like x/y/z.
    '''

    setup()

    def register(handler):
        global _on_firmware_version
        _on_firmware_version = handler

    return register


def _exit():
    _stop_poll()
    if GPIO is not None:
        GPIO.cleanup()


def setup():
    global i2c, _is_setup

    if _is_setup:
        return True

    _is_setup = True

    i2c = SMBus(i2c_bus)

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(SW_RESET_PIN, GPIO.OUT, initial=GPIO.HIGH)
    GPIO.setup(SW_XFER_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    atexit.register(_exit)

    def print_hex(data):
        if _debug:
            print(" ".join([hex(x) for x in data]))

    def get_status(id):
        for x in range(10):
            time.sleep(0.001)
            GPIO.setup(SW_XFER_PIN, GPIO.OUT, initial=GPIO.LOW)
            data = i2c.read_i2c_block_data(SW_ADDR, 0x00, 26)
            GPIO.setup(SW_XFER_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            if data[3] == 0x15 and data[4] == id:
                print_hex(data)
                return True

        return False

    reset()

    #                                 Size  Flags  Seq   ID      Command        Reserved      Argument 0                     Argument 1
    # Command, Argument 1 and Argument 2 are sent LSByte first, so 1 = 0x01 0x00 etc

    # Enable AirWheel, requires 0x20 to be sent in Argument 0 and 1
    if _debug:
        print("Enable AirWheel")
    i2c.write_i2c_block_data(SW_ADDR, 0x10, [0x00, 0x00, 0xA2,   0x90, 0x00,    0x00, 0x00,  0x20, 0x00, 0x00, 0x00,         0x20, 0x00, 0x00, 0x00])  # noqa: E241
    if not get_status(0xA2):
        raise RuntimeError("Invalid response for SET_RUNTIME_PARAMETER")

    # Enable all gestures and X/Y/Z data, 0 = Garbage, 1 = Flick WE, 2 = Flick EW, 3 = Flick SN, 4 = Flick NS, 5 = Circle CW, 6 = Circle CCW
    if _debug:
        print("Enable all gestures")
    i2c.write_i2c_block_data(SW_ADDR, 0x10, [0x00, 0x00, 0xA2,   0x85, 0x00,    0x00, 0x00,   0b01111111, 0x00, 0x00, 0x00,  0b01111111, 0x00, 0x00, 0x00])  # noqa: E241
    if not get_status(0xA2):
        raise RuntimeError("Invalid response for SET_RUNTIME_PARAMETER")

    # Enable all data output 0 = DSP, 1 = Gesture, 2 = Touch, 3 = AirWheel, 4 = Position
    if _debug:
        print("Enable all data output")
    i2c.write_i2c_block_data(SW_ADDR, 0x10, [0x00, 0x00, 0xA2,   0xA0, 0x00,    0x00, 0x00,   0b00011111, 0x00, 0x00, 0x00,  0b00011111, 0x00, 0x00, 0x00])  # noqa: E241
    if not get_status(0xA2):
        raise RuntimeError("Invalid response for SET_RUNTIME_PARAMETER")

    # Disable auto-calibration
    if not _enable_auto_calibration:
        if _debug:
            print("Disable auto-calibration")
        i2c.write_i2c_block_data(SW_ADDR, 0x10, [0x00, 0x00, 0xA2,   0x80, 0x00,   0x00, 0x00,   0x00, 0x00, 0x00, 0x00,        0b00011111, 0x00, 0x00, 0x00])  # noqa: E241
        if not get_status(0xA2):
            raise RuntimeError("Invalid response for SET_RUNTIME_PARAMETER")

    _start_poll()
