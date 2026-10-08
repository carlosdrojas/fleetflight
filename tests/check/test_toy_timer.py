"""Toy (c): a bounded-timer property violated only when two injections line up.

A fault message must switch the output off within 150 ms (I1, timer ``since_ms``).
* Nominal: the message arrives 50 ms after the fault: 50 ms.
* ``bus_delay`` alone: +100 ms: exactly 150 ms, still within the bound.
* ``restart`` alone: the controller is down 150 ms and drops what arrives meanwhile, but polls
  the fault line when it boots: at most 150 ms (restart at the fault), still within the bound.
* Both, lined up: fault and delay at 0 ms (message due at 150), restart at exactly 100 ms (down
  until 250). The message is dropped at 150 and the output is still on at 200: 200 > 150.
  Shortest path: 3 injections + 4 ticks = 7 moves, violated at 200 ms, duration 200 ms.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from fleetflight.check import check
from fleetflight.core import TICK, TICK_MS, Bounds, Invariant, Move, trace_hash

from .oracle import oracle_all_violating_lengths, oracle_check
from .toykit import ToyModel, assert_report_valid, by_id, cex_for, ev

FAULT = Move("fault")
DELAY = Move("bus_delay", (("msg", "fault#1"), ("extra_ms", 100)))
RESTART = Move("restart")
BOUND_MS, LATENCY_MS, BOOT_MS = 150, 50, 150


@dataclass(frozen=True, slots=True)
class TState:
    t_ms: int = 0
    fault_at: int | None = None
    msg_due: int | None = None
    delayed: bool = False
    down_until: int | None = None
    out_on: bool = True
    budget: int = 0

    @property
    def since(self) -> int | None:
        return self.fault_at if self.fault_at is not None and self.out_on else None


class TimerModel(ToyModel):
    name = "toy-timer"
    invariants = [
        Invariant("I1", "FAULT_OFF_BOUNDED", "After a fault the output is off within 150 ms.",
                  "G(fault ∧ out=ON → (t − since_ms) ≤ 150)",
                  lambda s: s.since is None or s.t_ms - s.since <= BOUND_MS,
                  bound_ms=BOUND_MS, timer_key="since_ms"),
        Invariant("I2", "OFF_ONLY_AFTER_FAULT", "The output only switches off after a fault.",
                  "G(out=OFF → fault)", lambda s: s.out_on or s.fault_at is not None),
    ]

    def __init__(self, bounds: Bounds, allowed: tuple[str, ...] = ("fault", "bus_delay", "restart")):
        super().__init__(bounds)
        self.allowed = allowed

    def init(self) -> TState:
        return TState(budget=self.bounds.max_injections)

    def moves(self, s: TState) -> list[Move]:
        inj = []
        if s.budget > 0:
            if s.fault_at is None:
                inj.append(FAULT)
            if s.msg_due is not None and not s.delayed:
                inj.append(DELAY)
            if s.down_until is None:
                inj.append(RESTART)
        return [m for m in inj if m.name in self.allowed] + [TICK]

    def apply(self, s: TState, m: Move):
        self._require(s, m)
        t = s.t_ms
        if m == FAULT:
            return replace(s, fault_at=t, msg_due=t + LATENCY_MS, budget=s.budget - 1), ev(t, "fault", "", True)
        if m == DELAY:
            return replace(s, msg_due=s.msg_due + 100, delayed=True, budget=s.budget - 1), ev(t, "bus_delay", "+100 ms", True)
        if m == RESTART:
            return replace(s, down_until=t + BOOT_MS, budget=s.budget - 1), ev(t, "restart", "", True)
        t += TICK_MS
        events = []
        down_until, out_on, msg_due = s.down_until, s.out_on, s.msg_due
        if down_until is not None and t >= down_until:
            down_until = None
            events += ev(t, "boot", "polls fault line")
            if s.fault_at is not None:
                out_on = False
        if msg_due is not None and t >= msg_due:
            msg_due = None
            if down_until is None:
                out_on = False
                events += ev(t, "deliver", "fault#1 -> output off")
            else:
                events += ev(t, "drop", "fault#1 arrived while booting")
        return replace(s, t_ms=t, down_until=down_until, out_on=out_on, msg_due=msg_due), events

    def snapshot(self, s: TState):
        return {"t_ms": s.t_ms, "fault_at": s.fault_at, "msg_due": s.msg_due,
                "ctl": "UP" if s.down_until is None else f"BOOTING until {s.down_until}",
                "out": "ON" if s.out_on else "OFF", "since_ms": s.since, "budget": s.budget}


BOUNDS = Bounds(max_depth=20, max_injections=3, horizon_ms=600)


def test_two_injections_lined_up_violate() -> None:
    report = check(TimerModel(BOUNDS), BOUNDS)
    assert_report_valid(report)
    rows = by_id(report)
    assert rows["I1"]["result"] == "FAIL" and rows["I2"]["result"] == "PASS"
    cex = cex_for(report, "I1")
    assert cex["search"]["depth"] == 7 and cex["ticks"] == 4
    assert cex["violated_at_ms"] == 200 == rows["I1"]["violated_at_ms"]
    assert cex["violation_duration_ms"] == 200 == rows["I1"]["violation_duration_ms"]
    assert [(mv["tick_index"], mv["t_ms"], mv["move"]["name"]) for mv in cex["moves"]] == [
        (0, 0, "fault"), (0, 0, "bus_delay"), (2, 100, "restart")]
    assert cex["moves"][1]["move"]["args"] == {"msg": "fault#1", "extra_ms": 100}
    assert cex["trace"][-1]["snapshot"]["since_ms"] == 0
    assert any(e["name"] == "drop" for step in cex["trace"] for e in step["events"])


def test_each_injection_alone_is_within_bound() -> None:
    for allowed, worst in ((("fault",), 50), (("fault", "bus_delay"), 150), (("fault", "restart"), 150)):
        report = check(TimerModel(BOUNDS, allowed), BOUNDS)
        assert report.verdict == "PASS", allowed
        assert by_id(report)["I1"]["worst_case_ms"] == worst, allowed


def test_counterexample_replays_to_same_hash() -> None:
    """Replay rule (CONTRACT.md §4): moves + ticks rebuild the path and the trace hash."""
    model = TimerModel(BOUNDS)
    cex = cex_for(check(model, BOUNDS), "I1")
    s = model.init()
    steps = [(None, model.snapshot(s))]
    for k in range(cex["ticks"] + 1):
        for mv in cex["moves"]:
            if mv["tick_index"] == k:
                m = Move.from_json(mv["move"])
                s, _ = model.apply(s, m)
                steps.append((m, model.snapshot(s)))
        if k < cex["ticks"]:
            s, _ = model.apply(s, TICK)
            steps.append((TICK, model.snapshot(s)))
    assert trace_hash(steps) == cex["trace_hash"]
    assert [snap for _, snap in steps] == [st["snapshot"] for st in cex["trace"]]
    assert cex["violated_at_ms"] == cex["ticks"] * TICK_MS


def test_timer_agrees_with_oracle() -> None:
    model = TimerModel(BOUNDS)
    oracle = oracle_check(model, BOUNDS)
    assert oracle["I2"] is None
    assert oracle["I1"] is not None and len(oracle["I1"]) == 7
    assert min(oracle_all_violating_lengths(model, BOUNDS)["I1"]) == 7
