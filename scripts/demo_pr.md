# Demo PR: a failing replay, then a passing fix

This is a written plan only. No remote, branch protection, push or PR has been
created by this stream. The reference SUT changes are already versioned in the
model stream; the demo changes only the explicit CI selection in
`scripts/ci_sut.txt`. Do not present it as a patch to Base firmware.

## Prerequisites

- Streams 01–05 are integrated on `integration` and the working tree is clean.
- Python 3.12+, compatible Node.js/npm, Bash and Make are available.
- Run the following locally to generate real evidence. Do not copy `fixtures/`
  or `mocks/`. Review the actual counterexample and generated tests before committing.

```sh
git worktree add ../fleetflight-demo-pr -b demo/firmware-fallback integration
cd ../fleetflight-demo-pr
make setup
make demo-fast
git status --short
git diff -- tests/regress
git add tests/regress
git commit -m "Store the real I1 counterexample and generated regression"
make regress
```

If the corpus was already committed by integration, omit the no-change commit.
An empty corpus, missing commands or an unexpected demo outcome is a blocker,
not a red firmware result. The branch's pin starts at `v0.3.3`, so this baseline
must pass before recording the red step.

## Red commit

```sh
printf '%s\n' v0.3.2 > scripts/ci_sut.txt
git add scripts/ci_sut.txt
git commit -m "Demo: check the hub-only v0.3.2 fix"
make regress
make check
```

Both make commands must fail because of an invariant violation from the real
CLI (CLI exit 1; Make itself reports an error). Inspect the replay JSON under
`out/regress.*` and `out/check/check.json`: the intended red reason is I1, not
an installation error, missing corpus, usage error or hash mismatch.

## Optional publishing — user action / approval required

The repository must already exist and `origin` must already point to it. This
plan does not create a GitHub repository or remote. After the user approves
publishing, they can run:

```sh
git remote -v
git push -u origin demo/firmware-fallback
gh pr create --base integration --head demo/firmware-fallback \
  --title 'Demo: replay the reference firmware fix in CI' \
  --body 'Replays the committed reference I1 counterexample against the pinned SUT. The hub-only version should fail; the inverter-fallback version should pass. This does not test Base firmware.'
gh pr checks --watch
```

Record the red `regress` job and its I1 evidence. The independent `check` job
should publish the failing report in its step summary and attach the newly
found counterexamples. Enable branch protection for the PR base and select the
actual **regress** job check as required. Also require `test`/`check` if desired.
Without that repository setting, the workflow does not itself prevent merges.

## Green commit on the same branch

```sh
printf '%s\n' v0.3.3 > scripts/ci_sut.txt
git add scripts/ci_sut.txt
git commit -m "Demo: verify the inverter fallback in v0.3.3"
make regress
make check
make test
```

After approval to publish the update:

```sh
git push origin demo/firmware-fallback
gh pr checks --watch
```

Record the same stored counterexample passing and the complete bounded check
passing. Show the unchanged corpus and the one-line SUT pin diff. Keep the PR
open for review; this plan does not merge into `integration` or `main`. The user
merges `integration` into `main` by hand.
