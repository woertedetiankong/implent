#!/usr/bin/env python3
"""PostToolUse hook body for the implementation-journal skill: what earlier tasks decided about a file,
given to the session the first time it edits that file.

The session-start line asks a session to look these decisions up before it changes code. A session
that is busy does not always do it, and then a rule the user set months ago is broken without anyone
noticing. So after the first Edit or Write to a file in a session, this prints the `Decided` lines of
every task record whose work changed that file (the skill's scripts/decided.py does the looking up).
It only tells: the edit has already been made and nothing is undone or refused.

Each record is given once in a session, and each file is looked up once. What has been given is kept
in a small file per session in the machine's temporary folder, never in the project. A compaction
empties it (session_start.py calls `forget`), since the session no longer has those lines; a record
the session-start hook has just printed whole is marked as given (`remember`).

Reads stdin JSON, git and the records under docs/tasks/ of the repository the edited file is in.
stdout is the JSON form that adds context for the model; plain text from a tool hook is not shown to it.
"""
import importlib.util
import json
import os
import re
import sys
import tempfile
import time

TASKS = "docs/tasks"
MAX_RECORDS = 4   # records given for one file; the rest are named
MAX_LINES = 14    # lines of one record's Decided (the validator warns past as many)
KEPT_DAYS = 3     # how long a session's note of what it was given is kept


def state_path(session, agent=""):
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", "%s%s" % (session, "-" + agent if agent else ""))[:120]
    return os.path.join(tempfile.gettempdir(), "implementation-journal", name + ".json")


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        state = {}
    return {"files": list(state.get("files") or []), "records": list(state.get("records") or [])}


def save(path, state):
    folder = os.path.dirname(path)
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(path + ".tmp", path)
        for name in os.listdir(folder):   # notes of sessions long over
            other = os.path.join(folder, name)
            if time.time() - os.path.getmtime(other) > KEPT_DAYS * 86400:
                os.remove(other)
    except OSError:
        pass


def forget(session):
    """The session lost what it was given (a compaction): give it again at the next edit."""
    folder = os.path.dirname(state_path(session))
    prefix = os.path.basename(state_path(session))[:-5]
    try:
        for name in os.listdir(folder):
            if name == prefix + ".json" or name.startswith(prefix + "-"):
                os.remove(os.path.join(folder, name))
    except OSError:
        pass


def remember(session, root, record_ids):
    """These records were just printed whole to the session: do not give their lines again."""
    if not session or not record_ids:
        return
    path = state_path(session)
    state = load(path)
    state["records"] = sorted(set(state["records"]) | {root + "::" + r for r in record_ids})
    save(path, state)


def repo_of(path):
    """The folder of the repository a file is in: the nearest one above it that holds a .git."""
    folder = os.path.dirname(path)
    while True:
        if os.path.exists(os.path.join(folder, ".git")):
            return folder
        up = os.path.dirname(folder)
        if up == folder:
            return ""
        folder = up


def lookup_script():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "skills", "implementation-journal", "scripts", "decided.py")


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    given = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    target, session = given.get("file_path") or given.get("notebook_path"), payload.get("session_id")
    if not target or not session:   # without a session there is no telling a first edit from a tenth
        return
    target = os.path.realpath(os.path.join(payload.get("cwd") or os.getcwd(), target))
    root = repo_of(target)
    if not root or not os.path.isdir(os.path.join(root, *TASKS.split("/"))):
        return
    rel = os.path.relpath(target, root).replace(os.sep, "/")
    if (rel + "/").startswith(TASKS + "/"):
        return
    where = state_path(session, str(payload.get("agent_id") or ""))
    state = load(where)
    if target in state["files"]:
        return
    script = lookup_script()
    try:
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location("decided", script)
        decided = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(decided)
        _, found, _ = decided.look_up(root, TASKS, [rel])
    except Exception:   # a hook that fails must not get in the way of the edit
        return
    state["files"].append(target)
    fresh = [(r, mine) for r, mine in found if r["decided"] and root + "::" + r["id"] not in state["records"]]
    state["records"] += [root + "::" + r["id"] for r, _ in fresh[:MAX_RECORDS]]
    save(where, state)
    if not fresh:
        return
    out = ["implementation-journal: earlier tasks decided things about %s that the code does not show: what the "
           "user settled, limits from outside, guesses. This is the first edit to that file in this session, so "
           "they are given here, once. Keep to them unless the user now decides otherwise; where two disagree, "
           "the newer record wins. If the change being made goes against one, tell the user which task it came "
           "from." % rel]
    for r, mine in fresh[:MAX_RECORDS]:
        out += ["", "## %s (%s, updated %s) %s" % (r["name"], "finished" if r["done"] else "open",
                                                   r["updated"] or "unknown", r["file"])]
        if any(f in r["was"] for f in mine):
            out.append(decided.changed_line(r, mine))
        out += r["decided"][:MAX_LINES]
        if len(r["decided"]) > MAX_LINES:
            out.append("(%d more lines under Decided in that record)" % (len(r["decided"]) - MAX_LINES))
    if len(fresh) > MAX_RECORDS:
        out += ["", "%d older records also changed this file: %s. `%s \"%s\" --all %s` prints what they decided." % (
            len(fresh) - MAX_RECORDS, ", ".join(r["name"] for r, _ in fresh[MAX_RECORDS:]),
            "python" if os.name == "nt" else "python3", script, rel)]
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "\n".join(out)}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
