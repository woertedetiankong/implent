#!/usr/bin/env bash
# SessionStart hook for the implementation-journal skill.
#
# Tells a new session which tasks are open in this repo: one open task gets its
# restart entry injected, several get a short list to choose from. The logic,
# and the reasons for it, are in session_start.py beside this file.
#
# stdout of a SessionStart hook is added to the session's context.
# Exits 0 silently when the project has no journal, so a global install is safe.
# Registered automatically by the Claude Code plugin (hooks/hooks.json);
# for a plain skill install, see hooks/README.md.
set -uo pipefail
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/session_start.py"
