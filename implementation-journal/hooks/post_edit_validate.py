#!/usr/bin/env python3
"""PostToolUse hook body for the implementation-journal skill.

After an Edit or Write to a Markdown file under docs/tasks/, runs the skill's
scripts/validate_journal.py on that file and feeds its ERROR lines back to the
session at once: a PostToolUse hook that exits 2 has its stderr shown to the
model, and the edit itself is not blocked. The validator passes over a Markdown
file that is not a task record, so other files kept in that folder are left
alone. Warnings are left to the check before finishing, so drafting is not
nagged mid-flow.

The path is compared with forward slashes: on Windows the tool gives it with
backslashes. Repos that keep task records elsewhere: change TASKS below.
"""
import json
import os
import subprocess
import sys

TASKS = "/docs/tasks/"


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    given = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    target = given.get("file_path") or ""
    spelt = target.replace("\\", "/")
    if TASKS not in spelt or not spelt.lower().endswith(".md") or not os.path.isfile(target):
        return 0
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(os.path.dirname(here), "skills", "implementation-journal", "scripts", "validate_journal.py")
    try:
        out = subprocess.run([sys.executable, script, target], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return 0
    errors = [line for line in out.stdout.decode("utf-8", "replace").splitlines() if " ERROR " in line]
    if not errors:
        return 0
    sys.stderr.write("implementation-journal validator found errors in %s:\n%s\n" % (target, "\n".join(errors)))
    return 2


if __name__ == "__main__":
    sys.exit(main())
