"""MOCK: what a FleetFlight model looks like.

Key design choice (open question #3): the model checker and the simulator share ONE
transition definition. The checker enumerates every enabled event at each tick; the
simulator picks one per tick from a seeded RNG (or from a counterexample file). So a
counterexample is not "translated" into a test, it is literally the same event list.

This is a behavioral model of a *reference* system. Not Base's Gen 3 architecture.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from fleetflight import Event, Model, assumption, invariant, bounded  # MOCK API

TICK_MS = 100


class Bms(Enum):
    HEALTHY = "HEALTHY"; FAULTED = "FAULTED"; UNKNOWN = "UNKNOWN"


class Inv(Enum):
    IDLE = "IDLE"; CHARGING = "CHARGING"; DISCHARGING = "DISCHARGING"; SHUTDOWN = "SHUTDOWN"


class Hub(Enum):
    ONLINE = "ONLINE"; RESTARTING = "RESTARTING"; DEGRADED = "DEGRADED"


@dataclass(frozen=True)
class Cmd:
    seq: int
    kind: str          # "DISCHARGE" | "CHARGE" | "STOP"
    kw: float
    expires_ms: int
    epoch: int = 0     # hub boot epoch (added by the fix)


@dataclass(frozen=True)
class Msg:
    id: str
    src: str
    dst: str
    body: object
    deliver_at_ms: int


@dataclass(frozen=True)
class State:
    t_ms: int
    bms: Bms
    inv: Inv
    hub: Hub
    hub_epoch: int
    hub_nvm_cmd: Cmd | None      # "restart recovery" storage
    inv_cmd: Cmd | None
    inv_last_cmd_ms: int
    bus: tuple[Msg, ...]         # in-flight messages
    fault_since_ms: int | None


# ---- explicit assumptions: rendered in every report ---------------------------------
assumption("bus.latency_ms <= 800")
assumption("bus may delay, drop, duplicate, reorder")
assumption("BMS FAULT message is edge-triggered; status heartbeat every 2000 ms")
assumption("inverter holds last setpoint 1000 ms without hub command, then IDLE")
assumption("hardware interlocks OUT OF SCOPE")


# ---- events: each is (guard, effect). Checker branches on every enabled one. ----------
@Event(injectable=True)
def bms_fault(s: State):
    if s.bms is not Bms.HEALTHY:
        return None
    msg = Msg("m_fault", "bms", "hub", "FAULT", deliver_at_ms=s.t_ms)  # latency chosen by bus_delay
    return replace(s, bms=Bms.FAULTED, fault_since_ms=s.t_ms, bus=s.bus + (msg,))


@Event(injectable=True, params={"extra_ms": range(0, 801, 100)})
def bus_delay(s: State, extra_ms: int):
    ...  # push deliver_at_ms of one in-flight message forward, within the latency bound


@Event(injectable=True)
def hub_restart(s: State):
    if s.hub is Hub.RESTARTING:
        return None
    # RX buffer is volatile: messages addressed to the hub are lost.
    bus = tuple(m for m in s.bus if m.dst != "hub")
    return replace(s, hub=Hub.RESTARTING, hub_epoch=s.hub_epoch + 1, bus=bus)


@Event()
def hub_boot_complete(s: State):
    if s.hub is not Hub.RESTARTING:
        return None
    return hub_on_boot(s)  # <- system-under-test hook


@Event()
def deliver(s: State):
    ...  # deliver any message whose deliver_at_ms <= t; routes to hub_on_msg / inv_on_cmd


@Event(always=True)
def tick(s: State):
    ...  # advance 100 ms; inverter hold-timer; BMS heartbeat


# ---- system under test: reference hub manager ----------------------------------------
# In production this hook would call the real hub-manager code (or a SIL build).
def hub_on_boot(s: State) -> State:
    # BUG (v0.3.1): trust NVM and resume the last command immediately.
    if s.hub_nvm_cmd and s.hub_nvm_cmd.expires_ms > s.t_ms:
        send = Msg("m_resume", "hub", "inv", s.hub_nvm_cmd, deliver_at_ms=s.t_ms + 50)
        return replace(s, hub=Hub.ONLINE, bus=s.bus + (send,))
    return replace(s, hub=Hub.ONLINE)


def hub_on_boot_v032(s: State) -> State:
    # PARTIAL FIX (v0.3.2): boot DEGRADED, drop NVM command, send STOP.
    # Still violates I1 on cex-0017: the 400 ms boot alone exceeds the 500 ms budget.
    stop = Msg("m_stop", "hub", "inv", Cmd(0, "STOP", 0.0, 0, epoch=s.hub_epoch), s.t_ms + 50)
    return replace(s, hub=Hub.DEGRADED, hub_nvm_cmd=None, bus=s.bus + (stop,))


# FIX (v0.3.3) lives in the inverter model, not the hub:
INV_HUB_LOSS_TIMEOUT_MS = 200   # was: hold setpoint 1000 ms
INV_HUB_LOSS_ACTION = Inv.SHUTDOWN


# ---- invariants -----------------------------------------------------------------------
@invariant("I1 FAULT_SHUTDOWN_BOUNDED")
@bounded(ms=500)
def fault_implies_shutdown(s: State) -> bool:
    return not (s.bms is Bms.FAULTED and s.inv is Inv.DISCHARGING)


@invariant("I2 NO_HIGH_POWER_WHEN_UNKNOWN")
def unknown_blocks_power(s: State) -> bool:
    return not (s.bms is Bms.UNKNOWN and s.inv_cmd is not None and s.inv_cmd.kw > 1.0)


@invariant("I3 NO_RESURRECTED_COMMANDS")
def no_resurrection(s: State) -> bool:
    return s.inv_cmd is None or s.inv_cmd.expires_ms > s.t_ms


@invariant("I4 IDEMPOTENT_COMMANDS")
def idempotent(s: State) -> bool:
    ...  # a duplicated seq never produces a second physical action


@invariant("I5 COMMS_LOSS_SAFE_FALLBACK")
@bounded(ms=1500)
def comms_loss_fallback(s: State) -> bool:
    ...  # no hub command for 1000 ms  =>  inverter IDLE/SHUTDOWN


MODEL = Model(
    name="core-ref",
    init=State(t_ms=0, bms=Bms.HEALTHY, inv=Inv.DISCHARGING, hub=Hub.ONLINE, hub_epoch=1,
               hub_nvm_cmd=Cmd(41, "DISCHARGE", 5.0, expires_ms=30_000),
               inv_cmd=Cmd(41, "DISCHARGE", 5.0, expires_ms=30_000),
               inv_last_cmd_ms=0, bus=(), fault_since_ms=None),
    tick_ms=TICK_MS,
    max_depth=40,           # 4 s horizon
    max_injections=3,       # at most 3 injected faults per trace
)
