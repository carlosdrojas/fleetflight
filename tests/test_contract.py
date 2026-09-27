"""Foundation tests: fixtures validate against schemas, and core helpers keep their promises."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from fleetflight.core import (
    TICK,
    TICK_MS,
    Bounds,
    Move,
    counterexample_id,
    model_hash,
    parse_sut_id,
    short_hash,
    split_assumption,
    trace_hash,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "fixtures"

FIXTURE_SCHEMA = {
    "describe.json": "describe.schema.json",
    "check-report.json": "check-report.schema.json",
    "cex-0017.json": "counterexample.schema.json",
    "replay-v031.json": "replay-result.schema.json",
    "replay-v033.json": "replay-result.schema.json",
    "runs.json": "run-list.schema.json",
}


def _registry() -> Registry:
    resources = []
    for p in SCHEMAS.glob("*.schema.json"):
        doc = json.loads(p.read_text())
        res = Resource.from_contents(doc)
        resources += [(doc["$id"], res), (p.name, res)]
    return Registry().with_resources(resources)


def validator(schema_file: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / schema_file).read_text())
    return Draft202012Validator(schema, registry=_registry())


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.parametrize("schema_file", sorted(p.name for p in SCHEMAS.glob("*.schema.json")))
def test_schemas_are_valid_draft_2020_12(schema_file: str) -> None:
    Draft202012Validator.check_schema(json.loads((SCHEMAS / schema_file).read_text()))


def test_every_fixture_has_a_schema() -> None:
    assert sorted(p.name for p in FIXTURES.glob("*.json")) == sorted(FIXTURE_SCHEMA)


@pytest.mark.parametrize("fixture,schema_file", sorted(FIXTURE_SCHEMA.items()))
def test_fixture_validates(fixture: str, schema_file: str) -> None:
    doc = load(fixture)
    errors = sorted(validator(schema_file).iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)
    assert next(iter(doc)) == "_fixture" and doc["_fixture"] is True


def test_schema_rejects_bad_documents() -> None:
    cex = load("cex-0017.json")
    v = validator("counterexample.schema.json")
    bad = dict(cex, violated_at_ms=725)  # not a multiple of TICK_MS
    assert not v.is_valid(bad)
    bad = dict(cex, assumptions=["latency is fine"])  # untagged assumption
    assert not v.is_valid(bad)
    bad = json.loads(json.dumps(cex))
    bad["trace"][0]["snapshot"]["x"] = 1.5  # floats not allowed in snapshots
    assert not v.is_valid(bad)


def test_counterexample_is_self_consistent() -> None:
    cex = load("cex-0017.json")
    trace = cex["trace"]
    assert trace[0]["move"] is None
    steps = [(Move.from_json(s["move"]) if s["move"] else None, s["snapshot"]) for s in trace]
    assert trace_hash(steps) == cex["trace_hash"]
    ticks = sum(1 for m, _ in steps[1:] if m == TICK)
    assert ticks == cex["ticks"] and cex["violated_at_ms"] == ticks * TICK_MS
    assert cex["search"]["depth"] == len(trace) - 1
    # moves + ticks reproduce the full move sequence (the replay rule in CONTRACT.md)
    rebuilt: list[Move] = []
    for k in range(cex["ticks"] + 1):
        rebuilt += [Move.from_json(m["move"]) for m in cex["moves"] if m["tick_index"] == k]
        if k < cex["ticks"]:
            rebuilt.append(TICK)
    assert rebuilt == [m for m, _ in steps[1:]]


def test_replay_fixtures_tell_the_story() -> None:
    cex = load("cex-0017.json")
    r1, r3 = load("replay-v031.json"), load("replay-v033.json")
    assert r1["hash_match"] and r1["trace_hash"] == cex["trace_hash"] and r1["verdict"] == "FAIL"
    assert not r3["hash_match"] and r3["verdict"] == "PASS" and r3["first_divergence"] is not None
    assert r3["violation_window_ms"]["over_budget_ms"] < 0 < r1["violation_window_ms"]["over_budget_ms"]


def test_move_json_round_trip_and_label() -> None:
    m = Move("bus_delay", (("msg", "fault#1"), ("extra_ms", 400)))
    assert Move.from_json(json.loads(json.dumps(m.to_json()))) == m
    assert m.label == "bus_delay(msg=fault#1, extra_ms=400)" and m.arg("extra_ms") == 400
    assert TICK.label == "tick" and not TICK.injected
    assert hash(m) == hash(Move.from_json(m.to_json()))


def test_trace_hash_is_order_and_value_sensitive() -> None:
    a = [(None, {"t_ms": 0, "x": "A"}), (TICK, {"t_ms": 50, "x": "A"})]
    b = [(None, {"x": "A", "t_ms": 0}), (TICK, {"x": "A", "t_ms": 50})]  # key order irrelevant
    c = [(None, {"t_ms": 0, "x": "A"}), (TICK, {"t_ms": 50, "x": "B"})]
    assert trace_hash(a) == trace_hash(b) != trace_hash(c)
    assert trace_hash(a).startswith("sha256:") and len(trace_hash(a)) == 7 + 64
    assert short_hash(trace_hash(a)) == trace_hash(a)[:19]


def test_ids_and_helpers() -> None:
    moves = [{"tick_index": 2, "t_ms": 100, "move": Move("bms_fault").to_json()}]
    cid = counterexample_id("core-ref", "firmware-ref@v0.3.1", "I1", moves)
    assert cid == counterexample_id("core-ref", "firmware-ref@v0.3.1", "I1", moves)
    assert cid != counterexample_id("core-ref", "firmware-ref@v0.3.2", "I1", moves)
    assert cid.startswith("cex-") and len(cid) == 12
    assert parse_sut_id("v0.3.1") == ("firmware-ref", "v0.3.1")
    assert parse_sut_id("other@v2") == ("other", "v2")
    assert split_assumption("OUT OF SCOPE hardware interlocks") == ("OUT OF SCOPE", "hardware interlocks")
    with pytest.raises(ValueError):
        split_assumption("latency is fine")
    with pytest.raises(ValueError):
        Bounds(horizon_ms=4025)
    desc = load("describe.json")
    assert model_hash(desc) == desc["model"]["hash"]
