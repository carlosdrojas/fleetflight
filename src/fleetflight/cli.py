"""`fleetflight` command line (stream 03 owns this file). Stub: every subcommand prints
"not implemented". See CONTRACT.md §6 for the full command surface and flags."""
from __future__ import annotations

import argparse
import sys

COMMANDS: dict[str, str] = {
    "describe": "print the model/SUT spec (components, injectables, invariants, assumptions)",
    "check": "bounded model check; writes check report and counterexamples",
    "explain": "step table for a counterexample",
    "sim": "seeded (or scripted) simulation run",
    "replay": "replay a counterexample against a SUT version",
    "regress": "generate / run regression tests from counterexamples",
    "report": "render a check report (markdown, junit)",
    "serve": "serve ui/dist and the read-only JSON API on localhost",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fleetflight", description="Pre-release verification for battery firmware.")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, help_text in COMMANDS.items():
        sub.add_parser(name, help=help_text)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, _rest = parser.parse_known_args(argv)  # stub: accept any flags
    if args.command is None:
        parser.print_help()
        return 2
    print(f"fleetflight {args.command}: not implemented", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
