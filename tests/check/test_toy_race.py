"""Toy (b): the classic two-process lost-update race. Must FAIL with a 4-move counterexample.

Each process increments a shared ``x`` non-atomically: ``step`` 1 reads x into a register,
``step`` 2 writes register+1 back. The scheduler (the adversary) picks which process steps, so
``step(proc=p)`` is an injection. Once both are done, x must be 2 (I1). The shortest violation
is read, read, write, write: exactly 4 moves, 0 ticks. I2 (x never exceeds 2) holds.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

from fleetflight.check import check
from fleetflight.core import TICK, TICK_MS, Bounds, Invariant, Move

from .oracle import oracle_all_violating_lengths, oracle_check
from .toykit import ToyModel, assert_report_valid, by_id, cex_for, ev

IDLE, READ, DONE = 0, 1, 2


def step(p: int) -> Move:
    return Move("step", (("proc", p),))


@dataclass(frozen=True, slots=True)
class RState:
    t_ms: int = 0
    x: int = 0
    pc: tuple[int, int] = (IDLE, IDLE)
    reg: tuple[int, int] = (0, 0)
    budget: int = 0


class RaceModel(ToyModel):
    name = "toy-race"
    invariants = [
        Invariant("I1", "NO_LOST_UPDATE", "After both increments finish, x is 2.",
                  "G(pc1=DONE ∧ pc2=DONE → x=2)",
                  lambda s: not (s.pc == (DONE, DONE)) or s.x == 2),
        Invariant("I2", "X_AT_MOST_2", "x never exceeds 2.", "G(x ≤ 2)", lambda s: s.x <= 2),
    ]

    def init(self) -> RState:
        return RState(budget=self.bounds.max_injections)

    def moves(self, s: RState) -> list[Move]:
        inj = [step(p) for p in (1, 2) if s.pc[p - 1] != DONE] if s.budget > 0 else []
        return inj + [TICK]

    def apply(self, s: RState, m: Move):
        self._require(s, m)
        if m == TICK:
            return replace(s, t_ms=s.t_ms + TICK_MS), []
        i = int(m.arg("proc")) - 1
        pc, reg = list(s.pc), list(s.reg)
        if pc[i] == IDLE:
            pc[i], reg[i] = READ, s.x
            x, what = s.x, f"p{i + 1} reads x={s.x}"
        else:
            pc[i], x = DONE, reg[i] + 1
            what = f"p{i + 1} writes x={x}"
        s2 = RState(s.t_ms, x, (pc[0], pc[1]), (reg[0], reg[1]), s.budget - 1)
        return s2, ev(s.t_ms, "step", what, injected=True)

    def snapshot(self, s: RState):
        names = {IDLE: "idle", READ: "read", DONE: "done"}
        return {"t_ms": s.t_ms, "x": s.x,
                "p1": f"{names[s.pc[0]]} reg={s.reg[0]}", "p2": f"{names[s.pc[1]]} reg={s.reg[1]}",
                "budget": s.budget}


BOUNDS = Bounds(max_depth=10, max_injections=4, horizon_ms=200)
CEX_LEN = 4


def _violates_i1(model: RaceModel, path: list[Move]) -> bool:
    s = model.init()
    for mv in path:
        s, _ = model.apply(s, mv)
    return not model.invariants[0].check(s)


def test_race_fails_with_known_length() -> None:
    report = check(RaceModel(BOUNDS), BOUNDS)
    assert_report_valid(report)
    rows = by_id(report)
    assert report.verdict == "FAIL" and report.exit_code == 1
    assert rows["I1"]["result"] == "FAIL" and rows["I2"]["result"] == "PASS"
    cex = cex_for(report, "I1")
    assert rows["I1"]["depth"] == cex["search"]["depth"] == CEX_LEN
    assert len(cex["trace"]) == CEX_LEN + 1
    assert cex["ticks"] == 0 and cex["violated_at_ms"] == 0
    assert cex["violation_duration_ms"] is None
    assert [mv["tick_index"] for mv in cex["moves"]] == [0] * CEX_LEN
    procs = [mv["move"]["args"]["proc"] for mv in cex["moves"]]
    assert sorted(procs) == [1, 1, 2, 2]
    # Both reads happen before either write.
    assert all("reads" in cex["trace"][i]["events"][0]["detail"] for i in (1, 2))
    assert cex["trace"][-1]["violations"] == ["I1"]
    assert "violations" not in cex["trace"][0]
    assert cex["search"]["minimal"] is True
    # The report stays complete: I2 still has to be proven, so the search did not stop early.
    assert report.to_json()["stats"]["complete"] is True


def test_race_counterexample_is_minimal_by_brute_force() -> None:
    """Enumerate EVERY move sequence of length <= CEX_LEN: nothing shorter violates I1."""
    model = RaceModel(BOUNDS)
    violating_lengths = set()
    for n in range(CEX_LEN + 1):
        # Every sequence over the move alphabet, filtered to the enabled ones step by step.
        alphabet = [step(1), step(2), TICK]
        for path in itertools.product(alphabet, repeat=n):
            s, ok = model.init(), True
            for mv in path:
                if mv not in model.moves(s):
                    ok = False
                    break
                s, _ = model.apply(s, mv)
            if ok and not model.invariants[0].check(s):
                violating_lengths.add(n)
    assert min(violating_lengths) == CEX_LEN
    cex = cex_for(check(model, BOUNDS), "I1")
    assert _violates_i1(model, [Move.from_json(t["move"]) for t in cex["trace"][1:]])


def test_race_agrees_with_oracle() -> None:
    model = RaceModel(BOUNDS)
    oracle = oracle_check(model, BOUNDS)
    lengths = oracle_all_violating_lengths(model, BOUNDS)
    report = check(model, BOUNDS)
    assert oracle["I2"] is None and by_id(report)["I2"]["result"] == "PASS"
    assert oracle["I1"] is not None and len(oracle["I1"]) == CEX_LEN
    assert min(lengths["I1"]) == by_id(report)["I1"]["depth"]


def test_budget_too_small_means_pass() -> None:
    b = Bounds(max_depth=10, max_injections=3, horizon_ms=200)
    report = check(RaceModel(b), b)
    assert report.verdict == "PASS"
    assert report.to_json()["stats"]["complete"] is True
