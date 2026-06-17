#!/usr/bin/env python3
"""serve_edit.py — tiny write-back sidecar for the project-tracker board.

The board (`_project2.html`) is a STATIC file served read-only by markserv. This
sidecar is the one moving part that lets a click in the browser persist back into the
canonical `cards/<id>.md` frontmatter. Scope is deliberately ONE field — `owner` —
the "assign in a meeting" use case (see SCHEMA.md / the analysis doc).

Design (matches the analysis decisions):
  * Owner-only. POST /assign {project, id, owner} -> rewrite the card's `owner:` line
    (empty owner => Unassigned => the line is removed), bump `updated:`, chmod 0664,
    regenerate the board via the sibling render.py.
  * No auth (open on the internal network — an accepted decision). Permissive CORS so
    the markserv-served board (a different origin/port) can fetch it.
  * Re-reads the .md FRESH on every write (never trusts a stale in-memory copy) so two
    meeting edits don't clobber.
  * Runs as its OWN host service on its own port (default 8766), beside markserv (8765),
    supervised by notes/.serve/run_tracker_edit.sh. markserv is untouched.

Run:  TRACKER_EDIT_PORT=8766 python3 serve_edit.py
Env:  TRACKER_PROJECTS_ROOT (default /import/snvm-sc-scratch1/feiw/notes/projects)
      TRACKER_EDIT_PORT      (default 8766)
"""
import datetime
import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
try:                                                # py3.7+
    from http.server import ThreadingHTTPServer
except ImportError:                                 # py3.6 (e.g. RHEL8 system python) — compose it
    from socketserver import ThreadingMixIn

    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

HERE = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.join(HERE, "render.py")
PROJECTS_ROOT = os.path.realpath(
    os.environ.get("TRACKER_PROJECTS_ROOT", "/import/snvm-sc-scratch1/feiw/notes/projects")
)
PORT = int(os.environ.get("TRACKER_EDIT_PORT", "8766"))

SAFE = re.compile(r"^[A-Za-z0-9._-]+$")          # project / id slugs — no slashes, no traversal
FM_RE = re.compile(r"^(---\s*\n)(.*?\n)(---\s*\n)(.*)$", re.DOTALL)


def sanitize_owner(raw):
    """One clean frontmatter-safe line; '' means Unassigned. Caps length, strips control chars."""
    s = re.sub(r"[\r\n\t]+", " ", str(raw or "")).strip()
    return s[:80]


def quote_if_needed(v):
    """Frontmatter scalar: quote when it carries YAML-significant chars (comma/colon/#/quotes)."""
    if v and (re.search(r'[,:#]', v) or v != v.strip() or v[0] in "\"'"):
        return '"' + v.replace('"', '\\"') + '"'
    return v


def rewrite_owner(text, owner):
    """Return new file text with the frontmatter `owner:` set to `owner` (or removed if empty),
    and `updated:` bumped to today. Operates ONLY within the first --- frontmatter block."""
    m = FM_RE.match(text)
    if not m:
        raise ValueError("no frontmatter block")
    open_d, fm, close_d, body = m.group(1), m.group(2), m.group(3), m.group(4)
    lines = fm.split("\n")
    today = datetime.date.today().isoformat()

    out, saw_owner, saw_updated = [], False, False
    for ln in lines:
        if re.match(r"^owner:\s*", ln):
            saw_owner = True
            if owner:
                out.append("owner: " + quote_if_needed(owner))
            # empty owner -> drop the line (Unassigned == absent)
            continue
        if re.match(r"^updated:\s*", ln):
            saw_updated = True
            out.append("updated: " + today)
            continue
        out.append(ln)

    if owner and not saw_owner:
        # insert after summary:, else after title:, else after id:, else at top
        idx = next((i for i, l in enumerate(out) if re.match(r"^summary:\s*", l)), None)
        if idx is None:
            idx = next((i for i, l in enumerate(out) if re.match(r"^title:\s*", l)), None)
        if idx is None:
            idx = next((i for i, l in enumerate(out) if re.match(r"^id:\s*", l)), -1)
        out.insert(idx + 1, "owner: " + quote_if_needed(owner))
    if not saw_updated:
        # keep frontmatter tidy: only add `updated:` if there's already a `created:` anchor
        idx = next((i for i, l in enumerate(out) if re.match(r"^created:\s*", l)), None)
        if idx is not None:
            out.insert(idx + 1, "updated: " + today)

    return open_d + "\n".join(out) + close_d + body


def apply_assign(project, card_id, owner):
    if not (SAFE.match(project) and SAFE.match(card_id)):
        raise ValueError("bad project or id")
    proj = os.path.realpath(os.path.join(PROJECTS_ROOT, project))
    if os.path.commonpath([proj, PROJECTS_ROOT]) != PROJECTS_ROOT or not os.path.isdir(proj):
        raise ValueError("unknown project")
    path = os.path.realpath(os.path.join(proj, "cards", card_id + ".md"))
    if os.path.commonpath([path, proj]) != proj or not os.path.isfile(path):
        raise ValueError("unknown card")

    owner = sanitize_owner(owner)
    with open(path, "r", encoding="utf-8") as f:      # fresh read per write
        text = f.read()
    new_text = rewrite_owner(text, owner)
    old_umask = os.umask(0o002)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_text)
    finally:
        os.umask(old_umask)
    try:
        os.chmod(path, 0o664)                          # stay group-writable
    except OSError:
        pass
    regen_ok = subprocess.run([sys.executable, RENDER, proj]).returncode == 0
    return {"ok": True, "id": card_id, "owner": owner, "regen": regen_ok}


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.split("?")[0] == "/health":
            return self._json(200, {"ok": True, "service": "tracker-edit", "root": PROJECTS_ROOT})
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path.split("?")[0] != "/assign":
            return self._json(404, {"ok": False, "error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(n) or b"{}")
            res = apply_assign(req.get("project", ""), req.get("id", ""), req.get("owner", ""))
            self._json(200, res)
        except ValueError as e:
            self._json(400, {"ok": False, "error": str(e)})
        except Exception as e:                          # noqa: BLE001 — surface anything else as 500
            self._json(500, {"ok": False, "error": str(e)})

    def log_message(self, fmt, *args):                  # quieter access log
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    if not os.path.isfile(RENDER):
        sys.exit(f"no renderer at {RENDER} (plugin install corrupt?)")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    sys.stderr.write(f"tracker-edit sidecar on :{PORT}  root={PROJECTS_ROOT}\n")
    srv.serve_forever()


if __name__ == "__main__":
    main()
