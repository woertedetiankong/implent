---
name: implementation-journal
description: "Keep one short record per task, so the next AI session can carry on where this one stopped and the person steering the work can see where it stands: what was decided that neither the code nor git history shows, what comes next, and a few plain lines for the person. Use when work will span sessions or the user says part of it is left for later, when the user makes a decision or names a constraint that should outlive the chat, when the user pastes back their answers to a plan (the decisions picked on a plan page) and building starts, when the user asks for a handoff, restart notes, a task record or a decision log, or asks to continue or change a task that already has a record under docs/tasks/. Do not use for a single-session fix that leaves nothing to remember."
---

# Implementation Journal

A new session starts knowing nothing of the last one. Most of what it needs it can find by itself: the code says what was built, and git says what changed and what was taken back. What it cannot find anywhere is what was only ever said: a decision the user made, a limit someone else imposes, a guess made where the request was silent, a question still waiting for an answer. This skill keeps exactly that, in one small file per task, together with a few lines for the person.

It keeps nothing else. A record that repeats the code costs time to write, time to read, and goes stale.

## The record

One file per task, `docs/tasks/<YYYY-MM-DD>-<slug>.md`, with three sections: a few lines for the person, and about 300 to 400 words for the next session. Read [references/task-file.md](references/task-file.md) before writing one; it has the format and the rules for each line.

- `## For People`: what the task is called, where it stands, what is waiting on the person, and what the last finished step came to. Plain words. The companion skill `bearings` shows these lines on the project map, and for most people that map is the only place they see them.
- `## Decided`: what the next session could not work out from the code and git history.
- `## Next`: what to do next, in order.

There is no brief, no log, no restart note and no index. The dated file names are the index.

Where the file lives: `docs/tasks/` unless the project already keeps task records somewhere, in which case use that. Check first whether the project tests or lints its `docs/` folder; if a file there would fail a check, put the records in a folder the project ignores and say where they are.

## When to write

- **Open the record** when the work will outlive this session, or at the first decision worth keeping, whichever comes first. A small fix that is done in one sitting and decides nothing gets no record.
- **Add to `Decided` as it happens**, not at the end. The moment to write is when the user settles something, when you learn of a limit from outside the code, when you choose one reading of an unclear request, when you leave something out on purpose, or when you try an approach and drop it for a reason a commit message will not carry.
- **When the user answers a plan** (the response pasted back from a plan page, such as the `html-plan` skill makes), write the answers under `Decided` before building. The plan page is not where the next session looks, so what was chosen on it is otherwise lost. Take the response one answer at a time:
  - An option the user picked or changed, an edit of theirs, or a comment that changes what gets built: a decision of the user's, one line each.
  - An answer the response marks as not opened (html-plan writes `_(not opened; default kept)_` beside it), or a default nobody touched: the user never looked at it, even if they said to go ahead with the plan. It is your own proposal still standing. Write it as a guess and do not put the user's name on it: `- Guess, a plan default the user did not open: exports are kept for 30 days.`
- **Bring the record up to date before any pause**: a final response, a hand back to the user, the end of a step. `Now`, `Next` and the status say how things stand at that moment, not how they were planned.
- **Close it** by setting `status: Complete` and rewriting the lines for people to describe the task as a whole.

Do not commit on your own because of this skill. When the work is committed, its record goes into the same commit.

## What belongs in Decided

Ask of each line: could a careful reader get this from the code and `git log`? If yes, leave it out.

Belongs:

- What the user decided, with the date, in a form the next session can act on ("shipping is refunded only with the last items of an order").
- A limit from outside: a provider's quota, a policy, a deadline, a machine that is not available.
- A guess. Say that it is one, so the next session checks it first when something fails.
- What was left out on purpose, and why.
- What is waiting on the user, and what must not be decided for them meanwhile.
- An approach that was tried and dropped, when the reason is not in the commit that removed it.

Does not belong: what was implemented, which files changed, how the code is laid out, test counts, anything a commit message already says.

## The project's own docs

A fact that is now true of the project for good belongs in the project's documents, not in a task file that will be closed. When this work makes something in the README, in AGENTS or CLAUDE guidance, or in other docs untrue, correct it in the same change: rewrite the stale sentence, do not leave it standing with a correction underneath. When the project has a `bearings` parts list and the work changed how a part works or added a new area, update that part's paths and flow diagram too.

## Several sessions at once

More than one session may be at work in the same project, in the same folder or in separate worktrees.

- One session, one task file. Write only your own. Do not tidy another task's record, even if it looks stale: another session may be working from it.
- A file every task shares (README, docs, the parts list) is edited narrowly: read it again right before editing, change only the lines that belong to your work, never rewrite it whole from memory.
- Before opening a new record, look at the open ones. If one already covers the same part of the project, tell the user before starting.
- When several tasks are open and it is not clear which one this session is for, ask before reading or writing any of them. The user may name a task the way the map shows it ("继续做“语音助手”"): that is the `Name` in a record's lines for people, not a file name.

## What earlier tasks decided

Once a task is marked Complete, no new session is shown its record. What it decided is still in force and still not in the code. So before changing code in a project that has records, look up what was decided about the files you are about to change:

```sh
python3 scripts/decided.py <files or folders>
```

The script is in this skill folder (in Claude Code, `${CLAUDE_SKILL_DIR}/scripts/decided.py`). Given no path, it takes the files with uncommitted changes. For every record, open or finished, whose commits changed one of those files, it prints the task's name, whether it is finished, and its lines under `Decided`. Which files a record's work changed is measured from git: the commits the record cites, and the commits it was committed with. A file renamed or moved since then is followed to the name it has now.

- Take those lines as still in force. When the work in front of you would go against one, say so to the user and name the task it came from, before doing it. A rule does not lapse because the request did not repeat it.
- When the user now decides differently, write the new decision in your own record and name the earlier task. Leave the earlier record as it is, unless this is that task opened again (see below). Where two records disagree, the newer one holds.
- A record the script "could not place" was committed apart from its work and cites no commit, so there is nothing to measure from. If its name sounds like the area you are working in, read its `Decided` yourself.

## Coming back to a finished task

- When the user asks to change something a finished record covers, that is the same task opened again, not a new one. Set its status back to `Open`, say in `Now` what is being changed, add what is decided this time under `Decided`, and keep the `Name`. Open a new record only for a different piece of work that happens to touch the same code, and name the earlier task in it.
- Do not change code that a finished record describes and leave the record saying the old thing: the map goes on showing those lines to people as what the task came to. For a change too small to open the task again, correct the lines it made untrue, rewrite the marks so they name what this change did, and set `updated:`. That narrow edit to a finished record is allowed.

## Older records

A project that used the earlier form of this skill has a folder per task (`handoff.md`, `task-brief.md`, `implementation-log.md`, `next-session.md`). Leave those folders as they are. To continue such a task, read its `handoff.md`, and its log when a decision's reason is unclear, and keep writing in that `handoff.md`: the lines for people at the top, new decisions under its key decisions. Do not convert old folders unless the user asks. New tasks get the one-file form.

## Check

Before finishing, run [scripts/validate_journal.py](scripts/validate_journal.py) with python3 on the record (in Claude Code the path is `${CLAUDE_SKILL_DIR}/scripts/validate_journal.py`). Fix every ERROR. Accept a WARN only on purpose and say so. The script checks what can be counted: the header, the three sections, the lines for people, the length (words, and lines under `Decided`), relative dates, broken links. It checks shape, not truth. What it cannot check is yours, so also read the record once as the next session would: does `Now` match the code as it stands, is every line under `Decided` something that is written nowhere else, and is every `Needs you` line still unanswered?

## Final response

Say where the record is and whether the task is open or complete, what was added under `Decided`, and which of the project's own docs were corrected. If no record was written, say why in one sentence.
