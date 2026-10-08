#!/usr/bin/env bash
source "$(dirname -- "$0")/common.sh"
require_cli
# Serve the newest demo run (scripts/demo.sh writes each run to out/demo.XXXXXX); override with a second argument.
OUT=${2:-$(ls -td out/demo.*/ 2>/dev/null | head -1)}
OUT=${OUT:-out/}
printf 'Serving artifacts from %s\n' "$OUT"
exec "$FF" serve --port "${1:-8765}" --out "$OUT"
