"""Static pins on the BLE HID firmware sketch (fix items P3.16 + P3.17).

The firmware sketch `pico-arduino/SkywriterController/SkywriterController.ino`
implements the device-identity / bring-up rules of `specs/ble_hid.md` §4:

- `AC-BLE-01` — the device advertises as `Skywriter HID` with a HID-class
  appearance (appearance value chosen inside `KeyboardBLE.begin` via
  `__BLEGetAppearance()`);
- `AC-BLE-02` — ONE composite HID device: both `MouseBLE` + `KeyboardBLE`
  libraries linked (their weak-install hooks merge every descriptor into a
  single Report Map), `startHID` called exactly once via exactly one
  `begin()`;
- the P3.16 sensor bring-up note: the firmware sends the four
  Set_Runtime_Parameter (0xA2) configuration commands itself (the stock
  `Skywriter.begin()` does not configure the sensor), each the 0x10 control
  write followed by EXACTLY 15 payload bytes.

The P3.17 pins below carry the pairing / battery / connection-lifecycle
rules of `specs/ble_hid.md` §5, §6, §8 (AC-BLE-03, AC-BLE-07 software side;
the RF truth is the Phase-4 hardware probes): battery = 100 % at connect
via the direct battery API, the neutral resync report on (re)connect,
sensor events dropped while unconnected, held state released on link loss,
advertising restarted on link loss, and the callback-context deadlock rule.

Radio/GATT/RF truth is the Phase-4 hardware probes; these source-level pins
only make a software regression (e.g. a reintroduced second `begin()`) fail
`bash run_tests.sh` immediately.
"""
import re
import pathlib

SKETCH = (pathlib.Path(__file__).resolve().parents[1]
          / "pico-arduino" / "SkywriterController" / "SkywriterController.ino")


def sketch_source():
    return SKETCH.read_text()


def sketch_code():
    """The sketch with C-style and line comments stripped, so code-level
    assertions (call counts, identifiers) see only executable text."""
    src = re.sub(r"/\*[\s\S]*?\*/", "", sketch_source())
    return "\n".join(line.split("//")[0] for line in src.splitlines())


def function_body(name):
    """The executable body of function `name`, from the comment-stripped
    source (braces counted, so nested blocks stay inside)."""
    src = sketch_code()
    m = re.search(r"(?:static\s+\w[\w\s&*]*?)?(\b" + re.escape(name)
                  + r")\s*\([^)]*\)\s*\{", src)
    assert m, f"function {name} not found"
    start = m.end()
    depth = 1
    i = start
    while i < len(src) and depth > 0:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
        i += 1
    return src[start:i - 1]


# ---------------------------------------------------------------- AC-BLE-01

def test_device_name_is_skywriter_hid():
    """The sketch's advertisement / device-name constant is `Skywriter HID`
    (specs/ble_hid.md §4, AC-BLE-01)."""
    src = sketch_source()
    assert 'SKYWRITER_DEVICE_NAME[] = "Skywriter HID"' in src


def test_device_name_used_for_both_name_slots():
    """The single name constant feeds both the advertisement (`localName`)
    and the HID attribute (`hidName`) — the composite begins with the
    device name, not a library default ("PicoW BLE Keyboard")."""
    src = sketch_code()
    m = re.search(r"KeyboardBLE\.begin\(([^;]*)\);", src)
    assert m, "the sketch must call KeyboardBLE.begin()"
    args = m.group(1)
    assert args.count("SKYWRITER_DEVICE_NAME") == 2, (
        "both begin() name arguments must be SKYWRITER_DEVICE_NAME, got: "
        f"{args!r}")


# ---------------------------------------------------------------- AC-BLE-02

def test_single_begin_single_starthid():
    """Exactly one begin() runs — KeyboardBLE's (AC-BLE-02: `startHID` runs
    inside either library's `begin()`, so a second `begin()` would start the
    HID transport twice)."""
    begins = re.findall(r"\bMouseBLE\.begin\(|\bKeyboardBLE\.begin\(",
                        sketch_code())
    assert begins == ["KeyboardBLE.begin("], (
        "exactly one *BLE.begin() call must exist, got: {}".format(begins))


def test_both_hid_libraries_linked():
    """AC-BLE-02's composite Report Map needs BOTH libraries linked (their
    weak-install hooks are merged by `__SetupHIDreportmap`): the sketch must
    include and actually use both objects."""
    src = sketch_source()
    assert "#include <MouseBLE.h>" in src
    assert "#include <KeyboardBLE.h>" in src
    # MouseBLE drives the pointer/button/wheel reports...
    assert re.search(r"MouseBLE\.move\(", src), "MouseBLE.move must be used"
    assert re.search(r"MouseBLE\.(press|release)\(", src), (
        "MouseBLE press/release must be used (touch-hold buttons)")
    # ...KeyboardBLE drives the keyboard and consumer (media) reports.
    assert re.search(r"KeyboardBLE\.press\(", src), "KeyboardBLE.press used"
    assert re.search(r"KeyboardBLE\.consumerPress\(", src), (
        "KeyboardBLE.consumerPress used")


def test_mouse_enable_bit_without_second_begin():
    """The mouse's `begin()` is skipped on purpose (it would call `startHID`
    twice); the sketch must set the public base-class enable bit instead,
    with a comment explaining the reasoning."""
    src = sketch_source()
    m = re.search(r"HID_Mouse&\s+(\w+)\s*=\s*MouseBLE;[\s\S]*?\1\._running\s*="
                  r"\s*true;", src)
    assert m, ("the sketch must set HID_Mouse::_running via a base up-cast "
               "(MouseBLE.begin would startHID twice)")
    # The comment must explain WHY the begin() is skipped.
    around = src[max(0, m.start() - 400):m.end() + 100]
    assert ("twice" in around or "second" in around), (
        "the mouse-enable workaround must document the double-start reason")


def test_battery_starts_at_100():
    """§8: the Battery Service must carry a sane value from the start —
    `startHID` derives it from `KeyboardBLE.begin`'s default battery=100 —
    and the sketch pins that in its comments."""
    src = sketch_source()
    assert "Battery Service starts at 100 %" in src


# ------------------------------------------------- sensor bring-up (P3.16)

def test_four_runtime_commands_sent_by_firmware():
    """The firmware configures the sensor itself: four Set_Runtime_Parameter
    command payload blocks must be defined and all four must be queued in
    `configure_sensor` (the stock `Skywriter.begin()` does not configure the
    sensor — the Python driver's `setup()` is the reference)."""
    src = sketch_source()
    for name in ("RUNTIME_ENABLE_AIRWHEEL",
                 "RUNTIME_ENABLE_GESTURES",
                 "RUNTIME_ENABLE_DATA_OUTPUT",
                 "RUNTIME_DISABLE_AUTO_CALIBRATION"):
        assert f"const unsigned char {name}[" in src, f"missing {name}"
        assert f"    {name}," in src, f"{name} not queued in configure_sensor"


def test_runtime_payloads_match_python_reference():
    """The four 15-byte Set_Runtime_Parameter payloads are byte-for-byte the
    Python driver's `setup()` writes (fix item P3.16: 'the same payload the
    Python setup() writes')."""
    src = sketch_source()
    for block in (
        # Enable AirWheel: 0x20 in both arguments.
        "0x00, 0x00, 0xA2,   0x90, 0x00,   0x00, 0x00,\n"
        "  0x20, 0x00, 0x00, 0x00,\n"
        "  0x20, 0x00, 0x00, 0x00",
        # Enable all gestures + position.
        "0x00, 0x00, 0xA2,   0x85, 0x00,   0x00, 0x00,\n"
        "  0x7F, 0x00, 0x00, 0x00,\n"
        "  0x7F, 0x00, 0x00, 0x00",
        # Enable all data output.
        "0x00, 0x00, 0xA2,   0xA0, 0x00,   0x00, 0x00,\n"
        "  0x1F, 0x00, 0x00, 0x00,\n"
        "  0x1F, 0x00, 0x00, 0x00",
        # Disable auto-calibration.
        "0x00, 0x00, 0xA2,   0x80, 0x00,   0x00, 0x00,\n"
        "  0x00, 0x00, 0x00, 0x00,\n"
        "  0x1F, 0x00, 0x00, 0x00",
    ):
        assert block in src, f"runtime payload missing/changed:\n{block}"


def test_control_write_followed_by_exactly_15_payload_bytes():
    """Each Set_Runtime_Parameter command is the 0x10 control write followed
    by EXACTLY 15 payload bytes — the loop bound must be the named constant
    (never a 16-step copy over a 15-element array — the removed deviation
    D2's shape)."""
    src = sketch_source()
    assert "SW_SET_RUNTIME_PAYLOAD_SIZE = 15" in src
    m = re.search(
        r"for\s*\(\s*unsigned char\s+\w+\s*=\s*0;\s*\w+\s*<"
        r"\s*SW_SET_RUNTIME_PAYLOAD_SIZE\s*;", src)
    assert m, "payload copy loop must be bounded by the 15-byte constant"


def test_every_command_waits_for_system_status_ack():
    """The firmware waits for each command's System_Status (0x15) frame and
    denies boot on failure (the Python driver raises) — the serial probe
    must be able to distinguish a misconfigured sensor."""
    src = sketch_source()
    assert "sensor_wait_system_status(SW_SET_RUNTIME)" in src
    assert "SKYSTATE sensor_config_failed" in src, (
        "a failed acknowledgment must print a visible serial line")
    assert "SKYSTATE sensor_ok" in src, "successful bring-up is pinned too"


# ------------------------------------------------------------- wiring pins

def test_mapper_receives_all_canonical_events():
    """Every decoded sensor stream is wired into the mapping engine: XYZ
    position, touch/tap/doubletap, gesture codes, AirWheel rotation — and
    the engine's tick() runs every loop iteration (the engine's timing is
    driven by the caller)."""
    src = sketch_source()
    assert "Skywriter.onXYZ(" in src
    assert "Skywriter.onTouch(" in src
    assert "Skywriter.onGesture(" in src
    assert "Skywriter.onAirwheel(" in src
    assert "mapper.onPosition(" in src
    assert "mapper.onTouch(" in src
    assert "mapper.onGesture(" in src
    assert "mapper.onAirwheel(" in src
    assert re.search(r"mapper\.tick\(\s*now", src)


def test_touch_code_mapping_covers_all_codes():
    """The driver's touch codes 0..14 (skywriter.h SW_DOUBLETAP_/SW_TAP_/
    SW_TOUCH_) map onto the engine's five zones and three kinds, in
    families of five ordered center, east, north, west, south."""
    src = sketch_source()
    m = re.search(
        r"static const SensorZone by_offset\[5\]\s*=\s*\{([^}]*)\}", src)
    assert m, "the zone table must exist"
    zone_ids = [z.strip() for z in m.group(1).split(",")]
    assert zone_ids == ["ZONE_CENTER", "ZONE_EAST", "ZONE_NORTH", "ZONE_WEST",
                        "ZONE_SOUTH"], zone_ids
    assert "code % 5" in src  # zone = (code mod 5) into the table
    # Family 0 = doubletap, 1 = tap, 2 = touch-hold (codes 0..4 / 5..9 / 10..14).
    assert re.search(r"if\s*\(code\s*<\s*5\)\s*return\s+TOUCH_DOUBLETAP", src)
    assert re.search(r"if\s*\(code\s*<\s*10\)\s*return\s+TOUCH_TAP", src)
    assert re.search(r"return\s+TOUCH_HOLD;", src)


def test_link_state_is_reported_to_the_serial_console():
    """specs/ble_hid.md §6: link (and bring-up) state goes to the serial
    console for the hardware probe."""
    src = sketch_source()
    assert "SKYSTATE ble_connected" in src
    assert "SKYSTATE ble_advertising" in src
    assert "SKYSTATE hid_started" in src
    assert "SKYWRITER-HID boot" in src


# ------------------------------------- P3.17: pairing, battery, lifecycle ---
# (specs/ble_hid.md §5, §6, §8 — AC-BLE-03 / AC-BLE-07 software side; the
# RF truth of these rules is the Phase-4 hardware probes P4.2/P4.3.)

def test_pairing_needs_no_sketch_code_and_bond_store_truth_is_documented():
    """§5: pairing (Just Works + numeric comparison) and bonding live in
    the core's Security Manager; the sketch documents that — including the
    FLASH-BACKED bond store of this core version (P3.17b resolved the old
    RAM-only assumption; see the note above) and the AC-BLE-06 hardware
    gate."""
    src = sketch_source()
    assert "Just Works" in src
    assert "numeric comparison" in src
    assert "bonding" in src
    assert "AC-BLE-06" in src and "FLASH-BACKED" in src, (
        "the sketch must document the core's flash-backed bond store "
        "(the AC-BLE-06 hardware gate)")


def test_battery_reported_100_at_connect_via_direct_api():
    """§8: battery = 100 % is refreshed at connect — through
    `PicoBluetoothBLEHID.setBattery()` directly, never through
    `MouseBLE.setBattery()` (its `_running` gate is never set by the
    core, so the wrapper silently does nothing)."""
    body = function_body("loop")
    assert "PicoBluetoothBLEHID.setBattery(100)" in body
    assert not re.search(r"MouseBLE\.setBattery", sketch_code()), (
        "MouseBLE.setBattery must not be called (unusable core-level bug)")
    assert "SKYSTATE ble_resync battery=100" in sketch_source()


def test_neutral_resync_report_on_connect():
    """§6 / AC-BLE-07: on (re)connect exactly one neutral report (no
    buttons, zero deltas, zero wheel) resyncs the host state; a lost
    media-key release is wiped by the zero consumer report too."""
    body = function_body("loop")
    assert "MouseBLE.move(0, 0, 0)" in body
    assert "KeyboardBLE.consumerRelease()" in body
    battery_at = body.index("setBattery(100)")
    resync_at = body.index("MouseBLE.move(0, 0, 0)")
    assert battery_at < resync_at, (
        "battery refresh and resync both belong to the connect drain")
    assert "SKYSTATE ble_resync" in sketch_source()


def test_callbacks_are_flag_only_no_hid_send_from_the_radio_context():
    """The Bluetooth stack's callbacks run in the stack's own context;
    `PicoBluetoothBLEHID.send()` busy-waits on that same context's
    send-completion round trip — a send from a callback deadlocks. The
    opened/closed handlers therefore only set flags (closed restarts
    advertising, the one BTstack call that is canonical there), and the
    reasoning stays documented in the sketch."""
    for name in ("on_ble_opened", "on_ble_closed"):
        body = function_body(name)
        for forbidden in (r"MouseBLE\.", r"KeyboardBLE\.",
                          r"PicoBluetoothBLEHID\.send",
                          r"PicoBluetoothBLEHID\.setBattery"):
            assert not re.search(forbidden, body), (
                f"{name} must not touch the HID send API: {forbidden}")
    assert "ble_connect_event = true" in function_body("on_ble_opened")
    assert "ble_disconnect_event = true" in function_body("on_ble_closed")
    assert "busy-wait" in sketch_source(), (
        "the deadlock reasoning must be documented")


def test_advertising_restarts_on_link_loss():
    """AC-BLE-05 (≤ 5 s — here: immediately): the closed callback restarts
    advertising inside the stack's own context."""
    assert "gap_advertisements_enable(1)" in function_body("on_ble_closed")


def test_disconnect_releases_all_held_state():
    """§6 link loss: the mapper's public disconnect() releases every held
    hold-row and drops unsent movement; the sketch's own side state — the
    scheduled pulse queue and the wrapper-latched mouse/keyboard state —
    is cleared in the same drain so the resync report is really neutral."""
    body = function_body("loop")
    assert "mapper.disconnect(now)" in body
    assert "pulses_clear()" in body
    assert "MouseBLE.release(MOUSE_ALL)" in body
    assert "KeyboardBLE.releaseAll()" in body
    assert "SKYSTATE ble_dropped" in sketch_source()
    # the serializer never leaves it a stub
    assert "void pulses_clear()" in sketch_code()


def test_unconnected_sensor_events_are_dropped():
    """§6 / AC-BLE-07: sensor events are dropped while no host is
    connected — every sensor→mapper callback gates on the live link state
    and never queues the event; the first suppressed frame prints the
    probe's evidence line."""
    for name in ("on_sensor_xyz", "on_sensor_touch", "on_sensor_gesture",
                 "on_sensor_airwheel"):
        assert "ble_link_open()" in function_body(name), (
            f"{name} must drop events while unconnected")
    assert "sensor_events_dropping_unconnected" in sketch_source()


def test_sensor_callbacks_registered_before_the_radio_starts():
    """A host connecting during bring-up must not fire into unregistered
    callbacks: the opened/closed callbacks are registered before
    KeyboardBLE.begin() powers the radio on."""
    setup_src = function_body("setup")
    assert setup_src.index("PicoBluetoothBLEHID.setOpenedCB") < \
        setup_src.index("KeyboardBLE.begin("), (
        "link callbacks must be registered before the radio starts")
