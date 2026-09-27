# FleetFlight contract (`contract-v1`)

This file, `src/fleetflight/core.py` and `schemas/` make up the frozen contract. Streams build against it in parallel. To change it, write a `## CONTRACT REQUEST` in your status file. Don't edit it yourself (`sessions/_common.md`).

## 1. Execution model: the adversary chooses, the system is deterministic
- Time is discrete. `TICK_MS = 50`, and every `t_ms` is an integer multiple of it.
- At each state, `model.moves(state)` lists the enabled **injections** (fault/timing choices such as `bms_fault`, `hub_restart`, `bus_delay(msg=…, extra_ms=…)`), followed by **`TICK`**. The order is deterministic and TICK always comes last.
  - **Injections** take no time. They are limited by `bounds.max_injections`, and the model keeps that budget in the state.
  - **`TICK`** advances time by one tick. Everything that isn't a choice happens inside it: due deliveries, SUT tick hooks, timers, heartbeats.
- `model.apply(state, move) -> (state', events)` is pure. So the *only* nondeterminism is which move gets picked, and a run is exactly its list of moves:
  - the **checker** explores every move (BFS);
  - the **simulator** picks one per step (seeded RNG, or a script);
  - a **counterexample** is the list of moves the checker found. Replaying it through the same `apply` reproduces the same snapshots and the same trace hash.

That's why the checker and the simulator share one definition. Nothing is translated, so a counterexample runs as-is against any SUT version.

## 2. Core API (`fleetflight.core`)
| Name | Summary |
|---|---|
| `Move(name, args, injected)` | Frozen and hashable. `args` is a tuple of `(name, int\|str)` pairs. `TICK = Move("tick", (), False)`. It has `.label`, `.arg(k)`, `.to_json()` → `{name, args:{}, injected, label}`, and `Move.from_json`. |
| `TraceEvent(t_ms, name, detail, injected)` | What happened during a move. Display only: never hashed, never part of the state. |
| `Invariant(id, name, description, formula, check, bound_ms=None, timer_key=None)` | `check(state) -> bool` is a pure predicate on **one** state. Bounded properties keep a timer in the state: `timer_key` names the snapshot key holding the `t_ms` at which the bounded condition began (or `None` when it doesn't hold). |
| `Bounds(max_depth=120, max_injections=3, horizon_ms=4000)` | `max_depth` counts moves (ticks and injections). States with `t_ms >= horizon_ms` are checked but not expanded. |
| `Model` protocol | `name`, `version`, `sut`, `bounds`, `assumptions`, `invariants`, plus the methods `init()`, `moves(s)`, `apply(s, m)`, `describe()`, `snapshot(s)`. `apply` raises `ValueError` on a move that isn't enabled. |
| `State` | The model's own frozen, hashable dataclass with a `t_ms: int` field. The checker uses only `hash`, `==`, `.t_ms` and `snapshot()`. |
| `snapshot(s)` | A flat `dict[str, str\|int\|None]`. It must contain `t_ms`, every key in `describe()["snapshot_keys"]` (conventionally `bms`, `bus`, `hub`, `inv`, `nvm`) and every invariant's `timer_key`. Example value: `inv: "DISCHARGING 5000W seq41"`. |
| `SUT` protocol | `name`, `version`, `hub_init(nvm)`, `inv_init()`, and the pure hooks `hub_on_boot(nvm, now)`, `hub_on_msg(hub, msg, now)`, `hub_on_tick(hub, now)`, `inv_on_cmd(inv, msg, now)`, `inv_on_tick(inv, now)`. Each hook returns `HookResult(ctl, sends: tuple[Msg,…])`. |
| `Msg(kind, src, dst, fields)` | A message a controller sends. The **model** owns the bus: it assigns the message ids (e.g. `fault#1`) and delivery times. |
| `ControllerState` | Frozen and hashable, with `.mode: str` and `.view()`. The hub state also has `.nvm`, the only thing that survives a restart. The model reads nothing else. |
| `trace_hash(steps)` | `"sha256:"` + sha256 of `canonical_json([[move_json\|null, snapshot], …])`, where `steps[0]` is `(None, init snapshot)`. Display it with `short_hash` (the first 12 hex). |
| `counterexample_id(model, sut_id, inv_id, moves)` | `"cex-<8 hex>"`, a stable hash and never a counter. |
| `model_hash(describe_doc)` · `sut_id(sut)` · `parse_sut_id("v0.3.1")` · `split_assumption(s)` · `canonical_json(o)` | Helpers. |

In production, `SUT` becomes an adapter to real code: firmware compiled for SIL (via FFI), or run as a subprocess fed the same hook calls. Nothing else changes.

## 3. Determinism rules
1. No wall-clock time, no unseeded randomness, and no iteration over unordered containers without sorting first, anywhere that affects a trace. The only wall-clock values allowed are `wall_s`, `states_per_s`, `created_at` and `run_id`, all in reports.
2. `moves()` returns the same list in the same order for equal states.
3. No floats in states or snapshots: use integer W and ms. Snapshot values are `str | int | None` only (no `bool`).
4. Anything hashed goes through `canonical_json` (sorted keys, no whitespace, UTF-8).
5. Two `check` runs with the same model, SUT and bounds produce identical reports, apart from the fields in rule 1. Replaying a counterexample N times gives N identical hashes.

## 4. Files that cross stream boundaries (`schemas/`, draft 2020-12)
Every document has a top-level `"schema"` field (e.g. `"fleetflight/counterexample@1"`, constants `SCHEMA_*` in core). Hand-written fixtures in `fixtures/` also have `"_fixture": true`; real output **never** does, and the UI shows a MOCK DATA badge only when it is present. `fixtures/make_fixtures.py` regenerates them. Shared `$defs` live in `common.schema.json`.

| Schema | Written by | Path / endpoint | Key content |
|---|---|---|---|
| `describe` | `Model.describe()` | `GET /api/describe`, `describe --json` | components (owner `model`/`sut`), injectables and param domains, invariants, assumptions, bounds, constants, `snapshot_keys` (order, and `lane` = swimlane), `sut_versions` |
| `check-report` | checker | `out/check-<run_id>.json`, `GET /api/runs/<id>` | model, sut, bounds, assumptions, `stats` (states, transitions, `max_depth_reached`, `wall_s`, `new_states_per_depth[d]`, `complete`), each invariant PASS/FAIL + `counterexample` id, `verdict` |
| `counterexample` | checker | `out/<cex-id>.json`, `GET /api/cex/<id>` | `invariant`, `violated_at_ms`, `violation_duration_ms`, `trace[]` (step, t_ms, move, full snapshot, events, violations), `moves[]`, `ticks`, `trace_hash`, `search` |
| `replay-result` | sim | `POST /api/replay`, `replay --json` | the SUT used, per-step `match`/`diff`, `trace_hash` vs `expected_trace_hash`, `full_trace_hash`, `skipped_moves`, per-invariant results with `max_window`, `violation_window_ms` |
| `run-list` | serve | `GET /api/runs` | one summary row per check report in `out/` |

- **Replay rule.** A counterexample's `moves` (injections only, each with `tick_index` = the number of TICKs before it) plus `ticks` reproduce the whole path. For `k = 0..ticks`: apply every move with `tick_index == k` in list order, then apply `TICK` if `k < ticks`. `violated_at_ms == ticks * 50`.
  - `replay` then keeps TICKing up to `horizon_ms`, which defaults to the counterexample's `bounds.horizon_ms`.
  - It compares steps `0..len(cex.trace)-1`, and `trace_hash` covers exactly those steps.
  - A scripted move that isn't enabled on the new SUT is **skipped and listed**, never forced.
- **Windows.** For an invariant with a `timer_key`, a window is a maximal stretch where `snapshot[timer_key]` is non-null. It has `start_ms = value`, and `end_ms` = the first `t_ms` where it becomes null (`null` and `open: true` if the run ends first). `violation_window_ms` in a replay is the longest window of the counterexample's invariant; it drives the "fault → stop vs budget" bars.
- **Invariant results.** `PASS` means the invariant holds in every reachable state within bounds (checker), or in every step of the run (replay).

## 5. Stream entry points (Python)
- **02 model**
  - `fleetflight.models.load_model(name="core-ref", sut=None, bounds=None) -> Model`, where `sut` is `"v0.3.1"` or `"firmware-ref@v0.3.1"`, and `None` means the newest version.
  - `list_models() -> dict[str, list[str]]`
  - `fleetflight.sut.load_sut(spec) -> SUT` and `list_suts() -> list[str]` (oldest first).
- **01 checker**
  - `fleetflight.check.check(model, bounds=None, *, on_progress=None) -> CheckReport`. `bounds` defaults to `model.bounds`; pass the same `Bounds` to `load_model` and to `check`.
  - `CheckReport.to_json()`, and `CheckReport.counterexamples: dict[id, dict]`.
  - `write_report(report, out_dir) -> list[Path]` writes `check-<run_id>.json` and `<cex-id>.json`.
  - `on_progress(stats: dict)` is called every N states and is the only thing tied to wall time.
- **03 cli**
  - `fleetflight.sim.simulate(model, scheduler, horizon_ms) -> Run`, with the schedulers `SeededScheduler(seed, rates)` and `ScriptedScheduler(moves)`.
  - `fleetflight.sim.replay(model, cex, horizon_ms=None) -> dict` (replay-result).
  - `fleetflight.regress.generate(cex, out_dir) -> Path`.
  - `fleetflight.report.to_markdown(report) -> str` and `to_junit(results) -> str`.

## 6. CLI surface (`fleetflight <cmd>`)
| Command | Flags |
|---|---|
| `describe` | `--model core-ref` `--sut V` `--json` |
| `check` | `--model core-ref` `--sut V` `--depth N` `--injections N` `--horizon-ms N` `--out DIR` (default `out/`) `--json PATH` |
| `explain` | `<cex-id\|path>` `--out DIR` |
| `sim` | `--model` `--sut V` `--seed N` `--scenario NAME` `--horizon-ms N` `--json PATH` |
| `replay` | `--counterexample <id\|path>` `--sut V` (default: the counterexample's SUT) `--repeat N` `--horizon-ms N` `--json PATH` |
| `regress` | `--from <id\|path>` \| `--all`, `--out-dir tests/regress` `--junit PATH` |
| `report` | `PATH` `--markdown` \| `--junit` |
| `serve` | `--port 8765` `--out out/` (binds 127.0.0.1, read-only). Endpoints: `GET /api/describe`, `/api/runs`, `/api/runs/<id>`, `/api/cex/<id>`, `POST /api/replay {cex, sut}`. |

Exit codes: **0** all invariants pass · **1** an invariant fails · **2** usage or input error. CI depends on these.
`V` accepts `v0.3.1` or `firmware-ref@v0.3.1`. Counterexample ids are resolved as `<out>/<id>.json`.
