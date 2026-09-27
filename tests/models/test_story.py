"""The demo story, verified with explicit move scripts (no checker needed).

Every number asserted here is what the real model + SUT produce. They are recorded in
status/02-model.md. If you change a constant and a number moves, update both.

"Window" = fault→stop time: from the I1 timer start to the first state where the inverter is no
longer DISCHARGING (the replay-result definition). I1 PASS iff every window <= 500 ms.
"""
from __future__ import annotations

import pytest

from fleetflight.core import Move
from fleetflight.models import SCENARIOS, load_model

from ._script import run_script

HORIZON = 3500


def delay(mid: str, extra: int) -> Move:
    return Move("bus_delay", (("msg", mid), ("extra_ms", extra)))


# The README sequence: fault at 100, its message delayed 400 ms, hub restarts at 200 while the
# FAULT is still in flight (so it is lost with the RX buffer, and so are the retransmits that
# arrive while the hub boots).
README_RESTART = [(100, Move("bms_fault")), (100, delay("fault@100", 400)), (200, Move("hub_restart"))]
HAPPY = [(100, Move("bms_fault")), (100, delay("fault@100", 400))]
# The shortest I1 counterexample the mini BFS finds for v0.3.1 (depth 12): fault while the
# hub-inverter link is down. Same root cause (inverter waits for the hub), no restart needed.
FAULT_DURING_LINK_LOSS = [(0, Move("bms_fault")), (0, Move("network_loss"))]
# I4: a pre-fault refresh (seq41) delayed 100 ms arrives after STOP seq42.
STALE_REORDER = [(100, Move("bms_fault")), (100, delay("cmd@100", 100))]
# I2: hub restart alone, no fault.
RESTART_ONLY = [(0, Move("hub_restart"))]


def run(version: str, script: list, **kw):
    r = run_script(load_model(sut=version, **kw), script, HORIZON)
    assert not r.skipped, r.skipped
    return r


@pytest.mark.parametrize("v", ["v0.3.1", "v0.3.2", "v0.3.3"])
def test_happy_path_passes(v: str) -> None:
    r = run(v, HAPPY)
    assert r.failures() == {}
    # The delayed FAULT does not matter: the 100 ms retransmit reaches the hub at 250.
    assert r.windows("i1_since_ms") == [(100, 300)]


def test_v031_readme_restart_violates_i1() -> None:
    r = run("v0.3.1", README_RESTART)
    f = r.failures()
    assert f["I1"] == 600                     # still discharging at the 500 ms deadline
    assert r.windows("i1_since_ms") == [(100, 700)]   # fault→stop 600 ms: 100 ms over budget
    # The NVM restore also re-commands 5 kW while the rebooted hub knows nothing about the BMS.
    assert f["I2"] == 650
    assert set(f) == {"I1", "I2"}
    events = [e.detail for evs in r.events for e in evs]
    assert "fault@100 (hub RX buffer cleared)" in events
    assert "fault@300 (hub restarting)" in events


def test_v032_same_sequence_still_fails_by_smaller_margin() -> None:
    r = run("v0.3.2", README_RESTART)
    assert r.failures() == {"I1": 600}        # I2 fixed: no resurrected command
    assert r.windows("i1_since_ms") == [(100, 650)]   # 550 ms: 50 ms over; the 400 ms boot eats the budget


def test_v033_same_sequence_passes() -> None:
    r = run("v0.3.3", README_RESTART)
    assert r.failures() == {}
    assert r.windows("i1_since_ms") == [(100, 500)]   # 400 ms: inverter's own 200 ms hub-loss timeout


def test_margins_shrink_across_versions() -> None:
    w = {v: run(v, README_RESTART).max_window_ms("i1_since_ms") for v in ("v0.3.1", "v0.3.2", "v0.3.3")}
    assert w == {"v0.3.1": 600, "v0.3.2": 550, "v0.3.3": 400}


@pytest.mark.parametrize("v,window,fails", [("v0.3.1", 1050, True), ("v0.3.2", 1050, True), ("v0.3.3", 250, False)])
def test_fault_during_link_loss(v: str, window: int, fails: bool) -> None:
    r = run(v, FAULT_DURING_LINK_LOSS)
    assert r.max_window_ms("i1_since_ms") == window
    assert ("I1" in r.failures()) is fails
    assert "I5" not in r.failures()           # v0.3.1 hold (1 s) is inside the 1.5 s comms budget


@pytest.mark.parametrize("v,fails", [("v0.3.1", True), ("v0.3.2", True), ("v0.3.3", False)])
def test_stale_reordered_command_is_reapplied_before_v033(v: str, fails: bool) -> None:
    r = run(v, STALE_REORDER)
    assert ("I4" in r.failures()) is fails
    if fails:
        assert r.failures()["I4"] == 250
        assert r.states[-1].i4_repeat == "e1 seq41"


@pytest.mark.parametrize("v,fails", [("v0.3.1", True), ("v0.3.2", False), ("v0.3.3", False)])
def test_restart_alone_resumes_blind_only_in_v031(v: str, fails: bool) -> None:
    r = run(v, RESTART_ONLY)
    assert ("I2" in r.failures()) is fails
    if fails:
        assert r.failures() == {"I2": 450}    # boot at 400, resumed 5 kW delivered at 450


@pytest.mark.parametrize("v", ["v0.3.1", "v0.3.3"])
def test_finding_single_shot_fault_breaks_every_version(v: str) -> None:
    """FINDING: with the brief's literal BMS (FAULT sent once, no retransmit), one dropped FAULT
    leaves the hub unaware until the next 2 s STATUS. No firmware version meets I1 then. That is
    why core-ref assumes FAULT is retransmitted until ACKed (see the assumptions)."""
    r = run(v, [(100, Move("bms_fault")), (100, Move("bus_drop", (("msg", "fault@100"),)))], fault_retx_ms=None)
    assert r.failures() == {"I1": 600}
    assert r.windows("i1_since_ms") == [(100, 2100)]


def test_named_scenarios_match_this_file() -> None:
    assert SCENARIOS["bms-fault-basic"][1] == HAPPY
    assert SCENARIOS["restart-during-fault"][1] == README_RESTART
    assert SCENARIOS["fault-during-link-loss"][1] == FAULT_DURING_LINK_LOSS
    assert SCENARIOS["stale-reorder"][1] == STALE_REORDER
    assert SCENARIOS["restart-only"][1] == RESTART_ONLY
