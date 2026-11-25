#!/usr/bin/env bash
# PostToolUse hook for the implementation-journal skill.
#
# After Edit/Write to a task record under docs/tasks/, feeds the validator's
# ERROR lines back to the session; the edit itself is not blocked. The logic is
# in post_edit_validate.py beside this file.
#
# Exits 0 silently when this machine has no Python 3, or the project has no
# journal, so a global install is safe.
# Registered automatically by the Claude Code plugin (hooks/hooks.json);
# for a plain skill install, see hooks/README.md.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$here/python.sh"
[ -n "$py" ] || exit 0
exec "$py" "$here/post_edit_validate.py"
