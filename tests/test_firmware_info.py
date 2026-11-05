'''Firmware-version validity pin (fix_plan P3.6, deviation D6).

`_handle_firmware_info` used to raise only for `FwValid` 0x00 and 0x0A and
silently treat **every other value** — e.g. a corrupted 0x55 — as valid
firmware, printing garbage bytes as a "version string". The spec
(`datasheets/Interface.pdf` §4.3, Table 4-6) defines exactly three values:

- 0xAA — ValidFW: a valid GestIC Library is available,
- 0x00 — Empty: no valid GestIC Library could be located,
- 0x0A — InvalidFW: an invalid library was stored, or the last update failed.

So **only an exact 0xAA is valid**; anything else is a failure and must
raise. These tests drive the driver's real `_handle_firmware_info` with the
recorded `F17_fw_version_valid` fixture payload (FwValid 0xAA) and mutated
copies for the failure values (no hardware is touched — see
`tests/adapters_python.py` for the mock setup).
'''

import pytest

from tests import fixtures
from tests.adapters_python import import_skywriter


@pytest.fixture()
def sky():
    return import_skywriter()


def _payload_with_fw_valid(sky, fw_valid):
    '''The recorded F17 payload's frame with a given FwValid byte.

    F17 is the vendor §3.5.2 example message (132 bytes: 4-byte header +
    128-byte payload; the FwVersion field is 120 bytes, NUL-padded in the
    fixture), so replacing its payload byte 0 gives a well-formed
    Fw_Version_Info frame carrying exactly the status we want to probe.
    '''
    frame = list(fixtures.load_frame('F17_fw_version_valid'))
    assert frame[3] == sky.SW_FW_VERSION
    frame[4] = fw_valid            # header is 4 bytes: payload index 0
    return frame[4:]               # the payload, per the D1 dispatch contract


def test_recorded_fixture_payload_is_fw_valid(sky):
    '''FwValid 0xAA must be accepted without error (the F17 fixture case).'''
    payload = list(fixtures.load_frame('F17_fw_version_valid'))[4:]
    assert payload[0] == 0xAA      # sanity: the fixture really is the valid case
    assert sky._handle_firmware_info(payload) is None
    # P3.11b: the decoded report travels as module state, so handlers and
    # the replay-harness adapter can read it alongside the callback.
    assert sky.fw_valid == 0xAA
    assert sky.fw_version == ("1.0.0;p:HillstarV01;DSP:ID9000r1849;i:B;"
                              "f:22500;nMsg;s:Beta2r1040:1049:MO;c:MKI;"
                              "t:2013/11/08 13:03:00")


def test_valid_report_fires_the_firmware_version_callback(sky):
    '''P3.11b: a registered `fw_version()` handler (private global here, per
    the adapter contract) receives the NUL-stripped version string — exactly
    the canonical `firmware_info` event's value.'''
    payload = list(fixtures.load_frame('F17_fw_version_valid'))[4:]
    seen = []
    saved = sky._on_firmware_version
    sky._on_firmware_version = lambda v: seen.append(v)
    try:
        sky._handle_firmware_info(payload)
    finally:
        sky._on_firmware_version = saved
    assert seen == [sky.fw_version]     # one event, same string as the state
    assert seen[0].startswith('1.0.0;p:HillstarV01;')


@pytest.mark.parametrize('fw_valid,message_fragment', [
    (0x00, 'No valid GestIC Library could be located'),
    (0x0A, 'An invalid GestiIC Library was stored, or the last update failed'),
])
def test_defined_invalid_values_raise(sky, fw_valid, message_fragment):
    '''The spec's two failure values must keep raising their errors.'''
    payload = _payload_with_fw_valid(sky, fw_valid)
    with pytest.raises(Exception) as excinfo:
        sky._handle_firmware_info(payload)
    assert message_fragment in str(excinfo.value)


@pytest.mark.parametrize('fw_valid', [0x01, 0x55, 0xAB, 0xFF])
def test_undefined_values_are_not_valid_firmware(sky, fw_valid):
    '''The regression core of D6: on master, any FwValid other than 0x00
    or 0x0A was treated as valid firmware. Undefined values must raise,
    never present themselves as a working version.'''
    payload = _payload_with_fw_valid(sky, fw_valid)
    with pytest.raises(Exception) as excinfo:
        sky._handle_firmware_info(payload)
    assert 'Unknown GestIC Library status' in str(excinfo.value)
