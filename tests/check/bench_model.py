"""A core-ref-shaped benchmark model for measuring checker throughput (not a test).

ASSUMED shape only: this is NOT core-ref (stream 02 owns that). It mimics its structure so the
checker's overhead can be measured before core-ref exists: a BMS that can fault, a bus of
in-flight messages the adversary can delay or drop, a hub that can restart (losing everything
but NVM), periodic heartbeats and commands, and an inverter that holds its last setpoint.

    .venv/bin/python -m tests.check.bench_model [max_depth] [max_injections] [horizon_ms]
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, replace

from fleetflight.core import TICK, TICK_MS, Bounds, Invariant, Move

from .toykit import ToyModel

LATENCY, BOOT, HOLD, HB_EVERY, BUDGET_MS = 50, 400, 1000, 500, 500


@dataclass(frozen=True, slots=True)
class BMsg:
    id: str
    kind: str        # FAULT | CMD | HB
    dst: str         # hub | inv
    due: int
    seq: int = 0
    delayed: bool = False


@dataclass(frozen=True, slots=True)
class BState:
    t_ms: int
    bms: str                     # HEALTHY | FAULTED
    bus: tuple[BMsg, ...]
    hub: str                     # ONLINE | BOOTING
    hub_boot_until: int | None
    hub_seq: int
    hub_knows_fault: bool
    nvm: tuple[str, int]         # last command (kind, seq)
    inv: str                     # DISCHARGING | IDLE | SHUTDOWN
    inv_last_cmd: int
    fault_n: int
    budget: int
    i1_since: int | None


def _i1_since(bms: str, inv: str, prev: int | None, t: int) -> int | None:
    if bms == "FAULTED" and inv == "DISCHARGING":
        return prev if prev is not None else t
    return None


class BenchModel(ToyModel):
    name = "bench-core-shape"
    invariants = [
        Invariant("I1", "FAULT_SHUTDOWN_BOUNDED", "Faulted BMS: inverter stops within 500 ms.",
                  "G(bms=FAULTED ∧ inv=DISCHARGING → (t − i1_since_ms) ≤ 500)",
                  lambda s: s.i1_since is None or s.t_ms - s.i1_since <= BUDGET_MS,
                  bound_ms=BUDGET_MS, timer_key="i1_since_ms"),
        Invariant("I2", "NO_DISCHARGE_WHILE_HUB_KNOWS_FAULT", "Never discharging once hub knows.",
                  "G(hub_knows_fault ∧ hub=ONLINE → inv≠DISCHARGING ∨ bus has STOP)",
                  lambda s: True),
    ]

    def init(self) -> BState:
        return BState(0, "HEALTHY", (), "ONLINE", None, 41, False, ("DISCHARGE", 41),
                      "DISCHARGING", 0, 0, self.bounds.max_injections, None)

    def moves(self, s: BState) -> list[Move]:
        out: list[Move] = []
        if s.budget > 0:
            if s.bms == "HEALTHY":
                out.append(Move("bms_fault"))
            if s.hub == "ONLINE":
                out.append(Move("hub_restart"))
            for m in s.bus:
                if not m.delayed:
                    for extra in (200, 400):
                        out.append(Move("bus_delay", (("msg", m.id), ("extra_ms", extra))))
                out.append(Move("bus_drop", (("msg", m.id),)))
        out.append(TICK)
        return out

    def apply(self, s: BState, mv: Move):
        if mv.name == "tick":
            return self._tick(s), []
        if s.budget <= 0:
            raise ValueError(mv.label)
        b = s.budget - 1
        if mv.name == "bms_fault":
            n = s.fault_n + 1
            msg = BMsg(f"fault#{n}", "FAULT", "hub", s.t_ms + LATENCY)
            return replace(s, bms="FAULTED", bus=s.bus + (msg,), fault_n=n, budget=b,
                           i1_since=_i1_since("FAULTED", s.inv, s.i1_since, s.t_ms)), []
        if mv.name == "hub_restart":
            bus = tuple(m for m in s.bus if m.dst != "hub")
            return replace(s, hub="BOOTING", hub_boot_until=s.t_ms + BOOT, hub_knows_fault=False,
                           bus=bus, budget=b), []
        mid = mv.arg("msg")
        if mv.name == "bus_delay":
            extra = int(mv.arg("extra_ms"))
            bus = tuple(replace(m, due=m.due + extra, delayed=True) if m.id == mid else m for m in s.bus)
        elif mv.name == "bus_drop":
            bus = tuple(m for m in s.bus if m.id != mid)
        else:
            raise ValueError(mv.label)
        return replace(s, bus=bus, budget=b), []

    def _tick(self, s: BState) -> BState:
        t = s.t_ms + TICK_MS
        hub, boot, seq, knows, nvm = s.hub, s.hub_boot_until, s.hub_seq, s.hub_knows_fault, s.nvm
        inv, last = s.inv, s.inv_last_cmd
        sends: list[BMsg] = []
        if hub == "BOOTING" and t >= boot:
            hub, boot = "ONLINE", None
            seq += 1
            sends.append(BMsg(f"cmd#{seq}", "CMD", "inv", t + LATENCY, seq))  # restore from NVM
        keep = []
        for m in s.bus:
            if m.due > t:
                keep.append(m)
                continue
            if m.dst == "hub" and hub == "ONLINE" and m.kind == "FAULT":
                knows = True
                seq += 1
                nvm = ("STOP", seq)
                sends.append(BMsg(f"cmd#{seq}", "CMD", "inv", t + LATENCY, seq))
            elif m.dst == "inv" and m.kind == "CMD":
                inv, last = ("SHUTDOWN" if knows and nvm[0] == "STOP" and m.seq == nvm[1] else "DISCHARGING"), t
            elif m.dst == "inv" and m.kind == "HB":
                last = t
        if hub == "ONLINE" and t % HB_EVERY == 0:
            seq += 1
            sends.append(BMsg(f"hb#{seq}", "HB", "inv", t + LATENCY, seq))
        if inv == "DISCHARGING" and t - last > HOLD:
            inv = "IDLE"
        bus = tuple(keep) + tuple(sends)
        return replace(s, t_ms=t, hub=hub, hub_boot_until=boot, hub_seq=seq, hub_knows_fault=knows,
                       nvm=nvm, inv=inv, inv_last_cmd=last, bus=bus,
                       i1_since=_i1_since(s.bms, inv, s.i1_since, t))

    def snapshot(self, s: BState):
        return {"t_ms": s.t_ms, "bms": s.bms,
                "bus": " ".join(f"{m.id}@{m.due}" for m in s.bus),
                "hub": s.hub if s.hub_boot_until is None else f"BOOTING until {s.hub_boot_until}",
                "inv": s.inv, "nvm": f"{s.nvm[0]} seq{s.nvm[1]}", "i1_since_ms": s.i1_since,
                "injections_left": s.budget}


def main(argv: list[str]) -> None:
    import cProfile
    import pstats

    from fleetflight.check import check

    d, k, h = (int(x) for x in (argv + ["120", "3", "3000"][len(argv):]))
    b = Bounds(d, k, h)
    model = BenchModel(b)
    if "--profile" in sys.argv:
        cProfile.runctx("check(model, b, stop_when_all_failed=False)", globals(), locals(), "/dev/null")
        prof = cProfile.Profile()
        prof.runctx("check(model, b, stop_when_all_failed=False)", globals(), locals())
        pstats.Stats(prof).sort_stats("tottime").print_stats(15)
        return
    r = check(model, b, stop_when_all_failed=False).to_json()
    st = r["stats"]
    print(b, {x["id"]: x["result"] for x in r["invariants"]},
          f"states={st['states']} transitions={st['transitions']} depth={st['max_depth_reached']} "
          f"wall={st['wall_s']}s states/s={st['states_per_s']}")


if __name__ == "__main__":
    main([a for a in sys.argv[1:] if not a.startswith("--")])
