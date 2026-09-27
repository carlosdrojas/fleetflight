"""FleetFlight: pre-release verification for distributed battery firmware.

The shared contract lives in :mod:`fleetflight.core` (see CONTRACT.md). Stream entry points:

* ``fleetflight.models.load_model(name, sut=None, bounds=None) -> Model``  (stream 02)
* ``fleetflight.check.check(model, bounds=None, *, on_progress=None) -> CheckReport``  (stream 01)
* ``fleetflight.sim.simulate(...)`` / ``fleetflight.sim.replay(model, cex, ...)``  (stream 03)
"""
from fleetflight.core import (
    TICK,
    TICK_MS,
    Bounds,
    HookResult,
    Invariant,
    Model,
    Move,
    Msg,
    SUT,
    TraceEvent,
    trace_hash,
)

__version__ = "0.1.0"

__all__ = [
    "TICK",
    "TICK_MS",
    "Bounds",
    "HookResult",
    "Invariant",
    "Model",
    "Move",
    "Msg",
    "SUT",
    "TraceEvent",
    "trace_hash",
    "__version__",
]
