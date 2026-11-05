'''Canonical sensor-event grammar (fix_plan P3.2).

The vocabulary from ``specs/hid_mapping.md`` §2 (plus its control-message
extension), as machine-checkable dicts. Fixture scenarios in
``specs/fixtures/manifest.json`` express their expectations in exactly this
grammar; ``canonicalize()`` translates each adapter's *native* decoder records
into it, so assertions can be written once and both drivers can be compared
for parity (AC-MAP-09).

Grammar (event -> keys)::

    {"event": "position",       "x", "y", "z"}     raw 16-bit sensor units, 0-65535
    {"event": "gesture",        "code", "class", "edge"}
                 code: 1 garbage, 2-5 flicks (W→E, E→W, S→N, N→S), 6/7 circles
                 class: wire bits 12-15 (0 garbage, 1 flick, 2 circle)
                 edge:  wire bit 16 (edge-flick flag)
    {"event": "touch"|"tap"|"doubletap", "zone"}
                 zone: south, west, north, east, center
    {"event": "airwheel",       "degrees"}          signed delta; + = clockwise
    {"event": "system_status",  "msg_id", "error"}  control: Set_Runtime ack (0x15)
    {"event": "firmware_info",  "fw_valid", "version"}  control: Fw_Version (0x83)

An expectation entry in the manifest may carry meta keys on top of the event
keys (never asserted as values):

    "omit_pending":  {"deviation": "D5", "drivers": ["python"]}
        While that deviation is open, the listed drivers may omit the event
        entirely. When the deviation row is removed from the specs/README.md
        ledger (fix closed), the annotation must be dropped from the manifest
        (the test_scenarios lint forces this) and the event becomes required.
    "keys_pending":  {"deviation": "D7", "keys": ["class", "edge"],
                      "drivers": ["cpp"]}
         While open, the listed drivers may leave those keys out of their
         event record (attributes that driver still discards). Whatever the
         decoder *does* provide must already match; the annotation must be
         dropped when the ledger row goes. Last user: D7's gesture
         class/edge gate on the Arduino driver, closed 2026-11-05 with P3.11
         (the Python side had carried class/edge since P3.7) — both drivers
         now decode the full 32-bit GestureInfo word and gesture events
         assert code/class/edge equally everywhere.
    "note":          short human context (not asserted, not checked)
'''

from . import deviations

META_KEYS = frozenset({'omit_pending', 'keys_pending', 'note'})

EVENT_KEYS = {
    'position': frozenset({'x', 'y', 'z'}),
    'gesture': frozenset({'code', 'class', 'edge'}),
    'touch': frozenset({'zone'}),
    'tap': frozenset({'zone'}),
    'doubletap': frozenset({'zone'}),
    'airwheel': frozenset({'degrees'}),
    'system_status': frozenset({'msg_id', 'error'}),
    'firmware_info': frozenset({'fw_valid', 'version'}),
}

# The Python and C++ decoders report positions in the same raw 16-bit units,
# but the Python driver rounds each axis to 4 decimal places of raw/65536
# before its callback sees it (``_round_to = 4``), so converting back to raw
# units loses up to 65536 * 0.00005 ≈ 3.3 units per axis. ±4 raw units is
# therefore the documented representation tolerance for both driver-vs-manifest
# asserts and Python-vs-C++ parity (AC-MAP-09); nothing coarser is tolerated.
POSITION_TOLERANCE = 4

# Gesture codes (Interface.pdf §4.5 / skywriter.h constants): 1 garbage,
# 2-5 flicks (west→east, east→west, south→north, north→south), 6/7 circles
# (clockwise, counter-clockwise). The Python driver exposes flicks as
# (from, to) zone-name pairs and circles as direction strings; the wire
# code, class (GestureInfo bits 12-15) and edge-flick flag (bit 16) travel
# with every gesture record since the driver decodes the full word (P3.7).

# Arduino touch/tap/doubletap codes (skywriter.h SW_* constants) -> canonical
# (event, zone). Lowest code = highest TouchInfo bit.
TOUCH_CODES = {
    0: ('doubletap', 'center'), 1: ('doubletap', 'east'),
    2: ('doubletap', 'north'), 3: ('doubletap', 'west'),
    4: ('doubletap', 'south'), 5: ('tap', 'center'),
    6: ('tap', 'east'), 7: ('tap', 'north'), 8: ('tap', 'west'),
    9: ('tap', 'south'), 10: ('touch', 'center'),
    11: ('touch', 'east'), 12: ('touch', 'north'),
    13: ('touch', 'west'), 14: ('touch', 'south'),
}


def canonicalize(adapter_name, records):
    '''Translate one adapter's native records into canonical-event dicts.'''
    if adapter_name == 'python':
        return [canonicalize_python_record(r) for r in records]
    if adapter_name == 'cpp':
        return [canonicalize_cpp_record(r) for r in records]
    raise ValueError(f'unknown adapter: {adapter_name!r}')


def canonicalize_python_record(record):
    kind = record.get('kind')
    if kind == 'move':
        return {'event': 'position',
                'x': int(round(record['x'] * 65536)),
                'y': int(round(record['y'] * 65536)),
                'z': int(round(record['z'] * 65536))}
    if kind in ('flick', 'garbage', 'circle'):
        # The GestureInfo attributes are carried on the record by the
        # adapter (driver globals snapshot, P3.7): code = wire bits 0-7,
        # class = wire bits 12-15, edge = wire bit 16.
        return {'event': 'gesture', 'code': record['code'],
                'class': record['class'], 'edge': record['edge']}
    if kind in ('touch', 'tap', 'doubletap'):
        return {'event': kind, 'zone': record['zone']}
    if kind == 'airwheel':
        return {'event': 'airwheel', 'degrees': float(record['degrees'])}
    raise ValueError(f'unknown python record kind: {kind!r}')


def canonicalize_cpp_record(record):
    kind = record.get('kind')
    if kind == 'move':
        return {'event': 'position', 'x': int(record['x']),
                'y': int(record['y']), 'z': int(record['z'])}
    if kind == 'touch_code':
        event, zone = TOUCH_CODES[record['code']]
        return {'event': event, 'zone': zone}
    if kind == 'gesture':
        # Same shape as the Python records: the Arduino driver decodes the
        # full 32-bit GestureInfo word too (P3.11), so the code/class/edge
        # triple travels with every gesture record on both drivers.
        return {'event': 'gesture', 'code': record['code'],
                'class': record['class'], 'edge': record['edge']}
    if kind == 'airwheel':
        return {'event': 'airwheel', 'degrees': float(record['degrees'])}
    raise ValueError(f'unknown cpp record kind: {kind!r}')


# --- matching / comparison ---------------------------------------------------


def _value_equal(event, key, want, have):
    '''Value equality with the documented representation tolerances.'''
    if event == 'position' and key in ('x', 'y', 'z'):
        return abs(want - have) <= POSITION_TOLERANCE
    if key == 'degrees':
        # Deltas are quantized to 11.25 degrees (one sensor step); require
        # exactness within float noise only.
        return abs(want - have) <= 1e-6
    if event == 'gesture' and key == 'edge':
        return bool(want) == bool(have)
    return want == have


def _gated_keys(expected):
    '''Keys whose absence a still-open deviation tolerates (may be empty).'''
    gate = expected.get('keys_pending')
    if gate and deviations.is_open(gate['deviation']):
        return frozenset(gate.get('keys') or ())
    return frozenset()


def event_match(expected, actual):
    '''Does one concrete canonical event satisfy one expectation entry?

    Every key named by the event grammar is checked. A key missing from
    ``actual`` is tolerated only if it is gated by a still-open deviation;
    a key that IS present must always match, gated or not.
    '''
    if actual.get('event') != expected['event']:
        return False
    gated = _gated_keys(expected)
    for key in EVENT_KEYS[expected['event']]:
        if key not in actual:
            if key in gated:
                continue
            return False
        if not _value_equal(expected['event'], key, expected.get(key),
                            actual[key]):
            return False
    return True


def find_match(expected, unused_actuals):
    '''Index of the first unconsumed actual matching ``expected``, or -1.'''
    for index, actual in enumerate(unused_actuals):
        if event_match(expected, actual):
            return index
    return -1


def is_omission_tolerated(expected, driver):
    '''May this driver omit the expected event right now?'''
    pending = expected.get('omit_pending')
    return bool(pending) and deviations.is_open(pending['deviation']) \
        and driver in (pending.get('drivers') or ())


def compare(expected_events, actual_events, driver):
    '''Assert-shaped compare: returns a list of failure strings (empty=pass).

    Consumes ``actual_events`` against ``expected_events`` (first-match
    semantics, values with the documented tolerances). Events the driver owes
    and did not emit are tolerated only with an `omit_pending` annotation
    (deviation open, driver listed); anything unexpected the driver emits is
    always a failure.
    '''
    failures = []
    unused = list(actual_events)
    for expected in expected_events:
        index = find_match(expected, unused)
        if index >= 0:
            unused.pop(index)
            continue
        if is_omission_tolerated(expected, driver):
            continue
        failures.append(f'missing: {format_event(expected)}')
    for actual in unused:
        failures.append(f'unexpected extra: {format_event(actual)}')
    return failures


# --- deviation realization ---------------------------------------------------


def omission_reproduces(expected, actual_events):
    '''True while the annotated omission still genuinely happens.

    The mirrored check of :func:`is_omission_tolerated`: while the annotation
    stands, the event must *indeed be absent* from the driver's record. If a
    fix lands making the event appear, the deviation row no longer reproduces:
    the ledger row must go first (then the manifest annotation, per the lint).
    '''
    return find_match(expected, list(actual_events)) < 0


def gated_keys_absent(expected, actual_events):
    '''True while the gated keys are still not fully present.

    For every actual event of the same kind whose values match the expectation
    entry, at least one gated key must still be missing. When a fix supplies
    all of them in every such event, the deviation row no longer reproduces:
    the ledger row must go first (then the manifest annotation, per the lint).
    '''
    gated = _gated_keys(expected)
    if not gated:
        return False
    for actual in actual_events:
        if actual.get('event') != expected['event']:
            continue
        # Only events that already match every non-gated key count as "the
        # fixed event"; mismatched events are *other* facts, not evidence.
        if all(key in actual and
               _value_equal(expected['event'], key, expected.get(key),
                            actual[key])
               for key in EVENT_KEYS[expected['event']] if key not in gated):
            if all(key in actual and actual[key] is not None
                   for key in gated):
                return False
    return True


# --- cross-driver parity (AC-MAP-09) -----------------------------------------


def parity_match(a, b, gated_keys_by_kind):
    '''Do two concrete canonical events describe the same sensor fact?

    Like :func:`event_match` but bidirectional (two decoders, no "expected"):
    keys present on both sides must be equal (with the documented tolerance);
    a key missing on one side is a real parity difference unless it is gated
    by a still-open deviation for that event kind.
    '''
    if a.get('event') != b.get('event'):
        return False
    gated = gated_keys_by_kind.get(a['event'], frozenset())
    for key in EVENT_KEYS[a['event']]:
        in_a, in_b = key in a, key in b
        if in_a and in_b:
            if not _value_equal(a['event'], key, a[key], b[key]):
                return False
        elif in_a or in_b:
            if key not in gated:
                return False
    return True


def parity_diffs(events_a, events_b, gated_keys_by_kind):
    '''Difference between two drivers' canonical event streams.

    Returns ``(leftovers_a, leftovers_b)``: events from each side that no
    event on the other side matches.

    Both ``gated_keys_by_kind`` (which keys a still-open deviation may leave
    out of an event) and metadata are supplied by the caller.
    '''
    unused_b = list(events_b)
    leftovers_a = []
    for event in events_a:
        for index, other in enumerate(unused_b):
            if parity_match(event, other, gated_keys_by_kind):
                unused_b.pop(index)
                break
        else:
            leftovers_a.append(event)
    leftovers_b = list(unused_b)
    return leftovers_a, leftovers_b


def format_event(event):
    '''Compact one-line rendering for failure messages.'''
    meta = {k: v for k, v in event.items()
            if k in ('event',) or k not in META_KEYS}
    quoted = ', '.join(f'{k}={v!r}' for k, v in sorted(meta.items()))
    return '{' + quoted + '}'
