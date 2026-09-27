You are session **00 foundation** for FleetFlight. Everything else is blocked on you, so be fast and precise: aim for 45 minutes.

First read `sessions/_common.md`, then `README.md` and everything in `mocks/`.

## Goal
Turn `~/Documents/Dev/fleetflight` into a git repo with a frozen shared contract. Other streams will then build in parallel against the contract and never need to talk to each other.

## Steps
1. **Repo setup.**
   - `git init -b main`.
   - `.gitignore` for Python, node, `out/` and `.venv`.
   - `pyproject.toml` with the package `fleetflight` in `src/`, a console script `fleetflight = fleetflight.cli:main`, Python >= 3.12, and dev deps pytest and rich.
   - Create the venv: `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`.
2. **`src/fleetflight/core.py`**, the shared API. Write it as real, typed, documented code:
   - **Time.** `TICK_MS = 50`. The model is discrete: all time is an integer count of milliseconds, in multiples of `TICK_MS`.
   - **`Move`**: a frozen dataclass with `name: str`, `args: tuple[tuple[str, int|str], ...]`, `injected: bool`.
     - The special move `TICK` (`injected=False`) advances time by one tick.
     - All other moves are adversary injections (fault or timing choices) and take no time.
   - **`TraceEvent`**: a frozen dataclass with `t_ms`, `name`, `detail: str`, `injected: bool`. These are system events emitted during a tick, for display only.
   - **`Invariant`**: a frozen dataclass with `id` (e.g. "I1"), `name` (e.g. "FAULT_SHUTDOWN_BOUNDED"), `description`, `formula: str` (display only), `check: Callable[[State], bool]`.
     - Invariants are **pure predicates on one state**.
     - Bounded-time properties are expressed by keeping timers in the state (e.g. `fault_since_ms`), so the checker never needs history.
   - **`Model` protocol**:
     - `name`, `version: str`, `sut: SUT`, `assumptions: list[str]`, `invariants: list[Invariant]`
     - `init() -> State`
     - `moves(state) -> list[Move]`: the enabled injections plus TICK, in a deterministic order, respecting the injection budget kept in the state.
     - `apply(state, move) -> tuple[State, list[TraceEvent]]`: pure and deterministic.
     - `describe() -> dict`: components, their states, injectables, invariants, assumptions and bounds. This feeds the UI's Spec screen.
     - `snapshot(state) -> dict[str, str|int|None]`: a flat, display-friendly view with keys like `bms`, `hub`, `inv`, `bus`, `nvm`. It drives the swimlanes.
   - **`SUT` protocol**: the seam where real firmware or software would plug in later. It has `name`, `version`, and pure hooks the model calls:
     - hub: `hub_on_boot`, `hub_on_msg`, `hub_on_tick`
     - inverter: `inv_on_cmd`, `inv_on_tick`
     - Each hook returns the new controller state plus the messages it sends.
     - Document that in production this becomes an adapter to real code, compiled for SIL or run as a subprocess.
   - **`State`**: models define their own frozen, hashable dataclass. The checker only needs `hash()`, `==`, and `snapshot()`.
   - **`trace_hash(steps) -> str`**: sha256 of canonical JSON over the list of `(move, snapshot)`. The first 12 hex chars are what gets displayed.
   - **`Bounds`**: a dataclass with `max_depth` (moves), `max_injections`, `horizon_ms`.
3. **`schemas/`**: JSON Schema (draft 2020-12) for every file that crosses a stream boundary:
   - `describe.schema.json`
   - `check-report.schema.json`: run id, model, sut, bounds, assumptions, stats (states, transitions, max_depth_reached, wall_s, per-depth new-state counts), and per-invariant result (PASS / FAIL, plus the counterexample id).
   - `counterexample.schema.json`: extend `mocks/counterexample-0017.json`. Every trace step carries a full `snapshot` and the `move`. Also include a `moves` list (just the injected moves with the tick index at which they occur), which is what replay and regression tests consume.
   - `replay-result.schema.json`: the SUT version, per-step match against the counterexample, trace hash, invariant results, and the `violation_window_ms` for the violated invariant.
4. **`fixtures/`**: hand-written example files that validate against the schemas: `describe.json`, `check-report.json`, `cex-0017.json`, `replay-v031.json`, `replay-v033.json`.
   - Put `"_fixture": true` at the top of each so nobody mistakes them for real output.
   - The UI and CLI streams build against these until real output exists.
5. **Stubs**: `cli.py` (a `main` that prints "not implemented" for each subcommand), and empty packages `check/`, `models/`, `sut/`, `sim/`, `regress/`, `report/`, `tests/`.
6. **`CONTRACT.md`**: one page covering the API above, the file formats, the determinism rules, the CLI command surface with flags, and the "adversary chooses injections, the system is deterministic" execution model.
   - CLI command surface: `describe | check | explain | sim | replay | regress | report | serve`.
   - Explain why this execution model is what makes checker and simulator share one definition: a counterexample is just a list of moves.
7. **`AGENTS.md`**: a short intro, a link to `sessions/_common.md` and `CONTRACT.md`, and empty **Decisions** and **Status** sections. Symlink `CLAUDE.md` and `GEMINI.md` to it.
8. `status/` with an empty `00-foundation.md`.
9. `pytest -q` must pass. Add a test that validates every fixture against its schema; `jsonschema` is fine as a dev dep.
10. **Commit and tag.** `git add -A && git commit`, then tag `contract-v1`.

## When done
Print the exact worktree commands the user should run next, one per stream: `git worktree add ../fleetflight-<stream> -b <stream>` for checker, model, cli, ui, ci-demo, pitch. The user launches the other sessions from those worktrees.

Stay inside your ownership.
- Don't implement the checker, the model or the UI.
- Do make the contract complete enough that nobody has to guess.
