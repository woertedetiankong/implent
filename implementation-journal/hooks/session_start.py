#!/usr/bin/env python3
"""SessionStart hook body for the implementation-journal skill.

Several sessions can have tasks open in one repo at the same time, so there is
no single "next session" file to inject. Each task has its own record under
docs/tasks/: one file, <date>-<slug>.md, open until its header says Complete.
A repo that started with the earlier form of the skill has a folder per task
instead. Such a task is open while its handoff.md does not say Complete and the
folder has a next-session.md, or the handoff has lines for people (a name and
where it stands), or it changed in the last STALE_DAYS. Apart from the restart
entry that is the rule the bearings map goes by (`tasks_shown` in bearings.py),
so the list a session is given and the map a person looks at name the same
tasks. An old project has many folders that were never marked Complete and say
nothing to a person; like the map, this leaves them out.

The records are looked for in docs/tasks/ of the folder the session started in,
and failing that of each folder above it up to the top of the repository, so a
session started in a subfolder is told the same.

- No open task: print nothing, unless the repo has finished tasks (see below).
- One open task: print its record (or, for an older folder, its restart
  entry), so resuming needs no pasting.
- Several: print a short list and tell the session to settle which task it is
  for before touching any record.
- A repo that still has only the older repo-level docs/tasks/NEXT-SESSION.md
  gets that file printed, exactly as before.

A record says how things stood when it was last written: "the run is in progress, do not restart it"
stays on the page long after the run ended. So every record is shown with the day it last changed and
how long ago that was, and one that has not changed in more than STALE_DAYS is not printed and does not
count as open here: it gets one line saying where it is. The day is the later of the `updated:` in its
header and the day the file itself last changed (its last commit when git has it unchanged, so a fresh
clone does not make every record look new; otherwise when it was last written).

A finished task's record is no longer shown to anyone, and the decisions in it are not in the code.
So when the repo has finished records, every output ends with one line that says how to look them up
for the files about to be changed (the skill's scripts/decided.py). That line is all a session with no
open task gets.

After a compaction (source == "compact") it also reminds the session to bring
its record up to date, since compaction is the context loss a planned pause
cannot catch.

Reads stdin JSON and journal files only; writes nothing in the project. stdout of a
SessionStart hook is added to the session's context. One thing is kept outside the project, in the
machine's temporary folder: which records this session has been given, so that decided_on_edit.py
beside this file gives a record's decisions once (see there).
"""
import datetime
import json
import os
import re
import subprocess
import sys

MAX_LISTED = 6
PYTHON = "python" if os.name == "nt" else "python3"  # what this machine calls it, for a command the session is shown
STALE_DAYS = 30  # a record that has not changed in longer than this is named, not printed
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


def git(folder, *args):
    try:
        out = subprocess.run(["git", "-C", folder, *args], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def changed_on(path):
    """The day a file last changed: its last commit when git has it as committed, otherwise the day it
    was last written. None for a file that is not there."""
    if not os.path.isfile(path):
        return None
    folder, name = os.path.split(path)
    status = git(folder, "status", "--porcelain", "--", name)
    if status is not None and not status.strip():
        at = (git(folder, "log", "-1", "--format=%at", "--", name) or "").strip()
        if at.isdigit():  # nothing for a file git ignores: that one falls through to the file's own date
            return datetime.date.fromtimestamp(int(at))
    try:
        return datetime.date.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return None


def last_moved(written, *paths):
    """(the day a record last changed as YYYY-MM-DD, how many days ago that was). `written` is the date
    its header gives, if any. ("", None) when nothing says."""
    days = [d for d in map(changed_on, paths) if d]
    try:
        days.append(datetime.date.fromisoformat(written))
    except ValueError:
        pass
    if not days:
        return "", None
    return max(days).isoformat(), max((datetime.date.today() - max(days)).days, 0)


def ago(day, age):
    if age is None:
        return "last changed: unknown"
    return "last changed %s, %s" % (day, "today" if age == 0 else "1 day ago" if age == 1 else "%d days ago" % age)


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


def decided_note(tasks_dir, cwd):
    """One line for a repo that has finished tasks: how to see what they decided about a file. Nothing when
    there are none, or when the lookup script is not where this hook expects it."""
    done = 0
    for name in os.listdir(tasks_dir):
        path = os.path.join(tasks_dir, name)
        if os.path.isdir(path):
            meta = frontmatter(read(os.path.join(path, "handoff.md")))
        elif name.lower().endswith(".md") and name.lower() not in NOT_RECORDS:
            meta = frontmatter(read(path))
        else:
            continue
        done += meta.get("status", "").lower().startswith("complete")
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(os.path.dirname(here), "skills", "implementation-journal", "scripts", "decided.py")
    if not done or not os.path.isfile(script):
        return ""
    return ("implementation-journal: %d finished task%s in this repo %s decisions the code does not show "
            "(what the user settled, limits from outside). Before changing code here, see the ones made about "
            "those files: `%s \"%s\" <files or folders>`." % (
                done, "" if done == 1 else "s", "holds" if done == 1 else "hold", PYTHON, script))


def find_tasks(start):
    """docs/tasks/ of the folder a session started in, or of the nearest folder above it up to the top of
    the repository (the folder that holds .git). Outside a repository only the start folder is looked in:
    there is nothing to say where the project ends. None when there is none."""
    start = os.path.abspath(start)
    top = start
    while not os.path.exists(os.path.join(top, ".git")):
        if os.path.dirname(top) == top:
            top = start   # not in a repository
            break
        top = os.path.dirname(top)
    folder = start
    while True:
        tasks = os.path.join(folder, "docs", "tasks")
        if os.path.isdir(tasks):
            return tasks
        if folder == top:
            return None
        folder = os.path.dirname(folder)


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
            day, age = last_moved(updated.group(0) if updated else "", dossier)
            found.append({"name": name[:-3], "entry": dossier, "updated": day, "age": age,
                          "state": people_line(record, "Now|现在"), "people": people_name(record), "whole": True})
            continue
        # an older folder: open until its handoff says Complete. Its restart entry is printed when it has
        # one; a handoff is too long to print and is pointed to instead.
        handoff_path = os.path.join(dossier, "handoff.md")
        handoff = read(handoff_path)
        meta = frontmatter(handoff)
        if not handoff or meta.get("status", "").lower().startswith("complete"):
            continue
        entry = entry_in(dossier)
        updated = re.search(r"\d{4}-\d{2}-\d{2}", meta.get("updated", "") or name)
        state = re.search(r"^Current state:\s*(.+)$", read(entry), re.I | re.M) if entry else None
        day, age = last_moved(updated.group(0) if updated else "", entry or handoff_path, handoff_path)
        plain = people_name(handoff) and people_line(handoff, "Now|现在")
        if not entry and not plain and (age is None or age > STALE_DAYS):
            continue
        found.append({
            "name": name,
            "entry": entry or handoff_path,
            "updated": day,
            "age": age,
            "state": state.group(1).strip() if state else people_line(handoff, "Now|现在"),
            "people": people_name(handoff),
            "whole": False,
            "pointed": not entry,
        })
    found.sort(key=lambda t: t["updated"], reverse=True)
    return found


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    cwd = payload.get("cwd") or os.getcwd()
    tasks_dir = find_tasks(cwd)
    if not tasks_dir:
        return
    legacy = os.path.join(tasks_dir, LEGACY_NAME)
    legacy_day, legacy_age = last_moved("", legacy)
    every = open_tasks(tasks_dir)
    tasks = [t for t in every if t["age"] is None or t["age"] <= STALE_DAYS]
    old = [t for t in every if t not in tasks]
    has_legacy = os.path.isfile(legacy) and legacy_age <= STALE_DAYS
    old_legacy = os.path.isfile(legacy) and not has_legacy
    note = decided_note(tasks_dir, cwd)

    def rel(path):
        return os.path.relpath(path, cwd)

    session, given = payload.get("session_id"), []
    try:
        sys.dont_write_bytecode = True   # nothing is left in the plugin's own folder either
        import decided_on_edit as once
    except ImportError:
        once = None
    if once and session and payload.get("source") in ("compact", "clear"):
        once.forget(session)   # what the session was given is gone from its context

    out = []
    if payload.get("source") == "compact" and (every or os.path.isfile(legacy)):
        out += [COMPACT_NOTE, ""]
    def row(task):
        known = ', "%s" to the user' % task["people"] if task["people"] else ""
        kind = "record" if task["whole"] else "handoff" if task.get("pointed") else "entry"
        line = f"- {task['name']}{known} ({ago(task['updated'], task['age'])}): {kind} `{rel(task['entry'])}`"
        return line + (" — " + task["state"][:160] if task["state"] else "")

    if has_legacy and all(t.get("pointed") for t in tasks):
        # the form before task folders had restart entries of their own: the repo-level entry is the
        # restart entry, and usually it is about one of these folders
        out += [f"implementation-journal restart entry ({rel(legacy)}), {ago(legacy_day, legacy_age)}:", "",
                read(legacy).rstrip()]
        if tasks:
            out += ["", "Task folders in this repo not marked finished (the entry above may be about one of them):"]
            out += [row(t) for t in tasks[:MAX_LISTED]]
    elif len(tasks) == 1 and not has_legacy:
        task = tasks[0]
        known = ', which the user knows as "%s"' % task["people"] if task["people"] else ""
        out.append(f"implementation-journal: one task is open in this repo ({task['name']}{known}).")
        if task.get("pointed"):
            out.append(f"It is kept in the older folder form and has no restart entry. Its handoff is "
                       f"`{rel(task['entry'])}`, {ago(task['updated'], task['age'])}"
                       + (": " + task["state"][:300] if task["state"] else "."))
        else:
            what = "Its record" if task["whole"] else "Its restart entry"
            out += [f"{what} ({rel(task['entry'])}), {ago(task['updated'], task['age'])}:", "",
                    read(task["entry"]).rstrip()]
        given = [task["name"]] if task["whole"] else []
    elif tasks:
        total = len(tasks) + (1 if has_legacy else 0)
        out.append(f"implementation-journal: {total} tasks are open in this repo. "
                   "This session may continue one of them or start something new.")
        out += [row(t) for t in tasks[:MAX_LISTED]]
        if len(tasks) > MAX_LISTED:
            out.append(f"- and {len(tasks) - MAX_LISTED} older open tasks under docs/tasks/")
        if has_legacy:
            out.append(f"- an older repo-level entry ({ago(legacy_day, legacy_age)}): `{rel(legacy)}`")
        out += ["",
                "If the user's first message makes clear which task this session is for, read that task's "
                "record before anything else. If it does not, ask which one, or whether this is new work. "
                "Leave the other tasks' records alone: other sessions may be working from them."]
    if old or old_legacy:
        count = len(old) + (1 if old_legacy else 0)
        out += [""] if out and out[-1] else []
        out.append("implementation-journal: %d record%s in this repo %s never marked finished but %s not changed "
                   "in over %d days, so %s not shown here. What such a record calls running, waiting or next was "
                   "true on the day it was written and may no longer be." % (
                       count, "" if count == 1 else "s", "was" if count == 1 else "were",
                       "has" if count == 1 else "have", STALE_DAYS, "it is" if count == 1 else "they are"))
        for task in old[:MAX_LISTED]:
            known = ', "%s" to the user' % task["people"] if task["people"] else ""
            out.append(f"- {task['name']}{known} ({ago(task['updated'], task['age'])}): `{rel(task['entry'])}`")
        if len(old) > MAX_LISTED:
            out.append(f"- and {len(old) - MAX_LISTED} more under docs/tasks/")
        if old_legacy:
            out.append(f"- an older repo-level entry ({ago(legacy_day, legacy_age)}): `{rel(legacy)}`")
        out.append("If the user asks to carry on with one of these, read it then, as an account of that day.")
    if note:
        out += ["", note] if out else [note]
    if out:
        print("\n".join(out))
    if once and given:
        once.remember(session, os.path.realpath(os.path.dirname(os.path.dirname(tasks_dir))), given)


if __name__ == "__main__":
    main()
