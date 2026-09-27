You are session **02 model** for FleetFlight. You're in worktree `../fleetflight-model` on branch `model`.

Read `sessions/_common.md`, `CONTRACT.md`, `src/fleetflight/core.py`, `README.md` and `mocks/spec_sketch.py` first. You own `src/fleetflight/models/`, `src/fleetflight/sut/` and `tests/models/`.

## Goal
Write the reference system `core-ref` (a behavioral model of BMS, bus, hub and inverter) and the system under test `firmware-ref` with three versions. Together they must honestly produce the demo story.

This is the part judges will scrutinize for "did you just plant a bug?". The bug has to come from a plausible, common design choice, and everything has to be labeled.

## Design
- **Environment (the model):**
  - **BMS:** HEALTHY / FAULTED / UNKNOWN. Sends FAULT edge-triggered, plus a status heartbeat every 2 s.
  - **Bus:** in-flight messages with delivery times. The adversary may delay (bounded by `LATENCY_MAX_MS = 800`), drop, duplicate or reorder.
  - **Hub lifecycle:** ONLINE / RESTARTING / DEGRADED. Restart takes `HUB_BOOT_MS = 400` and clears the RX buffer.
  - **Timers:** `fault_since_ms` and similar live in the state.
- **SUT (`src/fleetflight/sut/firmware_ref.py`):** the hub-manager and inverter-controller logic behind the contract's `SUT` hooks. Versions:
  - **v0.3.1:** hub restart recovery restores the last command from NVM and resends it if it hasn't expired. The inverter holds its last setpoint for 1 s without hub messages.
  - **v0.3.2:** hub boots DEGRADED, drops the NVM command and sends STOP on boot.
  - **v0.3.3:** v0.3.2 plus the inverter goes SHUTDOWN after `HUB_LOSS_TIMEOUT_MS = 200` without a hub heartbeat, and rejects commands from an older hub epoch.
  - Keep the SUT a clean seam: the model must never reach into SUT internals except through the hooks.
- **Invariants I1–I5**, as in README / mocks. I1 is bounded at 500 ms. Each needs `formula` text for display.
- **Injections**: bms_fault, hub_restart, bus_delay(msg, extra_ms in steps of 50–100), bus_drop, bus_dup, network_loss. Each is limited by `max_injections` (default 3).
  - Keep the branching factor small enough that the full check finishes in under ~60 s. Measure this and write it down.
- **Required from the contract:** `describe()` and `snapshot()`. Snapshots should read well in a swimlane, e.g. `inv: "DISCHARGING 5.0kW seq41"`.
- **Assumptions** list, word for word as the README's (adjusted to your real constants).

## Verify the story before the real checker exists
You don't have stream 01's checker. Use two methods:
1. **Scripted scenarios** in `tests/models/test_story.py`, applying explicit move lists:
   - Happy path (fault + delay, no restart) passes I1.
   - The v0.3.1 restart sequence violates I1.
   - The same sequence against v0.3.2 still violates I1, by a smaller margin.
   - Against v0.3.3 it passes.
   - Record the real millisecond numbers.
2. **A throwaway naive BFS** in `tests/models/_mini_bfs.py`, test-only. Run every version through it and confirm that v0.3.3 has no violations of any invariant within bounds.
   - If you find a *real* unexpected violation in I2–I5, **don't hide it by tweaking the invariant**. Write it up in status as a finding. It may be a better demo than the planned one.

## Anti-vacuity (important for credibility)
Add `tests/models/test_mutations.py`. For each invariant, create a deliberately broken SUT variant (a mutant) and assert the invariant FAILS for it. For example:
- I4: the inverter applies duplicate commands twice.
- I2: the hub ignores UNKNOWN.

This proves no invariant is trivially true. Report the mutant kill table in status; the pitch will use it.

## Sub-agents
When the model is done, spawn a sub-agent as an **adversarial reviewer**. Give it the model and SUT files and the README, and ask:
- (1) Is the v0.3.1 bug contrived, or a plausible real design?
- (2) Are any invariants vacuous or tuned to the story?
- (3) Which assumptions would a Base firmware engineer challenge first?

Act on real issues, and paste its verdict summary into your status file.

Commit at each milestone: environment, SUT versions, invariants, scripted story, mini-BFS, mutants, review.
