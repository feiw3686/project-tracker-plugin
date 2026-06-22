#!/usr/bin/env python3
"""render.py — INDEPENDENT milestone-swimlane board generator (project-tracker).

This is the SINGLE source of the board renderer. It lives in the plugin repo and is
run against a project dir (which holds only data: cards/ + _project.md). There is no
per-project copy of this file — `regen.py` invokes this one as its sibling, so the
renderer can never diverge across projects.

Reads the canonical cards/*.md directly (the same files the card-* skills write)
and emits a single self-contained _project2.html. No dependency on _graph/embed.js,
graph.json, m3-tracker/dag_from_md.py, Mermaid, or any CDN. Pure DOM/CSS/SVG.

Layout = the design in DESIGN.md:
  * milestones (the big steps) are horizontal lanes, stacked top-to-bottom
  * within a lane, rich rounded-rect cards flow left->right and wrap
  * master-tasks render as a titled cluster containing their child cards
  * a card's `bug` children render as a STACK: open/blocked bug overlays ON TOP
    (red), resolved bug tucks BEHIND (dimmed) -> the hyperfunction+debug metaphor
  * depends_on -> "needs:" chips (click to flash the target)
  * click any card -> a detail drawer (status, owner, deps, latest run cmd/artifact,
    PR link, body, "open source .md") + a copy-link button (deep-link to the card)
  * a "Meeting notes" button (by the overview) opens a LEFT, non-modal, editable drawer on
    the project's rolling _meeting.md (Edit/Preview rendered markdown; saved via the edit
    sidecar, autosave + optimistic-version conflict guard). Coexists with the card drawer.

Milestone is derived from each card's own `stepN` tag, inherited through `parent`
chains — fully data-driven, independent of any other tracker's hand map.

Per-project specifics — board title, milestone lane names, PR-link base URL — are read
from the project's _project.md front-matter (load_project_config), NOT hardcoded here.

Usage:
    python3 render.py <project-dir>           # -> <project-dir>/_project2.html
    python3 render.py <project-dir> -o /path/out.html
    python3 render.py <project-dir> --cards-dir cards
"""
import argparse
import datetime
import html as _html
import json
import os
import re

# Fallback lane names if a project's _project.md declares no `milestones:` block.
# Real projects override this in their _project.md front-matter (see load_project_config).
DEFAULT_MILESTONES = [
    (0, "Backlog"),
    (1, "Planning"),
    (2, "In progress"),
    (3, "Review"),
    (4, "Done"),
]


def strip_val(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def parse_list(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [strip_val(x) for x in inner.split(",")]
    return [strip_val(v)] if v else []


def parse_inline_dict(v):
    v = v.strip()
    out = {}
    if v.startswith("{") and v.endswith("}"):
        inner = v[1:-1].strip()
        if not inner:
            return out
        for part in inner.split(","):
            if ":" in part:
                k, val = part.split(":", 1)
                out[k.strip()] = strip_val(val)
    return out


def split_frontmatter(text):
    """Return (frontmatter_text, body_text). Frontmatter is between the first --- pair."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def parse_frontmatter(fm_text):
    fm = {}
    runs = []
    steps = []
    todos = []
    validation = {}
    lists = {"runs": runs, "steps": steps, "todo": todos}
    cur_item = None     # current list item (run / step / todo)
    mode = None         # None | "runs" | "steps" | "todo" | "val"
    for raw in fm_text.split("\n"):
        if mode in lists:
            lst = lists[mode]
            mitem = re.match(r"^\s+-\s*(.*)$", raw)
            if mitem:
                item = {}
                lst.append(item)
                cur_item = item
                rest = mitem.group(1)
                mk = re.match(r"^([\w-]+):\s*(.*)$", rest)
                if mk:
                    item[mk.group(1)] = strip_val(mk.group(2))
                else:
                    item["text"] = strip_val(rest)  # bare-string item (e.g. `- some text`)
                continue
            mfield = re.match(r"^\s+([\w-]+):\s*(.*)$", raw)
            if mfield and cur_item is not None:
                cur_item[mfield.group(1)] = strip_val(mfield.group(2))
                continue
            if not raw.strip():
                continue
            mode = None  # dedented -> back to top-level fields
        elif mode == "val":
            if raw.strip().startswith("#"):
                continue  # YAML comment inside the block
            mfield = re.match(r"^\s+([\w-]+):\s*(.*)$", raw)
            if mfield:
                validation[mfield.group(1)] = strip_val(mfield.group(2))
                continue
            if not raw.strip():
                continue
            mode = None  # dedented -> back to top-level fields
        if not raw.strip():
            continue
        if re.match(r"^runs:\s*$", raw):
            mode = "runs"
            continue
        if re.match(r"^steps:\s*$", raw):
            mode = "steps"
            continue
        if re.match(r"^todo:\s*$", raw):
            mode = "todo"
            continue
        if re.match(r"^validation:\s*$", raw):
            mode = "val"
            continue
        m = re.match(r"^(\w+):\s*(.*)$", raw)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    fm["_runs"] = runs
    fm["_steps"] = steps
    fm["_todos"] = todos
    fm["_validation"] = validation
    return fm


def load_card(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    fm_text, body = split_frontmatter(text)
    fm = parse_frontmatter(fm_text)
    runs = fm.pop("_runs", [])
    steps = fm.pop("_steps", [])
    todos = fm.pop("_todos", [])
    latest = runs[-1] if runs else None
    # per-branch health: latest run result per branch, in first-seen (chronological) order.
    # drives the card's bottom strip (one segment per dev branch the verification ran on).
    _brmap, _brorder = {}, []
    for r in runs:
        key = r.get("branch") or "—"
        if key not in _brmap:
            _brorder.append(key)
        _brmap[key] = {"branch": key, "result": r.get("result", ""), "when": r.get("when", "")}
    branch_runs = [_brmap[k] for k in _brorder]
    links = parse_inline_dict(fm.get("links", "")) if fm.get("links") else {}
    try:
        order = int(strip_val(fm.get("order", "")))
    except (TypeError, ValueError):
        order = None
    validation = fm.pop("_validation", {}) or {}
    ctype = strip_val(fm.get("type", "task"))
    # the "verification script" = an executable validation.cmd. master-tasks roll up
    # and are exempt; every other card must carry one to be credibly closeable.
    has_verification = bool(validation.get("cmd"))
    card = {
        "id": strip_val(fm.get("id", os.path.splitext(os.path.basename(path))[0])),
        "title": strip_val(fm.get("title", "")),
        "type": ctype,
        "status": strip_val(fm.get("status", "todo")),
        "summary": strip_val(fm.get("summary", "")),
        "owner": strip_val(fm.get("owner", "")),
        "updated_by": strip_val(fm.get("updated_by", "")),
        "parent": strip_val(fm.get("parent", "")) or None,
        "depends_on": parse_list(fm.get("depends_on", "")) if fm.get("depends_on") else [],
        "tags": parse_list(fm.get("tags", "")) if fm.get("tags") else [],
        "priority": strip_val(fm.get("priority", "")),
        "created": strip_val(fm.get("created", "")),
        "updated": strip_val(fm.get("updated", "")),
        "order": order,
        "stack": strip_val(fm.get("stack", "")) or None,
        "links": links,
        "result": (latest or {}).get("result", ""),
        "run": latest,
        "branch_runs": branch_runs,
        "steps": steps,
        "todos": todos,
        "validation": validation,
        "has_verification": has_verification,
        "needs_verification": ctype != "master-task",
        "body": body.strip(),
        "milestone": None,
    }
    return card


def step_from_tags(card):
    for t in card["tags"]:
        m = re.match(r"step(\d+)$", t)
        if m:
            return int(m.group(1))
    return None


def derive_milestones(cards):
    by_id = {c["id"]: c for c in cards}
    for c in cards:
        c["milestone"] = step_from_tags(c)
    # inherit through parent chains until fixpoint
    changed = True
    guard = 0
    while changed and guard < 50:
        changed = False
        guard += 1
        for c in cards:
            if c["milestone"] is None and c["parent"] and c["parent"] in by_id:
                pm = by_id[c["parent"]]["milestone"]
                if pm is not None:
                    c["milestone"] = pm
                    changed = True


# --------------------------------------------------- minimal markdown -> html
# Covers the subset used in _project.md: headings, **bold**, `code`, [t](u),
# - lists, > blockquotes, | tables |, --- rules, paragraphs. No CDN, stdlib only.

def md_inline(s):
    s = _html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", lambda m: "<code>" + m.group(1) + "</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: '<a href="' + m.group(2) + '" target="_blank">' + m.group(1) + "</a>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*\n]+)\*", r"<em>\1</em>", s)  # after bold, so ** is already consumed
    return s


def _md_table(rows):
    def cells(r):
        return [c.strip() for c in r.strip().strip("|").split("|")]
    header = cells(rows[0])
    body = rows[2:] if len(rows) >= 2 and re.search(r"-{2,}", rows[1]) else rows[1:]
    h = "<tr>" + "".join("<th>" + md_inline(c) + "</th>" for c in header) + "</tr>"
    b = "".join("<tr>" + "".join("<td>" + md_inline(c) + "</td>" for c in cells(r)) + "</tr>" for r in body)
    return "<table>" + h + b + "</table>"


def _render_items(items, start, indent):
    """items: list of (indent_spaces, text). Recursive nested <ul> builder."""
    html = "<ul>"
    i = start
    while i < len(items):
        ind, txt = items[i]
        if ind < indent:
            break
        if ind > indent:
            indent = ind  # defensive: first item sets the level
        html += "<li>" + md_inline(txt)
        i += 1
        if i < len(items) and items[i][0] > indent:
            child, i = _render_items(items, i, items[i][0])
            html += child
        html += "</li>"
    return html + "</ul>", i


def render_list(items):
    if not items:
        return ""
    html, _ = _render_items(items, 0, items[0][0])
    return html


def md_to_html(md):
    lines = md.split("\n")
    out, para = [], []
    i, n = 0, len(lines)

    def flush():
        if para:
            out.append("<p>" + md_inline(" ".join(para)) + "</p>")
            para.clear()

    while i < n:
        s = lines[i].strip()
        if not s:
            flush(); i += 1; continue
        if s.startswith("```"):
            flush(); i += 1; code = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i]); i += 1
            i += 1  # skip closing fence
            out.append("<pre><code>" + _html.escape("\n".join(code), quote=False) + "</code></pre>"); continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush(); lvl = min(len(m.group(1)) + 1, 6)
            out.append("<h%d>%s</h%d>" % (lvl, md_inline(m.group(2)), lvl)); i += 1; continue
        if re.match(r"^(-{3,}|\*{3,})$", s):
            flush(); out.append("<hr>"); i += 1; continue
        if s.startswith("|"):
            flush(); tbl = []
            while i < n and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip()); i += 1
            out.append(_md_table(tbl)); continue
        if s.startswith(">"):
            flush(); bq = []
            while i < n and lines[i].strip().startswith(">"):
                bq.append(re.sub(r"^\s*>\s?", "", lines[i])); i += 1
            out.append("<blockquote>" + md_to_html("\n".join(bq)) + "</blockquote>"); continue
        if re.match(r"^\s*[-*]\s+", lines[i]):
            flush(); litems = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                lm = re.match(r"^(\s*)[-*]\s+(.*)$", lines[i])
                litems.append((len(lm.group(1).expandtabs(2)), lm.group(2))); i += 1
            out.append(render_list(litems)); continue
        para.append(s); i += 1
    flush()
    return "\n".join(out)


def load_overview(md_path):
    """Project-level globals: everything in _project.md BEFORE the status board heading."""
    if not os.path.exists(md_path):
        return ""
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    _, body = split_frontmatter(text)
    idx = body.find("## Status board")
    if idx >= 0:
        body = body[:idx]
    return md_to_html(body.strip())


def load_cards(cards_dir):
    cards = []
    for name in sorted(os.listdir(cards_dir)):
        if name.endswith(".md") and not name.startswith("_"):
            cards.append(load_card(os.path.join(cards_dir, name)))
    derive_milestones(cards)
    return cards


def load_project_config(md_path):
    """Per-project board config from _project.md front-matter. Returns:
        title         board title / page <title> / h1   (default "Project board")
        pr_url_base   prefix for PR links; links.pr is appended (default "" -> no link)
        milestones    [[num, name], ...] lane definitions  (default DEFAULT_MILESTONES)

    The `milestones:` block is a YAML list of `<num>: <name>` items, e.g.:
        milestones:
          - 0: HF reference
          - 1: Scaffold & Stage
    """
    cfg = {"title": "Project board", "pr_url_base": "", "milestones": []}
    if not os.path.exists(md_path):
        cfg["milestones"] = [list(m) for m in DEFAULT_MILESTONES]
        return cfg
    with open(md_path, "r", encoding="utf-8") as f:
        fm_text, _ = split_frontmatter(f.read())
    mode = None
    for raw in fm_text.split("\n"):
        if mode == "milestones":
            mitem = re.match(r"^\s+-\s*(\d+)\s*:\s*(.+?)\s*$", raw)
            if mitem:
                cfg["milestones"].append([int(mitem.group(1)), strip_val(mitem.group(2))])
                continue
            if not raw.strip():
                continue
            mode = None  # dedented -> back to top-level fields
        if re.match(r"^milestones:\s*$", raw):
            mode = "milestones"
            continue
        mk = re.match(r"^(\w+):\s*(.*)$", raw)
        if mk and mk.group(1) in ("title", "pr_url_base"):
            # drop any trailing ` # comment` then strip quotes
            val = re.sub(r"\s+#.*$", "", mk.group(2))
            cfg[mk.group(1)] = strip_val(val)
    if not cfg["milestones"]:
        cfg["milestones"] = [list(m) for m in DEFAULT_MILESTONES]
    return cfg


# ------------------------------------------------------------------ template

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — milestone board</title>
<style>
:root{
  --todo:#9ca3af; --ready:#3b82f6; --wip:#f59e0b; --blocked:#ef4444;
  --done:#22c55e; --dropped:#cbd5e1;
  --todo-bg:#f3f4f6; --ready-bg:#eff6ff; --wip-bg:#fffbeb; --blocked-bg:#fef2f2;
  --done-bg:#f0fdf4; --dropped-bg:#f8fafc;
  --ink:#111827; --muted:#6b7280; --line:#e5e7eb; --bg:#fafafa;
}
*{box-sizing:border-box}
body{margin:0;font:13px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}
a{color:#2563eb;text-decoration:none} a:hover{text-decoration:underline}
.topbar{position:sticky;top:0;z-index:50;background:#fff;border-bottom:1px solid var(--line);padding:10px 16px}
.topbar h1{font-size:16px;margin:0 0 6px;display:flex;align-items:baseline;gap:10px}
.topbar h1 .sub{font-size:12px;font-weight:400;color:var(--muted)}
.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
#filter{flex:1;min-width:220px;padding:5px 9px;border:1px solid #d1d5db;border-radius:6px;font:inherit}
.legend{display:flex;gap:10px;flex-wrap:wrap;color:var(--muted);font-size:11px}
.legend .lg{display:inline-flex;align-items:center;gap:4px}
.legend .sw{width:10px;height:10px;border-radius:3px;display:inline-block}
.strip{display:flex;gap:3px;margin-top:8px}
.strip .seg{flex:1;height:8px;border-radius:3px;background:#e5e7eb;cursor:pointer;position:relative}
.strip .seg:hover{outline:2px solid #93c5fd}
.strip .seglbl{font-size:9px;color:var(--muted);text-align:center;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* project overview (pulled from _project.md, content before the status board) */
#overview{margin:2px 0 6px}
#overview>summary{cursor:pointer;font-weight:600;color:#374151;list-style:none;font-size:12px;display:inline-block}
#overview>summary::before{content:"▸ ";color:#9ca3af}
#overview[open]>summary::before{content:"▾ "}
.ov-body{max-width:1040px;max-height:48vh;overflow:auto;font-size:12.5px;color:#374151;
  border:1px solid var(--line);border-radius:6px;padding:4px 14px;margin-top:6px;background:#fff}
.ov-body h2{font-size:15px;margin:14px 0 6px;color:var(--ink)}
.ov-body h3{font-size:13px;margin:12px 0 5px;color:var(--ink)}
.ov-body h4{font-size:10.5px;margin:9px 0 3px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;font-weight:700}
.ov-body p{margin:6px 0}
.ov-body ul{margin:6px 0;padding-left:20px}
.ov-body table{border-collapse:collapse;margin:8px 0;font-size:12px}
.ov-body th,.ov-body td{border:1px solid var(--line);padding:4px 9px;text-align:left;vertical-align:top}
.ov-body th{background:#f8fafc}
.ov-body blockquote{border-left:3px solid #cbd5e1;margin:8px 0;padding:6px 12px;background:#f8fafc;color:#475569}
.ov-body code{background:#f1f5f9;padding:1px 4px;border-radius:3px;font-size:11.5px}
.ov-body pre{background:#0f172a;color:#e2e8f0;padding:9px 12px;border-radius:6px;overflow-x:auto;font-size:11.5px;margin:8px 0}
.ov-body pre code{background:none;color:inherit;padding:0;font-size:inherit}
.ov-body hr{border:none;border-top:1px solid var(--line);margin:10px 0}

.board{padding:8px 16px 60px;position:relative}
#edges{position:absolute;inset:0;pointer-events:none;z-index:40;overflow:visible}
#edges path{fill:none;stroke-width:2.2;opacity:.9}
#edges path.in{stroke:#2563eb} #edges path.out{stroke:#f59e0b}
.lane{display:flex;border-bottom:1px dashed var(--line);min-height:64px;scroll-margin-top:120px}
.lane.empty{opacity:.5}
.lane .gutter{flex:none;width:150px;padding:12px 10px 12px 0;border-right:2px solid var(--line)}
.lane .gutter .step{font-size:20px;font-weight:700;color:#9ca3af;line-height:1}
.lane .gutter .nm{font-weight:600;margin-top:2px}
.lane .gutter .prog{margin-top:6px;font-size:11px;color:var(--muted)}
.lane .gutter .bar{height:5px;border-radius:3px;background:#e5e7eb;margin-top:3px;overflow:hidden}
.lane .gutter .bar i{display:block;height:100%;background:var(--done)}
.lane .body{flex:1;display:flex;flex-wrap:wrap;gap:14px;padding:12px 4px 12px 14px;align-content:flex-start}
.lane.flash{animation:laneflash 1.3s ease-out}
@keyframes laneflash{from{background:#fef9c3}to{background:transparent}}

/* a stack wrapper holds the main card + its bug overlays */
.stack{position:relative;margin-top:14px;margin-bottom:6px}
.stack.nostack{margin-top:0}

/* ALL cards are the SAME fixed size & shape, for a uniform board */
.card{width:230px;height:124px;border:1px solid var(--line);border-radius:9px;background:#fff;
  box-shadow:0 1px 2px rgba(0,0,0,.05);cursor:pointer;overflow:hidden;position:relative;
  display:flex;flex-direction:column}
.card:hover{box-shadow:0 3px 10px rgba(0,0,0,.12)}
.card .strip4{height:4px;flex:none}
.card .pad{padding:8px 10px 8px;display:flex;flex-direction:column;flex:1;min-height:0}
.card .ttl{font-weight:650;font-size:12.5px;display:flex;gap:5px;align-items:flex-start;
  line-height:1.25;max-height:2.5em;overflow:hidden}
.card .ttl span:last-child{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card .ico{flex:none;font-size:11px;color:var(--muted)}
.card .sum{color:var(--muted);font-size:11px;margin-top:4px;flex:1;min-height:0;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card .itemref{font-size:9.5px;color:#9ca3af;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .foot{display:flex;align-items:center;gap:6px;margin-top:auto;padding-top:6px;flex-wrap:nowrap;overflow:hidden}
.chip{font-size:10px;border-radius:4px;padding:1px 6px;background:#f1f5f9;color:#475569;white-space:nowrap}
.chip.owner{background:#eef2ff;color:#4338ca}
.chip.unassigned{background:#f8fafc;color:#94a3b8;border:1px dashed #cbd5e1}
.chip.type{background:#f1f5f9;color:#64748b}
.chip.todo{background:var(--wip-bg);color:#92400e}   /* deferred-TODO count on the card face */
.badge{font-size:10px;font-weight:700}
.badge.pass{color:#15803d} .badge.fail{color:#b91c1c} .badge.partial{color:#a16207}
.dep{font-size:10px;color:#2563eb;cursor:pointer}
.dep:hover{text-decoration:underline}
/* bottom strip = verification + per-branch run health (one segment per dev branch) */
.card .vbar{height:6px;flex:none;display:flex;gap:1px;background:#fff}
.card .vbar .seg{flex:1;background:#cbd5e1}
.card .vbar .seg.more{flex:none;width:14px;background:#94a3b8;color:#fff;font-size:7px;font-weight:700;
  display:flex;align-items:center;justify-content:center;line-height:1;letter-spacing:-.5px}
.card .vbar.noscript{background:var(--blocked)}   /* solid red = no verification script (mis-configured) */
.lg .vbar-sw{display:inline-flex;gap:1px;width:18px;height:8px;border-radius:2px;overflow:hidden}
.lg .vbar-sw i{flex:1}

/* cluster = master-task container */
.cluster{border:1.5px solid #d1d5db;border-radius:11px;background:#fff;padding:0 0 8px;min-width:248px}
.cluster>.chead{display:flex;align-items:center;gap:6px;padding:7px 10px;border-bottom:1px dashed var(--line);
  border-radius:11px 11px 0 0;cursor:pointer}
.cluster>.chead .ctitle{font-weight:700;font-size:12.5px}
.cluster>.chead .cprog{font-size:10px;color:var(--muted);margin-left:auto}
.cluster>.cbody{display:flex;flex-wrap:wrap;gap:10px;padding:10px}
.cluster .strip4{height:4px;border-radius:11px 11px 0 0}

/* bug overlay = a FULL uniform card, offset & z-stacked around its parent */
.stack .card.layer{position:absolute;top:0;left:0}
.stack .stacktag{position:absolute;z-index:30;right:6px;font-size:9px;font-weight:700;
  padding:1px 5px;border-radius:8px;pointer-events:none}
.stacktag.open{top:-9px;background:var(--blocked);color:#fff}
.stacktag.resolved{bottom:-9px;background:var(--done);color:#fff}

/* step-stack expand toggle: click the chip to fan the steps into a column */
.stacktoggle{position:absolute;top:-11px;right:0;z-index:31;cursor:pointer;user-select:none;
  font-size:9px;font-weight:700;padding:1px 7px;border-radius:9px;background:#475569;color:#fff;
  box-shadow:0 0 0 1px #fff}
.stacktoggle:hover{background:#1e293b}
.stack.expanded{padding:0 !important}
.stack.expanded .card{position:static !important;top:auto !important;left:auto !important;
  z-index:auto !important;opacity:1 !important;margin:0 0 10px 0 !important}

.hidden{display:none !important}
.dim{opacity:.28}

/* drawer */
#scrim{position:fixed;inset:0;background:rgba(15,23,42,.35);z-index:90;display:none}
#scrim.on{display:block}
#drawer{position:fixed;top:0;right:0;height:100%;width:min(480px,92vw);background:#fff;z-index:100;
  box-shadow:-4px 0 22px rgba(0,0,0,.2);transform:translateX(100%);transition:transform .18s ease;
  display:flex;flex-direction:column}
#drawer.on{transform:translateX(0)}
#drawer .dhead{padding:14px 16px;border-bottom:1px solid var(--line)}
#drawer .dhead .x{float:right;cursor:pointer;color:var(--muted);font-size:20px;line-height:1}
#drawer .dhead h2{font-size:15px;margin:0 26px 6px 0}
#drawer .dhead .copylink{display:inline-flex;align-items:center;gap:4px;cursor:pointer;margin-top:6px;
  font-size:11px;border:1px solid var(--line);border-radius:6px;padding:3px 8px;background:#f8fafc;color:#475569}
#drawer .dhead .copylink:hover{background:#eef2ff;color:#4338ca;border-color:#c7d2fe}
#drawer .dhead .copylink.copied{background:var(--done);color:#fff;border-color:var(--done)}
#drawer .dhead a.copylink{text-decoration:none}
#drawer .dhead .dlinks{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:6px}
#drawer .dhead .dlinks .copylink{margin-top:0}
#drawer .meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
#drawer .dbody{padding:14px 16px;overflow:auto}
#drawer h3{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:16px 0 6px}
#drawer pre{background:#f8fafc;border:1px solid var(--line);border-radius:6px;padding:8px;white-space:pre-wrap;
  word-break:break-word;font:11.5px/1.5 ui-monospace,Menlo,Consolas,monospace;margin:0}
#drawer .kv{font-size:12px;margin:2px 0}
#drawer .body-md{font-size:12.5px;color:#374151;white-space:pre-wrap}
#drawer .redtext{color:#dc2626;font-weight:600}
/* inline owner assign control (the one editable field — writes back via the edit sidecar) */
#drawer .ownerctl{display:flex;align-items:center;gap:8px;margin:4px 0 2px}
#drawer #owner-select{font:inherit;padding:3px 7px;border:1px solid #d1d5db;border-radius:6px;background:#fff;cursor:pointer}
#drawer .owner-status{font-size:11px;color:var(--muted)}
#drawer .owner-status.ok{color:#15803d}
#drawer .owner-status.err{color:#b91c1c}
/* deferred-TODO callout: amber box (planned work, not an error), drawn right after the
   verification-script section so it reads as a peer of it. .done flips it green. */
#drawer .todoitem{font-size:12px;margin:6px 0;padding:7px 10px;border-radius:6px;
  background:var(--wip-bg);border-left:3px solid var(--wip);color:#92400e}
#drawer .todoitem.done{background:var(--done-bg);border-left-color:var(--done);color:#166534}
#drawer .todoitem .todowhy{color:#78716c;font-weight:400}
#drawer .todoitem code{background:#fef3c7}
#drawer code{background:#f1f5f9;padding:1px 4px;border-radius:3px;font-size:11px}
#drawer .body-md details.codefold{margin:8px 0;border:1px solid var(--line);border-radius:6px;background:#f8fafc;white-space:normal}
#drawer .body-md details.codefold>summary{cursor:pointer;padding:6px 10px;font:600 11.5px ui-monospace,Menlo,Consolas,monospace;color:#334155;list-style:none;user-select:none}
#drawer .body-md details.codefold>summary::-webkit-details-marker{display:none}
#drawer .body-md details.codefold>summary::before{content:"\\25B6  ";color:var(--muted);font-size:10px}
#drawer .body-md details.codefold[open]>summary::before{content:"\\25BC  "}
#drawer .body-md details.codefold>pre{margin:0;border:none;border-top:1px solid var(--line);border-radius:0 0 6px 6px;max-height:360px;overflow:auto}
.pill{display:inline-block;font-size:10px;font-weight:700;color:#fff;border-radius:10px;padding:1px 9px}

/* meeting-notes button (by "Project overview") + LEFT drawer (non-modal; coexists w/ card drawer) */
.topline{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.notesbtn{font:inherit;font-size:12px;cursor:pointer;border:1px solid #c7d2fe;background:#eef2ff;
  color:#4338ca;border-radius:6px;padding:4px 10px;white-space:nowrap}
.notesbtn:hover{background:#e0e7ff}
.notesbtn.on{background:#4338ca;color:#fff;border-color:#4338ca}
#notesdrawer{position:fixed;top:0;left:0;height:100%;width:min(920px,88vw);background:#fff;z-index:95;
  box-shadow:4px 0 22px rgba(0,0,0,.2);transform:translateX(-100%);transition:transform .18s ease;
  display:flex;flex-direction:column}
#notesdrawer.on{transform:translateX(0)}
#notesdrawer .ndhead{padding:12px 16px;border-bottom:1px solid var(--line)}
#notesdrawer .ndhead .x{float:right;cursor:pointer;color:var(--muted);font-size:20px;line-height:1}
#notesdrawer .ndhead h2{font-size:15px;margin:0 26px 8px 0}
#notesdrawer .ndtabs{display:flex;align-items:center;gap:6px}
#notesdrawer .ndtabs button{font:inherit;font-size:12px;cursor:pointer;border:1px solid var(--line);
  background:#f8fafc;color:#475569;border-radius:6px;padding:3px 12px}
#notesdrawer .ndtabs button.active{background:#4338ca;color:#fff;border-color:#4338ca}
#notesdrawer .ndtabs a.nd-share{font:inherit;font-size:12px;cursor:pointer;border:1px solid #c7d2fe;
  background:#eef2ff;color:#4338ca;border-radius:6px;padding:3px 10px;text-decoration:none;white-space:nowrap}
#notesdrawer .ndtabs a.nd-share:hover{background:#e0e7ff;text-decoration:none}
#notesdrawer .nd-status{margin-left:auto;font-size:11px;color:var(--muted)}
#notesdrawer .nd-status.ok{color:#15803d}
#notesdrawer .nd-status.err{color:#b91c1c}
#notesdrawer .ndbody{flex:1;min-height:0;display:flex;flex-direction:column}
#notesdrawer textarea{flex:1;width:100%;border:none;outline:none;resize:none;padding:14px 16px;
  font:12.5px/1.6 ui-monospace,Menlo,Consolas,monospace;color:#111827;background:#fff}
/* preview reuses the overview markdown child styles (.ov-body h2/ul/table/…) but drops its box */
#notesdrawer .note-md{flex:1;overflow:auto;max-width:none;max-height:none;border:none;border-radius:0;
  margin:0;padding:6px 16px 16px;background:#fff}
#notesdrawer.mode-preview textarea{display:none}
#notesdrawer.mode-edit .note-md{display:none}
</style>
</head>
<body>
<div class="topbar">
  <h1>__TITLE__ <span class="sub">milestone board · independent view · generated __GENERATED__</span></h1>
  <div class="topline"><details id="overview"><summary>Project overview</summary><div class="ov-body">__GLOBALS__</div></details><button id="notesbtn" class="notesbtn" onclick="toggleNotes()" title="Open the live meeting notes (editable, shared)">📝 Meeting notes</button></div>
  <div class="controls">
    <input id="filter" placeholder="filter: text · status:blocked · type:bug · @frankc · #sparse · result:fail">
    <div class="legend" id="legend"></div>
  </div>
  <div class="strip" id="strip"></div>
  <div class="strip" id="striplbl" style="margin-top:0"></div>
</div>
<div class="board" id="board"></div>

<div id="scrim" onclick="closeDrawer()"></div>
<div id="drawer">
  <div class="dhead"><span class="x" onclick="closeDrawer()">×</span><h2 id="d-title"></h2><div class="meta" id="d-meta"></div><div class="dlinks"><span class="copylink" id="d-copylink" onclick="copyCardLink()"><span>🔗</span><span id="d-copylink-label">Copy link</span></span><a class="copylink" id="d-opensrc" target="_blank"><span>📄</span><span>open .md</span></a><span class="copylink" id="d-copypath" onclick="copyCardPath()"><span>📋</span><span id="d-copypath-label">Copy md path</span></span></div></div>
  <div class="dbody" id="d-body"></div>
</div>

<div id="notesdrawer" class="mode-preview">
  <div class="ndhead">
    <span class="x" onclick="closeNotes()">×</span>
    <h2>📝 Meeting notes</h2>
    <div class="ndtabs">
      <button id="nd-edit-tab" onclick="setNotesMode('edit')">Edit</button>
      <button id="nd-prev-tab" class="active" onclick="setNotesMode('preview')">Preview</button>
      <a id="nd-share" class="nd-share" href="_meeting.md" target="_blank" onclick="return copyNoteLink(event)" title="Copy a shareable link to these meeting notes (rendered by markserv)">🔗 Copy link</a>
      <span id="nd-status" class="nd-status"></span>
    </div>
  </div>
  <div class="ndbody">
    <textarea id="nd-textarea" spellcheck="false" oninput="onNoteInput()" placeholder="Type meeting notes in markdown… (shared, live)"></textarea>
    <div id="nd-preview" class="ov-body note-md"></div>
  </div>
</div>

<script>
const CARDS = __PAYLOAD__;
const MILESTONES = __MILESTONES__;
const CARDS_DIR = "__CARDS_DIR__";
const CARDS_ABS = "__CARDS_ABS__";   // absolute filesystem path of the cards/ dir (for "copy md path")
const PR_URL_BASE = "__PR_URL_BASE__";
const PROJECT = "__PROJECT__";          // project name (= dir under the projects root) for the edit sidecar
const EDIT_PORT = "__EDIT_PORT__";      // tracker-edit sidecar port (beside markserv); see scripts/serve_edit.py
// edit endpoint = same host as the served board, sidecar port. Empty when opened via file:// (no live edit).
const EDIT_BASE = location.hostname ? (location.protocol+"//"+location.hostname+":"+EDIT_PORT) : "";

const STATUS_LABELS = ["todo","ready","in_progress","blocked","done","dropped"];
const COLORVAR = {todo:"--todo",ready:"--ready",in_progress:"--wip",blocked:"--blocked",done:"--done",dropped:"--dropped"};
const BGVAR = {todo:"--todo-bg",ready:"--ready-bg",in_progress:"--wip-bg",blocked:"--blocked-bg",done:"--done-bg",dropped:"--dropped-bg"};
const ICON = {"master-task":"▣",task:"▭",bug:"◆",milestone:"⬣",decision:"◈",research:"◌",infra:"▮"};

const byId = {}; CARDS.forEach(c=>byId[c.id]=c);
const children = {}; CARDS.forEach(c=>{ if(c.parent&&byId[c.parent]) (children[c.parent]=children[c.parent]||[]).push(c); });
const blocks = {}; CARDS.forEach(c=>c.depends_on.forEach(d=>{ (blocks[d]=blocks[d]||[]).push(c.id); }));
// distinct known owners (for the assign dropdown); empty owner = Unassigned, not listed here.
const OWNERS = [...new Set(CARDS.map(c=>c.owner).filter(Boolean))].sort();
// sort within a group by `order` (ascending), then created, then id — matches embed.js.
const byOrder=(a,b)=>{const oa=a.order==null?1e9:a.order, ob=b.order==null?1e9:b.order;
  if(oa!==ob) return oa-ob; return (a.created||"").localeCompare(b.created||"")||a.id.localeCompare(b.id);};
Object.keys(children).forEach(k=>children[k].sort(byOrder));
const cssvar = n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
// card links are authored relative to cards/<id>.md, but this page sits at the project
// root. Rebase relative links onto CARDS_DIR; the browser normalizes any ../ itself.
function rebase(url){ if(!url) return url; if(/^[a-z]+:/i.test(url)||url.startsWith("/")||url.startsWith("#")) return url; return (CARDS_DIR?CARDS_DIR+"/":"")+url; }

// inline formatting shared by body prose + pass_criteria: escape, then [[card]] + [text](url)
// links, !!red!! emphasis, `code`, **bold**. (Order: links before code/bold so URLs stay intact.)
function fmtInline(s){
  return esc(s)
    .replace(/\[\[([a-z0-9-]+)\]\]/g,(m,id)=>byId[id]?`<a onclick="openDrawer('${id}')">${id}</a>`:m)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g,(m,txt,url)=>`<a href="${rebase(url)}" target="_blank">${txt}</a>`)
    .replace(/!!([^!]+)!!/g,(m,t)=>`<span class="redtext">${t}</span>`)
    .replace(/`([^`]+)`/g,(m,t)=>`<code>${t}</code>`)
    .replace(/\*\*([^*]+)\*\*/g,(m,t)=>`<strong>${t}</strong>`);
}
// body: fold fenced code blocks ```lang [title]\n...\n``` into DEFAULT-COLLAPSED <details>
// (summary = the title after the language token, e.g. a filename); prose between fences is
// formatted with fmtInline. Plain text keeps pre-wrap via the .body-md container.
function renderBody(raw){
  const re=/```([^\n]*)\n([\s\S]*?)```/g;
  let out="", last=0, m;
  while((m=re.exec(raw))){
    out+=fmtInline(raw.slice(last,m.index).replace(/\n+$/,""));
    const info=m[1].trim(), sp=info.indexOf(" ");
    const title=(sp>=0?info.slice(sp+1):(info||"code")).trim();
    out+=`<details class="codefold"><summary>${esc(title)}</summary><pre><code>${esc(m[2].replace(/\n$/,""))}</code></pre></details>`;
    last=re.lastIndex;
  }
  out+=fmtInline(raw.slice(last).replace(/^\n+/,""));
  return out;
}

function normalKids(c){return (children[c.id]||[]).filter(k=>k.type!=="bug");}
function bugKids(c){return (children[c.id]||[]).filter(k=>k.type==="bug");}
function isDone(c){return c.status==="done"||c.status==="dropped";}

function rollup(ids){
  // count WORK ITEMS only; master-task containers are grouping, not units of work
  const cs = ids.map(i=>byId[i]).filter(Boolean).filter(c=>c.type!=="master-task");
  if(!cs.length) return {done:0,total:0,color:"--todo"};
  const done = cs.filter(isDone).length;
  let color="--done";
  if(cs.some(c=>c.status==="blocked")) color="--blocked";
  else if(cs.some(c=>c.status==="in_progress"||c.status==="ready")) color="--wip";
  else if(done<cs.length) color="--todo";
  return {done,total:cs.length,color};
}
// every descendant id (for cluster rollups)
function descendants(id){let out=[];(children[id]||[]).forEach(k=>{out.push(k.id);out=out.concat(descendants(k.id));});return out;}

// bottom strip: verification + per-branch run health (one segment per dev branch, latest 3)
function vbarFor(c){
  if(!c.needs_verification) return "";
  if(!c.has_verification){
    return `<div class="vbar noscript" title="No verification script — card is mis-configured (cannot be verified or closed)"></div>`;
  }
  const RES={pass:"--done",fail:"--blocked",partial:"--wip"};
  const all=(c.branch_runs&&c.branch_runs.length)?c.branch_runs:[{branch:"",result:"",when:""}];
  const hidden = all.length>3 ? all.length-3 : 0;     // show at most the latest 3 branches
  const shown = hidden ? all.slice(-3) : all;
  const more = hidden ? `<span class="seg more" title="${esc("+"+hidden+" older branch result"+(hidden>1?"s":"")+" hidden")}">+${hidden}</span>` : "";
  return `<div class="vbar">`+more+shown.map(s=>{
    const col2 = (s.result&&RES[s.result]) ? cssvar(RES[s.result]) : "#cbd5e1";
    const tip = (s.branch&&s.branch!=="—"?s.branch:"(no branch)")+": "+(s.result||"not run yet")+(s.when?" ("+s.when+")":"");
    return `<span class="seg" style="background:${col2}" title="${esc(tip)}"></span>`;
  }).join("")+`</div>`;
}

// a step card = one entry in a card's steps[] (the stack-of-steps model). One item = one md;
// its whole journey (plan -> compile -> integrate -> debug) lives there, each step a card.
function stepCard(item, step, idx, total, isTop){
  const el=document.createElement("div");
  el.className="card stepcard"; el.dataset.id=item.id;
  const st=step.status||"todo";
  el.style.background=cssvar(BGVAR[st]||"--todo-bg");
  const col=cssvar(COLORVAR[st]||"--todo");
  const isDebug=(step.kind==="debug");
  const icon=isDebug?ICON["bug"]:(ICON[item.type]||"▭");
  let foot=`<span class="chip type">step ${idx+1}/${total}</span>`;
  if(isDebug) foot+=`<span class="chip" style="background:#fef2f2;color:#b91c1c">debug</span>`;
  el.innerHTML=
    `<div class="strip4" style="background:${col}"></div>`+
    `<div class="pad">`+
      `<div class="ttl"><span class="ico">${icon}</span><span>${esc(item.title)}</span></div>`+
      `<div class="itemref">${esc(step.name||item.title)}</div>`+
      (step.summary?`<div class="sum">${esc(step.summary)}</div>`:"")+
      `<div class="foot">${foot}</div>`+
    `</div>`+(isTop?vbarFor(item):"");
  return el;
}

// render an item with steps[] as a STACK: earlier (done) steps tuck behind+below, the
// current (last) step sits on top. A single-step item renders as one plain card.
function renderStepStack(c){
  const steps=c.steps, n=steps.length;
  if(n===1) return stepCard(c, steps[0], 0, 1, true);
  const off=9;
  const stack=document.createElement("div");
  stack.className="stack";
  stack.style.paddingBottom=((n-1)*off)+"px";
  stack.style.paddingRight=((n-1)*6)+"px";
  steps.forEach((s,i)=>{
    const isTop=(i===n-1);
    const el=stepCard(c,s,i,n,isTop);
    if(isTop){ el.style.position="relative"; el.style.zIndex=20; }
    else { el.classList.add("layer","dim"); el.style.zIndex=1+i; el.style.top=((i+1)*off)+"px"; el.style.left=((i+1)*6)+"px"; }
    stack.appendChild(el);
  });
  const tog=document.createElement("div");
  tog.className="stacktoggle"; tog.dataset.n=n; tog.textContent="⤢ "+n+" steps";
  stack.appendChild(tog);
  return stack;
}

// a stack of SEPARATE sibling cards sharing a `stack:` key — each is a FULL card (own bottom strip).
// current/last (by order) on top; earlier cards tuck behind, dim. Visual mirror of renderStepStack,
// but the layers are independent cards (independent validation) rather than steps of one file.
function renderCardStack(cards){
  const n=cards.length;
  if(n===1) return renderNode(cards[0]);
  const off=9;
  const stack=document.createElement("div");
  stack.className="stack";
  stack.style.paddingBottom=((n-1)*off)+"px";
  stack.style.paddingRight=((n-1)*6)+"px";
  cards.forEach((c,i)=>{
    const isTop=(i===n-1);
    const el=cardFace(c);
    if(isTop){ el.style.position="relative"; el.style.zIndex=20; }
    else { el.classList.add("layer","dim"); el.style.zIndex=1+i; el.style.top=((i+1)*off)+"px"; el.style.left=((i+1)*6)+"px"; }
    stack.appendChild(el);
  });
  const tog=document.createElement("div");
  tog.className="stacktoggle"; tog.dataset.n=n; tog.dataset.noun="cards"; tog.textContent="⤢ "+n+" cards";
  stack.appendChild(tog);
  return stack;
}

// render a list of sibling cards into `into`, collapsing any that share a `stack:` key into ONE
// card-stack (rendered at the position of the group's first member). Non-stacked cards render normally.
function renderSiblings(cards, into){
  const done={};
  cards.forEach(c=>{
    if(c.stack){
      if(done[c.stack]) return;
      done[c.stack]=1;
      const grp=cards.filter(x=>x.stack===c.stack).slice().sort(byOrder);
      into.appendChild(grp.length>1 ? renderCardStack(grp) : renderNode(grp[0]));
    } else {
      into.appendChild(renderNode(c));
    }
  });
}

// owner chip: assigned -> @name (indigo); unassigned -> dashed grey "⊘ unassigned" (a real,
// claimable state, visually distinct from "forgot to set"). Class .ownerchip so a live assign
// can swap it in place without a full rebuild.
function ownerChip(c){
  return c.owner
    ? `<span class="chip owner ownerchip">@${esc(c.owner)}</span>`
    : `<span class="chip unassigned ownerchip" title="Unassigned — open the card to assign an owner">⊘ unassigned</span>`;
}
// dropdown options for the drawer's assign control: Unassigned + known owners (+ current value if
// it's a one-off not already in the list) + an "Other…" free-text escape hatch.
function ownerOptions(c){
  const cur=c.owner||"";
  const list=OWNERS.slice();
  if(cur && list.indexOf(cur)<0) list.push(cur);
  list.sort();
  const opts=[`<option value=""${cur===""?" selected":""}>⊘ Unassigned</option>`];
  list.forEach(o=>opts.push(`<option value="${esc(o)}"${o===cur?" selected":""}>${esc(o)}</option>`));
  opts.push(`<option value="__other__">＋ Other…</option>`);
  return opts.join("");
}
function metaHTML(c){
  const col=cssvar(COLORVAR[c.status]||"--todo");
  return [`<span class="pill" style="background:${col}">${esc(c.status)}</span>`,
    `<span class="chip type">${esc(c.type)}</span>`,
    c.type!=="master-task"?ownerChip(c):"",   // master-tasks roll up — no owner concept
    c.milestone!=null?`<span class="chip">step ${c.milestone}</span>`:`<span class="chip">unscheduled</span>`].join("");
}
// assign flow: dropdown change -> (maybe prompt for free text) -> POST to the edit sidecar ->
// on success update in-memory + the face chip + drawer meta (no full rebuild).
function assignOwner(id, val){
  const sel=document.getElementById("owner-select");
  if(val==="__other__"){
    const t=prompt("Owner (free text). Leave blank for Unassigned:", "");
    if(t===null){ if(sel) sel.value=(byId[id].owner||""); return; }   // cancelled
    val=t.trim();
  }
  postAssign(id, val);
}
function postAssign(id, owner){
  const st=document.getElementById("owner-status");
  const sel=document.getElementById("owner-select");
  if(!EDIT_BASE){ if(st){st.textContent="⚠ editing only works on the served board (not file://)";st.className="owner-status err";} return; }
  if(st){ st.textContent="saving…"; st.className="owner-status"; }
  fetch(EDIT_BASE+"/assign",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({project:PROJECT,id:id,owner:owner})})
    .then(r=>r.json().then(j=>({ok:r.ok,j})))
    .then(({ok,j})=>{
      if(!ok||!j||!j.ok) throw new Error((j&&j.error)||"save failed");
      byId[id].owner=j.owner||"";
      if(byId[id].owner && OWNERS.indexOf(byId[id].owner)<0){ OWNERS.push(byId[id].owner); OWNERS.sort(); }
      refreshOwnerUI(id);
      if(pinned===id) refreshDrawerMeta(byId[id]);
      if(st){ st.textContent=byId[id].owner?("✓ assigned to "+byId[id].owner):"✓ unassigned"; st.className="owner-status ok"; }
    })
    .catch(e=>{ if(st){st.textContent="⚠ "+e.message;st.className="owner-status err";} if(sel) sel.value=(byId[id].owner||""); });
}
function refreshOwnerUI(id){
  const c=byId[id];
  document.querySelectorAll(`.card[data-id="${CSS.escape(id)}"] .ownerchip`).forEach(el=>{ el.outerHTML=ownerChip(c); });
}
function refreshDrawerMeta(c){ const m=document.getElementById("d-meta"); if(m) m.innerHTML=metaHTML(c); }

function cardFace(c){
  const el=document.createElement("div");
  el.className="card"; el.dataset.id=c.id;
  el.style.background=cssvar(BGVAR[c.status]||"--todo-bg");
  const col=cssvar(COLORVAR[c.status]||"--todo");
  let foot=ownerChip(c);
  foot+=`<span class="chip type">${esc(c.type)}</span>`;
  const opentodo=(c.todos||[]).filter(t=>String(t.done||"").toLowerCase()!=="true").length;
  if(opentodo) foot+=`<span class="chip todo" title="${esc(opentodo+" deferred TODO"+(opentodo>1?"s":"")+" — open the card to read")}">⏳ ${opentodo}</span>`;
  if(c.result==="pass") foot+=`<span class="badge pass">✓</span>`;
  else if(c.result==="fail") foot+=`<span class="badge fail">✗</span>`;
  else if(c.result==="partial") foot+=`<span class="badge partial">~</span>`;
  if(c.depends_on.length){
    foot+=`<span class="chip" style="background:#fff;border:1px solid var(--line)">needs:</span>`;
    foot+=c.depends_on.map(d=>`<span class="dep" data-dep="${esc(d)}">${esc(d.replace(/^m3-/,''))}</span>`).join(" ");
  }
  const vbar=vbarFor(c);
  el.innerHTML=
    `<div class="strip4" style="background:${col}"></div>`+
    `<div class="pad"><div class="ttl"><span class="ico">${ICON[c.type]||"▭"}</span><span>${esc(c.title)}</span></div>`+
    (c.summary?`<div class="sum">${esc(c.summary)}</div>`:"")+
    `<div class="foot">${foot}</div></div>`+vbar;
  return el;
}

function clusterEl(c){
  const wrap=document.createElement("div");
  wrap.className="cluster"; wrap.dataset.id=c.id;
  const desc=descendants(c.id);
  const ru=rollup(desc);
  const col=cssvar(COLORVAR[c.status]||"--todo");
  const head=document.createElement("div");
  head.className="chead";
  head.innerHTML=`<span class="ico">${ICON["master-task"]}</span><span class="ctitle">${esc(c.title)}</span>`+
    `<span class="cprog">${ru.done}/${ru.total} done</span>`;
  const strip=document.createElement("div"); strip.className="strip4"; strip.style.background=col;
  const body=document.createElement("div"); body.className="cbody";
  renderSiblings(normalKids(c), body);
  head.addEventListener("click",e=>{e.stopPropagation();openDrawer(c.id);});
  wrap.appendChild(strip); wrap.appendChild(head); wrap.appendChild(body);
  return wrap;
}

// a node = the card/cluster + its bug cards stacked (uniform full cards) around it.
// resolved bugs tuck BEHIND (offset down-right, dim); open/blocked bugs overlay ON TOP (red).
function renderNode(c){
  // steps-as-stack model: an item with steps[] renders as its own step stack (one md, many steps)
  if(c.type!=="master-task" && c.steps && c.steps.length){ return renderStepStack(c); }
  const bugs=bugKids(c);
  const main = c.type==="master-task" ? clusterEl(c) : cardFace(c);
  if(!bugs.length){ return main; }   // no stack wrapper when nothing to stack -> stays uniform

  const open=bugs.filter(b=>!isDone(b));
  const resolved=bugs.filter(b=>isDone(b));
  const stack=document.createElement("div");
  stack.className="stack";
  // padding so the top/bottom offset layers stay inside the lane flow
  const padTop=open.length?(16+(open.length-1)*7):0;
  const padBot=resolved.length?(16+(resolved.length-1)*7):0;
  stack.style.paddingTop=padTop+"px"; stack.style.paddingBottom=padBot+"px";

  // resolved behind (low z, down-right, dim)
  resolved.forEach((b,i)=>{
    const L=cardFace(b); L.classList.add("layer","dim");
    L.style.zIndex=1+i; L.style.top=(padTop+10+i*7)+"px"; L.style.left=(12+i*7)+"px";
    stack.appendChild(L);
    stack.insertAdjacentHTML("beforeend",`<span class="stacktag resolved">✓ fixed</span>`);
  });
  main.style.position="relative"; main.style.zIndex=5; main.style.marginTop=padTop+"px";
  stack.appendChild(main);
  // open on top (high z, up-left, red status colour already on the card)
  open.forEach((b,i)=>{
    const L=cardFace(b); L.classList.add("layer");
    L.style.zIndex=10+i; L.style.top=(padTop-12-i*7)+"px"; L.style.left=(-6-i*7)+"px";
    stack.appendChild(L);
  });
  if(open.length) stack.insertAdjacentHTML("beforeend",`<span class="stacktag open">⚠ blocker</span>`);
  return stack;
}

function buildBoard(){
  const board=document.getElementById("board");
  const placed={}; // ids placed inside a cluster -> not a lane root
  CARDS.forEach(c=>{ if(c.type==="master-task") (children[c.id]||[]).forEach(k=>placed[k.id]=1); });

  const lanes=MILESTONES.slice();
  if(CARDS.some(c=>c.milestone==null)) lanes.push([null,"Unscheduled"]);
  lanes.forEach(([num,name])=>{
    const inLane=CARDS.filter(c=>c.milestone===num);
    // roots in this lane = not nested under an in-lane master-task
    const roots=inLane.filter(c=>!placed[c.id] || !(c.parent&&byId[c.parent]&&byId[c.parent].milestone===num));
    roots.sort(byOrder);
    const lane=document.createElement("div");
    lane.className="lane"+(inLane.length?"":" empty");
    lane.id="lane-"+num;
    const ru=rollup(inLane.map(c=>c.id));
    const pct=ru.total?Math.round(100*ru.done/ru.total):0;
    lane.innerHTML=`<div class="gutter"><div class="step">${num==null?"·":num}</div><div class="nm">${esc(name)}</div>`+
      (inLane.length?`<div class="prog">${ru.done}/${ru.total} done</div><div class="bar"><i style="width:${pct}%"></i></div>`
                    :`<div class="prog">— roadmap —</div>`)+`</div>`;
    const body=document.createElement("div"); body.className="body";
    renderSiblings(roots, body);
    lane.appendChild(body);
    board.appendChild(lane);
  });
  // edge overlay (tier-3: arrows only for the focused card)
  const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
  svg.id="edges";
  svg.innerHTML='<defs>'+
    '<marker id="ah-in" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="#2563eb"/></marker>'+
    '<marker id="ah-out" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="#f59e0b"/></marker>'+
    '</defs>';
  board.appendChild(svg);
  wireClicks();
}

let pinned=null;
const NS="http://www.w3.org/2000/svg";
function elFor(id){return document.querySelector(`[data-id="${CSS.escape(id)}"]`);}
function rectIn(board,el){const b=board.getBoundingClientRect(),r=el.getBoundingClientRect();
  return {cx:(r.left+r.right)/2-b.left, top:r.top-b.top, bot:r.bottom-b.top};}
function edge(svg,a,b,cls){
  const dy=Math.max(28,(b.top-a.bot)/2);
  const p=document.createElementNS(NS,"path");
  p.setAttribute("d",`M${a.cx},${a.bot} C${a.cx},${a.bot+dy} ${b.cx},${b.top-dy} ${b.cx},${b.top}`);
  p.setAttribute("class",cls); p.setAttribute("marker-end",cls==="in"?"url(#ah-in)":"url(#ah-out)");
  svg.appendChild(p);
}
function drawEdges(id){
  const board=document.getElementById("board"), svg=document.getElementById("edges");
  while(svg.childNodes.length>1) svg.removeChild(svg.lastChild); // keep <defs>
  svg.setAttribute("width",board.scrollWidth); svg.setAttribute("height",board.scrollHeight);
  const tgt=elFor(id); if(!tgt) return; const c=byId[id]; if(!c) return;
  const T=rectIn(board,tgt);
  c.depends_on.forEach(d=>{const s=elFor(d); if(s) edge(svg,rectIn(board,s),T,"in");});      // dep -> this
  (blocks[id]||[]).forEach(b=>{const e=elFor(b); if(e) edge(svg,T,rectIn(board,e),"out");});  // this -> dependent
}
function clearEdges(){const svg=document.getElementById("edges"); if(svg) while(svg.childNodes.length>1) svg.removeChild(svg.lastChild);}
window.addEventListener("resize",()=>{if(pinned)drawEdges(pinned);});
window.addEventListener("scroll",()=>{if(pinned)drawEdges(pinned);},true);

function nodeIdAt(t){const el=t.closest("[data-id]"); return el?el.dataset.id:null;}
function wireClicks(){
  const board=document.getElementById("board");
  board.addEventListener("click",e=>{
    const tog=e.target.closest(".stacktoggle");
    if(tog){ e.stopPropagation(); const stk=tog.closest(".stack");
      const ex=stk.classList.toggle("expanded");
      tog.textContent = ex ? "⤡ collapse" : ("⤢ "+tog.dataset.n+" "+(tog.dataset.noun||"steps")); return; }
    const dep=e.target.closest(".dep");
    if(dep){ e.stopPropagation(); flashCard(dep.dataset.dep); return; }
    const id=nodeIdAt(e.target);
    if(id) openDrawer(id);
  });
  // tier-3 arrows: show on hover, unless a card is pinned (drawer open)
  board.addEventListener("mouseover",e=>{ if(pinned) return; const id=nodeIdAt(e.target); if(id) drawEdges(id); });
  board.addEventListener("mouseout",e=>{ if(pinned) return; if(!e.relatedTarget||!e.relatedTarget.closest("[data-id]")) clearEdges(); });
}

function flashCard(id){
  const el=document.querySelector(`[data-id="${CSS.escape(id)}"]`);
  if(!el) return;
  el.scrollIntoView({block:"center",behavior:"smooth"});
  el.style.transition="box-shadow .1s"; el.style.boxShadow="0 0 0 3px #fbbf24";
  setTimeout(()=>{el.style.boxShadow="";},1100);
}

function openDrawer(id){
  const c=byId[id]; if(!c) return;
  document.getElementById("d-title").textContent=c.title;
  document.getElementById("d-meta").innerHTML=metaHTML(c);
  let h="";
  if(c.summary) h+=`<div class="kv">${esc(c.summary)}</div>`;
  h+=`<h3>identity</h3><div class="kv"><b>id</b> ${esc(c.id)}`;
  if(c.parent) h+=` · <b>parent</b> <a onclick="openDrawer('${esc(c.parent)}')">${esc(c.parent)}</a>`;
  if(c.updated) h+=` · <b>updated</b> ${esc(c.updated)}`+(c.updated_by?` by ${esc(c.updated_by)}`:"");
  h+=`</div>`;
  // owner assign — the one editable field. Writes back to the .md via the edit sidecar.
  if(c.type!=="master-task"){
    h+=`<h3>owner</h3><div class="ownerctl">`+
       `<select id="owner-select" onchange="assignOwner('${esc(c.id)}', this.value)">${ownerOptions(c)}</select>`+
       `<span id="owner-status" class="owner-status"></span></div>`;
  }
  if(c.steps&&c.steps.length){
    h+=`<h3>steps</h3>`+c.steps.map((s,i)=>{
      const st=s.status||"";
      const ic = st==="done"?"✓":st==="blocked"?"⛔":st==="in_progress"?"▸":st==="dropped"?"✗":"○";
      const dbg = s.kind==="debug"?` <span style="color:#b91c1c;font-weight:700">[debug]</span>`:"";
      return `<div class="kv">${ic} <b>${esc(s.name||("step "+(i+1)))}</b>${dbg}${st?" — "+esc(st):""}${s.summary?": "+esc(s.summary):""}</div>`;
    }).join("");
  }
  if(c.depends_on.length){
    h+=`<h3>depends on</h3>`+c.depends_on.map(d=>{
      const dc=byId[d]; const ok=dc&&isDone(dc);
      return `<div class="kv">${ok?"✓":"○"} <a onclick="openDrawer('${esc(d)}')">${esc(d)}</a>${dc?` — ${esc(dc.status)}`:""}</div>`;
    }).join("");
  }
  if(blocks[c.id]&&blocks[c.id].length){
    h+=`<h3>unblocks</h3>`+blocks[c.id].map(d=>`<div class="kv">→ <a onclick="openDrawer('${esc(d)}')">${esc(d)}</a></div>`).join("");
  }
  const bugs=bugKids(c);
  if(bugs.length){
    h+=`<h3>debug / bug cards</h3>`+bugs.map(b=>`<div class="kv">${isDone(b)?"✓":"⚠"} <a onclick="openDrawer('${esc(b.id)}')">${esc(b.title)}</a> — ${esc(b.status)}</div>`).join("");
  }
  if(c.needs_verification){
    h+=`<h3>verification script</h3>`;
    if(c.has_verification){
      const v=c.validation||{};
      h+=`<pre>${esc(v.cmd)}</pre>`;
      if(v.branch) h+=`<div class="kv" style="margin-top:6px"><b>branch</b> <code>${esc(v.branch)}</code></div>`;
      if(v.pass_criteria) h+=`<div class="kv"><b>pass</b> ${fmtInline(v.pass_criteria)}</div>`;
    } else {
      const closed=(c.status==="done"||c.status==="dropped");
      h+=`<div class="kv" style="color:#b91c1c"><b>⚠ Verification Script MISSING.</b> `+
         (closed ? `This card is marked <b>${esc(c.status)}</b> without a reproducible check — it cannot be credibly closed until a runnable validation script is added.`
                 : `Required before this card can be closed, and re-run on each new dev branch to detect regressions.`)+
         `</div>`;
    }
  }
  if(c.todos&&c.todos.length){
    h+=`<h3>todo · deferred</h3>`;
    h+=c.todos.map(t=>{
      const done=String(t.done||"").toLowerCase()==="true";
      const why=t.why?` <span class="todowhy">— ${fmtInline(t.why)}</span>`:"";
      return `<div class="todoitem${done?" done":""}">${done?"✓":"⏳"} <b>${fmtInline(t.text||"")}</b>${why}</div>`;
    }).join("");
  }
  if(c.branch_runs&&c.branch_runs.length){
    h+=`<h3>branch health</h3>`+c.branch_runs.map(s=>{
      const ic = s.result==="pass"?"✓":s.result==="fail"?"✗":s.result==="partial"?"~":"·";
      return `<div class="kv">${ic} <code>${esc(s.branch&&s.branch!=="—"?s.branch:"(no branch)")}</code> — ${esc(s.result||"not run")}${s.when?" · "+esc(s.when):""}</div>`;
    }).join("");
  }
  if(c.run){
    h+=`<h3>latest run${c.run.when?" · "+esc(c.run.when):""}${c.run.result?" · "+esc(c.run.result):""}</h3>`;
    if(c.run.cmd) h+=`<pre>${esc(c.run.cmd)}</pre>`;
    if(c.run.artifact) h+=`<div class="kv" style="margin-top:6px"><b>artifact</b> <code>${esc(c.run.artifact)}</code></div>`;
    if(c.run.note) h+=`<div class="kv" style="margin-top:6px">${esc(c.run.note)}</div>`;
  }
  const linkbits=[];
  if(c.links.pr) linkbits.push(PR_URL_BASE?`<a href="${PR_URL_BASE}${esc(c.links.pr)}" target="_blank">PR #${esc(c.links.pr)}</a>`:`PR #${esc(c.links.pr)}`);
  if(c.links.doc) linkbits.push(`<a href="${esc(rebase(c.links.doc))}" target="_blank">${/report/i.test(c.links.doc)?"report":"doc"}</a>`);
  if(c.links.slack) linkbits.push(`<a href="${esc(c.links.slack)}" target="_blank">slack</a>`);
  if(c.links.url) linkbits.push(`<a href="${esc(c.links.url)}" target="_blank">link</a>`);
  if(linkbits.length) h+=`<h3>links</h3><div class="kv">${linkbits.join(" · ")}</div>`;
  if(c.body){
    h+=`<h3>notes</h3><div class="body-md">${renderBody(c.body)}</div>`;
  }
  document.getElementById("d-body").innerHTML=h;
  // reset the copy-link button to its default state for this card
  const cl=document.getElementById("d-copylink"); cl.classList.remove("copied");
  document.getElementById("d-copylink-label").textContent="Copy link";
  // open-source-.md link (markserv URL) + copy-md-path button (filesystem path), per card
  const osl=document.getElementById("d-opensrc");
  if(CARDS_DIR){osl.href=CARDS_DIR+"/"+encodeURIComponent(id)+".md";osl.style.display="";}else{osl.style.display="none";}
  const cp=document.getElementById("d-copypath"); cp.classList.remove("copied");
  document.getElementById("d-copypath-label").textContent="Copy md path";
  if(CARDS_ABS){cp.style.display="";cp.title=cardPathFor(id);}else{cp.style.display="none";}
  document.getElementById("scrim").classList.add("on");
  document.getElementById("drawer").classList.add("on");
  pinned=id; drawEdges(id);   // pin arrows to the open card
  // deep-link: reflect the open card in the URL hash (no scroll jump)
  history.replaceState(null,"","#card-"+encodeURIComponent(id));
}
function cardLinkFor(id){return location.origin+location.pathname+"#card-"+encodeURIComponent(id);}
function flashCopied(){const cl=document.getElementById("d-copylink");cl.classList.add("copied");
  document.getElementById("d-copylink-label").textContent="Card link copied";
  setTimeout(()=>{cl.classList.remove("copied");document.getElementById("d-copylink-label").textContent="Copy link";},1500);}
function legacyCopy(text){const ta=document.createElement("textarea");ta.value=text;
  ta.style.position="fixed";ta.style.opacity="0";document.body.appendChild(ta);ta.select();
  try{document.execCommand("copy");}catch(e){}document.body.removeChild(ta);}
function copyCardLink(){
  if(!pinned) return;
  const url=cardLinkFor(pinned);
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(url).then(flashCopied,()=>{legacyCopy(url);flashCopied();});
  }else{legacyCopy(url);flashCopied();}
}
function cardPathFor(id){return CARDS_ABS?CARDS_ABS+"/"+id+".md":"";}
function flashPathCopied(){const cp=document.getElementById("d-copypath");cp.classList.add("copied");
  document.getElementById("d-copypath-label").textContent="Path copied";
  setTimeout(()=>{cp.classList.remove("copied");document.getElementById("d-copypath-label").textContent="Copy md path";},1500);}
function copyCardPath(){
  if(!pinned) return;
  const p=cardPathFor(pinned); if(!p) return;
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(p).then(flashPathCopied,()=>{legacyCopy(p);flashPathCopied();});
  }else{legacyCopy(p);flashPathCopied();}
}
function closeDrawer(){document.getElementById("scrim").classList.remove("on");document.getElementById("drawer").classList.remove("on");pinned=null;clearEdges();history.replaceState(null,"",location.pathname);}
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeDrawer();});
// open a card from the URL hash on load (and on back/forward navigation)
function openFromHash(){const m=/^#card-(.+)$/.exec(location.hash);if(m){const id=decodeURIComponent(m[1]);if(byId[id]){openDrawer(id);flashCard(id);}}}
window.addEventListener("hashchange",openFromHash);

// ---- meeting notes drawer (LEFT, non-modal, editable; coexists with the card drawer) ----
const NOTE_NAME="_meeting";
let notesOpen=false, notesMode="preview", notesVer=null, notesDirty=false,
    notesSaveTimer=null, notesPollTimer=null, notesOnline=true;
const ndEl=()=>document.getElementById("notesdrawer");
function ndStatus(msg,cls){const s=document.getElementById("nd-status");
  if(s){ s.textContent=msg||""; s.className="nd-status"+(cls?(" "+cls):""); }}
function nowhm(){const t=new Date();
  return String(t.getHours()).padStart(2,"0")+":"+String(t.getMinutes()).padStart(2,"0");}
function toggleNotes(){ notesOpen?closeNotes():openNotes(); }
function copyNoteLink(e){
  if(e) e.preventDefault();
  const url=new URL(NOTE_NAME+".md", location.href).href;   // markserv renders the .md as a standalone page
  const done=()=>ndStatus("link copied ✓ "+nowhm(),"ok");
  // navigator.clipboard only exists in a secure context (HTTPS/localhost); this board is plain HTTP,
  // so fall back to the execCommand textarea trick — no extra popup.
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(url).then(done).catch(()=>execCopy(url,done));
  } else { execCopy(url,done); }
  return false;
}
function execCopy(text,done){
  const ta=document.createElement("textarea");
  ta.value=text; ta.setAttribute("readonly","");
  ta.style.position="fixed"; ta.style.top="-9999px";
  document.body.appendChild(ta); ta.select();
  let ok=false; try{ ok=document.execCommand("copy"); }catch(_){}
  document.body.removeChild(ta);
  if(ok) done(); else window.prompt("Copy this link:",text);
}
function rememberNotesOpen(v){ try{localStorage.setItem("m3board:notesOpen:"+PROJECT, v?"1":"0");}catch(_){} }
function openNotes(){
  notesOpen=true;
  ndEl().classList.add("on");
  document.getElementById("notesbtn").classList.add("on");
  setNotesMode("preview");
  loadNote();
  if(!notesPollTimer) notesPollTimer=setInterval(pollNote,4000);   // live-refresh for viewers
  rememberNotesOpen(true);
}
function closeNotes(){
  if(notesDirty) saveNote();      // flush pending edits
  notesOpen=false;
  ndEl().classList.remove("on");
  document.getElementById("notesbtn").classList.remove("on");
  if(notesPollTimer){ clearInterval(notesPollTimer); notesPollTimer=null; }
  rememberNotesOpen(false);
}
function setNotesMode(m){
  if(m==="preview" && notesMode==="edit" && notesDirty) saveNote();  // save before showing preview
  notesMode=m;
  const d=ndEl();
  d.classList.toggle("mode-edit",m==="edit");
  d.classList.toggle("mode-preview",m==="preview");
  document.getElementById("nd-edit-tab").classList.toggle("active",m==="edit");
  document.getElementById("nd-prev-tab").classList.toggle("active",m==="preview");
  if(m==="edit" && notesOnline){ const ta=document.getElementById("nd-textarea"); ta.focus(); }
}
function applyNote(d){
  document.getElementById("nd-textarea").value=d.text||"";
  document.getElementById("nd-preview").innerHTML=d.html||"";
  notesVer=d.version; notesDirty=false;
}
function goOffline(){
  notesOnline=false;
  document.getElementById("nd-textarea").setAttribute("readonly","");
  ndStatus("editing offline — notes server unreachable","err");
}
function loadNote(){
  if(!EDIT_BASE){ goOffline(); return; }
  fetch(EDIT_BASE+"/note?project="+encodeURIComponent(PROJECT)+"&name="+NOTE_NAME)
    .then(r=>r.json()).then(d=>{ if(!d.ok) throw new Error(d.error||"load failed");
      notesOnline=true; document.getElementById("nd-textarea").removeAttribute("readonly");
      applyNote(d); ndStatus("",""); })
    .catch(()=>goOffline());
}
function onNoteInput(){
  if(!notesOnline) return;
  notesDirty=true; ndStatus("editing…","");
  if(notesSaveTimer) clearTimeout(notesSaveTimer);
  notesSaveTimer=setTimeout(()=>saveNote(),1500);     // debounced autosave
}
function saveNote(){
  if(!notesOnline || !EDIT_BASE) return;
  if(notesSaveTimer){ clearTimeout(notesSaveTimer); notesSaveTimer=null; }
  const text=document.getElementById("nd-textarea").value;
  ndStatus("saving…","");
  return fetch(EDIT_BASE+"/note",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({project:PROJECT,name:NOTE_NAME,text:text,base_version:notesVer})})
    .then(r=>r.json().then(d=>({code:r.status,d})))
    .then(({code,d})=>{
      if(code===409) return onNoteConflict(d);
      if(!d.ok) throw new Error(d.error||"save failed");
      notesVer=d.version; notesDirty=false;
      document.getElementById("nd-preview").innerHTML=d.html||"";
      ndStatus("saved ✓ "+nowhm(),"ok");
    })
    .catch(e=>ndStatus("⚠ "+e.message,"err"));
}
function onNoteConflict(d){
  // someone else saved since we loaded — let the scribe choose (don't silently clobber).
  const loadTheirs=confirm("Meeting notes changed elsewhere.\n\n"+
    "OK = load the latest (discard your unsaved text)\nCancel = overwrite with your version");
  if(loadTheirs){ applyNote(d); ndStatus("loaded latest",""); }
  else { notesVer=d.version; return saveNote(); }   // retry as an overwrite of current
}
function pollNote(){
  if(!notesOpen || notesDirty || !notesOnline || !EDIT_BASE) return;
  fetch(EDIT_BASE+"/note?project="+encodeURIComponent(PROJECT)+"&name="+NOTE_NAME)
    .then(r=>r.json()).then(d=>{ if(d.ok && d.version!==notesVer && !notesDirty){
      applyNote(d); ndStatus("updated "+nowhm(),""); } })
    .catch(()=>{});
}

function buildChrome(){
  const lg=document.getElementById("legend");
  STATUS_LABELS.forEach(s=>{
    lg.insertAdjacentHTML("beforeend",`<span class="lg"><span class="sw" style="background:${cssvar(COLORVAR[s])}"></span>${s}</span>`);
  });
  lg.insertAdjacentHTML("beforeend",`<span class="lg" title="card bottom strip = verification + per-branch run health; solid red = no script"><span class="vbar-sw"><i style="background:${cssvar('--done')}"></i><i style="background:${cssvar('--blocked')}"></i></span>bottom: branch health (red bar = no script)</span>`);
  const strip=document.getElementById("strip"), sl=document.getElementById("striplbl");
  MILESTONES.forEach(([num,name])=>{
    const inLane=CARDS.filter(c=>c.milestone===num);
    const ru=rollup(inLane.map(c=>c.id));
    const seg=document.createElement("div"); seg.className="seg";
    seg.style.background= inLane.length?cssvar(ru.color):"#eef0f2";
    seg.title=`Step ${num} · ${name} — ${ru.done}/${ru.total}`;
    seg.onclick=()=>{const l=document.getElementById("lane-"+num);l.scrollIntoView({behavior:"smooth",block:"start"});l.classList.remove("flash");void l.offsetWidth;l.classList.add("flash");};
    strip.appendChild(seg);
    const lbl=document.createElement("div"); lbl.className="seglbl"; lbl.style.flex="1"; lbl.textContent=num;
    sl.appendChild(lbl);
  });
}

function applyFilter(){
  const q=document.getElementById("filter").value.trim().toLowerCase();
  const toks=q?q.split(/\s+/):[];
  CARDS.forEach(c=>{
    const ok=!toks.length||toks.every(t=>{
      if(t.startsWith("status:")) return c.status===t.slice(7);
      if(t.startsWith("type:")) return c.type===t.slice(5);
      if(t.startsWith("result:")) return (c.result||"")===t.slice(7);
      if(t.startsWith("@")) return ((c.owner||"")+" "+(c.updated_by||"")).toLowerCase().includes(t.slice(1));
      if(t.startsWith("#")) return (c.tags||[]).join(" ").toLowerCase().includes(t.slice(1));
      const hay=[c.title,c.summary,c.id,c.status,c.type,c.result,(c.tags||[]).join(" ")].join(" ").toLowerCase();
      return hay.includes(t);
    });
    document.querySelectorAll(`[data-id="${CSS.escape(c.id)}"]`).forEach(el=>el.classList.toggle("dim",!ok));
  });
}

buildChrome();
buildBoard();
document.getElementById("filter").addEventListener("input",applyFilter);
openFromHash();   // deep-link: open the card named in the URL hash, if any

// ---- persist fold/unfold state across reloads (the board auto-refreshes; don't
//      re-fold the Project overview / meeting notes out from under a reader) ----
(function persistUI(){
  const lsGet=k=>{try{return localStorage.getItem(k);}catch(_){return null;}};
  const lsSet=(k,v)=>{try{localStorage.setItem(k,v);}catch(_){}};
  // Project overview <details>
  const ov=document.getElementById("overview");
  if(ov){
    const K="m3board:overviewOpen:"+PROJECT;
    if(lsGet(K)==="1") ov.open=true;
    ov.addEventListener("toggle",()=>lsSet(K, ov.open?"1":"0"));
  }
  // meeting-notes drawer (reopen if it was open before the reload)
  if(lsGet("m3board:notesOpen:"+PROJECT)==="1" && typeof openNotes==="function") openNotes();
})();
</script>
</body>
</html>
"""


def build_html(cards, cards_dir, overview_html, config, cards_abs="", project="", edit_port="8766"):
    payload = json.dumps(cards, ensure_ascii=False)
    ms = json.dumps(config["milestones"])
    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    html = TEMPLATE
    html = html.replace("__GLOBALS__", overview_html or "<p style='color:#9ca3af'>(no _project.md overview found)</p>")
    html = html.replace("__PAYLOAD__", payload)
    html = html.replace("__MILESTONES__", ms)
    html = html.replace("__CARDS_DIR__", cards_dir)
    html = html.replace("__CARDS_ABS__", cards_abs)
    html = html.replace("__GENERATED__", gen)
    html = html.replace("__TITLE__", _html.escape(config["title"], quote=False))
    html = html.replace("__PR_URL_BASE__", config["pr_url_base"])
    html = html.replace("__PROJECT__", project)
    html = html.replace("__EDIT_PORT__", str(edit_port))
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir", nargs="?", default=os.getcwd(),
                    help="project dir holding cards/ and _project.md (default: cwd)")
    ap.add_argument("--cards-dir", default="cards", help="cards dir, relative to project_dir")
    ap.add_argument("-o", "--out", default=None, help="output HTML (default: <project_dir>/_project2.html)")
    args = ap.parse_args()

    proj = os.path.abspath(args.project_dir)
    cards_path = os.path.join(proj, args.cards_dir)
    project_md = os.path.join(proj, "_project.md")
    out = args.out or os.path.join(proj, "_project2.html")
    project = os.path.basename(proj.rstrip("/"))            # dir name = project key for the edit sidecar
    edit_port = os.environ.get("TRACKER_EDIT_PORT", "8766")

    cards = load_cards(cards_path)
    overview = load_overview(project_md)
    config = load_project_config(project_md)
    html = build_html(cards, args.cards_dir, overview, config, cards_abs=cards_path,
                      project=project, edit_port=edit_port)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    by_ms = {}
    for c in cards:
        by_ms.setdefault(c["milestone"], []).append(c["id"])
    print("wrote", out)
    print("cards:", len(cards))
    for num, _ in config["milestones"]:
        ids = by_ms.get(num, [])
        if ids:
            print(f"  step {num}: {len(ids)}  {', '.join(ids)}")
    if None in by_ms:
        print(f"  unscheduled: {', '.join(by_ms[None])}")


if __name__ == "__main__":
    main()
