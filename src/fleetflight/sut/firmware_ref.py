"""firmware-ref: the reference hub-manager and inverter-controller logic (the system under test).

This is firmware WE wrote for the demo. It is not Base Gen 3 firmware. v0.3.1 is written the
way a reasonable engineer might write it on a first pass; the checker then finds what is wrong
with it. Every hook is pure: same inputs, same outputs, no I/O, no clock.

Versions (CONTRACT.md: ``load_sut("v0.3.1")``):

* **v0.3.1** "restart recovery". After a reboot the hub restores the last command from NVM and
  re-sends it if it has not expired, so a dispatch survives a hub crash. The inverter holds its
  last setpoint for ``INV_HOLD_MS`` without hub messages, then goes IDLE. The inverter drops a
  duplicate by comparing the seq with the one it is executing ("last-seen" dedupe).
* **v0.3.2** hub-side fix. The hub boots DEGRADED, drops the NVM command and sends STOP.
* **v0.3.3** inverter-side fix. v0.3.2 plus: the inverter goes SHUTDOWN after
  ``HUB_LOSS_TIMEOUT_MS`` without a hub message, and only accepts commands whose
  ``(epoch, seq)`` is newer than the one it executes (older hub epochs and reordered stale
  commands are rejected).

Message protocol (fields are ``(name, value)`` pairs, see ``core.Msg``):

* ``CMD`` hub→inv: ``seq, kind (DISCHARGE|STOP), watts, expires_ms, epoch``. The hub re-sends
  its current command every ``HUB_REFRESH_MS``; that refresh is the inverter's heartbeat.
* ``DISPATCH`` cloud→hub: ``kind, watts, expires_ms`` (scenario setup only).
* ``FAULT`` bms→hub (the hub answers ``ACK`` hub→bms), ``STATUS`` bms→hub: ``state``.

The view protocol the model relies on (the model reads ``mode`` and ``view()`` only):
hub view has ``mode, epoch, seq, kind, watts, bms, nvm``; inverter view has
``mode, epoch, seq, kind, watts, applies`` where ``applies`` counts setpoint applications.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from fleetflight.core import HookResult, Msg, SnapshotValue

INV_HOLD_MS = 1000
HUB_LOSS_TIMEOUT_MS = 200
HUB_REFRESH_MS = 100
NEVER_MS = 2**31 - 1     # STOP commands do not expire

VERSIONS = ("v0.3.1", "v0.3.2", "v0.3.3")


@dataclass(frozen=True, slots=True, order=True)
class Cmd:
    epoch: int
    seq: int
    kind: str          # "DISCHARGE" | "STOP"
    watts: int
    expires_ms: int

    @property
    def key(self) -> tuple[int, int]:
        return (self.epoch, self.seq)

    def to_msg(self) -> Msg:
        return Msg("CMD", "hub", "inv", (
            ("seq", self.seq), ("kind", self.kind), ("watts", self.watts),
            ("expires_ms", self.expires_ms), ("epoch", self.epoch)))

    @classmethod
    def from_msg(cls, m: Msg) -> Cmd:
        return cls(int(m.get("epoch")), int(m.get("seq")), str(m.get("kind")),
                   int(m.get("watts")), int(m.get("expires_ms")))

    def label(self) -> str:
        return f"seq{self.seq} {self.kind} {self.watts}W e{self.epoch}"


@dataclass(frozen=True, slots=True)
class HubNvm:
    """What survives a hub restart."""
    epoch: int
    next_seq: int
    cmd: Cmd | None     # last command, for "restart recovery" (v0.3.1 restores it)

    def label(self) -> str:
        return f"e{self.epoch} next{self.next_seq} " + (self.cmd.label() if self.cmd else "no-cmd")


@dataclass(frozen=True, slots=True)
class HubCtl:
    mode: str           # "ONLINE" | "DEGRADED"
    nvm: HubNvm
    cmd: Cmd | None
    bms: str            # the hub's belief: "HEALTHY" | "FAULTED" | "UNKNOWN"

    def view(self) -> dict[str, SnapshotValue]:
        c = self.cmd
        return {"mode": self.mode, "epoch": self.nvm.epoch, "seq": c.seq if c else None,
                "kind": c.kind if c else None, "watts": c.watts if c else 0, "bms": self.bms,
                "nvm": self.nvm.label()}


@dataclass(frozen=True, slots=True)
class InvCtl:
    mode: str           # "DISCHARGING" | "IDLE" | "SHUTDOWN"
    cmd: Cmd | None     # the command last applied (or refreshed)
    last_rx_ms: int     # last accepted hub command (the watchdog)
    applies: int        # number of setpoint applications so far

    def view(self) -> dict[str, SnapshotValue]:
        c = self.cmd
        return {"mode": self.mode, "epoch": c.epoch if c else None, "seq": c.seq if c else None,
                "kind": c.kind if c else None,
                "watts": c.watts if (c and self.mode == "DISCHARGING") else 0,
                "applies": self.applies}


class FirmwareRef:
    """firmware-ref at one version. Subclass and override a hook to make a mutant (tests only)."""

    name = "firmware-ref"

    def __init__(self, version: str) -> None:
        if version not in VERSIONS:
            raise ValueError(f"unknown firmware-ref version {version!r}; have {VERSIONS}")
        self.version = version
        self.boot_degraded = version >= "v0.3.2"
        self.inv_local_fallback = version >= "v0.3.3"
        # SUT constants shown on the Spec screen (model describe() merges them in)
        self.constants: dict[str, int] = {"HUB_REFRESH_MS": HUB_REFRESH_MS}
        if self.inv_local_fallback:
            self.constants["HUB_LOSS_TIMEOUT_MS"] = HUB_LOSS_TIMEOUT_MS
        else:
            self.constants["INV_HOLD_MS"] = INV_HOLD_MS

    # ---- initial states ---------------------------------------------------------------------
    def hub_init(self, nvm: HubNvm | None = None) -> HubCtl:
        """A hub that has been up for a while and has seen a HEALTHY BMS status."""
        return HubCtl("ONLINE", nvm or HubNvm(1, 41, None), None, "HEALTHY")

    def inv_init(self) -> InvCtl:
        return InvCtl("IDLE", None, 0, 0)

    # ---- hub manager --------------------------------------------------------------------------
    def _issue(self, hub: HubCtl, kind: str, watts: int, expires_ms: int) -> tuple[HubCtl, Cmd]:
        """Issue a new command with the next seq. Seq and epoch live in NVM."""
        n = hub.nvm
        cmd = Cmd(n.epoch, n.next_seq, kind, watts, expires_ms)
        keep = cmd if not self.boot_degraded else None  # v0.3.2+ no longer keeps a command in NVM
        return replace(hub, cmd=cmd, nvm=HubNvm(n.epoch, n.next_seq + 1, keep)), cmd

    def hub_on_boot(self, nvm: HubNvm, now_ms: int) -> HookResult:
        epoch = nvm.epoch + 1
        if self.boot_degraded:
            # v0.3.2+: boot DEGRADED, forget the old command, stop the inverter.
            hub = HubCtl("DEGRADED", HubNvm(epoch, nvm.next_seq, None), None, "UNKNOWN")
            hub, stop = self._issue(hub, "STOP", 0, NEVER_MS)
            return HookResult(hub, (stop.to_msg(),))
        # v0.3.1 "restart recovery": trust NVM and resume the last command if still valid.
        hub = HubCtl("ONLINE", HubNvm(epoch, nvm.next_seq, nvm.cmd), None, "UNKNOWN")
        c = nvm.cmd
        if c is not None and c.expires_ms > now_ms:
            return HookResult(replace(hub, cmd=c), (c.to_msg(),))
        return HookResult(hub)

    def hub_on_msg(self, hub: HubCtl, msg: Msg, now_ms: int) -> HookResult:
        if msg.kind == "DISPATCH":
            # From the cloud (the model only uses this to set up the scenario at t=0).
            hub, cmd = self._issue(hub, str(msg.get("kind")), int(msg.get("watts")),
                                   int(msg.get("expires_ms")))
            return HookResult(hub, (cmd.to_msg(),))
        if msg.kind == "FAULT":
            hub, sends = self._on_bms_faulted(replace(hub, bms="FAULTED"), now_ms)
            return HookResult(hub, sends + (Msg("ACK", "hub", "bms", (("of", "FAULT"),)),))
        if msg.kind == "STATUS":
            state = str(msg.get("state"))
            hub = replace(hub, bms=state)
            if state == "FAULTED":
                hub, sends = self._on_bms_faulted(hub, now_ms)
                return HookResult(hub, sends)
            return HookResult(hub)
        return HookResult(hub)

    def _on_bms_faulted(self, hub: HubCtl, now_ms: int) -> tuple[HubCtl, tuple[Msg, ...]]:
        if hub.cmd is not None and hub.cmd.kind == "STOP":
            return hub, ()
        hub, stop = self._issue(hub, "STOP", 0, NEVER_MS)
        return hub, (stop.to_msg(),)

    def hub_on_tick(self, hub: HubCtl, now_ms: int) -> HookResult:
        c = hub.cmd
        if c is not None and c.kind == "DISCHARGE" and c.expires_ms <= now_ms:
            hub, stop = self._issue(hub, "STOP", 0, NEVER_MS)
            return HookResult(hub, (stop.to_msg(),))
        if c is not None and now_ms % HUB_REFRESH_MS == 0:
            return HookResult(hub, (c.to_msg(),))
        return HookResult(hub)

    # ---- inverter controller -------------------------------------------------------------------
    def inv_on_cmd(self, inv: InvCtl, msg: Msg, now_ms: int) -> HookResult:
        if msg.kind != "CMD":
            return HookResult(inv)
        cmd = Cmd.from_msg(msg)
        if cmd.expires_ms <= now_ms:
            return HookResult(inv)                       # expired on arrival: ignore
        cur = inv.cmd
        if self.inv_local_fallback:
            # v0.3.3: strictly newer (epoch, seq) only; equal is a refresh; older is rejected.
            if cur is not None and cmd.key < cur.key:
                return HookResult(inv)
            if cur is not None and cmd.key == cur.key:
                return HookResult(replace(inv, last_rx_ms=now_ms))
        elif cur is not None and cmd.seq == cur.seq:
            # v0.3.1/v0.3.2: last-seen dedupe. Same seq as the one executing = refresh only.
            return HookResult(replace(inv, last_rx_ms=now_ms))
        mode = "DISCHARGING" if cmd.kind == "DISCHARGE" else "IDLE"
        return HookResult(InvCtl(mode, cmd, now_ms, inv.applies + 1))

    def inv_on_tick(self, inv: InvCtl, now_ms: int) -> HookResult:
        if inv.mode != "DISCHARGING":
            return HookResult(inv)
        if inv.cmd is not None and inv.cmd.expires_ms <= now_ms:
            return HookResult(replace(inv, mode="IDLE"))
        silent = now_ms - inv.last_rx_ms
        if self.inv_local_fallback:
            if silent > HUB_LOSS_TIMEOUT_MS:
                return HookResult(replace(inv, mode="SHUTDOWN"))
        elif silent > INV_HOLD_MS:
            return HookResult(replace(inv, mode="IDLE"))
        return HookResult(inv)

    # ---- display ------------------------------------------------------------------------------
    def changelog(self) -> str:
        return CHANGELOG[self.version]

    def __repr__(self) -> str:
        return f"FirmwareRef({self.version!r})"


CHANGELOG = {
    "v0.3.1": "Hub restart recovery: restore the last command from NVM and re-send it if not "
              "expired. Inverter holds its setpoint 1000 ms without hub messages, then IDLE.",
    "v0.3.2": "Hub boots DEGRADED, drops the NVM command and sends STOP on boot.",
    "v0.3.3": "v0.3.2 + inverter goes SHUTDOWN after 200 ms without a hub message and rejects "
              "commands older than the one it executes (older hub epoch or seq).",
}
