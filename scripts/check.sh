#!/usr/bin/env bash
source "$(dirname -- "$0")/common.sh"
require_cli
SUT=${1:-$(cat scripts/ci_sut.txt)}
OUT=${5:-out/check}
mkdir -p "$OUT"
"$FF" check --model core-ref --sut "$SUT" --depth "${2:-120}" \
    --injections "${3:-3}" --horizon-ms "${4:-4000}" --out "$OUT" --json "$OUT/check.json"
"$PY" scripts/artifacts.py check "$OUT/check.json" PASS
