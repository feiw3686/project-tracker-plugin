#!/usr/bin/env python3
"""Set a card's status (and bump updated / updated_by), then regen graph.json.

Surgical: only rewrites the status/updated/updated_by lines inside the
frontmatter block, preserving the rest of the file (comments, formatting).

Example:
    set_status.py --project minimax_m3 --id m3-o0-lowering --status done --by frankc
"""
import argparse, os, sys, re, datetime, subprocess

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PROJECTS_ROOT = os.path.normpath(os.path.join(SCRIPTS, "..", ".."))
STATUSES = ["todo", "ready", "in_progress", "blocked", "done", "dropped"]


def set_line(block, key, val):
    """Replace `key: ...` in the frontmatter block, or append it."""
    pat = re.compile(rf"^({re.escape(key)}):.*$", re.M)
    if pat.search(block):
        return pat.sub(f"{key}: {val}", block, count=1)
    return block.rstrip("\n") + f"\n{key}: {val}\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="minimax_m3")
    ap.add_argument("--id", required=True)
    ap.add_argument("--status", required=True, choices=STATUSES)
    ap.add_argument("--by", default=None, help="updated_by (defaults to existing owner)")
    a = ap.parse_args()

    path = os.path.join(PROJECTS_ROOT, a.project, "cards", a.id + ".md")
    if not os.path.isfile(path):
        sys.exit(f"no such card: {path}")
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^(---\n)(.*?)(\n---)", text, re.S)
    if not m:
        sys.exit(f"{path}: no frontmatter")
    block = m.group(2)
    today = datetime.date.today().isoformat()
    block = set_line(block, "status", a.status)
    block = set_line(block, "updated", today)
    if a.by:
        block = set_line(block, "updated_by", a.by)
    text = text[:m.start(2)] + block + text[m.end(2):]

    old_umask = os.umask(0o002)
    try:
        open(path, "w", encoding="utf-8").write(text)
    finally:
        os.umask(old_umask)
    print(f"{a.id}: status -> {a.status} (updated {today})")
    subprocess.run([sys.executable, os.path.join(SCRIPTS, "build_graph.py"), a.project])


if __name__ == "__main__":
    main()
