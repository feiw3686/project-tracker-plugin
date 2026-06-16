---
name: card-status
description: Change a tracked card's status (todo/ready/in_progress/blocked/done/dropped) in a markdown project-tracker graph and bump its updated date/author. Use when the user says "mark <card> done", "X is blocked", "start working on X", "this task is finished", or otherwise updates progress on a tracked card.
---

# card-status — change a card's status

Cards live at `/import/snvm-sc-scratch1/feiw/notes/projects/<project>/cards/<id>.md`.

## Steps

1. **Find the card** by `id`, or by matching the user's words against card titles in
   `<project>/cards/` (confirm if ambiguous).
2. **Set the status** to one of: `todo | ready | in_progress | blocked | done | dropped`.
   Easiest:
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/set_status.py \
     --project <project> --id <id> --status <status> --by <who>
   ```
   (It surgically rewrites `status:`, bumps `updated:` to today and `updated_by:`, then
   regenerates the graph.) Or edit the `status:` / `updated:` / `updated_by:` frontmatter
   lines directly with the Edit tool, then regenerate (step 4).
3. **Semantics to apply:**
   - If `blocked`, there should usually be a blocker dependency — use the `card-link`
     skill to add `depends_on` the blocker (and prefer logging *why* via `card-run` if
     it was a failed run).
   - **Do NOT hand-set a master-task's status** — it is rolled up from its children by
     `build_graph.py`. Change the children instead.
4. **Regenerate** (if you edited by hand rather than via set_status.py):
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_graph.py <project>
   ```
5. Confirm the new status to the user.
