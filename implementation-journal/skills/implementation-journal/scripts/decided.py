#!/usr/bin/env python3
"""What earlier tasks decided about the files you are about to change.

    decided.py <file or folder> [...]     the records whose work changed those files
    decided.py                            the same, for the files with uncommitted changes

A decision lives in the record of the task that made it. Once that task is marked Complete, a new
session is no longer shown its record, so a rule the user set months ago ("refund shipping only with
the last items") can be broken by a later change to the same code without anyone noticing. This prints
those lines again when they matter: for each record, open or finished, whose commits changed one of
the files named, its name, its state and everything under its `## Decided`.

Which files a record's work changed is measured, not written: the commits the record cites by hash,
and the commits that changed the record itself and no other task's record. A record that was never
committed with its work and cites no commit cannot be placed; those are counted at the end.

A file that was renamed or moved afterwards is followed to the name it has now, from the renames git
finds in the commits since: a rule made about src/pay.py still comes up when src/billing/pay.py is about
to change. Asking by the old name works too. What git does not call a rename is not followed: a file
split in two, or one moved and mostly rewritten in the same commit.

Reads git and the records under docs/tasks/ (--tasks DIR for another place). Writes nothing.
"""
import argparse
import os
import re
import subprocess
import sys

NOT_RECORDS = ("next-session.md", "index.md", "readme.md")
DECIDED_HEAD = re.compile(r"^##\s+(?:Decided|Key Decisions|Closed Decisions\b.*)\s*$", re.I)
PEOPLE_HEAD = re.compile(r"^##\s+(?:For People|给人看的?)\s*$", re.I)
NAME_LINE = re.compile(r"^\s*(?:[-*]\s+)?(?:Name|名字)\s*[:：]\s*(.+?)\s*$", re.I)
SHOWN = 6        # records printed unless --all
FILES_SHOWN = 4  # matching files named for each record


def git(root, *args, stdin=None):
    out = subprocess.run(["git", "-C", root, *args], capture_output=True, input=stdin)
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else ""


def slurp(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def read_record(text):
    """(header fields, the name a person knows the task by, the lines under Decided)."""
    lines, meta, body = text.split("\n"), {}, 0
    if lines and lines[0].strip() == "---":
        for at, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                body = at + 1
                break
            key, sep, value = line.partition(":")
            if sep:
                meta[key.strip().lower()] = value.strip()
    name, title, decided, inside = "", "", [], ""
    for line in lines[body:]:
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        if line.startswith("## "):
            inside = "decided" if DECIDED_HEAD.match(line) else "people" if PEOPLE_HEAD.match(line) else ""
        elif inside == "people" and not name:
            m = NAME_LINE.match(line)
            name = m.group(1) if m else ""
        elif inside == "decided" and line.strip() and not line.lstrip().startswith("<!--"):
            decided.append(line.rstrip())
    return meta, name or title, decided


def load_records(root, rel):
    """Every task record: one file `<id>.md` with a status in its header, or an older folder `<id>/`
    whose handoff.md is read the same way."""
    base, records = os.path.join(root, rel), []
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return records
    for name in names:
        path = os.path.join(base, name)
        single = not os.path.isdir(path)
        if single and (not name.lower().endswith(".md") or name.lower() in NOT_RECORDS):
            continue
        text = slurp(path if single else os.path.join(path, "handoff.md"))
        if not text:
            continue
        meta, known, decided = read_record(text)
        if single and "status" not in meta:
            continue  # some other Markdown file kept beside the records
        cited = text if single else text + slurp(os.path.join(path, "implementation-log.md"))
        when = re.search(r"\d{4}-\d{2}-\d{2}", meta.get("updated", "") or name)
        records.append({"id": name[:-3] if single else name,
                        "home": rel + "/" + name,
                        "file": rel + "/" + (name if single else name + "/handoff.md"),
                        "name": known or (name[:-3] if single else name),
                        "done": meta.get("status", "").lower().startswith("complete"),
                        "updated": when.group(0) if when else "",
                        "decided": decided,
                        "cited": set(re.findall(r"\b[0-9a-f]{7,40}\b", cited))})
    return records


def record_at(path, rel):
    """The id of the record a path under the tasks folder belongs to, or None."""
    if not path.startswith(rel + "/"):
        return None
    first, slash, _ = path[len(rel) + 1:].partition("/")
    if slash:
        return first
    return first[:-3] if first.lower().endswith(".md") and first.lower() not in NOT_RECORDS else None


def place(root, rel, records):
    """Give each record `files`: what its commits changed, outside the tasks folder."""
    words = sorted({w for r in records for w in r["cited"]})
    full = {}  # a cited word -> the commit it names; a word of hex digits is not always a commit
    if words:
        out = git(root, "cat-file", "--batch-check", stdin="\n".join(words).encode())
        for word, line in zip(words, out.splitlines()):
            bits = line.split()
            if len(bits) >= 2 and bits[1] == "commit":
                full[word] = bits[0]
    revs = {r["id"]: {full[w] for w in r["cited"] if w in full} for r in records}
    # the commits that changed a record and no other task's record are that task's work too
    log = git(root, "log", "--no-merges", "--format=%x01%H", "--name-only", "--", rel)
    for block in log.split("\x01")[1:]:
        rev, _, names = block.partition("\n")
        ids = {record_at(n.strip(), rel) for n in names.split("\n") if n.strip()} - {None}
        if len(ids) == 1 and ids <= set(revs):
            revs[ids.pop()].add(rev.strip())
    for r in records:
        r["files"], r["was"], when = set(), {}, {}
        if not revs[r["id"]]:
            continue
        # --no-renames: a commit that moved a file counts as changing both of its names
        out = git(root, "show", "--no-renames", "--format=%x01%ct", "--name-only", *sorted(revs[r["id"]]))
        for block in out.split("\x01")[1:]:
            at, _, names = block.partition("\n")
            for n in names.split("\n"):
                if n.strip() and not n.startswith(rel + "/"):
                    when[n] = min(int(at.strip() or 0), when.get(n, 1 << 62))
        r["files"], r["when"], r["placed"] = set(when), when, True
    follow(root, [r for r in records if r.get("when")])


def follow(root, records):
    """Give each record `was`: for a file that has been renamed since the record's work changed it, the
    name it has now -> the name it had then. The name it has now is added to `files`."""
    if not records:
        return
    first = min(min(r["when"].values()) for r in records)
    log = git(root, "log", "--no-merges", "-M", "--diff-filter=R", "--name-status", "--format=%x01%ct",
              "--since=%d" % first)
    moves = {}  # an old name -> [(when, the new name)], oldest first
    for block in reversed(log.split("\x01")[1:]):
        at, _, rows = block.partition("\n")
        for row in rows.split("\n"):
            bits = row.split("\t")
            if len(bits) == 3 and bits[0].startswith("R"):
                moves.setdefault(bits[1], []).append((int(at.strip() or 0), bits[2]))
    if not moves:
        return
    for r in records:
        for name, at in r["when"].items():
            now, hops = name, 0
            while now in moves and hops < 50:
                step = next(((t, new) for t, new in moves[now] if t >= at), None)
                if not step:
                    break
                (at, now), hops = step, hops + 1
            if now != name and now not in r["when"]:
                r["was"][now] = name
                r["files"].add(now)


def asked_paths(root, args):
    """The paths asked about, relative to the repo root. With none given: the uncommitted work."""
    if args:
        out = []
        for a in args:
            p = os.path.relpath(os.path.realpath(os.path.join(os.getcwd(), a)), root).replace(os.sep, "/")
            out.append("" if p == "." else p)
        return out, False
    status = subprocess.run(["git", "-C", root, "status", "--porcelain", "-z", "--untracked-files=all"],
                            capture_output=True).stdout.decode("utf-8", "replace")
    rows, out, skip = status.split("\0"), [], False
    for row in rows:
        if skip:  # the old name of a rename
            skip = False
            continue
        if len(row) > 3:
            out.append(row[3:])
            skip = row[0] in "RC"
    return out, True


def hits(files, asked):
    found = set()
    for q in asked:
        if q == "":
            return set(files)
        q = q.rstrip("/")
        found.update(f for f in files if f == q or f.startswith(q + "/"))
    return found


def look_up(root, rel, asked):
    """(every record, [(record, its files among those asked about)] newest first, the records that could
    not be placed). `asked` is paths relative to the repo root."""
    records = load_records(root, rel)
    if not records:
        return [], [], []
    place(root, rel, records)
    found = []
    for r in records:
        mine = hits(r["files"], asked)
        if mine:
            found.append((r, sorted(mine)))
    found.sort(key=lambda x: x[0]["updated"], reverse=True)
    return records, found, [r for r in records if not r.get("placed")]


def changed_line(r, mine):
    """The files of a record among those asked about, each with the name it had when the record's work
    changed it if that was another."""
    shown = ["%s (then %s)" % (f, r["was"][f]) if f in r["was"] else f for f in mine[:FILES_SHOWN]]
    return "changed: " + ", ".join(shown) + (" and %d more" % (len(mine) - FILES_SHOWN) if len(mine) > FILES_SHOWN else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("paths", nargs="*", help="files or folders about to be changed (none: the uncommitted work)")
    ap.add_argument("--tasks", default="docs/tasks", help="where the task records are (default docs/tasks)")
    ap.add_argument("--all", action="store_true", help="print every matching record, not the %d newest" % SHOWN)
    args = ap.parse_args()

    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True)
    if top.returncode:
        print("decided: not inside a git repository, so there is nothing to measure.")
        return 0
    root = os.path.realpath(top.stdout.decode().strip())
    rel = os.path.relpath(os.path.realpath(os.path.join(root, args.tasks)), root).replace(os.sep, "/")
    if not load_records(root, rel):
        print("decided: no task records under %s." % rel)
        return 0
    asked, from_work = asked_paths(root, args.paths)
    asked = [a for a in asked if not (a + "/").startswith(rel + "/")]
    if not asked:
        print("decided: no files to ask about (nothing uncommitted outside %s). Name the files or folders "
              "you are about to change." % rel)
        return 0
    records, found, unplaced = look_up(root, rel, asked)

    what = "the files with uncommitted changes" if from_work else ", ".join(a or "the whole project" for a in asked[:4]) + (
        " and %d more" % (len(asked) - 4) if len(asked) > 4 else "")
    if not found:
        print("decided: none of the %d task records changed %s." % (len(records), what))
    else:
        print("Earlier tasks whose work changed %s: %d of %d records." % (what, len(found), len(records)))
        print("The code does not show these lines: what the user decided, limits from outside, guesses. Keep to "
              "them unless the user now decides otherwise; where two disagree, the newer record wins. Read a "
              "record for more.")
        shown = found if args.all else found[:SHOWN]
        for r, mine in shown:
            state = "finished" if r["done"] else "open"
            print("\n## %s (%s, updated %s) %s" % (r["name"], state, r["updated"] or "unknown", r["file"]))
            print(changed_line(r, mine))
            print("\n".join(r["decided"]) if r["decided"] else "(nothing is written under Decided)")
        if len(found) > len(shown):
            print("\n%d older records also changed these files: %s. Run again with --all to print them." % (
                len(found) - len(shown), ", ".join(r["name"] for r, _ in found[len(shown):])))
    if unplaced:
        print("\n%d record%s could not be placed (no commit cited, and not committed with the work): %s." % (
            len(unplaced), "" if len(unplaced) == 1 else "s", ", ".join(r["name"] for r in unplaced[:8])
            + (" and others" if len(unplaced) > 8 else "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
