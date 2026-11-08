'''Virtual clock for replay tests — simulated elapsed time, zero sleeping.

The fixtures contain time-dependent expectations (e.g. ``time_gap_ms`` for
touch release-after-silence and hold-to-scroll cadence, see
``specs/fixtures/README.md``). Replay must simulate those gaps on a simulated
clock so tests stay fast and deterministic. Adapter code that would otherwise
read the wall clock (e.g. the Python driver's ``millis()``) is pointed at this
clock by its adapter.
'''


class VirtualClock:
    '''A millisecond clock that only moves when the test tells it to.'''

    def __init__(self):
        self._ms = 0.0

    def advance(self, ms):
        '''Move the simulated time forward by ``ms`` milliseconds (no sleep).'''
        self._ms += ms
        return self._ms

    @property
    def now_ms(self):
        return self._ms
