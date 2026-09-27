"""Exhaustive search with the THROWAWAY mini BFS (stream 01 owns the real checker).

Default run: 2 injections (a few seconds per version). Set FLEETFLIGHT_FULL=1 for the default
model bounds (3 injections, 3500 ms horizon, ~30 s per version); numbers are in status/02-model.md.
"""
from __future__ import annotations

import os

import pytest

from fleetflight.core import Bounds
from fleetflight.models import load_model

from ._mini_bfs import bfs
from ._script import run_script

FULL = os.environ.get("FLEETFLIGHT_FULL") == "1"
BOUNDS = None if FULL else Bounds(max_depth=120, max_injections=2, horizon_ms=3500)

EXPECTED = {"v0.3.1": ["I1", "I2", "I4"], "v0.3.2": ["I1", "I4"], "v0.3.3": []}


@pytest.mark.parametrize("v", sorted(EXPECTED))
def test_exhaustive_results(v: str) -> None:
    m = load_model(sut=v, bounds=BOUNDS)
    r = bfs(m)
    assert r.complete
    assert r.failed == EXPECTED[v], {k: [x.label for x in p if x.injected] for k, (_, p) in r.first_violation.items()}


@pytest.mark.parametrize("v", ["v0.3.1", "v0.3.2"])
def test_counterexamples_replay(v: str) -> None:
    """Every counterexample the BFS finds replays through the same apply() and still violates."""
    m = load_model(sut=v, bounds=BOUNDS)
    r = bfs(m)
    for inv_id, (t_ms, path) in r.first_violation.items():
        s = m.init()
        for mv in path:
            s, _ = m.apply(s, mv)
        assert s.t_ms == t_ms
        inv = next(i for i in m.invariants if i.id == inv_id)
        assert not inv.check(s)


def test_minimal_i1_counterexample_for_v031() -> None:
    m = load_model(sut="v0.3.1", bounds=BOUNDS)
    t_ms, path = bfs(m).first_violation["I1"]
    assert t_ms == 500 and len(path) == 12
    assert [x.name for x in path if x.injected] == ["bms_fault", "network_loss"]


def test_v033_passes_with_the_readme_restart_as_a_prefix() -> None:
    """Sanity: the mini BFS agrees with the scripted run on the README sequence."""
    from fleetflight.core import Move

    script = [(100, Move("bms_fault")), (100, Move("bus_delay", (("msg", "fault@100"), ("extra_ms", 400)))),
              (200, Move("hub_restart"))]
    assert run_script(load_model(sut="v0.3.3"), script, 3500).failures() == {}
