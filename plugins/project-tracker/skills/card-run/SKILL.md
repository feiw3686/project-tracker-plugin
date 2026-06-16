---
name: card-run
description: Log a run/result (pass/fail/partial) on a tracked card — appends to its runs list with the command, artifact path, and a short note, bumps updated, and optionally flips status. Use when the user reports a build/test/compile/DAG result for a tracked task, e.g. "the o0 compile failed with ...", "this passed", "log this run", "record that result".
---

# card-run — log a run result on a card

Cards live at `/import/snvm-sc-scratch1/feiw/notes/projects/<project>/cards/<id>.md`.
A card's `runs:` list is what drives the node's ✓/✗ **result badge** (the viewer shows
the latest run) and the hover detail. Keep it append-only.

## Steps

1. **Find the card** (by id or title match; confirm if ambiguous).
2. **Append a run entry** under `runs:` in the frontmatter (Edit tool), newest last:
   ```yaml
   runs:
     - when: <today YYYY-MM-DD>
       result: pass        # pass | fail | partial | n/a
       cmd: "<the command that was run>"
       artifact: <path to log / output, if any>
       note: "<short result summary>"
   ```
   If there is no `runs:` key yet, add one. Quote `cmd`/`note` (they often contain
   colons). Bump `updated:` (today) and `updated_by:`.
3. **Optionally flip status** (use judgement / ask):
   - `fail` that blocks progress -> `status: blocked` (and add the blocker via
     `card-link` if it's a separate infra/dep card).
   - `pass` that completes the card -> `status: done`; a `pass` mid-stream -> often
     `in_progress`.
   Do not set status on a `master-task` (rolled up from children).
4. **Regenerate:**
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_graph.py <project>
   ```
5. Report: the run logged + any status change.

## Notes
- This is the main way "a past run that went good/bad" and "a past running command"
  stay visible on the board — prefer it over burying results only in prose.
