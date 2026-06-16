---
name: card-edit
description: Generic fix for a tracked card — change its status (todo/ready/in_progress/blocked/done/dropped), wire relationships (depends_on / parent), or update metadata (owner, summary, priority, tags). Use when the user says "mark X done", "X is blocked", "start X", "X depends on Y", "make X a subtask of Z", "reassign X to <who>", "rename/retitle X", or otherwise edits an existing card's fields.
---

# card-edit — change status, links, or metadata on a card

The general-purpose "fix this card" skill (merges the old card-status + card-link). For
*adding a sub-stage/debug step* use `card-step`; for *the verification script or a run result*
use `card-verify`.

## Steps

1. **Find the card** (by id or title; confirm if ambiguous).
2. **Make the edit.** Easiest — the surgical helper (rewrites only the named fields, bumps
   `updated`/`updated_by`, regenerates the board):
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/card_edit.py --project <project> --id <id> \
     [--status <s>] [--parent <master-id>] [--add-dep <id>] [--rm-dep <id>] \
     [--owner <who>] [--summary "<one-liner>"] [--priority high|med|low] [--by <who>]
   ```
   Or edit the frontmatter directly (Edit tool) for anything not covered, then regen (step 4).
3. **Semantics:**
   - **Close-gate:** only set `--status done` if the card has a real `validation` script AND a
     matching **passing run** (see `card-verify`). Don't close on prose alone.
   - **`blocked`** usually pairs with a dependency (`--add-dep <blocker>`) or a `kind: debug`
     step (`card-step`) explaining why.
   - **`parent`** must point at a `type: master-task` (containment/nesting). **`depends_on`** =
     "needs that finished first" (dependency arrow). Keep edges minimal/meaningful.
   - **Never hand-set a `master-task`'s status** — it's rolled up from its children. Edit children.
4. **Regenerate** (if you hand-edited): `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/regen.py <project>`.
   If a `parent`/`depends_on` points at a missing id, fix it (don't leave the graph invalid).
5. Confirm what changed.

## Notes
- `id` is permanent — renaming it breaks `depends_on`/`parent` edges; change `title` instead.
- To split a big card into a master + children: set its `type: master-task` (it loses runs;
  status rolls up), create children with `card-add`, set each child's `parent:` to it.
