---
description: Generate this project's map page and open it in a browser
allowed-tools: Bash(python3:*)
---

!`python3 "${CLAUDE_PLUGIN_ROOT}/skills/bearings/scripts/bearings.py" web --open 2>&1`

The lines above are the output of generating the project map and opening it in a browser. Reply in one or two sentences, in the language the user works in: which page opened, or, if it failed, what that means. A message about a missing parts list means this project has no `docs/parts.md` yet; offer to draft one with the bearings skill. "not inside a git repository" means the command was run outside a project. Do not run any other command.
