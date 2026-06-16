# project-tracker-plugin

A Claude Code plugin for maintaining a **markdown card-graph project tracker** —
the cards and the milestone board you see at the project landing page (e.g.
`http://sc-vnc7.sambanovasystems.com:8765/projects/minimax_m3/`). Installs the
same way as the branch-management plugin.

Cards are one markdown file each, under
`/import/snvm-sc-scratch1/feiw/notes/projects/<project>/cards/<id>.md`; the board
is a projection of those files. The skills let you create and update cards
conversationally instead of hand-editing markdown.

> **Design & rationale:** see [DESIGN.md](DESIGN.md) — the card model, the milestone board,
> the credibility/validation contract, per-branch regression tracking, and the skill roadmap.

## Skills

| skill | say |
|---|---|
| `card-add` | "add a card for …", "track this as a new task" (a **new item**) |
| `card-step` | "X is blocked by …", "debug the failure in X", "next stage of X" (a **step**, incl. debug — not a new card) |
| `card-verify` | "add a verification script for X", "log a fail on X: \<cmd\>", "this passed on dev-06-15" |
| `card-edit` | "mark m3-o0-lowering done", "X depends on Y", "make X a subtask of Z", "reassign X" |

**Core model:** one md file = one work item; its sub-stages and debugging are `steps`
(a card stack), not separate files. Every non-master card needs a `validation`
**verification script** (the close-gate + per-branch regression probe). See [DESIGN.md](DESIGN.md).

(More skills — e.g. `add-dev-branch` automation — will be added over time.)

## One-time install

```bash
# in your shell — older Claude Code versions reject the plugin
claude update

# GitHub CLI auth (if not already done)
sudo yum-config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo
sudo yum -y install gh
gh auth login
```

```text
# inside Claude Code
/plugin marketplace add https://github.com/feiw3686/project-tracker-plugin.git
/plugin install project-tracker
/reload-plugins
```

## Pull later updates

```text
/plugin marketplace update project-tracker
/reload-plugins
```

## Layout

```
.claude-plugin/marketplace.json          # marketplace manifest
DESIGN.md                                # the why: card model, board, credibility, regression
plugins/project-tracker/
  .claude-plugin/plugin.json             # plugin manifest
  skills/{card-add,card-step,card-verify,card-edit}/SKILL.md
  scripts/{new_card,add_step,card_edit,regen}.py   # helpers (referenced via ${CLAUDE_PLUGIN_ROOT})
```
