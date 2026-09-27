#!/usr/bin/env bash
source "$(dirname -- "$0")/common.sh"
case ${1:-} in
    '') PAUSES=1 ;;
    --no-pauses) PAUSES=0 ;;
    *) die "Usage: bash scripts/demo.sh [--no-pauses]" ;;
esac
require_cli
if [[ "$PAUSES" == 1 && ! -t 0 ]]; then
    die "The recording demo needs a terminal. Use make demo-fast without pauses."
fi

pause() {
    if [[ "$PAUSES" == 1 ]]; then
        read -r -p "Press Enter to continue… " || die "Recording stopped at end of input."
    fi
}

# Each run gets fresh output, so a stale report cannot make a failed run look good.
mkdir -p out
RUN=$(mktemp -d "$ROOT/out/demo.XXXXXX")
printf 'Reference firmware only. Real artifacts: %s\n' "$RUN"

printf '\n1. Happy path: a BMS fault without a hub restart.\n'
pause
expect_exit 0 "$FF" sim --model core-ref --sut v0.3.1 \
    --scenario bms-fault-basic --seed 1 --horizon-ms 4000 --json "$RUN/happy.json"

printf '\n2. Search v0.3.1 for a failing ordering.\n'
pause
expect_exit 1 "$FF" check --model core-ref --sut v0.3.1 --depth 120 \
    --injections 3 --horizon-ms 4000 --out "$RUN" --json "$RUN/check-v031.json"
CEX=$("$PY" scripts/artifacts.py select "$RUN/check-v031.json")

printf '\n3. Explain the I1 counterexample selected from this report.\n'
pause
expect_exit 1 "$FF" explain "$CEX" --out "$RUN"

printf '\n4. Replay the original failure 100 times.\n'
pause
expect_exit 1 "$FF" replay --counterexample "$CEX" --repeat 100 --json "$RUN/replay-v031.json"
"$PY" scripts/artifacts.py replay "$RUN/replay-v031.json" FAIL --same-sut

printf '\n5. Replay against the hub-only fix; I1 must still fail.\n'
pause
expect_exit 1 "$FF" replay --counterexample "$CEX" --sut v0.3.2 --json "$RUN/replay-v032.json"
"$PY" scripts/artifacts.py replay "$RUN/replay-v032.json" FAIL

printf '\n6. Replay against the inverter fallback fix.\n'
pause
expect_exit 0 "$FF" replay --counterexample "$CEX" --sut v0.3.3 --json "$RUN/replay-v033.json"
"$PY" scripts/artifacts.py replay "$RUN/replay-v033.json" PASS

printf '\n7. Check all allowed orderings within the same bounds on v0.3.3.\n'
pause
expect_exit 0 "$FF" check --model core-ref --sut v0.3.3 --depth 120 \
    --injections 3 --horizon-ms 4000 --out "$RUN" --json "$RUN/check-v033.json"
"$PY" scripts/artifacts.py check "$RUN/check-v033.json" PASS
expect_exit 0 "$FF" report "$RUN/check-v033.json" --markdown

printf '\n8. Generate a regression from the actual counterexample and run it.\n'
pause
expect_exit 0 "$FF" regress --from "$CEX" --out-dir tests/regress
# Keep the original evidence alongside the generated test for version-pinned CI replay.
cp "$CEX" "tests/regress/$(basename -- "$CEX")"
expect_exit 0 "$PY" -m pytest tests/regress -q
printf '\nDemo completed. Reports: %s\nReview and commit generated tests/regress files before enabling the CI gate.\n' "$RUN"
