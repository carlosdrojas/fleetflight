from copy import deepcopy
from dataclasses import replace

import pytest

from fleetflight.core import Invariant, Move, TICK
from fleetflight.sim import ScriptedScheduler, SeededScheduler, replay, simulate
from tests.cli.toy_model import ToyModel, make_cex
from tests.test_contract import validator


def test_replay_identical_100_times_and_schema():
    cex = make_cex()
    validator("counterexample.schema.json").validate(cex)
    results = [replay(ToyModel("vbug"), cex) for repeat_index in range(100)]
    assert len({result["full_trace_hash"] for result in results}) == 1
    assert all(result["hash_match"] and result["matched_steps"] == len(cex["trace"]) for result in results)
    result = results[0]
    validator("replay-result.schema.json").validate(result)
    assert result["verdict"] == "FAIL"
    assert result["steps"][-1]["t_ms"] == 200
    assert result["trace_hash"] != result["full_trace_hash"]
    assert result["violation_window_ms"]["duration_ms"] == 150
    assert result["invariants"][0]["first_violation_ms"] == 100
    assert "_fixture" not in result


def test_fixed_toy_passes_and_records_divergence():
    result = replay(ToyModel("vfixed"), make_cex())
    validator("replay-result.schema.json").validate(result)
    assert result["verdict"] == "PASS"
    assert result["first_divergence"] == 2
    assert not result["hash_match"] and not result["same_sut"]
    assert result["violation_window_ms"] == {
        "invariant": "I1", "start_ms": 0, "end_ms": 50, "duration_ms": 50,
        "open": False, "bound_ms": 50, "over_budget_ms": 0,
    }


def test_script_order_final_tick_skips_and_json_arg_order():
    model = ToyModel("vbug")
    moves = make_cex()["moves"] + [{
        "tick_index": 0, "t_ms": 0,
        "move": Move("bus_delay", (("extra_ms", 50), ("msg", "fault#1"))).to_json(),
    }, {"tick_index": 2, "t_ms": 100, "move": Move("bms_fault").to_json()}]
    run = simulate(model, ScriptedScheduler(moves), 100)
    assert [step["move"]["name"] for step in run.steps[1:]] == ["bms_fault", "bus_delay", "tick", "tick"]
    assert run.steps[2]["move"]["label"] == "bus_delay(msg=fault#1, extra_ms=50)"
    assert len(run.skipped_moves) == 1
    assert run.skipped_moves[0]["tick_index"] == 2
    fixed = simulate(ToyModel("vfixed"), ScriptedScheduler(moves), 100)
    assert len(fixed.skipped_moves) == 2
    assert fixed.verdict == "PASS"


def test_replay_disabled_move_is_reported_and_never_forced():
    cex = make_cex()
    cex["moves"].append({"tick_index": 0, "t_ms": 0,
                         "move": Move("bus_delay", (("msg", "fault#1"), ("extra_ms", 50))).to_json()})
    result = replay(ToyModel("vfixed"), cex)
    validator("replay-result.schema.json").validate(result)
    assert result["skipped_moves"][0]["move"]["name"] == "bus_delay"
    assert result["verdict"] == "PASS"


def test_open_window_and_terminal_injection():
    script = [{"tick_index": 2, "t_ms": 100, "move": Move("bms_fault").to_json()}]
    run = simulate(ToyModel("vbug"), ScriptedScheduler(script), 100)
    assert run.steps[-1]["move"]["name"] == "bms_fault"
    assert run.invariants[0]["max_window"] == {"start_ms": 100, "end_ms": None, "duration_ms": 0, "open": True}
    result = replay(ToyModel("vbug"), make_cex(), horizon_ms=100)
    assert result["violation_window_ms"]["open"]
    assert result["violation_window_ms"]["duration_ms"] == 100


def test_initial_and_injection_invariants_are_checked():
    model = ToyModel()
    model.invariants += [Invariant("I2", "INITIAL_FAILURE", "test", "false", lambda state: False),
                         Invariant("I3", "NO_INJECTION", "test", "injections=0", lambda state: state.injections == 0)]
    run = simulate(model, ScriptedScheduler(make_cex()["moves"]), 50)
    assert run.steps[0]["violations"] == ["I2"]
    assert run.steps[1]["violations"] == ["I2", "I3"]
    assert run.invariants[1]["first_violation_ms"] == 0
    assert run.invariants[1]["max_window"] is None


def test_seeded_scheduler_reusable_and_budgeted():
    scheduler = SeededScheduler(17, {"bms_fault": 0.5, "bus_delay": 0.5})
    first = simulate(ToyModel("vbug"), scheduler, 200)
    second = simulate(ToyModel("vbug"), scheduler, 200)
    assert first.to_json() == second.to_json()
    assert first.snapshots[-1]["injections"] <= 3
    assert simulate(ToyModel(), SeededScheduler(1, {}), 200).verdict == "PASS"


@pytest.mark.parametrize("horizon", [-50, 1, 25, 1.5, True])
def test_invalid_horizon(horizon):
    with pytest.raises(ValueError):
        simulate(ToyModel(), SeededScheduler(1), horizon)


@pytest.mark.parametrize("rates", [{"a": -1}, {"a": 0.6, "b": 0.6}, {"a": float("nan")}])
def test_invalid_rates(rates):
    with pytest.raises(ValueError):
        SeededScheduler(1, rates)


def test_invalid_script_and_short_replay():
    with pytest.raises(ValueError):
        ScriptedScheduler([{"tick_index": 0, "move": TICK.to_json()}])
    with pytest.raises(ValueError):
        replay(ToyModel(), make_cex(), horizon_ms=50)


def test_timer_value_change_does_not_split_non_null_stretch():
    class CyclingToy(ToyModel):
        def apply(self, state, move):
            state, events = super().apply(state, move)
            if state.t_ms == 100:
                state = replace(state, fault_since_ms=100)
            return state, events

    run = simulate(CyclingToy("vbug"), ScriptedScheduler(make_cex()["moves"]), 300)
    assert run.invariants[0]["max_window"]["duration_ms"] == 250


def test_multiple_windows_choose_longest():
    class CyclingToy(ToyModel):
        def apply(self, state, move):
            state, events = super().apply(state, move)
            if state.t_ms == 200:
                state = replace(state, fault_since_ms=200)
            return state, events

    run = simulate(CyclingToy("vbug"), ScriptedScheduler(make_cex()["moves"]), 300)
    assert run.invariants[0]["max_window"] == {
        "start_ms": 0, "end_ms": 150, "duration_ms": 150, "open": False,
    }


def test_snapshot_diff_distinguishes_missing_from_null():
    cex = deepcopy(make_cex())
    cex["trace"][0]["snapshot"]["extra"] = None
    result = replay(ToyModel("vbug"), cex)
    assert result["steps"][0]["diff"] == ["extra"]
    assert result["first_divergence"] == 0


def test_horizon_extension_checks_late_violation():
    model = ToyModel("vfixed")
    model.invariants.append(Invariant("I2", "LATE", "test", "t<200", lambda state: state.t_ms < 200))
    result = replay(model, make_cex())
    assert result["invariants"][0]["result"] == "PASS"
    assert result["invariants"][1]["first_violation_ms"] == 200
    assert result["verdict"] == "FAIL"
