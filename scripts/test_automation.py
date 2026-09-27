"""Script safety tests. Synthetic data below is test input, never demo evidence."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("artifacts", SCRIPTS / "artifacts.py")
artifacts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifacts)


def write(tmp_path, doc):
    path = tmp_path / "result.json"
    path.write_text(json.dumps(doc))
    return path


def test_incomplete_search_cannot_pass(tmp_path):
    path = write(tmp_path, {"schema": "fleetflight/check-report@1", "verdict": "PASS",
                           "invariants": [{"id": "I1", "result": "PASS"}], "stats": {"complete": False}})
    with pytest.raises(ValueError, match="incomplete"):
        artifacts.validate_check(path, "PASS")


def test_fixture_cannot_be_demo_evidence(tmp_path):
    path = write(tmp_path, {"schema": "fleetflight/counterexample@1", "_fixture": True})
    with pytest.raises(ValueError, match="fixtures"):
        artifacts.validate_cex(path)


def test_wrong_invariant_cannot_stand_in_for_i1():
    with pytest.raises(ValueError, match="Expected I1"):
        artifacts.validate_results({"verdict": "FAIL", "invariants": [
            {"id": "I1", "result": "PASS"}, {"id": "I2", "result": "FAIL"}]}, "FAIL")


def test_replay_failure_does_not_hide_hash_mismatch(tmp_path):
    path = write(tmp_path, {"schema": "fleetflight/replay-result@1", "verdict": "FAIL",
                           "invariants": [{"id": "I1", "result": "FAIL"}],
                           "same_sut": True, "hash_match": False})
    with pytest.raises(ValueError, match="hash"):
        artifacts.validate_replay(path, "FAIL", same_sut=True)


@pytest.mark.parametrize("actual,expected", [(0, 2), (1, 0), (2, 2), (127, 2)])
def test_expected_violation_does_not_swallow_errors(actual, expected):
    result = subprocess.run(["bash", "-c", 'source "$1"; expect_exit 1 bash -c "exit $2"',
                             "test", str(SCRIPTS / "common.sh"), str(actual)], capture_output=True, text=True)
    assert result.returncode == expected


def test_select_uses_report_i1_not_first_file(tmp_path):
    sut = {"id": "firmware-ref@v0.3.1"}
    bounds = {"max_depth": 120, "max_injections": 3, "horizon_ms": 4000}
    cid = "cex-abcdef01"  # Synthetic identifier, not a measured counterexample.
    (tmp_path / f"{cid}.json").write_text(json.dumps({
        "schema": "fleetflight/counterexample@1", "id": cid,
        "invariant": {"id": "I1"}, "sut": sut, "bounds": bounds,
        "trace": [{}], "moves": [{}]}))
    (tmp_path / "cex-00000000.json").write_text("not a real counterexample")
    path = write(tmp_path, {"schema": "fleetflight/check-report@1", "verdict": "FAIL",
                           "sut": sut, "bounds": bounds, "stats": {"complete": True},
                           "invariants": [{"id": "I1", "result": "FAIL", "counterexample": cid}]})
    assert artifacts.select(path) == tmp_path / f"{cid}.json"
