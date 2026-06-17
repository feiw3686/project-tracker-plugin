#!/usr/bin/env python3
"""Scaffold a new tracker card and regenerate the project's board.

Writes <project>/cards/<id>.md with valid frontmatter, then regenerates the board
(render.py via regen.py). Both humans and the card-add skill can call this
for the mechanical part; the skill adds the judgement (id, summary, deps).

Example:
    new_card.py --project minimax_m3 --id m3-foo --title "Foo work" \
        --type task --status todo --owner frankc \
        --summary "one-line what/why" --parent m3-moe --depends m3-l0-parity --tags moe,o0
"""
import argparse, os, sys, datetime, subprocess

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
# cards live in the shared NFS notes tree (same path for everyone on the cluster);
# override with TRACKER_PROJECTS_ROOT if your checkout lives elsewhere.
PROJECTS_ROOT = os.environ.get(
    "TRACKER_PROJECTS_ROOT", "/import/snvm-sc-scratch1/feiw/notes/projects"
)
TYPES = ["master-task", "task", "bug", "milestone", "decision", "research", "infra"]
STATUSES = ["todo", "ready", "in_progress", "blocked", "done", "dropped"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="minimax_m3")
    ap.add_argument("--id", required=True, help="kebab-case slug == filename stem")
    ap.add_argument("--title", required=True)
    ap.add_argument("--type", default="task", choices=TYPES)
    ap.add_argument("--status", default="todo", choices=STATUSES)
    ap.add_argument("--summary", default="")
    ap.add_argument("--owner", default="")
    ap.add_argument("--updated-by", default=None)
    ap.add_argument("--parent", default=None)
    ap.add_argument("--depends", default="", help="comma-separated ids")
    ap.add_argument("--tags", default="", help="comma-separated")
    ap.add_argument("--milestone", type=int, default=None,
                    help="0-9 bring-up step -> adds a step<N> tag (places the card in that swimlane)")
    ap.add_argument("--priority", default=None, choices=[None, "high", "med", "low"])
    ap.add_argument("--validation-cmd", default=None,
                    help="executable verification script (pass/fail). If omitted, a non-master "
                         "card is scaffolded with `validation: script: MISSING` (flagged on the board).")
    ap.add_argument("--validation-branch", default=None, help="dev branch the verification runs on")
    ap.add_argument("--pass-criteria", default=None, help="human-readable pass criteria")
    ap.add_argument("--body", default="", help="markdown body (defaults to the summary)")
    ap.add_argument("--force", action="store_true", help="overwrite if the card exists")
    a = ap.parse_args()

    cards = os.path.join(PROJECTS_ROOT, a.project, "cards")
    if not os.path.isdir(cards):
        sys.exit(f"no cards dir: {cards}")
    path = os.path.join(cards, a.id + ".md")
    if os.path.exists(path) and not a.force:
        sys.exit(f"card already exists: {path} (use --force to overwrite)")

    today = datetime.date.today().isoformat()
    deps = [d.strip() for d in a.depends.split(",") if d.strip()]
    tags = [t.strip() for t in a.tags.split(",") if t.strip()]
    if a.milestone is not None and f"step{a.milestone}" not in tags:
        tags.append(f"step{a.milestone}")

    fm = ["---", f"id: {a.id}", f"title: {a.title}", f"type: {a.type}",
          f"status: {a.status}", f'summary: "{a.summary}"']
    # owner is the ASSIGNEE (who does the work). New cards default to UNASSIGNED — omit the
    # line entirely unless a taker is explicitly given (--owner); assign later inline on the
    # board. updated_by reflects the creator / last editor, which is NOT ownership.
    if a.owner:
        fm.append(f"owner: {a.owner}")
    ub = a.updated_by or a.owner
    if ub:
        fm.append(f"updated_by: {ub}")
    if a.parent:
        fm.append(f"parent: {a.parent}")
    if deps:
        fm.append("depends_on: [" + ", ".join(deps) + "]")
    if tags:
        fm.append("tags: [" + ", ".join(tags) + "]")
    if a.priority:
        fm.append(f"priority: {a.priority}")
    # verification script: master-tasks are exempt (they roll up); every other card
    # carries one — a real cmd if known, else an explicit MISSING marker (flagged red).
    if a.type != "master-task":
        if a.validation_cmd:
            fm.append("validation:")
            if a.validation_branch:
                fm.append(f"  branch: {a.validation_branch}")
            fm.append(f'  cmd: "{a.validation_cmd}"')
            if a.pass_criteria:
                fm.append(f'  pass_criteria: "{a.pass_criteria}"')
        else:
            fm.append("validation:")
            fm.append("  script: MISSING   # Verification Script MISSING — no runnable check; cannot be credibly closed")
    fm += [f"created: {today}", f"updated: {today}", "---", "",
           f"# {a.title}", "", (a.body or a.summary or "").strip(), ""]

    old_umask = os.umask(0o002)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(fm))
    finally:
        os.umask(old_umask)
    # belt-and-suspenders: cards live in a shared group-writable tree, so anyone in
    # the group can edit. Force 664 regardless of the caller's umask (the #1 cause of
    # "card not editable by others" is a creator whose umask was 022 -> 644).
    try:
        os.chmod(path, 0o664)
    except OSError:
        pass
    print(f"wrote {path}")
    subprocess.run([sys.executable, os.path.join(SCRIPTS, "regen.py"), a.project])


if __name__ == "__main__":
    main()
