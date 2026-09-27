"""THROWAWAY naive BFS (test-only). Stream 01 owns the real checker; this exists so stream 02 can
check the model's story and measure its state space before that checker lands."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fleetflight.core import Bounds, Move


@dataclass
class BfsResult:
    states: int = 0
    transitions: int = 0
    max_depth: int = 0
    complete: bool = True
    wall_s: float = 0.0
    first_violation: dict[str, tuple[int, list[Move]]] = field(default_factory=dict)  # id -> (t_ms, path)

    @property
    def failed(self) -> list[str]:
        return sorted(self.first_violation)


def bfs(model: Any, bounds: Bounds | None = None, *, stop_when_all_failed: bool = False,
        state_cap: int | None = None) -> BfsResult:
    b = bounds or model.bounds
    t0 = time.perf_counter()
    res = BfsResult()
    init = model.init()
    parent: dict[Any, tuple[Any, Move | None]] = {init: (None, None)}
    q: deque[tuple[Any, int]] = deque([(init, 0)])
    ids = [i.id for i in model.invariants]

    def path(s: Any) -> list[Move]:
        out: list[Move] = []
        while True:
            p, m = parent[s]
            if m is None:
                return out[::-1]
            out.append(m)
            s = p

    while q:
        s, d = q.popleft()
        res.states += 1
        res.max_depth = max(res.max_depth, d)
        for inv in model.invariants:
            if inv.id not in res.first_violation and not inv.check(s):
                res.first_violation[inv.id] = (s.t_ms, path(s))
        if stop_when_all_failed and len(res.first_violation) == len(ids):
            res.complete = False
            break
        if s.t_ms >= b.horizon_ms or d >= b.max_depth:
            continue
        if state_cap is not None and len(parent) > state_cap:
            res.complete = False
            continue
        for m in model.moves(s):
            ns, _ = model.apply(s, m)
            res.transitions += 1
            if ns not in parent:
                parent[ns] = (s, m)
                q.append((ns, d + 1))
    res.wall_s = time.perf_counter() - t0
    return res
