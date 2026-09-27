"""FleetFlight commands and a localhost, read-only artifact API."""
from __future__ import annotations

import argparse
import importlib
import json
import mimetypes
import re
import sys
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from fleetflight.core import Bounds, Move, SCHEMA_CHECK_REPORT, SCHEMA_COUNTEREXAMPLE, SCHEMA_RUN_LIST, short_hash
from fleetflight.regress import generate, run_counterexample
from fleetflight.report import to_junit, to_markdown
from fleetflight.sim import ScriptedScheduler, SeededScheduler, replay, simulate

console = Console(markup=False, highlight=False)


def _entrypoint(module, name):
    try:
        entry = getattr(importlib.import_module(module), name)
    except (ImportError, AttributeError) as error:
        raise ValueError(f"{module}.{name} is unavailable; integrate the model/checker stream first") from error
    return entry


def load_model(name="core-ref", sut=None, bounds=None):
    return _entrypoint("fleetflight.models", "load_model")(name, sut=sut, bounds=bounds)


def check_model(model, bounds, on_progress):
    return _entrypoint("fleetflight.check", "check")(model, bounds, on_progress=on_progress)


def write_report(report, out_dir):
    return _entrypoint("fleetflight.check", "write_report")(report, out_dir)

COMMANDS: dict[str, str] = {
    "describe": "print the model/SUT spec (components, injectables, invariants, assumptions)",
    "check": "bounded model check; writes check report and counterexamples",
    "explain": "step table for a counterexample",
    "sim": "seeded (or scripted) simulation run",
    "replay": "replay a counterexample against a SUT version",
    "regress": "generate / run regression tests from counterexamples",
    "report": "render a check report (markdown, junit)",
    "serve": "serve ui/dist and the read-only JSON API on localhost",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fleetflight", description="Pre-release verification for battery firmware.")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    commands = {}
    for name, help_text in COMMANDS.items():
        commands[name] = sub.add_parser(name, help=help_text)
    for name in ("describe", "check", "sim"):
        commands[name].add_argument("--model", default="core-ref")
        commands[name].add_argument("--sut")
    commands["describe"].add_argument("--json", action="store_true")
    check = commands["check"]
    check.add_argument("--depth", type=int, default=Bounds().max_depth)
    check.add_argument("--injections", type=int, default=Bounds().max_injections)
    check.add_argument("--horizon-ms", type=int, default=Bounds().horizon_ms)
    check.add_argument("--out", type=Path, default=Path("out"))
    check.add_argument("--json", type=Path)
    commands["explain"].add_argument("counterexample")
    commands["explain"].add_argument("--out", type=Path, default=Path("out"))
    sim = commands["sim"]
    sim.add_argument("--seed", type=int, required=True)
    sim.add_argument("--scenario", choices=["bms-fault-basic"])
    sim.add_argument("--horizon-ms", type=int, default=Bounds().horizon_ms)
    sim.add_argument("--json", type=Path)
    replay_parser = commands["replay"]
    replay_parser.add_argument("--counterexample", required=True)
    replay_parser.add_argument("--sut")
    replay_parser.add_argument("--repeat", type=int, default=1)
    replay_parser.add_argument("--horizon-ms", type=int)
    replay_parser.add_argument("--out", type=Path, default=Path("out"))
    replay_parser.add_argument("--json", type=Path)
    regress = commands["regress"]
    source = regress.add_mutually_exclusive_group(required=True)
    source.add_argument("--from", dest="source")
    source.add_argument("--all", action="store_true")
    regress.add_argument("--out-dir", type=Path, default=Path("tests/regress"))
    regress.add_argument("--out", type=Path, default=Path("out"))
    regress.add_argument("--junit", type=Path)
    report = commands["report"]
    report.add_argument("path", type=Path)
    format_group = report.add_mutually_exclusive_group(required=True)
    format_group.add_argument("--markdown", action="store_true")
    format_group.add_argument("--junit", action="store_true")
    commands["serve"].add_argument("--port", type=int, default=8765)
    commands["serve"].add_argument("--out", type=Path, default=Path("out"))
    return parser


def read_document(path, schema=None):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or (schema and doc.get("schema") != schema):
        raise ValueError(f"{path}: expected {schema or 'a JSON object'}")
    return doc


def read_cex(value, out_dir=Path("out")):
    path = Path(value)
    if re.fullmatch(r"cex-[0-9a-f]{4,}", str(value)):
        path = Path(out_dir) / f"{value}.json"
    return read_document(path, SCHEMA_COUNTEREXAMPLE)


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path, doc):
    write_text(path, json.dumps(doc, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def fixture_notice(doc):
    if doc.get("_fixture"):
        console.print("MOCK DATA — fixture values, not verification results.", style="yellow")


def show_results(items):
    table = Table("Invariant", "Result", "Detail", box=None)
    for item in items:
        detail = item.get("counterexample") or ""
        window = item.get("max_window")
        if window:
            detail = f"window {window['duration_ms']} ms" + (" (open)" if window["open"] else "")
        table.add_row(f"{item['id']} {item['name']}", item["result"], detail,
                      style="red" if item["result"] == "FAIL" else "green")
    console.print(table)


def show_trace(steps):
    if not steps:
        raise ValueError("trace must contain an initial state")
    keys = [key for key in steps[0]["snapshot"] if key != "t_ms"]
    table = Table("Step", "t(ms)", "Move / events", *keys, "Violations", box=None)
    for step in steps:
        move = Move.from_json(step["move"]) if step["move"] else None
        label = (move.label + ("*" if move.injected else "")) if move else "init"
        events = [event["name"] + (": " + event["detail"] if event["detail"] else "")
                  for event in step["events"]]
        table.add_row(str(step["step"]), str(step["t_ms"]), "\n".join([label] + events),
                      *[str(step["snapshot"].get(key, "")) for key in keys],
                      ", ".join(step.get("violations", [])))
    console.print(table)
    console.print("* = injected")


def replay_cex(cex, sut=None, horizon_ms=None):
    bounds = Bounds.from_json(cex["bounds"])
    model = load_model(cex["model"]["name"], sut=sut or cex["sut"]["id"], bounds=bounds)
    return replay(model, cex, horizon_ms=horizon_ms)


def _execute(args):
    if args.command == "describe":
        doc = load_model(args.model, sut=args.sut).describe()
        if args.json:
            print(json.dumps(doc, indent=2, ensure_ascii=False))
        else:
            fixture_notice(doc)
            console.print(f"{doc['model']['name']} · {doc['sut']['id']}")
            for component in doc["components"]:
                console.print(f"{component['name']} ({component['owner']}): {component['description']}")
            for injection in doc["injectables"]:
                console.print(f"INJECT {injection['name']}: {injection['description']} {injection['params']}")
            for inv in doc["invariants"]:
                console.print(f"{inv['id']} {inv['name']}: {inv['formula']}")
            for assumption in doc["assumptions"]:
                console.print(assumption)
        return 0
    if args.command == "check":
        bounds = Bounds(args.depth, args.injections, args.horizon_ms)
        model = load_model(args.model, sut=args.sut, bounds=bounds)
        console.print(f"{model.name} · depth ≤ {bounds.max_depth} moves · "
                      f"horizon {bounds.horizon_ms} ms · ≤ {bounds.max_injections} injections · BFS")
        for assumption in model.assumptions:
            console.print(assumption)
        with Progress(SpinnerColumn(), BarColumn(), TextColumn("{task.description}"), console=console,
                      disable=not console.is_terminal, transient=True) as progress:
            task = progress.add_task("exploring", total=None)

            def on_progress(stats):
                progress.update(task, description=f"exploring {stats.get('states', 0):,} states · "
                                f"{stats.get('transitions', 0):,} transitions")

            report = check_model(model, bounds, on_progress)
        doc = report.to_json()
        fixture_notice(doc)
        stats = doc["stats"]
        console.print(f"{stats['states']:,} states · {stats['transitions']:,} transitions · "
                      f"{stats['wall_s']:.3f} s · complete: {stats['complete']}")
        show_results(doc["invariants"])
        for path in write_report(report, args.out):
            console.print(f"Wrote {path}")
        if args.json:
            write_json(args.json, doc)
        return int(doc["verdict"] == "FAIL")
    if args.command == "explain":
        cex = read_cex(args.counterexample, args.out)
        fixture_notice(cex)
        inv = cex["invariant"]
        console.print(f"{inv['id']} {inv['name']} violated at t={cex['violated_at_ms']} ms")
        if cex["violation_duration_ms"] is not None:
            console.print(f"Duration {cex['violation_duration_ms']} ms · budget {inv['bound_ms']} ms")
        show_trace(cex["trace"])
        if cex.get("explanation"):
            console.print(cex["explanation"])
        return 1
    if args.command == "sim":
        bounds = Bounds(horizon_ms=args.horizon_ms)
        model = load_model(args.model, sut=args.sut, bounds=bounds)
        scheduler = SeededScheduler(args.seed)
        if args.scenario:
            scheduler = ScriptedScheduler([{"tick_index": 0, "t_ms": 0,
                                             "move": Move("bms_fault").to_json()}])
        run = simulate(model, scheduler, args.horizon_ms)
        if args.scenario and run.skipped_moves:
            raise ValueError("bms-fault-basic requires an enabled bms_fault injection at init")
        console.print(f"{model.name} · {model.describe()['sut']['id']} · seed {args.seed} · "
                      f"horizon {args.horizon_ms} ms")
        show_trace(run.steps)
        show_results(run.invariants)
        if args.json:
            write_json(args.json, run.to_json())
        return int(run.verdict == "FAIL")
    if args.command == "replay":
        if args.repeat < 1:
            raise ValueError("--repeat must be positive")
        cex = read_cex(args.counterexample, args.out)
        fixture_notice(cex)
        counts = Counter()
        failed = False
        for repeat_index in range(args.repeat):
            result = replay_cex(cex, args.sut, args.horizon_ms)
            counts[result["full_trace_hash"]] += 1
            failed |= result["verdict"] == "FAIL"
        console.print(f"{result['sut']['id']} · {result['matched_steps']}/{result['compared_steps']} steps match · "
                      f"hash match: {result['hash_match']}")
        for digest, count in sorted(counts.items()):
            console.print(f"{count:7d} {short_hash(digest)}")
        for skipped in result["skipped_moves"]:
            console.print(f"SKIPPED tick {skipped['tick_index']}: {skipped['move']['name']} — {skipped['reason']}")
        show_results(result["invariants"])
        if args.json:
            write_json(args.json, result)
        return int(failed)
    if args.command == "regress":
        sources = sorted(args.out.glob("cex-*.json")) if args.all else [args.source]
        if not sources:
            raise ValueError(f"no counterexamples found in {args.out}")
        results = []
        for source in sources:
            cex = read_cex(source, args.out)
            fixture_notice(cex)
            console.print(f"Wrote {generate(cex, args.out_dir)}")
            if args.all or args.junit:
                _entrypoint("fleetflight.models", "load_model")
                result = run_counterexample(cex)
                results.append(result)
                console.print(f"{cex['id']} · {result['sut']['id']} · {result['verdict']}")
        if args.junit:
            write_text(args.junit, to_junit(results))
        return int(any(result["verdict"] == "FAIL" for result in results))
    if args.command == "report":
        doc = read_document(args.path)
        print(to_markdown(doc) if args.markdown else to_junit(doc), end="")
        return int(doc["verdict"] == "FAIL")
    if args.command == "serve":
        if not 0 <= args.port <= 65535:
            raise ValueError("--port must be between 0 and 65535")
        with create_server(args.out, port=args.port) as server:
            console.print(f"FleetFlight http://127.0.0.1:{server.server_port}")
            server.serve_forever()
        return 0
    raise ValueError("unknown command")


def _safe_file(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError("path outside configured directory")
    return path


def run_list(out_dir):
    rows = []
    fixture = False
    for path in sorted(Path(out_dir).glob("check-*.json")):
        doc = read_document(_safe_file(out_dir, path.name), SCHEMA_CHECK_REPORT)
        row = {"run_id": doc["run_id"], "model": doc["model"]["name"], "sut": doc["sut"]["id"],
               "verdict": doc["verdict"], "states": doc["stats"]["states"],
               "wall_s": doc["stats"]["wall_s"],
               "counterexamples": [item["counterexample"] for item in doc["invariants"] if item["counterexample"]]}
        if "created_at" in doc:
            row["created_at"] = doc["created_at"]
        rows.append(row)
        fixture |= bool(doc.get("_fixture"))
    rows.sort(key=lambda row: (row.get("created_at", row["run_id"]), row["run_id"]), reverse=True)
    result = {"schema": SCHEMA_RUN_LIST, "runs": rows}
    if fixture:
        result["_fixture"] = True
    return result


def create_server(out_dir, port=8765, ui_dir=None):
    """Create a localhost server; POST replay computes in memory without writes."""
    out_dir = Path(out_dir).resolve()
    ui_dir = Path(ui_dir or Path(__file__).resolve().parents[2] / "ui" / "dist").resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send_json(self, status, document):
            data = json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def artifact(self, identifier, prefix, schema):
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", identifier) or identifier in (".", ".."):
                raise ValueError("invalid artifact id")
            return read_document(_safe_file(out_dir, f"{prefix}{identifier}.json"), schema)

        def do_GET(self):
            try:
                path = unquote(urlsplit(self.path).path)
                if path == "/api/describe":
                    return self.send_json(200, load_model().describe())
                if path == "/api/runs":
                    return self.send_json(200, run_list(out_dir))
                if path.startswith("/api/runs/"):
                    return self.send_json(200, self.artifact(path[len('/api/runs/'):], "check-", SCHEMA_CHECK_REPORT))
                if path.startswith("/api/cex/"):
                    return self.send_json(200, self.artifact(path[len('/api/cex/'):], "", SCHEMA_COUNTEREXAMPLE))
                if path.startswith("/api/"):
                    return self.send_json(404, {"error": "unknown endpoint"})
                target = _safe_file(ui_dir, path.lstrip("/") or "index.html")
                if not target.is_file():
                    return self.send_json(404, {"error": "UI file not found; build ui/dist first"})
                data = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except FileNotFoundError:
                self.send_json(404, {"error": "artifact not found"})
            except (ValueError, KeyError, TypeError, OSError) as error:
                self.send_json(400, {"error": str(error)})

        def do_POST(self):
            try:
                if urlsplit(self.path).path != "/api/replay":
                    return self.send_json(404, {"error": "unknown endpoint"})
                origin = self.headers.get("Origin")
                allowed = {f"http://127.0.0.1:{self.server.server_port}",
                           f"http://localhost:{self.server.server_port}"}
                if origin and origin not in allowed:
                    return self.send_json(403, {"error": "cross-origin replay is disabled"})
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("request body must be 1..65536 bytes")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or not isinstance(body.get("cex"), str):
                    raise ValueError("expected {cex: counterexample-id, sut: optional-version}")
                if body.get("sut") is not None and not isinstance(body["sut"], str):
                    raise ValueError("sut must be a string")
                cex = self.artifact(body["cex"], "", SCHEMA_COUNTEREXAMPLE)
                return self.send_json(200, replay_cex(cex, body.get("sut")))
            except FileNotFoundError:
                self.send_json(404, {"error": "counterexample not found"})
            except (ValueError, KeyError, TypeError, OSError) as error:
                self.send_json(400, {"error": str(error)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return _execute(args)
    except SystemExit as error:
        return int(error.code)
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"fleetflight: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
