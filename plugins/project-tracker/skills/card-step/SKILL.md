---
name: card-step
description: Add or update a STEP inside an existing card's steps[] list — the sub-stages of one work item (plan / compile / integrate / debug), rendered as a stack of cards. Use when the user reports a new stage, a blocker, or the DEBUGGING of an existing item, e.g. "X is blocked by ...", "debug the failure in X", "the next stage of X is ...", "X regressed on the new branch". This is how bugs/sub-stages are tracked WITHOUT creating a new card.
---

# card-step — add a step to an existing item (stack-of-steps model)

**One md file = one work item.** Its sub-stages and **debugging** live as `steps:` entries
on that one card — NOT as separate files. The board renders a multi-step card as a **stack**
(current/last step on top; earlier done steps tucked behind; a `kind: debug` step = ◆/red).

Use this skill (not `card-add`) whenever the work belongs to an item that already has a card.

## Steps

1. **Find the item's card** (by id or title; confirm if ambiguous). If the work is actually
   a brand-new independent item, use `card-add` instead.
2. **Append the step.** Easiest:
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/add_step.py \
     --project <project> --id <card-id> --name "<step label>" --status <status> \
     [--kind debug] [--summary "<one-liner>"] [--by <who>] [--sync-status]
   ```
   - `--kind debug` marks a bug/blocker/debugging step (renders ◆ + red accent).
   - `--sync-status` sets the card's top-level `status` to this (now-current) step's status —
     usually what you want, since the last step is the current state.
   - Or edit the `steps:` block directly with the Edit tool (chronological: first = earliest,
     last = current/top), then regenerate (step 4).
3. **Status semantics:** a `blocked`/`in_progress` debug step is the soft, in-file way to show
   "this item hit a problem" — it does NOT require flipping the item red or spawning a sibling.
   When the blocker clears, set that step to `done` (it tucks behind) and add the next step.
4. **Regenerate** (if you hand-edited): `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/regen.py <project>`.
5. Report the step added + any status change.

## Notes
- Per-branch **regression** = a `kind: debug` step recording the break + a failing branch-tagged
  run via `card-verify`. No separate "regression card".
- Keep step names short (they're the stacked card's title); put detail in `summary` / the body.
- A single-step card renders as one plain card; it becomes a visible stack once it has ≥2 steps.
