#!/usr/bin/env bash
# SessionStart hook for the implementation-journal skill.
#
# On startup/resume/clear: if the project has a restart entry
# (docs/tasks/NEXT-SESSION.md), inject it into context so the session
# resumes without the user pasting anything.
# On post-compaction starts (source == "compact"): additionally remind the
# session to refresh continuity docs, since compaction is the unplanned
# context loss the skill's "planned pause" workflow cannot catch.
#
# stdout of a SessionStart hook is added to Claude's context.
# Exits 0 silently when the project has no journal — safe to install globally.
# Registered automatically by the Claude Code plugin (hooks/hooks.json);
# for a plain skill install, see hooks/README.md.
set -uo pipefail

payload=$(cat)

get() {
  printf '%s' "$payload" \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('$1',''))" \
    2>/dev/null || true
}

source_val=$(get source)
cwd_val=$(get cwd)
[ -n "$cwd_val" ] || cwd_val="$PWD"

entry="$cwd_val/docs/tasks/NEXT-SESSION.md"
[ -f "$entry" ] || exit 0

if [ "$source_val" = "compact" ]; then
  echo "Context was just compacted. If dossier state changed since the last handoff refresh, refresh handoff.md and the restart entry per the implementation-journal skill before continuing."
  echo
fi

echo "implementation-journal restart entry ($entry):"
echo
cat "$entry"
