# 05 ci-demo

## Done
- Implemented Make targets: setup, test, check, demo, demo-fast, regress, ui, serve.
- Added one shared demo sequence with interactive pauses and a noninteractive wrapper.
  It selects the real I1 artifact from the current report, requires exact expected
  exit codes, checks original replay hashes, rejects fixtures and incomplete checks,
  and generates/copies the real regression evidence only after successful replay.
- Added independent Python 3.12 CI jobs: pytest, pinned-SUT regressions, bounded
  checking with an always-run Markdown summary and failure artifacts. Empty regression
  corpora fail. Branch protection must be enabled by the repository owner.
- Added a written red-to-green PR plan using scripts/ci_sut.txt, initially v0.3.3.
  No remote, push, PR, branch-protection setting or merge was created.
- Rewrote README with quickstart, architecture, current built/pending status,
  assumptions, prior art, repository layout and unmeasured-result placeholders.

## Validation / real numbers observed
- Local interpreter: Python 3.13.7. The workflow specifies Python 3.12; a hosted
  Actions run and a local 3.12 run have not been performed.
- `make test`: 28 passed (19 foundation tests plus 9 automation safety cases).
- Plain `pytest -q`: 19 passed. CI runs the 9 automation cases separately.
- `bash -n` passed for all shell scripts; Make target dry runs passed.
- Workflow parsed with Ruby YAML; its jobs are test, regress and check.
  actionlint and shellcheck are not installed locally.
- `demo_fast.sh` returned 2 with the missing model/CLI diagnostic.
- `regress.sh` returned 2 with the empty-corpus diagnostic.
- UI installation guard returned 2 with the missing package/lockfile diagnostic.
- No model timings, state counts, counterexample ids or replay hashes measured.
  Numbers in mocks/ and fixtures/ have not been promoted to results.

## Blocked / integration handoff
- This branch still has foundation stubs for streams 01–03 and no UI package/lockfile.
  Full `make setup`, UI build/serve, end-to-end demo and generated regression corpus
  remain pending integration. The guards above are verified, not the final bug story.
- After integration run `make setup && make demo-fast`, review and commit the
  generated tests/regress Python and JSON files, then run `make regress`, `make check`
  and `make test`. Replace README result placeholders only with observed output.
- Confirm `bms-fault-basic` is implemented under the contract's `sim --scenario`
  surface, and that the I1 BFS counterexample reproduces both fix stages. A different
  valid counterexample must not be silently presented as the intended story.
- The fast lane explicitly replays tests/regress/cex-*.json against the pin before
  pytest, so it does not need an uncontracted `regress --sut` option. Generated tests
  also run normally. The slow lane uses the same pin and contract default bounds.
- No Artifact read tool is available for the shared design canvas. Local mock
  sources were inspected; no UI implementation was attempted by this stream.
- Optional fresh-judge sub-agent test is deferred: its prerequisite is a successful
  demo_fast run on integration.

## CONTRACT REQUEST
None. Only stream-owned paths and this required status file changed.
