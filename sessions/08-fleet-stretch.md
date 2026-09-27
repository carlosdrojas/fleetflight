You are session **08 fleet (stretch)** for FleetFlight. Only start this if the integrator reports the core demo working on `integration` before **Sunday 3 AM**. Otherwise don't run it.

Work in worktree `../fleetflight-fleet` on branch `fleet`, created from `integration`. You own `src/fleetflight/fleet/` and `tests/fleet/`.

Read `sessions/_common.md`, `CONTRACT.md` and `STATUS.md` first.

## Goal
A small, honest extension that answers "can many individually fallible cores behave like one reliable plant?", using the verified core model.
- `fleet --core core-ref@v0.3.3 --n 500 --seed S --minutes 30 --inject "hub_restart:rate=…"`
  - Instantiates N cores with independent seeded adversaries, plus a simple fleet controller that dispatches a target kW across available cores.
  - Uses the **same** model code for each core; no second battery model.
- **Fleet invariants:**
  - F1: dispatched kW ≤ the sum of available capability.
  - F2: no dispatch to a core whose telemetry is stale.
- On violation, output the seed, core id and time, plus a single-core counterexample file that `fleetflight replay` can load.
- Simulation, not model checking: say this clearly in the output and docs. Exhaustive search at fleet scale isn't the claim.
- Performance: report cores × sim-seconds per wall-second.

If it isn't solid by **Sunday 6 AM**, abandon it and write what you learned in `status/08-fleet.md`. The core demo matters more.
