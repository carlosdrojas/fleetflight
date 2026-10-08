"""Vercel function: POST /api/replay {cex, sut} → a live replay through the real transition code.

The hosted twin of `fleetflight serve`'s POST /api/replay. It reads counterexamples from the exported
site data (ui/public/data/cex/) and runs `fleetflight.sim.replay` on demand (~0.1 s, ~30 MB).
Stdlib only: it imports the model and simulator directly, not cli.py (which needs rich).
"""
from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleetflight.core import SCHEMA_COUNTEREXAMPLE, Bounds  # noqa: E402
from fleetflight.models import load_model  # noqa: E402
from fleetflight.sim import replay  # noqa: E402

CEX_DIR = ROOT / "ui" / "public" / "data" / "cex"
CEX_RE = re.compile(r"cex-[0-9a-f]{4,64}")
MAX_BODY = 4096


def run_replay(body: object) -> tuple[int, dict]:
    if not isinstance(body, dict) or not isinstance(body.get("cex"), str):
        return 400, {"error": "expected {cex: counterexample-id, sut: optional-version}"}
    cex_id, sut = body["cex"], body.get("sut")
    if not CEX_RE.fullmatch(cex_id):
        return 400, {"error": "invalid counterexample id"}
    path = CEX_DIR / f"{cex_id}.json"
    if not path.is_file():
        return 404, {"error": "counterexample not found"}
    cex = json.loads(path.read_text(encoding="utf-8"))
    if cex.get("schema") != SCHEMA_COUNTEREXAMPLE:
        return 500, {"error": "bad counterexample file"}
    if sut is not None:
        if not isinstance(sut, str):
            return 400, {"error": "sut must be a string"}
        known = load_model(cex["model"]["name"]).describe()["sut_versions"]
        if sut not in known and not any(v.endswith(f"@{sut}") for v in known):
            return 400, {"error": f"unknown sut; expected one of {known}"}
    bounds = Bounds.from_json(cex["bounds"])
    model = load_model(cex["model"]["name"], sut=sut or cex["sut"]["id"], bounds=bounds)
    return 200, replay(model, cex)


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, doc: dict) -> None:
        data = json.dumps(doc, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= MAX_BODY:
                return self._send(400, {"error": f"request body must be 1..{MAX_BODY} bytes"})
            self._send(*run_replay(json.loads(self.rfile.read(length))))
        except (ValueError, KeyError, TypeError) as error:
            self._send(400, {"error": str(error)})

    def do_GET(self) -> None:
        self._send(405, {"error": "POST {cex, sut} to replay a counterexample"})
