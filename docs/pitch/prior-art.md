# Prior art

Researched 2026-09-26 by five parallel research agents. They covered FoundationDB/VOPR/Antithesis, Jepsen/TLA+/Spin, P/Coyote, PLECS/Typhoon, and a sweep for tools that share code between checker and simulator.
- Each **high-overlap** verdict was re-checked by opening the primary source; those rows are marked ✔ *re-verified*.
- Other rows cite pages the agents report having opened.
- A fetch that failed is marked as such and not cited as read.

## Bottom line (read this first)

**The technique is not new.** Every link in our pipeline exists in prior work:

| Link in the FleetFlight pipeline | Already done by |
|---|---|
| Exhaustive explicit-state checking of async protocols | Spin (1980s–), TLA+/TLC, P's PEx backend, UPPAAL |
| Model check → counterexample → executable replay of real code | **Spin `c_code`** (real C inside the verifier; `pan -r` replays the trail) |
| One definition that is both model-checked and run | **Stateright** (Rust actors, "run on a real network without being reimplemented") |
| Adversarial fault injection + deterministic replay of the failure | FoundationDB, TigerBeetle VOPR, Antithesis, **P**, Coyote |
| Minimal failing sequence → pasteable regression test | **Hypothesis** stateful testing |
| Formal counterexample → test harness, *for BMS-style controllers* | **Simulink Design Verifier** (harness model; MathWorks ships a Stateflow BMS example) |
| Model checking an embedded IoT firmware *protocol* | **P** on the AWS FreeRTOS OTA library |

So we **must not** claim deterministic replay, shared checker/simulator code, "model check → test", or "model checking firmware protocols" as new. Base engineers who've used P at AWS, or who know FoundationDB, will spot it.

**What we claim instead** is at the end of this file.

---

## Deterministic simulation testing (randomized, real code)

### FoundationDB simulation testing
- **Read:** https://apple.github.io/foundationdb/testing.html. The SIGMOD 2021 paper PDF didn't parse, so it isn't cited.
- **What it does:** runs a whole FDB cluster (network, machines, datacenters) single-threaded in one process, on a simulated clock. It injects machine kills, partitions and disk faults at random, with the same code as production. Determinism makes any failing run repeatable.
- **Quote:** "Determinism is crucial in that it allows perfect repeatability of a simulated run, facilitating controlled experiments to home in on issues."
- **Overlap: partial.**
  - Same determinism and replay idea, and FDB runs *real production code*, which we don't.
  - It samples randomly and isn't exhaustive. It has no minimality guarantee and targets a distributed database, not a device.
  - FleetFlight searches every ordering within bounds and returns a shortest counterexample, but against a model.

### TigerBeetle VOPR
- **Read:** https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/internals/vopr.md
- **What it does:** a deterministic simulator of a TigerBeetle cluster with stubbed clock, network and disk. A random seed sets the fault parameters (drops, partitions, storage corruption), and a seed plus the git commit reproduces any bug.
- **Quote:** "Because our simulator is deterministic based on a seed number and the Git commit, we can perfectly reproduce any bugs discovered in testing."
- **Overlap: partial, conceptually close.**
  - "Seed + commit reproduces the bug" is the same workflow as our "counterexample + firmware version replays".
  - VOPR is randomized, runs real Zig code, and is a database.

### Antithesis
- **Read:** https://antithesis.com/docs/introduction/how_antithesis_works/ and https://antithesis.com/blog/deterministic_hypervisor/
- **What it does:** a commercial platform that runs your real, containerized system in a deterministic hypervisor. It injects faults, explores timelines with guided search, checks declared properties, and makes every bug reproducible and rewindable.
- **Quote:** "The Antithesis environment is fully deterministic. This makes every bug we find perfectly reproducible…"
- **Overlap: partial.**
  - It's the strongest commercial version of "fault injection + deterministic replay", and it runs *unmodified real software*.
  - It uses guided random search, not exhaustive search.
  - We found no primary source on MCU or embedded firmware support. That's an absence of evidence, not a verified absence.

### Coyote (formerly P#)
- **Read:** https://microsoft.github.io/coyote/, https://microsoft.github.io/coyote/concepts/concurrency-unit-testing/, https://github.com/microsoft/coyote
- **What it does:** rewrites .NET binaries so it controls scheduling, timers and failures. It explores with random, PCT or other strategies, and replays found bugs exactly. It's used across Azure.
- **Quote:** "Once a bug is found, Coyote allows you to fully reproduce the exact same trace that led to the bug 100% of the time."
- **Overlap: partial.**
  - Same idea of controlling all nondeterminism and replaying.
  - It tests real C# code, not a model, and its search isn't exhaustive.
  - It has no discrete time and no firmware use.

## Model checking and specification

### P language (Microsoft → AWS) ✔ *re-verified*
- **Read:** https://p-org.github.io/P/, https://p-org.github.io/P/getstarted/usingP/, https://p-org.github.io/P/advanced/pex/, https://p-org.github.io/P/casestudies/, `Tutorial/Common/Timer/PSrc/Timer.p` in https://github.com/p-org/P, and https://www.microsoft.com/en-us/research/publication/p-safe-asynchronous-event-driven-programming-2/
- **What it does:** state machines that talk through events, with nondeterministic environment and failure machines.
  - The default checker is **randomized**: its output says "Checker is using 'random' strategy". The docs say "100,000 schedules typically finds most of the easy to find bugs".
  - **PEx** is the exhaustive backend, "for small (finite) instances of the system".
  - A failing run writes a `.schedule` file "that can be used to replay the error trace".
  - History: the Windows 8 USB stack was implemented and verified in P (PLDI 2013), and AWS has used it since 2019.
- **Embedded:** the P case studies page says "P was used for creating formal models of the OTA protocol [AWS FreeRTOS] … the team found 3 bugs in the model that pointed to potential issues in the actual implementation itself."
- **Time:** the tutorial Timer machine fires a timeout nondeterministically (`if(choose(10) == 0) { send client, eTimeOut; …`), with no clock and no durations.
- **Overlap: HIGH.** P already does "model of communicating machines + injected failures → counterexample → deterministic replay", including exhaustive search (PEx) and firmware-protocol use. **Don't claim any of that.**
- **What differs** is smaller, and every item is a design choice rather than an invention:
  1. **A clock.** Our model has 50 ms discrete time, and invariants carry `bound_ms` deadlines ("stop within 500 ms"). P's idiomatic timers have no durations. (You *could* model a clock in P by hand; we just made it the default.)
  2. **Plain Python + pytest** instead of a new language. The counterexample is emitted as a pytest.
  3. **Version swap:** one counterexample re-run against firmware-ref v0.3.1 / v0.3.2 / v0.3.3 with a stable trace hash.
  4. **The domain:** BMS/hub/inverter with NVM-surviving restarts.

### TLA+ at AWS
- **Read:** https://lamport.azurewebsites.net/tla/formal-methods-amazon.pdf (Newcombe et al., CACM 2015; the Lamport-hosted copy, because CACM returned 403). Text extracted and quotes checked ✔.
  - Also https://arxiv.org/abs/2006.00915 (MongoDB "eXtreme Modelling in Practice") and https://github.com/informalsystems/modelator.
- **What it does:** exhaustive TLC checking of *designs* (DynamoDB, S3, …) found deep bugs that reviews and tests had missed. Follow-on work closes the gap to code: MongoDB generated tests from models for Realm Sync, and Modelator runs TLA+/Apalache traces as tests against an implementation.
- **Quotes:** "How do we know that the executable code correctly implements the verified design? The answer is that we don't." · "the shortest error trace exhibiting the bug contained 35 high level steps."
- **Overlap: partial to high.** "Exhaustive check, then counterexample as a test against the implementation" is exactly what Modelator and the MongoDB work do. Their spec and code are separate artifacts joined by a mapping. Ours share one `apply()`, which closes the drift gap *only because our "implementation" is also a reference model*. That's a weaker position than it sounds, and we should say so.

### Spin / Promela ✔ *re-verified*
- **Read:** https://spinroot.com/spin/whatispin.html, https://spinroot.com/spin/Man/c_code.html, https://spinroot.com/spin/Man/Pan.html, https://spinroot.com/modex/ and https://spinroot.com/gerard/pdf/spin04.pdf (Holzmann & Joshi, "Model-Driven Software Verification", JPL; text extracted and quote checked).
- **What it does:** the classic exhaustive explicit-state checker (Bell Labs; used heavily at NASA/JPL).
  - `c_code` embeds real C in the model: "The Spin parser merely passes all C code fragments through into the generated verifier uninterpreted."
  - The verifier replays error trails for those models: `pan -r` "for models with embedded C code, play back error trail".
  - Modex extracts models from C source.
- **Quote:** "a software application can be included, without substantial change, into a verification test-harness and then verified" (spin04.pdf).
- **Overlap: HIGH.** Spin did "model check → executable replay of *real* C" about 20 years ago, which is a stronger version of our loop. It's also our best answer to "how would you check real firmware?"

### Stateright ✔ *re-verified*
- **Read:** https://github.com/stateright/stateright (README).
- **What it does:** a model checker for Rust actor systems, with configurable lossy/duplicating networks and a browser explorer for counterexamples. The same actor code "can also be run on a real network without being reimplemented".
- **Overlap: HIGH** on "one definition, model-checked and executed". Stateright doesn't mention timed semantics or emitting regression tests.

### Hypothesis stateful testing ✔ *re-verified*
- **Read:** https://hypothesis.readthedocs.io/en/latest/stateful.html
- **What it does:** `RuleBasedStateMachine` runs random rule sequences, shrinks a failure to a minimal program, and prints it so that "you should just be able to copy and paste the code into a test to reproduce it."
- **Overlap: HIGH** on "minimal failing sequence → regression test, in Python". Hypothesis samples randomly, so it gives no bounded-completeness guarantee. That completeness is our one technical difference from it.

### Simulink Design Verifier (MathWorks) ✔ *re-verified*
- **Read:** https://www.mathworks.com/help/sldv/ug/harness-model.html. The agent also read https://www.mathworks.com/help/stateflow/ug/battery-management-system.html.
- **What it does:** proves properties on Simulink/Stateflow models. "The harness model enables you to simulate a copy of your original model by using the test cases or counterexamples that Simulink Design Verifier generates." MathWorks ships a Stateflow BMS example (contactors, precharge, fault maturation).
- **Overlap: HIGH in structure** for single-controller BMS logic, and it's what an automotive-style BMS team might already own. It differs from us in three ways: it's proprietary, it covers one controller model, and it has no adversary for faults, restarts and bus delays *across* devices.

### UPPAAL
- **Read:** nothing BMS-specific; searches returned only paper titles (timed-automata battery models, battery-aware scheduling).
- **Overlap: partial.** UPPAAL is the standard *timed* model checker and could find the same race. Its model is separate from any implementation. If a judge says "just use UPPAAL", the honest answer is: yes, for the proof, and it would find this. Our value is in the replay, regression and CI workflow around it.

### CBMC in CI (AWS)
- **Read:** both fetches failed, so this row relies on search snippets only (FreeRTOS `tools/cbmc`, coreMQTT). **Don't cite it in the video.**
- **What it does:** bounded model checking of real embedded C "unit proofs" on every PR.
- **Overlap: partial.** Real code in CI, but single functions and mostly memory safety, not multi-device protocols.

### Jepsen
- **Read:** https://jepsen.io/, https://github.com/jepsen-io/jepsen, https://github.com/jepsen-io/elle
- **What it does:** runs real distributed databases, injects faults with a "nemesis", and checks recorded client histories with Knossos (linearizability) or Elle (transactional anomalies).
- **Overlap: partial.**
  - Same adversarial fault idea.
  - Jepsen uses randomized sampling against real binaries and checks histories black-box.
  - It has no model, no exhaustive search and no deterministic re-run of a schedule.

## Power-electronics simulation and HIL (complementary, not competing)

### PLECS / PLECS RT Box (Plexim)
- **Read:** https://www.plexim.com/products/rt_box and https://docs.plexim.com/plecs/5.0/scripting/. The Robot Framework demo PDF didn't parse, so it's known by title only.
- **What it does:** circuit-level power-electronics simulation. RT Box is a real-time CPU+FPGA box for HIL and rapid control prototyping. It's scriptable over XML-RPC/JSON-RPC from Python (parameter sweeps, parallel runs).
- **Quote:** "simulation steps as small as 4 nanoseconds".
- **Overlap: none to partial, complementary.**
  - PLECS answers "does the power stage behave correctly in *this* scenario?" at ns resolution.
  - FleetFlight answers "*which* scenario breaks the software coordination?" at 50 ms resolution.
  - A FleetFlight counterexample driving an RT Box run over XML-RPC is the natural roadmap step. That's **ROADMAP**, not built.

### Typhoon HIL / TyphoonTest
- **Read:** https://www.typhoon-hil.com/products/software/typhoontest/, https://www.typhoon-hil.com/documentation/typhoon-hil-typhoontest-library/ and https://www.typhoon-hil.com/solutions/e-mobility/battery-management-system/
- **What it does:** real-time HIL for power electronics, microgrids and BMS (a cell emulator with fault testing). TyphoonTest is **pytest-based** and connects to CI via Test Hub.
- **Quote:** "Since Typhoon API is python based, TyphoonTest is based on Pytest…"
- **Overlap: partial, and the closest neighbour in *form*: pytest + fault injection + CI.**
  - Typhoon's tests are written by hand, and no page we read mentions exhaustive or model-checked fault orderings.
  - The two fit together: an emitted FleetFlight pytest could be ported to a TyphoonTest rig as HIL confirmation. That's **ROADMAP**.

### Does Base use any of these?
We found **no public source** saying Base uses PLECS, RT Box or Typhoon. Don't imply it.

What we *did* verify is Base's Head of Firmware posting (https://www.builtinaustin.com/job/head-firmware/9146737, reposted about a month before 2026-09-26). It says the role will "Choose the platform: … toolchains, CI, HIL, OTA, observability, and security", and it asks for someone who has "built HIL infrastructure from scratch".
- **Read:** the tooling decision is open.
- **Frame:** FleetFlight is a layer *before and alongside* HIL. Never say "Base doesn't have X".

---

## The novelty claim we can defend

> **FleetFlight applies known techniques** (bounded exhaustive model checking as in Spin, TLA+ and P's PEx; one definition that is both checked and executed, as in Stateright; shrink-to-regression-test as in Hypothesis) **to BMS ↔ Hub ↔ Inverter coordination, with three specific choices:**
> 1. **a millisecond clock in the model**, so invariants are deadlines ("inverter stops within 500 ms of a BMS fault") rather than eventually-properties;
> 2. **counterexamples that re-run unchanged against each firmware version**, which is how it caught our own half-fix (v0.3.2 still fails; v0.3.3 passes) and put a number on the fix's availability cost;
> 3. **every counterexample becomes a pytest that CI replays on every PR**, in plain Python, with no new language to learn.

Things we should **not** say, anywhere:
- "first", "novel technique", "new approach to verification"
- "unlike TLA+/P, our counterexamples run against real code". Ours run against a *reference model*, while Spin `c_code` runs real C.
- "no one does this for batteries". Say instead: "we found no open tool doing exhaustive cross-device fault ordering for BMS/hub/inverter; that's a search result, not a proof".

For the video (one sentence, at 4:15 or in the README):
> "None of the techniques are new. Spin, TLA+, P and FoundationDB got here first. What we built is that workflow, fitted to battery firmware releases: timed invariants, same-counterexample-every-version, and a CI gate."
