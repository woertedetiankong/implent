# Handoff Discipline

Use this reference when creating or refreshing a cross-session handoff. The goal is restart continuity: a new human or AI session should know what is true, what to verify first, what to do next, and what not to touch.

## Two-Layer Model

1. `handoff.md`: the authority for the current milestone state.
2. New-session entry: a short pasteable restart opener, `next-session.md` in the same dossier. It points to that dossier's handoff, records errata when a handoff section became stale, and compresses the immediate next steps, red lines, and first verify command into a first message for the next session on this task.

Keep the layers distinct. The entry is a launch instruction and errata layer, not a second handoff; state details live in the handoff.

## Read Budget

The handoff competes for two scarce budgets: the next session's context window and the human's skim time. Target about 100 lines; the validator warns past that. When a handoff grows longer, move narrative and history into `implementation-log.md` and link it; the handoff keeps conclusions and pointers.

## Handoff Fields

Always present, even when the content is one line:

- Summary: what changed and why.
- Current state: one sentence saying where the milestone stands.
- Git and persistent state: branch, key commit hashes, PR state, unpushed work, generated artifacts, migrations, or external state that matters.
- Validation: what changed and the proof, such as commits, test results, manual checks, review findings, or produced artifacts. Required when status is Complete; a Provisional handoff may omit it only when no checks ran yet.
- Next backlog by ROI: the next actions in priority order, with short reasons.
- Restart verify: commands or checks that can be run first, with expected output and what a mismatch means.
- Implementation log declaration: a pointer to `implementation-log.md`, or `Not required - <reason>` in the rare case no log trigger occurred. Absence is ambiguous, so this line is never omitted.

Present only when they carry real content — omit the section instead of writing "None" or "None known"; the validator flags placeholder-only sections:

- Environment state: special local/runtime state that changes the safe next action, such as the current checkout driving production hooks, a required service already running, or a temporary data snapshot in use.
- Key decisions and closed decisions: rejected options with one-line reasons, labeled so future agents do not reopen them accidentally.
- Changed surfaces: paths or subsystems and the role of each change.
- Cross-module references: stable links to upstream dependencies and downstream dependents. Not optional when the work touches module boundaries or shared contracts.
- Red lines and gotchas: enforceable instructions ("do not push without user approval") and non-obvious services, env vars, data safety rules, or operational hazards.
- Docs sync: what durable knowledge was updated, skipped, or still needs reconciliation. When omitted, the final response must still state the reconciliation outcome.
- Known risks and follow-ups.

## Restart Verify

Make verification concrete enough to run immediately:

```bash
<command 1>  # expected: <observable output>; mismatch means: <diagnosis>
<command 2>  # expected: <observable output>; mismatch means: <diagnosis>
```

Prefer checks that anchor reality: `git log --oneline -2`, branch/status checks, targeted tests, schema/version checks, row counts, generated file hashes, service health endpoints, or CLI dry runs.

Do not write "verify manually" when a command would be more precise. If validation is manual, state the exact screen, file, API response, or artifact to inspect.

## New-Session Entry

The format lives in references/templates.md. Rules for the content:

- It must work when pasted as the first message of a new session.
- Write red lines as commands the agent can obey. "Be careful" is not enforceable; "do not push until the user explicitly says push" is enforceable.
- One entry per dossier, never one for the whole repo: tasks that are open at the same time must not share a file. A repo-level `docs/tasks/NEXT-SESSION.md` left from the older single-entry layout is moved into the dossier it points at (as `next-session.md`) the next time that dossier's entry is refreshed.
- When a new handoff supersedes the old one, rewrite the entry. Keep older entries only if the repo already preserves historical entries; otherwise link history from the handoff chain.

## Evidence

Do not mark work done without evidence. If tests were not run, say so. If a PR is not merged, do not write that it is merged.

## History And Knowledge Boundaries

For handoffs, prefer rewriting to current truth near completion; if preserving historical handoff snapshots is a project convention, create a new handoff and link it with `supersedes`. The implementation log is append-only (references/document-model.md).

Handoff stores operational state needed for the next session. Durable lessons, reusable architecture knowledge, integration contracts, and conventions belong in README, docs, or decision records.
