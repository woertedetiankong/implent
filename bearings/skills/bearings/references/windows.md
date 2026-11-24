# Several windows at once

Part of the `bearings` skill. `SKILL.md` covers the parts list, its diagrams and the script `scripts/bearings.py`; this file covers telling the sessions at work on the project apart.

People often run several Claude Code or Codex sessions on one project, and soon cannot say which window is doing what. `git` cannot say which of them changed a file either. So the script reads the session records both tools keep on the machine and puts each window on the project:

- **Every window that has been at work here in the last day gets a row**, not only the ones with uncommitted files: a letter, the window's name (its journal task if it is writing in a task's record under `docs/tasks/`, otherwise the session's title or opening request), and which tool it is.
- **How it stands.** Working: it is in the middle of a turn and its record moved in the last few minutes. Waiting for your reply: the agent has handed back and nobody has answered. Held up: it stopped in the middle of a step for a while, which is what a window waiting for a permission looks like, and also one running a long command; the page says both. Idle: nothing for a long time.
- **What it was last asked**, in the person's own words, and when it last moved.
- **What it changed**: its uncommitted files by part, and the commits made while one of its shell commands was running.
- **Collisions**, worst first: a file two windows both changed in one checkout (one will overwrite the other), a file changed in two worktrees (a conflict when they are merged), and a part two windows are both changing (worth a look). The parts list itself is left out: every window keeps its own lines of it up to date.

`bearings.py windows` prints all of this; the map shows it as "who is working where", with the collisions above it, and marks each lit room with the letters of the windows in it. `bearings.py check` still adds its "by window" list. The map also counts uncommitted work in the repository's other worktrees.

- A file changed with an edit tool is matched for certain. A file changed by a shell command is matched by time, and only when exactly one window fits; a commit is matched to a window the same way. Anything else is listed as having no window on record; say so rather than guessing.
- A window's state is read from its record, so it is as old as the page: regenerate the map before answering "is it still working".
- `--no-windows` skips the session records. Nothing is sent anywhere. The window names and the latest request typed into each window end up in the generated page, so mention that if the user is about to share the page.

When the user asks what "this window" did and several windows are at work, find this session in the list by its name and report that row. When the list shows that another window has changed a file this session is about to change, tell the user; what to do about it is theirs to decide.

## What to do, and when

- **The user asks which window is doing what, which one is waiting on them, or whether two windows are in each other's way** ("哪个窗口在等我", "这几个窗口有没有撞车"): `bearings.py windows`, or regenerate the map. Answer with the windows' names as shown, and for a collision name the file or the part and the two windows.
