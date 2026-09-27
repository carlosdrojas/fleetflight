"""Test helper: run an explicit move script through a model (the contract's replay rule)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fleetflight.core import TICK, TICK_MS, Move


@dataclass
class Run:
    model: Any
    states: list = field(default_factory=list)
    moves: list = field(default_factory=list)       # moves[i] produced states[i+1]
    events: list = field(default_factory=list)
    skipped: list = field(default_factory=list)

    @property
    def snaps(self) -> list[dict]:
        return [self.model.snapshot(s) for s in self.states]

    def failures(self) -> dict[str, int]:
        """invariant id -> first t_ms where it does not hold."""
        out: dict[str, int] = {}
        for s in self.states:
            for inv in self.model.invariants:
                if inv.id not in out and not inv.check(s):
                    out[inv.id] = s.t_ms
        return out

    def windows(self, key: str) -> list[tuple[int, int | None]]:
        """Maximal stretches where snapshot[key] is non-null: (start_ms, end_ms or None if open)."""
        out: list[tuple[int, int | None]] = []
        cur = None
        for snap in self.snaps:
            v = snap[key]
            if v is not None and cur is None:
                cur = v
            elif v is None and cur is not None:
                out.append((cur, snap["t_ms"]))
                cur = None
        if cur is not None:
            out.append((cur, None))
        return out

    def max_window_ms(self, key: str) -> int:
        last = self.states[-1].t_ms
        return max(((e if e is not None else last) - s for s, e in self.windows(key)), default=0)


def run_script(model: Any, script: list[tuple[int, Move]], horizon_ms: int) -> Run:
    """``script`` is ``[(t_ms, move), ...]``; injections at t apply before the TICK leaving t.

    Moves that are not enabled are skipped and recorded, never forced (CONTRACT.md §4)."""
    r = Run(model)
    s = model.init()
    r.states.append(s)
    for k in range(horizon_ms // TICK_MS + 1):
        for t, m in script:
            if t == k * TICK_MS:
                if m in model.moves(s):
                    s, ev = model.apply(s, m)
                    r.states.append(s); r.moves.append(m); r.events.append(ev)
                else:
                    r.skipped.append((t, m))
        if k * TICK_MS < horizon_ms:
            s, ev = model.apply(s, TICK)
            r.states.append(s); r.moves.append(TICK); r.events.append(ev)
    return r
