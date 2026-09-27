"""Validate the evidence needed by demo/CI scripts; never manufacture results."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path, kind: str) -> dict:
    doc = json.loads(path.read_text())
    require(isinstance(doc, dict), f"{path}: expected a JSON object")
    require(doc.get("schema") == f"fleetflight/{kind}@1", f"{path}: wrong schema")
    require("_fixture" not in doc, f"{path}: fixtures are not real verification evidence")
    return doc


def validate_results(doc: dict, expected: str) -> None:
    require(doc["verdict"] == expected, f"Expected verdict {expected}")
    rows = doc["invariants"]
    require(bool(rows), "No invariants checked")
    require(all(row["result"] in ("PASS", "FAIL") for row in rows), "Unknown invariant result")
    if expected == "PASS":
        require(all(row["result"] == "PASS" for row in rows), "An invariant failed")
    else:
        require(any(row["id"] == "I1" and row["result"] == "FAIL" for row in rows),
                "Expected I1 to fail, not merely another invariant")


def validate_check(path: Path, expected: str) -> dict:
    doc = load(path, "check-report")
    validate_results(doc, expected)
    require(doc["stats"]["complete"] is True, "Search incomplete; cannot claim all orderings checked")
    return doc


def validate_cex(path: Path) -> dict:
    doc = load(path, "counterexample")
    require(re.fullmatch(r"cex-[0-9a-f]{8}", doc["id"]) is not None, "Invalid content-hash counterexample id")
    require(doc["trace"] and doc["moves"], "Counterexample has no trace or injections")
    return doc


def select(path: Path) -> Path:
    doc = validate_check(path, "FAIL")
    row = next(row for row in doc["invariants"] if row["id"] == "I1")
    cid = row["counterexample"]
    require(isinstance(cid, str) and re.fullmatch(r"cex-[0-9a-f]{8}", cid) is not None,
            "I1 has no valid counterexample id")
    cex_path = path.parent / f"{cid}.json"
    cex = validate_cex(cex_path)
    require(cex["id"] == cid and cex["invariant"]["id"] == "I1", "Report/counterexample mismatch")
    require(cex["sut"] == doc["sut"] and cex["bounds"] == doc["bounds"], "Counterexample SUT/bounds mismatch")
    return cex_path.resolve()


def validate_replay(path: Path, expected: str, same_sut: bool = False) -> None:
    doc = load(path, "replay-result")
    validate_results(doc, expected)
    if same_sut:
        require(doc["same_sut"] is True, "Original replay used a different SUT")
        require(doc["hash_match"] is True and doc["trace_hash"] == doc["expected_trace_hash"],
                "Original replay did not reproduce the checker hash")
        require(doc["compared_steps"] > 0 and doc["matched_steps"] == doc["compared_steps"],
                "Original replay has mismatched steps")
        require(doc["first_divergence"] is None and not doc["skipped_moves"],
                "Original replay diverged or skipped an injection")
    elif doc["skipped_moves"]:
        print(f"Replay reports {len(doc['skipped_moves'])} skipped injection(s); inspect {path}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("select", "check", "replay", "cex"))
    parser.add_argument("path", type=Path)
    parser.add_argument("expected", nargs="?", choices=("PASS", "FAIL"), default="PASS")
    parser.add_argument("--same-sut", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "select":
            print(select(args.path))
        elif args.action == "check":
            validate_check(args.path, args.expected)
        elif args.action == "replay":
            validate_replay(args.path, args.expected, args.same_sut)
        else:
            validate_cex(args.path)
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        print(f"FleetFlight evidence error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
