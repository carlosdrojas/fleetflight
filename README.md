# FleetFlight (mocks)

**Pre-release verification for distributed battery firmware.**
*Model the system. Break the assumptions. Replay the failure.*

This directory is **mocks only**: what the project would look like when built. Nothing here runs yet.
Every number in these files (state counts, timings, run durations) is **MOCKED**. The component
model is a **reference implementation we wrote**, not Base's Gen 3 architecture.

## The one-sentence claim we'd make in the video

> FleetFlight found a timing-dependent coordination bug in a *reference* BMS ↔ Hub ↔ Inverter
> implementation, produced a minimal counterexample, replayed it deterministically in an executable
> simulator, verified the fix against the exact same sequence, and turned it into a CI regression test.

## Files

| File | What it mocks |
|---|---|
| `mocks/index.html` | The visual demo: run summary, counterexample swimlane, replay before/after fix, CI check. Open in a browser. |
| `mocks/cli.md` | Terminal transcripts for every demo step (`check`, `explain`, `replay`, `regress`, `ci`). |
| `mocks/spec_sketch.py` | How the model is written: **one** transition definition shared by the checker and the simulator. |
| `mocks/counterexample-0017.json` | The artifact the checker emits and the replayer consumes. |
| `mocks/test_cex_0017.py` | The regression test generated from that counterexample. |
| `mocks/fleetflight-verify.yml` | GitHub Actions job that runs it on every firmware PR. |

## The bug the demo finds (in our reference implementation)

**Stale-command resurrection after hub restart.**

1. Inverter is discharging 5 kW under hub command `seq 41` (valid for 30 s).
2. BMS goes `FAULTED` (injected overtemp). It sends `FAULT` once (edge-triggered).
3. That message is delayed 400 ms (inside the assumed ≤ 800 ms bus latency bound).
4. Hub restarts while the message is in flight. Its RX buffer is cleared, so the fault is lost.
5. Hub boots, restores `seq 41` from NVM for "restart recovery", re-sends `DISCHARGE 5 kW`.
6. Inverter accepts it (not expired) and its watchdog is refreshed.
7. `BMS = FAULTED ∧ Inverter = DISCHARGING` lasts 600 ms > the 500 ms bound. **I1 violated.**

Without step 4, the same fault reaches the hub at t = 500 ms and the inverter stops at 550 ms: **PASS**.
That's the point of the demo: the happy-path test passes; only exhaustive ordering finds this.

**Fix, in two rounds (this is the best part of the demo):**
- *v0.3.2, hub-side:* boot into `DEGRADED`, drop the NVM command, send `STOP` on boot. Replaying
  cex-0017 **still fails**: shutdown takes 550 ms because the 400 ms hub boot alone eats the budget.
- *v0.3.3, local fallback:* the inverter shuts down after 200 ms without a hub heartbeat. cex-0017
  passes (300 ms) and the full check passes. The checker also reports the cost: every hub restart
  now idles the inverter for about 400 ms.
- The lesson is about architecture, not a patch: safety can't depend on a component that can restart.

On honesty: we write the reference hub *naively* (restart recovery that trusts NVM is a common,
reasonable-looking pattern), then let the checker find what's wrong with it. We say that out loud in
the video instead of pretending it's a Base bug.

## Build vs roadmap

| Layer | Hackathon | Roadmap |
|---|---|---|
| Model backend | Behavioral state machines (Python) | PLECS / SIL → HIL → physical Gen 3 |
| Checker | Explicit-state BFS over 100 ms ticks, bounded depth | TLA+/Apalache export for unbounded proofs |
| System under test | Reference hub manager | Real hub-manager code; SIL-compiled BMS/inverter firmware |
| Scenarios | Fault/timing injection enumerated by the checker | Seeded from real field telemetry sequences |
| Fleet | Stretch: instantiate verified Virtual Core × N | Fleet invariants under distributed failure |

## Explicit assumptions (shown on screen, not buried)

- **ASSUMED** bus latency ≤ 800 ms; messages can be delayed, dropped, duplicated, reordered.
- **ASSUMED** BMS fault message is edge-triggered; periodic status every 2 s.
- **ASSUMED** inverter holds last setpoint for 1 s without a hub command, then goes `IDLE`.
- **ASSUMED** shutdown bound 500 ms. (Real number would come from Base's safety requirements.)
- **OUT OF SCOPE** hardware interlocks (contactors, hardwired BMS trip). This verifies the *software*
  coordination layer, which is the layer that races.

## Why not just PLECS / TLA+ / unit tests?

- **PLECS** answers "does the power system behave correctly?" FleetFlight answers "does the software
  behave correctly when async components, comms, faults and timing interact?" PLECS is a future backend.
- **TLA+** checks a spec that drifts from the code. Here the checker and simulator execute the *same*
  transition functions, so a counterexample is directly runnable against the system under test.
- **Unit tests** check the orderings someone thought of. The checker checks all of them within bounds.

Prior art to acknowledge: FoundationDB / TigerBeetle deterministic simulation, Jepsen, TLA+ at AWS,
Antithesis. The combination we'd claim is narrower: shared-definition model checking → deterministic
replay → generated regression, applied to BMS/inverter/hub coordination.
