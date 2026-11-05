'''Spec assertions for the structured fixture expectations (fix_plan P3.2).

Every scenario in ``specs/fixtures/manifest.json`` is replayed into both
decoders (Python driver, C++/Arduino driver through the compiled host
adapter) and checked against its machine-checkable expectations:

- ``expect.canonical`` — the canonical sensor events (``tests/canonical.py``
  grammar) the decoder must emit, with known-open deviations from
  specs/README.md annotated as ``omit_pending`` / ``keys_pending`` so the
  suite is green today and self-arming as each deviation is fixed,
- realization checks — every pending annotation must still literally
  reproduce (the annotated omission / attribute-drop really happens); a fix
  that lands without updating specs/README.md + the manifest fails here with
  instructions,
- ``expect.hid`` — HID outcome records (``tests/hid_grammar.py`` grammar) are
  validated for well-formedness now; their replay-assertion arms with the
  mapping-engine items P3.12–P3.15,
- cross-driver parity — where both decoders emit an event, the canonical
  streams must agree (AC-MAP-09), except for event omissions attributable to
  a deviation annotated for exactly one driver (e.g. D4's airwheel drop).

Known-red decoder defects (D1–D8, specs/README.md) are annotated in the
manifest, never swallowed silently by these tests.
'''

from collections import defaultdict

import pytest

from tests import adapters, canonical, fixtures, hid_grammar, deviations, runner

DRIVERS = ('python', 'cpp')


@pytest.fixture(scope='session')
def manifest():
    return fixtures.load_manifest()


@pytest.fixture(scope='session')
def cpp_adapter():
    return adapters.get_adapter('cpp')


# ------------------------------------------------------- manifest linting ---


def _validated_pending(pending, where):
    '''Check one omit_pending / keys_pending annotation against the ledger.'''
    assert isinstance(pending, dict), f'{where}: pending must be a dict'
    dev = pending.get('deviation')
    assert isinstance(dev, str) and deviations.exists(dev), (
        f'{where}: deviation {dev!r} is not in the specs/README.md ledger — '
        f'spell it right or fix the ledger')
    # A tolerance annotation is only meaningful while its deviation row
    # stands: the moment the fix closes it, this assertion fails and asks
    # the author to drop the annotation (otherwise the tolerance would
    # silently outlive the defect it describes).
    assert deviations.is_open(dev), (
        f'{where}: deviation {dev} is closed in specs/README.md — drop the '
        f'pending annotation so the expectation is fully asserted again')
    drivers = pending.get('drivers')
    assert isinstance(drivers, list) and drivers and set(drivers) <= set(DRIVERS), (
        f'{where}: drivers {drivers!r} must be a non-empty subset of {list(DRIVERS)}')
    for driver in drivers:
        assert deviations.affects(dev, driver), (
            f'{where}: ledger row {dev} does not list the {driver!r} driver '
            f'(the row affects: {sorted(deviations.table()[dev])})')


def _validated_entry(entry, where):
    assert isinstance(entry, dict), f'{where}: event entry must be a dict'
    event = entry.get('event')
    assert event in canonical.EVENT_KEYS, f'{where}: unknown event {event!r}'
    want = set(canonical.EVENT_KEYS[event]) | canonical.META_KEYS | {'event'}
    unknown = set(entry) - want
    assert not unknown, (
        f'{where}: unknown keys {sorted(unknown)}; meta keys are '
        f'{sorted(canonical.META_KEYS)}')
    if event == 'position':
        for axis in ('x', 'y', 'z'):
            assert isinstance(entry[axis], int) and not isinstance(entry[axis], bool), \
                f'{where}: {axis} must be an int (raw sensor units)'
    elif event == 'gesture':
        assert 1 <= entry['code'] <= 7, f'{where}: gesture code {entry["code"]!r} out of range'
        assert isinstance(entry.get('class'), int), \
            f'{where}: class must be the wire value of GestureInfo bits 12-15'
        assert isinstance(entry.get('edge'), bool), f'{where}: edge must be a bool'
    elif event in ('touch', 'tap', 'doubletap'):
        assert entry['zone'] in ('south', 'west', 'north', 'east', 'center'), \
            f'{where}: zone {entry["zone"]!r} unknown'
    elif event == 'airwheel':
        assert isinstance(entry['degrees'], (int, float)), \
            f'{where}: degrees must be numeric'
    elif event == 'system_status':
        for key in ('msg_id', 'error'):
            assert isinstance(entry[key], int), \
                f'{where}: {key} must be an int'
    elif event == 'firmware_info':
        assert isinstance(entry['fw_valid'], int), f'{where}: fw_valid must be an int'
        assert isinstance(entry['version'], str), f'{where}: version must be a string'
    if entry.get('omit_pending') is not None:
        _validated_pending(entry['omit_pending'], f'{where}.omit_pending')
    gate = entry.get('keys_pending')
    if gate is not None:
        keys = gate.get('keys')
        assert keys and set(keys) <= set(canonical.EVENT_KEYS[event]), (
            f'{where}.keys_pending: gated keys {keys!r} must be keys of {event}')
        _validated_pending(gate, f'{where}.keys_pending')


def test_manifest_is_structured_and_wellformed(manifest):
    assert manifest['schema'] == 'skywriter-fixtures/v2', (
        'expectations must carry the structured grammar (fix_plan P3.2)')
    names = set()
    for scenario in manifest['scenarios']:
        names.add(scenario['name'])
        expect = scenario.get('expect')
        assert isinstance(expect, dict), f'{scenario["name"]}: missing structured expect'
        canonical_list = expect.get('canonical')
        assert isinstance(canonical_list, list), \
            f'{scenario["name"]}: expect.canonical must be a list'
        assert isinstance(expect.get('hid'), list), \
            f'{scenario["name"]}: expect.hid must be a list'
        for index, entry in enumerate(canonical_list):
            _validated_entry(entry, f'{scenario["name"]}.canonical[{index}]')
    assert len(names) == len(manifest['scenarios']), 'scenario names must be unique'


def test_every_scenario_hid_outcome_records_are_wellformed(manifest):
    for scenario in manifest['scenarios']:
        hid_grammar.validate(scenario['expect']['hid'], scenario['name'])


# -------------------------------------------------- canonical expectations ---


@pytest.fixture(scope='session')
def replay_results_all(manifest, cpp_adapter):
    '''Replay every scenario once per adapter (one shared cache per run).'''
    out = {}
    for scenario in manifest['scenarios']:
        python_adapter = adapters.get_adapter('python')
        out[('python', scenario['name'])] = runner.replay(scenario, python_adapter)
        out[('cpp', scenario['name'])] = runner.replay(scenario, cpp_adapter)
    return out


@pytest.mark.parametrize('driver', DRIVERS)
def test_scenario_canonical_expectation(driver, manifest, replay_results_all):
    for scenario in manifest['scenarios']:
        result = replay_results_all[(driver, scenario['name'])]
        actual = canonical.canonicalize(driver, result.records)
        expected = scenario['expect']['canonical']
        failures = canonical.compare(expected, actual, driver)
        assert not failures, (
            f'{scenario["name"]}/{driver}: canonical expectation failed:\n'
            + '\n'.join('  - ' + f for f in failures)
            + '\nactual stream: '
            + ' -> '.join(canonical.format_event(e) for e in actual))


@pytest.mark.parametrize('driver', DRIVERS)
def test_deviation_annotations_still_reproduce(driver, manifest, replay_results_all):
    '''Every "pending" tolerance must still be literally true: the deviation
    must still cause exactly the annotated effect. When a fix lands, the
    ledger user updates specs/README.md first (removes the row), then the
    manifest annotation — until then the annotation is a false claim about
    the code and this test fails with exact instructions.'''
    for scenario in manifest['scenarios']:
        result = replay_results_all[(driver, scenario['name'])]
        actual = canonical.canonicalize(driver, result.records)
        for index, entry in enumerate(scenario['expect']['canonical']):
            omit = entry.get('omit_pending')
            if omit is not None and driver in omit.get('drivers', ()) \
                    and deviations.is_open(omit['deviation']):
                assert canonical.omission_reproduces(entry, actual), (
                    f'{scenario["name"]}/{driver}: omit_pending '
                    f'{omit["deviation"]} no longer reproduces — the driver '
                    f'now emits {canonical.format_event(entry)}. Update '
                    f'specs/README.md (remove the {omit["deviation"]} row) '
                    f'and drop the omit_pending annotation here; then the '
                    f'event becomes required.')
            gate = entry.get('keys_pending')
            if gate is not None and driver in gate.get('drivers', ()) \
                    and deviations.is_open(gate['deviation']):
                assert canonical.gated_keys_absent(entry, actual), (
                    f'{scenario["name"]}/{driver}: keys_pending '
                    f'{gate["deviation"]} no longer reproduces — the driver '
                    f'now supplies the gated keys {gate.get("keys")}. Update '
                    f'specs/README.md (remove the {gate["deviation"]} row) '
                    f'and drop the keys_pending annotation here; then the '
                    f'missing keys become required.')


# ------------------------------------------------------------ cross parity ---


def _gated_keys_by_kind(scenario):
    '''kind -> set of keys a still-open keys_pending annotation tolerates.'''
    gated = defaultdict(set)
    for entry in scenario['expect']['canonical']:
        gate = entry.get('keys_pending')
        if gate and deviations.is_open(gate['deviation']):
            gated[entry['event']].update(gate['keys'])
    return dict(gated)


def _omission_attribution(scenario, leftover, missing_driver):
    '''Can a manifest entry explain `missing_driver` omitting this event?

    ``leftover`` is an event the OTHER driver emitted; the annotation must
    claim the omission for ``missing_driver`` (and only for it), and the
    entry must describe the event (gated keys neutral via event_match).
    '''
    for entry in scenario['expect']['canonical']:
        pending = entry.get('omit_pending')
        if not pending or not deviations.is_open(pending['deviation']):
            continue
        drivers = set(pending.get('drivers') or ())
        # The annotation must claim the omission for exactly the missing
        # driver: claiming it for both drivers would describe an equal
        # (not one-sided) absence, which parity would not even surface.
        if drivers != {missing_driver}:
            continue
        if canonical.event_match(entry, leftover):
            return True
    return False


def test_canonical_parity_across_drivers(manifest, cpp_adapter):
    '''AC-MAP-09: where both decoders emit an event, the canonical streams
    agree (including the documented ±4-unit position rounding). Any stream
    difference must be an omission annotated for exactly one driver.'''
    for scenario in manifest['scenarios']:
        python_adapter = adapters.get_adapter('python')
        canon_py = canonical.canonicalize(
            'python', runner.replay(scenario, python_adapter).records)
        canon_cpp = canonical.canonicalize(
            'cpp', runner.replay(scenario, cpp_adapter).records)
        gated = _gated_keys_by_kind(scenario)
        leftovers_py, leftovers_cpp = canonical.parity_diffs(
            canon_py, canon_cpp, gated)

        messages = []
        for leftover in leftovers_py:
            # Python emitted an event the C++ stream lacks: the omission is
            # attributed to the C++ driver.
            if not _omission_attribution(scenario, leftover, 'cpp'):
                messages.append(
                    'python-only event with no attribution: '
                    + canonical.format_event(leftover))
        for leftover in leftovers_cpp:
            if not _omission_attribution(scenario, leftover, 'python'):
                messages.append(
                    'cpp-only event with no attribution: '
                    + canonical.format_event(leftover))
        assert not messages, (
            f'{scenario["name"]}: canonical streams diverge between the two '
            f'drivers (AC-MAP-09):\n' + '\n'.join('  - ' + m for m in messages)
            + '\npython stream: '
            + ' -> '.join(canonical.format_event(e) for e in canon_py)
            + '\ncpp stream:    '
            + ' -> '.join(canonical.format_event(e) for e in canon_cpp))
