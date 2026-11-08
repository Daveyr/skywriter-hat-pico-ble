'''Loaders for the recorded sensor frames in specs/fixtures.

Manifest metadata and expectations live only in ``specs/fixtures/manifest.json``
(that is the source of truth); these helpers just read it and replay it.
'''

import functools
import json
import pathlib

FIXTURE_DIR = pathlib.Path(__file__).resolve().parents[1] / 'specs' / 'fixtures'


@functools.lru_cache(maxsize=1)
def load_manifest():
    '''Parse specs/fixtures/manifest.json (cached — one read per test run).'''
    with open(FIXTURE_DIR / 'manifest.json') as f:
        return json.load(f)


@functools.lru_cache(maxsize=None)
def load_frame(name):
    '''Load a fixture frame as raw bytes (its hex file includes the header).'''
    meta = load_manifest()['frames'][name]
    raw = open(FIXTURE_DIR / meta['file']).read().strip()
    return bytes.fromhex(raw)


def scenario(manifest, name):
    '''Return one scenario dict by name.'''
    for s in manifest['scenarios']:
        if s['name'] == name:
            return s
    raise KeyError(f'unknown scenario: {name}')


def frame_bytes(scenario):
    '''Ordered list of frame bytes for a scenario (frames read in order).'''
    return [load_frame(n) for n in scenario['frames']]
