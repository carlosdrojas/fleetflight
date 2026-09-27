You are session **05 ci-demo** for FleetFlight. You're in worktree `../fleetflight-ci-demo` on branch `ci-demo`.

Read `sessions/_common.md`, `CONTRACT.md`, `mocks/fleetflight-verify.yml` and `mocks/cli.md` first. You own `.github/`, `scripts/`, `Makefile`, `tests/regress/` and `README.md`.

## Goal
Make the project reproducible by a judge in one command, gated in CI, and scripted for the demo video.

## Deliverables
1. **`Makefile`**:
   - `make setup`: venv, pip install, `npm ci` in ui.
   - `make test`
   - `make check`
   - `make demo`
   - `make ui`: build ui/dist.
   - `make serve`
2. **`scripts/demo.sh`**: the whole story end to end, with pauses (`read -p`) so it can be screen-recorded. It follows the "Demo story" in `_common.md` and must use only real commands:
   - happy-path `sim` passes
   - `check v0.3.1` finds a counterexample
   - `explain` it
   - `replay --repeat 100`
   - replay against v0.3.2: still fails
   - replay against v0.3.3: passes
   - full `check v0.3.3`: all pass
   - `regress --from` it, then `pytest tests/regress`

   Also add `scripts/demo_fast.sh` without pauses, used as a smoke test.
3. **`.github/workflows/fleetflight-verify.yml`**, based on the mock:
   - A fast lane, `regress`, that blocks the merge.
   - A slow lane, `check`, with a markdown step summary from `fleetflight report --markdown` and counterexamples uploaded as artifacts on failure.
   - Python 3.12, pip cache, and `pytest -q` as its own job.
4. **Demo-PR plan, written up only.** Write `scripts/demo_pr.md` explaining how to show a red check then a green check:
   - one branch pinned to SUT v0.3.2, then a commit moving to v0.3.3
   - the exact git commands
   - **Don't create the GitHub repo, push, or open PRs.** The user will do this or approve it later.
5. **`README.md`**: rewrite for the real product.
   - Tagline and a one-paragraph problem statement.
   - A 60-second quickstart (`make setup && make demo`).
   - An architecture diagram in ASCII or mermaid: spec → checker / simulator on one shared definition → counterexample → replay → regression → CI.
   - A built vs roadmap table.
   - Assumptions, "what we do and don't claim", prior art, and repo layout.
   - Keep the honest framing from the current README. Replace mock numbers with real ones once they exist; until then, write `<from make demo>` placeholders.
6. **Until the real CLI exists**, write the scripts against the command surface in CONTRACT.md. Where a command isn't available on your branch, guard with a clear message. Don't fake output.

## Sub-agents
Optional: once `demo_fast.sh` runs on the integration branch, a sub-agent can do a "fresh judge" test:
- Clone into a temp directory.
- Follow only the README.
- Report every place it got stuck.
