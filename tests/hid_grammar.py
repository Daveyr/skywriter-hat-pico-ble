'''HID outcome-record grammar (fix_plan P3.2).

Machine-checkable schema for the per-scenario HID output expectations in
``specs/fixtures/manifest.json`` (``expect.hid``): exactly what the
gesture→HID mapping engine may emit for a replayed scenario, expressed in the
report-channel vocabulary of ``specs/hid_mapping.md`` §3–§6.

Records (channel/action -> keys)::

    {"channel": "mouse", "action": "move",    "dx", "dy"}          signed raw→report deltas
    {"channel": "mouse", "action": "button",  "button", "state"}   button left/middle/right, down/up
    {"channel": "mouse", "action": "wheel",   "notches"}           + = scroll up (away from user)
    {"channel": "mouse", "action": "click",   "button", "count", "click_ms"?}
                  press+release pair(s) of TAP_CLICK_MS each (tap/doubletap)
    {"channel": "keyboard", "action": "press", "key", "usage"}    page_up/page_down
    {"channel": "consumer", "action": "press", "usage"}           media/volume usage code

Usage codes are the decimal USB HID usage IDs from hid_mapping.md §6:
Next Track 0x00B5=181, Previous Track 0x00B6=182, Volume Increment 0x00E9=233,
Volume Decrement 0x00EA=234; Page Up 0x4E=78, Page Down 0x4F=79.

What this module verifies today is **well-formedness** (the migration to a
machine-checkable format): every ``expect.hid`` list parses against the grammar
above. Replay-asserting the records against a live mapping engine is armed by
the mapping-engine items P3.12–P3.15, which target exactly these scenarios
(the manifest is their machine-readable acceptance data).
'''

MOUSE_ACTIONS = {
    'move': frozenset({'dx', 'dy'}),
    'button': frozenset({'button', 'state'}),
    'wheel': frozenset({'notches'}),
    'click': frozenset({'button', 'count', 'click_ms'}),
}
KEYBOARD_ACTIONS = {
    'press': frozenset({'key', 'usage'}),
}
CONSUMER_ACTIONS = {
    'press': frozenset({'usage'}),
}

BUTTONS = ('left', 'middle', 'right')
BUTTON_STATES = ('down', 'up')
KEYBOARD_KEYS = {'page_up': 78, 'page_down': 79}
CONSUMER_USAGES = {
    181: 'Scan Next Track (0x00B5)',
    182: 'Scan Previous Track (0x00B6)',
    233: 'Volume Increment (0x00E9)',
    234: 'Volume Decrement (0x00EA)',
}
# TAP_CLICK_MS per specs/hid_mapping.md §4; scenarios may override only via a
# spec change, not silently per-scenario.
CLICK_MS = 50


def validate(hid_records, scenario_name):
    '''Raise AssertionError with a readable message on any malformed record.'''
    for index, record in enumerate(hid_records):
        where = f'{scenario_name}.hid[{index}]'
        assert isinstance(record, dict), f'{where}: record must be a dict'
        channel = record.get('channel')
        action = record.get('action')
        if channel == 'mouse':
            actions = MOUSE_ACTIONS
        elif channel == 'keyboard':
            actions = KEYBOARD_ACTIONS
        elif channel == 'consumer':
            actions = CONSUMER_ACTIONS
        else:
            raise AssertionError(
                f"{where}: unknown channel {channel!r} "
                f'(expected mouse, keyboard or consumer)')
        assert action in actions, \
            f'{where}: unknown {channel} action {action!r}'
        want_keys = {'channel', 'action'} | set(actions[action])
        assert set(record) ^ want_keys == set(), \
            f'{where}: keys {sorted(record)} must be exactly {sorted(want_keys)}'

        if action == 'button':
            assert record['button'] in BUTTONS, f'{where}: button {record["button"]!r}'
            assert record['state'] in BUTTON_STATES, f'{where}: state {record["state"]!r}'
        elif action == 'move':
            for axis in ('dx', 'dy'):
                assert isinstance(record[axis], int) and not isinstance(
                    record[axis], bool), f'{where}: {axis} must be a signed int'
        elif action == 'wheel':
            notches = record['notches']
            assert isinstance(notches, int) and not isinstance(notches, bool), \
                f'{where}: notches must be a signed int'
            assert notches != 0, f'{where}: a wheel record means at least one notch'
        elif action == 'click':
            assert record['button'] in BUTTONS, f'{where}: button {record["button"]!r}'
            count = record['count']
            assert isinstance(count, int) and count >= 1, \
                f'{where}: click count must be >= 1'
            click_ms = record.get('click_ms')
            assert click_ms is None or (
                isinstance(click_ms, int) and click_ms > 0), \
                f'{where}: click_ms must be a positive int'
        elif channel == 'keyboard':
            usage = KEYBOARD_KEYS.get(record['key'])
            assert usage is not None, \
                f"{where}: keyboard key {record['key']!r} not in {sorted(KEYBOARD_KEYS)}"
            assert record['usage'] == usage, \
                f"{where}: usage {record['usage']!r} != {usage} for {record['key']!r}"
        elif channel == 'consumer':
            usage = record['usage']
            assert usage in CONSUMER_USAGES, \
                f'{where}: consumer usage {usage!r} not a §6 media usage ' \
                f'{sorted(CONSUMER_USAGES)}'
