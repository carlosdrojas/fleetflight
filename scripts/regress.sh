#!/usr/bin/env bash
source "$(dirname -- "$0")/common.sh"
require_python
SUT=$(cat scripts/ci_sut.txt)
shopt -s nullglob
CORPUS=(tests/regress/cex-*.json)
TESTS=(tests/regress/test_*.py)
[[ ${#CORPUS[@]} -gt 0 && ${#TESTS[@]} -gt 0 ]] || die "Regression corpus is empty. On an integrated checkout, run make demo-fast, review and commit tests/regress. Fixtures are not regression evidence."
require_cli
mkdir -p out
RUN=$(mktemp -d "$ROOT/out/regress.XXXXXX")
for cex in "${CORPUS[@]}"; do
    "$PY" scripts/artifacts.py cex "$cex"
    result="$RUN/$(basename -- "$cex")"
    "$FF" replay --counterexample "$cex" --sut "$SUT" --json "$result"
    "$PY" scripts/artifacts.py replay "$result" PASS
done
"$PY" -m pytest tests/regress -q --junitxml=out/regress.xml
