#!/usr/bin/env python3
"""Validate implementation-journal task records against the skill's rules.

A task's record is one file, docs/tasks/<date>-<slug>.md, with a header and
three sections. This checks the mechanical rules from SKILL.md and
references/task-file.md, so drift is caught by a command instead of by
model diligence:

- the header: `status:` Open or Complete, `updated:` with a YYYY-MM-DD date
- the three sections: For People, Decided, Next
- For People, which the bearings map shows to a person: Name and Now lines,
  no backticks, a sentence on every Added/Changed/Removed mark, no "None"
  under Needs you, at most three Not yet lines, a Done line on a task that
  was finished lately
- the read budget (WARN past MAX_LINES, and past MAX_DECIDED lines under
  Decided)
- in any record: relative-date phrases ("today", "last week", ...), broken
  relative links, leftover template placeholders. Code fences are skipped.

Projects that started with the earlier form of the skill keep a folder per
task. In such a folder only handoff.md is looked at, and only its For People
section and the checks that apply to any record: the old layout is not
enforced any more.

Usage:
  validate_journal.py [PATH ...] [--strict]

PATH may be a tasks directory (default: docs/tasks), an older dossier
directory, or individual files. A Markdown file that is not a task record is
passed over. Exit 1 on ERROR (or on WARN too with --strict), 0 otherwise.
"""

import argparse
import datetime
import re
import sys
from pathlib import Path

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
RELATIVE_DATE_RE = re.compile(
    r"\b(today|yesterday|tomorrow|recently"
    r"|last week|next week|this week|last month|next month)\b",
    re.IGNORECASE,
)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)[^)]*\)")
PLACEHOLDERS = ("<YYYY-MM-DD>", "<slug>", "<what the person would call", "<where it stands",
                "<one thing the work is waiting", "<what happens once", "<decision", "<next step")
MAX_LINES = 80      # references/task-file.md read budget
MAX_DECIDED = 14    # past a dozen lines, Decided has usually started to describe the code
NOT_RECORDS = ("next-session.md", "index.md", "readme.md")
# The one section a person reads, on the bearings map. bearings.py parses the same heading and keys;
# change them in both places or not at all.
PEOPLE_HEADINGS = ("For People", "给人看的", "给人看")
PEOPLE_REQUIRED = (("Name", "Name|名字"), ("Now", "Now|现在"))
PEOPLE_DONE = "Done|做成了"
PEOPLE_NEEDS_RE = re.compile(r"^\s*(?:[-*]\s+)?(?:Needs you|等你)\s*[:：]\s*(.*)$", re.IGNORECASE)
PEOPLE_LEFT_RE = re.compile(r"^\s*(?:[-*]\s+)?(?:Not yet|还没做)\s*[:：]\s*\S", re.IGNORECASE)
# A mark on a flow diagram: `Changed: Part / Box: sentence`. Without the sentence the page shows a bare name.
PEOPLE_MARK_RE = re.compile(r"^\s*(?:[-*]\s+)?(Added|Changed|Removed|新增|改了|去掉)\s*[:：]\s*(.*)$", re.IGNORECASE)
PEOPLE_RECENT_DAYS = 7  # a task finished this lately is asked for its Done line; older ones are left alone
NONE_RE = re.compile(r"^(?:none|nothing|n/a|无|没有|暂无)\W*$", re.IGNORECASE)


class Report:
    def __init__(self):
        self.errors = 0
        self.warnings = 0

    def error(self, path, line, msg):
        self.errors += 1
        print(f"{path}:{line}: ERROR {msg}")

    def warn(self, path, line, msg):
        self.warnings += 1
        print(f"{path}:{line}: WARN {msg}")


def read_lines(path):
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def fence_mask(lines):
    """True per line when inside a fenced code block (fence lines included)."""
    mask, inside = [], False
    for line in lines:
        if line.lstrip().startswith(("```", "~~~")):
            inside = not inside
            mask.append(True)
        else:
            mask.append(inside)
    return mask


def parse_frontmatter(lines):
    """The fields of a leading --- block, or {}."""
    if not lines or lines[0].strip() != "---":
        return {}
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip()
    return {}


def sections(lines):
    """Map '## Heading' -> (first line number of its body, body text)."""
    found, current, start = {}, None, 0
    for i, line in enumerate(lines):
        match = re.match(r"##\s+(.*)", line)
        if match:
            if current:
                found[current] = (start + 1, "\n".join(lines[start: i]))
            current, start = match.group(1).strip(), i + 1
    if current:
        found[current] = (start + 1, "\n".join(lines[start:]))
    return found


def check_common(path, lines, report):
    """Relative dates, broken relative links, leftover template placeholders."""
    mask = fence_mask(lines)
    for i, line in enumerate(lines, start=1):
        if mask[i - 1]:
            continue
        match = RELATIVE_DATE_RE.search(line)
        if match:
            report.warn(path, i, f'relative date "{match.group(0)}" — use an absolute YYYY-MM-DD date')
        for placeholder in PLACEHOLDERS:
            if placeholder in line:
                report.warn(path, i, f'template placeholder "{placeholder}" left unfilled')
        for target in LINK_RE.findall(line):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if not (path.parent / target.split("#")[0]).resolve().exists():
                report.error(path, i, f"broken relative link: {target}")


def recently(date_text):
    """True when an ISO date is within PEOPLE_RECENT_DAYS: the task was finished just now, not long ago."""
    try:
        then = datetime.date.fromisoformat(date_text.strip()[:10])
    except ValueError:
        return False
    return 0 <= (datetime.date.today() - then).days <= PEOPLE_RECENT_DAYS


def check_people(path, found, complete, updated, report):
    """The lines the project map shows to a person."""
    people = next((found[name] for name in PEOPLE_HEADINGS if name in found), None)
    if not people:
        if not complete:
            report.warn(path, 1, 'no "## For People" section — the project map cannot say where this task stands '
                                 "or what is waiting on the user")
        return
    line_no, body = people
    for key, names in PEOPLE_REQUIRED:
        if not re.search(rf"^\s*(?:[-*]\s+)?(?:{names})\s*[:：]\s*\S", body, re.MULTILINE | re.IGNORECASE):
            report.warn(path, line_no, f'For People has no "{key}:" line — the project map cannot show the task properly')
    if "`" in body:
        report.warn(path, line_no,
                    "For People is read by a person on the project map — no file names, code names or commands in backticks")
    left = 0
    for offset, text in enumerate(body.splitlines()):
        mark = PEOPLE_MARK_RE.match(text)
        if mark and not re.search(r"\S\s*[:：]\s*\S", mark.group(2)):
            report.warn(path, line_no + offset, f'"{mark.group(1)}" mark has no sentence — write it as '
                                                '"Part / Box: what is different"')
        needs = PEOPLE_NEEDS_RE.match(text)
        if needs and NONE_RE.match(needs.group(1).strip()):
            report.warn(path, line_no + offset, 'a "Needs you" line that says nothing is waiting — leave the line out')
        left += bool(PEOPLE_LEFT_RE.match(text))
    if left > 3:
        report.warn(path, line_no, f'{left} "Not yet" lines — keep the three that would surprise the person most')
    has_done = re.search(rf"^\s*(?:[-*]\s+)?(?:{PEOPLE_DONE})\s*[:：]\s*\S", body, re.MULTILINE | re.IGNORECASE)
    if complete and not has_done and recently(updated):
        report.warn(path, line_no, 'finished task with no "Done:" line under "## For People" — the project map '
                                   "drops it at once, and the user never sees what it came to")


def check_record(path, report):
    """A one-file task record."""
    lines = read_lines(path)
    fm = parse_frontmatter(lines)
    status = fm.get("status", "")
    if not re.match(r"(Open|Complete|Provisional)\b", status, re.IGNORECASE):
        report.error(path, 1, 'header "status:" must be Open or Complete')
    if not DATE_RE.search(fm.get("updated", "")):
        report.error(path, 1, 'header "updated:" must carry a YYYY-MM-DD date')
    complete = status.lower().startswith("complete")
    found = sections(lines)
    for name in ("Decided", "Next"):
        if name not in found:
            report.error(path, 1, f'missing section "## {name}"')
    check_people(path, found, complete, fm.get("updated", ""), report)
    if "Decided" in found:
        line_no, body = found["Decided"]
        entries = [l for l in body.splitlines() if l.lstrip().startswith(("- ", "* "))]
        if len(entries) > MAX_DECIDED:
            report.warn(path, line_no, f"{len(entries)} lines under Decided — remove the ones the code now shows by itself")
    if "Next" in found and not complete:
        line_no, body = found["Next"]
        steps = [l.strip() for l in body.splitlines() if l.strip()]
        if not steps or all(NONE_RE.match(l.lstrip("-*0123456789. ")) for l in steps):
            report.warn(path, line_no, "an open task with nothing under Next — say what the next session should start on")
    if len(lines) > MAX_LINES:
        report.warn(path, len(lines), f"record is {len(lines)} lines (budget {MAX_LINES}) — "
                                      "it has probably started to describe the code")
    check_common(path, lines, report)


def check_old_handoff(path, report):
    """handoff.md in an older dossier folder: only what the map reads, and what applies to any record."""
    lines = read_lines(path)
    fm = parse_frontmatter(lines)
    complete = fm.get("status", "").lower().startswith("complete")
    check_people(path, sections(lines), complete, fm.get("updated", ""), report)
    check_common(path, lines, report)


def is_record(path):
    """A Markdown file with a `status:` in its header and at least one of the record's sections."""
    if path.suffix.lower() != ".md" or path.name.lower() in NOT_RECORDS:
        return False
    lines = read_lines(path)
    if "status" not in parse_frontmatter(lines):
        return False
    return any(name in sections(lines) for name in ("Decided", "Next") + PEOPLE_HEADINGS)


def collect(paths):
    """(records, old handoffs) among the given paths."""
    records, old = [], []
    for path in paths:
        if path.is_dir():
            if (path / "handoff.md").is_file():          # one older dossier folder
                old.append(path / "handoff.md")
                continue
            for child in sorted(path.iterdir()):
                if child.is_dir() and (child / "handoff.md").is_file():
                    old.append(child / "handoff.md")
                elif child.is_file() and is_record(child):
                    records.append(child)
        elif path.is_file():
            if path.name == "handoff.md":
                old.append(path)
            elif is_record(path):
                records.append(path)
    return records, old


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    args = parser.parse_args()
    paths = args.paths or [Path("docs/tasks")]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print("no such path: " + ", ".join(str(p) for p in missing))
        return 1
    records, old = collect(paths)
    report = Report()
    for path in records:
        check_record(path, report)
    for path in old:
        check_old_handoff(path, report)
    print(f"\n{len(records) + len(old)} task record(s) checked: {report.errors} error(s), {report.warnings} warning(s)")
    return 1 if report.errors or (args.strict and report.warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
