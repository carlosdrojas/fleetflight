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

## Status
- 00 foundation: done. Tagged `contract-v1`. See `status/00-foundation.md`.
