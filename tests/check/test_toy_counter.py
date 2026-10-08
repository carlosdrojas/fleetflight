"""Toy (a): a counter with a known unreachable bad state. Every invariant must PASS.

x lives in Z/10. TICK adds 2; the injection ``double`` doubles x. From x=0 only even values
are reachable, so "x is odd" never happens (I1) and nor does x=7 (I2). A bounded invariant (I3)
whose timer never exceeds its bound checks that ``worst_case_ms`` is reported.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from fleetflight.check import check
from fleetflight.core import TICK, TICK_MS, Bounds, Invariant, Move

from .toykit import ToyModel, assert_report_valid, by_id, ev

DOUBLE = Move("double")


@dataclass(frozen=True, slots=True)
class CState:
    t_ms: int = 0
    x: int = 0
    budget: int = 0
    since: int | None = None     # t_ms at which x became >= 6 (bounded condition), else None


class CounterModel(ToyModel):
    name = "toy-counter"
    invariants = [
        Invariant("I1", "X_EVEN", "x is always even.", "G(x mod 2 = 0)", lambda s: s.x % 2 == 0),
        Invariant("I2", "X_NEVER_7", "x never equals 7.", "G(x != 7)", lambda s: s.x != 7),
        Invariant("I3", "HIGH_X_BOUNDED", "x never stays >= 6 for more than 200 ms.",
                  "G(x>=6 -> (t - since) <= 200)",
                  lambda s: s.since is None or s.t_ms - s.since <= 200,
                  bound_ms=200, timer_key="high_since_ms"),
    ]

    def init(self) -> CState:
        return CState(budget=self.bounds.max_injections)

    def moves(self, s: CState) -> list[Move]:
        return [DOUBLE, TICK] if s.budget > 0 else [TICK]

    def apply(self, s: CState, m: Move):
        self._require(s, m)
        if m == TICK:
            s2 = replace(s, t_ms=s.t_ms + TICK_MS, x=(s.x + 2) % 10)
            events = ev(s2.t_ms, "inc", f"x={s2.x}")
        else:
            s2 = replace(s, x=(2 * s.x) % 10, budget=s.budget - 1)
            events = ev(s.t_ms, "double", f"x={s2.x}", injected=True)
        high = s2.x >= 6
        return replace(s2, since=(s.since if s.since is not None else s2.t_ms) if high else None), events

    def snapshot(self, s: CState):
        return {"t_ms": s.t_ms, "x": s.x, "budget": s.budget, "high_since_ms": s.since}


BOUNDS = Bounds(max_depth=30, max_injections=2, horizon_ms=1000)


def test_counter_passes_everything() -> None:
    report = check(CounterModel(BOUNDS), BOUNDS)
    assert_report_valid(report)
    doc = report.to_json()
    assert doc["verdict"] == "PASS" and report.exit_code == 0
    assert report.counterexamples == {}
    assert doc["counterexample_files"] == []
    rows = by_id(report)
    assert [r["result"] for r in rows.values()] == ["PASS", "PASS", "PASS"]
    assert rows["I1"]["worst_case_ms"] is None
    # Window rule: open while x >= 6, closed at the first state where x < 6. With 2 doubles:
    assert rows["I3"]["worst_case_ms"] == 200  # 6 -tick-> 8 -double-> 6, twice, 8, then 0 at +200
    stats = doc["stats"]
    assert stats["complete"] is True
    assert stats["new_states_per_depth"][0] == 1
    assert sum(stats["new_states_per_depth"]) == stats["states"]
    assert stats["max_depth_reached"] == len(stats["new_states_per_depth"]) - 1
    assert "notes" not in doc


def test_state_count_matches_hand_enumeration() -> None:
    """The visited set is keyed on state equality: count distinct reachable states by hand."""
    m = CounterModel(BOUNDS)
    seen = {m.init()}
    frontier = [(m.init(), 0)]
    while frontier:
        s, d = frontier.pop()
        if d >= BOUNDS.max_depth or s.t_ms >= BOUNDS.horizon_ms:
            continue
        for mv in m.moves(s):
            s2, _ = m.apply(s, mv)
            if s2 not in seen:
                seen.add(s2)
                frontier.append((s2, d + 1))
    # DFS reaching a state first at a larger depth could under-explore, so only compare when
    # the depth bound is not binding (horizon cuts first: 1000 ms = 20 ticks + 2 doubles < 30).
    assert check(m, BOUNDS).to_json()["stats"]["states"] == len(seen)


def test_depth_bound_limits_search() -> None:
    small = Bounds(max_depth=3, max_injections=2, horizon_ms=1000)
    stats = check(CounterModel(small), small).to_json()["stats"]
    assert stats["max_depth_reached"] == 3
    assert len(stats["new_states_per_depth"]) == 4


def test_horizon_bound_limits_search() -> None:
    b = Bounds(max_depth=100, max_injections=0, horizon_ms=200)
    stats = check(CounterModel(b), b).to_json()["stats"]
    # No injections: a single chain of 4 ticks (0..200 ms), the state at 200 is not expanded.
    assert stats["states"] == 5
    assert stats["transitions"] == 4
    assert stats["new_states_per_depth"] == [1, 1, 1, 1, 1]
