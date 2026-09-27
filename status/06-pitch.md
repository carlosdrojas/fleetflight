# 06 pitch: status

**Done (drafts), all in `docs/pitch/`.** Numbers wait on the integrator's `STATUS.md`.

- `video-script.md`: 5-min script with timestamps, spoken words and on-screen notes per beat. Every number is `<from demo run>`, and a fill-in table at the end maps each one to the command that produces it.
- `prior-art.md`: 5 parallel research agents covered FDB, VOPR, Antithesis, Coyote, Jepsen, TLA+ at AWS, Spin, P, Stateright, Hypothesis, Simulink Design Verifier, UPPAAL, CBMC, PLECS and Typhoon. I re-opened the primary source for every "high overlap" verdict myself.
- `claims-audit.md`: every README / script / UI claim marked VERIFIED, VERIFY-BY (with the command), ASSUMED or REMOVE, plus the integrator's command list.
- `judge-qa.md`: 12 hard questions plus backups.
- `submission-checklist.md`: taken from the event's Submission Checklist and Demo Video Instructions pages (read via the public Notion API). Covers the track choice, repo steps, Loom settings and a write-up draft.

## Findings other streams need
- **Novelty.** P (PEx exhaustive checking, `.schedule` replay, FreeRTOS OTA case study), Spin `c_code` (replays trails through real C), Stateright (same code checked and run) and Hypothesis (shrink → paste into test) together cover the whole "model check → replay → regression" pipeline.
  - The README's current novelty sentence must change. Use the claim at the end of `prior-art.md`: timed deadlines, the same counterexample run against every firmware version, and pytest/CI, applied to BMS/hub/inverter.
- **05 README.** Mocks-era values contradict the real code:
  - 100 ms ticks (the real value is 50 ms)
  - a 30 s dispatch expiry (really 3000 ms)
  - an edge-triggered single-shot FAULT (really retransmitted every 100 ms until ACKed)
  - PR #212 / "412 unit tests" in the UI mock
  - See claims-audit C1–C12 and D2–D7.
- **Integrator.** The v0.3.3 trade-off ("inverter idles ~X ms per hub restart") is computed by no stream that I can see. Compute it from a real run, or the script drops it (claims-audit A12).
- **Integrator.** The generated regression test should be shown *failing* on v0.3.1 as well as passing on v0.3.3 (A13).
- **Event requirements** our plan must meet: Loom with the camera on, a team intro in the first 30 s, minimal cuts, console logs visible, and a README with quick start, architecture diagram, "no env vars needed", data provenance and limitations.

## Needs the user
- Track: Orchestration only is recommended; the reasoning is in submission-checklist.md.
- Creating a public GitHub repo (not done; `_common.md` requires asking first).
- Team roster and names in the script.

## CONTRACT REQUEST
None.
