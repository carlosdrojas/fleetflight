"""Regenerate the hand-written fixtures in this directory.

    .venv/bin/python fixtures/make_fixtures.py

These are FIXTURES, not output: every file carries "_fixture": true, the trace is scripted by
hand below (there is no model here), and every number is a PLACEHOLDER. They exist so the UI and
CLI streams can build before the real checker and model exist. They are generated rather than
typed so that trace hashes, step indices and windows are internally consistent.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fleetflight.core import (
    SCHEMA_CHECK_REPORT,
    SCHEMA_COUNTEREXAMPLE,
    SCHEMA_DESCRIBE,
    SCHEMA_REPLAY_RESULT,
    SCHEMA_RUN_LIST,
    TICK,
    TICK_MS,
    Move,
    TraceEvent,
    model_hash,
    trace_hash,
)

HERE = Path(__file__).parent
CEX_ID = "cex-0017"  # fixture id; real ids are counterexample_id(...) = "cex-<8 hex>"
HORIZON_MS = 2000

INVARIANTS = [
    {"id": "I1", "name": "FAULT_SHUTDOWN_BOUNDED",
     "description": "If the BMS is FAULTED, the inverter stops discharging within 500 ms.",
     "formula": "G( bms=FAULTED ∧ inv=DISCHARGING → (t − i1_since_ms) ≤ 500 )",
     "bound_ms": 500, "timer_key": "i1_since_ms"},
    {"id": "I2", "name": "NO_HIGH_POWER_WHEN_UNKNOWN",
     "description": "While BMS state is UNKNOWN the inverter never runs above 1 kW.",
     "formula": "G( bms=UNKNOWN → inv_watts ≤ 1000 )", "bound_ms": None, "timer_key": None},
    {"id": "I3", "name": "NO_RESURRECTED_COMMANDS",
     "description": "The inverter never executes a command after its expiry.",
     "formula": "G( inv_cmd ≠ ∅ → inv_cmd.expires_ms > t )", "bound_ms": None, "timer_key": None},
    {"id": "I4", "name": "IDEMPOTENT_COMMANDS",
     "description": "A duplicated command sequence number never causes a second physical action.",
     "formula": "G( applied_count(seq) ≤ 1 )", "bound_ms": None, "timer_key": None},
    {"id": "I5", "name": "COMMS_LOSS_SAFE_FALLBACK",
     "description": "After losing hub commands the inverter reaches IDLE or SHUTDOWN within 1.5 s.",
     "formula": "G( no_hub_cmd → (t − i5_since_ms) ≤ 1500 )", "bound_ms": 1500, "timer_key": "i5_since_ms"},
]
I1 = INVARIANTS[0]

ASSUMPTIONS = [
    "ASSUMED bus latency <= 800 ms; messages may be delayed, dropped, duplicated or reordered",
    "ASSUMED BMS FAULT message is edge-triggered; status heartbeat every 2000 ms",
    "ASSUMED inverter holds last setpoint 1000 ms without a hub command, then IDLE",
    "ASSUMED hub boot takes 400 ms and clears its RX buffer",
    "ASSUMED shutdown budget 500 ms",
    "OUT OF SCOPE hardware interlocks (contactors, hardwired BMS trip)",
]
BOUNDS = {"max_depth": 60, "max_injections": 3, "horizon_ms": 3000}
SUT_VERSIONS = ["firmware-ref@v0.3.1", "firmware-ref@v0.3.2", "firmware-ref@v0.3.3"]


def sut_ref(version: str) -> dict[str, str]:
    return {"id": f"firmware-ref@{version}", "name": "firmware-ref", "version": version}


def describe() -> dict[str, Any]:
    doc: dict[str, Any] = {
        "_fixture": True,
        "schema": SCHEMA_DESCRIBE,
        "model": {"name": "core-ref", "version": "0.0-fixture", "hash": "sha256:000000000000"},
        "sut": sut_ref("v0.3.1"),
        "sut_versions": SUT_VERSIONS,
        "tick_ms": TICK_MS,
        "components": [
            {"id": "bms", "name": "BMS", "owner": "model", "states": ["HEALTHY", "FAULTED", "UNKNOWN"],
             "description": "Battery management system. Sends FAULT once on the edge, STATUS every 2 s."},
            {"id": "bus", "name": "Bus", "owner": "model", "states": ["in-flight messages"],
             "description": "Carries messages with bounded latency; the adversary may delay, drop or duplicate."},
            {"id": "hub", "name": "Hub", "owner": "sut", "states": ["ONLINE", "RESTARTING", "DEGRADED"],
             "description": "Hub manager (system under test). Restart clears RX and keeps NVM."},
            {"id": "inv", "name": "Inverter", "owner": "sut", "states": ["IDLE", "CHARGING", "DISCHARGING", "SHUTDOWN"],
             "description": "Inverter controller (system under test)."},
        ],
        "injectables": [
            {"name": "bms_fault", "description": "BMS enters FAULTED (e.g. overtemp).", "params": []},
            {"name": "hub_restart", "description": "Hub reboots; RX buffer lost, NVM kept.", "params": []},
            {"name": "bus_delay", "description": "Push one in-flight message later, within the latency bound.",
             "params": [{"name": "msg", "values": "any in-flight message id"},
                        {"name": "extra_ms", "values": list(range(100, 801, 100))}]},
            {"name": "bus_drop", "description": "Lose one in-flight message.",
             "params": [{"name": "msg", "values": "any in-flight message id"}]},
            {"name": "bus_dup", "description": "Duplicate one in-flight message.",
             "params": [{"name": "msg", "values": "any in-flight message id"}]},
        ],
        "invariants": INVARIANTS,
        "assumptions": ASSUMPTIONS,
        "bounds": BOUNDS,
        "constants": {"LATENCY_MAX_MS": 800, "HUB_BOOT_MS": 400, "SHUTDOWN_BUDGET_MS": 500, "INV_HOLD_MS": 1000},
        "snapshot_keys": [
            {"key": "bms", "label": "BMS", "lane": True},
            {"key": "bus", "label": "Bus", "lane": True},
            {"key": "hub", "label": "Hub", "lane": True},
            {"key": "inv", "label": "Inverter", "lane": True},
            {"key": "nvm", "label": "Hub NVM", "lane": False},
            {"key": "i1_since_ms", "label": "I1 timer", "lane": False},
            {"key": "i5_since_ms", "label": "I5 timer", "lane": False},
            {"key": "injections_left", "label": "Injections left", "lane": False},
        ],
    }
    doc["model"]["hash"] = model_hash(doc)
    return doc


# ---- a hand-scripted trace (NOT a model): each entry is (move, snapshot changes, events) -----

def scripted_run(version: str) -> list[tuple[Move | None, dict[str, Any], list[TraceEvent]]]:
    """Placeholder story. v0.3.1 resends the NVM command; v0.3.3 has an inverter hub-loss
    timeout. Numbers are invented for the fixture only."""
    snap: dict[str, Any] = {
        "t_ms": 0, "bms": "HEALTHY", "bus": "", "hub": "ONLINE", "inv": "DISCHARGING 5000W seq41",
        "nvm": "seq41 DISCHARGE 5000W", "i1_since_ms": None, "i5_since_ms": None, "injections_left": 3,
    }
    steps: list[tuple[Move | None, dict[str, Any], list[TraceEvent]]] = [(None, dict(snap), [])]
    fault = Move("bms_fault", (), True)
    delay = Move("bus_delay", (("msg", "fault#1"), ("extra_ms", 400)), True)
    restart = Move("hub_restart", (), True)
    script = {2: [fault, delay], 4: [restart]}  # tick_index -> injections
    last_cmd_ms = 0
    tick_index = 0
    while True:
        for mv in script.get(tick_index, []):
            t = snap["t_ms"]
            ev = [TraceEvent(t, mv.name, mv.label, injected=True)]
            if mv.name == "bms_fault":
                snap.update(bms="FAULTED", bus=f"fault#1 bms→hub @{t}", i1_since_ms=t)
                ev.append(TraceEvent(t, "send", "fault#1 bms→hub"))
            elif mv.name == "bus_delay":
                snap.update(bus="fault#1 bms→hub @500")
            elif mv.name == "hub_restart":
                snap.update(hub="RESTARTING", bus="")
                ev.append(TraceEvent(t, "drop", "fault#1 (hub RX buffer cleared)"))
            snap["injections_left"] -= 1
            steps.append((mv, dict(snap), ev))
        if snap["t_ms"] >= HORIZON_MS:
            break
        t = snap["t_ms"] + TICK_MS
        snap["t_ms"] = t
        ev = []
        if version == "v0.3.3" and t == 400:
            snap.update(inv="SHUTDOWN", i1_since_ms=None)
            ev.append(TraceEvent(t, "inv_timeout", "no hub heartbeat for 200 ms → SHUTDOWN"))
        if t == 600:
            if version == "v0.3.1":
                snap.update(hub="ONLINE", bus="resume#2 hub→inv @650")
                ev.append(TraceEvent(t, "hub_boot", "restores seq41 from NVM, sends resume#2"))
            else:
                snap.update(hub="DEGRADED", bus="stop#2 hub→inv @650", nvm="")
                ev.append(TraceEvent(t, "hub_boot", "boots DEGRADED, sends stop#2"))
        if t == 650:
            snap["bus"] = ""
            if version == "v0.3.1":
                last_cmd_ms = t
                ev.append(TraceEvent(t, "deliver", "resume#2 → inv (watchdog refreshed)"))
            else:
                snap.update(inv="SHUTDOWN", i1_since_ms=None)
                ev.append(TraceEvent(t, "deliver", "stop#2 → inv"))
        if version == "v0.3.1" and snap["inv"].startswith("DISCHARGING") and t - last_cmd_ms >= 1000:
            snap.update(inv="IDLE", i1_since_ms=None)
            ev.append(TraceEvent(t, "inv_hold_expired", "no command for 1000 ms → IDLE"))
        steps.append((TICK, dict(snap), ev))
        tick_index += 1
    return steps


def violates_i1(snap: dict[str, Any]) -> bool:
    return snap["i1_since_ms"] is not None and snap["t_ms"] - snap["i1_since_ms"] > I1["bound_ms"]


def step_json(i: int, mv: Move | None, snap: dict[str, Any], ev: list[TraceEvent]) -> dict[str, Any]:
    d: dict[str, Any] = {"step": i, "t_ms": snap["t_ms"], "move": mv.to_json() if mv else None,
                         "snapshot": snap, "events": [e.to_json() for e in ev]}
    if violates_i1(snap):
        d["violations"] = ["I1"]
    return d


def counterexample(desc: dict[str, Any]) -> dict[str, Any]:
    run = scripted_run("v0.3.1")
    end = next(i for i, (_, s, _) in enumerate(run) if violates_i1(s))
    path = run[: end + 1]
    moves = []
    ticks = 0
    for mv, snap, _ in path[1:]:
        if mv == TICK:
            ticks += 1
        else:
            moves.append({"tick_index": ticks, "t_ms": ticks * TICK_MS, "move": mv.to_json()})
    last = path[-1][1]
    return {
        "_fixture": True,
        "schema": SCHEMA_COUNTEREXAMPLE,
        "id": CEX_ID,
        "model": desc["model"],
        "sut": sut_ref("v0.3.1"),
        "invariant": I1,
        "violated_at_ms": last["t_ms"],
        "violation_duration_ms": last["t_ms"] - last["i1_since_ms"],
        "bounds": BOUNDS,
        "search": {"strategy": "bfs", "minimal": True, "depth": len(path) - 1,
                   "states_explored": 12345, "transitions": 67890, "wall_s": 1.5},
        "assumptions": ASSUMPTIONS,
        "trace": [step_json(i, mv, s, ev) for i, (mv, s, ev) in enumerate(path)],
        "moves": moves,
        "ticks": ticks,
        "trace_hash": trace_hash([(mv, s) for mv, s, _ in path]),
        "explanation": "FIXTURE. Fault message lost across a hub restart; hub resumes the NVM command.",
        "replay": {"command": f"fleetflight replay --counterexample {CEX_ID}"},
    }


def windows(run: list[tuple[Move | None, dict[str, Any], list[TraceEvent]]], key: str) -> list[dict[str, Any]]:
    out, cur = [], None
    for _, s, _ in run:
        v = s[key]
        if v is not None and cur is None:
            cur = v
        elif v is None and cur is not None:
            out.append({"start_ms": cur, "end_ms": s["t_ms"], "duration_ms": s["t_ms"] - cur, "open": False})
            cur = None
    if cur is not None:
        t = run[-1][1]["t_ms"]
        out.append({"start_ms": cur, "end_ms": None, "duration_ms": t - cur, "open": True})
    return out


def replay(version: str, cex: dict[str, Any], desc: dict[str, Any]) -> dict[str, Any]:
    run = scripted_run(version)
    n = min(len(run), len(cex["trace"]))
    steps = []
    for i, (mv, s, ev) in enumerate(run):
        d = step_json(i, mv, s, ev)
        if i < n:
            exp = cex["trace"][i]
            diff = sorted(k for k in set(s) | set(exp["snapshot"]) if s.get(k) != exp["snapshot"].get(k))
            d["match"] = not diff and d["move"] == exp["move"]
            d["diff"] = diff
        else:
            d["match"], d["diff"] = None, []
        steps.append(d)
    matched = sum(1 for d in steps[:n] if d["match"])
    first_div = next((d["step"] for d in steps[:n] if not d["match"]), None)
    prefix = trace_hash([(mv, s) for mv, s, _ in run[:n]])
    i1_first = next((s["t_ms"] for _, s, _ in run if violates_i1(s)), None)
    w1 = max(windows(run, "i1_since_ms"), key=lambda w: w["duration_ms"], default=None)
    invs = []
    for inv in INVARIANTS:
        if inv["id"] == "I1":
            invs.append({"id": "I1", "name": inv["name"], "result": "FAIL" if i1_first is not None else "PASS",
                         "first_violation_ms": i1_first, "max_window": w1})
        else:
            invs.append({"id": inv["id"], "name": inv["name"], "result": "PASS",
                         "first_violation_ms": None, "max_window": None})
    return {
        "_fixture": True,
        "schema": SCHEMA_REPLAY_RESULT,
        "counterexample": cex["id"],
        "model": desc["model"],
        "sut": sut_ref(version),
        "cex_sut": cex["sut"]["id"],
        "same_sut": version == cex["sut"]["version"],
        "horizon_ms": HORIZON_MS,
        "steps": steps,
        "compared_steps": n,
        "matched_steps": matched,
        "first_divergence": first_div,
        "trace_hash": prefix,
        "expected_trace_hash": cex["trace_hash"],
        "hash_match": prefix == cex["trace_hash"],
        "full_trace_hash": trace_hash([(mv, s) for mv, s, _ in run]),
        "skipped_moves": [],
        "invariants": invs,
        "violation_window_ms": None if w1 is None else {
            "invariant": "I1", **w1, "bound_ms": I1["bound_ms"], "over_budget_ms": w1["duration_ms"] - I1["bound_ms"]},
        "verdict": "FAIL" if any(i["result"] == "FAIL" for i in invs) else "PASS",
    }


def check_report(cex: dict[str, Any], desc: dict[str, Any]) -> dict[str, Any]:
    per_depth = [1, 6, 21, 55, 120, 240, 410, 690, 980, 1210, 1400, 1380, 1250, 1090, 940, 800, 700, 610]
    invs = []
    for inv in INVARIANTS:
        fail = inv["id"] == "I1"
        invs.append({**inv, "result": "FAIL" if fail else "PASS",
                     "counterexample": cex["id"] if fail else None,
                     "violated_at_ms": cex["violated_at_ms"] if fail else None,
                     "violation_duration_ms": cex["violation_duration_ms"] if fail else None,
                     "depth": cex["search"]["depth"] if fail else None,
                     "worst_case_ms": None if fail or inv["bound_ms"] is None else 900})
    return {
        "_fixture": True,
        "schema": SCHEMA_CHECK_REPORT,
        "run_id": "fixture-v031",
        "created_at": "2026-09-26T00:00:00Z",
        "model": desc["model"],
        "sut": sut_ref("v0.3.1"),
        "bounds": BOUNDS,
        "strategy": "bfs",
        "assumptions": ASSUMPTIONS,
        "stats": {"states": sum(per_depth), "transitions": 3 * sum(per_depth), "max_depth_reached": len(per_depth) - 1,
                  "wall_s": 1.5, "states_per_s": round(sum(per_depth) / 1.5, 1),
                  "new_states_per_depth": per_depth, "complete": True},
        "invariants": invs,
        "counterexample_files": [f"{cex['id']}.json"],
        "notes": ["FIXTURE: every number in this file is a placeholder."],
        "verdict": "FAIL",
    }


def run_list(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "_fixture": True,
        "schema": SCHEMA_RUN_LIST,
        "runs": [{"run_id": report["run_id"], "created_at": report["created_at"], "model": report["model"]["name"],
                  "sut": report["sut"]["id"], "verdict": report["verdict"], "states": report["stats"]["states"],
                  "wall_s": report["stats"]["wall_s"], "counterexamples": [i["counterexample"] for i in report["invariants"] if i["counterexample"]]}],
    }


def main() -> None:
    desc = describe()
    cex = counterexample(desc)
    report = check_report(cex, desc)
    files = {
        "describe.json": desc,
        "check-report.json": report,
        "cex-0017.json": cex,
        "replay-v031.json": replay("v0.3.1", cex, desc),
        "replay-v033.json": replay("v0.3.3", cex, desc),
        "runs.json": run_list(report),
    }
    for name, doc in files.items():
        (HERE / name).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print("wrote", HERE / name)


if __name__ == "__main__":
    main()
