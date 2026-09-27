"""Independent test oracle for cross-checking the BFS checker (``fleetflight.check``).

A deliberately naive recursive DFS over paths of moves, written only against the public
``fleetflight.core`` contract (``Model.init/moves/apply``, ``Invariant.check``, ``Bounds``).
It shares no code with the checker implementation.

Bounds semantics (CONTRACT.md section 2):
* a path has at most ``bounds.max_depth`` moves;
* a state with ``t_ms >= bounds.horizon_ms`` is checked but not expanded;
* a state at depth ``== max_depth`` is checked but not expanded;
* the injection budget is enforced by the model itself and is ignored here.

Every invariant is checked on every visited state, including init.

Pruning is limited to memos that cannot hide a shorter (or, for the lengths oracle, any)
violation:
* :func:`oracle_check` revisits a state only if it is reached at a strictly smaller depth than
  any earlier visit (a shallower visit explores a superset of the deeper one's subtree, since
  horizon expansion depends only on the state and the remaining depth budget only grows).
* :func:`oracle_all_violating_lengths` memoizes exact ``(state, depth)`` pairs, whose subtrees
  are identical, so every reachable path length is still enumerated.
"""
from __future__ import annotations

import sys

from fleetflight.core import Bounds, Move

__all__ = ["oracle_check", "oracle_all_violating_lengths"]

_MIN_RECURSION_LIMIT = 10_000


def _ensure_recursion_limit(bounds: Bounds) -> None:
    needed = max(_MIN_RECURSION_LIMIT, 4 * bounds.max_depth + 200)
    if sys.getrecursionlimit() < needed:
        sys.setrecursionlimit(needed)


def _expandable(state, depth: int, bounds: Bounds) -> bool:
    return depth < bounds.max_depth and state.t_ms < bounds.horizon_ms


def oracle_check(model, bounds: Bounds | None = None) -> dict[str, list[Move] | None]:
    """For each invariant id: the SHORTEST violating path (list of moves from init) that the
    exhaustive DFS finds, or None if the invariant holds in every reachable state within bounds."""
    if bounds is None:
        bounds = model.bounds
    _ensure_recursion_limit(bounds)
    invariants = list(model.invariants)
    best: dict[str, list[Move] | None] = {inv.id: None for inv in invariants}
    min_depth_seen: dict[object, int] = {}
    path: list[Move] = []

    def visit(state) -> None:
        depth = len(path)
        prev = min_depth_seen.get(state)
        if prev is not None and prev <= depth:
            return
        min_depth_seen[state] = depth
        for inv in invariants:
            if not inv.check(state):
                cur = best[inv.id]
                if cur is None or depth < len(cur):
                    best[inv.id] = list(path)
        if not _expandable(state, depth, bounds):
            return
        for move in model.moves(state):
            nxt, _events = model.apply(state, move)
            path.append(move)
            visit(nxt)
            path.pop()

    visit(model.init())
    return best


def oracle_all_violating_lengths(model, bounds: Bounds | None = None) -> dict[str, set[int]]:
    """For each invariant id: every path length (number of moves from init) at which SOME path
    within bounds reaches a state violating that invariant. Empty set if it never fails."""
    if bounds is None:
        bounds = model.bounds
    _ensure_recursion_limit(bounds)
    invariants = list(model.invariants)
    lengths: dict[str, set[int]] = {inv.id: set() for inv in invariants}
    seen: set[tuple[object, int]] = set()

    def visit(state, depth: int) -> None:
        key = (state, depth)
        if key in seen:
            return
        seen.add(key)
        for inv in invariants:
            if not inv.check(state):
                lengths[inv.id].add(depth)
        if not _expandable(state, depth, bounds):
            return
        for move in model.moves(state):
            nxt, _events = model.apply(state, move)
            visit(nxt, depth + 1)

    visit(model.init(), 0)
    return lengths
