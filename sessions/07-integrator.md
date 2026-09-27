You are session **07 integrator** for FleetFlight. Start this session **Saturday ~11 PM**, or once streams 01–03 report their first milestones done.

Work in the main worktree `~/Documents/Dev/fleetflight` on branch `integration`. Never commit to `main`; the user merges `integration` into `main` by hand.

Read `sessions/_common.md`, `CONTRACT.md`, and every `status/*.md` on every branch (`git show <branch>:status/<file>`).

## Goal
One working product on `integration`: `make setup && make demo` runs the full story on real code, the UI shows real runs, CI config is valid, and every number in docs comes from a real run.

## Loop
1. **Merge.** `git checkout -b integration main` (or check out the existing branch). Merge branches in dependency order: `checker`, `model`, `cli`, `ui`, `ci-demo`, `pitch`.
   - Resolve conflicts by preferring the owning stream's version for its own paths.
   - Apply CONTRACT REQUESTs from the status files deliberately, and record each one in `AGENTS.md` → Decisions.
2. **Wire.** Connect the CLI to the real checker and model (see stream 03's status for the calls it expects). Get these running:
   - `fleetflight check --model core-ref --sut v0.3.1`
   - `fleetflight replay …`
   - `fleetflight serve` with the built UI
3. **Run** `scripts/demo_fast.sh` and `pytest -q`. Fix what breaks. If a fix belongs to a stream that's still active, write the issue into that stream's status file; the user will relay it.
4. **Record real numbers** in `STATUS.md` at the repo root: states explored, wall time, counterexample length, ms values for each version, mutant kill table, and states/s. These are the numbers the pitch and README use.
   - Then replace every `<from demo run>` / `<from make demo>` placeholder.
   - Grep for leftover mock numbers ("1,284,511", "41.2", "cex-0017" if the real id differs) and remove them.
5. **Review.** Spawn parallel sub-agents, one per area (checker, model+sut, cli+sim, ui), each with this brief:
   - "Review for correctness bugs, nondeterminism, crashes on edge input, and claims not backed by code. Return file:line findings with a concrete failure scenario; no style nits."
   - Verify each finding yourself, then fix the real ones.
6. **Final pass.** Run `make demo` as if recording. Every screen and command must work from a clean checkout: clone to a temp dir, `make setup`, `make demo`.

## Rules
- Don't add features. Integration and correctness only. If something's missing, cut it and note it in STATUS.md.
- Keep `AGENTS.md` → Status current.
- At the end, tell the user:
  - what's on `integration`
  - what was cut
  - the real numbers
  - the exact command to merge (`git checkout main && git merge --no-ff integration`), which they run themselves
  - any items needing their approval (GitHub remote, demo PR)
