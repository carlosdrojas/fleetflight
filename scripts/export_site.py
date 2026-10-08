"""Export a real demo run as static JSON for the hosted site (ui/public/data/).

The UI's site mode (VITE_FF_STATIC=1) reads these files instead of calling `fleetflight serve`:
  describe.json · runs.json · runs/<run_id>.json · cex/<id>.json · replay/<cex>__<version>.json · meta.json
Every file is produced by the same functions `serve` uses, from a real `scripts/demo.sh` output dir.

Usage: python scripts/export_site.py [OUT_DIR]   (default: the newest out/demo.*)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fleetflight.cli import load_model, read_document, replay_cex, run_list
from fleetflight.core import SCHEMA_CHECK_REPORT, SCHEMA_COUNTEREXAMPLE

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "ui" / "public" / "data"


def newest_demo() -> Path:
    runs = sorted(ROOT.glob("out/demo.*/"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        sys.exit("no out/demo.* directory; run `make demo` first")
    return runs[0]


def write(rel: str, doc: dict) -> None:
    path = DEST / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else newest_demo()
    if DEST.exists():
        shutil.rmtree(DEST)

    describe = load_model().describe()
    write("describe.json", describe)
    runs = run_list(src)
    write("runs.json", runs)
    for row in runs["runs"]:
        write(f"runs/{row['run_id']}.json", read_document(src / f"check-{row['run_id']}.json", SCHEMA_CHECK_REPORT))

    cex_ids = sorted({c for row in runs["runs"] for c in row["counterexamples"]})
    versions = [v.split("@")[-1] for v in describe["sut_versions"]]
    for cid in cex_ids:
        cex = read_document(src / f"{cid}.json", SCHEMA_COUNTEREXAMPLE)
        write(f"cex/{cid}.json", cex)
        for v in versions:
            write(f"replay/{cid}__{v}.json", replay_cex(cex, v))

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    checked_at = max((row.get("created_at", "") for row in runs["runs"]), default="")
    write("meta.json", {
        "checked_at": checked_at,
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": commit,
        "source": src.name,
        "counterexamples": cex_ids,
        "versions": versions,
    })
    print(f"exported {len(runs['runs'])} runs, {len(cex_ids)} counterexamples, {len(cex_ids) * len(versions)} replays from {src} → {DEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
