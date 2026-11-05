'''Deviation-ledger reader (fix_plan P3.2).

``specs/README.md``'s "Known driver deviations" table is the **single source
of truth** for which spec deviations are still open, and in which driver.
This module parses it so tests and fixture annotations never hard-copy that
status a second time (AGENTS.md "Search first"; specs win over code).

Adapter/driver keys used everywhere in the harness:

- ``python`` — the Raspberry Pi Python driver (``library/skywriter/__init__.py``)
- ``cpp``    — the Arduino/C++ driver (``arduino/Skywriter/skywriter.cpp``),
               the same source that runs on the Pico W

Ledger row shape (pipe table)::

    | D3 | Python + Arduino | AirWheel delta ignores the 8-bit counter wrap… | evidence |

The second cell lists affected drivers (free text naming "Python" and/or
"Arduino"; documentation-only deviations such as D8 name neither).
'''

import functools
import pathlib
import re

README = pathlib.Path(__file__).resolve().parents[1] / 'specs' / 'README.md'

# adapter/driver key -> case-insensitive token searched in the ledger's
# "Driver" cell.
_ADAPTER_TOKENS = {'python': 'python', 'cpp': 'arduino'}

_ROW = re.compile(r'^\|\s*(D\d+)\s*\|\s*([^|]+?)\s*\|')


@functools.lru_cache(maxsize=1)
def table():
    '''Deviation id -> set of adapter/driver keys affected by that deviation.'''
    rows = {}
    for line in README.read_text(errors='replace').splitlines():
        match = _ROW.match(line)
        if not match:
            continue
        dev_id, drivers_cell = match.groups()
        drivers = set()
        for driver_key, token in _ADAPTER_TOKENS.items():
            if token in drivers_cell.lower():
                drivers.add(driver_key)
        rows[dev_id] = drivers
    return rows


def exists(dev_id):
    '''The deviation id appears in the specs/README.md ledger.'''
    return dev_id in table()


def is_open(dev_id):
    '''Every row in the table is an open (unfixed) deviation by definition.'''
    return exists(dev_id)


def affects(dev_id, driver):
    '''Does this open deviation affect the named adapter/driver key?'''
    return driver in table().get(dev_id, set())


def affects_only_driver(dev_id, driver):
    '''Right tool for "this discrepancy exists on one driver only": the
    deviation is listed for exactly that driver (and not the other one).'''
    return table().get(dev_id, frozenset()) == {driver}


def all_deviation_ids():
    return set(table())
