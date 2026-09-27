"""core-ref / firmware-ref against the contract: API shape, describe() schema, snapshots, purity."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from fleetflight.core import SUT, TICK, TICK_MS, Bounds, Model, Move, model_hash, split_assumption, trace_hash
from fleetflight.models import list_models, load_model
from fleetflight.sut import list_suts, load_sut

from ._script import run_script

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ["v0.3.1", "v0.3.2", "v0.3.3"]


def _validator(name: str) -> Draft202012Validator:
    res = []
    for p in (ROOT / "schemas").glob("*.schema.json"):
        doc = json.loads(p.read_text())
        r = Resource.from_contents(doc)
        res += [(doc["$id"], r), (p.name, r)]
    schema = json.loads((ROOT / "schemas" / name).read_text())
    return Draft202012Validator(schema, registry=Registry().with_resources(res))


def test_entry_points() -> None:
    assert list_suts() == [f"firmware-ref@{v}" for v in VERSIONS]
    assert list_models() == {"core-ref": list_suts()}
    assert load_sut("v0.3.1").version == "v0.3.1"
    assert load_sut("firmware-ref@v0.3.2").version == "v0.3.2"
    assert load_model().sut.version == "v0.3.3"          # None = newest
    assert load_model(sut="firmware-ref@v0.3.1").sut.version == "v0.3.1"
    with pytest.raises(ValueError):
        load_sut("v9.9.9")
    with pytest.raises(ValueError):
        load_model("nope")
    m = load_model(sut="v0.3.1")
    assert isinstance(m, Model) and isinstance(m.sut, SUT)
    b = Bounds(max_depth=10, max_injections=1, horizon_ms=500)
    assert load_model(sut="v0.3.1", bounds=b).bounds == b


@pytest.mark.parametrize("v", VERSIONS)
def test_describe_validates(v: str) -> None:
    doc = load_model(sut=v).describe()
    errors = list(_validator("describe.schema.json").iter_errors(doc))
    assert not errors, [e.message for e in errors]
    assert "_fixture" not in doc
    assert doc["model"]["hash"] == model_hash(doc)
    assert doc["sut"]["id"] == f"firmware-ref@{v}"
    for a in doc["assumptions"]:
        split_assumption(a)
    ids = [i["id"] for i in doc["invariants"]]
    assert ids == ["I1", "I2", "I3", "I4", "I5"]
    assert all(i["formula"] for i in doc["invariants"])


def test_model_hash_differs_by_sut() -> None:
    hs = {load_model(sut=v).describe()["model"]["hash"] for v in VERSIONS}
    assert len(hs) == 3


@pytest.mark.parametrize("v", VERSIONS)
def test_snapshots_follow_contract(v: str) -> None:
    m = load_model(sut=v, bounds=Bounds(max_injections=4))
    keys = [k["key"] for k in m.describe()["snapshot_keys"]]
    timers = [i.timer_key for i in m.invariants if i.timer_key]
    script = [(100, Move("bms_fault")), (100, Move("bus_delay", (("msg", "fault@100"), ("extra_ms", 400)))),
              (200, Move("hub_restart")), (300, Move("network_loss"))]
    run = run_script(m, script, 3500)
    assert not run.skipped
    for snap in run.snaps:
        assert snap["t_ms"] % TICK_MS == 0
        for k in keys + timers:
            assert k in snap
        for val in snap.values():
            assert val is None or (type(val) in (int, str)), val


def test_moves_order_and_tick_last() -> None:
    m = load_model(sut="v0.3.1")
    s = m.init()
    for _ in range(2):
        s, _ = m.apply(s, TICK)
    mv = m.moves(s)
    assert mv[-1] == TICK and mv.count(TICK) == 1
    assert [x.name for x in mv[:3]] == ["bms_fault", "hub_restart", "network_loss"]
    assert m.moves(s) == mv                      # deterministic
    assert all(x.injected for x in mv[:-1])


def test_apply_rejects_disabled_moves() -> None:
    m = load_model(sut="v0.3.1")
    s = m.init()
    with pytest.raises(ValueError):
        m.apply(s, Move("bus_drop", (("msg", "nope@0"),)))
    s, _ = m.apply(s, Move("bms_fault"))
    with pytest.raises(ValueError):
        m.apply(s, Move("bms_fault"))           # already faulted
    with pytest.raises(ValueError):
        m.apply(s, Move("bus_delay", (("msg", "fault@0"), ("extra_ms", 999))))
    zero = load_model(sut="v0.3.1", bounds=Bounds(max_injections=0))
    assert zero.moves(zero.init()) == [TICK]
    with pytest.raises(ValueError):
        zero.apply(zero.init(), Move("hub_restart"))


def test_budget_is_enforced_in_state() -> None:
    m = load_model(sut="v0.3.1", bounds=Bounds(max_injections=2))
    s = m.init()
    s, _ = m.apply(s, Move("hub_restart"))
    s, _ = m.apply(s, Move("network_loss"))
    assert m.moves(s) == [TICK]


@pytest.mark.parametrize("v", VERSIONS)
def test_replay_is_deterministic(v: str) -> None:
    script = [(100, Move("bms_fault")), (100, Move("bus_delay", (("msg", "fault@100"), ("extra_ms", 400)))),
              (200, Move("hub_restart"))]
    hashes = set()
    for _ in range(3):
        r = run_script(load_model(sut=v), script, 2000)
        hashes.add(trace_hash([(None, r.snaps[0])] + list(zip(r.moves, r.snaps[1:]))))
    assert len(hashes) == 1


def test_states_are_hashable_and_equal_by_value() -> None:
    a, b = load_model(sut="v0.3.2"), load_model(sut="v0.3.2")
    sa, sb = a.init(), b.init()
    for _ in range(5):
        sa, _ = a.apply(sa, TICK)
        sb, _ = b.apply(sb, TICK)
    assert sa == sb and hash(sa) == hash(sb)


def test_model_only_touches_sut_through_hooks() -> None:
    """The SUT seam: the model module never imports firmware_ref internals."""
    src = (ROOT / "src/fleetflight/models/core_ref.py").read_text()
    assert "firmware_ref" not in src
    assert ".nvm." not in src and ".cmd" not in src and "last_rx_ms" not in src.replace("inv_last_rx_ms", "")


def test_single_shot_fault_option_changes_assumption() -> None:
    m = load_model(sut="v0.3.3", fault_retx_ms=None)
    assert "sent once" in m.assumptions[1]
    split_assumption(m.assumptions[1])
