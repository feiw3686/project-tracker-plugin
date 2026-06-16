#!/usr/bin/env python3
"""Regenerate a project's board.

The renderer (render.py) is the SINGLE source of the board generator and lives right
here in the plugin, next to this script. A project dir holds only data (cards/ +
_project.md); regen.py runs the sibling render.py against it. There is no per-project
copy of the renderer, so it can never diverge.

The shared default project root is the NFS notes tree; override with TRACKER_PROJECTS_ROOT.

    regen.py [project]      # default project: minimax_m3
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.join(HERE, "render.py")

PROJECTS_ROOT = os.environ.get(
    "TRACKER_PROJECTS_ROOT", "/import/snvm-sc-scratch1/feiw/notes/projects"
)


def regen(project="minimax_m3"):
    proj = os.path.join(PROJECTS_ROOT, project)
    if not os.path.isdir(proj):
        sys.exit(f"no project dir at {proj} (set TRACKER_PROJECTS_ROOT?)")
    if not os.path.isfile(RENDER):
        sys.exit(f"no renderer at {RENDER} (plugin install corrupt?)")
    return subprocess.run([sys.executable, RENDER, proj]).returncode


if __name__ == "__main__":
    sys.exit(regen(sys.argv[1] if len(sys.argv) > 1 else "minimax_m3"))
