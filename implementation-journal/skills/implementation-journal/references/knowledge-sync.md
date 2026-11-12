# Knowledge Sync

Use this reference before finalizing a milestone or cleaning docs.

## Source Order

When sources conflict, prefer:

1. Code, tests, schemas, generated types, and runtime behavior.
2. The accepted user/product decision for intended behavior.
3. Current docs and long-term plans.
4. Implementation logs and chat history.

If code and product intent conflict, document the mismatch as a risk or open question instead of silently choosing one.

## What To Update

| Change discovered | Durable knowledge target |
|---|---|
| New or changed API/route/command | Integration docs, API reference, README examples |
| New environment variable/config | README/setup docs, runbook, AGENTS/CLAUDE if agents need it |
| New data model/schema | Architecture docs, migration notes |
| New architecture decision | Decision record, task handoff |
| Changed user/operator workflow | README, runbook, workflow docs |
| Cross-module contract or shared implementation rule | Architecture docs immediately when confirmed; task handoff cross-module references |
| A part of the project now works differently, or a new area exists | The `bearings` parts list (`docs/parts.md`, or `PARTS.md` / `.bearings/parts.md` where the project keeps it) when the repo has one: that part's paths and flow diagram |
| Deprecated behavior | Remove or rewrite current-facing docs; preserve rationale in log/decision page if useful |
| Validation discovery | Handoff validation section; docs only if durable |
| Follow-up work | Long-term plan backlog or handoff follow-ups, not scattered TODO prose |

## Editing Principles

- Merge before appending. If a current-facing paragraph is now wrong, rewrite it.
- Delete stale final-state claims. A stale claim with a correction underneath is still a trap; replace or remove it, never append.
- Preserve important history in append-only logs or decision records, not in README or topic pages.
- Keep audience boundaries clean: README/docs teach users, AGENTS/CLAUDE guide agents, logs explain how decisions happened.
- Do not update global agent memory for ordinary project details.

## Cleanup Checklist

Before declaring the journal complete:

- Inventory likely affected docs and classify each as `rewrite`, `merge`, `delete`, `create`, or `keep`.
- Search the touched docs for the old name, old command, old route, old environment variable, or old behavior.
- For cross-module changes, search task dossiers, handoffs, and docs for stable links, module names, API names, command names, routes, schema/table names, and contract phrases that may reference the changed surface.
- Check README and docs instructions against package scripts, config files, and actual paths.
- Check AGENTS/CLAUDE claims against the repo.
- If multiple projects were touched or an upstream/downstream contract changed, search dependent project docs too.

## Deletion Policy

Be willing to delete:

- Completed temporary plans that no longer guide work.
- Superseded setup instructions.
- Duplicate summaries that say the same thing less accurately.
- Deprecated TODOs that were completed or rejected.
- Old descriptions of behavior that no longer exists.

Do not delete:

- User-stated requirements that still constrain the work.
- Rationale needed to understand a non-obvious decision.
- Migration or rollback information that operators still need.
- Compliance, audit, or release history unless the user explicitly wants it moved.

When unsure whether a fact is obsolete, mark it as an open question in the handoff and ask the user instead of pretending certainty.
