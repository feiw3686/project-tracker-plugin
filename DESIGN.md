# project-tracker — design & rationale

This document explains *what* the project-tracker is and *why* it is built the way it is.
For installation and the skill list, see [README.md](README.md).

The tracker is a **markdown card-graph**: every work item is one markdown file
(`projects/<project>/cards/<id>.md`), and every view (outline, milestone board) is a pure
*projection* of those files. The `card-*` skills are the conversational front-end that keeps
the cards in the required format so the projection stays trustworthy.

---

## 1. Core vision — why build this vs. Jira / Linear / Confluence

Two differentiators justify a purpose-built system:

1. **Whole-project graph at a glance.** One landing-page URL shows all ~100 work-item nodes
   at once, color-coded by status and grouped by milestone, so you instantly read
   "are we 10 / 20 / 40% done?" without drilling in.
2. **Tight integration with the skill system + Claude Code.** Cards are created, updated, and
   annotated by AI agents that are grounded in skill blueprints — so the card written closely
   matches the real work to be done, instead of being free-form busywork an engineer skips.

The whole point is to make status-tracking **effortless**: every required-format rule
(branch / command / artifact / validation) lives in a skill, not in the engineer's head.

---

## 2. The card model

- **One card = one markdown file** under `projects/<project>/cards/<id>.md`; the filename stem
  is the card `id`. The schema is each project's `_schema.md`.
- Card **types**: `task`, `bug`, `milestone`, `decision`, `research`, `infra`, `master-task`.
- **Relationships**:
  - `depends_on` — a hard dependency (X needs Y first).
  - `parent` — master-task containment (X is a subtask of master Z).
- **Steps (one item, one file)**: an item's sub-stages — plan → compile → integrate → **debug** —
  live as a `steps[]` list *on its own card*, NOT as separate files. A `kind: debug` step is the
  in-file way to track a bug/blocker. The board renders a multi-step card as a **stack** (see §3).
  This supersedes the earlier idea of separate `derived_from` debug cards / `regression_of`
  sibling cards — debugging is a step, not a new file.
- **Runs**: a `runs` list records each build/test/compile result (pass / fail / partial) with
  the command, artifact path, commit SHA, a short note, and the dev `branch` it ran on.
- **Validation block**: an *executable* close-gate contract — branch + command + pass criteria
  (see §4). Missing → a solid red bottom strip on the board.

The canonical cards are the single source of truth: the board (`build_project2.py` →
`_project2.html`) is a pure projection that reads `cards/*.md` directly. No view keeps its own copy.

---

## 3. The board / graph view

- Nodes = work items, connected by arrows showing dependencies.
- **Layered layout grouped by milestone** — the 9 model bring-up steps, milestone 0 on top
  through 9 at the bottom. Deliberately *not* a free-floating auto-layout (a prior Mermaid/dagre
  attempt gave tiny nodes, long crossing edges, and mixed milestones — the messiness we reject).
- Each node is a **rich rounded-rectangle card** readable without clicking: status color,
  assignee chip, and a one-line summary.
- **Interaction**: click a card → enlarge to a detail drawer (or jump to the markdown file),
  with "back to graph" navigation and clickable links to dependency / related cards.

### Stack-of-steps cards (signature visual)

One work item = one card; its `steps[]` render as a **stack**. The **current (last) step** sits
on top; earlier **done** steps tuck **behind**, dimmed. A `kind: debug` step (a bug/blocker) shows
a ◆ + red accent — a blocked debug step on top reads as "this item hit a problem", and clears by
going `done` (tucking behind) as the next step takes over. A small **`⤢ N steps` toggle** fans the
stack open into a column; a single-step item is just one plain card. (This replaces the older
"separate debug card overlaid via `derived_from`" metaphor — the stack now comes from one file's
steps, so there's no file-per-bug proliferation.)

The **bottom strip** is a second axis: solid red = no verification script; with a script, one
green/red/amber segment per dev branch (latest 3, `+N` for older) — so *status* (top) and
*per-branch health* (bottom) are independent (see §5).

### Implementation

- HTML + JS landing page, rendered with a deterministic **CSS-grid swimlane** renderer (one
  milestone = one horizontal lane; cards wrap left→right within a lane — "finite freedom").
  Chosen over Mermaid/dagre, which cannot do rich cards or the stack metaphor.
- Auto-generated from the current state of all cards by `build_project2.py` (reads `cards/*.md`
  directly; sorts each group by `order`). Pure DOM/CSS/SVG, no CDN.
- Hosted with **Markserv** so every file is browsable and directly editable by path.

---

## 4. Credibility — the central problem of heavy AI use

The failure mode: an AI marks things done that aren't, or flags problems that don't exist →
the tracker loses credibility → it becomes useless. The defenses:

- **Every card carries reproducible context** — branch, commit hash, exact run command,
  artifact location, and (for fixes) the fix itself.
- **Validation contract.** A card needs a `validation` block that is an *executable script*
  (branch + command + pass/fail criteria). Required only when **closing / marking done**, not at
  creation — so creation stays frictionless.
- **Prefer a deterministic script over an AI verifier.** A real pytest / compile beats
  "the agent says it looks right."

A card with `validation: script: MISSING` is flagged (see §5) and **cannot be credibly closed**.

---

## 5. The two-axis card face (status vs. health)

A card surfaces two *independent* questions through two strips:

- **Top strip = `status` color** — the work item's fundamental state (todo → done, blocked).
  *"Is this unit of work built?"*
- **Bottom strip = verification + per-branch run health** — *"Does its check pass, and on which
  dev branches?"*

This is why regression is **not** just the card color: a card can be **green-on-top (done)** and
**red-on-the-rightmost-bottom (regressed on the newest dev branch)** at the same time.

Bottom-strip states:

- **No verification script** (`validation.cmd` absent / `MISSING`) → **solid red** = mis-configured,
  cannot be trusted or closed. Red dominates even with run history (a run with no reproducible
  script isn't trusted).
- **Script present, 0 runs** → a single **neutral grey** segment ("configured, unverified") — so
  green always means a real pass.
- **Script + runs** → **one segment per branch**, chronological, newest on the right
  (latest result per branch): pass = green, fail = red, partial = amber. Multi-segment stripes
  only appear once a card has cross-branch history, so the `green…green ‖ red` regression pattern
  self-limits to where it matters.

Master-tasks are exempt (they render as clusters).

---

## 6. Per-branch regression tracking

Dev branches are cut periodically (each `main` resync → a new dated `dev/minimax-m3-YYYY-MM-DD`).
A card that was `done` on branch N may regress on branch N+1 (main moved, new compiler, …). This
is a **soft** failure — the work still functions on the prior branch — so it must **not** flip the
card red. Two things, two mechanisms (both in the steps/runs model — no new cards):

1. **The fact "works on N, broke on N+1"** = per-branch data in the card's `runs` list as a
   branch-tagged run. A new branch where the card still works is just a passing run tagged with
   that branch → **zero new files**, and it shows as the rightmost bottom-strip segment.
2. **The debugging effort when it breaks** = a **`kind: debug` step** added to the *same* card
   (via `card-step`), not a sibling/`regression_of` file. It rides on top of the card's stack
   (◆/red) until resolved, then tucks behind as `done`.

Rendering: the card keeps its top-strip `status` (e.g. green/done) while the **bottom strip's
newest segment goes red** and a debug step appears on its stack — so "fundamentally done" and
"regressed on the current branch" are both legible at once, without a separate card or a red flip.
The `add-dev-branch` automation (deferred) will do this loop: register the branch, re-run each
card's verification script, log the branch-tagged run, and add the debug step on a break.

---

## 7. AI permission boundaries

- AI **may**: create cards; fill in / update / annotate content.
- AI **should not** unilaterally: mark a card `done`, delete a card, or mark it irrelevant —
  these need human confirmation.
- **Anti-cheating**: if an agent both writes *and* runs its own validation, it can game a trivial
  test. Mitigation under consideration — human-in-the-loop approval of validation scripts (logged).

A long-running **"Program Manager"** agent is a future idea: it would suggest new work items,
check stale cards, run verifications, and nudge format violations — a helper under human
oversight, not a judge.

---

## 8. Skill suite (roadmap)

The skills encode the format rules so the card matches the real work. Status: ✅ shipped ·
🟡 partial · ❌ to build. The set was **consolidated** (2026-06-16) to four daily-driver skills
plus a regen helper; several earlier ideas folded in (see notes).

| skill | job | status |
|---|---|---|
| `card-add` | add a **new item**; decision-gate (new item vs. step of an existing one); identity fields + stable id; `--milestone`; scaffold `validation`; regen. | ✅ |
| `card-step` | add/update a **step** in `steps[]` (sub-stage or `kind: debug` blocker) — the stack-of-steps model. Subsumes `card-from-debug`, `card-derive`, `card-regression`. | ✅ |
| `card-verify` | set/replace the **verification script** (`validation`) AND log a branch-tagged **run** (cmd/artifact/sha/result). Subsumes `card-run` + `card-validate` + run-the-check. | ✅ |
| `card-edit` | generic fix: status (with **close-gate** on `→ done`), `depends_on`/`parent`, owner/summary/priority. Subsumes `card-status` + `card-link` + `card-modify` + `assign-card-to`. | ✅ |
| `regen.py` (helper) | project all `cards/*.md` → the board (`build_project2.py` → `_project2.html`). Single source; no view keeps its own copy. | ✅ |
| `add-dev-branch` | on each `main` resync: register the new dev branch, re-run every card's verification script, log branch-tagged runs, add a `kind: debug` step for any regression. | ❌ (deferred) |
| `start-project` | scaffold a new tracker directory + schema + template card. | ❌ |

**Folded-in decisions:** the **close-gate** (refuse `→ done` without a `validation` script + a
matching passing run) is a *rule inside* `card-edit`/`card-verify`, not a separate skill.
Per-branch **regression** = a `kind: debug` step (`card-step`) + a failing branch-tagged run
(`card-verify`) — no `regression_of` sibling card. Multi-assignee lives in `card-edit --owner`.

**Priority order:** (1) ✅ the four core skills + regen (done); (2) `add-dev-branch` automation
once every card has a real verification script; (3) generalize with `start-project`;
(4) later — `program-manager` agent.

---

*This design is implemented incrementally; the skill table above is the source of truth for what
exists today versus what is planned.*
