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

## For People

A dossier is written for the next AI session, with one exception. When the repo has a `bearings` parts list, the handoff opens with a `## For People` section, and the project map shows it to the person steering the work: what the task is called, where it stands, and what is waiting on them. People who build with AI rarely open a handoff, so this section is often the only way they learn that the work has stopped for their answer. The format is in references/templates.md. Rules for the content:

- Write it in the language the user works in, for a reader who may not be able to program. No file names, code names, commit hashes or commands, and no backticks. Where it names a part of the project, use the name the parts list gives it.
- `Name:` is what the person would call this task, in a few words. Keep it the same from one refresh to the next: they use it to ask for the task ("continue the voice assistant").
- `Now:` says where the task stands in one or two sentences, in terms of what someone using the project would notice ("it is live but switched off"), not in terms of the code.
- `Needs you:` has one line for each thing the work is waiting on the person for: a decision, a check only they can make, an approval. Say what they should do. When nothing is waiting, write no such line; never "None". When one has been answered, remove it.
- `Next:` is one sentence on what happens once those are answered.
- The keys may be written in Chinese instead (`名字：` `现在：` `等你：` `下一步：`); the map reads either.

When the session finished a step a person could notice (something they can now do, see or try), the section also says what that step came to. The map turns these lines into a page of words and pictures, and for a finished task it is all that remains on the map. Leave them out for a session that only investigated or planned.

- `Done:` says what a person can now do or see, in one or two sentences. Not what was written or refactored.
- `Try:` says how they can see it for themselves, in steps they can follow without a terminal where that is possible. Leave it out when there is honestly nothing for them to try.
- `Not yet:` has one line for each thing a person might assume is done and is not (not committed, switched off, never tried with a real user). At most three, the ones that would surprise them most; the open follow-ups belong in Next Steps below, not here. No line when there is none.
- `Added:`, `Changed:` and `Removed:` mark boxes on the flow diagrams of the parts list: `Part / Box: one sentence on what is different`, or `Part / Room / Box: ...` for a room's diagram. The map draws that diagram with the marked boxes standing out. Rules for marks:
  - First update the parts list if the step changed how a part works (knowledge-sync.md says when). Then read the part's flow diagram as it now stands and write marks against the boxes it has, by their exact names. A mark whose name misses is shown as words only.
  - Mark what works differently for the person or the data passing through, not every box whose code was edited. Three to six marks is typical; a fix or a setting change usually has none.
  - `Removed:` names a box that was taken off the diagram, or a thing that was tried and dropped; say why in the sentence.
  - A line that names only a part (`Changed: Deployment: two new settings`) is fine when no box fits.
- These lines describe the last finished step. Replace them when a later step finishes; do not let them pile up. When the task is marked Complete, rewrite them to describe the task as a whole.
- Chinese keys: `做成了：` `怎么试：` `还没做：` `新增：` `改了：` `去掉：`.
- After writing marks, check them: load the `bearings` skill if it is available (its SKILL.md gives the path of `bearings.py`) and run `bearings.py tasks`, which reports each mark whose part or box it cannot find. Without that skill, compare each name with the parts list by eye and say you did.

Rewrite the section whenever the handoff is rewritten. It restates the handoff for a different reader and is never a second source of truth: if the two disagree, the sections below it are right and this one is stale.

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
