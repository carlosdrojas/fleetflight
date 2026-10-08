# 03 CLI

## Done
- Simulator records init and every applied move, events, snapshots, violations, and generic timer windows. Both schedulers reset for repeatable reuse. Scripted moves run in order, including injections at the terminal tick; unavailable moves are skipped and reported.
- Replay compares/hashes the counterexample prefix, continues to the horizon, reports per-step divergence and longest windows, and checks all invariants over the full run.
- Argparse/Rich commands: describe, check, explain, sim, replay, regress, report, serve. Checker/model imports are lazy with an explicit integration error.
- Check passes the identical Bounds object to model and checker, uses live progress, and writes checker artifacts plus optional JSON output.
- Generated pytest files embed the full counterexample and readable MOVES, use the newest SUT by default, and assert every invariant. `FLEETFLIGHT_SUT` selects a version. Optional plugin: `pytest -p fleetflight.regress.plugin --fleetflight-sut v0.3.3 tests/regress`.
- `regress --from` generates; `--all` generates and replays every `out/cex-*.json` against the current SUT. `--junit` also runs replay. `--out` can select an alternate artifact directory.
- Markdown and JUnit outputs derive values from reports. Fixture displays carry an explicit MOCK DATA notice.
- Server binds 127.0.0.1, serves ui/dist and all five contract endpoints, and performs POST replay in memory. Paths and symlinks cannot escape the configured roots; cross-origin replay is rejected. Tests verify no artifact writes.
- All edits are on worktree `fleetflight-cli`, branch `cli`, in stream-owned paths plus this status file.

## Integration calls
- `fleetflight.models.load_model(name="core-ref", sut=None, bounds=None)`; describe uses `model.describe()` with no local rewriting.
- `fleetflight.check.check(model, bounds, on_progress=callback)`; callback reads `states` and `transitions` from the stats dictionary.
- CheckReport `.to_json()` and `fleetflight.check.write_report(report, out_dir)` returning paths. Counterexamples are persisted by write_report.
- Simulator requires `model.init()`, `.moves(state)`, `.apply(state, move)`, `.snapshot(state)`, `.invariants`, and `.describe()` exactly as contract-v1 defines them. No model internals or separate transition logic.
- Replay loads the counterexample's model name, SUT id (unless overridden), and original Bounds. Regress passes sut=None to select the current model default, unless the environment/plugin overrides it.
- `/api/replay` accepts `{ "cex": "cex-<hash>", "sut": "v..." }`; sut is optional and defaults to the originating SUT. API errors use HTTP 400/403/404 with `{ "error": "..." }`; success documents use frozen schemas.

## Validation
- `PYTHONPATH=src ../fleetflight/.venv/bin/python -m pytest -q -o addopts=''`: **57 passed in 1.81s** on this branch, with localhost socket binding permitted outside the sandbox.
- `git diff --check`: passed.
- Toy replay: 100/100 identical full hashes, exact originating trace hash, original SUT FAIL, fixed SUT PASS.
- Executed toy window: original 150 ms, fixed 50 ms, against a toy-only 50 ms bound. These are toy execution results, not core-ref or firmware measurements.
- Successful API responses validate against every corresponding frozen schema. Generated regressions execute under pytest with the optional plugin, passing on the fixed toy and failing on the buggy toy. Golden check/explain output tested by the optional sub-agent and reviewed locally.
- Edge cases covered: terminal-tick injections, argument-order normalization, disabled moves, initial/injection failures, open and multiple timer windows, post-counterexample failures, invalid horizons/rates/input, path traversal, symlink escape, and fixture labeling.

## Limitations
- Artifact reader is unavailable in this session; using the checked-in CLI and UI mocks.
- This branch still contains foundation stubs for checker/model. No core-ref correctness or state-count claim is made; the integrator must run the real demo after merging those streams.
- Available shared virtualenv uses Python 3.13; Python 3.12 was not available at `/opt/homebrew/bin/python3.12`.
- `sim --scenario bms-fault-basic` injects bms_fault at tick 0 and then only ticks; it errors if that injection is unavailable. Seeded rate semantics are documented on SeededScheduler.

## CONTRACT REQUEST
- `sim --json` has no frozen schema in contract-v1. The local Run document uses `fleetflight/simulation@1` with steps, invariants, skipped_moves, verdict, and trace_hash. Request a schema only if another stream needs to consume this document; no frozen files were changed.
