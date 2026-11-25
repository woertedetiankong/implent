#!/usr/bin/env bash
# PostToolUse hook for the implementation-journal skill.
#
# The first time a session edits a file, tells it what earlier tasks decided
# about that file. It only tells: the edit is not blocked or undone. The logic,
# and the reasons for it, are in decided_on_edit.py beside this file.
#
# Exits 0 silently when this machine has no Python 3, or the project has no
# journal, so a global install is safe.
# Registered automatically by the Claude Code plugin (hooks/hooks.json);
# for a plain skill install, see hooks/README.md.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$here/python.sh"
[ -n "$py" ] || exit 0
exec "$py" "$here/decided_on_edit.py"
