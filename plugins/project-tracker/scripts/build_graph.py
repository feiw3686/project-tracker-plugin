#!/usr/bin/env python3
"""Project graph builder for the markdown card tracker.

Scans <project>/cards/*.md, parses YAML frontmatter, validates the graph
(missing depends_on / parent refs, dependency cycles), rolls up master-task
status from children, and writes <project>/_graph/graph.json — the data the
Cytoscape viewer (_graph/embed.js) loads.

Usage:
    build_graph.py [project]      # project name under projects/ (default: minimax_m3)
    build_graph.py --all          # every dir under projects/ that has cards/

The graph is a pure projection of the card files; this script never edits cards.
"""
import sys, os, re, glob, json, datetime
import yaml

PROJECTS_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

STATUS_ORDER = ["blocked", "in_progress", "ready", "todo", "done", "dropped"]


def parse_frontmatter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        raise ValueError(f"{path}: no frontmatter")
    data = yaml.safe_load(m.group(1)) or {}
    return data


def rollup_status(child_statuses):
    """Aggregate a master-task's status from its children."""
    s = set(child_statuses)
    if not s:
        return "todo"
    if "blocked" in s:
        return "blocked"
    if s <= {"done", "dropped"}:
        return "done"
    if "in_progress" in s:
        return "in_progress"
    if "ready" in s:
        return "ready"
    return "todo"


def build(project):
    pdir = os.path.join(PROJECTS_ROOT, project)
    cards_dir = os.path.join(pdir, "cards")
    if not os.path.isdir(cards_dir):
        raise SystemExit(f"no cards/ dir under {pdir}")
    url_base = "/projects/" + os.path.relpath(pdir, PROJECTS_ROOT).replace(os.sep, "/")

    cards = {}
    errs, warns = [], []
    for p in sorted(glob.glob(os.path.join(cards_dir, "*.md"))):
        stem = os.path.basename(p)[:-3]
        try:
            fm = parse_frontmatter(p)
        except Exception as e:
            errs.append(str(e))
            continue
        cid = fm.get("id")
        if cid != stem:
            errs.append(f"id/stem mismatch: {os.path.basename(p)} id={cid!r}")
            cid = cid or stem
        cards[cid] = fm

    ids = set(cards)

    # --- validate refs ---
    for cid, fm in cards.items():
        par = fm.get("parent")
        if par and par not in ids:
            errs.append(f"{cid}: parent {par!r} does not exist")
        for d in fm.get("depends_on") or []:
            if d not in ids:
                errs.append(f"{cid}: depends_on {d!r} does not exist")

    # --- cycle check over depends_on ---
    WHITE, GREY, BLACK = 0, 1, 2
    color = {cid: WHITE for cid in cards}

    def dfs(u, stack):
        color[u] = GREY
        for v in cards[u].get("depends_on") or []:
            if v not in cards:
                continue
            if color[v] == GREY:
                errs.append("dependency cycle: " + " -> ".join(stack + [v]))
            elif color[v] == WHITE:
                dfs(v, stack + [v])
        color[u] = BLACK

    for cid in cards:
        if color[cid] == WHITE:
            dfs(cid, [cid])

    # --- children index + master rollups ---
    children = {}
    for cid, fm in cards.items():
        par = fm.get("parent")
        if par:
            children.setdefault(par, []).append(cid)

    nodes, edges = [], []
    for cid, fm in cards.items():
        typ = fm.get("type", "task")
        status = fm.get("status", "todo")
        progress = None
        if typ == "master-task":
            kids = children.get(cid, [])
            kid_status = [cards[k].get("status", "todo") for k in kids]
            status = rollup_status(kid_status)
            done = sum(1 for s in kid_status if s in ("done", "dropped"))
            progress = f"{done}/{len(kids)} done" if kids else "0/0"
            if not kids:
                warns.append(f"{cid}: master-task with no children")

        runs = fm.get("runs") or []
        last = runs[-1] if runs else {}
        result = last.get("result")

        data = {
            "id": cid,
            "title": fm.get("title", cid),
            "type": typ,
            "status": status,
            "summary": fm.get("summary", ""),
            "owner": fm.get("owner", ""),
            "updated_by": fm.get("updated_by", fm.get("owner", "")),
            "created": str(fm.get("created", "")),
            "updated": str(fm.get("updated", "")),
            "priority": fm.get("priority", ""),
            "tags": fm.get("tags") or [],
            "result": result or "",
            "deps": fm.get("depends_on") or [],
            "href": f"{url_base}/cards/{cid}.md",
        }
        if fm.get("order") is not None:
            data["order"] = fm.get("order")  # optional explicit board ordering; viewer sorts by it then created
        if progress is not None:
            data["progress"] = progress
        if last.get("cmd"):
            data["last_cmd"] = last["cmd"]
        if last.get("artifact"):
            data["last_artifact"] = last["artifact"]
        if last.get("note"):
            data["last_note"] = last["note"]
        par = fm.get("parent")
        if par in ids:
            data["parent"] = par  # cytoscape compound nesting
        nodes.append({"data": data})

        for d in fm.get("depends_on") or []:
            if d in ids:
                edges.append({"data": {"id": f"{d}__{cid}", "source": d, "target": cid, "kind": "dep"}})

    out = {
        "project": project,
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "stats": {
            "cards": len(cards),
            "by_status": _count(cards, "status"),
            "by_type": _count(cards, "type"),
        },
        "nodes": nodes,
        "edges": edges,
    }
    graph_dir = os.path.join(pdir, "_graph")
    os.makedirs(graph_dir, exist_ok=True)
    outpath = os.path.join(graph_dir, "graph.json")
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"[{project}] {len(cards)} cards, {len(edges)} dep-edges -> {outpath}")
    for w in warns:
        print(f"  warn: {w}")
    if errs:
        print(f"  {len(errs)} ERROR(S):")
        for e in errs:
            print(f"   - {e}")
    return len(errs)


def _count(cards, key):
    out = {}
    for fm in cards.values():
        out[fm.get(key, "?")] = out.get(fm.get(key, "?"), 0) + 1
    return out


def main(argv):
    if "--all" in argv:
        projects = [
            d for d in sorted(os.listdir(PROJECTS_ROOT))
            if os.path.isdir(os.path.join(PROJECTS_ROOT, d, "cards"))
        ]
    else:
        projects = [a for a in argv[1:] if not a.startswith("-")] or ["minimax_m3"]
    rc = 0
    for p in projects:
        rc += build(p)
    return 1 if rc else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
