You are session **01 checker** for FleetFlight. You're in worktree `../fleetflight-checker` on branch `checker`.

Read `sessions/_common.md`, `CONTRACT.md` and `src/fleetflight/core.py` first. You own `src/fleetflight/check/` and `tests/check/`.

## Goal
A correct, fast, bounded explicit-state model checker that works on any `Model` from the contract. This is the technical heart that judges will poke at, so correctness first, then speed.

## Requirements
- **`check(model, bounds, *, on_progress=None) -> CheckReport`**
  - Breadth-first search from `model.init()`.
  - Successors: `model.apply(state, m)` for every `m in model.moves(state)`.
  - Stop expanding a state beyond `bounds.max_depth` or `bounds.horizon_ms`.
- **Visited set.** Key it on the state itself (hash + eq). Keep parent pointers `(parent_id, move, trace_events)` so any state's path can be rebuilt.
- **Invariants.** Check every invariant on every newly discovered state.
  - Record the **first** (therefore shortest, because BFS) violating state for each invariant.
  - Keep searching until every invariant has a counterexample or the space is exhausted within bounds, so the PASS results mean "holds in all reachable states within bounds".
- **Counterexample.** Rebuild the path and emit a counterexample dict that validates against `schemas/counterexample.schema.json`. It needs:
  - full snapshots per step
  - the `moves` list
  - `violated_at_ms`
  - `violation_duration_ms` (read from the model's timer fields via `snapshot`, or computed along the path)
  - `trace_hash` from `core.trace_hash`
  - search stats
- **Stats**: states, transitions, max depth reached, wall seconds, and new states per depth. The UI draws the per-depth chart from this.
- **Report**: `CheckReport.to_json()` must validate against `check-report.schema.json`. The file writer `write_report(report, out_dir)` writes `check-<run>.json` and `cex-XXXX.json` files.
  - Counterexample ids must be stable and deterministic: a hash of model + sut + invariant + moves, not a counter.
- **Progress**: call `on_progress(stats)` every N states so the CLI can draw a progress bar. Nothing else inside the checker may depend on wall time.
- **Performance**: aim for more than 50k states/s on a laptop for a model the size of core-ref.
  - Profile with cProfile before optimizing.
  - Allowed tricks: interning, storing parent links in flat lists, avoiding dict churn.
  - No multiprocessing unless a single thread is clearly too slow. If you do add it, it must stay deterministic.

## Tests (tests/check/)
- **Toy models**, each in its own test file, with known answers:
  - (a) A counter with a known unreachable bad state: must PASS.
  - (b) A two-process lost-update race: must FAIL, with a counterexample of exact known length.
  - (c) A bounded-timer property violated only when two injections line up.
- **Minimality**: for model (b), prove the counterexample is the shortest by brute-force enumerating every path up to that length.
- **Determinism**: two runs give identical reports, apart from `wall_s` and the run id.
- **Schema validation** of everything you emit.

## Sub-agents
Spawn one sub-agent to independently write a naive recursive DFS checker in `tests/check/oracle.py` without looking at your implementation. Then cross-check: on every toy model, both must agree on PASS / FAIL for each invariant, and the BFS counterexample must be no longer than any the oracle finds.

## Milestones
1. The API compiles against core.py, and toy model (a) passes.
2. Counterexamples plus the minimality test.
3. Report and schema validation.
4. Performance pass. Record states/s in your status file.

Commit after each. Once stream 02's model exists on its branch you may try it locally (e.g. `git worktree` or `git show model:path`) to measure real performance, but don't copy its code into your branch.
