# Shared rules for every FleetFlight session

Read this before doing anything else. Your session prompt tells you your stream (which part you own).

## What we're building
FleetFlight: pre-release verification for distributed battery firmware (BMS ↔ Hub ↔ Inverter).
- A bounded model checker searches every allowed ordering of faults, delays and restarts.
- Each violation becomes a minimal counterexample.
- The counterexample is replayed deterministically in a simulator that runs **the same transition code**.
- The fix is verified against that same sequence, and the sequence becomes a regression test in CI.

Read these first:
- `README.md` (pitch, the bug story, assumptions, built vs roadmap)
- `mocks/` (cli.md, spec_sketch.py, counterexample-0017.json, test_cex_0017.py, fleetflight-verify.yml, index.html)
- `CONTRACT.md` and `src/fleetflight/core.py` (the shared API, written by the foundation session)
- `../CLAUDE.md` (hackathon context and judging rubric)
- Hi-fi design canvas: https://claude.ai/artifact/MBTZJWuDr2yBfjrs3uok9H (open it with the Artifact tool's `read` action, not WebFetch)

## The demo story the real code must reproduce
Check `core-ref` against each firmware version:
- **v0.3.1:** I1 fails with a short counterexample. The BMS fault message is delayed, the hub restarts and loses it, the hub restores the old DISCHARGE command from NVM, and the inverter is still discharging past the 500 ms budget.
- **v0.3.2** (hub fix): the same counterexample still fails, only slightly over budget.
- **v0.3.3** (inverter falls back to SHUTDOWN on hub loss): all invariants pass.
- **Happy path** (fault, no restart): passes.

Exact millisecond numbers come from the real code, not the mocks. **Numbers in mocks/ are placeholders. Never copy them into real output or docs.**

## Deadline
Submission is **Sunday Sep 27, 11:00 AM CT**: a 5-minute video plus the code link.
- Feature freeze: **Sunday 6:00 AM**.
- Integration starts **Saturday 11 PM**.
- If you're behind, cut scope and say so in your status file. Don't silently stub.

## Ground rules
- **Honesty.** Every claim is either verified by running the code or visibly labeled ASSUMED / MOCKED.
  - `core-ref` is a reference model we wrote, not Base Gen 3.
  - Never write "we found a Base bug" or "we verified Base firmware".
- **Simplicity.** Python 3.12, stdlib + pytest. `rich` is allowed in the CLI only. The UI may use Vite + React + TypeScript.
  - No Kafka, Temporal, Kubernetes, databases or queues.
  - Every feature must answer "what verification problem does this solve?"
- **Determinism.** No wall-clock time, randomness without a seed, or iteration over unordered sets inside anything that affects a trace.
- **Ownership.** Edit only the paths your stream owns (table below).
  - If you need a change to `core.py`, `schemas/` or `CONTRACT.md`, don't make it. Write a `## CONTRACT REQUEST` in your status file.
  - In the meantime, work around it with a local adapter.
- **Git.**
  - Work on your own branch, in your own worktree, and commit often with clear messages.
  - Never commit to `main`. Never merge into `main`: the user merges `integration` into `main` by hand.
  - Never create a GitHub remote, push, or open PRs without asking the user first.
- **Status.** Keep `status/<NN-stream>.md` (e.g. `status/02-model.md`) current: done, in progress, blocked, real numbers observed, contract requests. Update it at every milestone and before you stop.
- **Done means** `pytest -q` passes for your area, your status file is updated, and your work is committed.

## Ownership
| Stream | Owns |
|---|---|
| 00 foundation | `pyproject.toml`, `src/fleetflight/core.py`, `src/fleetflight/__init__.py`, `schemas/`, `fixtures/`, `CONTRACT.md`, `AGENTS.md` |
| 01 checker | `src/fleetflight/check/`, `tests/check/` |
| 02 model | `src/fleetflight/models/`, `src/fleetflight/sut/`, `tests/models/` |
| 03 cli | `src/fleetflight/sim/`, `src/fleetflight/regress/`, `src/fleetflight/report/`, `src/fleetflight/cli.py`, `tests/cli/` |
| 04 ui | `ui/` |
| 05 ci-demo | `.github/`, `scripts/`, `Makefile`, `tests/regress/` (generated), `README.md` |
| 06 pitch | `docs/pitch/` |
| 07 integrator | branch `integration`; may touch anything to glue; owns `STATUS.md` |

## Sub-agents
Use sub-agents where your prompt suggests them. Give each one a narrow, checkable task, and read and verify what it returns before relying on it.
