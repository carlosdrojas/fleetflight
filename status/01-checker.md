# 01 checker: status

**Done:** milestones 1–4, all on branch `checker`. `pytest -q`: 57 passed (whole repo, 38 of them in `tests/check/`).

## What exists
- `src/fleetflight/check/bfs.py`, exported from `fleetflight.check`:
  - `check(model, bounds=None, *, on_progress=None, progress_every=5000, stop_when_all_failed=True, run_id=None) -> CheckReport`
  - `CheckReport` has `.to_json()`, `.counterexamples`, `.run_id`, `.verdict` and `.exit_code`
  - `write_report(report, out_dir) -> list[Path]` (the report comes first, then one file per counterexample)
- **Search.** Level-by-level BFS.
  - The visited set is a `dict` keyed on the state itself.
  - Parent links are two flat int lists: `parent[id]`, and `move_idx[id]`, the index into `moves(parent)`.
  - No events or snapshots are stored per state.
  - Invariants that haven't failed yet are checked on every new state, init included.
  - A state is not expanded at `max_depth` or when `t_ms >= horizon_ms`.
- **Counterexamples.** The path is rebuilt by re-applying moves from `init()`. Every re-applied state must be the stored one, otherwise it raises `ModelNondeterminismError`. That check catches a nondeterministic model instead of emitting a counterexample that won't replay.
  - Each counterexample has a full trace (snapshot, events and `violations` per step), `moves` with `tick_index`, `ticks`, `trace_hash`, `violation_duration_ms` (= `t - snapshot[timer_key]`), `search`, and `replay.command`.
  - The id is `core.counterexample_id(model.name, sut_id, inv.id, moves)`.
- **Early stop.** The search stops once every invariant has a counterexample. It then sets `complete: false` and adds a note. `stop_when_all_failed=False` disables this.
- `run_id` = `<UTC yyyymmddThhmmss>-<sut version>-<6 hex of model/sut/bounds>`.

## Decisions (for AGENTS.md; I don't own that file)
- **`worst_case_ms` means the longest window**, using the CONTRACT §4 rule: a window opens when `snapshot[timer_key]` becomes non-null and closes at the first state where it is null again, and open windows count up to the current state. It is measured on every explored transition, including transitions into states already visited. It is reported only for bounded invariants that PASS. So it matches the replay's `violation_window_ms` and is the number to show on "v0.3.3: worst X ms vs 500 ms budget".
  - Note: the invariant is a state predicate. With a 500 ms bound, a window can be 550 ms and still PASS if the timer clears in the same tick the 550th ms is reached. That's a discretization artifact of `TICK_MS = 50`, visible in the toy counter (window 200 = bound 200, PASS).
- Trace events aren't stored during search. They are regenerated when the path is rebuilt (`apply` is pure). This deviates from the brief's `(parent_id, move, trace_events)` per state, and saves memory with no loss.

## Tests (`tests/check/`)
- `test_toy_counter.py` (a): even counter mod 10. Every invariant PASSes. The test also checks the state count against a hand enumeration, depth/horizon cut-offs, and `worst_case_ms == 200`.
- `test_toy_race.py` (b): lost-update race.
  - FAILs with exactly 4 moves (read, read, write, write), 0 ticks.
  - **Minimality** is proven by brute-force enumeration of every move sequence up to length 4.
  - With a budget of 3 it PASSes.
- `test_toy_timer.py` (c): a 150 ms bound violated only when `bus_delay` and `restart` line up.
  - Counterexample: `fault@0, bus_delay@0, restart@100`, 4 ticks, violated at 200 ms, duration 200.
  - Each injection alone PASSes: worst window 50, 150 and 150 ms.
  - The replay rule reproduces `trace_hash`.
- `oracle.py`: a naive recursive DFS written by a sub-agent that never looked at the checker. I reviewed it: its memos are exact and can't hide a shorter violation.
- `test_crosscheck.py`: BFS agrees with the oracle on PASS/FAIL, and BFS depth equals the oracle's minimum violating length. It covers 14 model/bounds cases, including the benchmark model up to 21k states.
- `test_report.py`:
  - schema validation of reports, counterexamples and written files
  - determinism (two runs are identical apart from `wall_s`, `states_per_s`, `run_id` and `created_at`)
  - content-hash ids
  - early stop
  - `on_progress`
  - violation at init
  - nondeterministic model rejected
- `bench_model.py`: a core-ref-*shaped* benchmark model (ASSUMED shape; this is **not** core-ref). It has a bus with delay/drop, hub restart with NVM, heartbeats and an inverter hold timer. Run it with `python -m tests.check.bench_model D K H [--profile]`.

## Performance (measured, Apple M1 Pro, Python 3.13.7, single thread)
Profiled with cProfile first. About 45% of the time was checker overhead: the loop, dict `setdefault` (a single hash per transition), and a per-state snapshot for window tracking. The rest was the model's `apply`/`dataclasses.replace`. One optimization: stop snapshotting once every bounded invariant has failed.

| Model | Bounds (depth, inj, horizon) | States | Wall | States/s |
|---|---|---|---|---|
| bench (I1 FAIL) | 120, 3, 2000 | 137,258 | 0.80 s | ~172k |
| bench (I1 FAIL) | 120, 3, 3000 | 303,531 | 1.76 s | ~173k |
| bench (I1 PASS, windows tracked throughout) | 120, 3, 3000 | 303,531 | 2.69 s | ~113k |

These are the bench model's numbers, not core-ref's. Real core-ref throughput depends mostly on the cost of its `apply` (SUT hooks). I'll re-measure once stream 02 commits a model; so far the `model` branch has no commits. No multiprocessing: one thread is well above the 50k target.

## Not done / next
- Measure against the real core-ref once `model` has commits (`git worktree` it locally, don't copy code).
- `explanation` (optional counterexample field) is not emitted; `explain` is the CLI's job.

## CONTRACT REQUEST
None. Optional clarification for 00: the check-report schema describes `worst_case_ms` as "the largest timer value seen in any explored state". I implemented the window length (see Decisions), which is what the UI and replay compare against the budget. Suggest rewording the description to match.
