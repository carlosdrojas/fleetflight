"""Behavioral models (stream 02).

Public API (CONTRACT.md §5):
    load_model(name="core-ref", sut=None, bounds=None) -> fleetflight.core.Model
    list_models() -> dict[str, list[str]]         # model name -> available SUT ids
"""
from __future__ import annotations

from typing import Any

from fleetflight.core import Bounds
from fleetflight.models.core_ref import DEFAULT_BOUNDS, CoreRef

__all__ = ["load_model", "list_models", "CoreRef", "DEFAULT_BOUNDS"]


def list_models() -> dict[str, list[str]]:
    from fleetflight.sut import list_suts

    return {"core-ref": list_suts()}


def load_model(name: str = "core-ref", sut: Any = None, bounds: Bounds | None = None, **options: Any) -> CoreRef:
    """``sut`` is a spec string ("v0.3.1", "firmware-ref@v0.3.1"), a SUT object, or None (newest).

    Extra keyword ``options`` are model knobs used by tests (e.g. ``fault_retx_ms=None``)."""
    from fleetflight.sut import load_sut

    if name != "core-ref":
        raise ValueError(f"unknown model {name!r}; have {sorted(list_models())}")
    if sut is None or isinstance(sut, str):
        sut = load_sut(sut)
    return CoreRef(sut, bounds, **options)
