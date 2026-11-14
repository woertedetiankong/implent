# Claude Code Hooks for implementation-journal

Harness enforcement for the skill's two weakest prompt-only guarantees: session-start continuity and immediate validation feedback.

The hooks register themselves through the Claude Code plugin: `hooks/hooks.json` loads whenever the plugin is installed from the marketplace, or the plugin folder sits in `~/.claude/skills/` (Claude Code loads it as `implementation-journal@skills-dir`). Run `/plugin` and check the plugin's hooks to confirm. Codex has no equivalent; there the skill's own steps cover the same ground.

## What each hook does

- `session-start.sh` (SessionStart), which runs `session_start.py` beside it: tells a new session which tasks are open in the project. A task is open until its record, `docs/tasks/<date>-<slug>.md`, says `status: Complete`. With one open task the hook prints that record, so resuming needs no pasting; with several it prints a short list and tells the session to settle which task it is for. In a project that started with the earlier form of the skill, a task is a folder, open while it has a `next-session.md` and its `handoff.md` is not Complete; those are still listed. After a compaction it also reminds the session to bring its record up to date.
- `post-edit-validate.sh` (PostToolUse on Edit/Write; Claude Code no longer has a MultiEdit tool): after any edit to a Markdown file under `docs/tasks/`, runs the skill's `scripts/validate_journal.py` on it and feeds ERROR lines back to the session at once. The validator passes over a Markdown file that is not a task record, so other files in that folder are left alone. Warnings wait for the check before finishing.

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
      }
    ]
  }
}
```

Notes:

- Commands without an `args` key run through a shell, so `$HOME` expands. Keep the inner quotes so paths with spaces survive; if the skill lives elsewhere, change the path.
- The SessionStart entry has no `matcher`, so it fires on every source (`startup`, `resume`, `clear`, `compact`, `fork`); the script branches on the source itself.
- Both scripts need `python3` on PATH (the validator already does).
- Hook changes are picked up when a session starts; restart or run `/hooks` to verify registration.
- Uninstall by removing the entries again — the scripts keep no state.

## Review checklist

- Read the scripts (`session-start.sh`, `session_start.py`, `post-edit-validate.sh`); they only read stdin JSON, read task records, and run the bundled validator. Neither writes files or touches the network.
- If your repos keep task records somewhere other than `docs/tasks/`, adjust the path in both scripts first.
