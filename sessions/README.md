# Launch guide

The prompts live in this folder. Every session reads `_common.md` first.

## Phase 0: foundation (one window, ~45 min, blocks everything)
```sh
cd ~/Documents/Dev/fleetflight
claude "Read sessions/00-foundation.md and follow it."
```
Wait until it commits and tags `contract-v1`.

## Phase 1: parallel streams (6 windows)
```sh
cd ~/Documents/Dev/fleetflight
for s in checker model cli ui ci-demo pitch; do git worktree add ../fleetflight-$s -b $s; done
```
Then launch one window per stream:

| Window | Command | Tool |
|---|---|---|
| 1 | `cd ~/Documents/Dev/fleetflight-checker && claude "Read sessions/01-checker.md and follow it."` | Claude |
| 2 | `cd ~/Documents/Dev/fleetflight-model && claude "Read sessions/02-model.md and follow it."` | Claude (the most important stream) |
| 3 | `cd ~/Documents/Dev/fleetflight-cli && claude "Read sessions/03-cli.md and follow it."` | Claude or Codex |
| 4 | `cd ~/Documents/Dev/fleetflight-ui && claude "Read sessions/04-ui.md and follow it."` | Claude (needs the Artifact tool to read the canvas) |
| 5 | `cd ~/Documents/Dev/fleetflight-ci-demo && claude "Read sessions/05-ci-demo.md and follow it."` | Claude or Codex |
| 6 | `cd ~/Documents/Dev/fleetflight-pitch && gemini` (then paste sessions/06-pitch.md) | Gemini or Claude |

For Codex, run `codex` and tell it to read the same file.

## Phase 2: integration (Sat ~11 PM)
```sh
cd ~/Documents/Dev/fleetflight
claude "Read sessions/07-integrator.md and follow it."
```

## Optional: phase 3, fleet stretch (only if the core works before Sun 3 AM)
```sh
git worktree add ../fleetflight-fleet -b fleet integration
cd ../fleetflight-fleet && claude "Read sessions/08-fleet-stretch.md and follow it."
```

## Timeline (CT)
| When | What |
|---|---|
| Sat now | 00 foundation |
| Sat +1h | 01–06 in parallel |
| Sat 11 PM | 07 integrator starts merging |
| Sun 3 AM | go / no-go on 08 fleet |
| Sun 6 AM | feature freeze |
| Sun 7–9 AM | record video from `scripts/demo.sh` and the UI |
| Sun 10:30 AM | submit (deadline 11:00) |

## Watching progress
Each stream keeps `status/<stream>.md` on its branch. To read one from anywhere:
`git -C ~/Documents/Dev/fleetflight show model:status/02-model.md`

If a stream writes a `## CONTRACT REQUEST`, relay it to the integrator (or to 00 while it's still open).
