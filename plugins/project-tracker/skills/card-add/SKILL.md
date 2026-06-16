---
name: card-add
description: Add a new card (task/bug/milestone/decision/research/infra/master-task) to a markdown project-tracker graph under /import/snvm-sc-scratch1/feiw/notes/projects/<project>/cards/. Use when the user says "add a card", "track this as a task", "new card for ...", "add a node from <this PR / blurb>", or wants to start tracking a unit of work in the card graph.
---

# card-add — add a card to a project tracker

Cards live at `/import/snvm-sc-scratch1/feiw/notes/projects/<project>/cards/<id>.md`.
The filename stem **is** the `id`. The schema is in `<project>/_schema.md` — read it
if unsure. The graph (`_project.md` landing page) is a projection of these files.

## Steps

1. **Project**: default `minimax_m3`; ask if ambiguous. Confirm the cards dir exists.
2. **id**: pick a short stable kebab-case slug (e.g. `m3-foo-bar`). It must be unique
   and is permanent (renaming breaks `depends_on`/`parent` edges). Check it doesn't
   already exist in `cards/`.
3. **Gather fields** (see `_schema.md`):
   - `title` (short), `type` (master-task|task|bug|milestone|decision|research|infra),
     `status` (todo|ready|in_progress|blocked|done|dropped, usually `todo`),
     `summary` (one line, <= ~80 chars — this is the node's third line),
     `owner`, `updated_by`.
   - Optional: `parent` (if it's a piece of a master-task), `depends_on` (ids it
     needs first), `tags`, `priority`, `links` (pr/slack/doc), `runs`.
   - If `type: master-task`: it is not worked on directly and has no `runs`; its
     status rolls up from children (which set `parent: <this-id>`).
4. **Write the card.** Easiest: run the helper (it scaffolds + regenerates):
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/new_card.py \
     --project <project> --id <id> --title "<title>" --type <type> --status <status> \
     --owner <who> --summary "<one-liner>" [--parent <m>] [--depends a,b] [--tags x,y]
   ```
   For richer cards (links, an initial run, a long body), write the `.md` directly
   with the Edit/Write tools following the `_schema.md` template, then regenerate (step 5).
   Set `umask 002` first if creating by hand, so the file stays group-writable.
5. **Regenerate the graph** (always, after any card change):
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_graph.py <project>
   ```
   Report any validation ERRORS it prints (missing refs, cycles, dup ids) and fix them.
6. Tell the user the card id + that the graph is updated (viewable at the
   `_project.md` landing page on markserv).

## Notes
- One card = one unit of work a person would pick up (or, for master-task, a theme
  that decomposes into such units). If a card is getting big, consider a master-task
  + children (see the `card-link` skill to attach children via `parent`).
