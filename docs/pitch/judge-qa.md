# Judge Q&A: the 12 hardest questions

The judges are Base engineers who know their firmware far better than we do. Rules for answering:
- Concede what's true, fast.
- Answer in one or two sentences, then stop.
- Never guess at Base internals. "I don't know how your hub does X. Here's how we'd find out" is a good answer.
- Numbers marked `<from demo run>` come from `STATUS.md` on `integration`.

---

**1. "Your model is made up. Why should I care what it proves?"**
> It is made up. core-ref is a reference model we wrote, and we say that on screen. What's real is the *machinery*: an exhaustive search over fault and timing orderings, a counterexample that replays byte-for-byte through the same transition code, and a pytest that CI runs on every change. The model is the part you'd replace with your code. The controller hooks (`hub_on_boot`, `hub_on_msg`, `inv_on_cmd`, …) are the seam where that happens.

**2. "Hardware interlocks would stop this. A hardwired BMS trip opens the contactor."**
> Probably, and it's out of scope on purpose (the assumptions screen says so). This checks the *software* coordination layer. Two reasons that still matters. First, an interlock trip is the last line of defense, so a software path that relies on it is a bug in its own right, and it shows up as nuisance trips and truck rolls. Second, not every invariant has an interlock behind it: I3 (no resurrected commands) and I4 (no duplicate actions) are about dispatch correctness, not only safety. If you tell us which faults are covered in hardware, we'd model the interlock as a component and change I1's budget to match.

**3. "State explosion. This can't scale."**
> It's bounded, and we say so: at most `<from demo run>` injections, a `<from demo run>` ms horizon, 50 ms ticks. Within those bounds the search is exhaustive; outside them it says nothing. The core-ref run is `<from demo run>` states in `<from demo run>` s on one laptop thread. Why a small bound is still useful: our bug needs three injections, and the "small scope" bet is that many coordination bugs need only a few faults. That's a bet, not a proof. The AWS TLA+ paper's DynamoDB bug had a 35-step shortest trace, which is also why nobody finds these by hand. The levers if it grows are symmetry reduction, partial-order reduction, and splitting invariants per component. We haven't built them.

**4. "How would you get a model of *our* real firmware?"**
> Not by hand-writing a second copy. That's how specs drift. Step 1: model only the environment (bus, restarts, BMS faults), which is what core-ref's model layer already is, and call your real hub-manager logic through the SUT hooks, in Python or through FFI. Step 2: compile the BMS and inverter decision logic for SIL behind the same hooks. Spin has done this with real C since the 2000s (`c_code`, JPL), so it's a known path. The parts we'd need from you are the message contracts and the timing budgets, not the firmware internals.

**5. "Why not TLA+ or P? They already do this."**
> They do most of it, and we cite them. TLA+ checks a spec separate from the code. The AWS paper itself says they don't know if the code matches the design. P is the closest to what we built. It's used at AWS, it has a replayable `.schedule` file, and it's been used on the FreeRTOS OTA protocol. Its default checker is randomized, and exhaustive search is the separate PEx backend. Its standard timer idiom is a nondeterministic timeout with no duration. We needed millisecond deadlines ("stop within 500 ms"), so our model has a clock. We picked a Python library over a new language for three reasons: the transition code is ordinary Python, a counterexample *is* a pytest, and one command re-runs it against v0.3.1/2/3. In a hackathon that was the shortest path to "a firmware engineer can read the model and the test". At Base, if the firmware team is happy writing P, use P. The workflow is the point, not our checker.

**6. "Your latency numbers are invented. Our bus doesn't behave like that."**
> Right. ≤ 800 ms, a 400 ms boot and a 500 ms budget are all ASSUMED and printed in every report. They're parameters, not code: change them and re-run. The honest reading of a PASS is "safe *if* latency ≤ 800 ms". Where real numbers would come from: field telemetry (message timestamps across restarts), your safety requirements for the budget, and boot-time measurements. A nice side effect: the checker tells you which assumption the result depends on. v0.3.2 fails *because* boot takes 400 ms.

**7. "This is three devices. We have tens of thousands of homes."**
> Fleet-scale model checking isn't what this does, and we don't claim it. The per-home coordination protocol is where these races live, and every home runs the same one, so verifying it once covers the fleet for that class of bug. Fleet-level properties like "never dispatch to a stale device" or "aggregate dispatch within available capacity" are a different tool: seeded simulation of N verified cores, with the same determinism so that a failing seed replays. That's `<stretch: fleet — built / not built, from STATUS.md>`.

**8. "What would you do in week 1 at Base?"**
> Listen before building. Day 1–2: sit with firmware and the hub team, and collect the three incidents or near-misses that were hardest to reproduce. Day 3–4: model the environment around *one* of them (the message types, restart behaviour and timing budget) and call the real hub-manager logic through the hooks. Day 5: see whether the checker reproduces the known incident. If it does, that's the demo that earns a CI slot. If it doesn't, we've learned which assumption is wrong, which is useful too.

**9. "How do you know the checker is right? Maybe it misses states."**
> We tested the checker independently. A separate brute-force DFS oracle, written without looking at the checker, agrees with it on PASS/FAIL and on minimum counterexample length across 14 model/bounds cases (`tests/check/test_crosscheck.py`). Minimality on the race toy is proven by enumerating every sequence up to length 4. Rebuilding the path re-applies each move and raises if the model is nondeterministic, so a counterexample that wouldn't replay is never emitted.

**10. "Your v0.3.3 fix idles the inverter on every hub restart. That costs us money."**
> Yes, and the tool is what surfaced it: about `<from demo run>` ms of idle per restart. Whether that's acceptable is a product decision (how often hubs restart, times the value of that dispatch), and we'd rather it were a number on a PR than a surprise in production. A cheaper variant is to hold the setpoint but cap power until the hub re-confirms the BMS. That's exactly the kind of change you'd run through the same counterexample before merging.

**11. "Isn't this just property-based testing / Hypothesis?"**
> It's close, and Hypothesis's stateful testing inspired the "failure → minimal program → paste into a test" part. The difference is completeness: Hypothesis samples randomly, while this enumerates every ordering within the bounds. So a PASS means "no counterexample exists within these bounds", not "we didn't find one in N tries". For a safety invariant that difference is the whole point.

**12. "Does your 'deterministic replay' survive real firmware with threads and interrupts?"**
> Not by itself. Determinism here comes from the model owning time and the bus, and from pure controller hooks. Real firmware keeps that property only if it's driven through the hooks, with no wall clock and no free-running threads. That's the same discipline FoundationDB and TigerBeetle impose on their production code. For an RTOS task you'd run it in SIL with a simulated clock. On HIL you lose bit-exact replay, and we'd say so: HIL confirms the scenario, it doesn't replay the hash.

---

## Backup answers (if there's time)

- **"Did you find a bug in Base firmware?"** No. We never had Base firmware. The bug is in firmware-ref v0.3.1, which we wrote naively on purpose. "Restart recovery that trusts NVM" is a common pattern.
- **"Is 50 ms fine enough?"** For coordination timing at 100s of ms, yes. For control loops, no; that's PLECS/HIL territory. One discretization artifact: a window can read 550 ms and still PASS if the timer clears on the same tick. status/01-checker.md documents this.
- **"Why Python? It's slow."** `<from demo run>` states/s single-threaded on the core-ref-shaped bench model (measured ~113k–172k, see `status/01-checker.md`). That's fast enough for these bounds, and it's readable by firmware and cloud engineers alike. The hot path could move to Rust (Stateright is the model) if the bounds need to grow.
- **"Who else does this for batteries?"** We searched and found no open tool doing exhaustive cross-device fault ordering for BMS/hub/inverter. That's absence of evidence, not proof. MathWorks Simulink Design Verifier does formal counterexample → test harness for single Stateflow controllers, and Typhoon HIL has pytest-based HIL tests. See `prior-art.md`.
