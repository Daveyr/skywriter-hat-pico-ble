"""Static pins on the BLE HID firmware sketch (fix item P3.16).

The firmware sketch `pico-arduino/SkywriterController/SkywriterController.ino`
implements the device-identity / bring-up rules of `specs/ble_hid.md` §4:

- `AC-BLE-01` — the device advertises as `Skywriter HID` with a HID-class
  appearance (appearance value chosen inside `KeyboardBLE.begin` via
  `__BLEGetAppearance()`);
- `AC-BLE-02` — ONE composite HID device: both `MouseBLE` + `KeyboardBLE`
  libraries linked (their weak-install hooks merge every descriptor into a
  single Report Map), `startHID` called exactly once via exactly one
  `begin()`;
- the fix item's sensor bring-up note: the firmware sends the four
  Set_Runtime_Parameter (0xA2) configuration commands itself (the stock
  `Skywriter.begin()` does not configure the sensor), each the 0x10 control
  write followed by EXACTLY 15 payload bytes.

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
