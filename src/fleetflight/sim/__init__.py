"""Deterministic simulation and replay through Model.apply."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from fleetflight.core import SCHEMA_REPLAY_RESULT, TICK, TICK_MS, Move, trace_hash


class ScriptedScheduler:
    """Apply injections in list order at their tick, recording disabled moves."""

    def __init__(self, moves):
        self.moves = list(moves)
        previous = -1
        for entry in self.moves:
            tick = entry["tick_index"]
            if type(tick) is not int or tick < 0 or tick < previous:
                raise ValueError("script tick_index must be non-negative and ordered")
            if entry.get("t_ms", tick * TICK_MS) != tick * TICK_MS:
                raise ValueError("script t_ms must equal tick_index * TICK_MS")
            move = Move.from_json(entry["move"])
            if not move.injected or move.name == TICK.name:
                raise ValueError("scripts must contain injections only")
            previous = tick
        self.reset()

    def reset(self):
        self.cursor = 0
        self.skipped_moves = []

    def choose(self, model, state, tick_index):
        while self.cursor < len(self.moves):
            entry = self.moves[self.cursor]
            if entry["tick_index"] != tick_index:
                break
            self.cursor += 1
            requested = Move.from_json(entry["move"])
            for enabled in model.moves(state):
                if (enabled.name == requested.name and enabled.injected == requested.injected
                        and dict(enabled.args) == dict(requested.args)):
                    return enabled
            self.skipped_moves.append({
                "tick_index": tick_index, "move": requested.to_json(),
                "reason": "move is not enabled by this model/SUT state",
            })
        return TICK


class SeededScheduler:
    """Per-decision probabilities by injection name; remaining probability ticks.

    Without explicit rates, enabled names share a total probability of 0.2.
    Argument variants of a chosen name are sampled uniformly.
    """

    def __init__(self, seed, rates=None):
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        self.seed = seed
        self.rates = None if rates is None else dict(rates)
        if self.rates is not None:
            if any(not math.isfinite(rate) or not 0 <= rate <= 1
                   for rate in self.rates.values()) or sum(self.rates.values()) > 1:
                raise ValueError("rates must be finite probabilities summing to at most one")
        self.reset()

    def reset(self):
        self.rng = random.Random(self.seed)
        self.skipped_moves = []

    def choose(self, model, state, tick_index):
        groups = {}
        for move in model.moves(state):
            if move.injected:
                groups.setdefault(move.name, []).append(move)
        draw = self.rng.random()
        cumulative = 0.0
        for name, choices in groups.items():
            cumulative += (0.2 / len(groups) if self.rates is None
                           else self.rates.get(name, 0))
            if draw < cumulative:
                return self.rng.choice(choices)
        return TICK


@dataclass
class Run:
    steps: list[dict[str, Any]]
    invariants: list[dict[str, Any]]
    skipped_moves: list[dict[str, Any]]

    @property
    def snapshots(self):
        return [step["snapshot"] for step in self.steps]

    @property
    def events(self):
        return [event for step in self.steps for event in step["events"]]

    @property
    def verdict(self):
        return "FAIL" if any(item["result"] == "FAIL" for item in self.invariants) else "PASS"

    @property
    def trace_hash(self):
        return hash_steps(self.steps)

    def to_json(self):
        return {"schema": "fleetflight/simulation@1", "steps": self.steps, "invariants": self.invariants,
                "skipped_moves": self.skipped_moves, "verdict": self.verdict,
                "trace_hash": self.trace_hash}


def hash_steps(steps):
    return trace_hash([(Move.from_json(step["move"]) if step["move"] else None,
                        step["snapshot"]) for step in steps])


def _max_window(steps, timer_key):
    if timer_key is None:
        return None
    windows = []
    start = None
    for step in steps:
        value = step["snapshot"][timer_key]
        if start is None and value is not None:
            start = value
        elif start is not None and value is None:
            windows.append({"start_ms": start, "end_ms": step["t_ms"],
                            "duration_ms": step["t_ms"] - start, "open": False})
            start = None
    if start is not None:
        windows.append({"start_ms": start, "end_ms": None,
                        "duration_ms": steps[-1]["t_ms"] - start, "open": True})
    return max(windows, key=lambda window: window["duration_ms"], default=None)


def _horizon(value):
    if type(value) is not int or value < 0 or value % TICK_MS:
        raise ValueError(f"horizon_ms must be a non-negative multiple of {TICK_MS}")
    return value


def simulate(model, scheduler, horizon_ms) -> Run:
    """Execute a fresh scheduler; check init, every injection, and every tick."""
    horizon_ms = _horizon(horizon_ms)
    scheduler.reset()
    state = model.init()
    steps = []

    def record(move, events):
        steps.append({
            "step": len(steps), "t_ms": state.t_ms,
            "move": move.to_json() if move is not None else None,
            "snapshot": model.snapshot(state),
            "events": [event.to_json() for event in events],
            "violations": [inv.id for inv in model.invariants if not inv.check(state)],
        })

    record(None, [])
    tick_index = 0
    while True:
        if state.t_ms >= horizon_ms and not isinstance(scheduler, ScriptedScheduler):
            break
        move = scheduler.choose(model, state, tick_index)
        if move == TICK and state.t_ms >= horizon_ms:
            break
        state, events = model.apply(state, move)
        record(move, events)
        if move == TICK:
            tick_index += 1
    invariants = []
    for inv in model.invariants:
        violations = [step["t_ms"] for step in steps if inv.id in step["violations"]]
        invariants.append({
            "id": inv.id, "name": inv.name, "result": "FAIL" if violations else "PASS",
            "first_violation_ms": violations[0] if violations else None,
            "max_window": _max_window(steps, inv.timer_key),
        })
    return Run(steps, invariants, list(scheduler.skipped_moves))


def replay(model, cex, horizon_ms=None) -> dict:
    """Replay the script, compare its prefix, then check through the horizon."""
    horizon = _horizon(cex["bounds"]["horizon_ms"] if horizon_ms is None else horizon_ms)
    ticks = cex["ticks"]
    if type(ticks) is not int or ticks < 0 or ticks * TICK_MS > horizon:
        raise ValueError("replay horizon must include all counterexample ticks")
    if not cex["trace"] or any(entry["tick_index"] > ticks for entry in cex["moves"]):
        raise ValueError("counterexample trace or injection tick is invalid")
    run = simulate(model, ScriptedScheduler(cex["moves"]), horizon)
    compared = min(len(run.steps), len(cex["trace"]))
    matched = 0
    first_divergence = None
    for index, step in enumerate(run.steps):
        step.update(match=None, diff=[])
        if index < compared:
            expected = cex["trace"][index]
            actual_snapshot, expected_snapshot = step["snapshot"], expected["snapshot"]
            step["diff"] = [key for key in sorted(actual_snapshot.keys() | expected_snapshot.keys())
                            if key not in actual_snapshot or key not in expected_snapshot
                            or actual_snapshot[key] != expected_snapshot[key]]
            expected_move = (Move.from_json(expected["move"]).to_json()
                             if expected["move"] else None)
            step["match"] = not step["diff"] and step["move"] == expected_move
            if step["match"]:
                matched += 1
            elif first_divergence is None:
                first_divergence = index
    prefix_hash = hash_steps(run.steps[:compared])
    description = model.describe()
    target = next((inv for inv in model.invariants if inv.id == cex["invariant"]["id"]), None)
    window = None
    if target is not None and target.bound_ms is not None:
        result = next(item for item in run.invariants if item["id"] == target.id)
        if result["max_window"] is not None:
            window = dict(result["max_window"], invariant=target.id, bound_ms=target.bound_ms,
                          over_budget_ms=result["max_window"]["duration_ms"] - target.bound_ms)
    return {
        "schema": SCHEMA_REPLAY_RESULT, "counterexample": cex["id"],
        "model": description["model"], "sut": description["sut"],
        "cex_sut": cex["sut"]["id"], "same_sut": description["sut"]["id"] == cex["sut"]["id"],
        "horizon_ms": horizon, "steps": run.steps, "compared_steps": compared,
        "matched_steps": matched, "first_divergence": first_divergence,
        "trace_hash": prefix_hash, "expected_trace_hash": cex["trace_hash"],
        "hash_match": prefix_hash == cex["trace_hash"], "full_trace_hash": run.trace_hash,
        "skipped_moves": run.skipped_moves, "invariants": run.invariants,
        "violation_window_ms": window, "verdict": run.verdict,
    }
