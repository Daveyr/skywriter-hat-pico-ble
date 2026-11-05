'''Adapter contract for the driver-agnostic replay runner (fix_plan P3.1).

An adapter wraps one sensor-event decoder and exposes it in a common shape:

- ``begin(clock)``     build a **fresh** decoder state (reset + handler capture)
- ``feed(frame, clock)`` replay one raw I2C frame; return the records the
                          decoder produced for that frame
- ``finish(clock)``    called once after the last frame; may evaluate
                          time-dependent outcomes (release-after-silence etc.)
- ``replay_frames(...)`` override for decoders whose state lives outside this
                          process (the C++ host decoder spawns one process per
                          scenario, so it needs the whole frame list at once)

Records are plain dicts of whatever the wrapped decoder actually emits, in
emission order, e.g. ``{"kind": "move", "x":..., "y":..., "z":...}``. They are
deliberately *native* (Python floats / C++ raw ints / Arduino touch codes) at
this stage; the structured canonical-event grammar in fix_plan item P3.2 will
normalize them for cross-driver parity assertions.
'''


class ReplayAdapter:
    name = 'abstract'

    def begin(self, clock):
        raise NotImplementedError

    def feed(self, frame, clock):
        raise NotImplementedError

    def finish(self, clock):
        return []

    def replay_frames(self, frames, clock, gap_ms):
        '''Play frames in order into a fresh state, advancing the clock.

        ``gap_ms`` is the per-scenario ``time_gap_ms`` from the manifest: it
        is simulated between consecutive frames and once more after the last
        frame (before ``finish``) so timed expectations recorded against the
        final frame can be evaluated. All time movement is on the simulated
        clock — nothing sleeps.
        '''
        self.begin(clock)
        records = []
        for idx, frame in enumerate(frames):
            if idx and gap_ms:
                clock.advance(gap_ms)
            records.extend(self.feed(frame, clock))
        if gap_ms:
            clock.advance(gap_ms)
        records.extend(self.finish(clock))
        return records


def get_adapter(name):
    '''Instantiate an adapter by key: 'python' or 'cpp'.'''
    if name == 'python':
        from .adapters_python import PythonDriverAdapter
        return PythonDriverAdapter()
    if name == 'cpp':
        from .adapters_cpp import CppDecoderAdapter
        return CppDecoderAdapter()
    raise ValueError(f'unknown adapter: {name}')
