"""Fix item P3.31's comments-only half: the Python driver.

Hardware session 6 (findings F19/F23, 2026-11-26) disproved the label both
drivers carried on the fourth sensor-configuration command: the payload
called "Disable auto-calibration" (dspCalOpMode, runtime parameter ID
0x80, Argument0 = 0x00, mask 0x1F) actually ENABLES all five masked
auto-calibration features — Interface.pdf §4.4.5.3 says a bit CLEARED (0)
in Argument0 ENABLES its feature and a bit SET (1) DISABLES it, with
Argument1 as the mask of the bits to apply. The genuine disable is an
EXPERIMENT for the Pico W firmware (the sketch's compile-time
SKYWRITER_CAL_DISABLE variant), NOT a default change here: these tests pin
that the Raspberry Pi driver's comments tell the truth while the bytes it
sends stay byte-for-byte what they always were.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DRIVER = ROOT / "library" / "skywriter" / "__init__.py"
LIBRARY_TEST = ROOT / "library" / "test.py"


def test_setup_comment_states_the_datasheet_semantics():
    """The correction: the setup() block that sends the dspCalOpMode
    command states the datasheet's inverted bit semantics and names the
    five features the legacy payload actually ENABLES — the old bare
    "Disable auto-calibration" comment (and its debug label) are gone."""
    src = DRIVER.read_text()
    assert "# Disable auto-calibration" not in src, (
        "the misleading comment must be gone")
    assert 'print("Disable auto-calibration")' not in src, (
        "the misleading debug label must be gone")
    for token in ("§4.4.5.3", "dspCalOpMode", "CLEARED", "ENABLES",
                  "DISABLES"):
        assert token in src, f"missing semantics token {token!r}"
    for feature in ("start-up", "gesture-triggered", "negative",
                    "idle", "invalidity-value"):
        assert feature in src, f"missing feature name {feature!r}"


def test_the_legacy_payload_is_unchanged():
    """The correction is comments-only: the legacy dspCalOpMode payload —
    Argument0 = 0x00, mask 0x1F — must keep reaching the I2C
    (Inter-Integrated Circuit) bus byte for byte, still sent by default
    (the `_enable_auto_calibration` switch keeps its historical False)."""
    src = DRIVER.read_text()
    block = ("[0x00, 0x00, 0xA2,   0x80, 0x00,   0x00, 0x00,   "
             "0x00, 0x00, 0x00, 0x00,        0b00011111, 0x00, 0x00, 0x00]")
    assert block in src, "the legacy payload bytes must not change"
    assert "if not _enable_auto_calibration:" in src, (
        "the command must still be sent by default")
    assert "_enable_auto_calibration = False" in src, (
        "the default must stay False (behaviour unchanged)")


def test_library_smoke_test_comment_no_longer_claims_calibration_off():
    """The library's own smoke test described the fourth command as
    "auto-calibration off" — it now says what the command actually does
    (leaves all five masked features ON)."""
    src = LIBRARY_TEST.read_text()
    assert "auto-calibration off" not in src, (
        "the smoke test's wrong claim must be gone")
    assert "P3.31" in src, (
        "the corrected wording must reference the semantics correction")
