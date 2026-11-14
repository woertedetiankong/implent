#!/usr/bin/env bash
# PostToolUse hook for the implementation-journal skill.
#
# After Edit/Write to a file under docs/tasks/, run the skill's
# scripts/validate_journal.py on that file and feed ERROR lines back to
# Claude immediately (PostToolUse exit code 2 sends stderr to the model;
# the edit itself is not blocked). The validator passes over a Markdown file
# that is not a task record, so other files kept in that folder are left
# alone. Warnings are left to the check before finishing, so drafting is not
# nagged mid-flow.
#
# Repos that keep dossiers elsewhere: adjust the case pattern below.
# Registered automatically by the Claude Code plugin (hooks/hooks.json);
# for a plain skill install, see hooks/README.md.
set -uo pipefail

payload=$(cat)

file=$(printf '%s' "$payload" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d.get("tool_input", {}).get("file_path", ""))
' 2>/dev/null || true)

case "$file" in
  */docs/tasks/*.md) [ -f "$file" ] || exit 0 ;;
  *) exit 0 ;;
esac

script="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/skills/implementation-journal/scripts/validate_journal.py"
errors=$(python3 "$script" "$file" 2>/dev/null | grep ' ERROR ' || true)
[ -z "$errors" ] && exit 0

{
  echo "implementation-journal validator found errors in $file:"
  echo "$errors"
} >&2
exit 2
