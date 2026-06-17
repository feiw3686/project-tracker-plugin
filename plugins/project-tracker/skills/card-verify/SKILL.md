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

   **Persisting a DAG / dashboard run as a durable artifact.** When the outcome came from a
   `user_run_dag_tests.sh` / `test.jsonnet` run, the `artifact_root` is huge (~GB) and lives
   in `dump/` under quota — it WILL be cleaned, and any `btd-dashboard…` URL into it rots.
   Save only the small proof, then point `artifact:` at the saved copy:
   - **Where:** `<project>/verification/<card-id>_<YYYY-MM-DD>/` (a feiw-owned, group-writable
     home). Do **not** use any ad-hoc `<project>/artifacts/` — those may be owned by another
     user with no group-write. `mkdir -p` it then `chmod g+w` the dir.
   - **What to copy (keep it < ~1 MB):** the dashboard JSON (`…/infra_logs/dashboard_*.json`,
     ~10 KB — source of truth for per-test pass/fail) + its `*_btd_url` file + each test's
     `apps_persistent/<test>/<node>/run.0.log` (**gzip** any that aren't already `.gz`).
   - **README.md** in the dir: branch, date, the exact **re-runnable** run `cmd`, a
     pass/fail table read from the dashboard JSON's `lists[].tests[].state`, and a one-line
     link back to `../../cards/<id>.md`. **No commit hash** — credibility is re-runnability
     on the branch (see the close-out note below), not a frozen SHA.
   - Then set the run entry's `artifact:` to that dir (not the `dump/` path).
   - **Derive the `validation.cmd`** from the `// RUN:` header at the top of `test.jsonnet`
     (and confirm the result/branch against the matching `.test_history.json` row).
   - Only flip `done` if the dashboard shows **all** tests `PASSED`; partial → keep
     `in_progress` and say which node is red.
4. **Status:** a `fail` that blocks → consider `card-edit --status blocked` (or a `kind: debug`
   step via `card-step` if it's a per-branch regression). A `pass` that completes the card →
   `card-edit --status done` **only if** a real `validation` script + this passing run exist
   (the close-gate). Never set status on a `master-task`.
5. **Regenerate:** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/regen.py <project>`.
6. Report: script set and/or run logged, plus any status change.

## Notes
- **One validation per card = the END step.** A card carries a single `validation`/`runs`;
  on a stacked card the bottom strip renders only on the top (= current/end) step, so the
  script validates the card's end step. Earlier steps are lightweight sub-stages, not
  independently verified. If a sub-unit needs its own branch/cmd/validation, it belongs on a
  **child card under a `master-task`** (`card-add --parent`), not a step. (See SCHEMA.md.)
- Both halves answer the credibility question: *can anyone re-derive this result?* The script
  says **how to check**; the runs say **what happened, on which branch**.
- **Credibility = re-runnability on the named `branch`, NOT a commit hash.** Never record a SHA
  on a run (or in a saved artifact's README). Runs happen on local, often-unpushed, often-dirty
  trees, so a hash points at code nobody can reproduce — false precision that invites false
  trust. Instead, keep the `validation` script **self-contained** (all inputs in-repo, no
  private paths) so a PASS means *anyone* can check out the branch and reproduce it. That is the
  close-gate for `done`. (See SCHEMA.md `validation`/`runs`.)
- Per-branch health: same script, one run entry per dev branch. Old branch ✓ + new branch ✗ =
  a regression → also add a `kind: debug` step (`card-step`) for the debugging effort.
