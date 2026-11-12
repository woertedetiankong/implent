#!/usr/bin/env python3
"""bearings: show a project as named parts, and which parts a piece of work touched.

A project lists its parts in docs/parts.md (a heading per part, the paths it owns as
backticked bullets, optionally a flow diagram). This script only reads and reports;
it never tells anyone what to change or leave alone.

  bearings.py parts                        list the parts, their file counts and unmapped files
  bearings.py check [--since REF | --commit REV] [--json]
                                           which parts the uncommitted work (or one past commit) touched
  bearings.py links [--json]               which part uses which, measured from import statements
  bearings.py web [--out FILE] [--open]    write the project map as one HTML page

Uncommitted work is split by window: which Claude Code or Codex session edited each file,
read from the session records those tools keep on this machine (--no-windows skips that).
The map also counts the uncommitted work in the repository's other worktrees.

Read-only towards the project: the only file it writes is the map page, under the git dir
unless --out says otherwise. Python 3 standard library only.
"""
import argparse
import collections
import datetime
import glob
import json
import mmap
import os
import posixpath
import re
import subprocess
import sys
import webbrowser

PARTS_FILES = ("docs/parts.md", "PARTS.md", ".bearings/parts.md", ".claude/parts.md")
SENSITIVE_RE = re.compile(r"^\s*(?:敏感|Sensitive)\s*[:：]\s*(.+)$", re.I)
ICON_RE = re.compile(r"^\s*(?:图标|Icon)\s*[:：]\s*([a-z-]+)\s*$", re.I)
FLOW_OPEN_RE = re.compile(r"^\s*```\s*flow\b[ \t]*(.*?)\s*$", re.I)  # a title may follow, for a project route
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
EXTERNAL_RE = re.compile(r"^\s*(?:外来|Vendored|Third-party)\s*[:：]\s*(.+)$", re.I)
FLOW_EDGE_RE = re.compile(r"^\s*(.+?)\s*(<->|->)\s*(.+?)\s*(?:[:：]\s*(.*))?$")
EXTERNAL_WORDS = ("外部", "external")
RULE_RE = re.compile(r"^\s*(?:规矩|Rule)\s*[:：]\s*(.+)$", re.I)
HISTORY = 200   # commits read for the map
RECENT_DAYS = 30
SHOWN = 80      # commits handed to the map page, which filters and trims them
SESSION_DAYS = 14   # session records older than this are not read
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
RUN_OPEN = 600      # seconds a shell command with no recorded result is taken to have run
PATCH_RE = re.compile(r'\*\*\* (?:Add File|Update File|Delete File|Move to): ([^\n\\"]+)')

TEXT = {
    "zh": {
        "no_parts": "没找到部分清单（{files}）。先让 AI 按技能说明起草一份。",
        "parts_head": "{n} 个部分，{files} 个文件：",
        "files": "{n} 个文件",
        "unmapped": "未归类的文件 {n} 个：",
        "unmapped_none": "所有文件都归了类。",
        "empty_part": "没有文件的部分：{names}",
        "nothing": "{since}没有任何改动。",
        "since_ref": "自 {ref} 起，",
        "since_head": "相对上次提交，",
        "since_commit": "提交 {ref}（{subject}）",
        "head": "{since}动了 {parts} 块、{files} 个文件：",
        "sensitive": "敏感：{why}",
        "unmapped_changed": "未归类",
        "by_window": "按窗口分：",
        "unknown_window": "没记到是哪个窗口",
        "last_at": "最后改动 {t}",
        "sep": "，",
        "outside_more": "（另有 {n} 个外来）",
        "outside": "外来：{why}",
        "uses": "{a} 用到 {b}（{n} 个文件）",
        "links_head": "从代码里量出来的连接，{n} 条（{langs}）：",
        "links_none": "没有量到连接。能量的语言：Python、JavaScript/TypeScript、Go。",
        "mutual": "互相用到：{pairs}",
    },
    "en": {
        "no_parts": "No parts list found ({files}). Have the agent draft one first, following the skill.",
        "parts_head": "{n} parts, {files} files:",
        "files": "{n} files",
        "unmapped": "{n} unmapped files:",
        "unmapped_none": "Every file belongs to a part.",
        "empty_part": "Parts with no files: {names}",
        "nothing": "{since}nothing changed.",
        "since_ref": "Since {ref}, ",
        "since_head": "Against the last commit, ",
        "since_commit": "Commit {ref} ({subject}) ",
        "head": "{since}{parts} parts and {files} files changed:",
        "sensitive": "sensitive: {why}",
        "unmapped_changed": "Unmapped",
        "by_window": "By window:",
        "unknown_window": "no window on record",
        "last_at": "last edit {t}",
        "sep": ", ",
        "outside_more": " (plus {n} from outside)",
        "outside": "from outside: {why}",
        "uses": "{a} uses {b} ({n} files)",
        "links_head": "{n} links measured from the code ({langs}):",
        "links_none": "No links measured. Languages it can measure: Python, JavaScript/TypeScript, Go.",
        "mutual": "use each other: {pairs}",
    },
}


def git(root, *args, stdin=None):
    out = subprocess.run(["git", "-C", root, *args], input=stdin, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(out.stderr.decode("utf-8", "replace").strip() or "git failed")
    return out.stdout


def repo_root():
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("bearings: not inside a git repository")
    return out.stdout.strip()


def state_path(root):
    git_dir = git(root, "rev-parse", "--git-dir").decode().strip()
    if not os.path.isabs(git_dir):
        git_dir = os.path.join(root, git_dir)
    return os.path.join(git_dir, "bearings", "map.html")


def zlist(raw):
    return [p for p in raw.decode("utf-8", "surrogateescape").split("\0") if p]


# Parts list ---------------------------------------------------------------

class Part:
    """A part of the project, or a sub-part inside one (then .parent is set)."""

    def __init__(self, name, parent=None):
        self.name, self.what, self.sensitive, self.patterns, self.rules = name, "", "", [], []
        self.group, self.icon, self.flow = "", "", None
        self.parent, self.children, self.external = parent, [], ""

    @property
    def top(self):
        return self.parent or self

    @property
    def outside(self):
        """Code copied in from elsewhere: it is drawn apart and left out of the project's own counts."""
        return self.external or (self.parent.external if self.parent else "")


def flow_node(flow, name):
    for node in flow["nodes"]:
        if node["name"] == name:
            return node
    node = {"name": name, "note": "", "icon": "", "ext": False}
    flow["nodes"].append(node)
    return node


def flow_line(flow, line):
    """`A -> B: label` draws an arrow (`<->` points both ways); `A | note | icon | 外部` describes a box."""
    if not line.strip():
        return
    edge = FLOW_EDGE_RE.match(line)
    if edge:
        a, arrow, b, label = edge.groups()
        flow_node(flow, a)
        flow_node(flow, b)
        flow["edges"].append({"a": a, "b": b, "label": (label or "").strip(), "both": arrow == "<->"})
        return
    fields = [x.strip() for x in line.split("|")]
    node = flow_node(flow, fields[0])
    for field in fields[1:]:
        if field.lower() in EXTERNAL_WORDS:
            node["ext"] = True
        elif re.fullmatch(r"[a-z-]+", field):
            node["icon"] = field
        elif field:
            node["note"] = field


def literal_len(pattern):
    star = pattern.find("*")
    return len(pattern) if star < 0 else star


def compile_pattern(pattern):
    """Only * is special (it stops at a slash; ** crosses them). A trailing / owns the whole folder."""
    if pattern.endswith("/"):
        return lambda path, p=pattern: path.startswith(p)
    if "*" not in pattern:
        return lambda path, p=pattern: path == p
    rx = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.compile("^" + rx + "$").match


def title_form(lines):
    """A list may start with one `#` title, for projects whose Markdown rules allow a single top-level
    heading. Every level then sits one deeper: `##` is a wing, `###` a part, `####` a sub-part."""
    tops, deeper, owning, level, fenced = 0, False, False, 0, False
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if fenced:
            continue
        head = HEAD_RE.match(line)
        if head:
            level = len(head.group(1))
            tops += level == 1
            deeper = deeper or level == 3
        elif level == 2 and line.lstrip().startswith(("- ", "* ")) and "`" in line:
            owning = True  # a `##` that owns paths is a part, so `#` is a wing
    return tops == 1 and deeper and not owning


def load_parts(root, explicit=None):
    """Returns (parts, path, routes). Routes are flow blocks outside any part: paths through the whole project."""
    candidates = [explicit] if explicit else list(PARTS_FILES)
    for rel in candidates:
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if os.path.isfile(path):
            break
    else:
        return None, None, []
    lines = open(path, encoding="utf-8").read().split("\n")
    shift = 1 if title_form(lines) else 0
    parts, routes, cur, top, group, flow = [], [], None, None, "", None
    for line in lines:
        if flow is not None:
            if line.strip().startswith("```"):
                flow = None
            else:
                flow_line(flow, line)
            continue
        opened = FLOW_OPEN_RE.match(line)
        if opened:
            if cur is not None:
                flow = cur.flow = cur.flow or {"nodes": [], "edges": []}
            else:
                flow = {"title": opened.group(1), "nodes": [], "edges": []}
                routes.append(flow)
            continue
        head = HEAD_RE.match(line)
        if head:
            level, name = len(head.group(1)) - shift, head.group(2)
            if level == 1:    # a wing groups the parts under it
                group, cur, top = name, None, None
            elif level == 2:
                cur = top = Part(name)
                cur.group = group
                parts.append(cur)
            elif level == 3 and top is not None:
                cur = Part(name, top)
                cur.group = group
                top.children.append(cur)
            elif level < 1:
                cur = top = None
            continue
        if cur is None or not line.strip():
            continue
        sens = SENSITIVE_RE.match(line)
        rule = RULE_RE.match(line)
        icon = ICON_RE.match(line)
        ext = EXTERNAL_RE.match(line)
        if icon:
            cur.icon = icon.group(1).lower()
        elif sens:
            cur.sensitive = sens.group(1).strip()
        elif ext:
            cur.external = ext.group(1).strip()
        elif rule:
            cur.rules.append(rule.group(1).strip())
        elif line.lstrip().startswith(("- ", "* ")):
            for pat in re.findall(r"`([^`]+)`", line):
                cur.patterns.append((pat, compile_pattern(pat), literal_len(pat)))
        elif not cur.what and not line.startswith(("#", ">")):
            cur.what = line.strip()
    return parts, path, routes


def leaf(path, parts, seen={}):
    """The part or sub-part that owns a path: the most specific pattern wins."""
    key = (id(parts), path)
    if key not in seen:
        best, best_rank = None, (-1, 0)
        for part in parts:
            for unit in [part] + part.children:
                for _, match, length in unit.patterns:
                    rank = (length, 1 if unit.parent else 0)  # on a tie the room inside wins
                    if rank > best_rank and match(path):
                        best, best_rank = unit, rank
        seen[key] = best
    return seen[key]


def owner(path, parts):
    """The top-level part that owns a path."""
    unit = leaf(path, parts)
    return unit.top if unit else None


def language(parts):
    return "zh" if any(ord(ch) > 0x2E7F for p in parts for ch in p.name) else "en"


def width(text):
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in text)


def pad(text, to):
    return text + " " * max(0, to - width(text))


# Tree state ---------------------------------------------------------------

def dirty_files(root, base):
    tracked = zlist(git(root, "diff", "--name-only", "-z", base, "--"))
    untracked = zlist(git(root, "ls-files", "--others", "--exclude-standard", "-z"))
    return sorted(set(tracked) | set(untracked))


def worktrees(root):
    """Every checkout of this repository, the current one first."""
    out = subprocess.run(["git", "-C", root, "worktree", "list", "--porcelain"], capture_output=True)
    trees, cur = [], None
    for line in out.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("worktree "):
            cur = {"path": os.path.realpath(line[9:]), "branch": ""}
            trees.append(cur)
        elif cur and line.startswith("branch "):
            cur["branch"] = line[7:].replace("refs/heads/", "", 1)
    here = os.path.realpath(root)
    trees = [w for w in trees if w["path"] != here and os.path.isdir(w["path"])]
    return [{"path": here, "branch": ""}] + trees


# Windows ------------------------------------------------------------------
# A window is one Claude Code or Codex session. Both tools keep a record of each session on
# this machine, and two things in it say which window changed a file:
#   edits  the file was named in one of the tool's own edit commands (certain);
#   runs   the file's modification time falls inside a shell command the session ran (a guess,
#          used only when no edit names the file and exactly one session fits).
# Nothing here is required: if the records are missing or their format has changed, every
# change simply has no window.

def stamp(text):
    try:
        return datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def inside(path, roots):
    return any(path == r or path.startswith(r + os.sep) for r in roots)


def first_ask(text, limit=60):
    """The opening line of what a person typed; "" for the context blocks the tool adds itself."""
    text = str(text).strip()
    if not text or text.startswith(("<", "#")):
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    line = next((x for x in lines if not x.startswith("[")), lines[0])
    return line if len(line) <= limit else line[: limit - 1] + "…"


def recent(paths, since):
    """Paths changed after `since`, newest first."""
    dated = []
    for path in paths:
        try:
            when = os.path.getmtime(path)
        except OSError:
            continue
        if when >= since:
            dated.append((when, path))
    return [path for _, path in sorted(dated, reverse=True)]


def mentions(path, roots):
    """Whether a session record names any of these checkouts at all; most records on a machine do not."""
    try:
        with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as data:
            return any(data.find(r.encode("utf-8")) >= 0 for r in roots)
    except (OSError, ValueError):
        return False


def new_session(tool, sid):
    return {"tool": tool, "id": sid, "title": "", "edits": {}, "runs": [], "open": {}}


def claude_sessions(roots, since):
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    # Every project folder, not only this repo's: a session started elsewhere can edit files here.
    files = glob.glob(os.path.join(home, "projects", "*", "*.jsonl"))
    files += glob.glob(os.path.join(home, "projects", "*", "*", "subagents", "*.jsonl"))
    found, seen = {}, set()
    for path in recent(files, since):  # newest first, so a resumed session keeps the edits it copied
        if not mentions(path, roots):
            continue
        sub = os.path.basename(os.path.dirname(path)) == "subagents"
        sid = os.path.basename(os.path.dirname(os.path.dirname(path))) if sub else os.path.basename(path)[:-6]
        s = found.get(sid) or found.setdefault(sid, new_session("Claude Code", sid))
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"tool_use"' in line and any(r in line for r in roots):
                    try:
                        d = json.loads(line)
                        blocks = d["message"]["content"] if d.get("type") == "assistant" else []
                    except (ValueError, KeyError, TypeError):
                        continue
                    when = stamp(d.get("timestamp"))
                    for b in blocks if isinstance(blocks, list) else []:
                        if not isinstance(b, dict) or b.get("type") != "tool_use" or b.get("id") in seen:
                            continue
                        seen.add(b.get("id"))
                        given = b.get("input") if isinstance(b.get("input"), dict) else {}
                        if b.get("name") in EDIT_TOOLS:
                            target = given.get("file_path") or given.get("notebook_path")
                            if target:
                                target = os.path.join(d.get("cwd") or "", target)
                                s["edits"][target] = max(when, s["edits"].get(target, 0))
                        elif b.get("name") in SHELL_TOOLS and not given.get("run_in_background"):
                            s["open"][b.get("id")] = when
                elif s["open"] and '"tool_result"' in line and any(k in line for k in s["open"]):
                    try:
                        d = json.loads(line)
                        blocks = d["message"]["content"] if d.get("type") == "user" else []
                    except (ValueError, KeyError, TypeError):
                        continue
                    for b in blocks if isinstance(blocks, list) else []:
                        if isinstance(b, dict) and b.get("tool_use_id") in s["open"]:
                            s["runs"].append((s["open"].pop(b["tool_use_id"]), stamp(d.get("timestamp"))))
                elif not sub and not s.get("ask") and '"type":"user"' in line and '"tool_result"' not in line:
                    try:  # the opening request names a session that was never given a title
                        d = json.loads(line)
                        said = d["message"]["content"] if d.get("type") == "user" and not d.get("isMeta") else ""
                    except (ValueError, KeyError, TypeError):
                        continue
                    for b in said if isinstance(said, list) else [{"text": said}]:
                        s["ask"] = s.get("ask") or first_ask(b.get("text") or "" if isinstance(b, dict) else "")
                elif not sub and ('"ai-title"' in line or '"custom-title"' in line):
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("type") == "custom-title" and d.get("customTitle"):
                        s["named"] = s["title"] = str(d["customTitle"])
                    elif d.get("type") == "ai-title" and d.get("aiTitle") and not s.get("named"):
                        s["title"] = str(d["aiTitle"])
        s["runs"] += [(start, start + RUN_OPEN) for start in s["open"].values()]
        s["open"] = {}
    for s in found.values():
        s["title"] = s["title"] or s.get("ask", "")
    return list(found.values())


def codex_sessions(roots, since):
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    found = []
    for path in recent(glob.glob(os.path.join(home, "sessions", "**", "*.jsonl"), recursive=True), since):
        if not mentions(path, roots):
            continue
        s = new_session("Codex", os.path.basename(path)[:-6])
        cwd, local = "", False
        with open(path, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh):
                if n == 0:
                    try:
                        cwd = os.path.realpath(json.loads(line)["payload"]["cwd"])
                    except (ValueError, KeyError, TypeError):
                        break
                    local = inside(cwd, roots)  # only then can a command name its files relative to cwd
                    continue
                call = '_call"' in line and (local or any(r in line for r in roots))
                done = s["open"] and "_call_output" in line
                ask = not s["title"] and '"user"' in line
                if not (call or done or ask):
                    continue
                try:
                    d = json.loads(line)
                    p = d.get("payload") or {}
                except ValueError:
                    continue
                kind, when = str(p.get("type")), stamp(d.get("timestamp"))
                if kind.endswith("_call"):
                    text = str(p.get("input") or p.get("arguments") or p.get("action") or "")
                    for target in PATCH_RE.findall(text):
                        target = os.path.join(cwd, target.strip())
                        s["edits"][target] = max(when, s["edits"].get(target, 0))
                    if call and p.get("call_id"):
                        s["open"][p["call_id"]] = when
                elif kind.endswith("_call_output") and p.get("call_id") in s["open"]:
                    s["runs"].append((s["open"].pop(p["call_id"]), when))
                elif ask and kind == "message" and p.get("role") == "user":
                    for c in p.get("content") or []:
                        s["title"] = s["title"] or first_ask(c.get("text") or "" if isinstance(c, dict) else "")
        s["runs"] += [(start, start + RUN_OPEN) for start in s["open"].values()]
        s["open"] = {}
        if s["edits"] or s["runs"]:
            found.append(s)
    return found


def task_name(path):
    """The journal task a file under docs/tasks/<dossier>/ belongs to, by its brief's heading."""
    m = re.match(r"(.*?/docs/tasks/([^/]+))/[^/]+$", path)
    if not m:
        return None
    try:
        with open(os.path.join(m.group(1), "task-brief.md"), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("# "):
                    return re.sub(r"^(?:Task Brief|任务书)\s*[:：]\s*", "", line[2:].strip())
    except OSError:
        pass
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", m.group(2))


def sessions(roots):
    """Recent sessions that worked in these checkouts: {tool, id, title, task, edits: {path: time}, runs}."""
    since = datetime.datetime.now().timestamp() - SESSION_DAYS * 86400
    found = []
    for reader in (claude_sessions, codex_sessions):
        try:
            found += reader(roots, since)
        except Exception:  # an unreadable or reshaped record must never break the map
            continue
    real, kept = {}, []
    for s in found:
        edits = {}
        for path, when in s["edits"].items():
            full = real.get(path) or real.setdefault(path, os.path.realpath(path))
            if inside(full, roots):
                edits[full] = max(when, edits.get(full, 0))
        if edits or s["runs"]:
            s["edits"], s["task"] = edits, ""
            for path, _ in sorted(edits.items(), key=lambda kv: -kv[1]):
                name = task_name(path)
                if name:
                    s["task"] = name
                    break
            kept.append(s)
    return kept


def clock(when):
    then = datetime.datetime.fromtimestamp(when)
    if then.date() == datetime.date.today():
        return then.strftime("%H:%M")
    return then.strftime("%m-%d %H:%M")


def in_flight(root, parts, look=True, everywhere=False):
    """The uncommitted files, split by the window that edited them.

    Returns (rows, windows). A row is one changed file in one checkout. A window carries the
    rows it edited after the file's last commit; rows nobody is on record for go to a window
    marked unknown, one per checkout.
    """
    here = {"path": os.path.realpath(root), "branch": ""}
    trees = worktrees(root) if everywhere else [here]
    found = sessions([w["path"] for w in trees]) if look else []
    rows = []
    for w in trees:
        try:
            changed = dirty_files(w["path"], "HEAD")
        except SystemExit:
            if w is trees[0]:
                raise
            continue
        for f in changed:
            full = os.path.realpath(os.path.join(w["path"], f))
            who, guess = [(s, s["edits"][full]) for s in found if full in s["edits"]], False
            if who:
                done = git(w["path"], "log", "-1", "--format=%ct", "--", f).decode().strip()
                who = [(s, when) for s, when in who if when > float(done or 0)]
            if not who and os.path.isfile(full):  # no edit names it: whose shell command was running?
                made = os.path.getmtime(full)
                near = [s for s in found if any(a - 1 <= made <= b + 2 for a, b in s["runs"])]
                if len(near) == 1:
                    who, guess = [(near[0], made)], True
            unit = leaf(f, parts)
            rows.append({"file": f, "tree": w, "part": unit.top.name if unit else "",
                         "sub": unit.name if unit and unit.parent else "", "who": who, "guess": guess})

    windows, by_id = [], {}
    for row in rows:
        for s, when in row["who"]:
            if s["id"] not in by_id:
                by_id[s["id"]] = {"tool": s["tool"], "title": s["title"], "task": s["task"], "unknown": False,
                                  "when": 0, "rows": []}
                windows.append(by_id[s["id"]])
            win = by_id[s["id"]]
            win["rows"].append(row)
            win["when"] = max(win["when"], when)
    windows.sort(key=lambda win: -win["when"])
    for w in trees:
        loose = [row for row in rows if row["tree"] is w and not row["who"]]
        if loose:
            windows.append({"tool": "", "title": "", "task": "", "unknown": True, "when": 0, "rows": loose})
    letters, unknown = 0, 0
    for win in windows:
        if win["unknown"]:
            unknown += 1
            win["key"] = "?" if unknown == 1 else "?%d" % unknown
        else:
            win["key"] = chr(65 + letters) if letters < 26 else str(letters + 1)
            letters += 1
        win["last"] = clock(win["when"]) if win["when"] else ""
        win["guessed"] = sum(1 for row in win["rows"] if row["guess"])
        win["where"] = sorted({row["tree"]["branch"] or os.path.basename(row["tree"]["path"])
                               for row in win["rows"] if row["tree"]["path"] != here["path"]})
        for row in win["rows"]:
            row.setdefault("keys", []).append(win["key"])
    return rows, windows


def grouped(rows, parts):
    """Rows as [{name, n, files}] in the order of the parts list, unmapped files last under ""."""
    groups = {}
    for row in rows:
        groups.setdefault(row["part"], []).append(row["file"])
    order = [p.name for p in parts if p.name in groups] + ([""] if "" in groups else [])
    return [{"name": name, "n": len(groups[name]), "files": groups[name]} for name in order]


# Commands -----------------------------------------------------------------

def tally(files, parts):
    """Files per part and sub-part as {unit: [own, outside]}, plus the unmapped files.
    A part's numbers include its sub-parts'; outside code is counted apart."""
    n, unmapped = collections.defaultdict(lambda: [0, 0]), []
    for f in files:
        unit = leaf(f, parts)
        if unit is None:
            unmapped.append(f)
            continue
        which = 1 if unit.outside else 0
        n[unit][which] += 1
        if unit.parent:
            n[unit.parent][which] += 1
    return n, unmapped


def cmd_parts(root, parts, t, args):
    files = zlist(git(root, "ls-files", "-z"))
    n, unmapped = tally(files, parts)
    if args.json:
        def row(p):
            out = {"name": p.name, "what": p.what, "sensitive": p.sensitive,
                   "files": n[p][0], "paths": [x[0] for x in p.patterns]}
            if n[p][1]:
                out["outside"] = n[p][1]
            if p.external:
                out["external"] = p.external
            if p.children:
                out["subs"] = [row(c) for c in p.children]
            return out
        print(json.dumps({"parts": [row(p) for p in parts], "unmapped": unmapped}, ensure_ascii=False, indent=2))
        return
    col = max(width(u.name) + (4 if u.parent else 0) for p in parts for u in [p] + p.children) + 2
    print(t["parts_head"].format(n=len(parts), files=len(files)))
    for p in parts:
        for u in [p] + p.children:
            marks = [t["sensitive"].format(why=u.sensitive)] if u.sensitive else []
            marks += [t["outside"].format(why=u.external)] if u.external else []
            mark = "  [" + "] [".join(marks) + "]" if marks else ""
            count = t["files"].format(n=n[u][1] if u.outside else n[u][0])
            if n[u][1] and not u.outside:
                count += t["outside_more"].format(n=n[u][1])
            indent = "      " if u.parent else "  "
            print(indent + pad(u.name, col - len(indent) + 2) + pad(count, 12) + (" " if width(count) >= 12 else "") + u.what + mark)
    empty = [u.name for p in parts for u in [p] + p.children if not sum(n[u])]
    if empty:
        print(t["empty_part"].format(names="、".join(empty)))
    if unmapped:
        print(t["unmapped"].format(n=len(unmapped)))
        for f in unmapped[: None if args.all else 40]:
            print("  " + f)
    else:
        print(t["unmapped_none"])


# Links measured from the code ---------------------------------------------
# Which part uses which, read from import statements. Unlike the flow diagrams, nobody writes
# these down: they are counted. Python, JavaScript/TypeScript and Go are read; other languages,
# and links that go over a network, are not seen.

LANGS = {".py": "Python", ".go": "Go", ".ts": "TypeScript", ".tsx": "TypeScript", ".mts": "TypeScript",
         ".cts": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript"}
JS_EXT = (".ts", ".tsx", ".mts", ".js", ".jsx", ".mjs", ".cjs", ".d.ts", ".json")
PY_FROM = re.compile(r"^[ \t]*from[ \t]+(\.*)([\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n#]+)", re.M)
PY_IMPORT = re.compile(r"^[ \t]*import[ \t]+([\w., \t]+)", re.M)
JS_SPEC = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\(\s*)['"]([^'"\n]+)['"]""")
GO_STR = re.compile(r'"([\w.\-/]+)"')
SOURCE_MAX = 1500000   # bytes; larger files are generated or data


def loose_json(text):
    """tsconfig files allow comments and trailing commas."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))


def read(root, f):
    try:
        with open(os.path.join(root, f), "rb") as fh:
            return fh.read(SOURCE_MAX + 1).decode("utf-8", "replace")
    except OSError:
        return ""


def code_links(root, files, parts):
    """Returns ({(unit_a, unit_b): [files, examples]}, languages): the files in a that import from b."""
    tracked = set(files)
    # Python: dotted module name -> file, from the package layout; then looser names for src/ layouts
    py, loose = {}, []
    for f in files:
        if not f.endswith(".py"):
            continue
        bits = f[:-3].split("/")
        i = len(bits) - 1
        while i > 0 and "/".join(bits[:i]) + "/__init__.py" in tracked:
            i -= 1
        if bits[-1] == "__init__":
            bits = bits[:-1]
        if bits[i:]:
            py[".".join(bits[i:])] = f
        loose.append((bits, f))
    for bits, f in loose:
        for k in range(len(bits) - 1):
            py.setdefault(".".join(bits[k:]), f)
    # JavaScript: path aliases from tsconfig, and the packages of a workspace
    aliases, packages = [], []
    for f in files:
        base = posixpath.basename(f)
        if re.fullmatch(r"[tj]sconfig(\.[\w-]+)?\.json", base):
            try:
                opts = loose_json(read(root, f)).get("compilerOptions") or {}
            except (ValueError, AttributeError):
                continue
            home = posixpath.join(posixpath.dirname(f), opts.get("baseUrl") or ".")
            for pattern, targets in (opts.get("paths") or {}).items():
                if pattern.endswith("*") and targets and str(targets[0]).endswith("*"):
                    to = posixpath.normpath(posixpath.join(home, targets[0][:-1]))
                    aliases.append((pattern[:-1], "" if to == "." else to + "/"))
        elif base == "package.json" and "/" in f and "node_modules" not in f:
            try:
                name = json.loads(read(root, f)).get("name")
            except (ValueError, AttributeError):
                continue
            if name:
                packages.append((str(name), posixpath.dirname(f)))
    if not aliases and any(f.startswith("src/") for f in files):
        aliases = [("@/", "src/"), ("~/", "src/")]
    aliases.sort(key=lambda x: -len(x[0]))
    packages.sort(key=lambda x: -len(x[0]))
    # Go: module path -> folder, and one file per folder to stand for the package
    gomods, godirs = [], {}
    for f in files:
        if posixpath.basename(f) == "go.mod":
            m = re.search(r"^module\s+(\S+)", read(root, f), re.M)
            if m:
                gomods.append((m.group(1), posixpath.dirname(f)))
        elif f.endswith(".go"):
            godirs.setdefault(posixpath.dirname(f), f)

    def js_file(stem):
        stem = posixpath.normpath(stem)
        if stem in tracked:
            return stem
        bare = re.sub(r"\.(js|jsx|mjs|cjs)$", "", stem)  # `./x.js` written for a `./x.ts` source
        for cand in (bare, stem):
            for ext in JS_EXT:
                for path in (cand + ext, cand + "/index" + ext):
                    if path in tracked:
                        return path
        return None

    def targets(f, ext, text):
        if ext == ".py":
            here = f.split("/")[:-1]
            for dots, module, names in PY_FROM.findall(text):
                names = [x.split(" as ")[0].strip() for x in names.strip("() \t").split(",")]
                mod = module.split(".") if module else []
                if dots:  # relative: resolved on the path
                    up = len(dots) - 1
                    if up > len(here):
                        continue
                    stem = "/".join(here[: len(here) - up] + mod)
                    for name in names:
                        for path in (stem + "/" + name + ".py", stem + "/" + name + "/__init__.py",
                                     stem + ".py", stem + "/__init__.py"):
                            if path.lstrip("/") in tracked:
                                yield path.lstrip("/")
                                break
                elif module:
                    for name in names:
                        hit = py.get(module + "." + name) or py.get(module)
                        if hit:
                            yield hit
            for line in PY_IMPORT.findall(text):
                for module in line.split(","):
                    bits = module.split(" as ")[0].strip().split(".")
                    while bits and ".".join(bits) not in py:
                        bits.pop()
                    if bits:
                        yield py[".".join(bits)]
        elif ext == ".go":
            head = text.split("\nfunc ", 1)[0]
            for spec in GO_STR.findall(head):
                for mod, folder in gomods:
                    if spec == mod or spec.startswith(mod + "/"):
                        hit = godirs.get(posixpath.normpath(posixpath.join(folder, spec[len(mod):].lstrip("/"))))
                        if hit:
                            yield hit
                        break
        else:
            for spec in JS_SPEC.findall(text):
                hit = None
                if spec.startswith("."):
                    hit = js_file(posixpath.join(posixpath.dirname(f), spec))
                else:
                    for prefix, to in aliases:
                        if spec.startswith(prefix):
                            hit = js_file(to + spec[len(prefix):])
                            break
                    else:
                        for name, folder in packages:
                            if spec == name or spec.startswith(name + "/"):
                                rest = spec[len(name):].lstrip("/")
                                hit = (js_file(folder + "/" + rest) or js_file(folder + "/src/" + rest)) if rest else \
                                    (js_file(folder + "/src/index") or js_file(folder + "/index") or folder + "/package.json")
                                break
                if hit:
                    yield hit

    links, langs = {}, collections.Counter()
    for f in files:
        ext = posixpath.splitext(f)[1]
        if ext not in LANGS:
            continue
        a = leaf(f, parts)
        if a is None or a.outside:
            continue
        text = read(root, f)
        if len(text) > SOURCE_MAX:
            continue
        langs[LANGS[ext]] += 1
        seen = set()
        for g in targets(f, ext, text):
            b = leaf(g, parts)
            if b is None or b is a or b in seen:
                continue
            seen.add(b)
            link = links.setdefault((a, b), [set(), []])
            link[0].add(f)
            if len(link[1]) < 3:
                link[1].append([f, g])
    return links, [name for name, _ in langs.most_common()]


def lifted(links, level):
    """Links between top-level parts (level "top"), or between the sub-parts inside one part (a Part)."""
    out = {}
    for (a, b), (sources, examples) in links.items():
        if level == "top":
            ka, kb = a.top, b.top
        elif a.parent is level and b.parent is level:
            ka, kb = a, b
        else:
            continue
        if ka is kb:
            continue
        link = out.setdefault((ka, kb), [set(), []])
        link[0] |= sources  # a file that reaches several rooms of one part still counts once
        link[1] = (link[1] + examples)[:3]
    return [{"a": a.name, "b": b.name, "n": len(sources), "ex": ex} for (a, b), (sources, ex) in
            sorted(out.items(), key=lambda kv: -len(kv[1][0]))]


def cmd_links(root, parts, t, args):
    files = zlist(git(root, "ls-files", "-z"))
    links, langs = code_links(root, files, parts)
    top = lifted(links, "top")
    if args.json:
        print(json.dumps({"languages": langs, "links": top,
                          "inside": {p.name: lifted(links, p) for p in parts if p.children and lifted(links, p)}},
                         ensure_ascii=False, indent=2))
        return
    if not top:
        print(t["links_none"])
        return
    print(t["links_head"].format(n=len(top), langs="、".join(langs) if t is TEXT["zh"] else ", ".join(langs)))
    weight = {(x["a"], x["b"]): x["n"] for x in top}
    for x in top:
        print("  " + t["uses"].format(a=x["a"], b=x["b"], n=x["n"]))
    both = sorted({tuple(sorted(k)) for k, n in weight.items()  # a real two-way tie, not one stray import
                   if min(n, weight.get((k[1], k[0]), 0)) * 4 >= max(n, weight.get((k[1], k[0]), 0))})
    if both:
        print(t["mutual"].format(pairs="；".join("%s ⇄ %s" % pair for pair in both)))


def cmd_check(root, parts, t, args):
    if args.commit:
        rev = git(root, "rev-parse", "--short", args.commit).decode().strip()
        subject = git(root, "log", "-1", "--format=%s", args.commit).decode().strip()
        since = t["since_commit"].format(ref=rev, subject=subject)
        changed = sorted(zlist(git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "--root", args.commit)))
    else:
        base = args.since or "HEAD"
        since = t["since_ref"].format(ref=args.since) if args.since else t["since_head"]
        changed = dirty_files(root, base)

    groups, unmapped = {}, []
    for f in changed:
        part = owner(f, parts)
        if part:
            groups.setdefault(part.name, []).append(f)
        else:
            unmapped.append(f)
    by_name = {p.name: p for p in parts}
    rows = [{"part": p.name, "files": groups[p.name], "sensitive": by_name[p.name].sensitive}
            for p in parts if p.name in groups]
    result = {"since": since.strip(), "parts": rows, "unmapped": unmapped}
    windows = []
    if not args.commit and not args.since and changed and not getattr(args, "no_windows", False):
        _, windows = in_flight(root, parts)
        result["windows"] = [{"key": w["key"], "tool": w["tool"], "title": w["task"] or w["title"], "last": w["last"],
                              "unknown": w["unknown"], "guessed": w["guessed"],
                              "parts": grouped(w["rows"], parts)} for w in windows]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not changed:
        print(t["nothing"].format(since=since))
        return
    print(t["head"].format(since=since, parts=len(rows) + bool(unmapped), files=len(changed)))
    print()
    col = max([width(r["part"]) for r in rows] + [width(t["unmapped_changed"])]) + 2
    for r in rows:
        note = t["sensitive"].format(why=r["sensitive"]) if r["sensitive"] else ""
        print(("  " + pad(r["part"], col) + pad(t["files"].format(n=len(r["files"])), 12) + note).rstrip())
        if args.files:
            for f in r["files"]:
                print("      " + f)
    if unmapped:
        print("  " + pad(t["unmapped_changed"], col) + t["files"].format(n=len(unmapped)))
        for f in unmapped[:6]:
            print("      " + f)
    if len(windows) > 1:  # with one window there is nothing to tell apart
        print()
        print(t["by_window"])
        for w in windows:
            name = t["unknown_window"] if w["unknown"] else (w["task"] or w["title"] or w["tool"])
            about = [] if w["unknown"] else [w["tool"], t["last_at"].format(t=w["last"])]
            where = "  ".join("%s %d" % (g["name"] or t["unmapped_changed"], g["n"]) for g in grouped(w["rows"], parts))
            print("  %-3s%s%s" % (w["key"], name, "（%s）" % t["sep"].join(about) if about else ""))
            print("      " + where)


def history(root, parts):
    """The last HISTORY commits, each with the parts it changed. Outside code is not the project's work."""
    raw = git(root, "log", "-n", str(HISTORY), "--no-merges", "--date=short", "--name-only",
              "--format=%x01%h%x02%ad%x02%s").decode("utf-8", "replace")
    commits = []
    for block in raw.split("\x01")[1:]:
        head, _, rest = block.partition("\n")
        rev, date, subject = (head.split("\x02") + ["", ""])[:3]
        groups, subs = {}, set()
        for f in filter(None, (line.strip() for line in rest.splitlines())):
            unit = leaf(f, parts)
            if unit is not None and unit.outside:
                continue
            groups.setdefault(unit.top.name if unit else "", []).append(f)
            if unit is not None and unit.parent:
                subs.add(unit)
        if groups:
            commits.append({"hash": rev, "date": date, "subject": subject, "groups": groups, "subs": subs})
    return commits


def cmd_web(root, parts, t, args):
    lang = language(parts)
    files = zlist(git(root, "ls-files", "-z"))
    n, _ = tally(files, parts)
    commits = history(root, parts)
    cutoff = (datetime.date.today() - datetime.timedelta(days=RECENT_DAYS)).isoformat()
    touching = {p.name: [c for c in commits if p.name in c["groups"]] for p in parts}
    links, langs = ({}, []) if args.no_links else code_links(root, files, parts)

    # What is uncommitted, in every checkout of the repository, split by window.
    rows, windows = in_flight(root, parts, look=not args.no_windows, everywhere=True)
    by_name = {p.name: p for p in parts}
    waiting = collections.Counter((r["part"], r["sub"]) for r in rows)

    def card(u):
        """What the page shows for a part or a sub-part."""
        return {"name": u.name, "icon": u.icon, "flow": u.flow, "what": u.what, "sensitive": u.sensitive,
                "rules": u.rules, "paths": [x[0] for x in u.patterns], "external": u.external,
                "files": n[u][1] if u.outside else n[u][0], "outside": 0 if u.outside else n[u][1]}

    out_parts = []
    for p in parts:
        mine = touching[p.name]
        together = []
        if len(mine) >= 3:
            for q in parts:
                if q.name == p.name:
                    continue
                both = sum(1 for c in mine if q.name in c["groups"])
                usual = len(touching[q.name]) / max(1, len(commits))  # how often q changes anyway
                if both * 4 >= len(mine) and both / len(mine) >= 1.5 * usual:
                    together.append({"name": q.name, "pct": round(100 * both / len(mine))})
            together.sort(key=lambda x: -x["pct"])
        subs = []
        for c in p.children:
            seen = [k for k in mine if c in k["subs"]]
            subs.append(dict(card(c), recent=sum(1 for k in seen if k["date"] >= cutoff),
                             pending=waiting[(p.name, c.name)]))
        out_parts.append(dict(card(p), group=p.group, subs=subs, inner=lifted(links, p) if p.children else [],
                              recent=sum(1 for c in mine if c["date"] >= cutoff),
                              last=mine[0]["date"] if mine else "", commits=len(mine), together=together[:4]))
    out_commits = [{"hash": c["hash"], "date": c["date"], "subject": c["subject"],
                    "parts": [{"name": name or "?", "n": len(fs), "files": fs[:6]} for name, fs in
                              sorted(c["groups"].items(), key=lambda kv: -len(kv[1]))]} for c in commits[:SHOWN]]

    def short(groups):
        return [{"name": g["name"], "n": g["n"], "files": g["files"][:6]} for g in groups]
    pending = {
        "parts": [{"part": g["name"], "n": g["n"], "files": g["files"], "sensitive": by_name[g["name"]].sensitive}
                  for g in short(grouped(rows, parts)) if g["name"]],
        "windows": [{"key": w["key"], "tool": w["tool"], "title": w["title"], "task": w["task"], "last": w["last"],
                     "where": "、".join(w["where"]) if lang == "zh" else ", ".join(w["where"]),
                     "unknown": w["unknown"], "n": len(w["rows"]), "guessed": w["guessed"], "parts": short(grouped(w["rows"], parts))}
                    for w in windows],
        "shared": [{"file": r["file"], "who": r["keys"]} for r in rows if len(r["who"]) > 1][:8],
    }

    listed = os.path.relpath(args.list_path, root).replace(os.sep, "/")
    data = {"project": os.path.basename(root), "lang": lang, "generated": datetime.date.today().isoformat(),
            "files": len(files), "history": len(commits), "recentDays": RECENT_DAYS, "list": listed,
            "parts": out_parts, "commits": out_commits, "pending": pending,
            "links": lifted(links, "top"), "measured": langs, "routes": args.routes}
    here = os.path.dirname(os.path.abspath(__file__))
    page = open(os.path.join(here, "map_template.html"), encoding="utf-8").read()
    page = page.replace("__PROJECT__", data["project"]).replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    if not args.fragment:
        page = ('<!doctype html>\n<html lang="%s">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n</head>\n<body style="margin:0">\n'
                % ("zh-CN" if lang == "zh" else "en")) + page + "\n</body>\n</html>\n"
    out = args.out or state_path(root)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(os.path.abspath(out))
    if args.open:
        webbrowser.open("file://" + os.path.abspath(out))


def main():
    ap = argparse.ArgumentParser(prog="bearings", description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", help="parts list, relative to the repo root (default: docs/parts.md)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parts", help="list parts and unmapped files")
    p.add_argument("--json", action="store_true")
    p.add_argument("--all", action="store_true", help="list every unmapped file")
    c = sub.add_parser("check", help="report which parts changed")
    c.add_argument("--since", help="everything changed since this commit, instead of only what is uncommitted")
    c.add_argument("--commit", help="report what this one past commit changed")
    c.add_argument("--json", action="store_true")
    c.add_argument("--files", action="store_true", help="list every changed file")
    w = sub.add_parser("web", help="write the project map as one HTML page")
    w.add_argument("--out", help="where to write it (default: <git-dir>/bearings/map.html)")
    w.add_argument("--open", action="store_true", help="open it in the browser")
    w.add_argument("--fragment", action="store_true", help="omit the html/head/body wrapper")
    w.add_argument("--no-links", action="store_true", help="do not read the code to measure which part uses which")
    k = sub.add_parser("links", help="which part uses which, measured from import statements")
    k.add_argument("--json", action="store_true")
    for cmd in (c, w):
        cmd.add_argument("--no-windows", action="store_true",
                         help="do not read Claude Code and Codex session records to tell windows apart")
    args = ap.parse_args()

    root = repo_root()
    parts, args.list_path, args.routes = load_parts(root, args.file)
    if not parts:
        raise SystemExit(TEXT["zh"]["no_parts"].format(files=" / ".join(PARTS_FILES)) + "\n"
                         + TEXT["en"]["no_parts"].format(files=" / ".join(PARTS_FILES)))
    t = TEXT[language(parts)]
    {"parts": cmd_parts, "check": cmd_check, "web": cmd_web, "links": cmd_links}[args.cmd](root, parts, t, args)


if __name__ == "__main__":
    main()
