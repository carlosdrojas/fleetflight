"""Report documents: schema validity, determinism, ids, file writing, progress, early stop."""
from __future__ import annotations

import json
from dataclasses import dataclass, replace

import pytest

from fleetflight.check import check, write_report
from fleetflight.check.bfs import ModelNondeterminismError
from fleetflight.core import TICK, TICK_MS, Bounds, Invariant, counterexample_id

from .test_toy_counter import CounterModel
from .test_toy_race import RaceModel
from .test_toy_timer import TimerModel
from .toykit import ToyModel, assert_report_valid, cex_for, schema_errors

TIMER = Bounds(20, 3, 600)
WALL_FIELDS = ("wall_s", "states_per_s")


def _strip_wall(doc: dict) -> dict:
    doc = json.loads(json.dumps(doc))
    doc.pop("run_id", None)
    doc.pop("created_at", None)
    for k in WALL_FIELDS:
        doc.get("stats", {}).pop(k, None)
        doc.get("search", {}).pop(k, None)
    return doc


@pytest.mark.parametrize("make,bounds", [
    (CounterModel, Bounds(20, 2, 600)), (RaceModel, Bounds(10, 4, 200)), (TimerModel, TIMER)])
def test_two_runs_are_identical_except_wall_time(make, bounds) -> None:
    a, b = check(make(bounds), bounds), check(make(bounds), bounds)
    assert _strip_wall(a.to_json()) == _strip_wall(b.to_json())
    assert list(a.counterexamples) == list(b.counterexamples)
    for cid in a.counterexamples:
        assert _strip_wall(a.counterexamples[cid]) == _strip_wall(b.counterexamples[cid])


def test_counterexample_id_is_content_hash() -> None:
    report = check(TimerModel(TIMER), TIMER)
    cex = cex_for(report, "I1")
    assert cex["id"] == counterexample_id("toy-timer", "toy@v1", "I1", cex["moves"])
    # A different model name gives a different id for the same moves.
    assert cex["id"] != counterexample_id("other", "toy@v1", "I1", cex["moves"])


def test_report_fields_are_consistent() -> None:
    report = check(TimerModel(TIMER), TIMER, run_id="unit-1")
    assert_report_valid(report)
    doc = report.to_json()
    assert doc["run_id"] == "unit-1"
    assert doc["strategy"] == "bfs" and doc["bounds"] == TIMER.to_json()
    assert doc["sut"] == {"id": "toy@v1", "name": "toy", "version": "v1"}
    assert doc["model"]["hash"].startswith("sha256:")
    assert doc["counterexample_files"] == [f"{cid}.json" for cid in report.counterexamples]
    cex = cex_for(report, "I1")
    assert cex["search"]["states_explored"] <= doc["stats"]["states"]
    assert cex["search"]["transitions"] <= doc["stats"]["transitions"]
    assert cex["assumptions"] == doc["assumptions"]
    for i, step in enumerate(cex["trace"]):
        assert step["step"] == i and step["t_ms"] == step["snapshot"]["t_ms"]
        assert step["t_ms"] % TICK_MS == 0


def test_default_run_id_is_valid() -> None:
    report = check(RaceModel(Bounds(10, 4, 200)))
    assert not schema_errors(report.to_json(), "check-report.schema.json")
    assert "v1" in report.run_id


def test_write_report(tmp_path) -> None:
    report = check(TimerModel(TIMER), TIMER, run_id="w1")
    paths = write_report(report, tmp_path / "out")
    names = [p.name for p in paths]
    assert names[0] == "check-w1.json"
    assert names[1:] == [f"{cid}.json" for cid in report.counterexamples]
    doc = json.loads(paths[0].read_text())
    assert doc == report.to_json()
    assert not schema_errors(doc, "check-report.schema.json")
    for p in paths[1:]:
        assert not schema_errors(json.loads(p.read_text()), "counterexample.schema.json")


def test_early_stop_when_every_invariant_failed() -> None:
    class BothFail(RaceModel):
        invariants = [RaceModel.invariants[0],
                      Invariant("I2", "NEVER_READS", "Nobody reads.", "G(false)",
                                lambda s: s.pc == (0, 0))]

    b = Bounds(10, 4, 200)
    stopped = check(BothFail(b), b)
    full = check(BothFail(b), b, stop_when_all_failed=False)
    assert_report_valid(stopped)
    assert stopped.to_json()["stats"]["complete"] is False
    assert stopped.to_json()["notes"]
    assert full.to_json()["stats"]["complete"] is True
    assert stopped.to_json()["stats"]["states"] < full.to_json()["stats"]["states"]
    # Early stop never changes the counterexamples themselves.
    assert list(stopped.counterexamples) == list(full.counterexamples)


def test_on_progress_is_called() -> None:
    seen = []
    report = check(TimerModel(TIMER), TIMER, on_progress=seen.append, progress_every=50)
    assert len(seen) >= 2 and seen[-1]["done"] is True
    counts = [p["states"] for p in seen]
    assert counts == sorted(counts) and counts[-1] == report.to_json()["stats"]["states"]
    assert seen[-1]["failed"] == ["I1"]
    # Progress callbacks never change the result.
    assert _strip_wall(report.to_json()) == _strip_wall(check(TimerModel(TIMER), TIMER).to_json())


def test_violation_at_init() -> None:
    class BadInit(RaceModel):
        invariants = [Invariant("I1", "X_POSITIVE", "x > 0.", "G(x>0)", lambda s: s.x > 0)]

    report = check(BadInit(Bounds(5, 1, 100)))
    assert_report_valid(report)
    cex = next(iter(report.counterexamples.values()))
    assert cex["search"]["depth"] == 0 and cex["ticks"] == 0 and cex["moves"] == []
    assert len(cex["trace"]) == 1 and cex["trace"][0]["violations"] == ["I1"]


@dataclass(frozen=True, slots=True)
class NState:
    t_ms: int = 0
    bad: bool = False


class Flaky(ToyModel):
    """apply() secretly depends on a call counter: a nondeterministic model."""

    name = "toy-flaky"
    invariants = [Invariant("I1", "NOT_BAD", "never bad", "G(!bad)", lambda s: not s.bad)]
    calls = 0

    def init(self):
        return NState()

    def moves(self, s):
        return [TICK]

    def apply(self, s, m):
        Flaky.calls += 1
        return replace(s, t_ms=s.t_ms + TICK_MS, bad=s.t_ms >= 100 and Flaky.calls < 5), []

    def snapshot(self, s):
        return {"t_ms": s.t_ms, "bad": "yes" if s.bad else "no"}


def test_nondeterministic_model_is_rejected() -> None:
    Flaky.calls = 0
    with pytest.raises(ModelNondeterminismError):
        check(Flaky(Bounds(10, 0, 500)))
