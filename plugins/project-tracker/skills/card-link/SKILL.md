---
name: card-link
description: Add or remove relationships between tracked cards — a dependency (depends_on) or a master-task containment (parent) — in a markdown project-tracker graph. Use when the user says "X depends on Y", "X needs Y first", "make X a subtask of master Z", "unblock X", "X is part of <master>", or wants to wire/unwire card relationships.
---

# card-link — wire dependencies / master-task membership

Cards live at `/import/snvm-sc-scratch1/feiw/notes/projects/<project>/cards/<id>.md`.
Two relationship kinds (see `_schema.md`):

- **`depends_on: [ids]`** — "needs those finished first" (a dependency edge; shown as
  `needs:` chips in the viewer).
- **`parent: <master-id>`** — "is a piece of master-task X" (containment; nests the
  card under the master in the outline). The parent **must** be a `type: master-task`.

## Steps

1. Identify the card(s) to edit and the target id(s). Confirm all referenced ids exist
   in `<project>/cards/` (a typo'd id will surface as a validation error).
2. **Edit the frontmatter** of the relevant card with the Edit tool:
   - add/remove an id in its `depends_on: [...]` list, and/or
   - set/clear its `parent:` field.
   Bump `updated:` (today) and `updated_by:` on the edited card.
3. **Regenerate** — this is where cycles get caught:
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_graph.py <project>
   ```
   If it reports a **dependency cycle** or **missing ref**, fix it (don't leave the graph
   invalid).
4. Summarize the edges you changed.

## Notes
- `depends_on` points dependency -> dependent (arrow from the thing needed to the thing
  that needs it). Keep edges minimal/meaningful.
- To convert a big card into a master-task + children (a "split"): change the card's
  `type` to `master-task` (it then has no runs; status rolls up), create the child cards
  (card-add), and set each child's `parent:` to it.
