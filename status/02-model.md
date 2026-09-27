# 02 model: status

**Done** (pending the review follow-ups below). Branch `model`. `pytest -q`: all pass (74 tests, ~11 s).
`core-ref` is a reference model we wrote; `firmware-ref` is reference firmware we wrote. Neither is Base Gen 3.

## What exists
- `src/fleetflight/sut/firmware_ref.py`: `FirmwareRef(version)` for v0.3.1 / v0.3.2 / v0.3.3 behind the pure `SUT` hooks. `load_sut`, `list_suts` in `sut/__init__.py`.
- `src/fleetflight/models/core_ref.py`: `CoreRef` (environment, injections, invariants I1–I5, assumptions, `describe()`, `snapshot()`, `SCENARIOS`). `load_model`, `list_models` in `models/__init__.py`.
- `tests/models/`: `test_model.py` (contract conformance, describe validates against the schema, determinism, seam), `test_story.py` (scripted demo story with real numbers), `test_mini_bfs.py` + `_mini_bfs.py` (THROWAWAY naive BFS, test-only), `test_mutations.py` (anti-vacuity kill table), `_script.py` (replay-rule helper).

## Design in one screen
- Tick = 50 ms. TICK order: hub boot completes → due deliveries (by due time, then id) → BMS STATUS (every 2000 ms) and FAULT retransmit → `hub_on_tick` → `inv_on_tick` → invariant timers.
- **BMS** (model): HEALTHY/FAULTED. FAULT sent on the edge, **retransmitted every 100 ms until the hub ACKs** (see Finding 1). STATUS every 2 s.
- **Bus** (model): every message takes 50 ms. The adversary can `bus_delay` (+100/200/400/700 ms, total ≤ 800 ms), `bus_drop`, or `bus_dup` any in-flight message. Delay gives reordering. Ids are `<kind>@<sent_ms>`, e.g. `fault@100`, `cmd@600.2`, `cmd@100+dup`: deterministic, and states from different paths merge.
- **Hub lifecycle** (model): `hub_restart` → RESTARTING for 400 ms. Messages queued for the hub are lost, and so are messages that arrive while it is down. Then `hub_on_boot(nvm)`; only NVM survives.
- **Link** (model): `network_loss` takes the hub↔inverter link down for the rest of the run.
- **Scenario at t=0**: the cloud sends DISPATCH (DISCHARGE 5000 W, expires 3000 ms) to the hub through `hub_on_msg`; the hub commands the inverter (seq41, epoch 1). The hub re-sends its current command every 100 ms (the inverter's heartbeat).
- **Seam**: the model reads only `ctl.mode`, `ctl.view()` and opaque `hub.nvm`. A test asserts `core_ref.py` never imports `firmware_ref`.

## Firmware versions
| Version | Hub | Inverter |
|---|---|---|
| v0.3.1 | Boot: restore last command from NVM and re-send it if not expired | Holds setpoint 1000 ms without hub messages, then IDLE. Dedupe: same seq as current = refresh, anything else is applied |
| v0.3.2 | Boot DEGRADED, drop the NVM command, send STOP | same as v0.3.1 |
| v0.3.3 | same as v0.3.2 | SHUTDOWN after 200 ms without a hub message; applies only strictly newer `(epoch, seq)` (older epoch **or** older seq rejected) |

Deviation: the brief says v0.3.3 "rejects commands from an older hub epoch". Epoch-only is not enough. The mutant `InvEpochOnlyOrdering` still fails I4 (a stale seq41 from the same epoch is re-applied), so v0.3.3 orders on `(epoch, seq)`.

## Invariants
| Id | Formula | Notes |
|---|---|---|
| I1 FAULT_SHUTDOWN_BOUNDED | `G( bms=FAULTED ∧ inv=DISCHARGING → (t − i1_since_ms) < 500 )` | timer_key `i1_since_ms` = start of the current FAULTED∧DISCHARGING stretch |
| I2 NO_HIGH_POWER_WHEN_UNKNOWN | `G( inv_watts > 1000 → inv_basis ≠ UNKNOWN )` | `inv_basis` = what the hub knew about the BMS (from deliveries since its last boot) when it sent the command the inverter is running or refreshing. Model-side bookkeeping, not a SUT field |
| I3 NO_RESURRECTED_COMMANDS | `G( inv=DISCHARGING → inv_cmd.expires_ms > t )` | expiry taken from the delivered message, not from the SUT |
| I4 IDEMPOTENT_COMMANDS | `G( ∀(epoch,seq): applied_count ≤ 1 )` | "applied" = the inverter view's `applies` counter went up |
| I5 COMMS_LOSS_SAFE_FALLBACK | `G( inv=DISCHARGING ∧ silent(hub→inv) → (t − i5_since_ms) < 1500 )` | silent = more than 100 ms since the last hub message was delivered; timer = time of that message |

**Deadline semantics (note for 01 checker / 03 sim):** bounded invariants fail when `t − since >= budget` while the condition still holds. So I1 PASS ⟺ every window (timer start → first state where it's null, the replay-result definition) is ≤ 500 ms, and checker and replay bars always agree. Consequence: at the *first* violating state, `violation_duration_ms = t − since` is exactly 500 (the budget). The meaningful "how late" number is the window. Example: v0.3.2 violates at t=600 with duration 500, and its window is 550.

## Real numbers (all measured; `tests/models/test_story.py` asserts them)
Scripted, horizon 3500 ms. Window = fault→stop.

| Scenario | v0.3.1 | v0.3.2 | v0.3.3 |
|---|---|---|---|
| `bms-fault-basic` (fault@100, FAULT +400 ms) | PASS, 200 ms | PASS, 200 ms | PASS, 200 ms |
| `restart-during-fault` (README: fault@100, FAULT +400, restart@200) | **I1 FAIL** at 600, window **600 ms** (+100); **I2 FAIL** at 650 | **I1 FAIL** at 600, window **550 ms** (+50) | **PASS**, window **400 ms** (−100) |
| `fault-during-link-loss` (fault@0 + network_loss@0) | I1 FAIL, 1050 ms | I1 FAIL, 1050 ms | PASS, 250 ms |
| `stale-reorder` (fault@100, `cmd@100` +100) | I4 FAIL at 250 | I4 FAIL at 250 | PASS |
| `restart-only` (restart@0) | I2 FAIL at 450 | PASS | PASS |

In the happy path, the delayed FAULT doesn't matter: the 100 ms retransmit reaches the hub at 150 + 100. The README story ("reaches hub at 500, stops at 550") was written for a single-shot FAULT, which Finding 1 rules out.

## Mini BFS (throwaway, `tests/models/_mini_bfs.py`), default bounds `max_depth=120, max_injections=3, horizon_ms=3500`
Measured on this laptop (Python 3.13, single process), full exploration (`complete`):

| SUT | States | Transitions | Wall | Failing invariants (minimal counterexample) |
|---|---|---|---|---|
| v0.3.1 | 1,093,851 | 1,567,342 | 32.3 s | I1 (bms_fault + network_loss @0, violated 500 ms, depth 12) · I2 (hub_restart, 450 ms, depth 10) · I4 (bms_fault + bus_delay(cmd@100, 100), 250 ms, depth 7) |
| v0.3.2 | 1,074,151 | 1,546,146 | 31.1 s | I1 (same as v0.3.1) · I4 (same) |
| v0.3.3 | 997,171 | 1,460,464 | 29.3 s | **none** |

- With the full 100 ms delay domain `{100..700}`, v0.3.3 also has no violations: 2,399,115 states in 136.7 s. That's too slow for the demo, so the default domain is `{100, 200, 400, 700}` (1- and 2-tick reorders plus near-max latency).
- Speedups that got it under 60 s: STOP commands never expire (a timestamped expiry kept states from merging: 289k → 71k at 2 injections), and the tick builds `State` directly instead of calling `dataclasses.replace`.
- `pytest -q` runs the BFS at 2 injections. `FLEETFLIGHT_FULL=1 pytest tests/models/test_mini_bfs.py` runs the default bounds.

## Findings (real, not planted, and not hidden)
1. **The brief's environment makes I1 unachievable for any firmware.** With a single-shot FAULT on a bus that can drop or delay by up to 800 ms, one dropped FAULT leaves the hub unaware until the next 2 s STATUS. Every version fails I1 (window 2000 ms); pinned by `test_finding_single_shot_fault_breaks_every_version`. We therefore ASSUME the BMS retransmits FAULT every 100 ms until ACKed, and say so in the assumptions. `load_model(..., fault_retx_ms=None)` reproduces the finding. This could be a demo beat: "the checker caught our spec, not just our code."
2. **The minimal I1 counterexample for v0.3.1 is fault + link loss, not the restart story.** Both have the same root cause: safety waits on the hub while the inverter holds its setpoint for 1 s. Replaying the link-loss counterexample against v0.3.2 fails by the *same* margin (1050 ms), because the hub fix doesn't touch it. With the fault model scoped to `bms_fault, hub_restart, bus_delay` (mini BFS, default bounds; v0.3.1 568k states / 16.2 s, v0.3.2 560k / 15.7 s, v0.3.3 544k / 14.6 s with no violations), the minimal I1 counterexamples are restart ones:
   - v0.3.1: `bms_fault@0, hub_restart@0, hub_restart@400` (depth 13; a second restart right after boot).
   - v0.3.2: `bms_fault@0, bus_delay(fault@0, +100)@0, hub_restart@100` (depth 13). This is the README pattern compressed. Its windows are **600 / 550 / 400 ms** for v0.3.1 / v0.3.2 / v0.3.3, the same margins as the README sequence.
3. **v0.3.1 also fails I2**: restart recovery re-commands 5 kW while the rebooted hub has no BMS report. This is the actual "stale-command resurrection" harm. The resurrection itself does not lengthen the I1 window, because the inverter was still holding anyway.
4. **v0.3.1 and v0.3.2 fail I4**: "last-seen" seq dedupe re-applies a reordered stale command after a STOP. v0.3.3's `(epoch, seq)` ordering fixes it, and epoch-only ordering would not.

## Anti-vacuity: mutant kill table (`python -m tests.models.test_mutations`)
Each mutant is v0.3.3 with one change. Each is searched with the mini BFS at the smallest bounds shown in the test. The unmutated v0.3.3 passes the same bounds.

| Mutant of v0.3.3 | What it breaks | Target | Killed | Failed invariants | Counterexample |
|---|---|---|---|---|---|
| HubIgnoresFault | hub never reacts to FAULT (still ACKs it) | I1 | yes | I1 | bms_fault; violated at 500 ms, depth 11 |
| HubIgnoresUnknown | DEGRADED hub resumes the 5 kW dispatch without waiting for a BMS report | I2 | yes | I2 | hub_restart; violated at 450 ms, depth 10 |
| InvIgnoresExpiry | inverter never checks expires_ms | I3 | yes | I3 | (no injection); violated at 3000 ms, depth 60 |
| InvAppliesDuplicates | inverter re-applies a command with the same (epoch, seq) | I4 | yes | I4 | (no injection); violated at 150 ms, depth 3 |
| InvHoldsForever | inverter has no hub-loss fallback at all | I5 | yes | I5 | network_loss; violated at 1500 ms, depth 31 |
| InvEpochOnlyOrdering | inverter rejects older epochs only (the literal v0.3.3 brief), not older seqs | I4 | yes | I4 | bms_fault, bus_delay(msg=cmd@100, extra_ms=100); violated at 250 ms, depth 7 |

6/6 killed. Every invariant has at least one mutant that breaks it.

## Adversarial review
(pending)

## Notes for other streams
- `load_model(name, sut, bounds, **options)`: `sut` may also be a SUT object (the mutants use this). Options: `fault_retx_ms` (None = single-shot), `injections` (a subset of `bms_fault, hub_restart, network_loss, bus_delay, bus_drop, bus_dup`), `delay_steps_ms`.
- `fleetflight.models.SCENARIOS[name] = (description, [(t_ms, Move), ...])`: `bms-fault-basic`, `restart-during-fault`, `fault-during-link-loss`, `stale-reorder`, `restart-only`, `link-loss`. Injections at `t` apply before the TICK that leaves `t` (the replay rule with `tick_index = t/50`).
- The snapshot has more keys than the fixture: `hub_bms`, `link`, `inv_basis`, `i4_repeat` (all `lane: false`). `describe()["snapshot_keys"]` lists them in order.
- Trace event names: `bms_fault`/`hub_restart`/... (injected), `send`, `refresh` (periodic command re-send), `deliver`, `lost`, `delayed`, `duplicated`, `hub_boot`, `inv_mode`, `inv_reapply`.

## CONTRACT REQUEST
- **CLI `check --only INJ[,INJ...]`** (03 cli), passed through as `load_model(..., injections=...)`. It scopes the fault model, e.g. `--only bms_fault,hub_restart,bus_delay` so the minimal I1 counterexample is a restart story (see Finding 2 for exactly which). This is a real feature ("verify against the faults your hardware can actually produce"). Until it lands, `sim --scenario restart-during-fault` plus `replay` shows the same sequence.
- No change to `core.py` or the schemas is needed.
