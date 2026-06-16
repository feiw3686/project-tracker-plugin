---
name: card-verify
description: Manage a card's VERIFICATION — set/replace its validation script (the executable pass/fail check) and/or log a run result (pass/fail/partial) with command, artifact, and dev branch. Use when the user says "add a verification script for X", "set how X is checked", "the o0 compile passed/failed", "log this run", "record that result on X", or reports a build/test/compile/benchmark outcome (incl. per-branch results).
---

# card-verify — set the verification script & log runs

A card's credibility lives in two linked things, both managed here:

- **`validation:`** — the **verification script**: an *executable* pass/fail check
  (`branch` + `cmd` + `pass_criteria`). Required to mark a card `done`, and re-run on each
  new dev branch to detect regressions. Missing = a **solid red bottom strip** on the board.
- **`runs:`** — the append-only **per-branch run log**. Each entry's `branch` + `result`
  drives the bottom-strip segments (green/red/amber, latest 3) and the latest-run badge.

## Steps

1. **Find the card** (by id or title; confirm if ambiguous). Don't set verification on a
   `master-task` (it rolls up from children).
2. **Set / replace the verification script** (when the user gives one, or asks to add one):
   edit the `validation:` block in the frontmatter (Edit tool) — it must come **before**
   `runs:`/`steps:` is fine either way, but keep it a clean block:
   ```yaml
   validation:
     branch: dev/minimax-m3-2026-06-15
     cmd: "pytest path/test_x.py && grep -q PASS run.0.log"   # EXECUTABLE, not prose
     pass_criteria: "argmax >= 99% AND max_abs < 0.02"
   ```
   Replace any `script: MISSING` placeholder. Prefer a **deterministic script** over an
   AI check (anti-gaming). Bump `updated:` / `updated_by:`.
3. **Log a run** (when the user reports an outcome): append under `runs:`, newest last:
   ```yaml
   runs:
     - when: <today YYYY-MM-DD>
       result: pass            # pass | fail | partial | n/a
       branch: <dev branch it ran on>   # runs is a PER-BRANCH log — always tag the branch
       cmd: "<command>"
       artifact: <path to log / pef / output>
       note: "<short result>"
   ```
   Quote `cmd`/`note` (colons). If there's no `runs:` key, add one.
4. **Status:** a `fail` that blocks → consider `card-edit --status blocked` (or a `kind: debug`
   step via `card-step` if it's a per-branch regression). A `pass` that completes the card →
   `card-edit --status done` **only if** a real `validation` script + this passing run exist
   (the close-gate). Never set status on a `master-task`.
5. **Regenerate:** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/regen.py <project>`.
6. Report: script set and/or run logged, plus any status change.

## Notes
- Both halves answer the credibility question: *can anyone re-derive this result?* The script
  says **how to check**; the runs say **what happened, on which branch**.
- Per-branch health: same script, one run entry per dev branch. Old branch ✓ + new branch ✗ =
  a regression → also add a `kind: debug` step (`card-step`) for the debugging effort.
