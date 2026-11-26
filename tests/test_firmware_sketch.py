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

The P3.18 pins carry the §7 performance rules (AC-BLE-04 software side):
move reports paced at the host-negotiated BLE connection interval via the
sketch's BTstack HCI event handler, the [7.5, 15] ms connection-parameter
request that keeps the ≥ 60 Hz pointer-rate floor reachable, and the
serial evidence line the hardware probe reads.

The P3.26 pins carry the boot-gate rules: a failed sensor configuration
is retried from loop() forever (never a permanent boot deny — hardware
session 5's F12 showed the old deny made the whole device invisible),
every failed attempt prints its own evidence line, the radio starts
regardless of the sensor's state, and the health line carries the
configuration outcome.

The P3.27 pins carry the per-link connect-drain latch: the stack's opened
callback fires once per notification-enable write (four to five per
connection), so the battery/resync drain is armed only on the link's
FIRST opened event (latched, cleared on the closed event) — one link
drains exactly once and `ble conn=` counts links.

The P3.31 pins carry the auto-calibration semantics correction + the
genuine-disable experiment: the legacy command-4 payload (Argument0 =
0x00, mask = 0x1F) actually ENABLES all five masked auto-calibration
features (Interface.pdf §4.4.5.3, dspCalOpMode: a bit CLEARED in
Argument0 enables the feature, a bit SET disables it, Argument1 is the
mask — the old "Disable auto-calibration" label had it backwards), the
corrected comments say so, and the genuine disable (Argument0 = 0x1F /
mask = 0x1F) plus the idle-only fallback (0x08/0x08) are compile-time
variants, OFF by default, named on the serial console (`cal=` on the
sensor_ok and health lines) so a capture can never mistake the
experiment build for the default.

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
                 "RUNTIME_AUTO_CALIBRATION"):
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
        # The legacy auto-calibration payload (P3.31 semantics correction:
        # it actually ENABLES all five masked auto-calibration features —
        # the "Disable" label was wrong; see the command-4 comment).
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
    """The firmware waits for each command's System_Status (0x15) frame —
    the Python driver raises on a missing/failed ack. Since P3.26 the
    failure is EVIDENCE and a retry (the old permanent boot deny is gone):
    the failed attempt prints the `sensor_config_retry` line, and
    successful bring-up still prints the `sensor_ok` line the serial
    probe asserts on."""
    src = sketch_source()
    assert "sensor_wait_system_status(SW_SET_RUNTIME)" in src
    assert "SKYSTATE sensor_ok" in src, "successful bring-up is pinned too"
    assert "SKYSTATE sensor_config_retry" in src, (
        "a failed acknowledgment must print a visible serial line — and "
        "since P3.26 that line is a retry report, not a boot denial")


# --------------------------------- P3.26: the boot gate never denies boot ---
# (Hardware session 5's F12: on cold boots where the sensor missed one
# configuration acknowledgment, configure_sensor() printed
# `sensor_config_failed` forever and the radio never started — the device
# was invisible to every host exactly when evidence was most needed. The
# physical cause (the starving supply) is fixed on the bench; the deny
# DESIGN must never come back.)

def test_boot_never_denies_on_sensor_config_failure():
    """No permanent deny: the old `sensor_config_failed` forever-loop is
    gone, setup() cannot block on the sensor beyond one bounded attempt,
    and the radio starts regardless of the sensor's state."""
    src = sketch_source()
    code = sketch_code()
    assert "sensor_config_failed" not in code, (
        "the deny-loop evidence line must be gone (P3.26: a failed sensor "
        "must never make the whole device invisible)")
    assert "for (;;)" not in code, (
        "a permanent loop must not exist anywhere in the sketch")
    setup_body = function_body("setup")
    assert "KeyboardBLE.begin(" in setup_body, (
        "the radio must still start in setup()")
    loop_body = function_body("loop")
    assert "sensor_config_retry_tick(" in loop_body, (
        "the sensor configuration retry runs from loop(), not setup()")


def test_sensor_config_retry_retries_the_whole_sequence():
    """A failed attempt retries the WHOLE four-command sequence from the
    top, forever — the F12 captures failed on cmd_index=0 AND cmd_index=1
    (per-command margin, not one power-on threshold), and a sequence that
    stopped part-way would leave the sensor half-configured."""
    tick = function_body("sensor_config_retry_tick")
    assert "configure_sensor_attempt()" in tick, (
        "the retry must rerun the whole sequence, not resume from the "
        "failed command")
    # The attempt itself iterates all four commands — same queue as the
    # first boot attempt.
    attempt = function_body("configure_sensor_attempt")
    for name in ("RUNTIME_ENABLE_AIRWHEEL",
                 "RUNTIME_ENABLE_GESTURES",
                 "RUNTIME_ENABLE_DATA_OUTPUT",
                 "RUNTIME_AUTO_CALIBRATION"):
        assert name in attempt, f"the attempt must queue {name}"
    # The retry keeps rescheduling itself until it succeeds — never gives
    # up, never stops.
    assert "sensor_config_next_attempt_ms" in tick


def test_sensor_config_retry_prints_per_attempt_evidence():
    """Each failed attempt prints one loud serial line naming the attempt
    number, the command that failed, and how long the attempt took — the
    capture instrument F12 asked for (how long the sensor needed)."""
    src = sketch_source()
    assert "SKYSTATE sensor_config_retry attempt=" in src
    assert "cmd_index=" in src
    assert "elapsed_ms=" in src


def test_sensor_config_success_line_carries_attempts_and_duration():
    """The success line keeps the probe's `SKYSTATE sensor_ok` token and
    now names how many attempts it took and how long the successful
    attempt ran — so a capture shows the sensor's recovery time."""
    src = sketch_source()
    assert "SKYSTATE sensor_ok attempts=" in src
    assert "took_ms=" in src


def test_health_line_reports_sensor_config_outcome():
    """P3.26 part 3: the sensor configuration's outcome lives on the
    health line (`sensor_cfg=` 0/1, `cfg_attempts=N`) instead of gating
    the whole device — a capture sees a deaf sensor and a working radio
    on the same line."""
    body = function_body("print_health_status")
    assert "sensor_cfg=" in body
    assert "sensor_configured" in body
    assert "cfg_attempts=" in body
    assert "sensor_config_attempts" in body


def test_sensor_polling_waits_for_configuration():
    """While the configuration is still retrying, poll() stays off: a poll
    could steal the System_Status acknowledgment frame the waiting
    command is parked on (both read the same sensor buffer over I2C),
    and an unconfigured sensor's padding would pollute the frame
    counters. The retry tick runs first; poll starts only once
    configured."""
    loop_body = function_body("loop")
    tick_at = loop_body.index("sensor_config_retry_tick(")
    gate_at = loop_body.index("if (sensor_configured)")
    poll_at = loop_body.index("Skywriter.poll()")
    assert tick_at < gate_at < poll_at, (
        "loop() must retry the configuration first, then poll only the "
        "configured sensor")


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


# ------------------------------------- P3.27: one drain per link -----------
# (Hardware session 5's btmon capture: the Bluetooth stack's opened callback
# fires once per notification-enable write — the host writes one enable
# switch per report channel, four to five per connection — so the unlatched
# connect drain ran four to five times per SINGLE link: four battery
# notifications, four neutral-report pairs, and a health line that counted
# conn=5 with disc=0. specs/ble_hid.md §6 pins the neutral report "once"
# per (re)connect — the latch is the code catching up with the spec.)

def test_connect_drain_is_latched_per_link():
    """P3.27: the opened callback arms the connect drain only on the
    link's FIRST subscription write (a per-link latch consulted, then
    set, before the arming flag), and the closed callback clears the
    latch so the NEXT link drains again."""
    opened = function_body("on_ble_opened")
    assert "ble_connect_drain_latched" in opened, (
        "the opened callback must consult the per-link drain latch — "
        "unlatched, one link drains once per subscription write")
    guard_at = opened.index("if (ble_connect_drain_latched)")
    set_at = opened.index("ble_connect_drain_latched = true")
    arm_at = opened.index("ble_connect_event = true")
    assert guard_at < set_at < arm_at, (
        "the latch must gate the arming: guard, set, then arm")
    closed = function_body("on_ble_closed")
    assert "ble_connect_drain_latched = false" in closed, (
        "the closed callback must clear the latch — the next link gets "
        "its own drain")


def test_connect_drain_latch_set_and_cleared_exactly_once_each():
    """The latch has exactly one set site (on_ble_opened) and one clear
    site (on_ble_closed); loop() never touches it — a loop-side clear
    would reopen the per-subscription-write storm between two drains."""
    code = sketch_code()
    assert code.count("ble_connect_drain_latched = true") == 1
    # Exactly one clear site — the declaration's `= false` initializer is
    # excluded from the count (lookbehind on its `bool `).
    clears = re.findall(r"(?<!bool )ble_connect_drain_latched = false", code)
    assert len(clears) == 1
    assert "ble_connect_drain_latched = true" in \
        function_body("on_ble_opened")
    assert "ble_connect_drain_latched = false" in \
        function_body("on_ble_closed")
    assert "ble_connect_drain_latched" not in function_body("loop"), (
        "the latch lives on the callback side; loop() drains the armed "
        "flag only")


def test_connect_drain_latch_is_documented_with_its_evidence():
    """The latch declaration must be volatile (the stack's callback
    context writes it) and its comment must carry the WHY (the opened
    callback fires once per subscription write, not once per link) and
    the hardware evidence it explains."""
    src = sketch_source()
    assert "volatile bool ble_connect_drain_latched" in src, (
        "the latch is written from the stack's callback context")
    decl_at = src.index("ble_connect_drain_latched")
    comment = src[:decl_at]
    for token in ("P3.27", "subscription", "once per link", "btmon"):
        assert token in comment, (
            f"the latch comment must name {token!r} — the WHY and the "
            "session-5 evidence belong next to the mechanism")


# ------------------------------------- P3.28: the link-loss reason line ----
# (Session 5's connect/disconnect bounce was root-caused and fixed host-side
# before the failing link's HCI reason code was ever captured — the btmon
# trace recorded the SUCCESSFUL pairing instead. Every future link loss
# must be able to name its own cause from the device side: 0x06 PIN or Key
# Missing = the reflash-orphaned pairing; 0x13/0x16 = the host or the local
# side terminated the connection; 0x08 = the supervision timeout (the
# connection watchdog decided the peer was gone). The wrapper's closed
# callback fires ON the HCI_EVENT_DISCONNECTION_COMPLETE event, and BTstack
# dispatches handlers in registration order, so the sketch's own HCI event
# handler (registered before begin()) sees the event BEFORE the closed
# callback arms the disconnect drain — the reason is already stored when
# loop() prints the dropped line.)

def test_ble_drop_reason_is_decoded_in_the_hci_event_handler():
    """P3.28: the sketch's BTstack HCI event handler decodes the HCI
    (Host Controller Interface — the radio-level event channel)
    Disconnection Complete event's reason code and stores it as public
    state for loop() — the radio-context rule stays: the handler only
    records, never prints, never touches the mapper."""
    body = function_body("on_hci_event")
    assert "HCI_EVENT_DISCONNECTION_COMPLETE" in body, (
        "the disconnection-complete event must be decoded in the HCI "
        "event handler")
    assert "hci_event_disconnection_complete_get_reason(" in body, (
        "the reason code must come from the event-decoding helper, not "
        "a hand-rolled byte offset")
    # Whitespace-tolerant: the assignment may wrap across lines.
    stored = " ".join(body.split())
    assert "ble_drop_reason = hci_event_disconnection_complete_get_reason(" \
        in stored, "the decoded reason must be stored"
    assert "ble_drop_reason_seen = true" in body, (
        "a seen-flag must mark the reason as real event evidence")
    # flag-only radio context, same rule as on_ble_opened/on_ble_closed.
    assert "Serial." not in body, (
        "the HCI handler must not print (the stack's callback context)")
    assert "mapper." not in body


def test_ble_drop_reason_state_is_volatile_and_latest_wins():
    """The reason state is written from the stack's callback context, so it
    is volatile; the snapshot is latest-wins (the twin of P3.24's
    unknown-frame snapshot) — it is NOT reset by the drain."""
    src = sketch_source()
    assert "volatile uint8_t ble_drop_reason" in src
    assert "volatile bool ble_drop_reason_seen" in src
    body = function_body("loop")
    assert "ble_drop_reason = 0" not in body, (
        "the drain must not reset the reason — latest-wins evidence, "
        "not one-shot")


def test_ble_dropped_line_carries_the_reason_code_and_name():
    """The disconnect drain's evidence line names WHY the link dropped:
    `SKYSTATE ble_dropped reason=0xNN <name>` — hex zero-padded, with the
    event's absence reported honestly (defensive: a link loss always
    produces a disconnection-complete event, but the line must not print a
    fake 0x00 if one was never seen)."""
    loop_body = function_body("loop")
    assert "SKYSTATE ble_dropped reason=" in loop_body, (
        "the dropped line must carry the reason")
    assert "ble_drop_reason_seen" in loop_body, (
        "the line must distinguish a real reason code from 'no event seen'")
    assert re.search(r"<\s*0x10.*Serial\.print\('0'\)", loop_body), (
        "the reason hex must print zero-padded")
    assert "ble_drop_reason_name(" in loop_body, (
        "the reason code must be paired with its human-readable name")


def test_ble_drop_reason_names_cover_the_ledger_codes():
    """The name helper covers the codes the work ledger names (0x06 key
    missing = the reflash-orphaned pairing; 0x13/0x16 = the host or local
    side terminated; 0x08 = supervision timeout) and answers 'unknown' for
    every other code — never an empty name."""
    body = function_body("ble_drop_reason_name")
    for code in ("0x06", "0x08", "0x13", "0x16"):
        assert f"case {code}:" in body, f"reason {code} must be named"
    assert "unknown" in body


def test_drop_reason_line_printed_from_loop_not_from_the_callback():
    """The reason print runs in the loop context (alongside the dropped
    lines, per the item) — the callback stays flag-only."""
    loop_body = function_body("loop")
    assert "SKYSTATE ble_dropped reason=" in loop_body
    dropped_at = loop_body.index("SKYSTATE ble_dropped reason=")
    advertising_at = loop_body.index("SKYSTATE ble_advertising")
    assert dropped_at < advertising_at, (
        "the reason line is part of the dropped-lines group")


# ------------------------------------- P3.18: §7 performance (AC-BLE-04) ---
# (Move-report pacing at the LIVE BLE connection interval, with the host's
# negotiated parameters tracked by the sketch's own BTstack HCI event
# handler. The RF truth — does the pointer really sustain ≥ 60 Hz on a
# phone/laptop — is the Phase-4 probe P4.3; these pins fail fast on
# software regressions.)

def test_report_pacing_is_wired_to_the_live_connection_interval():
    """§7 'Report coalescing': the sketch learns the negotiated connection
    interval from the stack (an HCI event handler decoding both the LE
    connection-complete and connection-update subevents) and re-programs
    the engine's move-report cadence in the loop context — never from the
    radio callback (the flag-only context rule)."""
    body = function_body("on_hci_event")
    assert "HCI_EVENT_LE_META" in body
    assert "hci_event_le_meta_get_subevent_code(" in body
    assert "HCI_SUBEVENT_LE_CONNECTION_COMPLETE" in body, (
        "the interval a host chooses at connection time must be captured")
    assert "HCI_SUBEVENT_LE_CONNECTION_UPDATE_COMPLETE" in body, (
        "later host re-negotiations must re-capture the interval too")
    for getter in ("hci_subevent_le_connection_complete_get_conn_interval",
                   "hci_subevent_le_connection_update_complete_get_conn_interval"):
        assert getter in body, f"{getter} must decode the negotiated interval"
    # flag-only in the stack context: the engine is reprogrammed in loop()
    assert "mapper." not in body, (
        "on_hci_event must not touch the mapper (radio context)")
    assert "ble_pace_dirty = true" in body
    loop_body = function_body("loop")
    assert "mapper.set_report_interval_ms(" in loop_body, (
        "loop() must apply the negotiated interval to the engine's cadence")
    # the handler is registered before the radio starts (same ordering rule
    # as the opened/closed callbacks — a host connecting during bring-up
    # must not fire into an unregistered handler)
    setup_src = function_body("setup")
    assert setup_src.index("hci_add_event_handler(") < \
        setup_src.index("KeyboardBLE.begin("), (
        "the HCI event handler must be registered before the radio starts")


def test_pace_request_targets_the_60hz_floor():
    """§7 row 'Pointer report rate ≥ 60 Hz': on connection the sketch asks
    the host to keep the interval inside [7.5, 15] ms (units of 1.25 ms:
    6..12) — the window that makes the floor reachable. Guards against a
    degraded-default host policy going unnoticed until the hardware
    probe."""
    src = sketch_source()
    assert "PACE_MIN_INTERVAL_UNITS = 6" in src, (
        "7.5 ms minimum interval (= 60 Hz at most ±1 report) must be the "
        "low end of the connection-parameter request")
    assert "PACE_MAX_INTERVAL_UNITS = 12" in src, (
        "15 ms — the engine's default REPORT_INTERVAL_MS — must be the "
        "high end of the request")
    body = function_body("on_hci_event")
    assert "gap_request_connection_parameter_update(" in body
    # it is a plain stack request, not the HID send API (callback context)
    assert "PicoBluetoothBLEHID.send" not in body


def test_pace_evidence_line_for_the_hardware_probe():
    """AC-BLE-04's probe reads the applied pace from the serial console:
    the SKYSTATE pace line names the engine's current move-report
    interval."""
    assert "SKYSTATE pace report_interval_ms=" in sketch_source()


def test_pace_resets_on_link_loss():
    """The disconnect drain returns the report cadence to the spec's named
    default (§3 rule 6) — each new host re-negotiates its own interval via
    the HCI watcher."""
    loop_body = function_body("loop")
    disconnect_at = loop_body.index("mapper.disconnect(now)")
    reset_at = loop_body.index(
        "mapper.set_report_interval_ms(SkywriterHIDMapper::REPORT_INTERVAL_MS)")
    assert reset_at > disconnect_at, (
        "the pace reset belongs to the link-loss drain")


# ------------------------------------- P3.24/P3.25: health-line snapshot ---
# (The unknown-frame content snapshot and the sized-read pattern — the
# answer to the hardware session-4 report F7: `other=100%` frames from the
# first poll, traced to the single 132-byte over-read desynchronising the
# sensor's message framing. The sketch prints the snapshot once per health
# line; the read pattern itself is pinned end-to-end through the real
# driver in tests/test_driver_read_pattern.py.)

def test_health_line_prints_the_unknown_frame_snapshot():
    """P3.24: the health line carries the latest undispatched frame's first
    8 bytes (`other_snap=`, colon-separated hex, zero-padded) and the byte
    count the reads actually returned (`other_read=`) — the content
    evidence that separates a shifted 0x91 (misaligned framing), all-0x00
    padding, an all-0xFF wedged slave, and an incomplete frame (known
    identity, read count under the promised Size)."""
    src = sketch_source()
    body = function_body("print_health_status")
    assert "other_snap=" in body, (
        "the health line must print the snapshot's content bytes")
    assert "Skywriter.other_snapshot" in body, (
        "the snapshot bytes come from the driver's public state")
    assert "other_read=" in body
    assert "Skywriter.other_snapshot_read" in body, (
        "the snapshot's actual-read-count comes from the driver's public "
        "state (the requestFrom counts the old code ignored)")
    # Zero-padded two-digit hex per byte, colon-separated — the exact
    # format the hardware session reads off the console.
    assert re.search(r"< 0x10\) Serial\.print\('0'\)", body), (
        "each snapshot byte must print zero-padded")
    assert body.count("Serial.print(':')") == 1, (
        "the eight snapshot bytes are colon-separated")


def test_health_line_snapshot_sits_with_the_other_counter():
    """The snapshot prints together with the `other=` counter it explains,
    so a single health line answers both "how many" and "what"."""
    body = function_body("print_health_status")
    other_at = body.index('" other="')
    snap_at = body.index('" other_snap="')
    events_at = body.index('" events pos="')
    assert other_at < snap_at < events_at


def test_driver_never_overreads_the_sensor_frame():
    """P3.25: the sketch-side sensor code must have no trace of the old
    single-request over-read — the read pattern (26 first, then
    Size-bounded continuations) lives in the shared driver, pinned by
    tests/test_driver_read_pattern.py; this pin keeps the sketch's own
    I2C (Inter-Integrated Circuit) read — the boot acknowledge check —
    at its exact 26 bytes."""
    code = sketch_code()
    m = re.search(r"Wire\.requestFrom\(SW_ADDR, \(unsigned char\)(\d+)\)", code)
    assert m and int(m.group(1)) == 26, (
        "the boot acknowledge read must ask for exactly the classic "
        "26-byte frame")
    assert "SW_MAX_FRAME_SIZE" not in code, (
        "the sketch must not request the longest-frame size — the old "
        "132-byte over-read pattern (P3.11b) must not return here")


# ------------------------------------- P3.21: keyboard usage codes (fix item)
# (Hardware sessions 1 + the 2026-11-17 "N": taps typed letters. Two causes,
# both fixed: the usage constants were 78/79 where the USB HID Usage Tables
# keyboard page gives Page Up 75 / Page Down 78, and the raw usage reached
# KeyboardBLE.press(), which treats 0-127 as ASCII characters — 78 = "N".)

def test_keyboard_usages_corrected_to_75_and_78():
    """The mapping engine's keyboard usage constants are the USB HID Usage
    Tables values: Page Up 0x4B = 75, Page Down 0x4E = 78 (0x4F = 79 is
    Right Arrow) — cross-checked against the core's key table
    (KEY_PAGE_UP = 0xD3 = 136 + 75, KEY_PAGE_DOWN = 0xD6 = 136 + 78)."""
    header = (pathlib.Path(__file__).resolve().parents[1] / "pico-arduino"
              / "SkywriterHID" / "src" / "SkywriterHIDMapper.h").read_text()
    assert "HID_USAGE_PAGE_UP = 75" in header
    assert "HID_USAGE_PAGE_DOWN = 78" in header
    assert "HID_USAGE_PAGE_UP = 78" not in header, (
        "the old wrong constant (78 = the corrected Page Down) must not "
        "survive anywhere")


def test_no_raw_keyboard_usage_reaches_press_or_release():
    """The Bluetooth keyboard library's press()/release() treat values
    0-127 as ASCII characters (raw usage 78 typed the letter "N") and only
    values 136 and up as non-printing keys (usage = value - 136). Every
    keyboard press AND release in the sketch must go through the
    non-printing-range offset, and no call site may pass a raw usage."""
    code = sketch_code()
    assert "KEYBOARD_NON_PRINTING_OFFSET = 136" in code, (
        "the non-printing range offset must exist as a named constant")
    # Every KeyboardBLE.press/release call in the sketch lives in
    # pulse_fire and applies the offset to the usage.
    calls = re.findall(r"KeyboardBLE\.(press|release)\((.*?\n?.*?)\);",
                       code)
    assert calls, "the sketch must press/release the keyboard somewhere"
    for action, arg in calls:
        assert "KEYBOARD_NON_PRINTING_OFFSET" in arg, (
            f"KeyboardBLE.{action}({arg!r}) must add the non-printing "
            f"range offset — a raw usage would be typed as a letter")
    # The known-bad shapes must never return.
    assert "KeyboardBLE.press((uint8_t)usage)" not in code
    assert "KeyboardBLE.release((uint8_t)usage)" not in code
    # The sink's keyboardPress keeps the RAW usage (the conversion happens
    # exactly once, in pulse_fire, for both press and release).
    sink_region = code[code.index("void keyboardPress"):
                       code.index("void consumerPress")]
    assert "usage" in sink_region and "KEYBOARD_NON_PRINTING_OFFSET" \
        not in sink_region, (
        "the conversion must happen once, in pulse_fire — not also in the "
        "sink (a double offset would send usage + 272)")
    # The ASCII-typing reason must stay documented next to the constant.
    assert "ASCII" in sketch_source()


# ------------------------------------- P3.22: health counters (fix item) ---
# (The hardware gate P4.0a's main instrument: with no oscilloscope or logic
# analyser, these counters are the only view of the transfer line and the
# failed reads over time. The sensor-side read counters live in the shared
# driver library as public state — see tests/test_driver_ts_pin.py for the
# release behaviour they sit next to.)

def test_health_status_line_printed_every_two_seconds():
    """The sketch prints one `SKYSTATE health` status line every 2 s with:
    uptime, the library's read counters with their shares (short reads and
    transfer-line-low polls as a fraction of all polls — visible without
    arithmetic), frames by message type, dispatched/dropped sensor events,
    HID reports by kind, and Bluetooth connects/disconnects."""
    src = sketch_source()
    code = sketch_code()
    assert "SKYSTATE health uptime_ms=" in src
    assert "HEALTH_INTERVAL_MS = 2000" in src
    body = function_body("print_health_status")
    for token in ("Skywriter.polls", "Skywriter.ts_low_polls",
                  "Skywriter.short_reads", "Skywriter.frames_sensor_data",
                  "Skywriter.frames_status", "Skywriter.frames_firmware",
                  "Skywriter.frames_other", "ev_position", "ev_touch",
                  "ev_gesture", "ev_airwheel", "ev_dropped", "hid_pointer",
                  "hid_button", "hid_wheel", "hid_key", "hid_media",
                  "ble_connects", "ble_disconnects"):
        assert token in body, f"the health line must include {token}"
    # The two shares are computed, not left as raw counts (P4.0a T5).
    assert body.count("100.0f *") == 2
    # The print runs from loop() on the 2 s gate.
    loop_body = function_body("loop")
    assert "print_health_status(now)" in loop_body
    assert loop_body.index("HEALTH_INTERVAL_MS") < \
        loop_body.index("print_health_status(now)"), (
        "the 2 s gate must guard the health print")


def test_the_200hz_sensor_path_never_prints():
    """P3.22: the sensor callbacks only increment counters — the health
    print is loop()'s job. (The per-link-loss drop notice is a separate,
    deliberate one-shot line.)"""
    for name in ("on_sensor_xyz", "on_sensor_touch", "on_sensor_gesture",
                 "on_sensor_airwheel"):
        assert "Serial." not in function_body(name), (
            f"{name} must not print (200 Hz path)")


# ------------------------------------- P3.29: the per-event evidence trace --
# (The 2026-11-25 acceptance session hit two questions the aggregate health
# counters cannot answer: which ZONE a tap landed in — every tap produced
# button clicks and none produced the Page Up/Down keys, and the counters
# cannot say whether the sensor never sent a north/south touch code or sent
# one that was mishandled — and whether a rotation attempt ever produced
# AirWheel-valid data at all (`events wheel=0` through both attempts). The
# SKYTRACE lines answer both from the device side, one compact line per
# dispatched event. The SystemInfo byte matters beyond validity gating: its
# EnvironmentalNoise (bit 4) and Clipping (bit 5) bits are the sensor's own
# health report, surfaced by NEITHER driver before P3.29, and they may name
# the hover-deafness cause directly (P4.0 hypothesis (g)).)

def _trace_guarded_text():
    """The sketch text inside `#if SKYWRITER_EVENT_TRACE` ... `#endif`
    regions (the event-trace gate and the P3.31 calibration variants are
    the sketch's only conditional-compilation blocks; the #if/#endif
    stack below resolves any balanced nesting)."""
    lines = sketch_source().splitlines()
    inside = []
    stack = []
    chunks = []
    start = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#if"):
            stack.append(s)
            if "SKYWRITER_EVENT_TRACE" in s and start is None:
                start = i
        elif s.startswith("#endif"):
            if stack:
                top = stack.pop()
                if "SKYWRITER_EVENT_TRACE" in top and start is not None:
                    chunks.append("\n".join(lines[start:i + 1]))
                    start = None
    assert stack == [], "unbalanced #if/#endif in the sketch"
    assert chunks, "no SKYWRITER_EVENT_TRACE-guarded region found"
    return "\n".join(chunks)


def test_event_trace_is_compile_time_gated_and_off_by_default():
    """P3.29: the per-event trace is compile-time gated — a named
    `SKYWRITER_EVENT_TRACE` macro defaults to 0 (the 200 Hz position path
    must stay quiet in normal builds), every SKYTRACE print lives inside a
    `#if SKYWRITER_EVENT_TRACE` region, and the default can be flipped for
    an acceptance-run build without hunting through the code."""
    src = sketch_source()
    ifndef_at = src.index("#ifndef SKYWRITER_EVENT_TRACE")
    define_at = src.index("#define SKYWRITER_EVENT_TRACE 0")
    assert ifndef_at < define_at, (
        "the gate macro must default to 0 (an #ifndef fallback the build "
        "flags can override)")
    guarded = _trace_guarded_text()
    assert "SKYTRACE " in guarded, "the trace lines are missing"
    # Every SKYTRACE occurrence sits inside a guarded region — nothing
    # prints per-event in a default build.
    for line in src.splitlines():
        if "SKYTRACE" in line:
            assert line.strip().startswith("//") or "SKYTRACE" in guarded, (
                f"an ungated SKYTRACE print leaked out: {line!r}")


def test_event_trace_lines_carry_the_item_fields():
    """The trace prints each dispatched event compactly with the fields the
    acceptance session named: kind + touch code/zone (+ family) on touch
    lines, the position values on position lines, the gesture code on
    gesture lines, the wheel degrees on wheel lines — and EVERY line ends
    with the per-frame context the counters cannot show: the AirWheel-valid
    flag/counter and the RAW SystemInfo byte with its two health bits
    decoded (noise = bit 4, clip = bit 5)."""
    guarded = _trace_guarded_text()
    for token in ("SKYTRACE pos x=", "SKYTRACE touch code=",
                  "SKYTRACE gest code=", "SKYTRACE wheel deg="):
        assert token in guarded, f"missing trace line {token!r}"
    # The per-event payloads.
    for token in ("zone=", "family=", "y=", "z=", "class=", "edge="):
        assert token in guarded, f"missing trace field {token!r}"
    # The shared per-frame context: AirWheel validity + raw counter from the
    # driver's public state, the raw SystemInfo byte, and the decoded health
    # bits (bit 4 EnvironmentalNoise = 0x10, bit 5 Clipping = 0x20).
    for token in ("aw_valid=", "aw_cnt=", "sys=", "noise=", "clip="):
        assert token in guarded, f"missing trace context {token!r}"
    assert "Skywriter.airwheel_valid" in guarded
    assert "Skywriter.airwheel_counter" in guarded
    assert "Skywriter.last_sysinfo" in guarded
    assert "0x10" in guarded and "0x20" in guarded, (
        "the noise (bit 4) and clipping (bit 5) bits must be decoded from "
        "the SystemInfo byte's own bit masks")


def test_event_trace_position_is_rate_limited():
    """Even when enabled, the 200 Hz position path stays readable: position
    lines are rate-limited through a named interval constant (the touch,
    gesture and wheel events are rare and print every one)."""
    guarded = _trace_guarded_text()
    assert "TRACE_POSITION_INTERVAL_MS" in guarded, (
        "the position rate limit must be a named constant")
    body = function_body("trace_position")
    assert "TRACE_POSITION_INTERVAL_MS" in body
    assert "trace_last_position_ms" in body, (
        "the rate limit must compare against a last-printed timestamp")


def test_sensor_callbacks_call_the_gated_trace_helpers():
    """Every dispatched sensor event gets its trace call — after the
    unconnected drop gate and after the mapper dispatch (the item says
    "each dispatched event"), and the callbacks themselves stay free of
    Serial prints (the 200 Hz path never prints directly; the gated
    helpers are the only serial output it can reach)."""
    pairs = (("on_sensor_xyz", "trace_position("),
             ("on_sensor_touch", "trace_touch("),
             ("on_sensor_gesture", "trace_gesture("),
             ("on_sensor_airwheel", "trace_airwheel("))
    for name, call in pairs:
        body = function_body(name)
        assert call in body, f"{name} must call {call}"
        assert "Serial." not in body, (
            f"{name} must not print directly — the trace helper is the "
            "only serial output the 200 Hz path reaches")
        # The dispatch happens before the trace: the line shows an event
        # that actually reached the engine.
        assert body.index("mapper.on") < body.index(call), (
            f"{name}'s trace call must follow the mapper dispatch")
    for helper in ("trace_position", "trace_touch", "trace_gesture",
                   "trace_airwheel"):
        assert "Serial.print" in function_body(helper), (
            f"trace helper {helper} must print")


def test_health_line_carries_the_sysinfo_health_bits():
    """The sensor's own health report is visible in EVERY build (not gated
    like SKYTRACE): the always-on health line carries the latest
    sensor-data frame's RAW SystemInfo byte (`sysinfo=0xNN`) plus its two
    health bits decoded — `noise=` (bit 4, EnvironmentalNoise) and `clip=`
    (bit 5, Clipping) — right after the other-frame snapshot it explains
    and before the event counters."""
    body = function_body("print_health_status")
    assert "sysinfo=0x" in body, (
        "the health line must print the raw SystemInfo byte")
    assert "Skywriter.last_sysinfo" in body, (
        "the byte comes from the driver's public state")
    assert "noise=" in body and "clip=" in body, (
        "the two health bits must be decoded, not left as bit arithmetic")
    assert "0x10" in body and "0x20" in body, (
        "the decode uses the byte's own bit masks (bit 4, bit 5)")
    assert "SKYTRACE" not in body, (
        "the health line is always on — no trace-gate dependency")
    other_read_at = body.index("other_read=")
    sysinfo_at = body.index("sysinfo=0x")
    events_at = body.index('" events pos="')
    assert other_read_at < sysinfo_at < events_at, (
        "the sysinfo fields sit between the snapshot and the events")


def test_flash_script_can_enable_the_trace_for_acceptance_builds():
    """The acceptance-run build path: `SKYWRITER_EVENT_TRACE=1 ./flash.sh …`
    must forward the switch to the compiler as a `-D` definition (so an
    acceptance build never requires editing the sketch source), and the
    default build must pass no such flag. (P3.31 revision of the
    mechanism: the requested -D definitions now fold into ONE
    `compiler.cpp.extra_flags` value carried in the positional parameters.
    `build.extra_flags` turned out to be the BOARD'S OWN flag slot —
    boards.txt gives the Pico W `-DPICO_CYW43_SUPPORTED=1` through it,
    and overriding that slot compiles the core WITHOUT the WiFi driver
    while arduino-cli caches the broken core archive per FQBN, killing
    every later build of that FQBN — verified 2026-11-26. The
    compiler-level slot adds our flags without touching the board's.)"""
    flash = (SKETCH.parents[1] / "flash.sh").read_text()
    assert "SKYWRITER_EVENT_TRACE" in flash, (
        "flash.sh must accept the SKYWRITER_EVENT_TRACE=1 build knob")
    assert 'set -- "$@" -DSKYWRITER_EVENT_TRACE=1' in flash, (
        "the switch must reach the compiler as a -D definition")
    # The default stays off: the knob reads with a `:-0` fallback and no
    # build property is passed unless at least one switch is set.
    assert "${SKYWRITER_EVENT_TRACE:-0}" in flash
    assert 'if [ "$#" -gt 0 ]; then' in flash, (
        "the default build must pass no -D flag")


# ------------------------------------- P3.31: auto-calibration semantics + experiment --
# (Hardware session 6, findings F19/F23: the sensor's Clipping health bit
# is set on EVERY frame ever captured, including the FIRST data frame of a
# fresh boot, and the "auto-calibration is disabled" premise turned out
# FALSE — Interface.pdf §4.4.5.3 (dspCalOpMode) says a bit CLEARED in
# Argument0 ENABLES its auto-calibration feature and a bit SET DISABLES
# it, with Argument1 as the mask, so the legacy payload both drivers send
# (Argument0 = 0x00, mask 0x1F) actually ENABLES all five masked features.
# The correction is comments-only; the genuine disable is a compile-time
# EXPERIMENT variant so the default build's behaviour is unchanged.)

def _cal_branches():
    """The three branch texts of the calibration-variant block: the
    `#if SKYWRITER_CAL_DISABLE` full-disable branch, the
    `#elif SKYWRITER_CAL_DISABLE_IDLE` idle-only branch and the legacy
    `#else` default. The payload block is the FIRST `#if
    SKYWRITER_CAL_DISABLE` region in the sketch — the variant-NAME macro
    below it reuses the same #if line, so the scan stops after the first
    complete region (and asserts it found the payload, not the macro)."""
    lines = sketch_source().splitlines()
    branches = {}
    current = None
    buf = []
    inside = False
    for line in lines:
        s = line.strip()
        if not inside:
            if s.startswith("#if SKYWRITER_CAL_DISABLE"):
                inside = True
                current, buf = "if", [line]
            continue
        if s.startswith("#elif SKYWRITER_CAL_DISABLE_IDLE"):
            branches[current] = "\n".join(buf)
            current, buf = "elif", [line]
        elif s == "#else":
            branches[current] = "\n".join(buf)
            current, buf = "else", [line]
        elif s == "#endif" and current is not None:
            branches[current] = "\n".join(buf)
            break  # the FIRST #if region is the payload block
        else:
            buf.append(line)
    assert set(branches) == {"if", "elif", "else"}, (
        "the calibration variant block must have exactly three branches")
    assert "RUNTIME_AUTO_CALIBRATION" in branches["if"], (
        "the first #if region must be the payload block, not the name macro")
    return branches


def test_calibration_comment_states_the_datasheet_semantics():
    """P3.31: the command-4 label no longer claims a plain "Disable" — the
    corrected comment states the datasheet's inverted bit semantics
    (Interface.pdf §4.4.5.3, dspCalOpMode), names the five masked features
    the legacy payload actually ENABLES, and notes the AFA bit outside
    the mask."""
    src = sketch_source()
    assert "// 4. Disable auto-calibration" not in src, (
        "the misleading command-4 label must be gone")
    for token in ("§4.4.5.3", "dspCalOpMode", "CLEARED", "ENABLES",
                  "DISABLES", "AFA"):
        assert token in src, f"missing semantics token {token!r}"
    for feature in ("start-up", "gesture-triggered", "negative",
                    "idle", "invalidity-value"):
        assert feature in src, f"missing feature name {feature!r}"


def test_calibration_experiment_variants_are_gated_off_by_default():
    """P3.31: the genuine-disable experiment is compile-time gated OFF —
    a default build sends the legacy payload byte-for-byte (behaviour
    unchanged), `-DSKYWRITER_CAL_DISABLE=1` swaps in the genuine disable
    (Argument0 = 0x1F, mask = 0x1F — all five masked features off) and
    `-DSKYWRITER_CAL_DISABLE_IDLE=1` the idle-only fallback (0x08/0x08).
    The single array name keeps the queue wiring variant-independent."""
    src = sketch_source()
    for macro in ("SKYWRITER_CAL_DISABLE", "SKYWRITER_CAL_DISABLE_IDLE"):
        ifndef_at = src.index(f"#ifndef {macro}")
        define_at = src.index(f"#define {macro} 0")
        assert ifndef_at < define_at, (
            f"{macro} must default to 0 (an #ifndef fallback the build "
            "flags can override)")
    branches = _cal_branches()
    legacy = ("0x00, 0x00, 0xA2,   0x80, 0x00,   0x00, 0x00,\n"
              "  0x00, 0x00, 0x00, 0x00,\n"
              "  0x1F, 0x00, 0x00, 0x00")
    disable_all = ("0x00, 0x00, 0xA2,   0x80, 0x00,   0x00, 0x00,\n"
                   "  0x1F, 0x00, 0x00, 0x00,\n"
                   "  0x1F, 0x00, 0x00, 0x00")
    disable_idle = ("0x00, 0x00, 0xA2,   0x80, 0x00,   0x00, 0x00,\n"
                    "  0x08, 0x00, 0x00, 0x00,\n"
                    "  0x08, 0x00, 0x00, 0x00")
    assert legacy in branches["else"], (
        "the default branch must keep the legacy payload byte-for-byte")
    assert disable_all in branches["if"], (
        "the full-disable branch must set every masked feature bit")
    assert disable_idle in branches["elif"], (
        "the idle-only branch must set only the idle-calibration bit")
    # The three branches define ONE array name — the queue stays untouched
    # whichever variant is compiled.
    assert src.count("const unsigned char RUNTIME_AUTO_CALIBRATION[") == 3, (
        "each branch must define the same single array name")
    assert "    RUNTIME_AUTO_CALIBRATION," in src, (
        "configure_sensor_attempt must queue the calibration command")


def test_calibration_variant_is_named_on_the_serial_evidence():
    """P3.31: the experiment's identity is on the serial console in every
    capture mode — the `SKYSTATE sensor_ok` boot line AND the repeating
    health line both name the active calibration variant (`cal=`), so a
    monitor attached after boot (session 2's capture mode) still shows
    which build runs."""
    src = sketch_source()
    for name in ("legacy_all_enabled", "disable_all", "disable_idle"):
        assert f'"{name}"' in src, f"missing variant name {name!r}"
    ok_body = function_body("sensor_config_report_success")
    assert '" cal="' in ok_body, (
        "the sensor_ok boot line must name the calibration variant")
    assert "SKYWRITER_CAL_VARIANT_NAME" in ok_body
    health = function_body("print_health_status")
    assert '" cal="' in health and "SKYWRITER_CAL_VARIANT_NAME" in health, (
        "the health line must repeat the variant (late-attached monitors)")
    # The health-line token sits with the configuration fields it explains.
    cfg_at = health.index("cfg_attempts=")
    cal_at = health.index('" cal="')
    polls_at = health.index('" polls="')
    assert cfg_at < cal_at < polls_at, (
        "cal= belongs with sensor_cfg/cfg_attempts, before the read counters")


def test_flash_script_forwards_the_calibration_knobs():
    """P3.31: flash.sh accepts both experiment knobs with off defaults,
    and every requested -D definition reaches the compiler inside ONE
    `compiler.cpp.extra_flags` value — the COMPILER-level slot, never the
    board's own `build.extra_flags` slot (boards.txt gives the Pico W
    `-DPICO_CYW43_SUPPORTED=1` through `build.extra_flags`; overriding it
    compiles the core without the WiFi driver and arduino-cli caches the
    broken core archive per FQBN — verified 2026-11-26 — while repeated
    same-key --build-property values are last-one-wins, so the trace and
    experiment switches must combine as one space-separated value passed
    as exactly two arguments through the positional parameters)."""
    flash = (SKETCH.parents[1] / "flash.sh").read_text()
    for knob in ("SKYWRITER_EVENT_TRACE", "SKYWRITER_CAL_DISABLE",
                 "SKYWRITER_CAL_DISABLE_IDLE"):
        assert knob in flash, f"flash.sh must accept the {knob}=1 knob"
        assert "${" + knob + ":-0}" in flash, (
            f"{knob} must default off (:-0 fallback)")
    # ONE build-property emission for every combination of switches: the
    # fold line is the only place a property is passed to the compile.
    assert ('set -- --build-property "compiler.cpp.extra_flags='
            in flash), (
        "all -D flags must fold into the single compiler.cpp.extra_flags "
        "value — never the board's own build.extra_flags slot")
    assert flash.count("set -- --build-property") == 1, (
        "exactly one build-property emission for every switch combination")
    # The board's own flag slot must not be touched anywhere: no
    # build.extra_flags= value is ever passed (the comment may NAME the
    # slot to explain why — it never assigns it).
    assert "build.extra_flags=" not in flash, (
        "the board's build.extra_flags slot must never be overridden")
    # The value must survive as one argument: the compile passes the
    # folded list through the positional parameters ("$@"), never through
    # an unquoted variable that would re-split the value's spaces.
    assert '"$@"' in flash, (
        'the compile must pass the folded build property via "$@"')
    # The idle fallback yields to the full disable when both are set.
    full_at = flash.index('"${SKYWRITER_CAL_DISABLE:-0}"')
    idle_line = 'elif [ "${SKYWRITER_CAL_DISABLE_IDLE:-0}" = "1" ]; then'
    assert idle_line in flash and full_at < flash.index(idle_line), (
        "SKYWRITER_CAL_DISABLE=1 must take precedence over the idle knob")
    # The sketch-dir argument survives the positional scratch space.
    assert 'cd "$SKETCH_DIR_ARG"' in flash or "SKETCH_DIR_ARG" in flash, (
        "the sketch-dir argument must be saved before $@ is reused")
