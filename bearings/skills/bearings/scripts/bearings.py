#!/usr/bin/env python3
"""bearings: show a project as named parts, and which parts a piece of work touched.

A project lists its parts in docs/parts.md (a heading per part, the paths it owns as
backticked bullets, optionally a flow diagram). This script only reads and reports;
it never tells anyone what to change or leave alone.

  bearings.py parts                        list the parts, their file counts and unmapped files
  bearings.py check [--since REF | --commit REV] [--json]
                                           which parts the uncommitted work (or one past commit) touched
  bearings.py web [--out FILE] [--open]    write the project map as one HTML page

Read-only towards the project: the only file it writes is the map page, under the git dir
unless --out says otherwise. Python 3 standard library only.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import webbrowser

PARTS_FILES = ("docs/parts.md", "PARTS.md", ".claude/parts.md")
SENSITIVE_RE = re.compile(r"^\s*(?:敏感|Sensitive)\s*[:：]\s*(.+)$", re.I)
ICON_RE = re.compile(r"^\s*(?:图标|Icon)\s*[:：]\s*([a-z-]+)\s*$", re.I)
FLOW_OPEN_RE = re.compile(r"^\s*```\s*flow\s*$", re.I)
FLOW_EDGE_RE = re.compile(r"^\s*(.+?)\s*(<->|->)\s*(.+?)\s*(?:[:：]\s*(.*))?$")
EXTERNAL_WORDS = ("外部", "external")
RULE_RE = re.compile(r"^\s*(?:规矩|Rule)\s*[:：]\s*(.+)$", re.I)
HISTORY = 200   # commits read for the map
RECENT_DAYS = 30
SHOWN = 80      # commits handed to the map page, which filters and trims them

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
    def __init__(self, name):
        self.name, self.what, self.sensitive, self.patterns, self.rules = name, "", "", [], []
        self.group, self.icon, self.flow = "", "", None


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


def load_parts(root, explicit=None):
    candidates = [explicit] if explicit else list(PARTS_FILES)
    for rel in candidates:
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if os.path.isfile(path):
            break
    else:
        return None, None
    parts, cur, group, in_flow = [], None, "", False
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if in_flow:
            if line.strip().startswith("```"):
                in_flow = False
            else:
                flow_line(cur.flow, line)
            continue
        if cur is not None and FLOW_OPEN_RE.match(line):
            in_flow, cur.flow = True, cur.flow or {"nodes": [], "edges": []}
            continue
        if line.startswith("# "):  # a top-level heading groups the parts under it
            group, cur = line[2:].strip(), None
            continue
        if line.startswith("## "):
            cur = Part(line[3:].strip())
            cur.group = group
            parts.append(cur)
            continue
        if cur is None or not line.strip():
            continue
        sens = SENSITIVE_RE.match(line)
        rule = RULE_RE.match(line)
        icon = ICON_RE.match(line)
        if icon:
            cur.icon = icon.group(1).lower()
        elif sens:
            cur.sensitive = sens.group(1).strip()
        elif rule:
            cur.rules.append(rule.group(1).strip())
        elif line.lstrip().startswith(("- ", "* ")):
            for pat in re.findall(r"`([^`]+)`", line):
                cur.patterns.append((pat, compile_pattern(pat), literal_len(pat)))
        elif not cur.what and not line.startswith(("#", ">")):
            cur.what = line.strip()
    return parts, path


def owner(path, parts):
    best, best_len = None, -1
    for part in parts:
        for _, match, length in part.patterns:
            if length > best_len and match(path):
                best, best_len = part, length
    return best


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


# Commands -----------------------------------------------------------------

def cmd_parts(root, parts, t, args):
    files = zlist(git(root, "ls-files", "-z"))
    counts, unmapped = {p.name: 0 for p in parts}, []
    for f in files:
        part = owner(f, parts)
        if part:
            counts[part.name] += 1
        else:
            unmapped.append(f)
    if args.json:
        print(json.dumps({"parts": [{"name": p.name, "what": p.what, "sensitive": p.sensitive,
                                     "files": counts[p.name], "paths": [x[0] for x in p.patterns]} for p in parts],
                          "unmapped": unmapped}, ensure_ascii=False, indent=2))
        return
    col = max(width(p.name) for p in parts) + 2
    print(t["parts_head"].format(n=len(parts), files=len(files)))
    for p in parts:
        mark = "  [" + t["sensitive"].format(why=p.sensitive) + "]" if p.sensitive else ""
        print("  " + pad(p.name, col) + pad(t["files"].format(n=counts[p.name]), 12) + p.what + mark)
    empty = [p.name for p in parts if not counts[p.name]]
    if empty:
        print(t["empty_part"].format(names="、".join(empty)))
    if unmapped:
        print(t["unmapped"].format(n=len(unmapped)))
        for f in unmapped[: None if args.all else 40]:
            print("  " + f)
    else:
        print(t["unmapped_none"])


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


def history(root, parts):
    """The last HISTORY commits, each with the parts it changed."""
    raw = git(root, "log", "-n", str(HISTORY), "--no-merges", "--date=short", "--name-only",
              "--format=%x01%h%x02%ad%x02%s").decode("utf-8", "replace")
    commits = []
    for block in raw.split("\x01")[1:]:
        head, _, rest = block.partition("\n")
        rev, date, subject = (head.split("\x02") + ["", ""])[:3]
        groups = {}
        for f in filter(None, (line.strip() for line in rest.splitlines())):
            part = owner(f, parts)
            groups.setdefault(part.name if part else "", []).append(f)
        commits.append({"hash": rev, "date": date, "subject": subject, "groups": groups})
    return commits


def cmd_web(root, parts, t, args):
    lang = language(parts)
    files = zlist(git(root, "ls-files", "-z"))
    counts = {p.name: 0 for p in parts}
    for f in files:
        part = owner(f, parts)
        if part:
            counts[part.name] += 1
    commits = history(root, parts)
    cutoff = (datetime.date.today() - datetime.timedelta(days=RECENT_DAYS)).isoformat()
    touching = {p.name: [c for c in commits if p.name in c["groups"]] for p in parts}
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
        out_parts.append({"name": p.name, "group": p.group, "icon": p.icon, "flow": p.flow, "what": p.what, "sensitive": p.sensitive, "rules": p.rules,
                          "paths": [x[0] for x in p.patterns], "files": counts[p.name],
                          "recent": sum(1 for c in mine if c["date"] >= cutoff),
                          "last": mine[0]["date"] if mine else "", "commits": len(mine), "together": together[:4]})
    out_commits = [{"hash": c["hash"], "date": c["date"], "subject": c["subject"],
                    "parts": [{"name": n or "?", "n": len(fs), "files": fs[:6]} for n, fs in
                              sorted(c["groups"].items(), key=lambda kv: -len(kv[1]))]} for c in commits[:SHOWN]]

    class Now:  # what is uncommitted, through the same code path as `check --json`
        since = commit = None
        json = True
        files = False
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_check(root, parts, t, Now)
    pending = json.loads(buf.getvalue())
    for row in pending["parts"]:
        row["n"], row["files"] = len(row["files"]), row["files"][:6]

    data = {"project": os.path.basename(root), "lang": lang, "generated": datetime.date.today().isoformat(),
            "files": len(files), "history": len(commits), "recentDays": RECENT_DAYS,
            "parts": out_parts, "commits": out_commits, "pending": pending}
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
    args = ap.parse_args()

    root = repo_root()
    parts, _ = load_parts(root, args.file)
    if not parts:
        raise SystemExit(TEXT["zh"]["no_parts"].format(files=" / ".join(PARTS_FILES)) + "\n"
                         + TEXT["en"]["no_parts"].format(files=" / ".join(PARTS_FILES)))
    t = TEXT[language(parts)]
    {"parts": cmd_parts, "check": cmd_check, "web": cmd_web}[args.cmd](root, parts, t, args)


if __name__ == "__main__":
    main()
