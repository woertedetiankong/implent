#!/usr/bin/env python3
"""bearings: show a project as named parts, and which parts a piece of work touched.

A project lists its parts in docs/parts.md (a heading per part, the paths it owns as
backticked bullets, optionally a flow diagram). This script only reads and reports;
it never tells anyone what to change or leave alone.

  bearings.py parts                        list the parts, their file counts and unmapped files
  bearings.py check [--since REF | --commit REV] [--json]
                                           which parts the uncommitted work (or one past commit) touched
  bearings.py links [--json]               which part uses which, measured from import statements
  bearings.py doctor [--json]              check the list against the code; it reports and stops nothing
  bearings.py web [--out FILE] [--open]    write the project map as one HTML page
  bearings.py tasks [--json]               the tasks in progress, from the implementation-journal skill's
                                           records: the lines written there for people, and the parts touched
  bearings.py windows [--json]             every Claude Code and Codex window at work in this project: working,
                                           waiting for you or idle, what it was last asked, what it has changed
                                           and committed, and where two windows collide

Uncommitted work is split by window: which Claude Code or Codex session edited each file,
read from the session records those tools keep on this machine (--no-windows skips that).
The map also counts the uncommitted work in the repository's other worktrees.

Read-only towards the project: it writes the map page, under the git dir unless --out says otherwise,
and beside it a dated copy of the parts list whenever the list has changed, so that "what changed lately"
can be measured for a list nobody has committed. Python 3 standard library only.
"""
import argparse
import collections
import datetime
import difflib
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
CODE_NAME_RE = re.compile(r"`([^`]+)`")
EXTERNAL_WORDS = ("外部", "external")
RULE_RE = re.compile(r"^\s*(?:规矩|Rule)\s*[:：]\s*(.+)$", re.I)
HISTORY = 200   # commits read for the map
RECENT_DAYS = 30
SHOWN = 80      # commits handed to the map page, which filters and trims them
SESSION_DAYS = 14   # session records older than this are not read
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
RUN_OPEN = 600      # seconds a shell command with no recorded result is taken to have run
WINDOW_HOURS = 24   # a window with no uncommitted work is still shown if it was at work here this recently
BUSY_SECONDS = 180  # a turn in progress whose record moved this recently: the window is working
HELD_SECONDS = 3600 # a turn in progress that has been still for longer than that is counted as stopped
PATCH_RE = re.compile(r'\*\*\* (?:Add File|Update File|Delete File|Move to): ([^\n\\"]+)')
# Tasks. The implementation-journal skill keeps one record per task under docs/tasks/, written for the
# next AI session. It carries a `## For People` section, the few lines meant for a person:
TASKS_DIR = "docs/tasks"
PEOPLE_HEAD_RE = re.compile(r"^##\s+(?:For People|给人看的?)\s*$", re.I)
PEOPLE_RE = re.compile(r"^\s*(?:[-*]\s+)?(名字|Name|现在|Now|等你|Needs you|下一步|Next|做成了|Done|怎么试|Try"
                       r"|还没做|Not yet|新增|Added|改了|Changed|去掉|Removed)\s*[:：]\s*(.+?)\s*$", re.I)
PEOPLE_KEYS = {"名字": "name", "name": "name", "现在": "now", "now": "now",
               "等你": "needs", "needs you": "needs", "下一步": "next", "next": "next",
               "做成了": "made", "done": "made", "怎么试": "try", "try": "try", "还没做": "left", "not yet": "left",
               "新增": "new", "added": "new", "改了": "chg", "changed": "chg", "去掉": "gone", "removed": "gone"}
# The lines above the first row say where a task stands. The rest say what a finished step came to: what was
# made, how to try it, what is left, and which boxes of which flow diagram are new, changed or gone
# (`Changed: Part / Box: one sentence`; a room goes between, `Part / Room / Box`; a line with no box is
# about the part as a whole).
MARK_RE = re.compile(r"^(.+?)\s*[:：]\s*(.+)$")
NOTHING_RE = re.compile(r"^(?:none|nothing|n/a|无|没有|暂无)\W*$", re.I)

TEXT = {
    "zh": {
        "no_parts": "没找到部分清单（{files}）。先让 AI 按技能说明起草一份。",
        "parts_head": "{n} 个部分，{files} 个文件：",
        "files": "{n} 个文件",
        "unmapped": "未归类的文件 {n} 个：",
        "unmapped_none": "所有文件都归了类。",
        "empty_part": "没有文件的部分：{names}",
        "no_flow": "还没有流程图的 {n} 个：{names}",
        "nothing": "{since}没有任何改动。",
        "since_ref": "自 {ref} 起，",
        "since_head": "相对上次提交，",
        "since_commit": "提交 {ref}（{subject}）",
        "head": "{since}动了 {parts} 块、{files} 个文件：",
        "sensitive": "敏感：{why}",
        "unmapped_changed": "未归类",
        "by_window": "按窗口分：",
        "windows_head": "在这个项目里的窗口 {n} 个：",
        "windows_none": "没有找到最近在这个项目里干活的窗口。",
        "st_working": "在干活", "st_waiting": "停下来等你回话", "st_held": "停住了，可能在等你批准", "st_idle": "没在动", "st_": "",
        "win_said": "最近一次要它做：{x}", "win_clean": "没有未提交的改动", "win_commits": "提交了 {n} 次",
        "clash_head": "撞车 {n} 处：", "clash_none": "窗口之间没有撞车。",
        "clash_file": "{who} 都改了同一个文件：{file}（{part}）",
        "clash_merge": "同一个文件在几个工作区里都改了（{where}），合并时会冲突：{file}",
        "clash_part": "{who} 都在改“{part}”",
        "unknown_window": "没记到是哪个窗口",
        "last_at": "最后改动 {t}",
        "sep": "，",
        "doctor_head": "清单体检：{path}",
        "doctor_ok": "清单和代码对得上，没有发现问题。",
        "doctor_paths": "路径对不上任何文件的 {n} 处（代码可能挪过位置）：",
        "doctor_unmapped": "没有归类的文件 {n} 个（运行 parts 看是哪些）",
        "doctor_names": "方框的名字可能写错了 {n} 处（差一点就是另一块的名字，现在点不过去）：",
        "doctor_name": "{where} 的流程图里的“{box}”，像是“{unit}”",
        "doctor_level": "大块的流程图没有用自己的小房间当方框 {n} 个（可能和某个小房间画重了）：",
        "doctor_loose": "图上画了、代码里量不到的连接 {n} 条（走网络的属于正常，其余值得看一眼）：",
        "doctor_frame": "还没有整体框架图（清单最上面一个不带标题的 flow 块，用{level}当方框）",
        "level_wings": "各个区", "level_parts": "各个部分", "frame": "整体框架图",
        "doctor_wings": "还没有图的区 {n} 个（区标题下面一个不带标题的 flow 块，用区里的部分当方框）：",
        "doctor_orphans": "不在上一层图里的方框 {n} 个（每个方框都要出现在装着它的那张图上；不在运行路上的单独写一行，注明它服务谁）：",
        "doctor_shelf": "没有连线、也没写它服务谁的方框 {n} 个：",
        "doctor_shelf_row": "{on} 里的“{box}”",
        "doctor_open_in": "外面连着、里面没接上的线 {n} 条（上一层的图画了这条线，打开方框后里面找不到另一头）：",
        "doctor_open_in_row": "{unit}：上一层连着“{other}”{label}，它自己的图里没有",
        "doctor_said": "（{x}）",
        "doctor_open_out": "里面画了、外面没有的线 {n} 条（方框自己的图连到了外面，外面却没有一张图画这条线）：",
        "doctor_open_out_row": "{unit} 的图连着“{other}”",
        "doctor_routes_off": "主线上有、框架图里没有的连接 {n} 条：",
        "doctor_pieces": "断成几截的图 {n} 张：",
        "doctor_pieces_row": "{on}（{n} 截）",
        "doctor_unlabeled": "没写传的是什么的箭头 {n} 条：",
        "doctor_code": "箭头上写的代码名字在代码里找不到了 {n} 处（可能改过名）：",
        "doctor_code_row": "{on}：{arrow} 上的 `{name}`，“{unit}”的代码里没有",
        "doctor_stale": "画完流程图之后代码又改了不少的 {n} 个：",
        "doctor_stale_row": "{name}（画于 {date}，之后改了 {n} 次）",
        "doctor_bare": "还没有流程图的 {n} 个（运行 parts 看是哪些）",
        "doctor_limit": "体检查得出清单过时和写错，查不出一张流程图画得对不对。",
        "route": "主线",
        "outside_more": "（另有 {n} 个外来）",
        "outside": "外来：{why}",
        "uses": "{a} 用到 {b}（{n} 个文件）",
        "links_head": "从代码里量出来的连接，{n} 条（{langs}）：",
        "links_none": "没有量到连接。能量的语言：Python、JavaScript/TypeScript、Go、C/C++。",
        "mutual": "互相用到：{pairs}",
        "tasks_head": "正在做的事 {n} 件：",
        "tasks_none": "任务记录里没有正在做的事。",
        "tasks_old": "另有 {n} 件很久没动、也没有给人看的说明，没有列出。",
        "task_bare": "AI 还没有给它写给人看的说明",
        "task_updated": "{d} 更新",
        "task_now": "现在：{x}",
        "task_needs": "等你：{x}",
        "task_next": "下一步：{x}",
        "tasks_done_head": "最近做完的事 {n} 件：",
        "tasks_older_head": "更早做完的事 {n} 件：",
        "task_again": "做完过，现在重新打开了", "task_times": "第 {n} 次做完",
        "task_after": "做完之后它动过的文件又被改了 {n} 次",
        "task_made": "做成了：{x}",
        "task_try": "怎么试：{x}",
        "task_left": "还没做：{x}",
        "task_marks": "流程图上的变化：{x}",
        "mark_new": "新增", "mark_chg": "改了", "mark_gone": "去掉",
        "doctor_marks": "任务说明里对不上流程图的 {n} 处（名字要和清单里的一样，否则图上标不出来）：",
        "doctor_mark_unit": "“{task}”：清单里没有叫“{name}”的部分或房间",
        "doctor_mark_box": "“{task}”：“{unit}”的流程图里没有叫“{box}”的框",
        "task_rooms": "动过：{x}",
        "task_folder": "记录在：{x}",
    },
    "en": {
        "no_parts": "No parts list found ({files}). Have the agent draft one first, following the skill.",
        "parts_head": "{n} parts, {files} files:",
        "files": "{n} files",
        "unmapped": "{n} unmapped files:",
        "unmapped_none": "Every file belongs to a part.",
        "empty_part": "Parts with no files: {names}",
        "no_flow": "{n} without a flow diagram: {names}",
        "nothing": "{since}nothing changed.",
        "since_ref": "Since {ref}, ",
        "since_head": "Against the last commit, ",
        "since_commit": "Commit {ref} ({subject}) ",
        "head": "{since}{parts} parts and {files} files changed:",
        "sensitive": "sensitive: {why}",
        "unmapped_changed": "Unmapped",
        "by_window": "By window:",
        "windows_head": "{n} windows at work in this project:",
        "windows_none": "No window has been at work in this project lately.",
        "st_working": "working", "st_waiting": "stopped, waiting for your reply", "st_held": "held up, perhaps waiting for your approval", "st_idle": "idle", "st_": "",
        "win_said": "last asked: {x}", "win_clean": "nothing uncommitted", "win_commits": "{n} commits",
        "clash_head": "{n} places where windows collide:", "clash_none": "No window is in another's way.",
        "clash_file": "{who} both changed the same file: {file} ({part})",
        "clash_merge": "the same file is changed in several checkouts ({where}) and will conflict on merge: {file}",
        "clash_part": "{who} are both changing \"{part}\"",
        "unknown_window": "no window on record",
        "last_at": "last edit {t}",
        "sep": ", ",
        "doctor_head": "Check-up of {path}",
        "doctor_ok": "The list agrees with the code; nothing found.",
        "doctor_paths": "{n} paths that match no file (the code may have moved):",
        "doctor_unmapped": "{n} unmapped files (run parts to see them)",
        "doctor_names": "{n} box names that may be misspelt (close to another unit's name, so no door opens):",
        "doctor_name": "\"{box}\" in the flow of {where} looks like \"{unit}\"",
        "doctor_level": "{n} parts whose flow does not use their own rooms as boxes (it may repeat a room's diagram):",
        "doctor_loose": "{n} arrows between parts that the code does not back (fine over a network, worth a look otherwise):",
        "doctor_frame": "No diagram of the whole project yet (one untitled flow block at the top of the list, with {level} as its boxes)",
        "level_wings": "the wings", "level_parts": "the parts", "frame": "the project diagram",
        "doctor_wings": "{n} wings without a diagram (one untitled flow block under the wing's heading, with its parts as the boxes):",
        "doctor_orphans": "{n} boxes missing from the diagram one level up (every box appears on the diagram of what holds it; one that is not on the path at run time gets a line of its own, with a note saying whom it serves):",
        "doctor_shelf": "{n} boxes with no arrow and no note saying whom they serve:",
        "doctor_shelf_row": "\"{box}\" in {on}",
        "doctor_open_in": "{n} lines drawn outside a box that do not arrive inside it (the level above draws the line; the box's own diagram does not show the other end):",
        "doctor_open_in_row": "{unit}: the level above connects it to \"{other}\"{label}; its own diagram does not show that",
        "doctor_said": " ({x})",
        "doctor_open_out": "{n} lines drawn inside a box that nothing outside it draws (its own diagram reaches out; no diagram outside it shows that line):",
        "doctor_open_out_row": "the diagram of {unit} connects to \"{other}\"",
        "doctor_routes_off": "{n} links on a route that the framework diagrams do not have:",
        "doctor_pieces": "{n} diagrams in more than one piece:",
        "doctor_pieces_row": "{on} ({n} pieces)",
        "doctor_unlabeled": "{n} arrows that do not say what travels along them:",
        "doctor_code": "{n} code names on arrows that the code no longer holds (renamed, perhaps):",
        "doctor_code_row": "{on}: `{name}` on {arrow} is not in the code of \"{unit}\"",
        "doctor_stale": "{n} units whose code changed a good deal after the flow was drawn:",
        "doctor_stale_row": "{name} (drawn {date}, {n} changes since)",
        "doctor_bare": "{n} without a flow diagram (run parts to see them)",
        "doctor_limit": "A check-up finds a list that is out of date or miswritten. It cannot tell whether a flow diagram is true.",
        "route": "route",
        "outside_more": " (plus {n} from outside)",
        "outside": "from outside: {why}",
        "uses": "{a} uses {b} ({n} files)",
        "links_head": "{n} links measured from the code ({langs}):",
        "links_none": "No links measured. Languages it can measure: Python, JavaScript/TypeScript, Go, C/C++.",
        "mutual": "use each other: {pairs}",
        "tasks_head": "{n} tasks in progress:",
        "tasks_none": "The task records hold nothing in progress.",
        "tasks_old": "{n} more have not moved in a long time and carry no lines for people; they are not listed.",
        "task_bare": "the agent has not written its lines for people yet",
        "task_updated": "updated {d}",
        "task_now": "Now: {x}",
        "task_needs": "Needs you: {x}",
        "task_next": "Next: {x}",
        "tasks_done_head": "{n} finished lately:",
        "tasks_older_head": "{n} finished earlier:",
        "task_again": "finished once, open again", "task_times": "finished for the {n}th time",
        "task_after": "the files it changed were changed {n} times since",
        "task_made": "Done: {x}",
        "task_try": "Try: {x}",
        "task_left": "Not yet: {x}",
        "task_marks": "Changes on the flow diagrams: {x}",
        "mark_new": "added", "mark_chg": "changed", "mark_gone": "removed",
        "doctor_marks": "{n} marks in the tasks' lines for people that miss the flow diagrams (a name must match the list, or the page cannot mark it):",
        "doctor_mark_unit": '"{task}": no part or room on the list is called "{name}"',
        "doctor_mark_box": '"{task}": the flow diagram of "{unit}" has no box called "{box}"',
        "task_rooms": "Touched: {x}",
        "task_folder": "Recorded in: {x}",
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
        self.wing = None     # the Wing a top-level part sits in, when the list has wings
        self.lines = [0, 0]  # where it is written in the list: first line, one past the last

    @property
    def top(self):
        return self.parent or self

    @property
    def outside(self):
        """Code copied in from elsewhere: it is drawn apart and left out of the project's own counts."""
        return self.external or (self.parent.external if self.parent else "")


class Wing:
    """The parts under one `#` heading. A wing can say what it is for and carry a diagram of how its parts
    work together; the diagram of the whole project uses the wings as its boxes."""

    def __init__(self, name):
        self.name, self.what, self.icon, self.flow, self.parts = name, "", "", None, []


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
        label = label or ""
        code = [x.strip() for x in CODE_NAME_RE.findall(label) if x.strip()]  # `Name`: what the code calls it
        flow["edges"].append({"a": a, "b": b, "label": CODE_NAME_RE.sub("", label).strip(" ,，、"),
                              "both": arrow == "<->", "code": code})
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
    """Returns (parts, path, routes, top). Flow blocks outside any part are read by where they stand and
    whether they carry a title. With a title: a route, how one thing travels through the project. Without
    one: the diagram of the level they stand at, which is the whole project before the first heading and a
    wing right under its `#` heading. `top` holds those two: {"frame": flow or None, "wings": [Wing]}."""
    candidates = [explicit] if explicit else list(PARTS_FILES)
    for rel in candidates:
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if os.path.isfile(path):
            break
    else:
        return None, None, [], {"frame": None, "wings": []}
    parts, routes, top = read_list(open(path, encoding="utf-8").read())
    return parts, path, routes, top


def read_list(text):
    """The parts list from its text: (parts, routes, top)."""
    lines = text.split("\n")
    shift = 1 if title_form(lines) else 0
    parts, routes, cur, top, group, flow = [], [], None, None, "", None
    frame, wings, wing = None, [], None
    for at, line in enumerate(lines):
        if cur is not None:
            cur.lines[1] = at + 1
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
            elif opened.group(1):
                flow = {"title": opened.group(1), "nodes": [], "edges": []}
                routes.append(flow)
            elif wing is not None:
                flow = wing.flow = wing.flow or {"nodes": [], "edges": []}
            else:
                flow = frame = frame or {"nodes": [], "edges": []}
            continue
        head = HEAD_RE.match(line)
        if head:
            level, name = len(head.group(1)) - shift, head.group(2)
            if level == 1:    # a wing groups the parts under it
                group, cur, top = name, None, None
                wing = Wing(name)
                wings.append(wing)
            elif level == 2:
                cur = top = Part(name)
                cur.group, cur.lines = group, [at, at + 1]
                parts.append(cur)
                if wing is not None:
                    cur.wing = wing
                    wing.parts.append(cur)
            elif level == 3 and top is not None:
                cur = Part(name, top)
                cur.group, cur.lines = group, [at, at + 1]
                top.children.append(cur)
            elif level < 1:
                cur = top = wing = None
            continue
        if not line.strip():
            continue
        if cur is None:
            if wing is not None:  # under a wing's heading: its pictogram, and one line on what the wing is for
                icon = ICON_RE.match(line)
                if icon:
                    wing.icon = icon.group(1).lower()
                elif not wing.what and not line.lstrip().startswith(("#", ">", "-", "*", "`", "|")):
                    wing.what = line.strip()
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
    return parts, routes, {"frame": frame if frame and frame["nodes"] else None,
                           "wings": [w for w in wings if w.parts]}


# Wiring -------------------------------------------------------------------
# The list is a set of boxes inside boxes: the project holds wings, a wing holds parts, a part holds rooms.
# Each level has its own diagram, drawn with the boxes of the level below. Read together they are one
# wiring: an arrow drawn at one level has to come out somewhere at the level inside it, the way a wire
# into a block comes out at a port inside the block. This section resolves the two ends of every arrow to
# the units they stand for, so the page can show what goes in and out of each box and the check-up can say
# where two levels stopped agreeing.

def unit_up(u):
    """The unit that holds this one: a room's part, a part's wing."""
    return None if isinstance(u, Wing) else (u.parent or u.wing)


def unit_kids(u):
    return u.parts if isinstance(u, Wing) else u.children


def within(x, u):
    """Is unit u the unit x, or somewhere inside it?"""
    while u is not None and not isinstance(u, str):
        if u is x:
            return True
        u = unit_up(u)
    return False


def related(a, b):
    """The same box, or one inside the other. A name that stands for no unit matches only itself."""
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return within(a, b) or within(b, a)


def unit_label(u):
    if isinstance(u, str):
        return u
    return (u.parent.name + " / " if not isinstance(u, Wing) and u.parent else "") + u.name


class Wiring:
    """Every arrow of every diagram, with both ends resolved. An end is a unit (Wing or Part), or a plain
    name for someone or something outside the project (a person, an outside service, whoever starts or
    ends a route)."""

    def __init__(self, parts, routes, top):
        self.parts, self.wings, self.frame, self.routes = parts, top["wings"], top["frame"], routes
        self.rooms = [c for p in parts for c in p.children]
        self.ids = {}
        for i, w in enumerate(self.wings):
            self.ids[w] = "w%d" % i
        for i, p in enumerate(parts):
            self.ids[p] = "p%d" % i
            for j, c in enumerate(p.children):
                self.ids[c] = "p%d.%d" % (i, j)
        # (the unit whose diagram it is, or None; where it is; the flow; its kind)
        self.diagrams = [(None, "", self.frame, "frame")] if self.frame else []
        self.diagrams += [(None, r["title"], r, "route") for r in routes]
        self.diagrams += [(w, w.name, w.flow, "unit") for w in self.wings if w.flow and w.flow["nodes"]]
        self.diagrams += [(u, unit_label(u), u.flow, "unit") for p in parts for u in [p] + p.children
                          if u.flow and u.flow["nodes"]]
        # Names that stand outside the project wherever they appear: a person, an outside service, and
        # the plain boxes of the project's diagram and of the routes.
        self.actors = set()
        for owner, _, flow, kind in self.diagrams:
            for n in flow["nodes"]:
                if n["ext"] or ((n["icon"] == "user" or owner is None) and self.unit(n["name"], owner, kind) is None):
                    self.actors.add(n["name"])
        self.wires = []
        for owner, where, flow, kind in self.diagrams:
            ends = {n["name"]: self.end(n, owner, kind) for n in flow["nodes"]}
            for n in flow["nodes"]:
                e = ends[n["name"]]
                n["to"] = "" if isinstance(e, str) or e is owner else self.ids[e]
                # outside the box this diagram opens up: drawn at its edge, as something the box connects to
                n["outer"] = kind != "route" and (isinstance(e, str) or (owner is not None and not within(owner, e)))
            for edge in flow["edges"]:
                a, b = ends[edge["a"]], ends[edge["b"]]
                if a is b or (not isinstance(a, str) and not isinstance(b, str) and related(a, b)):
                    continue  # a step inside the unit, or between a unit and something in it
                self.wires.append({"a": a, "b": b, "edge": edge, "owner": owner, "where": where, "kind": kind})

    def unit(self, name, owner, kind="unit"):
        """The unit a box name stands for, in the diagram of `owner`. The nearest one wins: something
        inside the owner, then beside it, then anywhere."""
        if owner is None:
            order = self.wings + self.parts + self.rooms if kind == "frame" else self.parts + self.rooms + self.wings
        else:
            up = unit_up(owner)
            order = unit_kids(owner) + (unit_kids(up) if up is not None else []) + self.parts + self.wings + self.rooms
        for u in order:
            if u.name == name:
                return u
        return None

    def end(self, node, owner, kind):
        if node["ext"]:
            return node["name"]
        u = self.unit(node["name"], owner, kind)
        if u is not None:
            return u
        if owner is None or node["name"] in self.actors:
            return node["name"]
        return owner  # a plain box in a unit's own diagram is a step of that unit

    def boxes(self, unit):
        """What the unit's own diagram shows, each box resolved."""
        if not (unit.flow and unit.flow["nodes"]):
            return None
        return [self.end(n, unit, "unit") for n in unit.flow["nodes"]]

    def parent_flow(self, unit):
        """The diagram one level up, where this unit is a box: (flow, its owner or None), or (None, None)."""
        up = unit_up(unit)
        if up is None:
            return self.frame, None
        return (up.flow if up.flow and up.flow["nodes"] else None), up

    def crossings(self, unit):
        """Every arrow, drawn on a diagram outside the unit, with one end in the unit and the other not:
        (the other end, which way, the arrow, where it is drawn, must, met). `must` marks the ones on the
        diagram one level up, where the unit is a box: its own diagram has to show the other end of those.
        `met` says whether it does (None when the unit has no diagram yet)."""
        inside = self.boxes(unit)
        up = unit_up(unit)
        for w in self.wires:
            ia, ib = within(unit, w["a"]), within(unit, w["b"])
            if ia == ib or (w["owner"] is not None and within(unit, w["owner"])):
                continue
            other, via, e = (w["b"], w["a"], w["edge"]) if ia else (w["a"], w["b"], w["edge"])
            must = w["kind"] != "route" and w["owner"] is up and via is unit
            met = None if inside is None else any(related(x, other) for x in inside)
            yield other, "both" if e["both"] else ("out" if ia else "in"), e, w["where"], must, met

    def ports(self, unit):
        """What goes into the unit and what comes out, told at the unit's own level: a neighbour deep
        inside another part or wing is shown as the box that stands beside this unit and holds it. One
        row for each neighbour and direction, with the words of every arrow that runs between them."""
        above = set()
        up = unit_up(unit)
        while up is not None:
            above.add(up)
            up = unit_up(up)
        rows, seen = [], {}
        for other, way, e, where, must, met in self.crossings(unit):
            while not isinstance(other, str) and unit_up(other) is not None and unit_up(other) not in above:
                other = unit_up(other)
            key = (other if isinstance(other, str) else id(other), way)
            row = seen.get(key)
            if row is None:
                row = seen[key] = {"other": other, "dir": way, "labels": [], "code": [], "must": False,
                                   "met": None, "where": where}
                rows.append(row)
            if e["label"] and e["label"] not in row["labels"]:
                row["labels"].append(e["label"])
            row["code"] += [c for c in e["code"] if c not in row["code"]]
            if must:
                row["must"], row["where"] = True, where
                row["met"] = met if row["met"] is None else (row["met"] and met)
        # a neighbour that things travel both ways with is one row: its one-way arrows are folded into it
        for both in [r for r in rows if r["dir"] == "both"]:
            for r in [r for r in rows if r is not both and r["other"] is both["other"]]:
                both["labels"] += [x for x in r["labels"] if x not in both["labels"]]
                both["code"] += [x for x in r["code"] if x not in both["code"]]
                if r["must"]:
                    both["met"] = r["met"] if not both["must"] else (both["met"] and r["met"])
                    both["must"] = True
                rows.remove(r)
        return rows

    def backed(self, unit, other, routes=True):
        """Does any diagram outside `unit` draw a line from its box (or from something in it) to `other`,
        or to what holds `other`, or to something in `other`? An arrow drawn only inside a unit, reaching
        out to a neighbour that nothing outside the unit connects it to, is a wire with one loose end.
        A line between the wings the two sit in is not enough: that says the wings are connected, not
        that this box is."""
        for w in self.wires:
            if (w["owner"] is not None and within(unit, w["owner"])) or (w["kind"] == "route" and not routes):
                continue
            if (within(unit, w["a"]) and related(w["b"], other)) or (within(unit, w["b"]) and related(w["a"], other)):
                return True
        return False

    def problems(self):
        """Where the levels do not agree. Each finding is a short row of plain facts; nothing here is a rule
        about the code, only about the drawings."""
        out = {"open_in": [], "open_out": [], "orphans": [], "shelf": [], "routes_off": [], "unlabeled": [],
               "pieces": [], "wings_bare": [], "no_frame": False}
        units = self.wings + [u for p in self.parts for u in [p] + p.children]
        tops = self.wings or self.parts
        out["no_frame"] = self.frame is None and len(tops) > 1
        out["wings_bare"] = [w.name for w in self.wings if len(w.parts) > 1 and not (w.flow and w.flow["nodes"])]
        for u in units:
            if not isinstance(u, Wing) and u.outside:
                continue
            flow, owner = self.parent_flow(u)
            if flow is None:
                continue
            ends = [self.end(n, owner, "frame" if owner is None else "unit") for n in flow["nodes"]]
            if isinstance(u, Part) and u.parent and not any(e in u.parent.children for e in ends):
                continue  # the part's diagram uses none of its rooms: reported once, as drawn at the wrong level
            if not any(e is u for e in ends):
                out["orphans"].append({"unit": unit_label(u), "on": unit_label(owner) if owner else ""})
        for u in units:
            for other, way, e, _, must, met in self.crossings(u):
                if must and met is False:
                    out["open_in"].append({"unit": unit_label(u), "other": unit_label(other),
                                           "label": e["label"], "dir": way})
            seen = set()
            for w in self.wires if self.parent_flow(u)[0] is not None else []:
                if w["owner"] is not u:  # until the level above is drawn there is nothing to agree with
                    continue
                ia, ib = within(u, w["a"]), within(u, w["b"])
                if ia == ib:
                    continue
                other = w["b"] if ia else w["a"]
                if isinstance(other, str) or id(other) in seen:
                    continue
                seen.add(id(other))
                if not self.backed(u, other):
                    out["open_out"].append({"unit": unit_label(u), "other": unit_label(other)})
        structural = self.frame is not None or any(w.flow and w.flow["nodes"] for w in self.wings)
        for w in self.wires if structural else []:
            if w["kind"] != "route" or isinstance(w["a"], str) or isinstance(w["b"], str):
                continue
            # a route walks over the wiring: each step needs a line on the framework diagrams, drawn from
            # either of the two boxes (on the diagram that holds it, or on its own)
            if not any(x["kind"] != "route" and ((within(w["a"], x["a"]) and related(x["b"], w["b"])) or
                                                 (within(w["a"], x["b"]) and related(x["a"], w["b"])) or
                                                 (within(w["b"], x["a"]) and related(x["b"], w["a"])) or
                                                 (within(w["b"], x["b"]) and related(x["a"], w["a"])))
                       for x in self.wires):
                out["routes_off"].append({"route": w["where"], "a": unit_label(w["a"]), "b": unit_label(w["b"])})
        for owner, where, flow, kind in self.diagrams:
            wired = collections.defaultdict(set)
            for e in flow["edges"]:
                wired[e["a"]].add(e["b"])
                wired[e["b"]].add(e["a"])
                if not e["label"]:
                    out["unlabeled"].append({"on": where, "a": e["a"], "b": e["b"]})
            for n in flow["nodes"]:  # a box on the shelf: no arrow, so its note has to say whom it serves
                if n["name"] not in wired and not n["note"]:
                    out["shelf"].append({"on": where, "box": n["name"]})
            left, groups = set(wired), 0
            while left:
                groups += 1
                stack = [left.pop()]
                while stack:
                    for nxt in wired[stack.pop()]:
                        if nxt in left:
                            left.discard(nxt)
                            stack.append(nxt)
            if groups > 1:
                out["pieces"].append({"on": where, "n": groups})
        return out

    def code_gone(self, root, files, listed=""):
        """Names written on arrows (`Name`) that the code at either end no longer holds. An arrow says in
        plain words what travels along it; the name is what the code calls that, so a rename shows up here.
        The list itself (`listed`) is not searched: every name is written there."""
        asked = []  # (where, edge, name, unit)
        for owner, where, flow, kind in self.diagrams:
            ends = {n["name"]: self.end(n, owner, kind) for n in flow["nodes"]}
            for e in flow["edges"]:
                for unit in {id(x): x for x in (ends[e["a"]], ends[e["b"]]) if not isinstance(x, str)}.values():
                    asked += [(where, e, name, unit) for name in e["code"]]
        want = collections.defaultdict(set)
        for _, _, name, unit in asked:
            want[unit].add(name)
        if not want:
            return []
        for f in files:
            if f == listed:
                continue
            unit, text = leaf(f, self.parts), None
            while unit is not None:
                if want.get(unit):
                    text = read(root, f) if text is None else text
                    want[unit] -= {name for name in want[unit] if name in text}
                unit = unit_up(unit)
        return [{"on": where, "a": e["a"], "b": e["b"], "name": name, "unit": unit_label(unit)}
                for where, e, name, unit in asked if name in want[unit]]

    def loose(self, links):
        """Marks the arrows between two parts (or wings) of the project that the measured links do not back."""
        joined = {(x["a"], x["b"]) for x in links} | {(x["b"], x["a"]) for x in links}

        def tops(u):
            if isinstance(u, Wing):
                return {p.name for p in u.parts}
            return {u.top.name}
        for w in self.wires:
            if w["kind"] == "unit" and not isinstance(w["owner"], Wing):
                continue
            if isinstance(w["a"], str) or isinstance(w["b"], str):
                continue
            a, b = tops(w["a"]), tops(w["b"])
            if not (a & b) and not any((x, y) in joined for x in a for y in b):
                w["edge"]["loose"] = True


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
    if not text or text.startswith(("<", "#", "This session is being continued")):
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
    # `turn`: "busy" while the agent is in the middle of a turn, "done" once it has handed back to the person.
    # `seen`: when the record last moved. `said`: the latest thing the person asked. `here`: started in a checkout.
    return {"tool": tool, "id": sid, "title": "", "edits": {}, "runs": [], "open": {},
            "turn": "", "seen": 0.0, "said": "", "here": False, "born": 0.0}


def born(path):
    """When a session record was started. Windows are lettered in this order, so a window keeps its letter
    from one look to the next while the same windows are open."""
    try:
        info = os.stat(path)
    except OSError:
        return 0.0
    return getattr(info, "st_birthtime", 0) or info.st_ctime


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
        newest = not sub and not s["seen"]  # a resumed session has several records; the newest says how it stands
        if newest:
            s["seen"] = os.path.getmtime(path)
        if not sub:
            s["born"] = min(s["born"] or born(path), born(path))
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not s["here"] and '"cwd":"' in line and any('"cwd":"%s' % json.dumps(r)[1:-1] in line for r in roots):
                    s["here"] = True
                if newest and '"stop_reason"' in line and '"type":"assistant"' in line:
                    # the agent's last word in a turn ends it; anything else means the turn is still running
                    s["turn"] = "done" if '"stop_reason":"end_turn"' in line else "busy"
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
                elif not sub and '"type":"user"' in line and '"tool_result"' not in line:
                    try:  # the opening request names a session that was never given a title
                        d = json.loads(line)
                        said = d["message"]["content"] if d.get("type") == "user" and not d.get("isMeta") else ""
                    except (ValueError, KeyError, TypeError):
                        continue
                    for b in said if isinstance(said, list) else [{"text": said}]:
                        ask = first_ask(b.get("text") or "" if isinstance(b, dict) else "")
                        if ask:
                            s["ask"] = s.get("ask") or ask
                            if newest:  # a new request opens a turn
                                s["said"], s["turn"] = ask, "busy"
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
                ask = '"user"' in line
                if '"task_started"' in line:
                    s["turn"] = "busy"
                elif '"task_complete"' in line or '"turn_aborted"' in line:
                    s["turn"] = "done"
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
                        said = first_ask(c.get("text") or "" if isinstance(c, dict) else "")
                        if said:
                            s["title"], s["said"] = s["title"] or said, said
        s["runs"] += [(start, start + RUN_OPEN) for start in s["open"].values()]
        s["open"] = {}
        s["here"], s["seen"], s["born"] = local, os.path.getmtime(path), born(path)
        if s["edits"] or s["runs"] or s["here"]:
            found.append(s)
    return found


def brief_name(folder):
    """What a task dossier calls its task: the heading of its brief, or the folder's name without the date."""
    try:
        with open(os.path.join(folder, "task-brief.md"), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("# "):
                    return re.sub(r"^(?:Task Brief|任务书)\s*[:：]\s*", "", line[2:].strip())
    except OSError:
        pass
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", os.path.basename(folder))


NOT_TASKS = ("next-session.md", "index.md", "readme.md")  # Markdown beside the task records that is not one


def file_title(path):
    """What a one-file task record calls its task: its `#` heading, or the file's name without the date."""
    for line in slurp(path).split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", os.path.basename(path)[:-3])


def task_of(path):
    """The journal task a file belongs to: (task id, task name). A task's record is one file,
    docs/tasks/<id>.md, or in older projects a folder of several, docs/tasks/<id>/."""
    m = re.match(r"(.*?/docs/tasks/([^/]+))/[^/]+$", path)
    if m:
        return m.group(2), brief_name(m.group(1))
    m = re.match(r".*?/docs/tasks/([^/]+)\.md$", path)
    if m and os.path.basename(path).lower() not in NOT_TASKS:
        return m.group(1), file_title(path)
    return None


def task_at(rest):
    """The task id a path inside the tasks folder belongs to, or None: `<id>/anything` or `<id>.md`."""
    first, slash, _ = rest.partition("/")
    if slash:
        return first
    return first[:-3] if first.lower().endswith(".md") and first.lower() not in NOT_TASKS else None


def slurp(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def read_handoff(handoff):
    """A handoff's header and its `## For People` section: (meta, said, marks)."""
    lines = handoff.split("\n")
    meta, body = {}, 0
    if lines[0].strip() == "---":
        for at, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                body = at + 1
                break
            key, sep, value = line.partition(":")
            if sep:
                meta[key.strip().lower()] = value.strip()
    said, inside = {"name": "", "now": "", "needs": [], "next": "", "made": [], "try": "", "left": []}, False
    marks = []
    for line in lines[body:]:
        if line.startswith("## "):
            inside = bool(PEOPLE_HEAD_RE.match(line))
        elif inside:
            m = PEOPLE_RE.match(line)
            if m and not NOTHING_RE.match(m.group(2)):
                key = PEOPLE_KEYS[m.group(1).lower()]
                if key in ("new", "chg", "gone"):
                    where = MARK_RE.match(m.group(2))
                    path = [x for x in re.split(r"\s+/\s+", where.group(1) if where else m.group(2)) if x]
                    marks.append({"kind": key, "path": path, "text": where.group(2) if where else ""})
                elif key in ("needs", "made", "left"):
                    said[key].append(m.group(2))
                else:
                    said[key] = said[key] or m.group(2)
    return meta, said, marks


def load_tasks(root, where):
    """The tasks the implementation-journal skill keeps, one dossier folder each: [{id, name, plain, now,
    needs, next, made, try, left, marks, done, updated, cited}]. Those records are written for the next AI
    session, so only two things are read from them: the handoff's status and date, and its `## For People`
    section, the few lines the agent writes there in the reader's own language: where the task stands
    (名字/Name, 现在/Now, 等你/Needs you, 下一步/Next) and what its last finished step came to (做成了/Done,
    怎么试/Try, 还没做/Not yet, 新增/Added, 改了/Changed, 去掉/Removed). A record without that section is
    still a task; it has a name from its heading and no more.

    A task's record is one file, `<id>.md` with a `status:` in its header, or, in projects that started
    with the older form, a folder `<id>/` whose `handoff.md` is read the same way. `home` is that file or
    folder, `file` the file the lines for people are in, both relative to the tasks folder."""
    base = where if os.path.isabs(where) else os.path.join(root, where)
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return []
    tasks = []
    for name in names:
        folder = os.path.join(base, name)
        single = not os.path.isdir(folder)
        if single and (not name.lower().endswith(".md") or name.lower() in NOT_TASKS):
            continue
        handoff = slurp(folder if single else os.path.join(folder, "handoff.md"))
        if not handoff:
            continue
        meta, said, marks = read_handoff(handoff)
        if single and "status" not in meta:
            continue  # some other Markdown file kept beside the task records
        when = re.search(r"\d{4}-\d{2}-\d{2}", meta.get("updated", "") or name)
        tasks.append({"id": name[:-3] if single else name, "home": name,
                      "file": name if single else name + "/handoff.md",
                      "name": said["name"] or (file_title(folder) if single else brief_name(folder)),
                      "plain": bool(said["name"] and said["now"]),
                      "now": said["now"], "needs": said["needs"][:5], "next": said["next"],
                      "made": said["made"][:4], "try": said["try"], "left": said["left"][:6], "marks": marks[:16],
                      "done": meta.get("status", "").lower().startswith("complete"),
                      "updated": when.group(0) if when else "",
                      "cited": set(re.findall(r"\b[0-9a-f]{7,40}\b", handoff + (
                          "" if single else slurp(os.path.join(folder, "implementation-log.md")))))})
    return tasks


STORY = 12   # past versions of a handoff read for a task's story


def task_stories(root, rel, tasks):
    """How each task got to where it is, read from the history of its handoff: {task id: [{date, done,
    made}]}, oldest first, one entry each time its status or what it had made changed. This is what shows
    that a finished task was opened again and finished a second time: the handoff itself only ever says
    how things stand now. A handoff that was never committed has no story."""
    if not rel or not tasks:
        return {}
    paths = {posixpath.join(rel, t["file"]): t["id"] for t in tasks}
    out = subprocess.run(["git", "-C", root, "log", "--format=%x01%H%x02%ad", "--date=short", "--name-only",
                          "--", *paths], capture_output=True)
    if out.returncode:
        return {}
    revs = collections.defaultdict(list)  # task id -> [(rev, date)], newest first
    for block in out.stdout.decode("utf-8", "replace").split("\x01")[1:]:
        head, _, names = block.partition("\n")
        rev, _, date = head.partition("\x02")
        for name in names.split("\n"):
            if name.strip() in paths:
                revs[paths[name.strip()]].append((rev, date.strip(), name.strip()))
    asked = [(tid, rev, date, path) for tid, rows in revs.items() for rev, date, path in rows[:STORY]]
    if not asked:
        return {}
    blobs = subprocess.run(["git", "-C", root, "cat-file", "--batch"], capture_output=True,
                           input="".join("%s:%s\n" % (rev, path) for _, rev, _, path in asked).encode())
    raw, at, stories = blobs.stdout, 0, collections.defaultdict(list)
    for tid, rev, date, path in asked:
        end = raw.find(b"\n", at)
        if end < 0:
            break
        head = raw[at:end].split()
        at = end + 1
        if len(head) < 3 or head[1] != b"blob":
            continue
        size = int(head[2])
        meta, said, _ = read_handoff(raw[at:at + size].decode("utf-8", "replace"))
        at += size + 1
        stories[tid].append({"date": date, "done": meta.get("status", "").lower().startswith("complete"),
                             "made": said["made"][0] if said["made"] else ""})
    for tid, rows in stories.items():
        rows.reverse()
        kept = []
        for row in rows:
            if not kept or (kept[-1]["done"], kept[-1]["made"]) != (row["done"], row["made"]):
                kept.append(row)
        stories[tid] = kept
    return stories


def task_rooms(task, commits, rel):
    """Where a task's committed work landed, as {part name: files}. Measured, not written: the commits
    its records cite by hash, and the commits that changed its dossier and no other task's. The dossier's
    own files are bookkeeping and are left out, so the picture is of the work itself."""
    rooms, prefix = collections.Counter(), rel + "/" if rel else None
    files, last, own = set(), 0, set()
    for c in commits:
        mine = any(t.startswith(c["hash"]) or c["hash"].startswith(t) for t in task["cited"])
        if not mine and prefix:
            mine = {task_at(f[len(prefix):]) for fs in c["groups"].values() for f in fs
                    if f.startswith(prefix)} - {None} == {task["id"]}
        if mine:
            own.add(c["hash"])
            last = max(last, c["when"])
            for name, fs in c["groups"].items():
                work = [f for f in fs if not (prefix and f.startswith(prefix))]
                files.update(work)
                if work:
                    rooms[name] += len(work)
    # What happened to those files afterwards, in commits that are not this task's. A finished task's
    # write-up describes the code as it was then; this is how a reader learns it has moved on since.
    task["after"] = None if not files else sum(
        1 for c in commits if c["when"] > last and c["hash"] not in own
        and any(f in files for fs in c["groups"].values() for f in fs))
    task["files"], task["last"], task["own"] = files, last, own
    return rooms


def older_commits(root, parts, rel, tasks, commits):
    """The commits a task's records point at that lie further back than the map's window: the ones cited
    by hash, and the ones that changed its dossier. Without them a task finished long ago would show no
    parts at all. Returns them in the form `history` gives."""
    known = {c["hash"] for c in commits}
    words = {w for t in tasks for w in t["cited"] if not any(w.startswith(k) or k.startswith(w) for k in known)}
    revs = set()
    if words:  # a word of hex digits in a record is not always a commit
        out = subprocess.run(["git", "-C", root, "cat-file", "--batch-check"], capture_output=True,
                             input="\n".join(sorted(words)).encode())
        for line in out.stdout.decode("utf-8", "replace").splitlines():
            bits = line.split()
            if len(bits) >= 2 and bits[1] == "commit":
                revs.add(bits[0])
    if rel:
        for t in tasks:
            out = subprocess.run(["git", "-C", root, "log", "--no-merges", "--format=%H", "-n", "100", "--",
                                  posixpath.join(rel, t["home"])], capture_output=True)
            revs.update(out.stdout.decode().split())
    revs = [r for r in revs if not any(r.startswith(k) for k in known)]
    return history(root, parts, revs) if revs else []


def changed_after(root, task):
    """How many later commits, not the task's own, changed the files the task changed. Asked of git over
    the whole history, so it does not stop at the map's window."""
    files = sorted(task["files"])[:300]
    if not files or not task["last"]:
        return task["after"]
    out = subprocess.run(["git", "-C", root, "rev-list", "--no-merges", "--abbrev-commit",
                          "--max-age=%d" % (task["last"] + 1), "HEAD", "--", *files],
                         capture_output=True)
    if out.returncode:
        return task["after"]
    revs = out.stdout.decode().split()
    return sum(1 for r in revs if not any(r.startswith(o) or o.startswith(r) for o in task["own"]))


def place_marks(task, parts):
    """Find each mark's part, room and box on the list. A mark names boxes of a flow diagram someone drew
    for the list, so a name can miss: `unit` stays "" when no part or room carries the name, and `drawn`
    says whether the box is in that unit's diagram. A removed box is not expected to be there."""
    tops = {p.name: p for p in parts}
    for m in task["marks"]:
        path, unit = m.pop("path"), None
        top = tops.get(path[0]) if path else None
        if path and not top:  # a room named without its part
            room = next((c for p in parts for c in p.children if c.name == path[0]), None)
            if room:
                top, path = room.parent, [room.parent.name] + path
        if top:
            room = next((c for c in top.children if len(path) > 1 and c.name == path[1]), None)
            unit, rest = (room, path[2:]) if room else (top, path[1:])
        else:
            rest = path[1:]
        m["part"], m["room"] = top.name if top else (path[0] if path else ""), unit.name if unit and unit.parent else ""
        m["unit"], m["box"] = unit.name if unit else "", " / ".join(rest)
        m["drawn"] = bool(unit and unit.flow and any(n["name"] == m["box"] for n in unit.flow["nodes"]))


def tasks_shown(root, where, parts, commits):
    """(tasks to show, how many were left out). A task is in progress until its handoff says Complete. A
    finished one is kept for as long as its record is, provided the agent wrote lines for people: for
    RECENT_DAYS as "finished lately", after that as `old`, which the page folds away. An unfinished one
    with no lines for people that has not moved in RECENT_DAYS is left out: it would be a stale name the
    reader can do nothing with. Each task gets `rooms`, [{name, n}] in the order of the list; `after`, how
    often the files it changed were changed again by later work (None when its commits are not known);
    `story`, how its status and result changed over time; `times`, how often it was finished; `again`,
    whether it was finished once and is open again."""
    base = where if os.path.isabs(where) else os.path.join(root, where)
    rel = os.path.relpath(base, root).replace(os.sep, "/")
    rel = None if rel.startswith("..") else rel
    today, shown, left_out = datetime.date.today(), [], 0
    loaded = load_tasks(root, where)
    commits = commits + older_commits(root, parts, rel, loaded, commits) if commits else commits
    for t in loaded:
        try:
            t["days"] = (today - datetime.date.fromisoformat(t["updated"])).days
        except ValueError:
            t["days"] = -1
        recent = 0 <= t["days"] <= RECENT_DAYS
        if t["done"] and not (t["plain"] or t["made"]):
            continue
        t["old"] = t["done"] and not recent  # finished a while ago: kept, but out of the way
        if not t["done"] and not t["plain"] and not recent:
            left_out += 1
            continue
        landed = task_rooms(t, commits, rel)
        t["rooms"] = [{"name": p.name, "n": landed[p.name]} for p in parts if landed[p.name]]
        if landed[""]:
            t["rooms"].append({"name": "", "n": landed[""]})
        t["rel"] = rel
        if t["done"] and commits:
            t["after"] = changed_after(root, t)
        place_marks(t, parts)
        shown.append(t)
    stories = task_stories(root, rel, shown)
    for t in shown:
        story = stories.get(t["id"], [])
        # the file as it stands may be ahead of its last commit
        if story and (story[-1]["done"], story[-1]["made"]) != (t["done"], t["made"][0] if t["made"] else ""):
            story.append({"date": t["updated"], "done": t["done"], "made": t["made"][0] if t["made"] else ""})
        t["story"] = story[-8:]
        t["times"] = sum(1 for i, row in enumerate(story) if row["done"] and (i == 0 or not story[i - 1]["done"]))
        t["again"] = not t["done"] and any(row["done"] for row in story)  # finished once, open again
    shown.sort(key=lambda t: t["updated"], reverse=True)
    # what waits on the reader comes first, what is finished comes last, what was finished long ago after that
    shown.sort(key=lambda t: (t["old"], t["done"], not t["needs"]))
    return shown, left_out


def sessions(roots):
    """Recent sessions that worked in these checkouts: {tool, id, title, task, edits: {path: time}, runs,
    turn, seen, said, here}."""
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
        if edits or s["runs"] or s["here"]:
            s["edits"], s["task"], s["dossier"] = edits, "", ""
            for path, _ in sorted(edits.items(), key=lambda kv: -kv[1]):
                hit = task_of(path)
                if hit:
                    s["dossier"], s["task"] = hit
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
                by_id[s["id"]] = {"tool": s["tool"], "title": s["title"], "task": s["task"], "dossier": s["dossier"],
                                  "unknown": False, "when": 0, "rows": []}
                windows.append(by_id[s["id"]])
            win = by_id[s["id"]]
            win["rows"].append(row)
            win["when"] = max(win["when"], when)
    # A window with nothing uncommitted is still at work here if its session sat in a checkout lately:
    # reading, planning, or already committed.
    now = datetime.datetime.now().timestamp()
    by_session = {s["id"]: s for s in found}
    for s in found:
        if s["id"] not in by_id and s["here"] and now - s["seen"] <= WINDOW_HOURS * 3600:
            by_id[s["id"]] = {"tool": s["tool"], "title": s["title"], "task": s["task"], "dossier": s["dossier"],
                              "unknown": False, "when": 0, "rows": []}
            windows.append(by_id[s["id"]])
    for sid, win in by_id.items():
        s = by_session[sid]
        win["session"], win["seen"], win["said"] = s, max(s["seen"], win["when"]), s["said"]
        still = now - win["seen"]
        # working: in a turn and the record moved a moment ago. held: in a turn but still for a while, which is
        # what a window waiting for a permission looks like, or one running a long command. waiting: the agent
        # has handed back and the person has not answered. idle: nothing for a long time.
        win["state"] = ("working" if still <= BUSY_SECONDS else "held" if still <= HELD_SECONDS else "idle") \
            if s["turn"] == "busy" else ("waiting" if still <= WINDOW_HOURS * 3600 else "idle") \
            if s["turn"] == "done" else ("working" if still <= BUSY_SECONDS else "idle")
    windows.sort(key=lambda win: win["session"]["born"])  # oldest first: a window keeps its letter and its place
    for w in trees:
        loose = [row for row in rows if row["tree"] is w and not row["who"]]
        if loose:
            windows.append({"tool": "", "title": "", "task": "", "dossier": "", "unknown": True, "when": 0,
                            "rows": loose, "session": None, "seen": 0, "said": "", "state": ""})
    letters, unknown = 0, 0
    for win in windows:
        if not win["unknown"] and not win["dossier"]:
            # No edit command names a dossier, but a file this window changed by a shell command may lie in
            # one. That is enough to say which task the window is on; its name stays the session's own.
            for row in win["rows"]:
                hit = task_of(os.path.join(row["tree"]["path"], row["file"]))
                if hit:
                    win["dossier"] = hit[0]
                    break
        if win["unknown"]:
            unknown += 1
            win["key"] = "?" if unknown == 1 else "?%d" % unknown
        else:
            win["key"] = chr(65 + letters) if letters < 26 else str(letters + 1)
            letters += 1
        win["last"] = clock(win["seen"]) if win["seen"] else ""
        win["guessed"] = sum(1 for row in win["rows"] if row["guess"])
        win["where"] = sorted({row["tree"]["branch"] or os.path.basename(row["tree"]["path"])
                               for row in win["rows"] if row["tree"]["path"] != here["path"]})
        for row in win["rows"]:
            row.setdefault("keys", []).append(win["key"])
    return rows, windows


def clashes(rows, windows, records=()):
    """Where windows get in each other's way, worst first: the same file changed by two windows in one
    checkout (one will overwrite the other), the same file changed in two checkouts (a conflict when they
    are merged), and the same part being changed by two windows (worth a look). `records` is the parts
    list followed by the tasks folder. The list is left out altogether: every window keeps its own lines
    of it up to date, which is what it is for. Both are left out of the last kind."""
    out, seen = [], set()
    listed = records[0] if records else ""
    rows = [r for r in rows if r["file"] != listed]
    for r in rows:
        keys = [k for k in r.get("keys", []) if not k.startswith("?")]
        if len(keys) > 1:
            seen.add(r["file"])
            out.append({"kind": "file", "file": r["file"], "part": r["part"], "who": keys, "where": []})
    trees = collections.defaultdict(list)
    for r in rows:
        trees[r["file"]].append(r)
    for f, same in trees.items():
        if len({id(r["tree"]) for r in same}) > 1 and f not in seen:
            seen.add(f)
            out.append({"kind": "merge", "file": f, "part": same[0]["part"],
                        "who": sorted({k for r in same for k in r.get("keys", []) if not k.startswith("?")}),
                        "where": sorted({r["tree"]["branch"] or os.path.basename(r["tree"]["path"]) for r in same})})
    by_part = collections.defaultdict(lambda: collections.defaultdict(int))
    for r in rows:
        if r["part"] and not r["file"].startswith(tuple(records) or ("\0",)):
            for k in r.get("keys", []):
                if not k.startswith("?"):
                    by_part[r["part"]][k] += 1
    hard = {c["part"] for c in out}
    for part, who in by_part.items():
        if len(who) > 1 and part not in hard:
            out.append({"kind": "part", "file": "", "part": part, "who": sorted(who), "where": [],
                        "n": dict(who)})
    return out


def window_commits(windows, commits):
    """Gives each window the commits made while one of its shell commands was running, when exactly one
    window fits: the same reasoning that matches a file changed by a shell command. Each window gets
    `commits`, [{hash, subject, parts}], newest first."""
    for win in windows:
        win["commits"] = []
    for c in commits:
        near = [win for win in windows if win.get("session") and
                any(a - 1 <= c["when"] <= b + 2 for a, b in win["session"]["runs"])]
        if len(near) == 1:
            near[0]["commits"].append({"hash": c["hash"], "subject": c["subject"],
                                       "parts": sorted(name for name in c["groups"] if name)})


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
    routes = args.routes
    files = zlist(git(root, "ls-files", "-z"))
    n, unmapped = tally(files, parts)
    if args.json:
        def row(p):
            out = {"name": p.name, "what": p.what, "sensitive": p.sensitive,
                   "files": n[p][0], "paths": [x[0] for x in p.patterns]}
            if p.children or p.parent or routes:  # lists in the newer form also say what is still undrawn
                out["flow"] = bool(p.flow and p.flow["nodes"])
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
    bare = [(u.parent.name + " / " if u.parent else "") + u.name for p in parts for u in [p] + p.children
            if not u.outside and not (u.flow and u.flow["nodes"])]
    if bare:
        print(t["no_flow"].format(n=len(bare), names="、".join(bare[:30]) + (" …" if len(bare) > 30 else "")))
    if unmapped:
        print(t["unmapped"].format(n=len(unmapped)))
        for f in unmapped[: None if args.all else 40]:
            print("  " + f)
    else:
        print(t["unmapped_none"])


# Links measured from the code ---------------------------------------------
# Which part uses which, read from import statements. Unlike the flow diagrams, nobody writes
# these down: they are counted. Python, JavaScript/TypeScript, Go and C/C++ are read; other languages,
# and links that go over a network, are not seen.

LANGS = {".py": "Python", ".go": "Go", ".ts": "TypeScript", ".tsx": "TypeScript", ".mts": "TypeScript",
         ".cts": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
         ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++", ".hh": "C++"}
C_EXT = (".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh")
C_INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*["<]([^">\n]+)[">]', re.M)
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
    # Python: every dotted name a file can be imported by -> [(the folder that name starts from, file,
    # whether the package layout says so)]. `a/b/c.py` is `c`, `b.c` or `a.b.c` depending on which folder
    # is on the import path: folders holding an __init__.py settle it, the longer names are looser guesses.
    py = collections.defaultdict(list)
    for f in files:
        if not f.endswith(".py"):
            continue
        bits = f[:-3].split("/")
        i = len(bits) - 1
        while i > 0 and "/".join(bits[:i]) + "/__init__.py" in tracked:
            i -= 1
        if bits[-1] == "__init__":
            bits = bits[:-1]
        for k in range(len(bits)):
            if k == i or k < len(bits) - 1:
                py[".".join(bits[k:])].append(("/".join(bits[:k]), f, k == i))

    def py_file(name, folder, text):
        """The file a dotted name means to code in `folder` (whose source is `text`), or None. Several
        files can answer to one name (`utils`, `config`) and a file can carry a standard-library name
        (`logging.py`), so: a name that one of the importer's own folders provides wins, the nearest
        one first; failing that, a package elsewhere in the repo counts when exactly one place provides
        it; a lone script in some other folder counts only when the importer puts that folder on its
        path itself (it touches sys.path and names the folder), since otherwise it cannot reach it."""
        found = py.get(name)
        if not found:
            return None
        near = [c for c in found if not c[0] or (folder + "/").startswith(c[0] + "/")]
        if near:
            return max(near, key=lambda c: (len(c[0]), c[2]))[1]
        if "." not in name:
            found = [c for c in found if c[1].endswith("/__init__.py") or ("sys.path" in text and re.search(
                r"""['"/\\]%s['"/\\]""" % re.escape(posixpath.basename(c[0])), text))]
        found = [c for c in found if c[2]] or found
        return found[0][1] if len(found) == 1 else None

    # JavaScript: path aliases from tsconfig, and the packages of a workspace.
    # An alias is (the folder its tsconfig sits in, prefix, target folder): `@/` in one app of a
    # monorepo is not `@/` in the app next to it.
    aliases, packages = [], []
    for f in files:
        base = posixpath.basename(f)
        if re.fullmatch(r"[tj]sconfig(\.[\w-]+)?\.json", base):
            try:
                opts = loose_json(read(root, f)).get("compilerOptions") or {}
            except (ValueError, AttributeError):
                continue
            scope = posixpath.dirname(f)
            home = posixpath.join(scope, opts.get("baseUrl") or ".")
            for pattern, targets in (opts.get("paths") or {}).items():
                if pattern.endswith("*") and targets and str(targets[0]).endswith("*"):
                    to = posixpath.normpath(posixpath.join(home, targets[0][:-1]))
                    aliases.append((scope, pattern[:-1], "" if to == "." else to + "/"))
        elif base == "package.json" and "/" in f and "node_modules" not in f:
            try:
                name = json.loads(read(root, f)).get("name")
            except (ValueError, AttributeError):
                continue
            if name:
                packages.append((str(name), posixpath.dirname(f)))
    if not aliases and any(f.startswith("src/") for f in files):
        aliases = [("", "@/", "src/"), ("", "~/", "src/")]
    aliases.sort(key=lambda x: (-len(x[0]), -len(x[1])))  # the nearest tsconfig first, then the longest prefix
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

    # C and C++: every tracked file by its base name, to resolve an `#include` the build finds on an include path
    cnames = collections.defaultdict(list)
    if any(f.endswith(C_EXT) for f in files):
        for f in files:
            cnames[posixpath.basename(f)].append(f)

    def c_file(spec, folder):
        """The file an `#include` means to code in `folder`: the one beside the including file, else the only
        file in the repo whose path ends that way. When several do (one `board.h` per board), the one that
        shares more of its folders with the including file than any other; a tie is left out, not guessed."""
        spec = posixpath.normpath(spec.replace("\\", "/"))
        near = posixpath.normpath(posixpath.join(folder, spec))
        if near in tracked:
            return near
        if spec.startswith(".."):
            return None
        found = [c for c in cnames.get(posixpath.basename(spec), ()) if c == spec or c.endswith("/" + spec)]
        if len(found) < 2:
            return found[0] if found else None
        here = folder.split("/") if folder else []

        def shared(c):
            n = 0
            for x, y in zip(here, c.split("/")):
                if x != y:
                    break
                n += 1
            return n
        ranked = sorted(found, key=shared, reverse=True)
        return ranked[0] if shared(ranked[0]) > shared(ranked[1]) else None

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
            folder = "/".join(here)
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
                        hit = py_file(module + "." + name, folder, text) or py_file(module, folder, text)
                        if hit:
                            yield hit
            for line in PY_IMPORT.findall(text):
                for module in line.split(","):
                    bits = module.split(" as ")[0].strip().split(".")
                    while bits:
                        hit = py_file(".".join(bits), folder, text)
                        if hit:
                            yield hit
                            break
                        bits.pop()
        elif ext in C_EXT:
            folder = posixpath.dirname(f)
            for spec in C_INCLUDE.findall(text):
                hit = c_file(spec.strip(), folder)
                if hit:
                    yield hit
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
            mine = [a for a in aliases if not a[0] or f.startswith(a[0] + "/")]  # from tsconfigs above this file
            for spec in JS_SPEC.findall(text):
                hit = None
                if spec.startswith("."):
                    hit = js_file(posixpath.join(posixpath.dirname(f), spec))
                else:
                    decides = None  # the nearest tsconfig that knows the prefix; one further up gets no say
                    for scope, prefix, to in mine:
                        if spec.startswith(prefix) and decides in (None, scope):
                            decides = scope
                            hit = js_file(to + spec[len(prefix):])
                            if hit:
                                break
                    if not hit:
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


def history(root, parts, revs=None):
    """The last HISTORY commits, each with the parts it changed; or, given `revs`, exactly those commits,
    however far back they are. Outside code is not the project's work."""
    # -z gives file names as they are. Without it git quotes every name that is not plain ASCII
    # ("docs/\344\275\277...md"), and a file with a Chinese name would match no part.
    span = ["--no-walk=unsorted", "--stdin"] if revs is not None else ["-n", str(HISTORY), "--no-merges"]
    if revs is not None and not revs:
        return []
    raw = git(root, "log", "-z", *span, "--date=short", "--name-only", "--format=%x01%h%x02%ad%x02%ct%x02%s",
              stdin="\n".join(revs).encode() if revs is not None else None).decode("utf-8", "replace")
    commits = []
    for block in raw.split("\x01")[1:]:
        head, _, rest = block.partition("\0")
        rev, date, when, subject = (head.rstrip("\n").split("\x02", 3) + ["", "", ""])[:4]
        groups, subs = {}, set()
        for f in filter(None, (name.strip("\n") for name in rest.split("\0"))):
            unit = leaf(f, parts)
            if unit is not None and unit.outside:
                continue
            groups.setdefault(unit.top.name if unit else "", []).append(f)
            if unit is not None and unit.parent:
                subs.add(unit)
        if groups:
            commits.append({"hash": rev, "date": date, "when": int(when or 0), "subject": subject,
                            "groups": groups, "subs": subs})
    return commits


def drawn_times(root, list_path, parts):
    """When each unit's lines in the list were last changed: {unit: unix time}. A unit written
    or edited but not yet committed counts as drawn when the file was last saved."""
    saved = os.path.getmtime(list_path)
    out = subprocess.run(["git", "-C", root, "blame", "--line-porcelain", "--", list_path], capture_output=True)
    times = []
    if out.returncode == 0:
        when, pending = 0.0, False
        for line in out.stdout.decode("utf-8", "replace").splitlines():
            if line.startswith("committer-time "):
                when = float(line[15:])
            elif re.match(r"^[0-9a-f]{40} ", line):
                pending = line.startswith("0" * 40)
            elif line.startswith("\t"):
                times.append(saved if pending else when)
    drawn = {}
    for p in parts:
        for u in [p] + p.children:
            start = u.lines[0]
            end = u.children[0].lines[0] if u.children else u.lines[1]  # a part's own lines stop at its first room
            span = times[start:end]
            drawn[u] = max(span) if span else saved
    return drawn


def aging(root, list_path, parts, commits):
    """For every unit with a flow diagram: {unit: (date drawn, commits to its code since)}."""
    drawn = drawn_times(root, list_path, parts)
    listed = os.path.relpath(list_path, root).replace(os.sep, "/")
    out = {}
    for p in parts:
        for u in [p] + p.children:
            if not (u.flow and u.flow["nodes"]):
                continue
            since = 0
            for c in commits:
                if c["when"] <= drawn[u]:
                    continue
                if u.parent:
                    since += u in c["subs"]
                else:
                    since += any(f != listed for f in c["groups"].get(p.name, []))
            out[u] = (datetime.date.fromtimestamp(drawn[u]).isoformat(), since)
    return out


STALE = 8   # commits to a unit's code after its flow was drawn, before the check-up mentions it
SPANS = (7, 30, 90)   # the stretches of days the page can report changes over
KEPT = 60             # copies of the list kept beside the map page, for a list that is not committed


def list_before(root, list_path, when):
    """The text of the parts list as it stood at unix time `when`, and where that came from: its last
    committed version before then ("git"), or, for a list that was not committed by then, the newest copy
    kept beside the map page ("local"). ("", "new") when the list was first committed after `when`;
    ("", "short") when it was never committed and the copies kept do not reach back that far; ("", "")
    when it was never committed and no copy has been kept yet."""
    rel = os.path.relpath(list_path, root).replace(os.sep, "/")
    if not rel.startswith(".."):
        out = subprocess.run(["git", "-C", root, "log", "-1", "--format=%H", "--before=%d" % when, "--", rel],
                             capture_output=True)
        rev = out.stdout.decode().strip()
        if rev:
            text = subprocess.run(["git", "-C", root, "show", "%s:%s" % (rev, rel)], capture_output=True)
            if text.returncode == 0:
                return text.stdout.decode("utf-8", "replace"), "git"
    kept = sorted(glob.glob(os.path.join(os.path.dirname(state_path(root)), "lists", "*.md")))
    day = datetime.date.fromtimestamp(when).isoformat()
    before = [k for k in kept if os.path.basename(k)[:10] <= day]
    if before:
        return slurp(before[-1]), "local"
    first = subprocess.run(["git", "-C", root, "log", "--diff-filter=A", "--format=%ct", "--", rel],
                           capture_output=True).stdout.decode().split() if not rel.startswith("..") else []
    if first:
        return "", "new"
    return "", "short" if kept else ""


def keep_list(root, list_path):
    """Keeps today's copy of the list beside the map page when it differs from the last one kept. A list
    that lives uncommitted for weeks has no history in git; these copies are what "changed lately" is
    measured against then. They are local, like the page itself."""
    folder = os.path.join(os.path.dirname(state_path(root)), "lists")
    text = slurp(list_path)
    kept = sorted(glob.glob(os.path.join(folder, "*.md")))
    if not text or (kept and slurp(kept[-1]) == text):
        return
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, datetime.date.today().isoformat() + ".md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    for old in sorted(glob.glob(os.path.join(folder, "*.md")))[:-KEPT]:
        os.remove(old)


def drawing(flow):
    """What a diagram says, in a form two versions can be compared by."""
    if not (flow and flow["nodes"]):
        return None
    return ({n["name"] for n in flow["nodes"]}, {(e["a"], e["b"], e["label"], e["both"]) for e in flow["edges"]})


def list_units(parts, routes, top):
    """{label: (kind, drawing)} for everything on a list that has a name: wings, parts, rooms, routes, and
    the diagram of the whole project under the label ""."""
    out = {"": ("frame", drawing(top["frame"]))}
    for w in top["wings"]:
        out["# " + w.name] = ("wing", drawing(w.flow))
    for p in parts:
        out[p.name] = ("part", drawing(p.flow))
        for c in p.children:
            out[p.name + " / " + c.name] = ("room", drawing(c.flow))
    for r in routes:
        out["~ " + (r["title"] or "")] = ("route", drawing(r))
    return out


def changes(root, list_path, parts, routes, top, wiring, commits, tasks, days, records=()):
    """What changed in the last `days` days, measured: the list as it stands against the list as it stood
    then, the tasks' own histories, and the commits. Nothing here is written by anyone."""
    now = datetime.datetime.now().timestamp()
    since = now - days * 86400
    day = datetime.date.fromtimestamp(since).isoformat()
    out = {"days": days, "since": day, "base": "", "added": [], "removed": [], "redrawn": [], "tasks": [],
           "busy": [], "commits": 0, "short": False}
    text, out["base"] = list_before(root, list_path, since)
    ids = {unit_label(u): wiring.ids[u] for u in wiring.ids if not isinstance(u, Wing)}
    ids.update({"# " + u.name: wiring.ids[u] for u in wiring.ids if isinstance(u, Wing)})
    if text:
        then = list_units(*read_list(text))
        today = list_units(parts, routes, top)
        plain = lambda label: label[2:] if label[:2] in ("# ", "~ ") else label
        for label, (kind, drew) in today.items():
            if label not in then:
                if kind in ("part", "room", "wing"):
                    out["added"].append({"name": plain(label), "to": ids.get(label, ""), "kind": kind})
                elif kind == "route" or drew:
                    out["redrawn"].append({"name": plain(label), "to": "", "kind": kind, "plus": len(drew[0]) if drew else 0,
                                           "minus": 0, "first": True})
                continue
            was = then[label][1]
            if drew != was and drew:
                out["redrawn"].append({"name": plain(label), "to": ids.get(label, ""), "kind": kind,
                                       "plus": len(drew[0] - was[0]) if was else len(drew[0]),
                                       "minus": len(was[0] - drew[0]) if was else 0, "first": not was})
        out["removed"] = [{"name": plain(label), "kind": kind} for label, (kind, _) in then.items()
                          if label not in today and kind in ("part", "room", "wing")]
    for at, t in enumerate(tasks):
        story = [r for r in t["story"]]
        events = []
        for i, row in enumerate(story):
            if row["date"] < day:
                continue
            before = story[i - 1] if i else None
            events.append("done" if row["done"] and not (before and before["done"]) else
                          "more" if row["done"] else "again" if before and before["done"] else
                          "new" if before is None else "step")
        if not story and t["updated"] >= day:
            events.append("done" if t["done"] else "step")
        if events:  # one line a task: where the stretch left it
            out["tasks"].append({"i": at, "what": events[-1]})
    busy = collections.Counter()
    for c in commits:
        if c["when"] >= since:
            out["commits"] += 1
            for name, fs in c["groups"].items():  # the list and the task records are bookkeeping, not work on a part
                if name and any(not f.startswith(records) for f in fs):
                    busy[name] += 1
    out["busy"] = [{"name": name, "n": n} for name, n in busy.most_common(6)]
    out["short"] = len(commits) >= HISTORY and commits[-1]["when"] > since  # the window ends inside the span
    return out


def cmd_doctor(root, parts, t, args):
    """What a machine can tell about the list: out of date, or miswritten. It reports and stops nothing."""
    files = zlist(git(root, "ls-files", "-z"))
    listed = os.path.relpath(args.list_path, root).replace(os.sep, "/")
    _, unmapped = tally(files, parts)
    units = [u for p in parts for u in [p] + p.children]
    label = lambda u: (u.parent.name + " / " if u.parent else "") + u.name
    def on_disk(pat):  # a file git does not track (a local secrets file, say) is not a stale path
        return bool(glob.glob(os.path.join(root, pat.rstrip("/")), recursive=True))
    dead = [(label(u), pat) for u in units for pat, match, _ in u.patterns
            if not any(match(f) for f in files) and not on_disk(pat)]
    names = {u.name for u in units}
    near = []
    flows = [(label(u), u.flow) for u in units if u.flow] + [(t["route"] + " " + (r["title"] or "?"), r) for r in args.routes]
    for where, flow in flows:
        for node in flow["nodes"]:
            if node["name"] in names or node["ext"] or len(node["name"]) < 3:
                continue
            close = difflib.get_close_matches(node["name"], names, n=1, cutoff=0.8)
            if close:
                near.append({"where": where, "box": node["name"], "unit": close[0]})
    level = [p.name for p in parts if p.children and p.flow and p.flow["nodes"]
             and not ({n["name"] for n in p.flow["nodes"]} & {c.name for c in p.children})]
    links, langs = code_links(root, files, parts)
    wiring = Wiring(parts, args.routes, args.top)
    flows += [(t["frame"], args.top["frame"])] if args.top["frame"] else []
    flows += [(w.name, w.flow) for w in args.top["wings"] if w.flow]
    if langs:
        wiring.loose(lifted(links, "top"))
    loose = [{"route": w["where"] or t["frame"], "a": w["edge"]["a"], "b": w["edge"]["b"]}
             for w in wiring.wires if w["edge"].get("loose")]
    wires = wiring.problems()
    gone = wiring.code_gone(root, files, listed)
    old = sorted(((label(u), d, n) for u, (d, n) in aging(root, args.list_path, parts, history(root, parts)).items()
                  if n >= STALE), key=lambda x: -x[2])
    bare = [label(u) for u in units if not u.outside and not (u.flow and u.flow["nodes"])]
    missed = mark_misses([x for x in tasks_shown(root, args.tasks, parts, [])[0] if not x["old"]], t)
    if args.json:
        print(json.dumps({"list": listed, "dead_paths": [{"unit": u, "path": p} for u, p in dead],
                          "unmapped": len(unmapped), "near_names": near, "wrong_level": level, "unbacked": loose,
                          "wiring": dict(wires, code_gone=gone),
                          "stale": [{"unit": u, "drawn": d, "changes_since": n} for u, d, n in old],
                          "undrawn": bare, "marks_missed": missed}, ensure_ascii=False, indent=2))
        return
    zh = t is TEXT["zh"]
    join = "；" if zh else "; "
    print(t["doctor_head"].format(path=listed))
    found = False

    def section(title, rows):
        nonlocal found
        if rows:
            found = True
            print("  " + title.format(n=len(rows)))
            for row in rows[:12]:
                print("      " + row)
            if len(rows) > 12:
                print("      …")
    section(t["doctor_paths"], ["%s  `%s`" % x for x in dead])
    if unmapped:
        found = True
        print("  " + t["doctor_unmapped"].format(n=len(unmapped)))
    section(t["doctor_names"], [t["doctor_name"].format(**x) for x in near])
    section(t["doctor_level"], level)
    section(t["doctor_loose"], ["%s → %s（%s）" % (x["a"], x["b"], x["route"]) if zh else
                                "%s -> %s (%s)" % (x["a"], x["b"], x["route"]) for x in loose])
    # The wiring: do the levels agree with each other?
    arrow = "%s → %s" if zh else "%s -> %s"
    here = lambda where: where or t["frame"]
    if wires["no_frame"]:
        found = True
        print("  " + t["doctor_frame"].format(level=t["level_wings" if args.top["wings"] else "level_parts"]))
    section(t["doctor_wings"], wires["wings_bare"])
    homes = collections.OrderedDict()
    for x in wires["orphans"]:
        homes.setdefault(here(x["on"]), []).append(x["unit"].split(" / ")[-1])
    if homes:
        found = True
        print("  " + t["doctor_orphans"].format(n=len(wires["orphans"])))
        for where, names in homes.items():
            print("      %s%s%s" % (where, "：" if zh else ": ", ("、" if zh else ", ").join(names)))
    section(t["doctor_shelf"], [t["doctor_shelf_row"].format(on=here(x["on"]), box=x["box"]) for x in wires["shelf"]])
    section(t["doctor_open_in"], [t["doctor_open_in_row"].format(unit=x["unit"], other=x["other"],
            label=(t["doctor_said"].format(x=x["label"]) if x["label"] else "")) for x in wires["open_in"]])
    section(t["doctor_open_out"], [t["doctor_open_out_row"].format(**x) for x in wires["open_out"]])
    section(t["doctor_routes_off"], [(arrow + ("（%s）" if zh else " (%s)")) % (x["a"], x["b"], x["route"])
                                     for x in wires["routes_off"]])
    section(t["doctor_pieces"], [t["doctor_pieces_row"].format(on=here(x["on"]), n=x["n"]) for x in wires["pieces"]])
    section(t["doctor_unlabeled"], [here(x["on"]) + ("：" if zh else ": ") + arrow % (x["a"], x["b"])
                                    for x in wires["unlabeled"]])
    section(t["doctor_code"], [t["doctor_code_row"].format(on=here(x["on"]), arrow=arrow % (x["a"], x["b"]),
                                                           name=x["name"], unit=x["unit"]) for x in gone])
    section(t["doctor_stale"], [t["doctor_stale_row"].format(name=u, date=d, n=n) for u, d, n in old])
    section(t["doctor_marks"], missed)
    if not found:
        print("  " + t["doctor_ok"])
    if bare:
        print("  " + t["doctor_bare"].format(n=len(bare)))
    print(t["doctor_limit"])


def mark_misses(tasks, t):
    """Marks that the page cannot draw where the agent meant: a part or room the list does not have, or a
    new or changed box that is not in that unit's diagram."""
    rows = []
    for x in tasks:
        for m in x["marks"]:
            if not m["unit"]:
                rows.append(t["doctor_mark_unit"].format(task=x["name"], name=m["room"] or m["part"]))
            elif m["box"] and m["kind"] != "gone" and not m["drawn"]:
                rows.append(t["doctor_mark_box"].format(task=x["name"], unit=m["unit"], box=m["box"]))
    return rows


def cmd_tasks(root, parts, t, args):
    """The tasks in progress and the ones finished lately: the lines the agent wrote for people in each
    dossier, and the parts touched."""
    tasks, left_out = tasks_shown(root, args.tasks, parts, history(root, parts))
    if args.json:
        print(json.dumps({"tasks": [{"folder": x["id"], "name": x["name"], "finished": x["done"],
                                     "for_people": x["plain"], "now": x["now"],
                                     "needs": x["needs"], "next": x["next"], "done": x["made"], "try": x["try"],
                                     "not_yet": x["left"], "marks": x["marks"], "updated": x["updated"],
                                     "parts": x["rooms"], "finished_long_ago": x["old"],
                                     "changed_since": x["after"], "times_finished": x["times"],
                                     "open_again": x["again"], "story": x["story"]} for x in tasks],
                          "not_listed": left_out,
                          "marks_missed": mark_misses([x for x in tasks if not x["old"]], t)},
                         ensure_ascii=False, indent=2))
        return
    older = [x for x in tasks if x["old"]]
    tasks = [x for x in tasks if not x["old"]]
    doing, done = [x for x in tasks if not x["done"]], [x for x in tasks if x["done"]]
    print(t["tasks_head"].format(n=len(doing)) if doing else t["tasks_none"])
    for x in doing + done:
        if done and x is done[0]:
            print(t["tasks_done_head"].format(n=len(done)))
        notes = [t["task_updated"].format(d=x["updated"] or "?")]
        notes += [t["task_again"]] if x["again"] else []
        notes += [t["task_times"].format(n=x["times"])] if x["done"] and x["times"] > 1 else []
        notes += [t["task_after"].format(n=x["after"])] if x["done"] and x["after"] else []
        print("  %s  [%s]" % (x["name"], t["sep"].join(notes)))
        said = [t["task_now"].format(x=x["now"])] if x["now"] else []
        said += [t["task_needs"].format(x=need) for need in x["needs"]]
        said += [t["task_next"].format(x=x["next"])] if x["next"] else []
        said += [t["task_made"].format(x=line) for line in x["made"]]
        said += [t["task_try"].format(x=x["try"])] if x["try"] else []
        said += [t["task_left"].format(x=line) for line in x["left"]]
        if x["marks"]:
            said.append(t["task_marks"].format(x="  ".join(
                "%s %s" % (t["mark_" + m["kind"]], " / ".join(k for k in (m["unit"] or m["part"], m["box"]) if k))
                for m in x["marks"])))
        for line in said or [t["task_bare"]]:
            print("      " + line)
        if x["rooms"]:
            print("      " + t["task_rooms"].format(x="  ".join("%s %d" % (r["name"] or t["unmapped_changed"], r["n"])
                                                                for r in x["rooms"])))
        print("      " + t["task_folder"].format(x=posixpath.join(x["rel"] or args.tasks, x["home"])))
    if older:
        print(t["tasks_older_head"].format(n=len(older)))
        for x in older:
            print("  %s  [%s]%s" % (x["name"], t["task_updated"].format(d=x["updated"] or "?"),
                                   "  " + t["task_after"].format(n=x["after"]) if x["after"] else ""))
    if left_out:
        print(t["tasks_old"].format(n=left_out))
    for row in mark_misses(tasks, t):
        print("  ! " + row)


def cmd_windows(root, parts, t, args):
    """Every window at work in this project: how it stands, what it was last asked, what it has changed and
    committed, and where two windows get in each other's way."""
    rows, windows = in_flight(root, parts, everywhere=True)
    window_commits(windows, history(root, parts))
    listed = os.path.relpath(args.list_path, root).replace(os.sep, "/")
    tasks_rel = os.path.relpath(args.tasks if os.path.isabs(args.tasks) else os.path.join(root, args.tasks), root)
    hits = clashes(rows, windows, (listed, tasks_rel.replace(os.sep, "/") + "/"))
    known = [w for w in windows if not w["unknown"]]
    if args.json:
        print(json.dumps({"windows": [{"key": w["key"], "tool": w["tool"], "name": w["task"] or w["title"],
                                       "state": w["state"], "last_active": w["last"], "last_asked": w["said"],
                                       "task": w["dossier"], "uncommitted": [{"part": g["name"], "files": g["n"]}
                                                                              for g in grouped(w["rows"], parts)],
                                       "commits": [c["hash"] for c in w["commits"]]} for w in known],
                          "no_window_on_record": sum(len(w["rows"]) for w in windows if w["unknown"]),
                          "clashes": hits}, ensure_ascii=False, indent=2))
        return
    if not known:
        print(t["windows_none"])
        return
    print(t["windows_head"].format(n=len(known)))
    for w in known:
        print("  %s  %s  [%s%s%s%s%s]" % (w["key"], w["task"] or w["title"] or w["tool"], w["tool"], t["sep"],
                                         t["st_" + w["state"]], t["sep"], t["last_at"].format(t=w["last"])))
        if w["said"] and w["said"] != (w["task"] or w["title"]):
            print("      " + t["win_said"].format(x=w["said"]))
        groups = grouped(w["rows"], parts)
        print("      " + (t["sep"].join("%s %d" % (g["name"] or t["unmapped_changed"], g["n"]) for g in groups)
                          if groups else t["win_clean"])
              + ((t["sep"] + t["win_commits"].format(n=len(w["commits"]))) if w["commits"] else ""))
    loose = sum(len(w["rows"]) for w in windows if w["unknown"])
    if loose:
        print("  ?  %s  %s" % (t["unknown_window"], t["files"].format(n=loose)))
    if not hits:
        print(t["clash_none"])
        return
    print(t["clash_head"].format(n=len(hits)))
    for c in hits:
        print("  " + t["clash_" + c["kind"]].format(who="、".join(c["who"]) if t is TEXT["zh"] else ", ".join(c["who"]),
                                                    file=c["file"], part=c["part"] or t["unmapped_changed"],
                                                    where="、".join(c["where"])))


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
    window_commits(windows, commits)
    by_name = {p.name: p for p in parts}
    waiting = collections.Counter((r["part"], r["sub"]) for r in rows)

    age = aging(root, args.list_path, parts, commits)
    wiring = Wiring(parts, args.routes, args.top)
    if langs:
        wiring.loose(lifted(links, "top"))

    def ports(u):
        """What goes in and out of a unit, for the page: the neighbour's name and where a click on it leads."""
        return [{"name": x["other"] if isinstance(x["other"], str) else x["other"].name,
                 "to": "" if isinstance(x["other"], str) else wiring.ids[x["other"]], "dir": x["dir"],
                 "labels": x["labels"], "code": x["code"], "must": x["must"], "met": x["met"], "where": x["where"]}
                for x in wiring.ports(u)]

    def card(u):
        """What the page shows for a part or a sub-part."""
        return {"ports": ports(u), "drawn": age[u][0] if u in age else "", "since": age[u][1] if u in age else 0, "name": u.name, "icon": u.icon, "flow": u.flow, "what": u.what, "sensitive": u.sensitive,
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
    # Tasks in progress, from the journal's dossiers: the lines the agent wrote for people, and where the
    # work landed, which is measured. A window that is writing in a task's dossier is that task's window.
    tasks, tasks_old = tasks_shown(root, args.tasks, parts, commits)
    out_tasks = []
    for task in tasks:
        on = [w for w in windows if w["dossier"] == task["id"]]
        mine = {(r["tree"]["path"], r["file"]): r for w in on for r in w["rows"]
                if not (task["rel"] and r["file"].startswith(task["rel"] + "/"))}
        if task["plain"]:
            for w in on:
                w["task"] = task["name"]  # the window goes by the name the reader knows the task by
        out_tasks.append({"id": task["id"], "name": task["name"], "plain": task["plain"], "now": task["now"],
                          "needs": task["needs"], "next": task["next"], "updated": task["updated"],
                          "finished": task["done"], "made": task["made"], "try": task["try"], "left": task["left"],
                          "marks": task["marks"], "old": task["old"], "after": task["after"], "story": task["story"],
                          "times": task["times"], "again": task["again"],
                          # uncommitted work in the task's files; none is reported when its own record is being
                          # rewritten in the same work, since then the lines are moving along with the code
                          "touched": 0 if task["rel"] and any(
                              task_at(r["file"][len(task["rel"]) + 1:]) == task["id"] for r in rows
                              if r["file"].startswith(task["rel"] + "/"))
                          else sum(1 for r in rows if r["file"] in task["files"]),
                          "days": task["days"], "parts": task["rooms"],
                          "pending": short(grouped(list(mine.values()), parts)), "wins": [w["key"] for w in on]})

    pending = {
        # changed files that no part owns come last, under the name "": the page says they are not on the list
        "parts": [{"part": g["name"], "n": g["n"], "files": g["files"],
                   "sensitive": by_name[g["name"]].sensitive if g["name"] else ""}
                  for g in short(grouped(rows, parts))],
        "windows": [{"key": w["key"], "tool": w["tool"], "title": w["title"], "task": w["task"], "last": w["last"],
                     "where": "、".join(w["where"]) if lang == "zh" else ", ".join(w["where"]),
                     "unknown": w["unknown"], "n": len(w["rows"]), "guessed": w["guessed"], "parts": short(grouped(w["rows"], parts)),
                     "state": w["state"], "said": w["said"],
                     "commits": [{"hash": c["hash"], "subject": c["subject"][:90], "parts": c["parts"]} for c in w["commits"][:6]],
                     "committed": len(w["commits"])}
                    for w in windows],
        "shared": [{"file": r["file"], "who": r["keys"]} for r in rows if len(r["who"]) > 1][:8],
    }

    listed = os.path.relpath(args.list_path, root).replace(os.sep, "/")
    records = tuple(x for x in (os.path.relpath(args.list_path, root).replace(os.sep, "/"),
                                (tasks[0]["rel"] + "/") if tasks and tasks[0]["rel"] else "") if x)
    lately = [changes(root, args.list_path, parts, args.routes, args.top, wiring, commits, tasks, days, records)
              for days in SPANS]
    pending["clashes"] = clashes(rows, windows, records)[:12]
    keep_list(root, args.list_path)
    data = {"project": os.path.basename(root), "lang": lang, "generated": datetime.date.today().isoformat(),
            "lately": lately,
            "files": len(files), "history": len(commits), "recentDays": RECENT_DAYS, "list": listed,
            "parts": out_parts, "commits": out_commits, "pending": pending,
            "links": lifted(links, "top"), "measured": langs, "routes": args.routes,
            "frame": args.top["frame"],
            "wings": [{"name": w.name, "what": w.what, "icon": w.icon, "flow": w.flow, "ports": ports(w),
                       "parts": [parts.index(p) for p in w.parts]} for w in args.top["wings"]],
            "tasks": out_tasks, "tasksOld": tasks_old}
    here = os.path.dirname(os.path.abspath(__file__))
    page = open(os.path.join(here, "map_template.html"), encoding="utf-8").read()
    # Every "<" in the data is written as \u003c. A commit subject holding both "<!--" and "<script" would
    # otherwise put the browser in a state where the page's own </script> no longer ends the script.
    page = page.replace("__PROJECT__", data["project"]).replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"))
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


LIST_FORMAT = """\
the parts list (docs/parts.md, PARTS.md or .bearings/parts.md), every keyword it understands:
  # Wing            groups the parts under it        (with one `#` title on top, every level sits one deeper)
  ## Part           first plain line: what it is for
  ### Room          a room inside the part above; same fields as a part
  - `dir/` `a/*.py` paths it owns: a trailing / owns the folder, * stops at a slash, ** crosses them
  图标：name        or  Icon: name        mic speaker phone play book search plug user card database mail
                                          home grid spark layout lang cloud flask note lock box
  敏感：why         or  Sensitive: why    drawn hatched
  外来：what        or  Vendored: what    code written elsewhere: dashed, counted apart
  规矩：rule（source，date）  or  Rule: ...
  ```flow           how the level it stands at works, drawn with the boxes of the level below:
                      before the first heading   the whole project    boxes: the wings (the parts, with no wings)
                      under a `# Wing` heading   that wing            boxes: its parts
                      inside a part              that part            boxes: its rooms (its steps, with no rooms)
                      inside a room              that room            boxes: its steps
  ```flow Title     outside every part: a route, how one thing travels through the project (boxes: parts)
    A -> B: label     an arrow, and what travels along it;  <->  points both ways
    A -> B: label `Name`   also what the code calls that (a type, a function, an endpoint); doctor checks it exists
    Name | note | icon | 外部     a box;  外部 / external marks a service outside the project; icon user, a person
    Name | note       with no arrow: a box that is not on the path at run time; the note says whom it serves
    a box named exactly like a wing, part or room is a door to it
  under a `# Wing` heading, before its first part: one plain line on what the wing is for, and 图标：/ Icon:

a task's lines for people (the `## For People` section of its record, docs/tasks/<task>.md; in older
projects docs/tasks/<task>/handoff.md):
  名字：/ Name:  现在：/ Now:  等你：/ Needs you: (one line each)  下一步：/ Next:     where the task stands
  做成了：/ Done:  怎么试：/ Try:  还没做：/ Not yet:                     what its last finished step came to
  新增：/ Added:  改了：/ Changed:  去掉：/ Removed:   Part / Box: one sentence     (Part / Room / Box for a room)
    marks that box on the part's flow diagram; the names must be the ones on the list
"""


def main():
    ap = argparse.ArgumentParser(prog="bearings", description=__doc__.split("\n\n")[0], epilog=LIST_FORMAT,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="parts list, relative to the repo root (default: docs/parts.md)")
    ap.add_argument("--tasks", default=TASKS_DIR, metavar="DIR",
                    help="folder of task dossiers kept by the implementation-journal skill (default: docs/tasks)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("tasks", help="the tasks in progress and finished lately: what the agent wrote for people, and the parts touched")
    j.add_argument("--json", action="store_true")
    v = sub.add_parser("windows", help="every Claude Code and Codex window at work here: how it stands, what it changed, where two collide")
    v.add_argument("--json", action="store_true")
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
    d = sub.add_parser("doctor", help="check the list against the code: stale paths, misspelt boxes, aged diagrams")
    d.add_argument("--json", action="store_true")
    for cmd in (c, w):
        cmd.add_argument("--no-windows", action="store_true",
                         help="do not read Claude Code and Codex session records to tell windows apart")
    args = ap.parse_args()

    root = repo_root()
    parts, args.list_path, args.routes, args.top = load_parts(root, args.file)
    if not parts:
        raise SystemExit(TEXT["zh"]["no_parts"].format(files=" / ".join(PARTS_FILES)) + "\n"
                         + TEXT["en"]["no_parts"].format(files=" / ".join(PARTS_FILES)))
    t = TEXT[language(parts)]
    {"parts": cmd_parts, "check": cmd_check, "web": cmd_web, "links": cmd_links, "doctor": cmd_doctor,
     "tasks": cmd_tasks, "windows": cmd_windows}[args.cmd](root, parts, t, args)


if __name__ == "__main__":
    main()
