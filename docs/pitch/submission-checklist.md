# Submission checklist

**Source:** the event page's "Submission Checklist" and "Demo Video Instructions" child pages, read 2026-09-26 via the public Notion API. Event page: https://common-scooter-829.notion.site/Base-AITX-Talent-Hackathon-3e01e636288e80a7b914c993f90ae6c5

- **Due:** Sunday Sep 27, **11:00 AM CT**. Internal target: submitted by **10:15 AM**. Airtable uploads and Loom processing can be slow.
- **Where:** https://airtable.com/appWQWPtBqDUhCPPj/shrU4GuBeUnMzyrd5 (one submission per team).
- **Feature freeze:** 6:00 AM (per `sessions/_common.md`). Record from 7:00 AM on a frozen `main`.

## Required by the event (verbatim items, with our plan)

- [ ] **Project title:** "FleetFlight: pre-release verification for distributed battery firmware"
- [ ] **2–5 min demo video.** "Use Loom … Show the core loop live." Script: `video-script.md`.
- [ ] **Repo link (publicly viewable).** Must include a README with:
  - [ ] Quick start (commands to run): `make setup && make demo` (owned by stream 05)
  - [ ] Tech stack & architecture diagram ("simple is fine"): Python 3.12 stdlib + pytest (+ `rich` in the CLI), Vite/React UI. Diagram: model ↔ checker ↔ sim ↔ regress ↔ CI, with the SUT hook seam marked.
  - [ ] How to reproduce the demo (env vars, API keys, sample `.env`). We need **no** keys or env vars; the README should say so explicitly so the judges don't go looking for one.
  - [ ] Datasets / synthetic data + provenance. No external data. core-ref and firmware-ref are **synthetic reference implementations we wrote**; `fixtures/` and `mocks/` are hand-written placeholders. Say this in one paragraph.
  - [ ] Known limitations & next steps: link to the assumptions list and the build-vs-roadmap table, plus `docs/pitch/prior-art.md`.
- [ ] **Deployed URL (if any) or short screen capture of the working app.** We have no deployment (`serve` binds localhost). Attach a 30–60 s capture of the UI swimlane + replay, or point to the timestamp in the Loom.
- [ ] **Team roster** (names, roles, contacts): `<fill in>`
- [ ] **Short write-up (150–300 words):** problem → who it helps → solution → impact. Draft below.

## Track choice

**Primary: Track 2, Orchestration.** The brief is "coordinate many independent things … what matters is how it holds up when pieces fail." FleetFlight is literally that question, asked exhaustively: three independent controllers coordinating over a lossy bus while an adversary restarts them and delays their messages.
- The demo's story *is* "how it holds up when pieces fail", including the pieces-fail case the obvious fix misses.
- This is where Fit to Track (30 pts) is strongest.

**Second track: recommend *not* entering.**
- **Most Commercializable:** the brief is "something that could actually ship as a product on top of what Base does … for its members". FleetFlight is an internal engineering tool, not a member-facing product. We'd score low on "The Problem" and "The Why" there, and a stretched framing risks reading as the thing the judges dislike.
- **Open Grid Data:** doesn't fit; no ERCOT data is used.
- The event allows "up to 2 tracks *if it fits*". It doesn't fit, and saying so is itself a taste signal.
- **Your call:** if you'd rather enter a second track anyway, Commercializable is the only defensible one, pitched as "a pre-release gate Base's firmware team could adopt tomorrow". That argues *Usability*, not member value, so expect a weak Fit score.

## Repo link steps (need your approval: `_common.md` forbids creating a remote or pushing without asking)

1. The integrator finishes `integration`; **you** run `git checkout main && git merge --no-ff integration`.
2. From a clean clone in a temp dir: `make setup && make demo && .venv/bin/pytest -q`. It must pass with no local state.
3. Pre-publish sweep:
   - `git grep -n -E "1,284,511|41\.2 s|3f0a77c2e519|<from demo run>|<from make demo>|TODO"` should return only intentional hits in `mocks/` and `fixtures/`.
   - `git grep -n -i -E "api[_-]?key|secret|token|password"` should find nothing sensitive.
   - Make sure there are no `.venv/`, `out/`, `node_modules/` or `ui/dist/` directories unless the UI build is committed deliberately.
4. Create the GitHub repo (**ask first**): `gh repo create fleetflight --public --source . --remote origin --push`. Or create it private, check it, then flip it to public.
5. Open the repo URL in a **logged-out / incognito** window and confirm the README renders and the code is visible.
6. Optional: pin a tag, `git tag submission-2026-09-27 && git push origin submission-2026-09-27`, so the judges see exactly what was submitted even if you push later.

## Video: recording and export

The event asks for **Loom**, **camera on**, 2–5 min, "minimize editing or cuts", "showcase the console logs", and this flow:
1. Team intro (≤ 30 s)
2. Elevator pitch (≤ 30 s)
3. Live demo
4. Narrate how it's built
5. "So what?"

Our script folds 1–2 into 0:00–0:30 and covers 4 inside the demo beats. If you have more than one team member, add ~5 s per person at the very start and trim 1:00–2:15 to compensate.

**Settings**
- Loom desktop app: **Screen + Camera**, full screen, **1080p**. Microphone: an external mic or AirPods, not the laptop mic. Check the level in a 10 s test clip.
- **Length ≤ 5:00.** Aim for 4:45. **ASSUMED, check before recording:** the Loom free tier may cap video length (reportedly 5 min). If the recording would be cut, rehearse to 4:40.
- Terminal: ≥ 18 pt font, dark theme, ~100 columns, a clear prompt (`PS1='$ '`), and `clear` between commands. Pre-type long commands in a scratch file to paste.
- Browser: UI at 110–125% zoom, bookmarks bar hidden, other tabs closed.
- macOS **Do Not Disturb** on. Quit Slack/Discord/Mail. Hide the desktop icons.
- **No cuts through the core loop.** If the v0.3.1 `check` takes more than ~15 s, record it live anyway and narrate over the progress bar. Don't fake speed. A cut is OK only between beats, never inside `check → replay`.
- After recording:
  - Loom share setting: **"Anyone with the link can view"**, no password, comments on.
  - **Download an MP4 backup** (Loom → ⋯ → Download) and keep it locally in case the link breaks.
  - Put the Loom link in the Airtable form **and** the README.

**Pre-flight (run right before recording, on the frozen `main`)**
- [ ] `make setup && make demo` succeeds end to end.
- [ ] Every `<from demo run>` in `video-script.md` is replaced with a number from `STATUS.md`.
- [ ] Every claim you'll say out loud is VERIFIED or said *as* an assumption in `claims-audit.md`.
- [ ] `out/` is cleared so the UI's run list shows only today's real runs, with no MOCK DATA badge.
- [ ] One full rehearsal against a timer.

## Write-up draft (≈ 200 words; paste into the form after filling the placeholders)

> **Problem.** A home battery is several computers that must agree: a BMS, a hub and an inverter, talking over a bus that can delay messages, with any of them able to restart. The dangerous bugs live in rare orderings (a fault message in flight while the hub reboots). Unit tests check the orderings someone thought of; bench testing can't hit a 50 ms window on demand.
>
> **Who it helps.** Firmware and hub-software engineers shipping releases to an installed fleet.
>
> **Solution.** FleetFlight model-checks the coordination layer. Breadth-first search covers every allowed ordering of faults, restarts and delays within stated bounds, and each violation becomes a shortest counterexample. That counterexample replays deterministically through the same transition code (100/100 identical trace hashes), re-runs unchanged against each firmware version, and is emitted as a pytest that CI replays on every PR. In our demo it finds a stale-command resurrection in a reference implementation *we wrote*, catches our first fix as incomplete, and quantifies the real fix's availability cost.
>
> **Impact.** Timing bugs move from field incidents to red PR checks. The controller hooks are the seam for real hub code, then SIL, then HIL. Assumptions are printed in every report. core-ref is not Base firmware.

## Roster
| Name | Role | Contact |
|---|---|---|
| `<fill in>` | | |
