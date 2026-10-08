"""Shared plumbing for the checker's toy models: a stub SUT and the Model boilerplate.

Toy models are tiny, hand-analysable systems whose answers we know in advance. They implement
the contract ``Model`` protocol directly, so the checker is tested on exactly the surface it
uses against core-ref.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fleetflight.check import CheckReport
from fleetflight.core import SCHEMA_DESCRIBE, Bounds, Invariant, Move, TraceEvent

ROOT = Path(__file__).resolve().parents[2]


class ToySUT:
    """The toys have no controller code; this only fills the ``model.sut`` slot."""

    name = "toy"
    version = "v1"


class ToyModel:
    """Boilerplate shared by the toys. Subclasses set ``name``, ``invariants``, ``init``,
    ``moves``, ``apply`` and ``snapshot``."""

    version = "1.0"
    assumptions = ["ASSUMED toy model for checker tests"]
    invariants: list[Invariant] = []

    def __init__(self, bounds: Bounds) -> None:
        self.bounds = bounds
        self.sut = ToySUT()

    def describe(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_DESCRIBE,
            "model": {"name": self.name, "version": self.version},
            "sut": {"name": self.sut.name, "version": self.sut.version},
            "bounds": self.bounds.to_json(),
            "invariants": [inv.to_json() for inv in self.invariants],
        }

    def _require(self, state: Any, move: Move) -> None:
        if move not in self.moves(state):
            raise ValueError(f"move {move.label} not enabled")


def ev(t_ms: int, name: str, detail: str = "", injected: bool = False) -> list[TraceEvent]:
    return [TraceEvent(t_ms, name, detail, injected)]


# -------------------------------------------------------------------------------------------
# Schema validation of checker output
# -------------------------------------------------------------------------------------------


def _validator(schema_file: str):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    schemas = ROOT / "schemas"
    resources = []
    for p in schemas.glob("*.schema.json"):
        doc = json.loads(p.read_text())
        res = Resource.from_contents(doc)
        resources += [(doc["$id"], res), (p.name, res)]
    schema = json.loads((schemas / schema_file).read_text())
    return Draft202012Validator(schema, registry=Registry().with_resources(resources))


def schema_errors(doc: dict[str, Any], schema_file: str) -> list[str]:
    errors = sorted(_validator(schema_file).iter_errors(doc), key=lambda e: list(e.path))
    return [f"{list(e.path)}: {e.message}" for e in errors]


def assert_report_valid(report: CheckReport) -> None:
    errs = schema_errors(report.to_json(), "check-report.schema.json")
    assert not errs, "\n".join(errs)
    for cex in report.counterexamples.values():
        errs = schema_errors(cex, "counterexample.schema.json")
        assert not errs, "\n".join(errs)
    assert "_fixture" not in report.to_json()


def by_id(report: CheckReport) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in report.to_json()["invariants"]}


def cex_for(report: CheckReport, inv_id: str) -> dict[str, Any]:
    return report.counterexamples[by_id(report)[inv_id]["counterexample"]]
