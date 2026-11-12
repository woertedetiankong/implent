---
name: implementation-journal
description: "Maintain cross-session implementation memory for milestone-sized coding work, so the next AI session can pick up where this one stopped: a plan-linked task dossier, a decisions-only implementation log, a restart-ready handoff, and reconciliation of durable knowledge into the project docs. Use when work spans sessions, touches multiple modules or architecture, or when the user asks for implementation notes, handoff or restart docs, task dossiers, decision logging, knowledge reconciliation, or phase-complete cleanup. Do not use for single-session fixes that need no continuity."
---

# Implementation Journal

Use this skill to make long-running AI-assisted development compound instead of evaporating into chat history. The job is not to keep a command transcript. The job is to connect a plan, the current milestone, the implementation reasoning, the restart handoff, and the project docs.

These records are written for the next AI session. They are not the way a person gets to understand the project; for that, the companion skill `bearings` draws the project as a map with a flow diagram per part.

## Core Rule

For ordinary small fixes, do not create ceremony unless the user asks for it. For milestone-sized work, create or update a task dossier, log meaningful implementation decisions only when there is a real decision trail to preserve, keep restart continuity current, and finish by reconciling what became true back into the plan and docs.

Existing project conventions win. If the repo already has task folders, decision records, wiki pages, or handoff docs, use those names and locations instead of the defaults below.

## Documents

Creation conditions live in this file only; the references hold formats and field-level guidance.

- Long-term plan: an existing roadmap, issue, goal brief, plan document, or user-provided plan. Do not invent a roadmap when the user only asked for one slice; if none exists, set `Parent plan: None found` in the task brief. When the plan lives in this repo, maintain its status dashboard (references/document-model.md); never bootstrap a dashboard for an external plan.
- Task dossier at `docs/tasks/<YYYY-MM-DD>-<slug>/` for milestone-sized work:
  - `task-brief.md`: the contract for this slice.
  - `implementation-log.md`: append-only decision log, started at the first log trigger (workflow step 3).
  - `handoff.md`: rewritten near completion so the next human or AI can continue without reading the whole log.
- New-session entry at `docs/tasks/NEXT-SESSION.md`, or the repo's existing session/todo file: a short pasteable restart opener plus errata pointing at the latest handoff — never a second status document.

That is the whole set. Do not add an index of dossiers, a wiki, or a summary page on your own judgment: every extra file is one more place that goes stale. The dated dossier folders are the index. A repo that already keeps such files falls under "existing project conventions win".

## Goal Brief Input

`goal-brief-builder` is an optional upstream skill, not a dependency. If a `goal-brief-*.md`, `/goal` brief, issue brief, or similar execution brief exists, treat it as the parent plan and source of intent. Extract only the current slice, success criteria, constraints, forbidden shortcuts, validation expectations, and expected docs updates; do not copy the whole brief into `task-brief.md`, and do not run a goal-brief interview from this skill unless the request is too ambiguous or risky to implement safely.

Read [references/document-model.md](references/document-model.md) when choosing artifact paths or deciding which document owns a piece of knowledge.
Read [references/handoff-discipline.md](references/handoff-discipline.md) before creating or refreshing a handoff or new-session entry.
Read [references/templates.md](references/templates.md) before creating new documents.
Read [references/knowledge-sync.md](references/knowledge-sync.md) before end-of-stage cleanup or docs reconciliation.

## Workflow

1. Ground in the plan and repo.
   - Locate the long-term plan or the most specific source of intent.
   - Discover existing conventions before creating files: task folders, handoffs, session entries, todo files, decision records, roadmap docs, README, AGENTS/CLAUDE, and docs directories.
   - Identify the current slice, success criteria, scope, constraints, and known affected docs. For multi-module work, identify upstream/downstream modules and existing dossiers that may reference the changed contract.
   - If the milestone is too large to finish safely in one implementation pass, carve out the smallest coherent sub-slice that preserves the milestone intent, record it in `task-brief.md`, and ask for confirmation only when the slice boundary changes user-visible scope or risk.

2. Create or update the task dossier.
   - Keep `task-brief.md` current when scope or acceptance criteria materially change.
   - Link the dossier from the long-term plan when one exists.

3. Log implementation memory when a log trigger occurs.
   - Log triggers: behavior chosen for an ambiguous spec, hidden constraint discovered, approach abandoned, tradeoff made, intentional deviation from the plan, validation that changed understanding, risk or follow-up identified, or cross-session reasoning that would be hard to reconstruct.
   - Create `implementation-log.md` at the first trigger. Milestone-sized work almost always has one; in the rare case it does not, the handoff says so (references/handoff-discipline.md) instead of inventing entries.
   - When a logged decision lands in code, record the commit hash or PR number in the entry so future debugging can jump from the decision to the diff.
   - Do not log file-opening commands, obvious edits, or narration that merely says "implemented X".
   - After each verified work unit (passing tests, a commit, a settled decision, a new risk), write back progress, evidence, and changed next steps. Do not wait until the end of the chat if the state has materially changed.
   - When a confirmed discovery affects shared contracts, architecture rules, integration behavior, or future slices, update the relevant docs immediately if another active or upcoming module may depend on it. Use a clearly named durable-knowledge follow-up only when the fact needs user confirmation, would expand scope, or cannot be safely edited now.
   - Use absolute dates such as `2026-06-10`; never relative dates such as "today" or "recently".

4. Refresh the handoff before any planned pause, final response, commit, or phase completion.
   - Rewrite `handoff.md` to reflect the final code state and current next steps, following references/handoff-discipline.md. Mark it provisional if implementation or validation is intentionally incomplete.
   - Refresh the new-session entry so it points at the latest handoff. If part of the handoff is already stale, record the correction as errata in the entry instead of silently rewriting history.

5. Reconcile durable knowledge.
   - Update the long-term plan status for the slice with absolute dates and links to the dossier or handoff. For an in-repo plan, refresh its status dashboard per references/document-model.md.
   - Update README, AGENTS/CLAUDE guidance, and docs that now describe stale behavior: merge duplicates, rewrite outdated sections, delete superseded claims. Replace a stale instruction; never leave it in place with a correction appended underneath. Preserve important history in the implementation log or a decision record, not in current-facing docs.
   - Run the cleanup loop in references/knowledge-sync.md: inventory likely stale docs, classify each as rewrite/merge/delete/keep, edit, then rerun targeted searches for the old commands, names, routes, or claims.
   - When the repo has a parts list for the `bearings` map (`docs/parts.md`) and this work changed how a part works or added a new area, update that part's paths and flow diagram there. It is the picture people read, so it goes stale the same way a README does.

## Quality Gate

Before finishing a milestone, run the mechanical check, then judge what it cannot see.

Run [scripts/validate_journal.py](scripts/validate_journal.py) with python3 from the repo root (in Claude Code the path is `${CLAUDE_SKILL_DIR}/scripts/validate_journal.py`), passing the repo's tasks dir or the touched dossier files — plus any reconciled docs, so the relative-date and broken-link checks cover them. Fix every ERROR and rerun until clean. Accept a WARN only deliberately and name it in the final response. If python3 is unavailable, say so and apply the same checks by hand.

Then check by judgment, since the script checks presence and shape, not truth:

- `handoff.md` reflects the actual final code state (or is clearly marked provisional), and its restart verify expected-outputs are truthful.
- `implementation-log.md` holds decisions, not narration.
- The new-session entry points to the latest handoff, not merely to one that exists.
- Current-facing docs contain no stale claims about the changed behavior, and the long-term plan status (including an in-repo dashboard) is updated when a parent plan exists.

## Final Response

State the dossier path, the handoff path and whether it is complete or provisional, and which docs were reconciled. If no dossier or implementation log was created, say why in one sentence.
