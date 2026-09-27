You are session **06 pitch** for FleetFlight. You're in worktree `../fleetflight-pitch` on branch `pitch`. You write no product code.

Read `sessions/_common.md`, `README.md`, `mocks/`, `../CLAUDE.md` (rubric and ground rules) and `../base-hackathon-ideas.md` first. You own `docs/pitch/`.

This stream suits Gemini CLI or Claude equally. If you're Gemini, report findings and don't commit; the user will commit.

## Goal
Everything needed to submit and to survive judge questions. The judges are Base engineers, who know their firmware far better than we do.

## Deliverables (docs/pitch/)
1. **`video-script.md`**: a 5-minute script with timestamps, the exact words spoken, and what's on screen for each beat. Structure:
   - 0:00–0:30: the problem, in the Base engineer's framing: pre-release race conditions and hardware-bound testing.
   - 0:30–1:00: why the obvious test passes.
   - 1:00–2:15: the check finds the counterexample, walked through on the swimlane.
   - 2:15–2:45: deterministic replay (100/100).
   - 2:45–3:45: fix, still fails, real fix, and the trade-off. This is the strongest beat.
   - 3:45–4:15: regression and CI.
   - 4:15–4:45: honesty (assumptions, what we don't claim) and the roadmap (PLECS/SIL, HIL, field telemetry to scenarios).
   - 4:45–5:00: close.

   Mark every number as `<from demo run>`; fill them in from the integrator's `STATUS.md` later.
2. **`prior-art.md`**: verified, cited prior art, with links you actually opened:
   - FoundationDB deterministic simulation, TigerBeetle VOPR, Antithesis, Jepsen, TLA+ at AWS, P language (Microsoft, used for async embedded and distributed systems), Spin/Promela, PLECS/RT Box, Typhoon HIL.
   - For each: what it does, and exactly how FleetFlight differs, or doesn't.
   - End with the narrow novelty claim we can defend. If research shows the P language or a similar tool already does "model check → executable replay" for embedded async code, **say so plainly** and reframe as "applying X to BMS/hub/inverter coordination, with Y".
3. **`claims-audit.md`**: every claim in README, video script and UI copy, each marked VERIFIED (with the command that verifies it), ASSUMED, or REMOVE.
4. **`judge-qa.md`**: the 12 hardest questions Base engineers will ask, with short honest answers. At least:
   - "your model is made up"
   - interlocks
   - state explosion / bounds
   - how you'd get a model of our real firmware
   - "why not TLA+ or P"
   - latency assumptions
   - fleet scale
   - "what would you do in week 1 at Base"
5. **`submission-checklist.md`**: from the event page's Submission Checklist (https://common-scooter-829.notion.site/Base-AITX-Talent-Hackathon-3e01e636288e80a7b914c993f90ae6c5). Include the track choice with a justification (Orchestration primary; say whether a second track is worth entering), the repo link steps, and the video export settings.

## Sub-agents
Run the prior-art research as parallel sub-agents, one per 2–3 tools. Each must return:
- the URL(s) it read
- a 3-line summary
- "overlap with FleetFlight: none / partial / high, because …"

Verify any "high overlap" verdict yourself before writing it down.
