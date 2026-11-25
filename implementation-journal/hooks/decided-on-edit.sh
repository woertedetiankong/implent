#!/usr/bin/env bash
# PostToolUse hook for the implementation-journal skill.
#
# The first time a session edits a file, tells it what earlier tasks decided
# about that file. It only tells: the edit is not blocked or undone. The logic,
# and the reasons for it, are in decided_on_edit.py beside this file.
#
# Exits 0 silently when the file's repository has no task records, so a global
# install is safe.
# Registered automatically by the Claude Code plugin (hooks/hooks.json);
# for a plain skill install, see hooks/README.md.
set -uo pipefail
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/decided_on_edit.py"
