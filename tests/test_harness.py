'''Meta-tests for the fixture-replay harness itself (fix_plan item P3.1).

These prove the mechanism the decoder/mapping work items will build on:

- the manifest loads and every scenario replays into the Python driver and
  the C++ host decoder without error,
- decoder state is fresh per replay,
- the VirtualClock simulates ``time_gap_ms`` without wall-clock sleeping,
- plumbing sanity pins (what already matches the spec today): position
  decode (F01), flick dispatch (F02), tap dispatch (F09) on both adapters.

Spec-behaviour assertions for the known-red decoder deviation (D8) come
with the fix items P3.12–P3.19 and the structured naming of P3.2 — this file
deliberately asserts only what is true today. (D4, touch every-set-bit
dispatch, was closed 2026-11-05 with P3.10; D7, the Arduino driver's gesture
class/edge attributes, was closed 2026-11-05 with P3.11 — the C++ flick pin
below now asserts the full record; D9, the control-frame canonical events,
was closed 2026-11-05 with P3.11b — both drivers surface
`system_status`/`firmware_info` records now.)
'''

import time

import pytest

from tests import adapters, fixtures, runner


@pytest.fixture(scope='session')
def manifest():
    return fixtures.load_manifest()


@pytest.fixture(scope='session')
def cpp_adapter():
    # One shared instance; adaptation state is per-replay, and the compiled
    # host decoder binary is hash-cached on tests/build/.
    return adapters.get_adapter('cpp')


@pytest.fixture(scope='session')
def python_adapter():
    return adapters.get_adapter('python')


# ---------------------------------------------------------------- harness ---

def test_manifest_loads_and_every_scenario_is_replayable(manifest):
    assert manifest['schema'] == 'skywriter-fixtures/v2'
    assert manifest['frames'] and manifest['scenarios']

    # Loading every referenced fixture frame must succeed and every frame's
    # size byte must agree with its actual length (runs the inline check in
    # run_tests.sh against the same corpus, from the harness itself).
    for scenario in manifest['scenarios']:
        frames = fixtures.frame_bytes(scenario)
        assert len(frames) == len(scenario['frames'])
        for frame in frames:
            assert frame[0] == len(frame)


def test_virtual_clock_advances_without_sleeping():
    clock = runner.VirtualClock()
    assert clock.now_ms == 0
    started = time.monotonic()
    clock.advance(10_000)   # 10 simulated seconds, instantly
    elapsed = time.monotonic() - started
    assert clock.now_ms == 10_000
    assert elapsed < 0.1, 'VirtualClock must not sleep'


def test_every_scenario_replays_on_every_adapter(manifest, cpp_adapter):
    # The real value here: no scenario may blow up either driver. Whether each
    # scenario produces *any* record is checked by the plumbing pins below and,
    # per scenario, by the spec-assertion items (P3.2, P3.3+): some scenarios
    # legitimately produce nothing (e.g. "gesture in progress" emits no event;
    # the 0x15/0x83 control frames emit exactly one control event each since
    # P3.11b).
    python_adapter = adapters.get_adapter('python')

    for scenario in manifest['scenarios']:
        result_py = runner.replay(scenario, python_adapter)
        result_cpp = runner.replay(scenario, cpp_adapter)
        assert isinstance(result_py.records, list)
        assert isinstance(result_cpp.records, list)


def test_fresh_decoder_state_per_replay(cpp_adapter, python_adapter):
    # Replaying the same scenario twice must give identical records — proves
    # "fresh decoder state"; state leaking between runs would change the
    # deltas the decoder computes.
    scenario = fixtures.scenario(fixtures.load_manifest(), 'flick_east_west')
    first = runner.replay(scenario, cpp_adapter)
    second = runner.replay(scenario, cpp_adapter)
    assert first.records == second.records

    scenario = fixtures.scenario(fixtures.load_manifest(), 'tap_center')
    first = runner.replay(scenario, python_adapter)
    second = runner.replay(scenario, python_adapter)
    assert first.records == second.records


def test_simulated_time_gap_between_frames(python_adapter):
    # The release-by-silence scenario carries time_gap_ms=250. The clock ends
    # up advanced by gap x frame_count: one advance between each pair of
    # frames, one more so the post-scenario finish() check (once P3.13's
    # mapping adapter exists) can evaluate "release 250 ms after the last
    # touch frame" — all simulated, zero wall time.
    scenario = fixtures.scenario(fixtures.load_manifest(),
                                 'touch_press_and_release')
    result = runner.replay(scenario, python_adapter)
    assert scenario['time_gap_ms'] == 250
    assert result.clock.now_ms == 250 * len(scenario['frames'])


# ------------------------------------------------- plumbing sanity pins ----

def test_python_adapter_position_values(python_adapter):
    # F01: x=500, y=1000, z=200 (raw/65536 rounded to 4 dp by the driver).
    scenario = fixtures.scenario(fixtures.load_manifest(), 'position_track')
    result = runner.replay(scenario, python_adapter)
    assert [r['kind'] for r in result.records] == ['move']
    (move,) = result.records
    assert move['x'] == pytest.approx(0.0076)
    assert move['y'] == pytest.approx(0.0153)
    assert move['z'] == pytest.approx(0.0031)


def test_python_adapter_flick_dispatch(python_adapter):
    scenario = fixtures.scenario(fixtures.load_manifest(), 'flick_west_east')
    result = runner.replay(scenario, python_adapter)
    # F02's gesture word 02 10 02 00: code 2, class 1 (flick), edge flag
    # clear — bit 17 is reserved and must stay ignored.
    assert result.records == [{
        'kind': 'flick', 'from': 'west', 'to': 'east',
        'code': 2, 'class': 1, 'edge': False,
    }]


def test_python_adapter_tap_dispatch(python_adapter):
    scenario = fixtures.scenario(fixtures.load_manifest(), 'tap_center')
    result = runner.replay(scenario, python_adapter)
    assert result.records == [{'kind': 'tap', 'zone': 'center'}]


def test_cpp_adapter_position_values(cpp_adapter):
    scenario = fixtures.scenario(fixtures.load_manifest(), 'position_track')
    result = runner.replay(scenario, cpp_adapter)
    assert result.records == [{'kind': 'move', 'x': 500, 'y': 1000, 'z': 200}]


def test_cpp_adapter_flick_dispatch(cpp_adapter):
    scenario = fixtures.scenario(fixtures.load_manifest(), 'flick_west_east')
    result = runner.replay(scenario, cpp_adapter)
    # F02's gesture word 02 10 02 00: code 2 (SW_FLICK_WEST_EAST), class 1
    # (flick), edge flag clear, bit 17 reserved and ignored — the full
    # GestureInfo decode the driver carries since P3.11.
    assert result.records == [{
        'kind': 'gesture', 'code': 2, 'class': 1, 'edge': False,
    }]


def test_cpp_adapter_tap_dispatch(cpp_adapter):
    scenario = fixtures.scenario(fixtures.load_manifest(), 'tap_center')
    result = runner.replay(scenario, cpp_adapter)
    assert result.records == [{'kind': 'touch_code', 'code': 5}]  # SW_TAP_CENTER
