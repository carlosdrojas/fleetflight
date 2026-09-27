#!/usr/bin/env bash
source "$(dirname -- "$0")/common.sh"
require_cli
exec "$FF" serve --port "${1:-8765}" --out out/
