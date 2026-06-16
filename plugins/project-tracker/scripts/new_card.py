#!/usr/bin/env python3
"""Scaffold a new tracker card and regenerate the project's graph.json.

Writes projects/<project>/cards/<id>.md with valid frontmatter, then runs
build_graph.py. Both humans and the card-add skill can call this for the
mechanical part; the skill adds the judgement (id, summary, deps).

Example:
    new_card.py --project minimax_m3 --id m3-foo --title "Foo work" \
        --type task --status todo --owner frankc \
        --summary "one-line what/why" --parent m3-moe --depends m3-l0-parity --tags moe,o0
"""
import argparse, os, sys, datetime, subprocess

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PROJECTS_ROOT = os.path.normpath(os.path.join(SCRIPTS, "..", ".."))
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
    ap.add_argument("--priority", default=None, choices=[None, "high", "med", "low"])
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

    fm = ["---", f"id: {a.id}", f"title: {a.title}", f"type: {a.type}",
          f"status: {a.status}", f'summary: "{a.summary}"']
    if a.owner:
        fm.append(f"owner: {a.owner}")
    fm.append(f"updated_by: {a.updated_by or a.owner}")
    if a.parent:
        fm.append(f"parent: {a.parent}")
    if deps:
        fm.append("depends_on: [" + ", ".join(deps) + "]")
    if tags:
        fm.append("tags: [" + ", ".join(tags) + "]")
    if a.priority:
        fm.append(f"priority: {a.priority}")
    fm += [f"created: {today}", f"updated: {today}", "---", "",
           f"# {a.title}", "", (a.body or a.summary or "").strip(), ""]

    old_umask = os.umask(0o002)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(fm))
    finally:
        os.umask(old_umask)
    print(f"wrote {path}")
    subprocess.run([sys.executable, os.path.join(SCRIPTS, "build_graph.py"), a.project])


if __name__ == "__main__":
    main()
