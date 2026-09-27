"""Breadth-first explicit-state search over any contract ``Model``.

How it works
------------
* States are deduplicated in one ``dict`` keyed on the state itself (the model's frozen
  dataclass: ``hash`` + ``==``). The dict value is the state's integer id.
* Parent links live in two flat lists indexed by id: ``parent[id]`` and ``move_idx[id]``, the
  position of the producing move in ``model.moves(parent_state)``. We do not keep trace events
  or snapshots per state. A counterexample path is rebuilt by re-applying its moves from
  ``init()``, which regenerates the events and snapshots and doubles as a determinism check
  (every re-applied state must be the one the search stored).
* The search goes level by level, so the first state found that violates an invariant is at
  minimum depth: the counterexample is a shortest path in moves. Every invariant that has not
  failed yet is checked on every newly discovered state (init included).
* A state at depth ``max_depth`` or with ``t_ms >= horizon_ms`` is checked but not expanded.
* The search stops early once every invariant has a counterexample (``complete`` is then
  False). Otherwise it runs until the reachable space within bounds is exhausted, so PASS means
  "holds in every reachable state within bounds".

Only ``on_progress`` and the ``wall_s`` / ``states_per_s`` / ``created_at`` / ``run_id`` report
fields depend on wall-clock time. Nothing that decides what is explored does.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fleetflight.core import (
    SCHEMA_CHECK_REPORT,
    SCHEMA_COUNTEREXAMPLE,
    TICK_MS,
    Bounds,
    Invariant,
    Model,
    Move,
    counterexample_id,
    model_hash,
    sha256_hex,
    sut_id,
    trace_hash,
)

__all__ = ["CheckReport", "check", "write_report", "PROGRESS_EVERY"]

PROGRESS_EVERY = 5000
"""Default: call ``on_progress`` once per this many newly discovered states."""

ProgressFn = Callable[[dict[str, Any]], None]


class ModelNondeterminismError(RuntimeError):
    """Re-applying a stored path did not reproduce the state the search discovered."""


@dataclass
class CheckReport:
    """Result of one :func:`check` run.

    ``doc`` is the check-report document; ``counterexamples`` maps cex id to its document.
    """

    doc: dict[str, Any]
    counterexamples: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return self.doc

    @property
    def run_id(self) -> str:
        return self.doc["run_id"]

    @property
    def verdict(self) -> str:
        return self.doc["verdict"]

    @property
    def exit_code(self) -> int:
        """CLI exit code per CONTRACT.md §6: 0 all pass, 1 an invariant fails."""
        return 0 if self.verdict == "PASS" else 1


@dataclass
class _Found:
    """What the search records when it finds an invariant's first violating state."""

    state_id: int
    states: int
    transitions: int
    wall_s: float


def check(
    model: Model,
    bounds: Bounds | None = None,
    *,
    on_progress: ProgressFn | None = None,
    progress_every: int = PROGRESS_EVERY,
    stop_when_all_failed: bool = True,
    run_id: str | None = None,
) -> CheckReport:
    """Bounded BFS over ``model``. See the module docstring for the exact semantics.

    ``bounds`` defaults to ``model.bounds``. The injection budget is enforced by the model, so
    pass the same ``Bounds`` to ``load_model`` and here.
    """
    bounds = bounds or model.bounds
    invariants: list[Invariant] = list(model.invariants)
    started = time.perf_counter()

    init = model.init()
    moves_of = model.moves
    apply = model.apply
    snapshot = model.snapshot
    max_depth = bounds.max_depth
    horizon = bounds.horizon_ms

    # Flat per-state storage indexed by state id.
    index: dict[Any, int] = {init: 0}
    parent: list[int] = [-1]
    move_idx: list[int] = [-1]

    found: dict[int, _Found] = {}          # invariant position -> first violation
    # Bounded invariants that have not failed: track the longest open timer (worst_case_ms).
    worst: dict[int, int | None] = {k: None for k, inv in enumerate(invariants) if inv.timer_key}
    pending = [(k, inv.check) for k, inv in enumerate(invariants)]
    pending_bounded = [(k, invariants[k].timer_key) for k in worst]
    transitions = 0
    new_per_depth = [1]
    next_progress = progress_every

    def note_worst(state: Any) -> None:
        snap = snapshot(state)
        t = snap["t_ms"]
        for k, key in pending_bounded:
            since = snap.get(key)
            if since is not None:
                dur = t - since
                if worst[k] is None or dur > worst[k]:
                    worst[k] = dur

    def examine(state: Any, sid: int) -> bool:
        """Check pending invariants on a new state. Returns True if something failed."""
        nonlocal pending, pending_bounded
        failed = False
        for k, chk in pending:
            if not chk(state):
                found[k] = _Found(sid, len(parent), transitions, time.perf_counter() - started)
                failed = True
        if failed:
            pending = [(k, c) for k, c in pending if k not in found]
            pending_bounded = [(k, key) for k, key in pending_bounded if k not in found]
        return failed

    if pending_bounded:
        note_worst(init)
    examine(init, 0)
    had_invariants = bool(invariants)
    stopped_early = had_invariants and not pending and stop_when_all_failed

    frontier_states: list[Any] = [init]
    frontier_ids: list[int] = [0]
    depth = 0
    while frontier_states and depth < max_depth and not stopped_early:
        next_states: list[Any] = []
        next_ids: list[int] = []
        for sid, state in zip(frontier_ids, frontier_states):
            if state.t_ms >= horizon:
                continue
            for i, m in enumerate(moves_of(state)):
                s2, _events = apply(state, m)
                transitions += 1
                n = len(parent)
                nid = index.setdefault(s2, n)
                if nid != n:
                    continue
                parent.append(sid)
                move_idx.append(i)
                next_states.append(s2)
                next_ids.append(n)
                if pending_bounded:
                    note_worst(s2)
                if pending and examine(s2, n) and not pending and stop_when_all_failed:
                    stopped_early = True
                    break
                if on_progress is not None and n + 1 >= next_progress:
                    next_progress += progress_every
                    on_progress(_progress(n + 1, transitions, depth + 1, len(next_states),
                                          started, invariants, found))
            if stopped_early:
                break
        depth += 1
        if next_states:
            new_per_depth.append(len(next_states))
        frontier_states, frontier_ids = next_states, next_ids

    wall_s = time.perf_counter() - started
    stats = {
        "states": len(parent),
        "transitions": transitions,
        "max_depth_reached": len(new_per_depth) - 1,
        "wall_s": round(wall_s, 4),
        "states_per_s": round(len(parent) / wall_s, 1) if wall_s > 0 else 0.0,
        "new_states_per_depth": new_per_depth,
        "complete": not stopped_early,
    }
    if on_progress is not None:
        on_progress(_progress(len(parent), transitions, stats["max_depth_reached"], 0,
                              started, invariants, found, done=True))

    return _build_report(model, bounds, invariants, index, parent, move_idx, found, worst, stats,
                         run_id=run_id)


def _progress(states: int, transitions: int, depth: int, frontier: int, started: float,
              invariants: list[Invariant], found: dict[int, _Found], done: bool = False) -> dict[str, Any]:
    wall = time.perf_counter() - started
    return {
        "states": states,
        "transitions": transitions,
        "depth": depth,
        "frontier": frontier,
        "wall_s": round(wall, 3),
        "states_per_s": round(states / wall, 1) if wall > 0 else 0.0,
        "failed": [invariants[k].id for k in sorted(found)],
        "done": done,
    }


# --------------------------------------------------------------------------------------------
# Path reconstruction and documents
# --------------------------------------------------------------------------------------------


def _path_ids(parent: list[int], sid: int) -> list[int]:
    ids = []
    while sid != -1:
        ids.append(sid)
        sid = parent[sid]
    ids.reverse()
    return ids


def _replay_path(model: Model, index: dict[Any, int], parent: list[int], move_idx: list[int],
                 sid: int) -> list[tuple[Move | None, Any, list]]:
    """Rebuild ``[(move, state, events)]`` from init to state ``sid`` by re-applying moves.

    Every re-applied state must be the one the search stored under that id; otherwise the
    model is not deterministic and no counterexample from it could be trusted.
    """
    ids = _path_ids(parent, sid)
    state = model.init()
    steps: list[tuple[Move | None, Any, list]] = [(None, state, [])]
    for step_id in ids[1:]:
        m = model.moves(state)[move_idx[step_id]]
        state, events = model.apply(state, m)
        if index.get(state) != step_id:
            raise ModelNondeterminismError(
                f"re-applying {m.label} at step {len(steps)} did not reproduce the state the "
                "search discovered; model.moves/apply are not deterministic")
        steps.append((m, state, list(events)))
    return steps


def _model_ref(model: Model) -> dict[str, str]:
    return {"name": model.name, "version": model.version, "hash": model_hash(model.describe())}


def _sut_ref(model: Model) -> dict[str, str]:
    return {"id": sut_id(model.sut), "name": model.sut.name, "version": model.sut.version}


def _counterexample(model: Model, bounds: Bounds, inv: Invariant, invariants: list[Invariant],
                    steps: list[tuple[Move | None, Any, list]], f: _Found,
                    model_ref: dict[str, str], sut_ref: dict[str, str]) -> dict[str, Any]:
    trace = []
    hash_steps = []
    moves_json = []
    ticks = 0
    for i, (m, state, events) in enumerate(steps):
        snap = dict(model.snapshot(state))
        hash_steps.append((m, snap))
        step: dict[str, Any] = {
            "step": i,
            "t_ms": snap["t_ms"],
            "move": m.to_json() if m is not None else None,
            "snapshot": snap,
            "events": [e.to_json() for e in events],
        }
        violations = [x.id for x in invariants if not x.check(state)]
        if violations:
            step["violations"] = violations
        trace.append(step)
        if m is None:
            continue
        if m.injected:
            moves_json.append({"tick_index": ticks, "t_ms": ticks * TICK_MS, "move": m.to_json()})
        else:
            ticks += 1

    last = trace[-1]["snapshot"]
    duration = None
    if inv.timer_key is not None and last.get(inv.timer_key) is not None:
        duration = last["t_ms"] - last[inv.timer_key]
    cid = counterexample_id(model.name, sut_ref["id"], inv.id, moves_json)
    return {
        "schema": SCHEMA_COUNTEREXAMPLE,
        "id": cid,
        "model": model_ref,
        "sut": sut_ref,
        "invariant": inv.to_json(),
        "violated_at_ms": last["t_ms"],
        "violation_duration_ms": duration,
        "bounds": bounds.to_json(),
        "search": {
            "strategy": "bfs",
            "minimal": True,
            "depth": len(steps) - 1,
            "states_explored": f.states,
            "transitions": f.transitions,
            "wall_s": round(f.wall_s, 4),
        },
        "assumptions": list(model.assumptions),
        "trace": trace,
        "moves": moves_json,
        "ticks": ticks,
        "trace_hash": trace_hash(hash_steps),
        "replay": {"command": f"fleetflight replay --counterexample {cid}"},
    }


def _build_report(model: Model, bounds: Bounds, invariants: list[Invariant], index: dict[Any, int],
                  parent: list[int],
                  move_idx: list[int], found: dict[int, _Found], worst: dict[int, int | None],
                  stats: dict[str, Any], *, run_id: str | None) -> CheckReport:
    model_ref = _model_ref(model)
    sut_ref = _sut_ref(model)
    cexes: dict[str, dict[str, Any]] = {}
    inv_rows = []
    for k, inv in enumerate(invariants):
        row: dict[str, Any] = inv.to_json()
        f = found.get(k)
        if f is None:
            row.update(result="PASS", counterexample=None, violated_at_ms=None,
                       violation_duration_ms=None, depth=None, worst_case_ms=worst.get(k))
        else:
            steps = _replay_path(model, index, parent, move_idx, f.state_id)
            if inv.check(steps[-1][1]):
                raise ModelNondeterminismError(
                    f"{inv.id}: re-applied counterexample path does not violate the invariant")
            cex = _counterexample(model, bounds, inv, invariants, steps, f, model_ref, sut_ref)
            cexes[cex["id"]] = cex
            row.update(result="FAIL", counterexample=cex["id"], violated_at_ms=cex["violated_at_ms"],
                       violation_duration_ms=cex["violation_duration_ms"], depth=cex["search"]["depth"],
                       worst_case_ms=None)
        inv_rows.append(row)

    verdict = "PASS" if all(r["result"] == "PASS" for r in inv_rows) else "FAIL"
    notes = []
    if not stats["complete"]:
        notes.append("Search stopped early: every invariant already has a counterexample, "
                     "so not every reachable state was explored.")
    now = datetime.now(timezone.utc)
    if run_id is None:
        # Wall-clock prefix for sorting + a content hash of what was checked.
        ident = sha256_hex([model_ref, sut_ref, bounds.to_json()])[:6]
        run_id = f"{now:%Y%m%dT%H%M%S}-{sut_ref['version']}-{ident}"
    doc: dict[str, Any] = {
        "schema": SCHEMA_CHECK_REPORT,
        "run_id": run_id,
        "created_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model": model_ref,
        "sut": sut_ref,
        "bounds": bounds.to_json(),
        "strategy": "bfs",
        "assumptions": list(model.assumptions),
        "stats": stats,
        "invariants": inv_rows,
        "counterexample_files": [f"{cid}.json" for cid in cexes],
        "verdict": verdict,
    }
    if notes:
        doc["notes"] = notes
    return CheckReport(doc, cexes)


def write_report(report: CheckReport, out_dir: str | Path) -> list[Path]:
    """Write ``check-<run_id>.json`` and one ``<cex-id>.json`` per counterexample."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    p = out / f"check-{report.run_id}.json"
    p.write_text(json.dumps(report.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths.append(p)
    for cid, cex in report.counterexamples.items():
        p = out / f"{cid}.json"
        p.write_text(json.dumps(cex, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths.append(p)
    return paths
