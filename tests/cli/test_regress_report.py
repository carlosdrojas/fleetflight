import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

from fleetflight import models
from fleetflight.regress import generate
from fleetflight.report import to_junit, to_markdown
from fleetflight.sim import replay
from tests.cli.toy_model import ToyModel, make_cex
from tests.test_contract import load


def test_generated_regression_imports_runs_and_catches_bug(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "load_model", lambda name, sut=None, bounds=None: ToyModel(sut, bounds), raising=False)
    monkeypatch.delenv("FLEETFLIGHT_SUT", raising=False)
    cex = make_cex()
    path = generate(cex, tmp_path)
    spec = importlib.util.spec_from_file_location("generated_regression", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    test = getattr(module, "test_" + cex["id"].replace("-", "_"))
    test()
    assert module.MOVES == cex["moves"]
    monkeypatch.setenv("FLEETFLIGHT_SUT", "vbug")
    with pytest.raises(AssertionError, match="Invariant failures"):
        test()


def test_generate_rejects_path_in_id(tmp_path):
    cex = dict(make_cex(), id="../../outside")
    with pytest.raises(ValueError):
        generate(cex, tmp_path)


def test_junit_multiple_reports_and_escaping():
    cex = make_cex()
    failed = replay(ToyModel("vbug"), cex)
    passed = replay(ToyModel("vfixed"), cex)
    failed["invariants"][0]["name"] = "A < B & C"
    root = ElementTree.fromstring(to_junit([failed, passed]))
    assert root.attrib == {"tests": "2", "failures": "1", "errors": "0"}
    assert len(root.findall(".//failure")) == 1
    assert root.find(".//testcase").get("name") == "I1 A < B & C"
    assert ElementTree.fromstring(to_junit([])).get("tests") == "0"


def test_markdown_labels_fixture_and_uses_supplied_values():
    report = load("check-report.json")
    output = to_markdown(report)
    assert "MOCK DATA" in output
    assert f"{report['stats']['states']:,} states" in output
    assert all(assumption in output for assumption in report["assumptions"])
    report.pop("_fixture")
    assert "MOCK DATA" not in to_markdown(report)


def test_pytest_plugin_restores_environment(monkeypatch):
    from fleetflight.regress.plugin import pytest_configure, pytest_unconfigure

    class Config:
        def addinivalue_line(self, name, value):
            assert name == "markers"

        def getoption(self, name):
            return "vfixed"

    monkeypatch.setenv("FLEETFLIGHT_SUT", "vbug")
    config = Config()
    pytest_configure(config)
    assert os.environ["FLEETFLIGHT_SUT"] == "vfixed"
    pytest_unconfigure(config)
    assert os.environ["FLEETFLIGHT_SUT"] == "vbug"


@pytest.mark.parametrize("version,exit_code", [("vfixed", 0), ("vbug", 1)])
def test_generated_file_runs_under_pytest_with_plugin(tmp_path, version, exit_code):
    path = generate(make_cex(), tmp_path)
    root = Path(__file__).resolve().parents[2]
    script = (
        "import sys, pytest, fleetflight.models\n"
        "from tests.cli.toy_model import ToyModel\n"
        "fleetflight.models.load_model = lambda name, sut=None, bounds=None: ToyModel(sut, bounds)\n"
        "raise SystemExit(pytest.main(sys.argv[1:]))\n"
    )
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join([str(root / "src"), str(root)]))
    result = subprocess.run(
        [sys.executable, "-c", script, "-q", "-p", "fleetflight.regress.plugin",
         "--fleetflight-sut", version, str(path)],
        cwd=tmp_path, env=environment, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == exit_code, result.stdout + result.stderr
