"""Anti-vacuity: for every invariant, a deliberately broken firmware (a mutant of v0.3.3, which
passes everything) must make the exhaustive search FAIL that invariant. If a mutant survived, its
invariant would be trivially true and worth nothing.

The kill table printed by ``python -m tests.models.test_mutations`` goes in status/02-model.md.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from fleetflight.core import Bounds, HookResult
from fleetflight.models import load_model
from fleetflight.sut.firmware_ref import FirmwareRef, InvCtl

from ._mini_bfs import bfs


class _Mutant(FirmwareRef):
    what = ""

    def __init__(self) -> None:
        super().__init__("v0.3.3")
        self.version = f"v0.3.3-{type(self).__name__}"


class HubIgnoresFault(_Mutant):
    what = "hub never reacts to FAULT (still ACKs it)"

    def hub_on_msg(self, hub, msg, now_ms):
        if msg.kind == "FAULT":
            return HookResult(hub, tuple(m for m in super().hub_on_msg(hub, msg, now_ms).sends if m.kind == "ACK"))
        return super().hub_on_msg(hub, msg, now_ms)


class HubIgnoresUnknown(_Mutant):
    what = "DEGRADED hub resumes the 5 kW dispatch without waiting for a BMS report"

    def hub_on_tick(self, hub, now_ms):
        if hub.mode == "DEGRADED":
            hub, cmd = self._issue(replace(hub, mode="ONLINE"), "DISCHARGE", 5000, 3000)
            return HookResult(hub, (cmd.to_msg(),))
        return super().hub_on_tick(hub, now_ms)


class InvIgnoresExpiry(_Mutant):
    what = "inverter never checks expires_ms"

    def inv_on_tick(self, inv, now_ms):
        if inv.mode == "DISCHARGING" and inv.cmd is not None and inv.cmd.expires_ms <= now_ms:
            return HookResult(inv)
        return super().inv_on_tick(inv, now_ms)


class InvAppliesDuplicates(_Mutant):
    what = "inverter re-applies a command with the same (epoch, seq)"

    def inv_on_cmd(self, inv, msg, now_ms):
        res = super().inv_on_cmd(inv, msg, now_ms)
        c = res.ctl.cmd
        if res.ctl is not inv and inv.cmd is not None and c == inv.cmd and res.ctl.applies == inv.applies:
            mode = "DISCHARGING" if c.kind == "DISCHARGE" else "IDLE"
            return HookResult(InvCtl(mode, c, now_ms, inv.applies + 1))
        return res


class InvHoldsForever(_Mutant):
    what = "inverter has no hub-loss fallback at all"

    def inv_on_tick(self, inv, now_ms):
        if inv.mode == "DISCHARGING" and not (inv.cmd and inv.cmd.expires_ms <= now_ms):
            return HookResult(inv)
        return super().inv_on_tick(inv, now_ms)


class InvEpochOnlyOrdering(_Mutant):
    what = "inverter rejects older epochs only (the literal v0.3.3 brief), not older seqs"

    def inv_on_cmd(self, inv, msg, now_ms):
        cur = inv.cmd
        if msg.kind == "CMD" and cur is not None and int(msg.get("epoch")) == cur.epoch and int(msg.get("seq")) < cur.seq:
            from fleetflight.sut.firmware_ref import Cmd
            cmd = Cmd.from_msg(msg)
            if cmd.expires_ms > now_ms:
                mode = "DISCHARGING" if cmd.kind == "DISCHARGE" else "IDLE"
                return HookResult(InvCtl(mode, cmd, now_ms, inv.applies + 1))
        return super().inv_on_cmd(inv, msg, now_ms)


# mutant, invariant it must break, smallest bounds that give the search a chance to find it
MUTANTS = [
    (HubIgnoresFault, "I1", Bounds(max_depth=120, max_injections=1, horizon_ms=3500)),
    (HubIgnoresUnknown, "I2", Bounds(max_depth=120, max_injections=1, horizon_ms=3500)),
    (InvIgnoresExpiry, "I3", Bounds(max_depth=120, max_injections=0, horizon_ms=3500)),
    (InvAppliesDuplicates, "I4", Bounds(max_depth=120, max_injections=0, horizon_ms=3500)),
    (InvHoldsForever, "I5", Bounds(max_depth=120, max_injections=1, horizon_ms=3500)),
    (InvEpochOnlyOrdering, "I4", Bounds(max_depth=120, max_injections=2, horizon_ms=3500)),
]


def kill(mutant_cls, bounds: Bounds):
    m = load_model(sut=mutant_cls(), bounds=bounds)
    return bfs(m)


@pytest.mark.parametrize("mutant_cls,target,bounds", MUTANTS, ids=[m[0].__name__ for m in MUTANTS])
def test_mutant_is_killed(mutant_cls, target: str, bounds: Bounds) -> None:
    r = kill(mutant_cls, bounds)
    assert target in r.failed, f"{mutant_cls.__name__} survived: {target} still passes"


@pytest.mark.parametrize("bounds", [m[2] for m in MUTANTS[:5]])
def test_unmutated_v033_passes_the_same_bounds(bounds: Bounds) -> None:
    assert bfs(load_model(sut="v0.3.3", bounds=bounds)).failed == []


def test_every_invariant_has_a_mutant() -> None:
    ids = [i.id for i in load_model().invariants]
    assert sorted({t for _, t, _ in MUTANTS}) == ids


if __name__ == "__main__":
    print("| Mutant of v0.3.3 | What it breaks | Target | Killed | Failed invariants | Counterexample |")
    print("|---|---|---|---|---|---|")
    for cls, target, b in MUTANTS:
        r = kill(cls, b)
        t_ms, path = r.first_violation.get(target, (None, []))
        inj = ", ".join(x.label for x in path if x.injected) or "(no injection)"
        print(f"| {cls.__name__} | {cls.what} | {target} | {'yes' if target in r.failed else 'NO'} | "
              f"{' '.join(r.failed)} | {inj}; violated at {t_ms} ms, depth {len(path)} |")
