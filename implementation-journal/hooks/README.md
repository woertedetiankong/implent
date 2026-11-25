# Claude Code Hooks for implementation-journal

Harness support for the three things the skill cannot guarantee by its text alone: that a new session learns what is open, that a record is checked the moment it is written, and that a session changing a file learns what was decided about it.

The hooks register themselves through the Claude Code plugin: `hooks/hooks.json` loads whenever the plugin is installed from the marketplace, or the plugin folder sits in `~/.claude/skills/` (Claude Code loads it as `implementation-journal@skills-dir`). Run `/plugin` and check the plugin's hooks to confirm. Codex has no equivalent; there the skill's own steps cover the same ground.

## What each hook does

- `session-start.sh` (SessionStart), which runs `session_start.py` beside it: tells a new session which tasks are open in the project. A task is open until its record, `docs/tasks/<date>-<slug>.md`, says `status: Complete`. With one open task the hook prints that record, so resuming needs no pasting; with several it prints a short list and tells the session to settle which task it is for. In a project that started with the earlier form of the skill, a task is a folder. It is open while its `handoff.md` is not Complete and the folder has a `next-session.md`, or the handoff has lines for people, or it changed in the last 30 days: the rule the bearings map goes by, so the list given to a session and the map shown to a person name the same tasks. A folder with no `next-session.md` is pointed to, not printed. The records are looked for in `docs/tasks/` of the folder the session started in or of a folder above it, up to the top of the repository, so a session started in a subfolder is told the same. Each record comes with the day it last changed and how many days ago that was. A record that has not changed in more than 30 days (`STALE_DAYS` in `session_start.py`) is not printed and does not count as open: the hook names it in one line and says that what it calls running or waiting was true on the day it was written. That day is the later of the header's `updated:` and the day the file last changed, taken from its last commit when git has it unchanged (so a fresh clone does not make every record look new) and from the file itself otherwise. After a compaction it also reminds the session to bring its record up to date. When the repo has finished tasks, the output ends with one line that names the skill's `scripts/decided.py` and says to run it on the files about to be changed: a finished task's record is shown to no one, and what it decided is not in the code. A session with no open task gets that line alone.
- `post-edit-validate.sh` (PostToolUse on Edit/Write; Claude Code no longer has a MultiEdit tool): after any edit to a Markdown file under `docs/tasks/`, runs the skill's `scripts/validate_journal.py` on it and feeds ERROR lines back to the session at once. The validator passes over a Markdown file that is not a task record, so other files in that folder are left alone. Warnings wait for the check before finishing.
- `decided-on-edit.sh` (PostToolUse on Edit/Write/NotebookEdit), which runs `decided_on_edit.py` beside it: the first time a session edits a file, gives it the `Decided` lines of every task record whose work changed that file, found by the skill's `scripts/decided.py`. The session-start line asks for this lookup; in a trial, one of two sessions that were not reminded changed the code against an earlier rule without seeing it. The hook only tells: it runs after the edit, and blocks and undoes nothing. Each record is given once in a session and each file looked up once; after a compaction they are given again. A record the session-start hook has just printed whole is not repeated. It stays silent for a file in a repository with no `docs/tasks/`, and for the records themselves.

A separate PreCompact hook was considered and rejected: PreCompact hook output is not added to Claude's context, so it cannot instruct the session to refresh anything. The SessionStart `compact` source is the working equivalent, firing immediately after compaction.

## Manual install (only when the plugin is not loaded)

Do not add these entries when the plugin is loaded: every hook would run twice. If you added them by hand before the plugin existed, remove them.

Add to `~/.claude/settings.json` (all projects) or `<project>/.claude/settings.json` (one project). If a `hooks` key already exists, merge these entries into it:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$HOME/.claude/skills/implementation-journal/hooks/session-start.sh\""
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "\"$HOME/.claude/skills/implementation-journal/hooks/post-edit-validate.sh\""
          }
        ]
      },
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "\"$HOME/.claude/skills/implementation-journal/hooks/decided-on-edit.sh\""
          }
        ]
      }
    ]
  }
}
```

Notes:

- Commands without an `args` key run through a shell, so `$HOME` expands. Keep the inner quotes so paths with spaces survive; if the skill lives elsewhere, change the path.
- The SessionStart entry has no `matcher`, so it fires on every source (`startup`, `resume`, `clear`, `compact`, `fork`); the script branches on the source itself.
- All three scripts need `python3` on PATH (the validator already does).
- Hook changes are picked up when a session starts; restart or run `/hooks` to verify registration.
- Uninstall by removing the entries again. Nothing is kept in a project. `decided_on_edit.py` keeps one small file per session in the machine's temporary folder (`implementation-journal/<session id>.json`: which files it has looked up and which records it has given), and removes those older than three days.

## Review checklist

- Read the scripts (`session-start.sh`, `session_start.py`, `post-edit-validate.sh`, `decided-on-edit.sh`, `decided_on_edit.py`); they only read stdin JSON, read task records, ask git about commits, and run the bundled validator and lookup. None writes in a project or touches the network; the one file written is the per-session note described above.
- If your repos keep task records somewhere other than `docs/tasks/`, adjust the path in the scripts first (`docs/tasks` in `session_start.py` and `post-edit-validate.sh`, `TASKS` in `decided_on_edit.py`).
