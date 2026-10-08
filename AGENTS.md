# FleetFlight: agent guide

FleetFlight does pre-release verification for distributed battery firmware (BMS ↔ Hub ↔ Inverter).
- A bounded model checker searches every allowed ordering of faults, delays and restarts.
- Each violation becomes a minimal counterexample.
- The counterexample is replayed deterministically through the **same** transition code, and then becomes a CI regression test.

Read these before touching code:
- [`sessions/_common.md`](sessions/_common.md): shared rules, stream ownership, deadlines, honesty rules.
- [`CONTRACT.md`](CONTRACT.md): the frozen API (`src/fleetflight/core.py`), file formats (`schemas/`), determinism rules and the CLI surface.
- Your own `sessions/NN-<stream>.md`.

Setup: `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' && .venv/bin/pytest -q`.
Numbers in `mocks/` and `fixtures/` are placeholders. Never quote them as results.

`CLAUDE.md` and `GEMINI.md` are symlinks to this file.

## Decisions
- **contract-v1** (00 foundation): `TICK_MS = 50`. Invariants are single-state predicates; bounded ones expose `bound_ms` + `timer_key` so durations and windows are computed generically from snapshots.
- The injection budget lives in the model state, so `load_model(..., bounds=)` and `check(model, bounds)` take the same `Bounds`.
- SUT seam: pure hooks returning `HookResult(ctl, sends)`. The hub's `nvm` is the only state that survives a restart. The model owns the bus (message ids and delivery times).
- A counterexample is `moves` (injections with `tick_index`) + `ticks`. Replay continues to the horizon, but hashes and compares only the counterexample's length. Moves that aren't enabled are skipped and reported, never forced.
- Counterexample ids are content hashes (`cex-<8 hex>`). The `cex-0017` fixture id is a fixture only.
- Added a `run-list` schema for `GET /api/runs` (not in the original brief) so the UI doesn't have to guess its shape.
- `rich` is a runtime dependency as well as a dev one, so that `pip install -e .` gives a working CLI. Only `cli.py` may import it.
- **Integration (07), applied contract requests:**
  - 02 model: `check --only INJ[,INJ…]` passes `injections=` to `load_model`, which scopes the fault model. Unknown names exit 2 and list the model's injectables.
  - 01 checker: the `worst_case_ms` schema description now says "longest window", matching the implementation. Description only; the schema shape is unchanged.
  - 03 cli: the `sim --json` schema request is **declined**, since no other stream consumes that document.
  - 04 ui: `GET /api/regress[/<id>]` is **not built** (feature freeze). The Regressions screen falls back cleanly.
- **Integration glue:**
  - `sim --scenario NAME` runs `fleetflight.models.SCENARIOS` (it used to hard-code `bms_fault@0`).
  - The `explain`/`sim` terminal tables show swimlane keys plus timers, hide heartbeat send/deliver events and fold quiet ticks. The JSON and UI keep the full trace.
  - `explain` exits 1, because it shows a violation; the demo expects that.
  - `/api/runs` dedupes by `run_id`.
  - `make serve` serves the newest `out/demo.*`.
- **Demo story = what the checker finds:** the shortest I1 counterexample on v0.3.1 is fault + link loss (`cex-286e0592`). It still fails on v0.3.2 (1050 ms) and passes on v0.3.3 (250 ms). The restart story appears only as the scripted scenario `restart-during-fault`, or through `--only`, and v0.3.2 passes the scoped restart counterexample (see STATUS.md).

- **Hosted demo (2026-10-08):** Vercel. UI built with `VITE_FF_STATIC=1` reads the exported run from `ui/public/data/` (`make site-data`, committed). `POST /api/replay` is live via `api/replay.py` (stdlib-only, imports model + sim directly, not cli.py); the UI falls back to the exported replay and labels it. Full `check` is never run on the host (~36 s, ~860 MB).
- **3D replay** (`#/scene/<cex>[/<ms>]`): three.js, lazy-loaded; every visual comes from the replay trace (`ui/src/lib/scene.ts`). The site lands on it.

## Status
- 00 foundation: done. Tagged `contract-v1`. See `status/00-foundation.md`.
- 01–06 merged into `integration` (07). `make demo-fast` passes end to end on real code. Real numbers are in `STATUS.md`. `pytest -q` is green, as are the UI's 23 vitest tests and its build.
- Cut: `/api/regress`, fleet stretch (08), and the "idle per restart" line in the pitch (only a model test computes it; see STATUS.md).
- 2026-10-08: `integration` merged to `main`. 3D replay + hosted-demo plumbing on `main`. Not yet pushed: no GitHub remote, no Vercel project.
