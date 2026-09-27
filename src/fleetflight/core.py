"""FleetFlight shared contract (contract-v1).

Every stream builds against this module. It defines the execution model, the Model and SUT
protocols, and the few pure helpers (hashing, ids, JSON encoding) that must agree bit-for-bit
between the checker, the simulator, the regression generator and the UI.

Execution model: the adversary chooses, the system is deterministic
---------------------------------------------------------------------
Time is discrete. All time is an integer count of milliseconds, always a multiple of TICK_MS.

At every state the model offers a list of moves (``Model.moves``):

* ``TICK`` advances time by one tick. During the tick the model runs everything that is *not*
  a choice: due message deliveries, SUT tick hooks, timers, heartbeats. It is the only move
  that takes time.
* Every other move is an **injection**: a fault or timing choice made by the adversary
  (``bms_fault``, ``hub_restart``, ``bus_delay(msg=..., extra_ms=...)``, ...). Injections take
  no time and are limited by a budget (``Bounds.max_injections``) that the model keeps in the
  state.

``Model.apply(state, move)`` is pure and deterministic. So the only nondeterminism in the whole
system is *which move is chosen*, and a run is fully described by its list of moves:

* the checker explores every choice (BFS over ``moves``/``apply``);
* the simulator picks one choice per step (seeded RNG, or a script);
* a counterexample is just the list of moves the checker found, and replaying it through the
  same ``apply`` reproduces the same states, the same snapshots and the same trace hash.

The checker and the simulator therefore share one definition of the system. Nothing is
translated between them.

Determinism rules (anything that affects a trace)
-------------------------------------------------
* No wall-clock time, no unseeded randomness, no iteration over ``set``/``frozenset`` or other
  unordered containers without sorting first.
* ``moves(state)`` returns the same list, in the same order, for equal states.
* States are frozen, hashable dataclasses with a ``t_ms: int`` field. Avoid floats: use integer
  watts / milliseconds.
* Snapshot values are ``str``, ``int`` or ``None`` only (no ``bool``, no ``float``).
* JSON that is hashed goes through :func:`canonical_json`.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeAlias, TypeVar, runtime_checkable

__all__ = [
    "TICK_MS",
    "CONTRACT_VERSION",
    "SCHEMA_DESCRIBE",
    "SCHEMA_CHECK_REPORT",
    "SCHEMA_COUNTEREXAMPLE",
    "SCHEMA_REPLAY_RESULT",
    "SCHEMA_RUN_LIST",
    "ASSUMPTION_TAGS",
    "ArgValue",
    "SnapshotValue",
    "Snapshot",
    "Move",
    "TICK",
    "TraceEvent",
    "Invariant",
    "Bounds",
    "Msg",
    "HookResult",
    "ControllerState",
    "SUT",
    "Model",
    "State",
    "canonical_json",
    "sha256_hex",
    "trace_hash",
    "short_hash",
    "model_hash",
    "sut_id",
    "parse_sut_id",
    "counterexample_id",
    "split_assumption",
]

# --------------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------------

TICK_MS: int = 50
"""Length of one TICK in milliseconds. Every ``t_ms`` in the system is a multiple of this."""

CONTRACT_VERSION = "contract-v1"

# Value of the required top-level "schema" field in each JSON document that crosses a stream
# boundary. The matching JSON Schemas live in schemas/.
SCHEMA_DESCRIBE = "fleetflight/describe@1"
SCHEMA_CHECK_REPORT = "fleetflight/check-report@1"
SCHEMA_COUNTEREXAMPLE = "fleetflight/counterexample@1"
SCHEMA_REPLAY_RESULT = "fleetflight/replay-result@1"
SCHEMA_RUN_LIST = "fleetflight/run-list@1"

ASSUMPTION_TAGS: tuple[str, ...] = ("ASSUMED", "OUT OF SCOPE")
"""Every assumption string starts with one of these tags followed by a space."""

ArgValue: TypeAlias = int | str
SnapshotValue: TypeAlias = str | int | None
Snapshot: TypeAlias = dict[str, SnapshotValue]

# --------------------------------------------------------------------------------------------
# Moves and trace events
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Move:
    """One choice at a state: either TICK (time passes) or an adversary injection.

    ``args`` is a tuple of ``(name, value)`` pairs in the order the model declares them.
    Arg names are unique within a move. Two moves are equal iff name, args and injected are
    equal, so a move read back from JSON compares equal to the one the model offers.
    """

    name: str
    args: tuple[tuple[str, ArgValue], ...] = ()
    injected: bool = True

    def arg(self, key: str) -> ArgValue:
        """Return the value of argument ``key`` (KeyError if absent)."""
        for k, v in self.args:
            if k == key:
                return v
        raise KeyError(key)

    @property
    def label(self) -> str:
        """Display form, e.g. ``bus_delay(msg=fault#1, extra_ms=400)`` or ``tick``."""
        if not self.args:
            return self.name
        return f"{self.name}({', '.join(f'{k}={v}' for k, v in self.args)})"

    def to_json(self) -> dict[str, Any]:
        """JSON form used in every file: ``{"name", "args": {..}, "injected", "label"}``.

        ``label`` is informational; :meth:`from_json` ignores it.
        """
        return {
            "name": self.name,
            "args": {k: v for k, v in self.args},
            "injected": self.injected,
            "label": self.label,
        }

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> Move:
        """Inverse of :meth:`to_json`. Preserves the arg order of the JSON object."""
        args = d.get("args") or {}
        return cls(
            name=d["name"],
            args=tuple((str(k), v) for k, v in args.items()),
            injected=bool(d.get("injected", True)),
        )


TICK: Move = Move("tick", (), injected=False)
"""The only non-injected move. Advances time by exactly TICK_MS."""


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """Something the system did during a move (message sent/delivered, timer fired, ...).

    For display only: trace events are not part of the state, not hashed, and never affect
    behavior. ``injected`` is True for the event that records an injection itself.
    """

    t_ms: int
    name: str
    detail: str = ""
    injected: bool = False

    def to_json(self) -> dict[str, Any]:
        return {"t_ms": self.t_ms, "name": self.name, "detail": self.detail, "injected": self.injected}

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> TraceEvent:
        return cls(int(d["t_ms"]), d["name"], d.get("detail", ""), bool(d.get("injected", False)))


# --------------------------------------------------------------------------------------------
# Invariants and bounds
# --------------------------------------------------------------------------------------------

S = TypeVar("S")
State: TypeAlias = Hashable
"""Models define their own frozen, hashable dataclass with a ``t_ms: int`` field.

The checker only relies on ``hash()``, ``==``, ``state.t_ms`` and ``model.snapshot(state)``.
"""


@dataclass(frozen=True)
class Invariant:
    """A safety property: a pure predicate on ONE state (True = holds).

    Bounded-time properties ("within 500 ms") are expressed by keeping a timer in the state
    (e.g. ``fault_since_ms``), so the checker never needs history. For such invariants set
    ``bound_ms`` and ``timer_key``:

    * ``timer_key`` names a snapshot key whose value is the ``t_ms`` at which the bounded
      condition started (e.g. "bms FAULTED and inverter DISCHARGING"), or ``None`` while the
      condition does not hold.
    * The checker computes ``violation_duration_ms = t_ms - snapshot[timer_key]`` at the
      violating state. The replayer computes the condition *window* (start, end, duration) from
      consecutive snapshots. Nobody needs to know model internals.
    """

    id: str                      # "I1"
    name: str                    # "FAULT_SHUTDOWN_BOUNDED"
    description: str             # one sentence, plain English
    formula: str                 # display only, e.g. "G(bms=FAULTED -> inv!=DISCHARGING within 500ms)"
    check: Callable[[Any], bool] = field(compare=False, repr=False)
    bound_ms: int | None = None
    timer_key: str | None = None

    @property
    def key(self) -> str:
        """``"I1 FAULT_SHUTDOWN_BOUNDED"``: the display key used in reports and tests."""
        return f"{self.id} {self.name}"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "formula": self.formula,
            "bound_ms": self.bound_ms,
            "timer_key": self.timer_key,
        }


@dataclass(frozen=True)
class Bounds:
    """Search / simulation bounds.

    * ``max_depth``: maximum number of moves (TICKs + injections) on a path from init.
    * ``max_injections``: maximum injected moves on a path. Enforced by the MODEL (the budget is
      kept in the state so ``moves`` stops offering injections), which is why the same Bounds
      object is passed to ``load_model`` and to ``check``.
    * ``horizon_ms``: states with ``t_ms >= horizon_ms`` are checked but not expanded.
    """

    max_depth: int = 120
    max_injections: int = 3
    horizon_ms: int = 4000

    def __post_init__(self) -> None:
        if self.max_depth < 0 or self.max_injections < 0 or self.horizon_ms < 0:
            raise ValueError("Bounds must be non-negative")
        if self.horizon_ms % TICK_MS:
            raise ValueError(f"horizon_ms must be a multiple of TICK_MS={TICK_MS}")

    def to_json(self) -> dict[str, int]:
        return {"max_depth": self.max_depth, "max_injections": self.max_injections, "horizon_ms": self.horizon_ms}

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> Bounds:
        return cls(int(d["max_depth"]), int(d["max_injections"]), int(d["horizon_ms"]))


# --------------------------------------------------------------------------------------------
# System under test: the seam where real firmware plugs in
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Msg:
    """A message a controller sends. The MODEL owns the bus: it assigns ids and delivery times.

    ``kind`` e.g. "FAULT", "STATUS", "CMD", "STOP", "HEARTBEAT". ``fields`` carries the payload
    as sorted-or-declared ``(name, value)`` pairs, e.g. ``(("seq", 41), ("kind", "DISCHARGE"),
    ("watts", 5000), ("epoch", 1))``.
    """

    kind: str
    src: str                     # "bms" | "hub" | "inv"
    dst: str
    fields: tuple[tuple[str, ArgValue], ...] = ()

    def get(self, key: str, default: ArgValue | None = None) -> ArgValue | None:
        for k, v in self.fields:
            if k == key:
                return v
        return default


@runtime_checkable
class ControllerState(Protocol):
    """Controller state owned by the SUT: a frozen, hashable dataclass.

    The model may read ``mode`` (e.g. hub "ONLINE"/"DEGRADED", inverter "DISCHARGING"/
    "SHUTDOWN"/"IDLE") and ``view()`` (for snapshots) and nothing else. A hub controller state
    must also have an ``nvm`` attribute: the part that survives a restart.
    """

    mode: str

    def view(self) -> dict[str, SnapshotValue]: ...


@dataclass(frozen=True, slots=True)
class HookResult:
    """What every SUT hook returns: the new controller state plus the messages it sends."""

    ctl: Any                     # the new ControllerState
    sends: tuple[Msg, ...] = ()


@runtime_checkable
class SUT(Protocol):
    """The system under test: hub-manager and inverter-controller logic.

    Hooks are PURE: same inputs, same outputs, no I/O, no clock. The model calls them and never
    reaches into SUT internals otherwise. ``now_ms`` is the model time.

    In this repo the SUT is a Python reference implementation (``firmware-ref``). In production
    this protocol becomes an adapter to real code: firmware compiled for SIL (called through
    FFI) or run as a subprocess that is fed the same hook calls over a pipe. The model, the
    checker, the simulator and every counterexample stay unchanged.
    """

    name: str                    # "firmware-ref"
    version: str                 # "v0.3.1"

    # initial controller states (the model builds the scenario from these + hooks)
    def hub_init(self, nvm: Hashable) -> ControllerState: ...
    def inv_init(self) -> ControllerState: ...

    # hub manager
    def hub_on_boot(self, nvm: Hashable, now_ms: int) -> HookResult:
        """Called when a hub restart completes. Only ``nvm`` survived the restart."""
        ...

    def hub_on_msg(self, hub: ControllerState, msg: Msg, now_ms: int) -> HookResult: ...
    def hub_on_tick(self, hub: ControllerState, now_ms: int) -> HookResult: ...

    # inverter controller
    def inv_on_cmd(self, inv: ControllerState, msg: Msg, now_ms: int) -> HookResult: ...
    def inv_on_tick(self, inv: ControllerState, now_ms: int) -> HookResult: ...


def sut_id(sut: SUT) -> str:
    """``"firmware-ref@v0.3.1"``."""
    return f"{sut.name}@{sut.version}"


def parse_sut_id(spec: str, default_name: str = "firmware-ref") -> tuple[str, str]:
    """Accept ``"firmware-ref@v0.3.1"`` or the shorthand ``"v0.3.1"``; return (name, version)."""
    if "@" in spec:
        name, version = spec.split("@", 1)
        return name, version
    return default_name, spec


# --------------------------------------------------------------------------------------------
# Model protocol
# --------------------------------------------------------------------------------------------


@runtime_checkable
class Model(Protocol[S]):
    """A behavioral model of the environment (BMS, bus, hub lifecycle, inverter plant) that
    calls a SUT for all controller decisions.

    Obtain one with ``fleetflight.models.load_model(name, sut=None, bounds=None)`` (stream 02).
    """

    name: str                    # "core-ref"
    version: str                 # model version, e.g. "1.0"
    sut: SUT
    bounds: Bounds               # the bounds this instance was built with (injection budget!)
    assumptions: list[str]       # each starts with an ASSUMPTION_TAGS tag
    invariants: list[Invariant]  # ordered by id

    def init(self) -> S:
        """The single initial state (t_ms = 0)."""
        ...

    def moves(self, state: S) -> list[Move]:
        """Enabled injections (respecting the budget kept in ``state``) followed by TICK.

        Deterministic order. TICK is always last and always present.
        """
        ...

    def apply(self, state: S, move: Move) -> tuple[S, list[TraceEvent]]:
        """Pure and deterministic. Raises ValueError if ``move`` is not enabled in ``state``."""
        ...

    def describe(self) -> dict[str, Any]:
        """A document valid against schemas/describe.schema.json. Feeds the UI Spec screen."""
        ...

    def snapshot(self, state: S) -> Snapshot:
        """Flat, display-friendly view. MUST contain ``t_ms`` and the lane keys listed in
        ``describe()["snapshot_keys"]`` (conventionally bms, bus, hub, inv, nvm), plus every
        invariant's ``timer_key``. Values are str | int | None only."""
        ...


# --------------------------------------------------------------------------------------------
# Hashing and ids
# --------------------------------------------------------------------------------------------


def canonical_json(obj: Any) -> str:
    """The one JSON encoding used for hashing: sorted keys, no whitespace, UTF-8, no NaN."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def trace_hash(steps: Sequence[tuple[Move | None, Mapping[str, SnapshotValue]]]) -> str:
    """Hash of a trace: sha256 over canonical JSON of ``[[move_json|null, snapshot], ...]``.

    ``steps[0]`` is the initial state with move ``None``. ``move_json`` is ``Move.to_json()``
    (it includes ``label``, which is derived, so this is still a pure function of the moves).
    Returns ``"sha256:<64 hex>"``. Display :func:`short_hash` of it.
    """
    payload = [[m.to_json() if m is not None else None, dict(snap)] for m, snap in steps]
    return "sha256:" + sha256_hex(payload)


def short_hash(h: str) -> str:
    """``"sha256:3f0a...(64)" -> "sha256:3f0a77c2e519"`` (first 12 hex chars)."""
    prefix, _, hexpart = h.partition(":")
    return f"{prefix}:{hexpart[:12]}" if hexpart else h[:12]


def model_hash(describe_doc: Mapping[str, Any]) -> str:
    """Identity of a model+SUT definition: hash of its describe() document minus the
    ``model.hash`` field itself and ``_fixture``. Returns ``"sha256:<12 hex>"``."""
    doc = {k: v for k, v in describe_doc.items() if k != "_fixture"}
    if isinstance(doc.get("model"), Mapping):
        doc["model"] = {k: v for k, v in doc["model"].items() if k != "hash"}
    return "sha256:" + sha256_hex(doc)[:12]


def counterexample_id(model_name: str, sut: str, invariant_id: str, moves: Sequence[Mapping[str, Any]]) -> str:
    """Stable id ``"cex-<8 hex>"`` from model, SUT id, invariant id and the counterexample's
    ``moves`` list (the JSON entries ``{"tick_index", "t_ms", "move"}``). Never a counter."""
    return "cex-" + sha256_hex([model_name, sut, invariant_id, list(moves)])[:8]


def split_assumption(text: str) -> tuple[str, str]:
    """``"ASSUMED bus latency <= 800 ms" -> ("ASSUMED", "bus latency <= 800 ms")``."""
    for tag in ASSUMPTION_TAGS:
        if text.startswith(tag + " "):
            return tag, text[len(tag) + 1 :]
    raise ValueError(f"assumption must start with one of {ASSUMPTION_TAGS}: {text!r}")
