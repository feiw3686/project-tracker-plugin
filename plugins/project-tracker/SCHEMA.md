# Card schema — frontmatter spec

*The canonical contract every `cards/*.md` file follows. Humans and the graph
skills both read this. It ships with the project-tracker plugin (one source of
truth — projects do NOT keep their own copy). Keep it small; the graph is a
projection of these fields.*

Each card = one markdown file. The filename stem **is** the `id`.

```yaml
---
id: sparse-attn-o0             # REQUIRED. stable slug == filename stem
title: Sparse-attn O0 lowering # REQUIRED. short, shown on node line 1
type: task                     # REQUIRED. master-task|task|bug|milestone|decision|research|infra  -> NODE SHAPE
status: in_progress            # REQUIRED. todo|ready|in_progress|blocked|done|dropped              -> NODE COLOR
summary: "one-line what/why"   # REQUIRED. node face line 3 (<= ~80 chars). authored, not auto.
owner: feiw                    # ASSIGNEE — who does the work (NOT the creator). see note below.
updated_by: feiw               # last toucher (shown on node face)
parent: sparse-attn            # optional. the master-task this card decomposes (nests under it)
depends_on: [scaffold]         # optional. ids -> directed dependency edges (arrow dep -> dependent)
tags: [sparse, o0]             # optional. for filter/search
priority: high                 # optional. high|med|low
order: 30                      # optional. int board sort key (ascending); unset -> sorts by created
stack: sparse-attn-o0          # optional. group key — sibling cards sharing it render as ONE stack
created: 2026-05-30
updated: 2026-06-03            # shown on node face
links: { pr: 73399 }           # optional. pr | slack | doc | url ...
validation:                    # the VERIFICATION SCRIPT. REQUIRED to mark status:done.
  branch: dev/<your-branch>    #   which dev branch the check is defined against
  cmd: "python3 ... && grep -q PASS run.0.log"   # an EXECUTABLE pass/fail check (not prose)
  pass_criteria: "argmax >= 99% AND max_abs < 0.02"
  # when none exists yet, state it explicitly so it's legible + flagged on the board:
  #   validation:
  #     script: MISSING
steps:                         # optional. if present, the card renders as a STACK — one card per step.
  - name: "integrate"          #   step label (the stacked card's title). REQUIRED per step.
    status: in_progress        #   todo|ready|in_progress|blocked|done|dropped -> step card color
    kind: step                 #   optional. step|debug (debug = a bug/debugging step -> ◆ + red accent)
    summary: "one-liner"        #   optional. shown on the step card
    when: 2026-06-15            #   optional. date
  # chronological: first = earliest. The LAST step is current (renders on TOP); earlier tuck behind, dim.
  # keep top-level `status` synced to the current (last) step.
runs:                          # optional. node face shows the LATEST; hover shows cmd/artifact
  - when: 2026-06-03
    result: fail               # pass|fail|partial|n/a -> node ✓/✗ badge
    cmd: "python3 ..."
    artifact: /import/.../run.0.log
    note: "short result note"
todo:                          # optional. DEFERRED follow-ups — highlighted in the drawer right
  - text: "the deferred work, one line"   #   after the verification script; face shows a ⏳N chip.
    why: "optional: why it's deferred / what it's blocked on"
    done: false                #   optional. true -> the item flips green (✓) instead of amber (⏳)
  # bare-string form also works:  `- "just the text"`
# fusion/split-ready (no tooling yet; schema supports it):
supersedes: []                 # ids this card merges/replaces
superseded_by: null
---
# Free-form body: full notes, repro, findings. Link related cards with [[other-id]].
```

## Field semantics

- **type -> shape**: `master-task`=container box (nests its children),
  `task`=rounded-rect, `bug`=diamond, `milestone`=hexagon,
  `decision`=parallelogram, `research`=ellipse, `infra`=cylinder.
- **status -> color**: todo=grey, ready=blue, in_progress=amber, blocked=red,
  done=green, dropped=faded.
- **owner = assignee (who does the work), NOT the creator.** There is deliberately no
  `creator` field: in practice the tracker maintainer opens nearly every card, so a
  creator would carry ~no signal and is already derivable from `created` + git history /
  `updated_by`. `owner` may be a single person or a comma-list (`"a, b, c"`) for shared
  work; it renders as the `@owner` chip on the node face and is matched by the `@` search
  filter. If work is ever delegated, just change `owner` — don't add a second person field.
- **master-task**: not worked on directly. Has no `runs`/`validation` of its own.
  Its `status` + node face are **rolled up** from children (children set
  `parent: <this-id>`): face shows progress (e.g. `3/7 done`), color is the
  aggregate (blocked if any child blocked; done only when all children done).
- **depends_on vs parent**: `depends_on` = "needs X finished first" (dependency
  edge). `parent` = "is a piece of master-task X" (containment / nesting). Use
  both as appropriate.
- **validation (the verification script)**: an *executable* pass/fail check, not
  prose. **Required to mark `done`** — a card cannot be credibly closed without one
  (and a matching passing `run`). It is also the regression probe: on each new dev
  branch the script is re-run to decide whether the card still works or regressed.
  master-tasks are exempt (they roll up). A card with no script must say so
  explicitly (`validation:\n  script: MISSING`); the board shows it on the card's
  **bottom strip**: solid red = no script; with a script, one green/red/amber
  segment per dev branch (latest 3, `+N` marker for older).
  **The credibility bar for a PASS is re-runnability, not a frozen commit.** The
  script must be *self-contained* — all inputs in-repo, no private paths — and pass
  when anyone checks out the named `branch` and runs it. That, and only that, is what
  makes a `done` credible: not an artifact path, not a commit hash.
- **runs**: append a record per real run via the `card-verify` skill. The node face
  shows the latest run's `result` badge + date; hover shows its `cmd`/`artifact`.
  Each run carries a `branch:` (dev branch it ran on) — `runs` is a per-branch log.
  **Do NOT record commit hashes.** A SHA is false precision: runs happen on local,
  often-unpushed, often-dirty trees, so a recorded hash points at code nobody else
  can reproduce — worse than no hash, because it invites false trust. Credibility
  comes from re-running the script on the named `branch`, not from pinning bytes.
- **steps (one item, one file)**: a single work item = ONE md file. When that item
  has internal sub-stages (plan → compile → integrate → **debug a blocker**), record
  them as `steps:` entries — do **NOT** spin up a new card per sub-stage or per bug.
  The board renders a multi-step item as a **stack of cards** (current/last step on
  top; earlier done steps tuck behind, dim). A `kind: debug` step is the in-file way
  to track a bug/debugging effort (◆ + red accent) instead of a separate bug file.
  A single-step item just renders as one plain card. Keep top-level `status` synced
  to the current step. Use `card-step` to add/update steps; `card-add` is for new items only.
- **one validation per card == the END step.** A card carries a single
  `validation`/`runs`; on a stacked card the **bottom strip renders only on the top
  (= last = current) step**, so that one verification script validates the card's
  **current/end step**. Earlier steps are not independently verified — they are
  lightweight sub-stages of the one deliverable, validated as a whole when it lands.
  **If a sub-unit needs its OWN independent branch / cmd / validation, it is not a
  step — make it a child card under a `master-task`** (`card-add --parent <master>`).
  Each child then self-validates (own bottom strip, own close-gate) and the master
  rolls up. Rule of thumb: *sub-stage validated at the end → `step`; sub-unit with
  its own verification → child card under a master-task.*
- **todo (deferred follow-ups)**: optional list of follow-up items that are *known and intended but
  deliberately not done now* (e.g. a better approach blocked on another change). Each item has `text`
  (one line; `` `code` ``/`**bold**`/`[[card]]` work), optional `why` (why deferred / what it's blocked
  on), and optional `done` (true → the item flips green). Rendered as a **highlighted amber callout in
  the card drawer, right after the verification script** (so it reads as a peer of it), and the card
  face shows a `⏳N` chip (N = open items). Use it instead of burying follow-ups in the body prose —
  the body is for notes/findings, `todo` is for actionable deferred work that must stay visible.
- **stack (group separate cards into a visual stack)**: optional group key. Cards that share
  the same `stack:` value (under the same parent) render as ONE **stack of cards** — ordered by
  `order`, current/last on top, earlier ones tucked behind and dimmed. Same visual as a `steps[]`
  stack, but **each layer is its own card with its own validation / bottom strip** (one green +
  validated, the next red + script-MISSING, etc.). Use it when the sub-units of one deliverable
  each need **independent verification** yet should still read as one grouped item — e.g. a
  hyperfunction's `…-7b` compile card (validated) stacked with its `…-7c` integrate card (not
  yet). Contrast with `steps[]`: steps = sub-stages in ONE file sharing the end-step validation;
  `stack:` = separate files, each independently validated, drawn together.
- **order**: optional integer. The board (`render.py`) sorts cards — and each
  master's children — by `order` ascending, falling back to `created` (then `id`)
  when unset. Use it to force a reading/step order (e.g. step1<step2<…); space
  values (10, 20, 30…) to leave room to insert. Projects that don't set it are
  unaffected (everything falls back to `created`, the prior behavior).

## Conventions

- `id` is kebab-case and stable — renaming breaks `depends_on`/`parent` edges.
- One card per unit of work that a person would pick up and do (or, for
  `master-task`, a theme that decomposes into such units).

## Body formatting (rendered in the card drawer)

The free-form body supports a small markdown subset in the drawer's *notes* panel:

- `[[other-id]]` → link to that card; `[text](url)` → external link.
- `` `code` ``, `**bold**`.
- `!!text!!` → **red emphasis** — use for warnings (e.g. `!!NOT A REAL PASS CHECK YET!!`).
  Also works in `validation.pass_criteria`.
- A fenced code block ```` ```lang title ```` renders as a **default-collapsed dropdown**
  whose summary is the `title` after the language token (typically a filename). Put the
  dropdown right after the line that first names the script, e.g.:

  ````
  Save this as `run_x.sh`:
  ```bash run_x.sh
  #!/usr/bin/env bash
  ...
  ```
  ````
  Long embedded scripts stay folded so the body reads cleanly; click to expand.
