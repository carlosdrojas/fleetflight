"""core-ref: a behavioral model of the environment around a BMS ↔ Hub ↔ Inverter system.

This is a reference model WE wrote. It is not Base's Gen 3 architecture.

The model owns the environment: the BMS, the bus (in-flight messages and their delivery times),
the hub's power lifecycle (ONLINE → RESTARTING → booted) and the hub↔inverter link. Every
controller decision is delegated to the SUT through the pure hooks of ``core.SUT``. The model
reads a controller's ``mode`` and ``view()`` and nothing else, and it keeps the hub's NVM only
while the hub is down (that is the one thing a restart preserves).

Moves (CONTRACT.md §1): injections first, in a fixed order, then TICK.

* ``bms_fault``: BMS goes FAULTED and sends FAULT to the hub (retransmitted every
  ``FAULT_RETX_MS`` until the hub ACKs it).
* ``hub_restart``: hub loses power; messages queued for it are lost; it boots after
  ``HUB_BOOT_MS`` via ``hub_on_boot(nvm)``.
* ``network_loss``: the hub↔inverter link goes down for the rest of the run.
* ``bus_delay(msg, extra_ms)``, ``bus_drop(msg)``, ``bus_dup(msg)``: for each in-flight message.

A TICK advances 50 ms and runs, in order: hub boot completion, due deliveries (by delivery
time, then send time, then id), BMS status/retransmits, ``hub_on_tick``, ``inv_on_tick``, then the timers the
invariants read.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from fleetflight.core import (
    SCHEMA_DESCRIBE,
    TICK,
    TICK_MS,
    Bounds,
    Invariant,
    Move,
    Msg,
    Snapshot,
    TraceEvent,
    model_hash,
    sut_id,
)

MODEL_NAME = "core-ref"
MODEL_VERSION = "1.0"

# ---- constants (all shown on the Spec screen) --------------------------------------------------
LATENCY_BASE_MS = 50          # every message takes one tick unless the adversary delays it
LATENCY_MAX_MS = 800          # total latency of any message never exceeds this
DELAY_STEPS_MS = (100, 200, 400, 700)   # 1- and 2-tick reorders + near-max latency; see status for the 100-ms-step run
HUB_BOOT_MS = 400
BMS_STATUS_MS = 2000          # BMS STATUS heartbeat period (sent at t = 2000, 4000, ...; one was seen before t=0)
FAULT_RETX_MS = 100           # FAULT retransmit period until ACKed (None = single-shot)
SHUTDOWN_BUDGET_MS = 500      # I1
COMMS_LOSS_BUDGET_MS = 1500   # I5
HIGH_POWER_W = 1000           # I2
DISPATCH_WATTS = 5000
DISPATCH_EXPIRES_MS = 3000
HUB_REFRESH_MS = 100          # the hub re-sends its command this often (the SUT's choice; shown)

DEFAULT_BOUNDS = Bounds(max_depth=120, max_injections=3, horizon_ms=3500)

INJECTIONS = ("bms_fault", "hub_restart", "network_loss", "bus_delay", "bus_drop", "bus_dup")


@dataclass(frozen=True, slots=True)
class BusMsg:
    id: str
    msg: Msg
    sent_ms: int
    due_ms: int
    basis: str = ""      # for hub→inv CMDs: what the hub knew about the BMS when it sent it
    dup: bool = False

    def label(self) -> str:
        return f"{self.id} {self.msg.src}→{self.msg.dst} due {self.due_ms}"


@dataclass(frozen=True, slots=True)
class State:
    t_ms: int
    inj_left: int
    # environment
    bms: str                         # HEALTHY | FAULTED
    fault_acked: bool
    next_retx_ms: int | None
    link_up: bool
    bus: tuple[BusMsg, ...]          # sorted by (due_ms, sent_ms, id)
    # controllers (SUT-owned values; the model only calls hooks and reads mode/view)
    hub: Any                         # hub ControllerState, or None while RESTARTING
    boot_at_ms: int | None
    nvm_down: Any                    # the hub's NVM while it is down (opaque to the model), else None
    nvm_label: str                   # the hub's last view()["nvm"], shown while it is down
    inv: Any
    # observations the model keeps for the invariants
    hub_bms_seen: str                # BMS state last delivered to the hub since its boot, or UNKNOWN
    inv_last_rx_ms: int              # last hub message delivered to the inverter
    inv_basis: str                   # hub's BMS knowledge when it sent the command the inverter runs
    inv_expires_ms: int | None       # expiry of the command the inverter runs
    applied: tuple[tuple[int, int], ...]   # (epoch, seq) the inverter has applied, sorted
    i4_repeat: str | None            # first (epoch, seq) applied twice
    i1_since_ms: int | None
    i5_since_ms: int | None


def _inv_running(s: State) -> bool:
    return s.inv.mode == "DISCHARGING"


def _inv_watts(s: State) -> int:
    return int(s.inv.view().get("watts") or 0)


# ---- invariants ---------------------------------------------------------------------------------

# Bounded invariants use deadline semantics: at t = since + budget the inverter must already have
# left DISCHARGING. With 50 ms sampling this makes PASS exactly "every window <= budget", where a
# window runs from timer start to the first state in which the condition no longer holds (the
# replay-result definition), so the checker and the replay bars always agree.


def _i1(s: State) -> bool:
    return s.i1_since_ms is None or s.t_ms - s.i1_since_ms < SHUTDOWN_BUDGET_MS


def _i2(s: State) -> bool:
    return not (s.inv_basis == "UNKNOWN" and _inv_watts(s) > HIGH_POWER_W)


def _i3(s: State) -> bool:
    return not (_inv_running(s) and s.inv_expires_ms is not None and s.inv_expires_ms <= s.t_ms)


def _i4(s: State) -> bool:
    return s.i4_repeat is None


def _i5(s: State) -> bool:
    return s.i5_since_ms is None or s.t_ms - s.i5_since_ms < COMMS_LOSS_BUDGET_MS


INVARIANTS = [
    Invariant(
        "I1", "FAULT_SHUTDOWN_BOUNDED",
        f"If the BMS is FAULTED, the inverter stops discharging within {SHUTDOWN_BUDGET_MS} ms.",
        f"G( bms=FAULTED ∧ inv=DISCHARGING → (t − i1_since_ms) < {SHUTDOWN_BUDGET_MS} )",
        _i1, bound_ms=SHUTDOWN_BUDGET_MS, timer_key="i1_since_ms"),
    Invariant(
        "I2", "NO_HIGH_POWER_WHEN_UNKNOWN",
        f"The inverter never runs above {HIGH_POWER_W} W on a command the hub sent while it had "
        "no BMS report since its last boot (BMS state UNKNOWN to the hub).",
        f"G( inv_watts > {HIGH_POWER_W} → inv_basis ≠ UNKNOWN )",
        _i2),
    Invariant(
        "I3", "NO_RESURRECTED_COMMANDS",
        "The inverter never executes a command after its expiry.",
        "G( inv=DISCHARGING → inv_cmd.expires_ms > t )",
        _i3),
    Invariant(
        "I4", "IDEMPOTENT_COMMANDS",
        "A command (epoch, seq) is applied by the inverter at most once: duplicated or reordered "
        "copies never cause a second physical action.",
        "G( ∀(epoch,seq): applied_count(epoch,seq) ≤ 1 )",
        _i4),
    Invariant(
        "I5", "COMMS_LOSS_SAFE_FALLBACK",
        f"If hub messages stop reaching the inverter, it leaves DISCHARGING within "
        f"{COMMS_LOSS_BUDGET_MS} ms of the last one.",
        f"G( inv=DISCHARGING ∧ silent(hub→inv) → (t − i5_since_ms) < {COMMS_LOSS_BUDGET_MS} )",
        _i5, bound_ms=COMMS_LOSS_BUDGET_MS, timer_key="i5_since_ms"),
]

ASSUMPTIONS = [
    f"ASSUMED bus latency <= {LATENCY_MAX_MS} ms; messages may be delayed, dropped, duplicated or reordered",
    f"ASSUMED BMS FAULT message is edge-triggered and retransmitted every {FAULT_RETX_MS} ms until the hub ACKs it; status heartbeat every {BMS_STATUS_MS} ms",
    f"ASSUMED hub boot takes {HUB_BOOT_MS} ms and clears its RX buffer; only NVM survives a restart",
    f"ASSUMED shutdown budget {SHUTDOWN_BUDGET_MS} ms (a real number would come from Base's safety requirements)",
    f"ASSUMED one dispatch at t=0: DISCHARGE {DISPATCH_WATTS} W, expires at {DISPATCH_EXPIRES_MS} ms; cloud re-dispatch after a hub restart is not modeled",
    "ASSUMED network_loss means the hub-inverter link is down for the rest of the run",
    "OUT OF SCOPE hardware interlocks (contactors, hardwired BMS trip)",
    "OUT OF SCOPE core-ref is a reference model we wrote, not Base Gen 3 firmware",
]

SNAPSHOT_KEYS = [
    ("bms", "BMS", True),
    ("bus", "Bus", True),
    ("hub", "Hub", True),
    ("inv", "Inverter", True),
    ("nvm", "Hub NVM", False),
    ("hub_bms", "BMS as seen by hub", False),
    ("link", "Hub-inverter link", False),
    ("inv_basis", "Inverter command basis", False),
    ("i1_since_ms", "I1 timer", False),
    ("i5_since_ms", "I5 timer", False),
    ("i4_repeat", "I4 repeated command", False),
    ("injections_left", "Injections left", False),
]


class CoreRef:
    """The core-ref model bound to one SUT and one set of bounds."""

    name = MODEL_NAME
    version = MODEL_VERSION

    def __init__(self, sut: Any, bounds: Bounds | None = None, *,
                 fault_retx_ms: int | None = FAULT_RETX_MS,
                 injections: tuple[str, ...] = INJECTIONS,
                 delay_steps_ms: tuple[int, ...] = DELAY_STEPS_MS) -> None:
        self.sut = sut
        self.bounds = bounds or DEFAULT_BOUNDS
        self.fault_retx_ms = fault_retx_ms
        self.injections = tuple(i for i in INJECTIONS if i in injections)
        self.delay_steps_ms = tuple(sorted(delay_steps_ms))
        self.invariants = list(INVARIANTS)
        self.assumptions = list(ASSUMPTIONS)
        if fault_retx_ms is None:
            self.assumptions[1] = (f"ASSUMED BMS FAULT message is edge-triggered and sent once (no "
                                   f"retransmit); status heartbeat every {BMS_STATUS_MS} ms")
        elif fault_retx_ms != FAULT_RETX_MS:
            self.assumptions[1] = self.assumptions[1].replace(f"every {FAULT_RETX_MS} ms", f"every {fault_retx_ms} ms")

    # ---- init ---------------------------------------------------------------------------------
    def init(self) -> State:
        sut = self.sut
        hub = sut.hub_init(None)
        inv = sut.inv_init()
        # Scenario setup at t=0: the cloud dispatches DISCHARGE; the hub commands the inverter.
        dispatch = Msg("DISPATCH", "cloud", "hub", (
            ("kind", "DISCHARGE"), ("watts", DISPATCH_WATTS), ("expires_ms", DISPATCH_EXPIRES_MS)))
        r = sut.hub_on_msg(hub, dispatch, 0)
        hub = r.ctl
        expires = None
        for m in r.sends:
            if m.dst == "inv":
                inv = sut.inv_on_cmd(inv, m, 0).ctl
                expires = int(m.get("expires_ms", 0))
        v = inv.view()
        s = State(
            t_ms=0, inj_left=self.bounds.max_injections,
            bms="HEALTHY", fault_acked=True, next_retx_ms=None, link_up=True, bus=(),
            hub=hub, boot_at_ms=None, nvm_down=None, nvm_label="", inv=inv,
            hub_bms_seen="HEALTHY", inv_last_rx_ms=0, inv_basis="HEALTHY", inv_expires_ms=expires,
            applied=((int(v["epoch"]), int(v["seq"])),) if v.get("seq") is not None else (),
            i4_repeat=None, i1_since_ms=None, i5_since_ms=None)
        return s

    # ---- moves --------------------------------------------------------------------------------
    def moves(self, s: State) -> list[Move]:
        out: list[Move] = []
        if s.inj_left > 0 and s.t_ms < self.bounds.horizon_ms:
            inj = self.injections
            if "bms_fault" in inj and s.bms == "HEALTHY":
                out.append(Move("bms_fault"))
            if "hub_restart" in inj and s.hub is not None:
                out.append(Move("hub_restart"))
            if "network_loss" in inj and s.link_up:
                out.append(Move("network_loss"))
            for b in s.bus:
                if "bus_delay" in inj:
                    for extra in self.delay_steps_ms:
                        if b.due_ms + extra - b.sent_ms <= LATENCY_MAX_MS:
                            out.append(Move("bus_delay", (("msg", b.id), ("extra_ms", extra))))
                if "bus_drop" in inj:
                    out.append(Move("bus_drop", (("msg", b.id),)))
                if "bus_dup" in inj and not b.dup:
                    out.append(Move("bus_dup", (("msg", b.id),)))
        out.append(TICK)
        return out

    def _enabled(self, s: State, m: Move) -> bool:
        if m == TICK:
            return True
        if not m.injected or s.inj_left <= 0 or s.t_ms >= self.bounds.horizon_ms or m.name not in self.injections:
            return False
        if m.name == "bms_fault":
            return s.bms == "HEALTHY" and not m.args
        if m.name == "hub_restart":
            return s.hub is not None and not m.args
        if m.name == "network_loss":
            return s.link_up and not m.args
        try:
            b = self._find(s, str(m.arg("msg")))
        except KeyError:
            return False
        if b is None:
            return False
        if m.name == "bus_delay":
            if len(m.args) != 2:
                return False
            extra = m.arg("extra_ms")
            return extra in self.delay_steps_ms and b.due_ms + int(extra) - b.sent_ms <= LATENCY_MAX_MS
        if m.name == "bus_drop":
            return len(m.args) == 1
        if m.name == "bus_dup":
            return len(m.args) == 1 and not b.dup
        return False

    @staticmethod
    def _find(s: State, mid: str) -> BusMsg | None:
        for b in s.bus:
            if b.id == mid:
                return b
        return None

    # ---- apply --------------------------------------------------------------------------------
    def apply(self, s: State, m: Move) -> tuple[State, list[TraceEvent]]:
        if not self._enabled(s, m):
            raise ValueError(f"move {m.label} is not enabled at t={s.t_ms}")
        if m == TICK:
            return self._tick(s)
        t = s.t_ms
        ev = [TraceEvent(t, m.name, m.label, True)]
        s = replace(s, inj_left=s.inj_left - 1)
        if m.name == "bms_fault":
            s = replace(s, bms="FAULTED", fault_acked=False)
            bus = list(s.bus)
            self._send_bms(bus, Msg("FAULT", "bms", "hub", (("state", "FAULTED"),)), t, ev)
            nxt = t + self.fault_retx_ms if self.fault_retx_ms else None
            s = replace(s, bus=_sorted(bus), next_retx_ms=nxt)
        elif m.name == "hub_restart":
            lost = [b for b in s.bus if b.msg.dst == "hub"]
            for b in lost:
                ev.append(TraceEvent(t, "lost", f"{b.id} (hub RX buffer cleared)"))
            s = replace(s, hub=None, nvm_down=s.hub.nvm, nvm_label=str(s.hub.view().get("nvm", "")),
                        boot_at_ms=t + HUB_BOOT_MS,
                        hub_bms_seen="UNKNOWN",
                        bus=tuple(b for b in s.bus if b.msg.dst != "hub"))
        elif m.name == "network_loss":
            lost = [b for b in s.bus if _on_link(b)]
            for b in lost:
                ev.append(TraceEvent(t, "lost", f"{b.id} (hub-inverter link down)"))
            s = replace(s, link_up=False, bus=tuple(b for b in s.bus if not _on_link(b)))
        else:
            b = self._find(s, str(m.arg("msg")))
            assert b is not None
            rest = [x for x in s.bus if x is not b]
            if m.name == "bus_delay":
                nb = replace(b, due_ms=b.due_ms + int(m.arg("extra_ms")))
                s = replace(s, bus=_sorted(rest + [nb]))
                ev.append(TraceEvent(t, "delayed", f"{b.id} now due {nb.due_ms}"))
            elif m.name == "bus_drop":
                s = replace(s, bus=_sorted(rest))
                ev.append(TraceEvent(t, "lost", f"{b.id} (dropped)"))
            else:
                nb = replace(b, id=b.id + "+dup", dup=True)
                s = replace(s, bus=_sorted(list(s.bus) + [nb]))
                ev.append(TraceEvent(t, "duplicated", f"{nb.id} due {nb.due_ms}"))
        return self._observe(s), ev

    def _tick(self, s: State) -> tuple[State, list[TraceEvent]]:
        sut = self.sut
        t = s.t_ms + TICK_MS
        ev: list[TraceEvent] = []
        hub, inv = s.hub, s.inv
        bus = list(s.bus)
        out: list[BusMsg] = []           # sent this tick, queued after deliveries
        seen = s.hub_bms_seen
        bms, acked, nxt = s.bms, s.fault_acked, s.next_retx_ms
        last_rx, basis, expires = s.inv_last_rx_ms, s.inv_basis, s.inv_expires_ms
        applied, repeat = s.applied, s.i4_repeat
        nvm_down, boot_at, nvm_label = s.nvm_down, s.boot_at_ms, s.nvm_label

        def inv_hook(res: Any) -> None:
            nonlocal inv, applied, repeat
            before = int(inv.view().get("applies") or 0)
            inv = res.ctl
            v = inv.view()
            if int(v.get("applies") or 0) > before and v.get("seq") is not None:
                key = (int(v["epoch"]), int(v["seq"]))
                if key in applied:
                    if repeat is None:
                        repeat = f"e{key[0]} seq{key[1]}"
                    ev.append(TraceEvent(t, "inv_reapply", f"inverter applied e{key[0]} seq{key[1]} again"))
                else:
                    applied = tuple(sorted(applied + (key,)))
            for mm in res.sends:
                self._queue(out, bus, mm, t, seen, s.link_up, ev)

        def hub_sends(res: Any, refresh_seq: Any = None) -> None:
            for mm in res.sends:
                quiet = mm.kind == "CMD" and refresh_seq is not None and mm.get("seq") == refresh_seq
                self._queue(out, bus, mm, t, seen, s.link_up, ev, quiet)

        # 1. hub boot completes
        if hub is None and boot_at is not None and boot_at <= t:
            res = sut.hub_on_boot(nvm_down, t)
            hub, nvm_down, boot_at = res.ctl, None, None
            nvm_label = ""
            ev.append(TraceEvent(t, "hub_boot", f"hub up as {hub.mode}"))
            hub_sends(res)

        # 2. deliveries due now, by (due, id)
        due = [b for b in bus if b.due_ms <= t]
        bus = [b for b in bus if b.due_ms > t]
        for b in due:
            dst = b.msg.dst
            if dst == "hub":
                if hub is None:
                    ev.append(TraceEvent(t, "lost", f"{b.id} (hub restarting)"))
                    continue
                if b.msg.kind == "FAULT":
                    seen = "FAULTED"
                elif b.msg.kind == "STATUS":
                    seen = str(b.msg.get("state"))
                res = sut.hub_on_msg(hub, b.msg, t)
                hub = res.ctl
                ev.append(TraceEvent(t, "deliver", f"{b.id} → hub"))
                hub_sends(res)
            elif dst == "inv":
                last_rx = t
                res = sut.inv_on_cmd(inv, b.msg, t)
                ev.append(TraceEvent(t, "deliver", f"{b.id} → inv"))
                inv_hook(res)
                v = inv.view()
                if b.msg.kind == "CMD" and v.get("seq") == b.msg.get("seq") and v.get("epoch") == b.msg.get("epoch"):
                    basis = b.basis
                    expires = int(b.msg.get("expires_ms", 0))
            elif dst == "bms":
                if b.msg.kind == "ACK" and bms == "FAULTED":
                    acked, nxt = True, None
                ev.append(TraceEvent(t, "deliver", f"{b.id} → bms"))

        # 3. BMS environment: status heartbeat and FAULT retransmit
        if t % BMS_STATUS_MS == 0:
            self._send_bms(out, Msg("STATUS", "bms", "hub", (("state", bms),)), t, ev, bus)
        if bms == "FAULTED" and not acked and nxt is not None and t >= nxt:
            self._send_bms(out, Msg("FAULT", "bms", "hub", (("state", "FAULTED"),)), t, ev, bus)
            nxt = t + self.fault_retx_ms if self.fault_retx_ms else None

        # 4. controller tick hooks
        if hub is not None:
            before_seq = hub.view().get("seq")
            res = sut.hub_on_tick(hub, t)
            hub = res.ctl
            hub_sends(res, refresh_seq=before_seq)
        prev_mode = inv.mode
        inv_hook(sut.inv_on_tick(inv, t))
        if inv.mode != prev_mode:
            ev.append(TraceEvent(t, "inv_mode", f"inverter {prev_mode} → {inv.mode}"))

        i1, i5 = _timers(t, bms, inv.mode, last_rx, s.i1_since_ms)
        ns = State(t, s.inj_left, bms, acked, nxt, s.link_up, _sorted(bus + out), hub, boot_at,
                   nvm_down, nvm_label, inv, seen, last_rx, basis, expires, applied, repeat, i1, i5)
        return ns, ev

    # ---- helpers ------------------------------------------------------------------------------
    @staticmethod
    def _new_id(kind: str, t: int, taken: list[BusMsg], more: list[BusMsg]) -> str:
        base = f"{kind.lower()}@{t}"
        ids = {b.id for b in taken} | {b.id for b in more}
        if base not in ids:
            return base
        n = 2
        while f"{base}.{n}" in ids:
            n += 1
        return f"{base}.{n}"

    def _send_bms(self, out: list[BusMsg], msg: Msg, t: int, ev: list[TraceEvent],
                  other: list[BusMsg] | None = None) -> None:
        mid = self._new_id(msg.kind, t, out, other or [])
        out.append(BusMsg(mid, msg, t, t + LATENCY_BASE_MS))
        ev.append(TraceEvent(t, "send", f"{mid} {msg.kind} bms→hub"))

    def _queue(self, out: list[BusMsg], bus: list[BusMsg], msg: Msg, t: int, seen: str,
               link_up: bool, ev: list[TraceEvent], refresh: bool = False) -> None:
        mid = self._new_id(msg.kind, t, out, bus)
        b = BusMsg(mid, msg, t, t + LATENCY_BASE_MS, basis=seen if msg.src == "hub" else "")
        detail = f"{mid} {msg.kind} {msg.src}→{msg.dst}"
        if msg.kind == "CMD":
            detail += f" seq{msg.get('seq')} {msg.get('kind')} {msg.get('watts')}W e{msg.get('epoch')}"
        if _on_link(b) and not link_up:
            ev.append(TraceEvent(t, "lost", f"{detail} (link down)"))
            return
        out.append(b)
        ev.append(TraceEvent(t, "refresh" if refresh else "send", detail))

    def _observe(self, s: State) -> State:
        """Recompute the invariant timers from the current state."""
        i1, i5 = _timers(s.t_ms, s.bms, s.inv.mode, s.inv_last_rx_ms, s.i1_since_ms)
        if i1 == s.i1_since_ms and i5 == s.i5_since_ms:
            return s
        return replace(s, i1_since_ms=i1, i5_since_ms=i5)

    # ---- snapshot / describe ------------------------------------------------------------------
    def snapshot(self, s: State) -> Snapshot:
        iv = s.inv.view()
        inv = f"{s.inv.mode}"
        if s.inv.mode == "DISCHARGING":
            inv += f" {iv.get('watts')}W"
        if iv.get("seq") is not None:
            inv += f" seq{iv['seq']} e{iv['epoch']}"
        if s.hub is None:
            hub = f"RESTARTING until {s.boot_at_ms}"
            nvm = s.nvm_label
        else:
            hv = s.hub.view()
            hub = f"{s.hub.mode} e{hv.get('epoch')}"
            if hv.get("seq") is not None:
                hub += f" seq{hv['seq']} {hv.get('kind')}"
                if hv.get("kind") != "STOP":
                    hub += f" {hv.get('watts')}W"
            nvm = str(hv.get("nvm", ""))
        bms = s.bms
        if s.bms == "FAULTED":
            bms += " acked" if s.fault_acked else " unacked"
        return {
            "t_ms": s.t_ms,
            "bms": bms,
            "bus": "; ".join(b.label() for b in s.bus),
            "hub": hub,
            "inv": inv,
            "nvm": nvm,
            "hub_bms": s.hub_bms_seen,
            "link": "UP" if s.link_up else "DOWN",
            "inv_basis": s.inv_basis,
            "i1_since_ms": s.i1_since_ms,
            "i5_since_ms": s.i5_since_ms,
            "i4_repeat": s.i4_repeat,
            "injections_left": s.inj_left,
        }

    def describe(self) -> dict[str, Any]:
        from fleetflight.sut import list_suts

        sid = sut_id(self.sut)
        inj_desc = {
            "bms_fault": ("BMS enters FAULTED (e.g. overtemp) and sends FAULT to the hub, "
                          "retransmitted until ACKed.", []),
            "hub_restart": (f"Hub loses power: queued RX messages are lost, it boots after "
                            f"{HUB_BOOT_MS} ms with only its NVM.", []),
            "network_loss": ("The hub-inverter link goes down for the rest of the run.", []),
            "bus_delay": (f"Push one in-flight message later; total latency stays <= {LATENCY_MAX_MS} ms.",
                          [{"name": "msg", "values": "any in-flight message id"},
                           {"name": "extra_ms", "values": list(self.delay_steps_ms)}]),
            "bus_drop": ("Lose one in-flight message.", [{"name": "msg", "values": "any in-flight message id"}]),
            "bus_dup": ("Duplicate one in-flight message (same due time).",
                        [{"name": "msg", "values": "any in-flight message id (not itself a duplicate)"}]),
        }
        doc: dict[str, Any] = {
            "schema": SCHEMA_DESCRIBE,
            "model": {"name": self.name, "version": self.version, "hash": ""},
            "sut": {"id": sid, "name": self.sut.name, "version": self.sut.version},
            "sut_versions": list_suts() if self.sut.name == "firmware-ref" else [sid],
            "tick_ms": TICK_MS,
            "components": [
                {"id": "bms", "name": "BMS", "owner": "model", "states": ["HEALTHY", "FAULTED"],
                 "description": f"Battery management system. Sends FAULT on the HEALTHY→FAULTED edge "
                                f"(retransmitted until ACKed) and STATUS every {BMS_STATUS_MS} ms. "
                                "The hub's view of it is UNKNOWN until a report arrives after a boot."},
                {"id": "bus", "name": "Bus", "owner": "model", "states": ["in-flight messages"],
                 "description": f"Carries every message with {LATENCY_BASE_MS} ms latency; the adversary may "
                                f"delay (total <= {LATENCY_MAX_MS} ms), drop or duplicate, which also reorders."},
                {"id": "hub", "name": "Hub manager", "owner": "sut", "states": ["ONLINE", "RESTARTING", "DEGRADED"],
                 "description": f"System under test. RESTARTING is the model's power lifecycle "
                                f"({HUB_BOOT_MS} ms, RX lost, NVM kept); the rest is firmware logic."},
                {"id": "inv", "name": "Inverter controller", "owner": "sut",
                 "states": ["DISCHARGING", "IDLE", "SHUTDOWN"],
                 "description": "System under test. Executes hub commands and falls back when the hub goes silent."},
            ],
            "injectables": [{"name": n, "description": inj_desc[n][0], "params": inj_desc[n][1]}
                            for n in self.injections],
            "invariants": [i.to_json() for i in self.invariants],
            "assumptions": list(self.assumptions),
            "bounds": self.bounds.to_json(),
            "constants": {
                "LATENCY_BASE_MS": LATENCY_BASE_MS,
                "LATENCY_MAX_MS": LATENCY_MAX_MS,
                "HUB_BOOT_MS": HUB_BOOT_MS,
                "BMS_STATUS_MS": BMS_STATUS_MS,
                "FAULT_RETX_MS": self.fault_retx_ms if self.fault_retx_ms else 0,
                "SHUTDOWN_BUDGET_MS": SHUTDOWN_BUDGET_MS,
                "COMMS_LOSS_BUDGET_MS": COMMS_LOSS_BUDGET_MS,
                "HIGH_POWER_W": HIGH_POWER_W,
                "DISPATCH_WATTS": DISPATCH_WATTS,
                "DISPATCH_EXPIRES_MS": DISPATCH_EXPIRES_MS,
                **dict(getattr(self.sut, "constants", {})),
            },
            "snapshot_keys": [{"key": k, "label": lbl, "lane": lane} for k, lbl, lane in SNAPSHOT_KEYS],
        }
        doc["model"]["hash"] = model_hash(doc)
        return doc


def _delay(mid: str, extra: int) -> Move:
    return Move("bus_delay", (("msg", mid), ("extra_ms", extra)))


SCENARIOS: dict[str, tuple[str, list[tuple[int, Move]]]] = {
    # name: (description, [(t_ms, injected move), ...]); injections at t apply before the TICK leaving t
    "bms-fault-basic": (
        "Happy path: BMS fault at 100 ms, its FAULT message delayed 400 ms, no restart.",
        [(100, Move("bms_fault")), (100, _delay("fault@100", 400))]),
    "restart-during-fault": (
        "The README sequence: fault at 100 ms, FAULT delayed 400 ms, hub restarts at 200 ms.",
        [(100, Move("bms_fault")), (100, _delay("fault@100", 400)), (200, Move("hub_restart"))]),
    "fault-during-link-loss": (
        "BMS fault while the hub-inverter link is down (the minimal I1 counterexample for v0.3.1).",
        [(0, Move("bms_fault")), (0, Move("network_loss"))]),
    "stale-reorder": (
        "A pre-fault refresh (seq41) is delayed past the STOP (I4 in v0.3.1/v0.3.2).",
        [(100, Move("bms_fault")), (100, _delay("cmd@100", 100))]),
    "restart-only": (
        "Hub restart with a healthy BMS (I2 in v0.3.1: blind resume from NVM).",
        [(0, Move("hub_restart"))]),
    "link-loss": (
        "The hub-inverter link goes down at 0 ms (I5 fallback).",
        [(0, Move("network_loss"))]),
}


def _timers(t: int, bms: str, inv_mode: str, last_rx: int, i1_prev: int | None) -> tuple[int | None, int | None]:
    """The I1 and I5 timers (see the invariants' timer_key)."""
    running = inv_mode == "DISCHARGING"
    i1 = (i1_prev if i1_prev is not None else t) if (bms == "FAULTED" and running) else None
    i5 = last_rx if (running and t - last_rx > HUB_REFRESH_MS) else None
    return i1, i5


def _on_link(b: BusMsg) -> bool:
    return {b.msg.src, b.msg.dst} == {"hub", "inv"}


def _sorted(bus: list[BusMsg]) -> tuple[BusMsg, ...]:
    # Ties on due time are delivered FIFO by send time (then id). Sorting by id alone was a bug:
    # "cmd@1100" < "cmd@900" flipped the tie order after t=1000 (found by the adversarial review).
    return tuple(sorted(bus, key=lambda b: (b.due_ms, b.sent_ms, b.id)))
