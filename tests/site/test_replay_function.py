"""The hosted replay function (api/replay.py) returns what `fleetflight replay` returns and rejects bad input."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CEX_DIR = ROOT / "ui" / "public" / "data" / "cex"
spec = importlib.util.spec_from_file_location("replay_fn", ROOT / "api" / "replay.py")
fn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fn)

needs_data = pytest.mark.skipif(not (CEX_DIR / "cex-286e0592.json").is_file(), reason="site data not exported")


@needs_data
@pytest.mark.parametrize("sut, verdict, window", [("v0.3.1", "FAIL", 1050), ("v0.3.2", "FAIL", 1050), ("firmware-ref@v0.3.3", "PASS", 250)])
def test_replays_the_exported_counterexample(sut, verdict, window):
    status, doc = fn.run_replay({"cex": "cex-286e0592", "sut": sut})
    assert status == 200
    assert doc["verdict"] == verdict
    assert doc["violation_window_ms"]["duration_ms"] == window


@needs_data
def test_matches_the_exported_replay_byte_for_byte():
    exported = json.loads((ROOT / "ui/public/data/replay/cex-286e0592__v0.3.1.json").read_text())
    assert fn.run_replay({"cex": "cex-286e0592", "sut": "v0.3.1"}) == (200, exported)


@pytest.mark.parametrize("body, status", [
    ({"cex": "../../etc/passwd"}, 400),
    ({"cex": "cex-286e0592/../x"}, 400),
    ({"cex": "cex-deadbeef"}, 404),
    ({"cex": 7}, 400),
    ("cex-286e0592", 400),
])
def test_rejects_bad_input(body, status):
    assert fn.run_replay(body)[0] == status


@needs_data
def test_rejects_unknown_sut():
    status, doc = fn.run_replay({"cex": "cex-286e0592", "sut": "v9.9.9"})
    assert status == 400 and "unknown sut" in doc["error"]
