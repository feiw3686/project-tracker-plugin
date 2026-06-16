#!/usr/bin/env python3
"""Generic-fix a card: surgically set common fields, bump updated/updated_by, regen board.

Covers status + relationships + light metadata (the merged card-status + card-link).
Only rewrites the named frontmatter lines; preserves the rest (comments, steps, runs).

    card_edit.py --project minimax_m3 --id m3-o0-lowering --status done --by frankc
    card_edit.py --id m3-l1-parity --add-dep m3-checkpoint-load
    card_edit.py --id m3-foo --parent m3-perfsdk --owner faline --priority high

NOTE on closing: setting --status done is gated in the card-edit SKILL (needs a real
validation script + a passing run). This script does not itself enforce the gate.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PROJECTS_ROOT = os.environ.get(
    "TRACKER_PROJECTS_ROOT", "/import/snvm-sc-scratch1/feiw/notes/projects"
)
STATUSES = ["todo", "ready", "in_progress", "blocked", "done", "dropped"]


def set_line(block, key, val):
    pat = re.compile(rf"^({re.escape(key)}):.*$", re.M)
    if pat.search(block):
        return pat.sub(f"{key}: {val}", block, count=1)
    return block.rstrip("\n") + f"\n{key}: {val}\n"


def get_list(block, key):
    m = re.search(rf"^{re.escape(key)}:\s*\[(.*?)\]\s*$", block, re.M)
    if not m:
        return None
    inner = m.group(1).strip()
    return [x.strip() for x in inner.split(",") if x.strip()] if inner else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="minimax_m3")
    ap.add_argument("--id", required=True)
    ap.add_argument("--status", choices=STATUSES)
    ap.add_argument("--parent")
    ap.add_argument("--owner")
    ap.add_argument("--summary")
    ap.add_argument("--priority", choices=["high", "med", "low"])
    ap.add_argument("--add-dep", action="append", default=[], help="add an id to depends_on")
    ap.add_argument("--rm-dep", action="append", default=[], help="remove an id from depends_on")
    ap.add_argument("--by", default=None, help="updated_by")
    a = ap.parse_args()

    path = os.path.join(PROJECTS_ROOT, a.project, "cards", a.id + ".md")
    if not os.path.isfile(path):
        sys.exit(f"no such card: {path}")
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^(---\n)(.*?)(\n---)", text, re.S)
    if not m:
        sys.exit(f"{path}: no frontmatter")
    block = m.group(2)
    changed = []

    if a.status:
        block = set_line(block, "status", a.status); changed.append(f"status={a.status}")
    if a.parent:
        block = set_line(block, "parent", a.parent); changed.append(f"parent={a.parent}")
    if a.owner:
        block = set_line(block, "owner", a.owner); changed.append(f"owner={a.owner}")
    if a.summary:
        block = set_line(block, "summary", f'"{a.summary}"'); changed.append("summary")
    if a.priority:
        block = set_line(block, "priority", a.priority); changed.append(f"priority={a.priority}")
    if a.add_dep or a.rm_dep:
        deps = get_list(block, "depends_on") or []
        for d in a.add_dep:
            if d not in deps:
                deps.append(d)
        deps = [d for d in deps if d not in a.rm_dep]
        block = set_line(block, "depends_on", "[" + ", ".join(deps) + "]")
        changed.append("depends_on=[" + ", ".join(deps) + "]")

    if not changed:
        sys.exit("nothing to change (pass --status / --parent / --add-dep / ...)")

    block = set_line(block, "updated", datetime.date.today().isoformat())
    if a.by:
        block = set_line(block, "updated_by", a.by)
    text = text[: m.start(2)] + block + text[m.end(2):]

    old_umask = os.umask(0o002)
    try:
        open(path, "w", encoding="utf-8").write(text)
    finally:
        os.umask(old_umask)
    try:
        os.chmod(path, 0o664)
    except OSError:
        pass
    print(f"{a.id}: {', '.join(changed)}")
    subprocess.run([sys.executable, os.path.join(SCRIPTS, "regen.py"), a.project])


if __name__ == "__main__":
    main()
