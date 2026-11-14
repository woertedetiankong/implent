#!/usr/bin/env python3
"""SessionStart hook body for the implementation-journal skill.

Several sessions can have tasks open in one repo at the same time, so there is
no single "next session" file to inject. Each task has its own record under
docs/tasks/: one file, <date>-<slug>.md, open until its header says Complete.
A repo that started with the earlier form of the skill has a folder per task
instead; such a task is open while the folder has a next-session.md and its
handoff.md is not marked Complete.

- No open task: print nothing.
- One open task: print its record (or, for an older folder, its restart
  entry), so resuming needs no pasting.
- Several: print a short list and tell the session to settle which task it is
  for before touching any record.
- A repo that still has only the older repo-level docs/tasks/NEXT-SESSION.md
  gets that file printed, exactly as before.

After a compaction (source == "compact") it also reminds the session to bring
its record up to date, since compaction is the context loss a planned pause
cannot catch.

Reads stdin JSON and journal files only; writes nothing. stdout of a
SessionStart hook is added to the session's context.
"""
import json
import os
import re
import sys

MAX_LISTED = 6
ENTRY_NAME = "next-session.md"
LEGACY_NAME = "NEXT-SESSION.md"
NOT_RECORDS = ("next-session.md", "index.md", "readme.md")
COMPACT_NOTE = (
    "Context was just compacted. If this session was working on a task that has a record under "
    "docs/tasks/ and things have moved since the record was last updated, bring the record up to "
    "date per the implementation-journal skill before continuing."
)


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def frontmatter(text):
    lines = text.splitlines()
    fields = {}
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                return fields
            key, sep, value = line.partition(":")
            if sep:
                fields[key.strip()] = value.strip()
    return {}


def people_line(record, keys):
    """One line of a record's For People section, by its key. `Name:` is what a person knows the task by:
    the bearings map shows that name and tells them to ask for the task by it, so the session has to be
    able to match it."""
    section = re.search(r"^##[ \t]+(?:For People|给人看的?)[ \t]*$(.*?)(?=^##[ \t]|\Z)", record, re.I | re.M | re.S)
    line = section and re.search(r"^\s*(?:[-*]\s+)?(?:%s)\s*[:：]\s*(.+?)\s*$" % keys, section.group(1), re.I | re.M)
    return line.group(1) if line else ""


def people_name(record):
    return people_line(record, "Name|名字")


def entry_in(dossier):
    try:
        names = os.listdir(dossier)
    except OSError:
        return None
    for name in names:
        if name.lower() == ENTRY_NAME:
            return os.path.join(dossier, name)
    return None


def open_tasks(tasks_dir):
    found = []
    for name in sorted(os.listdir(tasks_dir)):
        dossier = os.path.join(tasks_dir, name)
        if not os.path.isdir(dossier):
            # a one-file record: open until its header says Complete
            if not name.lower().endswith(".md") or name.lower() in NOT_RECORDS:
                continue
            record = read(dossier)
            meta = frontmatter(record)
            if "status" not in meta or meta["status"].lower().startswith("complete"):
                continue
            updated = re.search(r"\d{4}-\d{2}-\d{2}", meta.get("updated", "") or name)
            found.append({"name": name[:-3], "entry": dossier, "updated": updated.group(0) if updated else "",
                          "state": people_line(record, "Now|现在"), "people": people_name(record), "whole": True})
            continue
        entry = entry_in(dossier)
        if not entry:
            continue
        handoff = read(os.path.join(dossier, "handoff.md"))
        meta = frontmatter(handoff)
        if meta.get("status", "").lower().startswith("complete"):
            continue
        updated = re.search(r"\d{4}-\d{2}-\d{2}", meta.get("updated", "") or name)
        state = re.search(r"^Current state:\s*(.+)$", read(entry), re.I | re.M)
        found.append({
            "name": name,
            "entry": entry,
            "updated": updated.group(0) if updated else "",
            "state": state.group(1).strip() if state else "",
            "people": people_name(handoff),
            "whole": False,
        })
    found.sort(key=lambda t: t["updated"], reverse=True)
    return found


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    cwd = payload.get("cwd") or os.getcwd()
    tasks_dir = os.path.join(cwd, "docs", "tasks")
    if not os.path.isdir(tasks_dir):
        return
    legacy = os.path.join(tasks_dir, LEGACY_NAME)
    has_legacy = os.path.isfile(legacy)
    tasks = open_tasks(tasks_dir)
    if not tasks and not has_legacy:
        return

    def rel(path):
        return os.path.relpath(path, cwd)

    out = []
    if payload.get("source") == "compact":
        out += [COMPACT_NOTE, ""]
    if not tasks:
        out += [f"implementation-journal restart entry ({rel(legacy)}):", "", read(legacy).rstrip()]
    elif len(tasks) == 1 and not has_legacy:
        task = tasks[0]
        known = ', which the user knows as "%s"' % task["people"] if task["people"] else ""
        what = "Its record" if task["whole"] else "Its restart entry"
        out += [f"implementation-journal: one task is open in this repo ({task['name']}{known}).",
                f"{what} ({rel(task['entry'])}):", "", read(task["entry"]).rstrip()]
    else:
        total = len(tasks) + (1 if has_legacy else 0)
        out.append(f"implementation-journal: {total} tasks are open in this repo. "
                   "This session may continue one of them or start something new.")
        for task in tasks[:MAX_LISTED]:
            known = ', "%s" to the user' % task["people"] if task["people"] else ""
            kind = "record" if task["whole"] else "entry"
            line = f"- {task['name']}{known} (updated {task['updated'] or 'unknown'}): {kind} `{rel(task['entry'])}`"
            if task["state"]:
                line += " — " + task["state"][:160]
            out.append(line)
        if len(tasks) > MAX_LISTED:
            out.append(f"- and {len(tasks) - MAX_LISTED} older open tasks under docs/tasks/")
        if has_legacy:
            out.append(f"- an older repo-level entry: `{rel(legacy)}`")
        out += ["",
                "If the user's first message makes clear which task this session is for, read that task's "
                "record before anything else. If it does not, ask which one, or whether this is new work. "
                "Leave the other tasks' records alone: other sessions may be working from them."]
    print("\n".join(out))


if __name__ == "__main__":
    main()
