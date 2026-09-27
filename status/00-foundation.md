# 00 foundation: status

**Done.** Tagged `contract-v1` on `main`.

- Repo, `.gitignore`, `pyproject.toml` (package `fleetflight`, console script, Python >= 3.12, dev deps pytest/rich/jsonschema). The local venv uses Python 3.13; there is no 3.12 on this machine.
- `src/fleetflight/core.py`: `TICK_MS`, `Move`/`TICK`, `TraceEvent`, `Invariant` (+ `bound_ms`, `timer_key`), `Bounds`, `Msg`, `HookResult`, `ControllerState`, `SUT`, `Model`, `trace_hash`, `short_hash`, `model_hash`, `counterexample_id`, `sut_id`/`parse_sut_id`, `split_assumption`, `canonical_json`.
- `schemas/`: `common`, `describe`, `check-report`, `counterexample`, `replay-result` and `run-list` (the last one is extra, for `GET /api/runs`).
- `fixtures/`: `describe.json`, `check-report.json`, `cex-0017.json`, `replay-v031.json`, `replay-v033.json` and `runs.json`, all `"_fixture": true`. Regenerate with `.venv/bin/python fixtures/make_fixtures.py`. The trace is hand-scripted and every number is a placeholder.
- Stubs: `cli.py` prints "not implemented" and exits 2. The `check/ models/ sut/ sim/ regress/ report/` packages have docstrings naming their public API.
- `tests/test_contract.py` covers:
  - schemas are valid draft 2020-12;
  - every fixture validates against its schema;
  - negative cases are rejected;
  - the counterexample is self-consistent (hash, ticks, replay rule);
  - hashing and id helpers.
- `pytest -q`: 19 passed.

Deviation from the brief: `rich` is also a runtime dependency, so a plain `pip install -e .` gives a working CLI.
