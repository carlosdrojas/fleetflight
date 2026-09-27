"""Small deterministic test model, independent of the reference firmware."""
from dataclasses import dataclass, replace
from types import SimpleNamespace

from fleetflight.core import (
    Bounds, Invariant, Move, SCHEMA_COUNTEREXAMPLE, SCHEMA_DESCRIBE,
    TICK, TICK_MS, TraceEvent, counterexample_id, model_hash,
)
from fleetflight.sim import ScriptedScheduler, simulate


@dataclass(frozen=True)
class ToyState:
    t_ms: int = 0
    fault_since_ms: int | None = None
    faulted: bool = False
    injections: int = 0
    delayed: bool = False


class ToyModel:
    name = "toy"
    version = "1.0"
    assumptions = ["ASSUMED toy shutdown bound is 50 ms"]

    def __init__(self, sut=None, bounds=None):
        version = (sut or "vfixed").split("@")[-1]
        if version not in ("vbug", "vfixed"):
            raise ValueError(f"unknown toy SUT: {sut}")
        self.sut = SimpleNamespace(name="toy-firmware", version=version)
        self.bounds = bounds or Bounds(horizon_ms=200)
        self.invariants = [Invariant(
            "I1", "STOP_BOUNDED", "Stop after a fault", "fault -> stop within 50ms",
            lambda state: state.fault_since_ms is None or state.t_ms - state.fault_since_ms <= 50,
            bound_ms=50, timer_key="fault_since_ms",
        )]

    def init(self):
        return ToyState()

    def moves(self, state):
        moves = []
        if state.injections < self.bounds.max_injections:
            if not state.faulted:
                moves.append(Move("bms_fault"))
            elif not state.delayed and self.sut.version == "vbug":
                moves.append(Move("bus_delay", (("msg", "fault#1"), ("extra_ms", 50))))
        return moves + [TICK]

    def apply(self, state, move):
        if move not in self.moves(state):
            raise ValueError("disabled toy move")
        if move == TICK:
            state = replace(state, t_ms=state.t_ms + TICK_MS)
            timeout = 50 if self.sut.version == "vfixed" else 150 + 50 * state.delayed
            if state.fault_since_ms is not None and state.t_ms - state.fault_since_ms >= timeout:
                state = replace(state, fault_since_ms=None)
        elif move.name == "bms_fault":
            state = replace(state, faulted=True, fault_since_ms=state.t_ms,
                            injections=state.injections + 1)
        else:
            state = replace(state, delayed=True, injections=state.injections + 1)
        return state, [TraceEvent(state.t_ms, move.name, injected=move.injected)]

    def snapshot(self, state):
        return {"t_ms": state.t_ms, "inv": "RUN" if state.fault_since_ms is not None else "STOP",
                "fault_since_ms": state.fault_since_ms, "injections": state.injections}

    def describe(self):
        doc = {
            "schema": SCHEMA_DESCRIBE,
            "model": {"name": self.name, "version": self.version, "hash": "sha256:" + "0" * 12},
            "sut": {"id": f"toy-firmware@{self.sut.version}", "name": "toy-firmware", "version": self.sut.version},
            "sut_versions": ["toy-firmware@vbug", "toy-firmware@vfixed"], "tick_ms": TICK_MS,
            "components": [{"id": "inv", "name": "Toy inverter", "owner": "sut",
                            "states": ["RUN", "STOP"], "description": "Toy timeout controller"}],
            "injectables": [{"name": "bms_fault", "description": "Start fault timer", "params": []}],
            "invariants": [inv.to_json() for inv in self.invariants], "assumptions": self.assumptions,
            "bounds": self.bounds.to_json(), "constants": {},
            "snapshot_keys": [{"key": "inv", "label": "Inverter", "lane": True}],
        }
        doc["model"]["hash"] = model_hash(doc)
        return doc


def make_cex():
    """Construct a labeled toy fixture whose snapshots and hash are executed."""
    model = ToyModel("vbug")
    moves = [{"tick_index": 0, "t_ms": 0, "move": Move("bms_fault").to_json()}]
    run = simulate(model, ScriptedScheduler(moves), 100)
    doc = model.describe()
    return {
        "_fixture": True, "schema": SCHEMA_COUNTEREXAMPLE,
        "id": counterexample_id(model.name, doc["sut"]["id"], "I1", moves),
        "model": doc["model"], "sut": doc["sut"], "invariant": model.invariants[0].to_json(),
        "violated_at_ms": 100, "violation_duration_ms": 100,
        "bounds": model.bounds.to_json(),
        "search": {"strategy": "bfs", "minimal": False, "depth": len(run.steps) - 1,
                   "states_explored": 0, "transitions": 0, "wall_s": 0},
        "assumptions": model.assumptions, "trace": run.steps, "moves": moves,
        "ticks": 2, "trace_hash": run.trace_hash,
    }
