# Claims audit

Every claim made in the README, the video script (`video-script.md`) and the UI copy (the `mocks/index.html` design copy, plus the hard-coded strings in `ui/src` on branch `ui`).

**Verdicts**
- **VERIFIED:** checked now, with the command or source given.
- **VERIFY-BY:** true only once the given command prints it on the integrated build. It becomes VERIFIED when the integrator runs it and records the output in `STATUS.md`. Until then, **don't say it in the video**.
- **ASSUMED:** a modelling assumption. Say it *as* an assumption, on screen.
- **REMOVE:** wrong, unverifiable, or contradicted by the real code. Delete it or reword it as shown.

State of the branches when audited (2026-09-26, ~23:30 CT):
- `checker` has 4 milestones committed.
- `model` has uncommitted work in its worktree (`core_ref.py`, `firmware_ref.py`).
- `cli`, `ui` and `ci-demo` are in progress.
- Nothing is integrated, so **no end-to-end claim is verified yet**.

Paths are relative to the repo root. `$FF` means `fleetflight` (the CLI).

---

## A. Core product claims (README, script, UI)

| # | Claim | Where | Verdict | Verify with / action |
|---|---|---|---|---|
| A1 | "A bounded model checker searches every allowed ordering of faults, delays and restarts" (within bounds) | README, script 1:00, UI | VERIFIED for the checker; VERIFY-BY for core-ref | Checker: `pytest tests/check/test_crosscheck.py -q`, where BFS matches an independent DFS oracle on 14 cases (status/01-checker.md). core-ref: `$FF check --model core-ref --sut v0.3.1`, where the report shows `"complete": true`. **Always say "within bounds".** Note: the checker stops early once every invariant has failed (`complete: false`). On v0.3.1 say "found a counterexample", not "searched everything". |
| A2 | "Each violation becomes a minimal counterexample" | README, script | VERIFIED (method), VERIFY-BY (core-ref) | The BFS gives a shortest path *in moves*, and minimality is brute-force proven on the race toy (`tests/check/test_toy_race.py`). Say "shortest", and don't say "simplest" or "minimal in time". |
| A3 | "Replayed deterministically through the **same** transition code" / "Nothing gets translated" | README, script 2:15, UI pipeline | VERIFY-BY | `$FF replay --counterexample <id>`: `trace_hash` must equal the one in `<id>.json`. The design (CONTRACT §1: `apply` is shared, the replay rule) makes this true by construction. |
| A4 | "100/100 identical trace hashes" | script 2:15, mocks/cli.md | VERIFY-BY | `$FF replay --counterexample <id> --repeat 100 --json out/r.json` and count distinct hashes = 1. Or: `for i in $(seq 100); do $FF replay --counterexample <id> --json - \| jq -r .trace_hash; done \| sort -u \| wc -l` → `1`. |
| A5 | "The hash matches the checker's byte for byte" | script 2:15 | VERIFY-BY | As A3. |
| A6 | Happy path (fault, no restart) PASSes | script 0:30, _common.md | VERIFY-BY | `$FF sim --model core-ref --sut v0.3.1 --scenario bms-fault-basic --seed 1` → I1 PASS. **Check that the scenario name exists in `cli`.** |
| A7 | v0.3.1 fails I1 via stale-command resurrection after hub restart | README, script 1:00 | VERIFY-BY | `$FF check --sut v0.3.1` then `$FF explain <id>`. **The step list in the script must match `explain` output.** The real model retransmits FAULT every 100 ms until ACKed, so the real path may differ from the mock's single-shot story. |
| A8 | v0.3.2 still fails on the same counterexample, "only slightly over budget" | README, script 2:45 | VERIFY-BY | `$FF replay --counterexample <id> --sut v0.3.2` → I1 FAIL, with `violation_window_ms` > 500. |
| A9 | "The hub's 400 ms boot alone eats most of the budget, so no hub-side change can fix this" | README, script 2:45 | ASSUMED + REWORD | The 400 ms is the ASSUMED `HUB_BOOT_MS`. "No hub-side change can fix it" is an argument, not a check. Say: "with a 400 ms boot, a hub-side fix can't meet a 500 ms budget on this sequence". |
| A10 | v0.3.3 passes the same counterexample *and* the full check | README, script 2:45 | VERIFY-BY | `$FF replay --counterexample <id> --sut v0.3.3` → PASS; `$FF check --sut v0.3.3` → exit 0, all PASS, `complete: true`. |
| A11 | "I1 worst case X ms" on v0.3.3 | script 2:45, mocks | VERIFY-BY | `worst_case_ms` for I1 in the v0.3.3 check report. Mind the discretization note in status/01-checker.md: a 550 ms window can PASS a 500 ms bound at 50 ms ticks. |
| A12 | Trade-off: "every hub restart idles the inverter ~400 ms" | README, script 2:45, mocks/cli.md | VERIFY-BY or REMOVE | No stream has committed to computing this. If nothing in the code prints it, **cut the sentence** or derive it live: replay a hub_restart-only scenario on v0.3.3 and read the inverter's non-DISCHARGING window. Don't state it from reasoning. |
| A13 | "The counterexample becomes a pytest; CI runs it on every PR" | README, script 3:45 | VERIFY-BY | `$FF regress --from <id>` writes `tests/regress/test_*.py`; `pytest tests/regress -q` passes on v0.3.3 **and fails on v0.3.1**. Show the failing case once, or the claim is weak. Check `.github/workflows/*.yml` exists and is valid. |
| A14 | "Fast lane replays every stored counterexample in < 10 s and blocks the merge" | README, UI | VERIFY-BY / REWORD | The time comes from the CI log or a local `time pytest tests/regress`. "Blocks the merge" needs branch protection on a real GitHub repo; unless that's set up, say "fails the PR check". |
| A15 | "If anyone reintroduces restart recovery, this test goes red" | script 3:45 | VERIFY-BY | As A13: the generated test must fail against v0.3.1. |
| A16 | "Assumptions print first / are in every report" | script 1:00, UI | VERIFY-BY | `$FF check` prints ASSUMPTIONS before results; `describe.assumptions` is in the JSON. |
| A17 | "The adversary can fault the BMS, restart the hub, delay/drop/duplicate a message" | script 1:00 | VERIFIED (model worktree, uncommitted) | `INJECTIONS = (bms_fault, hub_restart, network_loss, bus_delay, bus_drop, bus_dup)` in `src/fleetflight/models/core_ref.py`. Re-check after merge. |
| A18 | "50 ms ticks" | script | VERIFIED | `TICK_MS = 50` in `src/fleetflight/core.py` (contract-v1). |
| A19 | Checker speed: "~113k–172k states/s, one thread" | judge-qa backup | VERIFIED for the **bench model only** | `python -m tests.check.bench_model 120 3 3000` (status/01-checker.md, M1 Pro, Py 3.13). **Not core-ref.** Quote the core-ref number from STATUS.md. |
| A20 | "`<N>` states in `<T>` s" | script 1:00, UI stats | VERIFY-BY | v0.3.1 check report `stats.states`, `stats.wall_s`. |

## B. Honesty and scope claims (must stay, and must be true)

| # | Claim | Where | Verdict | Note |
|---|---|---|---|---|
| B1 | "core-ref is a reference model we wrote, not Base Gen 3" | everywhere | VERIFIED | Docstrings in `core_ref.py` and `firmware_ref.py`, plus the OUT OF SCOPE assumption. |
| B2 | "We didn't find a bug in Base's system" | script 4:15 | VERIFIED | We never had Base code. |
| B3 | Bus latency ≤ 800 ms; delay/drop/dup/reorder | README, UI, script | ASSUMED | `LATENCY_MAX_MS = 800`. "Reorder" follows from delays; there's no separate reorder injection. Fine as worded. |
| B4 | BMS FAULT edge-triggered | README, UI mock | **REMOVE / REWORD** | The real model **retransmits FAULT every 100 ms until ACKed** by default (`FAULT_RETX_MS = 100`). Use whatever the check report's assumptions list says. |
| B5 | Heartbeat 2 s | README, UI | ASSUMED | `BMS_STATUS_MS = 2000`. |
| B6 | Inverter holds setpoint 1 s then IDLE (v0.3.1–2); v0.3.3 shuts down after 200 ms | README, script | ASSUMED (a firmware-ref design choice) | `INV_HOLD_MS`, `HUB_LOSS_TIMEOUT_MS`. |
| B7 | Hub boot 400 ms, RX buffer cleared, only NVM survives | UI, script | ASSUMED | `HUB_BOOT_MS = 400`. |
| B8 | Shutdown budget 500 ms | everywhere | ASSUMED | "A real number would come from Base's safety requirements". Keep that phrase. |
| B9 | Hardware interlocks out of scope | everywhere | ASSUMED (scope) | Keep. |
| B10 | "A proof only covers the model" | UI mock | VERIFIED (it's a statement of method) | Keep. Better: "a PASS only covers the model, within bounds". |
| B11 | "The techniques aren't new: Spin, TLA+, P, FoundationDB got there first" | script 4:15 | VERIFIED | See `prior-art.md` (primary sources re-opened). |

## C. README (current `README.md`, the mocks-era text; stream 05 is rewriting it)

| # | Claim | Verdict | Action |
|---|---|---|---|
| C1 | "Explicit-state BFS over **100 ms** ticks" | **REMOVE** | It's 50 ms (contract-v1). |
| C2 | "seq 41 (valid for **30 s**)" | **REMOVE** | Real `DISPATCH_EXPIRES_MS = 3000`. Use the real value or drop it. |
| C3 | Step-by-step bug story with 400/500/550/600 ms | **REMOVE numbers** | Replace them with `explain` output from the real run. |
| C4 | v0.3.2 "shutdown takes 550 ms"; v0.3.3 "passes (300 ms)" | **REMOVE numbers** | VERIFY-BY A8/A10. |
| C5 | "Without step 4 … inverter stops at 550 ms: PASS" | **REMOVE number** | VERIFY-BY A6. |
| C6 | "TLA+ checks a spec that drifts from the code. Here … a counterexample is directly runnable against the system under test" | **REWORD** | True only because our SUT is also a reference model. Suggested: "The checker and simulator run the same transition code, so a counterexample runs as-is against every firmware-ref version. Checking real firmware needs a SIL adapter behind the same hooks (roadmap), which is the approach Spin's `c_code` takes." |
| C7 | "PLECS is a future backend" / "Higher-fidelity backends plug in behind the same model interface" | ASSUMED (roadmap) | Keep it under a **Roadmap** heading and say "designed to", not "plugs in". |
| C8 | "TLA+/Apalache export for unbounded proofs" (roadmap) | ASSUMED (roadmap) | Fine under Roadmap. Nobody is building it. |
| C9 | "Unit tests check the orderings someone thought of. The checker checks all of them within bounds." | VERIFIED (with "within bounds") | Keep. |
| C10 | Prior-art paragraph and "the combination we'd claim" | **REWORD** | Replace it with the claim at the end of `prior-art.md`. The current wording ("shared-definition model checking → deterministic replay → generated regression" as the novel part) is taken by Stateright, P, Spin and Hypothesis. |
| C11 | Fleet stretch: "500 Virtual Cores … F2 FAIL seed 8841" | **REMOVE** unless built | Stream 08 status decides. |
| C12 | "Nothing here runs yet" / "mocks only" | **REMOVE** at integration | Stream 05 owns it. |

## D. UI copy (the `mocks/index.html` design and `ui/src` on branch `ui`)

| # | Copy | Verdict | Action |
|---|---|---|---|
| D1 | "MOCK · ALL NUMBERS ILLUSTRATIVE" banner | VERIFIED as designed | The real UI shows the badge only when `_fixture: true` ("At least one payload on this page has _fixture: true"). Clear `out/` of fixtures before recording. |
| D2 | "≤ 40 ticks × 100 ms" | **REMOVE** | Real bounds are 50 ms ticks, default `Bounds(max_depth=120, max_injections=3, horizon_ms=3500)`. The UI must read them from the report. |
| D3 | "1,284,511 states explored · 41.2 s" | **REMOVE** | Mock. Read from the report. |
| D4 | "CI · firmware PR #212 … unit tests 412 passed" | **REMOVE** | There's no PR #212 and no 412 unit tests. Show only the real CI run, or cut the panel. |
| D5 | "BFS · shortest counterexample first" | VERIFIED | The checker's BFS (status/01-checker.md). |
| D6 | "No counterexamples in any run. Every checked invariant held within bounds." | VERIFIED as logic | Shown only when true; the wording includes "within bounds". |
| D7 | Regression test snippet with `seed=8841`, `"m_resume" not in r.sent_messages` | **REMOVE** | Replay needs no seed (the moves are the script), and the message ids are model-assigned (e.g. `fault#1`). Show the real generated file instead. |
| D8 | "Model fidelity ladder: Behavioral BUILT; PLECS/SIL, HIL, physical ROADMAP" | VERIFIED as labeled | Keep the BUILT/ROADMAP labels. |
| D9 | "PLECS checks whether the power system behaves correctly. FleetFlight checks whether the software does…" | VERIFIED (a positioning statement) | Consistent with the PLECS docs (`prior-art.md`). |
| D10 | "Fast lane … under 10 s, and block the merge" | VERIFY-BY | See A14. |

## E. Judge Q&A claims (`judge-qa.md`)

| # | Claim | Verdict | Source |
|---|---|---|---|
| E1 | AWS paper: "How do we know that the executable code correctly implements the verified design? … we don't." / DynamoDB bug with a 35-step shortest trace | VERIFIED | https://lamport.azurewebsites.net/tla/formal-methods-amazon.pdf (text extracted and searched) |
| E2 | P: default checker is randomized; PEx is exhaustive "for small (finite) instances"; `.schedule` replay; FreeRTOS OTA case study; nondeterministic timer idiom | VERIFIED | p-org.github.io pages and Timer.p (see `prior-art.md`) |
| E3 | Spin `c_code` runs real C in the verifier; `pan -r` replays trails | VERIFIED | spinroot.com c_code and Pan manual pages |
| E4 | The oracle cross-check covers 14 model/bounds cases | VERIFIED on `checker` | status/01-checker.md; `pytest tests/check/test_crosscheck.py -q` |
| E5 | "Many coordination bugs need only a few faults" (small-scope) | ASSUMED | Stated as a bet in the answer; keep that framing. |
| E6 | Base Head of Firmware posting mentions "CI, HIL, OTA" and "built HIL infrastructure from scratch" | VERIFIED | https://www.builtinaustin.com/job/head-firmware/9146737 (opened 2026-09-26). Use only to show we did our homework, never to say "Base lacks HIL". |
| E7 | Fleet stretch built or not | VERIFY-BY | Stream 08 status / STATUS.md |

---

## Integrator: minimal command set to flip VERIFY-BY → VERIFIED

```bash
$FF sim --model core-ref --sut v0.3.1 --scenario bms-fault-basic --seed 1          # A6
$FF check --model core-ref --sut v0.3.1 --json out/c1.json; echo "exit=$?"          # A1 A2 A7 A16 A20 (expect exit=1)
$FF explain <id>                                                                     # A7 (script step list)
$FF replay --counterexample <id> --repeat 100                                        # A3 A4 A5
$FF replay --counterexample <id> --sut v0.3.2                                        # A8
$FF replay --counterexample <id> --sut v0.3.3                                        # A10
$FF check --model core-ref --sut v0.3.3 --json out/c3.json; echo "exit=$?"          # A10 A11 (expect exit=0)
$FF regress --from <id> && pytest tests/regress -q                                   # A13 (pass on v0.3.3)
# A13/A15: prove the test fails against v0.3.1 (e.g. a generated test param or --sut override)
time pytest tests/regress -q                                                         # A14
```
Record every output number in `STATUS.md`. Then replace every `<from demo run>` in `video-script.md` and `judge-qa.md`.
