#!/usr/bin/env python3
"""Regenerate a project's board — runs its build_project2.py (the milestone board).

The board generator lives in the project dir (next to cards/ and _project.md), so the
board is a pure projection of the cards. The shared default root is the NFS notes tree;
override with the TRACKER_PROJECTS_ROOT env var.

    regen.py [project]      # default project: minimax_m3
"""
import os
import subprocess
import sys

PROJECTS_ROOT = os.environ.get(
    "TRACKER_PROJECTS_ROOT", "/import/snvm-sc-scratch1/feiw/notes/projects"
)


def regen(project="minimax_m3"):
    proj = os.path.join(PROJECTS_ROOT, project)
    gen = os.path.join(proj, "build_project2.py")
    if not os.path.isfile(gen):
        sys.exit(f"no board generator at {gen} (set TRACKER_PROJECTS_ROOT?)")
    return subprocess.run([sys.executable, gen], cwd=proj).returncode


if __name__ == "__main__":
    sys.exit(regen(sys.argv[1] if len(sys.argv) > 1 else "minimax_m3"))
