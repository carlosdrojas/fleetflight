#!/usr/bin/env bash
# Sourced by entry points; paths are relative to this checkout, not the caller.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
VENV=${VENV:-.venv}
PY="$VENV/bin/python"
FF="$VENV/bin/fleetflight"

die() { printf 'FleetFlight: %s\n' "$*" >&2; exit 2; }

require_python() {
    [[ -x "$PY" ]] || die "Missing $PY. Run make setup first."
}

require_cli() {
    require_python
    [[ -x "$FF" ]] || die "Missing $FF. Run make setup first."
    # The foundation CLI accepts flags but returns 2 for every command.
    if ! "$FF" describe --model core-ref --sut v0.3.1 --json >/dev/null; then
        die "The real core-ref model/CLI is unavailable or broken. Integrate streams 01–03; no demo results were produced."
    fi
}

expect_exit() {
    local expected=$1 actual=0
    shift
    printf '\n$'
    printf ' %q' "$@"
    printf '\n'
    "$@" || actual=$?
    [[ "$actual" == "$expected" ]] || die "Expected exit $expected, got $actual. Stopping; an error is not a demonstrated invariant failure."
}
