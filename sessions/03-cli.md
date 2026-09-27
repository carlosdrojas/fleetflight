You are session **03 cli** for FleetFlight. You're in worktree `../fleetflight-cli` on branch `cli`.

Read `sessions/_common.md`, `CONTRACT.md`, `src/fleetflight/core.py` and `mocks/cli.md` first. You own `src/fleetflight/sim/`, `src/fleetflight/regress/`, `src/fleetflight/report/`, `src/fleetflight/cli.py` and `tests/cli/`.

## Goal
Build the simulator, replay, regression generator and CLI, i.e. everything a user types. `mocks/cli.md` is the target UX. Match its feel, but every number must come from the real code.

The checker (stream 01) and model (stream 02) are being built in parallel. Develop against:
- (a) the contract types,
- (b) `fixtures/`,
- (c) a tiny toy model you write in `tests/cli/toy_model.py`.

Import the real checker and model lazily, with a clear error if they're missing, so integration is just a merge.

## Components
- **`sim/`**
  - `simulate(model, scheduler, horizon_ms) -> Run`, where `Run` holds steps, snapshots, trace events and invariant results per step.
  - Schedulers:
    - `SeededScheduler(seed, rates)`: a random adversary for exploratory runs.
    - `ScriptedScheduler(moves)`: replays a counterexample's `moves` list. At each tick, apply the scripted injections for that tick in order, then TICK.
  - `replay(model, cex) -> ReplayResult`: compares per-step snapshots against the counterexample, computes the trace hash, and outputs the replay-result schema.
  - `--sut vX` swaps the SUT version, so replaying a counterexample against a fixed version is one flag.
- **`regress/`**
  - `generate(cex, out_dir)` writes `tests/regress/test_<cex-id>.py`: a readable pytest file that embeds the injected moves (like `mocks/test_cex_0017.py`) and asserts invariants hold.
  - Also a pytest plugin or marker so `pytest tests/regress` runs them against the current SUT version.
- **`report/`**
  - `to_markdown(check_report)`: used for the GitHub step summary.
  - `to_junit(results)`: used by CI.
- **`cli.py`**: argparse subcommands, output styled with rich.
  - `describe [--json]`
  - `check --model core-ref --sut v0.3.1 [--depth N] [--json PATH]`, with a live progress bar and the summary table.
  - `explain <cex-id|path>`: the step table like mocks/cli.md §3.
  - `sim --seed N [--sut]`
  - `replay --counterexample X [--sut] [--repeat N]`. `--repeat` prints the `uniq -c`-style hash count.
  - `regress --from X | --all [--junit PATH]`
  - `report PATH --markdown`
  - `serve [--port 8765] [--out out/]`: stdlib `http.server` serving `ui/dist/` plus a tiny JSON API. It must be read-only and bound to localhost:
    - `GET /api/describe`
    - `GET /api/runs`
    - `GET /api/runs/<id>`
    - `GET /api/cex/<id>`
    - `POST /api/replay {cex, sut}`: runs a replay and returns JSON.
  - Exit codes: 0 if all pass, 1 if an invariant fails, 2 on usage error. CI depends on these.

## Tests (tests/cli/)
- Replay of a toy-model counterexample reproduces the identical hash 100/100 times.
- Replaying against a "fixed" toy SUT passes.
- A generated regression file imports and runs.
- CLI exit codes.
- Every JSON the `serve` API returns validates against the schemas.

## Sub-agents
Optional: spawn one sub-agent to write `tests/cli/test_cli_golden.py`, golden-output tests of `explain` and `check` on the toy model. This keeps output stable while you iterate.

Once you're done with the toy model, write in your status file exactly which calls into checker and model you rely on, so the integrator can wire them in.
