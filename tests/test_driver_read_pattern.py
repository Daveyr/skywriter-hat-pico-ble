'''The Arduino driver's poll() read pattern and unknown-frame snapshot
(fix_plan items P3.25 + P3.24, the answer to the hardware report's F7).

In plain language: the gesture sensor signals "a message is waiting" and
the Pico reads it over the I2C (Inter-Integrated Circuit — the two-wire
bus between the Pico and the sensor) bus. Until now the driver asked for
132 bytes on EVERY read, while a normal sensor message is only 26 bytes —
so it clocked 106 bytes past the end of every message. What the sensor
serves there is undefined; if it serves the start of the NEXT queued
message, its internal read pointer ends up mid-frame and every later read
starts inside a message, so the header's identity byte never lands on a
known value again — exactly the "other=100% from the first poll, zero
events" signature the first hardware counter capture showed (fix_plan
P4.0a, hypothesis H7). The Raspberry Pi Python driver never over-reads: 26
bytes first, then continuation reads sized from the frame's own Size
field (its P3.11c fix).

P3.25 ports that pattern to the Arduino driver: read EXACTLY 26 bytes
first; only when the frame's own Size field (validated 4..132) says the
message is longer, fetch continuation reads bounded by Size (32-byte
chunks) while the transfer line is still asserted; a frame that cannot be
completed is never dispatched half-read; the transfer-line release rule
(P3.23) stands on every exit path.

P3.24 adds the instrument the next hardware session needs: whenever a
transfer read a header but did NOT dispatch (unknown identity, corrupt
Size, or an incomplete frame), the driver stores a public snapshot — the
first 8 frame bytes and the byte count the reads actually returned (the
requestFrom return values the old code ignored). The firmware sketch's
health line prints it. Its content names the fault: a 0x91 identity
visible at a SHIFTED offset confirms the framing misalignment; all 0x00
means the bus answers padding on empty reads; all 0xFF means a wedged
slave; a known identity with a read count under the promised Size means
an incomplete read.

Test method: the real driver is compiled for the host behind the tests/cpp
shims; the Wire shim models the sensor continuing its buffer across the
reads of one asserted transfer (the same contract the Python driver's
sized reads rely on) and records every requestFrom call, so each test
asserts the genuine poll()'s read pattern and dispatch outcome. Verified
FAILING against the pre-P3.25 code — 8 of the 10 (the old single 132-byte
request, no continuations, no snapshot; the short-read and
transfer-accounting cases were already true then and stay green) — and
must stay green.
'''

import hashlib
import pathlib
import re
import subprocess

_THIS_DIR = pathlib.Path(__file__).resolve().parent
_CPP_DIR = _THIS_DIR / 'cpp'
_REPO_ROOT = _THIS_DIR.parents[0]
_DRIVER_DIR = _REPO_ROOT / 'arduino' / 'Skywriter'
_FIXTURES = _REPO_ROOT / 'specs' / 'fixtures'
_BUILD_DIR = _THIS_DIR / 'build'

_TIMEOUT_COMPILE = 300
_TIMEOUT_RUN = 30

_SOURCES = (_CPP_DIR / 'arduino_shim.cpp',
             _CPP_DIR / 'host_read_pattern_main.cpp',
             _DRIVER_DIR / 'skywriter.cpp')


def _frame(fixture):
    '''A recorded fixture frame as one hex string (header included).'''
    return open(_FIXTURES / fixture).read().strip()


_F01 = _frame('F01_position_only.hex')            # classic 26-byte sensor frame
_F17 = _frame('F17_fw_version_valid.hex')        # 132-byte Fw_Version_Info frame
_F21 = _frame('F21_circle_cw.hex')               # 14-byte shorter sensor frame

# A frame that cannot be completed: F17's first 26 bytes, Size field still
# promising 132 — the bus has nothing more when the driver comes back for
# the continuation (the Python driver's empty-continuation case).
_F17_TRUNCATED = ' '.join(_F17.split()[:26])

# A complete frame whose identity byte is none of the known messages: the
# "unknown identity" snapshot case (Size 26 = 0x1a, identity 0x99).
_F_UNKNOWN_IDENT = (
    '1a 08 01 99 aa bb cc dd 00 00 00 00 00 00 00 00 00 00 00 00 00 00 '
    '00 00 00 00')

# The all-zero signature: 26 bytes of 0x00 — Size 0 is corrupt AND the
# content is the "bus answers padding on reads with nothing queued"
# discriminator the hardware session must tell apart from real frames.
_F_ALL_ZERO = ' '.join(['00'] * 26)


def _run(script):
    '''Compile (hash-cached) and run the read-pattern host binary; returns
    one parsed result dict per instruction.'''
    fingerprint = hashlib.sha256()
    for path in _SOURCES + (_CPP_DIR / 'Arduino.h',
                            _CPP_DIR / 'Wire.h',
                            _DRIVER_DIR / 'skywriter.h'):
        fingerprint.update(path.read_bytes())
    binary = _BUILD_DIR / ('read_pattern-' + fingerprint.hexdigest()[:12])
    if not binary.exists():
        from .adapters_cpp import compiler_command
        _BUILD_DIR.mkdir(parents=True, exist_ok=True)
        cmd = compiler_command() + [
            '-I', str(_CPP_DIR),      # the shims shadow the real headers
            '-I', str(_DRIVER_DIR),   # "skywriter.h"
        ] + [str(src) for src in _SOURCES] + ['-o', str(binary)]
        proc = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT_COMPILE)
        if proc.returncode != 0:
            raise RuntimeError(
                'failed to compile the read-pattern host binary:\n'
                f"$ {' '.join(cmd)}\n"
                + proc.stdout.decode(errors='replace')
                + proc.stderr.decode(errors='replace'))
    stdin = ''.join(instruction + '\n' for instruction in script)
    proc = subprocess.run([str(binary)], input=stdin.encode('ascii'),
                          capture_output=True, timeout=_TIMEOUT_RUN)
    if proc.returncode != 0:
        raise RuntimeError(
            f'read-pattern host binary crashed (rc={proc.returncode}):\n'
            + proc.stderr.decode(errors='replace'))
    results = []
    for line in proc.stdout.decode().splitlines():
        assert line.startswith('POLL '), f'unrecognised output: {line!r}'
        out = {}
        for token in line.split()[1:]:
            key, _, value = token.partition('=')
            out[key] = value
        out['reqs'] = [int(q) for q in out['reqs'].split(',') if q]
        out['served'] = [int(s) for s in out['served'].split(',') if s]
        for key in ('polls', 'ts', 'short', 'sensor', 'status', 'fw',
                    'other', 'read', 'released'):
            out[key] = int(out[key])
        out['snap'] = bytes.fromhex(out['snap'].replace(':', ''))
        results.append(out)
    return results


def _deltas(before, after):
    '''Counter movement across one poll (cumulative counters → deltas).'''
    keys = ('ts', 'short', 'sensor', 'status', 'fw', 'other')
    return {k: after[k] - before[k] for k in keys}


# ------------------------------------------------------------- P3.25 reads --

def test_classic_frame_is_exactly_one_26_byte_request():
    '''A 26-byte sensor-data frame (the recorded F01) must arrive as ONE
    read of EXACTLY 26 bytes — never the old 132-byte over-read (H7's
    mechanism) — and must dispatch as sensor data.'''
    before, after = _run(['FRAME ' + _F01, 'FRAME ' + _F01])
    assert after['reqs'] == [26], (
        f'the classic frame must be one 26-byte request, got {after["reqs"]}')
    d = _deltas(before, after)
    assert d == {'ts': 1, 'short': 0, 'sensor': 1, 'status': 0, 'fw': 0,
                 'other': 0}, f'expected one dispatched sensor frame, got {d}'
    assert after['released'] == 1


def test_shorter_frame_reads_only_26_and_never_continues():
    '''A 14-byte frame (F21, the AirWheel-disabled output mask): the first
    read still asks for 26 and the bus serves only the 14 the frame has —
    the Size field (not the request) bounds the payload, and NO
    continuation read follows, because continuations exist only for
    messages LONGER than the first read.'''
    results = _run(['FRAME ' + _F21])
    assert results[0]['reqs'] == [26], results[0]['reqs']
    assert results[0]['served'] == [14], results[0]['served']
    assert results[0]['sensor'] == 1
    assert results[0]['other'] == 0
    assert results[0]['released'] == 1


def test_long_frame_reads_26_then_size_bounded_continuations():
    '''The 132-byte Fw_Version_Info frame (F17): the read pattern is the
    Python driver's P3.11c chase — 26 first, then continuation chunks
    bounded by the frame's own Size (26 + 32 + 32 + 32 + 10 = 132). The
    whole-frame capture that P3.11b introduced survives, without the
    over-read past short frames.'''
    results = _run(['FRAME ' + _F17])
    assert results[0]['reqs'] == [26, 32, 32, 32, 10], results[0]['reqs']
    assert results[0]['served'] == [26, 32, 32, 32, 10], results[0]['served']
    assert results[0]['fw'] == 1, 'the firmware frame must dispatch complete'
    assert results[0]['other'] == 0
    assert results[0]['released'] == 1


def test_incomplete_frame_is_not_dispatched_half_read():
    '''A frame whose Size promises 132 bytes but whose bus empties after
    the first 26 (F17 truncated): the driver may try ONE bounded
    continuation, gets nothing more, and must NOT dispatch the half-read
    message — it counts as an undispatched frame with the snapshot showing
    a read count of 26 against the promised 132. The release rule stands
    on this new exit path.'''
    results = _run(['FRAME ' + _F17_TRUNCATED])
    r = results[0]
    assert r['reqs'][0] == 26, 'the first read is always the 26-byte one'
    assert r['fw'] == 0 and r['sensor'] == 0 and r['status'] == 0, (
        'a frame that cannot be completed must never dispatch')
    assert r['other'] == 1, 'the incomplete frame is counted, not lost'
    assert r['snap'][0] == 0x84 and r['snap'][3] == 0x83, (
        'the snapshot shows the valid header of the incomplete frame')
    assert r['read'] == 26, (
        f'the snapshot read count shows what actually arrived, got {r["read"]}')
    assert r['released'] == 1


def test_corrupt_size_below_minimum_is_not_dispatched():
    '''A Size field under 4 (here 0x00) cannot describe a real message: no
    continuation read, no dispatch — the frame is counted and its content
    snapshotted (the all-0x00 padding signature, exactly the discriminator
    the hardware session must tell from real frames).'''
    results = _run(['FRAME ' + _F_ALL_ZERO])
    r = results[0]
    assert r['reqs'] == [26], 'one first read only, never a continuation'
    assert r['sensor'] == 0 and r['fw'] == 0 and r['status'] == 0
    assert r['other'] == 1
    assert r['snap'] == bytes(8), 'the all-0x00 signature must be captured'
    assert r['read'] == 26
    assert r['released'] == 1


def test_corrupt_size_above_cap_is_not_dispatched():
    '''A Size field above the longest real message (0xFF = 255 > 132) is
    the same corrupt-shape rejection: no continuation reads past the
    longest message, no dispatch, snapshot taken.'''
    corrupt = 'ff 08 01 91 ' + ' '.join(['00'] * 22)
    results = _run(['FRAME ' + corrupt])
    r = results[0]
    assert r['reqs'] == [26], r['reqs']
    assert r['sensor'] == 0 and r['fw'] == 0 and r['status'] == 0
    assert r['other'] == 1
    assert r['snap'][0] == 0xff and r['snap'][3] == 0x91
    assert r['read'] == 26
    assert r['released'] == 1


# --------------------------------------------------- P3.24 snapshot content --

def test_unknown_identity_frame_snapshots_its_content():
    '''A COMPLETE frame whose identity byte is none of the three known
    messages: the P3.24 case — counted as other, first 8 frame bytes and
    the actual read count stored, so a shifted 0x91 (the H7 signature)
    would be visible in exactly this snapshot.'''
    results = _run(['FRAME ' + _F_UNKNOWN_IDENT])
    r = results[0]
    assert r['other'] == 1
    assert r['sensor'] == 0 and r['status'] == 0 and r['fw'] == 0
    expected = bytes.fromhex('1a080199aabbccdd')
    assert r['snap'] == expected, (
        f'the snapshot must carry the first 8 frame bytes, got {r["snap"].hex()}')
    assert r['read'] == 26
    assert r['released'] == 1


def test_snapshot_holds_the_latest_undispatched_frame():
    '''The snapshot always holds the LATEST undispatched frame, so a long
    run of garbage ends on the newest evidence — while dispatched frames
    leave it untouched.'''
    results = _run(['FRAME ' + _F_ALL_ZERO,
                    'FRAME ' + _F_UNKNOWN_IDENT,
                    'FRAME ' + _F01])
    # The dispatched F01 poll must not touch the snapshot...
    assert results[2]['other'] == results[1]['other'], (
        'no new undispatched frame on the dispatched F01 poll')
    assert results[2]['snap'] == bytes.fromhex('1a080199aabbccdd'), (
        'the snapshot must still hold the last undispatched frame, not the '
        'dispatched one')


def test_short_read_counts_without_snapshot():
    '''A read that cannot even produce the 4 header bytes keeps its own
    counter (P3.22) and does not fire the snapshot — no identity byte
    exists to snapshot.'''
    results = _run(['SHORT'])
    r = results[0]
    assert r['short'] == 1
    assert r['other'] == 0, 'a short read is not an undispatched frame'
    assert r['snap'] == bytes(8) and r['read'] == 0, (
        'the snapshot must stay untouched by the short-read path')
    assert r['released'] == 1, 'the P3.23 release stands on this path too'


def test_transfer_accounting_closes():
    '''The health counters must account for EVERY transfer: short reads +
    dispatched frames (sensor + status + firmware) + undispatched frames
    (other) = transfers started. Nothing silently disappears — the whole
    point of the instrument after H7 showed 100% of polls vanishing into
    the "other" bucket.'''
    script = ['FRAME ' + _F01, 'FRAME ' + _F17, 'FRAME ' + _F21,
              'FRAME ' + _F_ALL_ZERO, 'FRAME ' + _F17_TRUNCATED, 'SHORT',
              'FRAME ' + _F01]
    results = _run(script)
    r = results[-1]
    accounted = r['short'] + r['sensor'] + r['status'] + r['fw'] + r['other']
    assert accounted == r['ts'] == len(script), (
        f'transfers={r["ts"]} accounted={accounted} polls={len(script)}')
