"""Systems under test (stream 02).

Public API (CONTRACT.md §5):
    load_sut(spec) -> fleetflight.core.SUT       # "firmware-ref@v0.3.1" or "v0.3.1"
    list_suts() -> list[str]                     # SUT ids, oldest version first
"""
from __future__ import annotations

from fleetflight.core import SUT, parse_sut_id
from fleetflight.sut.firmware_ref import VERSIONS, FirmwareRef

__all__ = ["load_sut", "list_suts", "FirmwareRef"]


def list_suts() -> list[str]:
    return [f"{FirmwareRef.name}@{v}" for v in VERSIONS]


def load_sut(spec: str | None = None) -> SUT:
    """``None`` means the newest firmware-ref version."""
    if spec is None:
        return FirmwareRef(VERSIONS[-1])
    name, version = parse_sut_id(spec)
    if name != FirmwareRef.name:
        raise ValueError(f"unknown SUT {name!r}; have {list_suts()}")
    return FirmwareRef(version)
