#!/usr/bin/env bash
source "$(dirname -- "$0")/common.sh"
[[ -f ui/package.json && -f ui/package-lock.json ]] || die "UI package/lockfile missing. Integrate stream 04, then rerun make setup. Python-only: $PY -m pip install -e '.[dev]'"
command -v npm >/dev/null || die "npm is required for the UI. Install Node.js with npm."
case ${1:-} in
    install) (cd ui && npm ci) ;;
    build)
        (cd ui && npm run build)
        [[ -f ui/dist/index.html ]] || die "UI build did not produce ui/dist/index.html."
        ;;
    *) die "Usage: bash scripts/ui.sh install|build" ;;
esac
