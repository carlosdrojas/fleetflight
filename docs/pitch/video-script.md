# FleetFlight: 5-minute demo video script

**Status: numbers filled from `STATUS.md`** (integrator, real run on 2026-09-27). The 1:00–2:15 walkthrough and the 2:45 beat were rewritten to follow the real counterexample (fault + link loss), not the mock restart story. Don't record with mock numbers: `1,284,511`, `41.2 s`, `cex-0017`, `600 ms`, `550 ms`, `300 ms` and `~400 ms` all come from `mocks/` and are placeholders.

**Before recording, check the story against real output.** The narration follows the demo story in `sessions/_common.md`. The real model (`core-ref`, branch `model`) differs from the mocks in ways that change the wording:
- It uses 50 ms ticks, not 100 ms.
- The BMS FAULT is retransmitted every 100 ms until the hub ACKs it, unless the model is run with `fault_retx_ms=None`.
- The dispatch expires at 3 s, not 30 s.

Done by the integrator: the 1:00–2:15 steps below follow `fleetflight explain cex-286e0592` (the real shortest counterexample). If a fresh run produces a different id, re-check the narration against its `explain` output.

**Recording format** (from the event's *Demo Video Instructions*, see `submission-checklist.md`):
- Loom, camera on, 2–5 minutes, with a team intro in the first 30 s.
- Show the product live with as few cuts as possible, and show the console output.
- Close with the "so what".

This script puts a 5-second intro at the front of the problem beat instead of adding a separate 30 s intro.

**Target:** about 700 spoken words, roughly 140 wpm. Words in *italics* are stressed. Rehearse once against a timer. If you run long, cut from 1:00–2:15, never from 2:45–3:45.

**Screen setup:** left half terminal (large font, ≥ 18 pt, dark theme), right half UI at `fleetflight serve` (`http://127.0.0.1:8765`). Record at 1920×1080.

---

## 0:00–0:30 · The problem

**On screen:** camera (Loom bubble) plus the UI header: "FleetFlight · pre-release verification for battery firmware". Then the pipeline strip: spec + invariants → checker → counterexample → replay → fix → regression → CI.

**Spoken:**
> Hi, I'm `<name>`, and this is FleetFlight.
>
> A home battery is three computers that have to agree: the BMS, the hub and the inverter. They talk over a bus that can delay messages, and any of them can reboot. The dangerous bugs live in the *orderings*: a fault message is in flight at the exact moment the hub restarts. You can't unit-test that, and on a bench you'd need to hit a 50-millisecond window by hand. So these bugs tend to show up after release, in the field.
>
> FleetFlight finds them before release, on a laptop.

---

## 0:30–1:00 · Why the obvious test passes

**On screen:** terminal.
```
fleetflight sim --model core-ref --sut v0.3.1 --scenario bms-fault-basic --seed 1
```
Highlight the `I1 FAULT_SHUTDOWN_BOUNDED PASS` line and the fault→shutdown time.

**Spoken:**
> Here's the obvious test. The inverter is discharging at 5 kilowatts, and the BMS faults. The fault reaches the hub, the hub sends STOP, and the inverter is shut down in 200 milliseconds, inside our 500-millisecond budget. Green.
>
> But that's *one* ordering. The question a safety engineer actually asks is: does this hold for *every* ordering of faults, delays and restarts the system is allowed to see?

---

## 1:00–2:15 · The check finds a counterexample

**On screen:**
1. Terminal: `fleetflight check --model core-ref --sut v0.3.1`. Let the progress bar run (show the real state count). Pause on the ASSUMPTIONS block, then on the result table: I1 FAIL with the counterexample id.
2. UI: open that run and step through the counterexample swimlane (BMS / bus / hub / inverter lanes) one step per sentence below.

**Spoken:**
> So we check. This is a bounded model checker: breadth-first search over every allowed choice. At each 50-millisecond tick, the adversary can fault the BMS, restart the hub, or delay, drop or duplicate a message, or cut the hub-to-inverter link, with up to 3 injections and a 4-second horizon.
>
> Notice the assumptions print *first*. Bus latency up to 800 milliseconds, hub boot 400, hardware interlocks out of scope. Everything we prove is conditional on these, so they're on screen, not in a footnote.
>
> 1.29 million states, about 38 seconds. Invariant I1 fails, and so do I2 and I4. Because the search is breadth-first, this is a *shortest* counterexample: 12 moves, two injections and ten ticks.
>
> Let's walk it. *[swimlane step 1]* The BMS faults and sends FAULT. *[step 2]* At the same instant, the hub-to-inverter link drops. *[step 3]* The hub gets the fault, ACKs it and sends STOP, but the STOP never reaches the inverter. *[step 4]* The inverter does what v0.3.1 was written to do: hold its last setpoint for a second without hub messages. So it keeps discharging.
>
> *[violation marker]* The BMS is faulted and the inverter is still discharging at 500 milliseconds, the edge of the budget. Replayed to the end, it runs for 1,050.
>
> Every step in that trace is individually reasonable. That's why nobody writes this test.

---

## 2:15–2:45 · Deterministic replay

**On screen:** terminal.
```
fleetflight replay --counterexample cex-286e0592 --repeat 100
```
Show the 100 identical `trace_hash` lines (or the summary `100/100 identical`). Then the UI replay view showing "trace hash matches checker ✓".

**Spoken:**
> A counterexample you can't reproduce is a rumor. This one is a list of moves, and the simulator executes it through the *same* transition functions the checker searched. Nothing gets translated. We replay it a hundred times and get a hundred identical trace hashes: b545736726cb. The hash matches the checker's byte for byte.

---

## 2:45–3:45 · Fix, still fails, real fix, and the trade-off  ← strongest beat

**On screen:**
1. UI: SUT selector at v0.3.2 (hub boots DEGRADED, drops the NVM command and sends STOP on boot).
2. Terminal: `fleetflight replay --counterexample cex-286e0592 --sut v0.3.2`. I1 still FAILs; show the fault→shutdown bar against the 500 ms budget line.
3. UI: switch to v0.3.3 (inverter goes SHUTDOWN after 200 ms without a hub message). Replay: PASS, bar well under budget.
4. Terminal: `fleetflight check --model core-ref --sut v0.3.3`: all invariants PASS, with the worst-case windows in the Detail column.

**Spoken:**
> So we fix the hub, which is the obvious move. The same check also flagged I2: after a restart, v0.3.1 restores DISCHARGE from NVM without hearing from the BMS. Version 0.3.2 fixes that: on boot, go DEGRADED, forget the NVM command, send STOP.
>
> And we replay the *exact same* fault sequence against it. *Still fails*: 1,050 milliseconds. The hub did its job; the STOP just can't reach an inverter that's waiting on the hub. I fixed the wrong component, and the tool caught it.
>
> The real rule is architectural: *safety can't depend on a component you can lose*. Version 0.3.3 moves the decision down to the inverter. No hub message for 200 milliseconds means shut down locally.
>
> Same sequence: pass, 250 milliseconds. And not just this sequence. The full check, 1.19 million states, passes every invariant, with a worst case of 450.
>
> That safety has a price we can measure too. In this model, after a hub restart v0.3.3 sits idle for the rest of the dispatch, because we don't model the cloud re-dispatching. That's a trade-off someone should weigh on the PR, not discover in the field.

---

## 3:45–4:15 · Regression test and CI

**On screen:**
1. Terminal: `fleetflight regress --from cex-286e0592`, then `pytest tests/regress -q` (green against v0.3.3). Optional: `FLEETFLIGHT_SUT=v0.3.1 pytest tests/regress -q` goes red.
2. Briefly: the generated test file, with the moves list and the pinned assertions.
3. `.github/workflows/fleetflight-verify.yml`, or the demo PR's checks, showing the two lanes: `regress` (fast) and `check` (bounded).

**Spoken:**
> That counterexample is now a pytest file, generated rather than hand-written, with the moves pinned. In CI there are two lanes. The fast lane replays every stored counterexample in about half a second and blocks the merge. The slow lane re-runs the bounded check against the PR's code. If anyone brings back the one-second hold, this test goes red on the pull request, not in the field.

---

## 4:15–4:45 · What we don't claim, and what's next

**On screen:** UI assumptions panel (ASSUMED / OUT OF SCOPE chips), then the "model fidelity ladder": Behavioral model (BUILT) → PLECS / SIL → HIL → physical (ROADMAP).

**Spoken:**
> What we *don't* claim. core-ref is a reference model we wrote. It is *not* Base firmware, and we didn't find a bug in your system. The latencies and budgets are assumptions, and a pass only holds inside those bounds. Hardware interlocks are out of scope. And the techniques aren't new: Spin, TLA+, P and FoundationDB got there first. We fitted that workflow to battery firmware releases.
>
> What's next is making the model less made-up. The controller hooks are the seam: swap in real hub code, then SIL-compiled firmware, then run the same counterexamples on HIL. And seed the adversary from field telemetry, so the orderings we search are the ones the fleet actually sees.

---

## 4:45–5:00 · Close

**On screen:** the pipeline strip again, the repo URL, and the camera.

**Spoken:**
> The happy path passed. An exhaustive check found the ordering that didn't, replayed it exactly, caught our half-fix, and turned the lesson into a CI gate. That's FleetFlight. Thanks.

---

## Numbers to fill in (checklist for the integrator)

| Where | Placeholder | Source |
|---|---|---|
| 0:30 | happy-path fault→shutdown ms | `fleetflight sim … --scenario bms-fault-basic` |
| 1:00 | max injections, horizon | `check` header (`Bounds`) |
| 1:00 | states explored, wall seconds | `check` stats, v0.3.1 |
| 1:00 | counterexample length (moves) and id | `check` output / `<cex-id>.json` |
| 1:00 | I1 violation ms | `explain <cex-id>` (`violation_duration_ms`) |
| 2:15 | 100/100 identical hash (short hash) | `replay --repeat 100` |
| 2:45 | v0.3.2 fault→shutdown ms | `replay --sut v0.3.2` (`violation_window_ms`) |
| 2:45 | v0.3.3 fault→shutdown ms | `replay --sut v0.3.3` |
| 2:45 | v0.3.3 I1 worst case | `check --sut v0.3.3` (`worst_case_ms`) |
| 2:45 | inverter idle per hub restart (trade-off) | whatever the checker/report prints; **if nothing computes it, cut that sentence** |
| 3:45 | regress fast-lane seconds | `pytest tests/regress -q` or the CI log |

If any beat can't be shown live (for example the trade-off number isn't computed by code), cut the sentence rather than say it. See `claims-audit.md`.
