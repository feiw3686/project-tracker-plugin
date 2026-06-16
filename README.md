# project-tracker-plugin

A Claude Code plugin for maintaining a **markdown card-graph project tracker** —
the cards and the milestone board you see at the project landing page (e.g.
`http://sc-vnc7.sambanovasystems.com:8765/projects/minimax_m3/`). Installs the
same way as the branch-management plugin.

Cards are one markdown file each, under
`/import/snvm-sc-scratch1/feiw/notes/projects/<project>/cards/<id>.md`; the board
is a projection of those files. The skills let you create and update cards
conversationally instead of hand-editing markdown.

## Skills

| skill | say |
|---|---|
| `card-add` | "add a card for …", "track this as a task" |
| `card-status` | "mark m3-o0-lowering done", "X is blocked" |
| `card-link` | "X depends on Y", "make X a subtask of master Z" |
| `card-run` | "log a fail on m3-checkpoint-load: \<cmd\>", "this passed" |

(More skills for maintaining the board + cards will be added over time.)

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
plugins/project-tracker/
  .claude-plugin/plugin.json             # plugin manifest
  skills/{card-add,card-status,card-link,card-run}/SKILL.md
  scripts/{new_card,set_status,build_graph}.py   # helpers (referenced via ${CLAUDE_PLUGIN_ROOT})
```
