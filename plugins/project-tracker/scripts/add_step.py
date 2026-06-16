#!/usr/bin/env python3
"""Append a step to a card's steps[] list (the stack-of-steps model), then regen the board.

One md = one item; its sub-stages and DEBUGGING live as steps, NOT separate cards. A step
with --kind debug is the in-file way to track a bug/blocker (renders as a ◆/red step card).
The board renders steps[] as a stack: the LAST step on top, earlier (done) steps tucked behind.

    add_step.py --project minimax_m3 --id m3-7c-integration \
        --name "RAIL PMU capacity" --status blocked --kind debug \
        --summary "32768 PMU vs 1040/RDU" --by feiw --sync-status

--sync-status sets the card's top-level status to this (now-current) step's status.
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="minimax_m3")
    ap.add_argument("--id", required=True)
    ap.add_argument("--name", required=True, help="step label (the stacked card's title)")
    ap.add_argument("--status", required=True, choices=STATUSES)
    ap.add_argument("--kind", choices=["step", "debug"], default="step")
    ap.add_argument("--summary", default=None)
    ap.add_argument("--by", default=None, help="updated_by")
    ap.add_argument("--sync-status", action="store_true",
                    help="set the card's top-level status to this step's status")
    a = ap.parse_args()

    path = os.path.join(PROJECTS_ROOT, a.project, "cards", a.id + ".md")
    if not os.path.isfile(path):
        sys.exit(f"no such card: {path}")
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^(---\n)(.*?)(\n---)", text, re.S)
    if not m:
        sys.exit(f"{path}: no frontmatter")
    block = m.group(2)

    step = [f"  - name: {a.name}", f"    status: {a.status}"]
    if a.kind == "debug":
        step.append("    kind: debug")
    if a.summary:
        step.append(f'    summary: "{a.summary}"')
    step_text = "\n".join(step)

    lines = block.split("\n")
    if any(re.match(r"^steps:\s*$", ln) for ln in lines):
        # append after the LAST indented line of the existing steps: block
        si = next(i for i, ln in enumerate(lines) if re.match(r"^steps:\s*$", ln))
        j = si + 1
        while j < len(lines) and (lines[j].startswith(" ") or not lines[j].strip()):
            j += 1
        lines[j:j] = step.copy()
        block = "\n".join(lines)
    else:
        # create steps: — before `runs:` if present, else at end of the block
        new_block = "steps:\n" + step_text
        rm = re.search(r"^runs:\s*$", block, re.M)
        if rm:
            block = block[:rm.start()] + new_block + "\n" + block[rm.start():]
        else:
            block = block.rstrip("\n") + "\n" + new_block + "\n"

    if a.sync_status:
        block = set_line(block, "status", a.status)
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
    print(f"{a.id}: +step '{a.name}' ({a.status}{', debug' if a.kind == 'debug' else ''})")
    subprocess.run([sys.executable, os.path.join(SCRIPTS, "regen.py"), a.project])


if __name__ == "__main__":
    main()
