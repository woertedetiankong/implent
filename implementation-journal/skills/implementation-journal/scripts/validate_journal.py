#!/usr/bin/env python3
"""Validate implementation-journal artifacts against the skill's discipline.

Checks the mechanical rules from SKILL.md and references/ so drift is caught
by a command instead of model diligence:

- handoff.md: frontmatter (status/updated), required sections, a runnable
  Restart Verify block with expected outputs, no "verify manually",
  read budget (WARN past HANDOFF_MAX_LINES).
- task-brief.md: Goal, Success Criteria, Parent plan, Created date.
- implementation-log.md: dated entry headings; consistency with the handoff
  (a missing log must be declared "Not required" in the handoff).
- next-session.md (one per dossier): handoff pointer that resolves to the
  handoff beside it, Errata / Now do / Red lines / First verify fields.
  WARN when a repo-level entry sits beside per-task entries.
- Markdown files: relative-date phrases ("today", "last week", ...), broken
  relative links, leftover template placeholders. Code fences are skipped.

Usage:
  validate_journal.py [PATH ...] [--strict]

PATH may be a tasks directory (default: docs/tasks), a dossier directory,
or individual files; file roles are inferred from names. Exit 1 on ERROR
(or on WARN too with --strict), 0 otherwise. Repos with their own
conventions can pass explicit paths; unknown layouts degrade to warnings.
"""

import argparse
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
PLACEHOLDERS = (
    "<YYYY-MM-DD>", "<command 1>", "<Verifiable criterion>",
    "<One concrete sentence", "<observable output>", "<milestone or slice>",
    "<Next action", "<one-sentence result", "<enforceable instruction",
    "<Decision and rationale", "<Risk>", "<Follow-up>", "<Assumption or",
    "<path or subsystem>", "<special environment state",
)
HANDOFF_REQUIRED = ("Summary", "Current State", "Next Steps", "Restart Verify")
# references/handoff-discipline.md read budget.
HANDOFF_MAX_LINES = 100
# Always written even when one line, because their absence is ambiguous.
HANDOFF_DECLARE = ("Git And Persistent State", "Implementation Log")
# A conditional section whose every line matches this is placeholder-only
# and should be omitted per references/handoff-discipline.md.
NONEISH_RE = re.compile(
    r"^(?:[\w /()-]+:)?\s*(?:none(?: known| yet)?|unknown(?:/not applicable)?"
    r"|not applicable|n/a)\s*\.?\s*$",
    re.IGNORECASE,
)

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
    """Return (dict, last_line_index) for a leading --- block, or ({}, 0)."""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    fields = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return fields, i
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return {}, 0


def sections(lines):
    """Map '## Heading' -> (line_no, body_text)."""
    found, current, start = {}, None, 0
    for i, line in enumerate(lines):
        match = re.match(r"##\s+(.*)", line)
        if match:
            if current:
                found[current] = (start, "\n".join(lines[start: i]))
            current, start = match.group(1).strip(), i + 1
    if current:
        found[current] = (start, "\n".join(lines[start:]))
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
            resolved = (path.parent / target.split("#")[0]).resolve()
            if not resolved.exists():
                report.error(path, i, f"broken relative link: {target}")


def check_handoff(path, report):
    lines = read_lines(path)
    if len(lines) > HANDOFF_MAX_LINES:
        report.warn(path, len(lines),
                    f"handoff is {len(lines)} lines (budget {HANDOFF_MAX_LINES}) — move narrative into implementation-log.md")
    fm, _ = parse_frontmatter(lines)
    status = fm.get("status", "")
    if not re.match(r"(Complete|Provisional)\b", status):
        report.error(path, 1, 'frontmatter "status:" must be Complete or Provisional')
    if not DATE_RE.search(fm.get("updated", "")):
        report.error(path, 1, 'frontmatter "updated:" must carry a YYYY-MM-DD date')

    found = sections(lines)
    for name in HANDOFF_REQUIRED:
        if name not in found:
            report.error(path, 1, f'missing required section "## {name}"')
    for name in HANDOFF_DECLARE:
        if name not in found:
            report.warn(path, 1, f'missing "## {name}" — always declare it, one line is enough')
    if status.startswith("Complete") and "Validation" not in found:
        report.warn(path, 1, 'status Complete but no "## Validation" section — record the evidence')

    for name, (line_no, body) in found.items():
        if name in HANDOFF_REQUIRED or name in HANDOFF_DECLARE:
            continue
        content = [l.strip().lstrip("-*").strip() for l in body.splitlines()]
        content = [l for l in content if l and not l.startswith("```")]
        if not content or all(NONEISH_RE.match(l) for l in content):
            report.warn(path, line_no,
                        f'section "## {name}" is empty or placeholder-only — omit conditional sections instead')

    if "Restart Verify" in found:
        line_no, body = found["Restart Verify"]
        commands = [l for l in body.splitlines()
                    if l.strip() and not l.strip().startswith(("```", "#"))]
        if not commands:
            report.error(path, line_no, "Restart Verify has no runnable command")
        if "expected" not in body:
            report.error(path, line_no, "Restart Verify commands must state expected output")
        elif "mismatch" not in body:
            report.warn(path, line_no, "Restart Verify should say what a mismatch means")

    for i, line in enumerate(lines, start=1):
        if "verify manually" in line.lower():
            report.warn(path, i, 'says "verify manually" — name the exact command, screen, file, or artifact')

    log_section = found.get("Implementation Log")
    log_file = path.parent / "implementation-log.md"
    if not log_file.exists():
        if log_section and "not required" not in log_section[1].lower():
            report.warn(path, log_section[0],
                        'no implementation-log.md: section must say "Not required" with the reason')
    elif log_section and "implementation-log.md" not in log_section[1]:
        report.warn(path, log_section[0], "implementation-log.md exists but is not referenced here")


def check_brief(path, report):
    lines = read_lines(path)
    text = "\n".join(lines)
    for heading in ("## Goal", "## Success Criteria", "## Scope", "## Constraints"):
        if heading not in text:
            report.error(path, 1, f'missing section "{heading}"')
    if "Parent plan:" not in text:
        report.warn(path, 1, 'missing "Parent plan:" line (use "None found" when no plan exists)')
    if not any("Created:" in l and DATE_RE.search(l) for l in lines):
        report.warn(path, 1, 'missing "Created: YYYY-MM-DD" line')


def check_log(path, report):
    text = "\n".join(read_lines(path))
    if not re.search(r"^###\s+\d{4}-\d{2}-\d{2}", text, re.MULTILINE):
        report.error(path, 1, "no dated entry heading (### YYYY-MM-DD); an empty log should not exist")


def check_next_session(path, report):
    lines = read_lines(path)
    text = "\n".join(lines)
    pointer = re.search(r"Read\s+`([^`]+)`\s+first", text)
    if not pointer:
        report.error(path, 1, 'missing handoff pointer ("Read `<handoff path>` first")')
    else:
        target = Path(pointer.group(1))
        # Pointers may be written relative to the entry, the repo root, or
        # any directory between, so try every ancestor; cwd-independent.
        bases = [path.resolve().parent, *path.resolve().parents]
        hits = [target] if target.is_absolute() and target.exists() else \
            [base / target for base in bases if (base / target).exists()]
        own = path.parent / "handoff.md"
        if not hits:
            report.error(path, 1, f"handoff pointer does not resolve: {pointer.group(1)}")
        elif own.exists() and hits[0].resolve() != own.resolve():
            # One entry per dossier: it restarts its own task, not another one.
            report.warn(path, 1, f"entry points at another dossier's handoff ({pointer.group(1)}) — "
                                 "point it at the handoff.md beside it")
    if not (path.parent / "handoff.md").exists():
        own_entries = [p for p in path.parent.glob("*/*") if p.name.lower() == "next-session.md"]
        if own_entries:
            report.warn(path, 1, "repo-level entry beside per-task entries — move it into the dossier "
                                 "it points at as next-session.md; tasks open at the same time must not share one file")
    for field in ("Errata:", "Now do:", "Red lines:", "First verify:"):
        if field not in text:
            report.warn(path, 1, f'missing "{field}" field')


def classify(path):
    name = path.name.lower()
    if "handoff" in name:
        return check_handoff
    if "brief" in name:
        return check_brief
    if "implementation-log" in name or name == "log.md":
        return check_log
    if "next-session" in name:
        return check_next_session
    return None


def collect(paths):
    """Expand args into journal files; default tasks dir when none given."""
    if not paths:
        default = Path("docs/tasks")
        if not default.is_dir():
            print("No paths given and docs/tasks not found; pass the tasks dir, "
                  "dossier dirs, or files explicitly.", file=sys.stderr)
            sys.exit(2)
        paths = [default]
    files = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.md")))
        elif p.is_file():
            files.append(p)
        else:
            print(f"Path not found: {p}", file=sys.stderr)
            sys.exit(2)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", help="tasks dir, dossier dirs, or files")
    parser.add_argument("--strict", action="store_true", help="warnings also fail")
    args = parser.parse_args()

    report = Report()
    files = collect(args.paths)
    checked = 0
    for path in files:
        checker = classify(path)
        if path.suffix.lower() == ".md":
            check_common(path, read_lines(path), report)
        if checker:
            checker(path, report)
            checked += 1

    print(f"\n{len(files)} file(s) scanned, {checked} journal file(s) checked: "
          f"{report.errors} error(s), {report.warnings} warning(s)")
    if report.errors or (args.strict and report.warnings):
        sys.exit(1)


if __name__ == "__main__":
    main()
