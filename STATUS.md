# FleetFlight: integration status (real numbers)

Owner: 07 integrator, branch `integration`. **Every number here comes from a real run on 2026-09-27** (Apple M1 Pro, Python 3.13.7, single thread), from `bash scripts/demo_fast.sh` unless noted. `core-ref` is a reference model we wrote and `firmware-ref` is reference firmware we wrote. Neither is Base firmware.
The pitch and README quote these numbers. Wall times vary from run to run by a few seconds, but state counts, ids and hashes are deterministic.

## Demo story as the real code tells it
The BFS's shortest I1 counterexample on v0.3.1 is **BMS fault + hub↔inverter link loss at t=0**, not the delayed-fault + hub-restart story in the mocks. Both have the same root cause: the inverter keeps discharging on the hub's say-so for 1000 ms, which is longer than the 500 ms budget. The demo narrates what the checker found:

| Step | Command | Result |
|---|---|---|
| 1. Happy path | `sim --sut v0.3.1 --scenario bms-fault-basic` (fault@100, FAULT delayed +400 ms) | all PASS; I1 fault→stop window **200 ms** |
| 2. Check v0.3.1 | `check --sut v0.3.1 --depth 120 --injections 3 --horizon-ms 4000` | **1,291,349 states**, 1,844,026 transitions, **38.2 s**, complete; I1, I2, I4 FAIL |
| 3. Explain | `explain cex-286e0592` | `bms_fault@0, network_loss@0`; **12 moves** (2 injections + 10 ticks); I1 violated at **500 ms** (the formula is strict `< 500`) |
| 4. Replay ×100 | `replay --counterexample cex-286e0592 --repeat 100` | 13/13 steps match the checker, `hash match: True`; **100/100 identical** full hashes `sha256:b545736726cb` |
| 5. Hub-only fix | `replay … --sut v0.3.2` | I1 still **FAIL**, window **1050 ms** (550 over budget) |
| 6. Inverter fix | `replay … --sut v0.3.3` | I1 **PASS**, window **250 ms** |
| 7. Check v0.3.3 | `check --sut v0.3.3` (same bounds) | **1,187,853 states**, 1,728,511 transitions, **35.5 s**, complete; all 5 PASS; worst window I1 **450 ms**, I5 **250 ms** |
| 8. Regression | `regress --from cex-286e0592` then `pytest tests/regress` | generated test **fails on v0.3.1 and v0.3.2**, **passes on v0.3.3** (`FLEETFLIGHT_SUT=…`); `make regress` 0.5 s |

Fault→stop windows for `cex-286e0592`, as measured by replay: **v0.3.1 1050 ms · v0.3.2 1050 ms · v0.3.3 250 ms** (budget 500 ms).

The other v0.3.1 counterexamples:
- I2 `cex-6b2a6d1b`: `hub_restart@0`, violated at 450 ms. The rebooted hub resumes 5 kW from NVM without a BMS report; this is the stale-command resurrection.
- I4 `cex-0b2044d5`: `bms_fault@100, bus_delay(cmd@100, +100)@100`, violated at 250 ms. A reordered stale command is re-applied after the STOP.

Throughput on core-ref: **~33.8k states/s** (v0.3.1) and **~33.4k states/s** (v0.3.3). The ~113k–172k states/s in `status/01-checker.md` is the checker's bench model, not core-ref.
Max BFS depth reached: 83.

## The restart story (secondary, measured)
- **Scripted scenario** `sim --scenario restart-during-fault` (fault@100, FAULT +400 ms, hub restart @200): I1 windows **600 / 550 / 400 ms** for v0.3.1 / v0.3.2 / v0.3.3. This is a hand-picked sequence, not a checker finding.
- **Scoped check** `check --sut v0.3.1 --only bms_fault,hub_restart,bus_delay` (horizon 4000): 652,180 states in 19.7 s. The shortest I1 counterexample is `cex-07af641d` = `bms_fault@0, hub_restart@0, hub_restart@400`, violated at 500 ms. Its replay windows are **900 / 450 / 250 ms**, so v0.3.2 *passes* this one. The "hub fix is not enough" beat therefore rests on the link-loss counterexample above, not on the restart.

## Anti-vacuity (mutant kill table)
`python -m tests.models.test_mutations` (stream 02's mini BFS, not the product checker): **6/6 mutants of v0.3.3 killed**, and every invariant I1–I5 is killed by at least one mutant. The full table is in `status/02-model.md`.

## Tests
- `pytest -q`: **160 passed** (includes the generated regression). `make test` also runs `scripts/test_automation.py`.
- `ui`: `npm test` 23/23 and `npm run build` clean.
- CI workflow YAML parses. It has not run on hosted Actions (no remote).

## Not computed, so cut from the pitch
- **"v0.3.3 idles the inverter ~X ms per hub restart."** No product command computes it. The model's tests pin an availability metric (`tests/models/test_story.py`): after a hub restart with a healthy BMS, v0.3.3 is not discharging for 2750 of the 3000 ms dispatch (v0.3.2: 2550, v0.3.1: 0). That's because re-dispatch after restart isn't modeled, so it's the rest of the dispatch, not a short blip. Quote it only with that caveat.
- `GET /api/regress` (UI contract request 04): not built. The Regressions screen falls back to showing the counterexample's moves and CLI commands.
- Fleet stretch (session 08): not built.

## Review (07, four read-only sub-agents; each finding re-checked by the integrator)
- **Fixed:** `check --only` with an unknown name listed the already-filtered injectables in its error message. It now lists the model's full set.
- **Fixed (UI):** `Versions` and `stepSummary` now guard against null trace or event entries, and axis ticks are whole milliseconds (they used to show duplicate labels like `0 0 0 1 1 1` on tiny ranges).
- **Stale:** "the regress CI job always fails on an empty corpus". The corpus is now committed (`tests/regress/cex-286e0592.json` + the generated test).
- **Known, not changed (latent):** the model's I5 timer (`core_ref.py`, `last_rx = t` on every delivery to the inverter) also counts messages v0.3.3 rejects as stale, while the firmware's own watchdog doesn't count them. No verdict changes today: v0.3.3's own 200 ms fallback fires long before the 1500 ms I5 budget. A future SUT with a longer loss timeout could get a false I5 PASS. We left it alone so the measured numbers wouldn't move at feature freeze.
- **Known, cosmetic:** `stats.max_depth_reached` can read one less than the last BFS round when that round only produced already-seen states. It doesn't affect verdicts or counterexamples.
- **Checked and held up:** BFS minimality (against the DFS oracle, early-stop path included); window/`worst_case_ms`; `complete`; report determinism; checker trace hash = replay trace hash for all three core-ref counterexamples; exit codes; serve path safety; the generated test fails on v0.3.1 and passes on v0.3.3.
- `status/02-model.md`'s mini-BFS state counts (1.09M, 35 s, …) come from `FLEETFLIGHT_FULL=1`; default `pytest` runs 2 injections. The product-checker numbers above are the ones to quote.
