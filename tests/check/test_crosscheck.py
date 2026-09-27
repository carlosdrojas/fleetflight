"""The BFS checker against the independent DFS oracle (tests/check/oracle.py) on every toy.

Both must agree on PASS/FAIL for each invariant, and the BFS counterexample must be no longer
than any violating path the oracle finds.
"""
from __future__ import annotations

import pytest

from fleetflight.check import check
from fleetflight.core import Bounds

from .oracle import oracle_all_violating_lengths, oracle_check
from .test_toy_counter import CounterModel
from .test_toy_race import RaceModel
from .test_toy_timer import TimerModel
from .toykit import by_id

CASES = [
    ("counter", lambda b: CounterModel(b), Bounds(20, 2, 600)),
    ("counter-deep", lambda b: CounterModel(b), Bounds(8, 3, 2000)),
    ("race", lambda b: RaceModel(b), Bounds(10, 4, 200)),
    ("race-short-budget", lambda b: RaceModel(b), Bounds(10, 3, 200)),
    ("race-shallow", lambda b: RaceModel(b), Bounds(3, 4, 200)),
    ("timer", lambda b: TimerModel(b), Bounds(20, 3, 600)),
    ("timer-no-restart", lambda b: TimerModel(b, ("fault", "bus_delay")), Bounds(20, 3, 600)),
    ("timer-no-delay", lambda b: TimerModel(b, ("fault", "restart")), Bounds(20, 3, 600)),
    ("timer-short-horizon", lambda b: TimerModel(b), Bounds(20, 3, 150)),
    ("timer-depth-6", lambda b: TimerModel(b), Bounds(6, 3, 600)),
    ("timer-depth-7", lambda b: TimerModel(b), Bounds(7, 3, 600)),
]


@pytest.mark.parametrize("name,make,bounds", CASES, ids=[c[0] for c in CASES])
def test_bfs_agrees_with_oracle(name, make, bounds) -> None:
    model = make(bounds)
    rows = by_id(check(model, bounds, stop_when_all_failed=False))
    shortest = oracle_check(model, bounds)
    lengths = oracle_all_violating_lengths(model, bounds)
    for inv in model.invariants:
        row = rows[inv.id]
        oracle_fails = shortest[inv.id] is not None
        assert (row["result"] == "FAIL") == oracle_fails, (name, inv.id)
        assert bool(lengths[inv.id]) == oracle_fails, (name, inv.id)
        if oracle_fails:
            assert row["depth"] <= len(shortest[inv.id]), (name, inv.id)
            assert row["depth"] == min(lengths[inv.id]), (name, inv.id)


def test_depth_bound_is_exact_for_timer() -> None:
    """The timer counterexample needs exactly 7 moves: depth 6 must PASS, depth 7 must FAIL."""
    assert check(TimerModel(Bounds(6, 3, 600)), Bounds(6, 3, 600)).verdict == "PASS"
    assert check(TimerModel(Bounds(7, 3, 600)), Bounds(7, 3, 600)).verdict == "FAIL"
