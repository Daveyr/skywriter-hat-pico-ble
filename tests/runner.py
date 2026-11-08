'''Driver-agnostic replay runner (fix_plan item P3.1).

Loads a scenario from ``specs/fixtures/manifest.json``, asks its adapter to
play the scenario's frames in order into a **fresh** decoder state, advancing
the VirtualClock by ``time_gap_ms`` between frames (no sleeping), and collects
the decoder's native event records.

Usage::

    from tests import fixtures, adapter, runner
    manifest = fixtures.load_manifest()
    result = runner.replay(fixtures.scenario(manifest, 'tap_center'),
                           adapters.get_adapter('cpp'))
'''

from .adapters import get_adapter  # noqa: F401  (re-exported for convenience)
from .fixtures import frame_bytes, load_frame, load_manifest, scenario  # noqa: F401
from .virtual_clock import VirtualClock


class ReplayResult:
    '''Outcome of one replayed scenario: records + the simulated clock.'''

    def __init__(self, scenario, adapter_name, clock, records):
        self.scenario = scenario
        self.adapter_name = adapter_name
        self.clock = clock
        self.records = records

    def __repr__(self):
        return (f"<ReplayResult {self.scenario['name']}/"
                f"{self.adapter_name}: {len(self.records)} record(s)>")

    def kinds(self):
        '''List of record kinds, in emission order (handy for assertions).'''
        return [r['kind'] for r in self.records]


def replay(scenario, adapter):
    '''Replay one manifest scenario into a fresh decoder state via ``adapter``.'''
    clock = VirtualClock()
    frames = frame_bytes(scenario)
    gap_ms = scenario.get('time_gap_ms')
    records = adapter.replay_frames(frames, clock, gap_ms)
    return ReplayResult(scenario, adapter.name, clock, records)
