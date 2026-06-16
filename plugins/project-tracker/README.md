# project-tracker (plugin)

Skills to create and maintain a markdown card-graph project tracker. Cards live
at `/import/snvm-sc-scratch1/feiw/notes/projects/<project>/cards/<id>.md` (the
filename stem is the card `id`); the schema is each project's `_schema.md`. The
board (`<project>/_project2.html`) is a pure projection of these files.

**Core model:** one md file = one work item. Its sub-stages and **debugging** are
`steps` on that card (rendered as a stack), *not* separate files. Every non-master
card carries a `validation` **verification script** — the credibility close-gate and
the per-branch regression probe; until one exists it shows a red bottom strip.

## Skills

- **card-add** — add a **new item**. Includes a decision-gate (new item vs. a step of an
  existing one), `--milestone`, and a `validation` scaffold.
- **card-step** — add/update a **step** in a card's `steps[]` (sub-stage or `kind: debug`
  blocker). This is how bugs/sub-stages/regressions are tracked — without a new card.
- **card-verify** — set/replace the **verification script** and/or log a **run** result
  (pass/fail/partial, per dev `branch`).
- **card-edit** — generic fix: status (with close-gate), `depends_on`/`parent`,
  owner/summary/priority.

## Helper scripts (`scripts/`, invoked via `${CLAUDE_PLUGIN_ROOT}`)

- `new_card.py` — scaffold a new card file from fields (forces group-writable 664).
- `add_step.py` — append a step to a card's `steps[]` (optionally sync top-level status).
- `card_edit.py` — surgically set status / parent / depends_on / metadata + bump `updated`.
- `render.py` — the board generator (single source; the project dir holds only data).
- `regen.py` — regenerate a project's board (runs the sibling `render.py` against it).

All scripts default `TRACKER_PROJECTS_ROOT` to the shared NFS notes tree
(`/import/snvm-sc-scratch1/feiw/notes/projects`); override the env var for another location.
Every skill regenerates the board via `regen.py` after a change.

See **DESIGN.md** (repo root) for the why: the card model, milestone swimlane board,
credibility/verification contract, and per-branch regression tracking.
