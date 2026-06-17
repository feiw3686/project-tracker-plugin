---
name: card-add
description: Add a new card (task/bug/milestone/decision/research/infra/master-task) to a markdown project-tracker graph under /import/snvm-sc-scratch1/feiw/notes/projects/<project>/cards/. Use when the user says "add a card", "track this as a task", "new card for ...", "add a node from <this PR / blurb>", or wants to start tracking a unit of work in the card graph.
---

# card-add — add a NEW item to a project tracker

Cards live at `/import/snvm-sc-scratch1/feiw/notes/projects/<project>/cards/<id>.md`.
The filename stem **is** the `id`. The schema is in `${CLAUDE_PLUGIN_ROOT}/SCHEMA.md`
(canonical, ships with the plugin) — read it if unsure. The board (`_project2.html`)
is a projection of these files.

## STOP — new item, or a step of an existing one?

**One md file = one work item.** Before creating a file, decide:

- A **new unit of work** someone owns end-to-end → **new card** (continue below).
- A **sub-stage, a blocker, or the debugging** of an existing item ("X is blocked by…",
  "debug the failure in X", "the next stage of X", "X regressed on the new branch") →
  that is a **step of X's card**, NOT a new file. **Use the `card-step` skill instead.**
  *Exception:* if that sub-unit needs its **own independent verification** (its own
  branch / cmd / validation), it is not a step — make it a **child card under a
  `master-task`** (this skill, with `--parent <master>`). Steps share the card's single
  end-step validation; child cards each self-validate. (See SCHEMA.md → `steps`.)

Heuristic: if the request references an existing card, it's almost certainly a step.
Do not spawn a separate bug/debug card — that's the file-proliferation we're avoiding.

## Steps

1. **Project**: default `minimax_m3`; ask if ambiguous. Confirm the cards dir exists.
2. **id**: pick a short stable kebab-case slug (e.g. `m3-foo-bar`). It must be unique
   and is permanent (renaming breaks `depends_on`/`parent` edges). Check it doesn't
   already exist in `cards/`.
3. **Gather fields** (see `${CLAUDE_PLUGIN_ROOT}/SCHEMA.md`):
   - `title` (short), `type` (master-task|task|bug|milestone|decision|research|infra),
     `status` (todo|ready|in_progress|blocked|done|dropped, usually `todo`),
     `summary` (one line, <= ~80 chars — this is the node's third line), `updated_by`.
   - **`owner` (assignee) — leave UNASSIGNED by default.** Do NOT default it to yourself or
     the requester. Omit `--owner` so the card starts unclaimed (it renders a dashed
     `⊘ unassigned` chip, and is assignable inline on the board). Only pass `--owner X` when
     a taker is genuinely already decided. `updated_by` is the creator/last-editor — that is
     not ownership.
   - Optional: `parent` (if it's a piece of a master-task), `depends_on` (ids it
     needs first), `tags`, `priority`, `links` (pr/slack/doc), `runs`.
   - **`validation` (verification script) — set this on every non-master card.**
     It is an *executable* pass/fail check (`branch` + `cmd` + `pass_criteria`).
     Creation stays frictionless: if no script exists yet, write it **explicitly**
     as missing so it's legible and gets flagged on the board:
     ```yaml
     validation:
       script: MISSING
     ```
     Then encourage filling in a real `cmd` — a card cannot be credibly closed
     (`status: done`) without a runnable verification script + a matching passing run.
   - If `type: master-task`: it is not worked on directly and has no `runs` and no
     `validation`; its status rolls up from children (which set `parent: <this-id>`).
4. **Write the card.** Easiest: run the helper (it scaffolds + regenerates the board):
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/new_card.py \
     --project <project> --id <id> --title "<title>" --type <type> --status <status> \
     --owner <who> --summary "<one-liner>" [--milestone 0-9] [--parent <m>] \
     [--depends a,b] [--tags x,y] [--validation-cmd "<check>" --validation-branch <b> --pass-criteria "<…>"]
   ```
   `--milestone N` places the card in swimlane N (adds a `stepN` tag). A card also
   inherits its milestone from its `parent`. For richer cards (links, an initial run,
   a long body, a `steps:` stack), write the `.md` directly with the Edit/Write tools
   following the `SCHEMA.md` template (it stays group-writable — `new_card.py` forces
   664; if hand-editing, `umask 002` first), then regenerate (step 5).
5. **Regenerate the board** (always, after any card change):
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/regen.py <project>
   ```
   (`new_card.py` already does this.) The board is `<project>/_project2.html`.
6. Tell the user the card id + that the board is updated (viewable on markserv). New cards are
   **Unassigned** — mention they can assign an owner inline from the card drawer on the board.

## Notes
- One card = one unit of work a person would pick up (or, for master-task, a theme
  that decomposes into such units). Sub-stages and **debugging** of one item are `steps`
  on its card (`card-step`), not new cards. If a card grows into several real units,
  make it a `master-task` + children (set each child's `parent:`; wire deps with `card-edit`).
- **Why the verification script matters.** It does double duty: (1) the credibility
  close-gate — proof the work actually passes before a card goes `done`; and (2) the
  per-branch regression probe — when a new dev branch is cut, each card's verification
  script is re-run to decide whether it still works or regressed. A card with
  `validation: script: MISSING` shows a **solid red bottom strip** on the board until a
  real script is added.
