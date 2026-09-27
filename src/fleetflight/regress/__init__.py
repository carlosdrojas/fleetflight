"""Readable, self-contained regression tests using the current SUT by default."""
from __future__ import annotations

import os
import re
from pathlib import Path
from pprint import pformat

from fleetflight.core import Bounds
from fleetflight.sim import replay


def run_counterexample(cex, sut=None):
    from fleetflight.models import load_model

    model = load_model(cex["model"]["name"],
                       sut=sut or os.environ.get("FLEETFLIGHT_SUT"),
                       bounds=Bounds.from_json(cex["bounds"]))
    return replay(model, cex)


def generate(cex, out_dir) -> Path:
    """Embed the full counterexample and its readable injection script in pytest."""
    if not re.fullmatch(r"cex-[0-9a-f]{4,}", cex["id"]):
        raise ValueError("invalid counterexample id")
    name = cex["id"].replace("-", "_")
    metadata = {key: value for key, value in cex.items() if key != "moves"}
    source = (
        '"""Generated FleetFlight regression; FLEETFLIGHT_SUT overrides the current SUT."""\n'
        "from fleetflight.regress import run_counterexample\n\n\n"
        f"MOVES = {pformat(cex['moves'], sort_dicts=False, width=100)}\n\n"
        f"COUNTEREXAMPLE = {pformat(metadata, sort_dicts=False, width=100)}\n"
        'COUNTEREXAMPLE["moves"] = MOVES\n\n\n'
        f"def test_{name}():\n"
        "    result = run_counterexample(COUNTEREXAMPLE)\n"
        '    failures = [item for item in result["invariants"] if item["result"] == "FAIL"]\n'
        '    assert not failures, f"Invariant failures: {failures}; skipped: {result[\'skipped_moves\']}"\n'
    )
    destination = Path(out_dir) / f"test_{name}.py"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source, encoding="utf-8")
    return destination
