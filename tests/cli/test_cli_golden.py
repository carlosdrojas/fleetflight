"""Stable terminal transcripts from an executed toy trace and labeled checker doubles."""
import json
from io import StringIO
from types import SimpleNamespace

import pytest

from fleetflight import cli
from fleetflight.core import Bounds
from tests.cli.toy_model import ToyModel, make_cex


@pytest.fixture
def terminal(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(cli, "console", cli.Console(
        file=stream, width=120, force_terminal=False, color_system=None,
        markup=False, highlight=False,
    ))
    return stream


def transcript(stream):
    return "\n".join(line.rstrip() for line in stream.getvalue().splitlines()) + "\n"


@pytest.mark.parametrize("by_id", [False, True], ids=["path", "counterexample-id"])
def test_explain_golden(tmp_path, terminal, by_id):
    cex = make_cex()
    path = tmp_path / f"{cex['id']}.json"
    path.write_text(json.dumps(cex), encoding="utf-8")
    source = cex["id"] if by_id else str(path)

    assert cli.main(["explain", source, "--out", str(tmp_path)]) == 1
    assert transcript(terminal) == (
        "MOCK DATA — fixture values, not verification results.\n"
        "I1 STOP_BOUNDED violated at t=100 ms\n"
        "Duration 100 ms · budget 50 ms\n"
        " Step  t(ms)  Move / events  inv   fault_since_ms  injections  Violations\n"
        " 0     0      init           STOP  None            0\n"
        " 1     0      bms_fault*     RUN   0               1\n"
        "              bms_fault\n"
        " 2     50     tick           RUN   0               1\n"
        "              tick\n"
        " 3     100    tick           RUN   0               1           I1\n"
        "              tick\n"
        "* = injected\n"
    )


@pytest.mark.parametrize("verdict", ["FAIL", "PASS"])
def test_check_golden(monkeypatch, terminal, verdict):
    cex = make_cex()
    sut = "vbug" if verdict == "FAIL" else "vfixed"
    doc = {
        "_fixture": True,
        "stats": {"states": 0, "transitions": 0, "wall_s": 0, "complete": True},
        "invariants": [{
            **ToyModel(sut).invariants[0].to_json(),
            "result": verdict,
            "counterexample": cex["id"] if verdict == "FAIL" else None,
        }],
        "verdict": verdict,
    }
    report = SimpleNamespace(to_json=lambda: doc)

    def load_model(name, sut, bounds):
        assert name == "toy"
        return ToyModel(sut, bounds)

    def check_model(model, bounds, on_progress):
        assert bounds is model.bounds
        assert bounds == Bounds(max_depth=4, max_injections=1, horizon_ms=100)
        on_progress(doc["stats"])
        return report

    def write_report(actual_report, out_dir):
        assert actual_report is report
        paths = [out_dir / "check-toy-golden.json"]
        if verdict == "FAIL":
            paths.append(out_dir / f"{cex['id']}.json")
        return paths

    monkeypatch.setattr(cli, "load_model", load_model)
    monkeypatch.setattr(cli, "check_model", check_model)
    monkeypatch.setattr(cli, "write_report", write_report)

    assert cli.main([
        "check", "--model", "toy", "--sut", sut, "--depth", "4",
        "--injections", "1", "--horizon-ms", "100",
    ]) == int(verdict == "FAIL")

    expected = (
        "toy · depth ≤ 4 moves · horizon 100 ms · ≤ 1 injections · BFS\n"
        "ASSUMED toy shutdown bound is 50 ms\n"
        "MOCK DATA — fixture values, not verification results.\n"
        "0 states · 0 transitions · 0.000 s · complete: True\n"
        " Invariant        Result  Detail\n"
    )
    if verdict == "FAIL":
        expected += (
            " I1 STOP_BOUNDED  FAIL    <cex-id>\n"
            "Wrote out/check-toy-golden.json\n"
            "Wrote out/<cex-id>.json\n"
        )
    else:
        expected += " I1 STOP_BOUNDED  PASS\nWrote out/check-toy-golden.json\n"
    assert transcript(terminal).replace(cex["id"], "<cex-id>") == expected
