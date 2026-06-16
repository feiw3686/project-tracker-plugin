# project-tracker (plugin)

Skills to create and maintain a markdown card-graph project tracker. Cards live
at `/import/snvm-sc-scratch1/feiw/notes/projects/<project>/cards/<id>.md` (the
filename stem is the card `id`); the schema is each project's `_schema.md`. The
landing-page board is a projection of these files.

## Skills

- **card-add** — add a card (task/bug/milestone/decision/research/infra/master-task).
- **card-status** — change a card's status (todo/ready/in_progress/blocked/done/dropped).
- **card-link** — add/remove relationships: `depends_on` (dependency) or `parent`
  (master-task containment).
- **card-run** — log a run/result (pass/fail/partial) on a card with cmd + artifact.

## Helper scripts (`scripts/`, invoked via `${CLAUDE_PLUGIN_ROOT}`)

- `new_card.py` — scaffold a new card file from fields.
- `set_status.py` — flip a card's status + bump `updated`.
- `build_graph.py` — regenerate the project's `graph.json` board projection.

> Note: these skills currently regenerate the `graph.json`/outline board via
> `build_graph.py`. Wiring them to also regenerate the newer milestone board
> (`_project2.html`, via `build_project2.py`) is a planned follow-up.
