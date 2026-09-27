"""Bounded explicit-state model checker (stream 01).

Public API (CONTRACT.md §5):
    check(model, bounds=None, *, on_progress=None) -> CheckReport
    CheckReport.to_json() -> dict                 # schemas/check-report.schema.json
    CheckReport.counterexamples -> dict[str, dict]  # id -> schemas/counterexample.schema.json
    write_report(report, out_dir) -> list[pathlib.Path]
"""
from fleetflight.check.bfs import CheckReport, check, write_report

__all__ = ["CheckReport", "check", "write_report"]
