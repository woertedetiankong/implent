# Document Model

Use this reference when deciding where implementation knowledge should live. Creation conditions live in SKILL.md; this file covers ownership, paths, and shape.

## Layers

| Layer | Audience | Purpose | Edit style |
|---|---|---|---|
| Long-term plan | User, product owner, future agents | Intent, milestones, status dashboard, links to evidence | Living status document |
| Task dossier | Current and next implementer | Work contract and milestone memory | Task-scoped |
| Implementation log | Future implementer debugging decisions | Decisions, constraints, failed paths, validation discoveries | Conditional append-only |
| Handoff | Next human or AI | Current state, what changed, how to continue, how to verify restart reality | Rewrite to current truth |
| New-session entry | Next AI session on this task | Pasteable restart opener: its dossier's handoff pointer, errata, next steps, red lines, first verify | One per dossier; lightweight current pointer |
| README/docs | New users/operators/integrators | How to run, use, integrate, and operate | Rewrite to current truth |
| AGENTS/CLAUDE | Agents working in the repo | Project conventions and non-obvious guardrails | Concise current guidance |

## Default Paths

Use existing repo conventions first. If none exist:

```text
docs/tasks/<YYYY-MM-DD>-<slug>/task-brief.md
docs/tasks/<YYYY-MM-DD>-<slug>/implementation-log.md
docs/tasks/<YYYY-MM-DD>-<slug>/handoff.md
docs/tasks/<YYYY-MM-DD>-<slug>/next-session.md
```

Use lowercase hyphenated slugs. Prefer the milestone outcome over an implementation detail, such as `auth-device-flow` rather than `add-routes`.

## Long-Term Plan

The plan should answer: what is being built, why it matters, what milestones exist, and what status each milestone has. Keep it brief and link out to task dossiers or handoffs for evidence. Do not duplicate implementation details from the task dossier into the plan.

The plan's status area is the human owner's dashboard. At AI speed the owner manages by reviewing decisions and steering direction, not by reading code, so the dashboard must answer in one skim: where does each milestone stand, what needs my judgment, what was just decided for me, and what could hurt. When the plan lives in this repo, keep a `## Status Dashboard` section in it using the template in references/templates.md:

- Milestone table: one row per milestone with status, absolute date, evidence link (dossier at start, handoff at completion), and a short note.
- Needs your judgment: open questions that block or steer direction, each linking to the dossier or handoff holding the detail, with the consequence of leaving it unanswered. This is the only place such questions accumulate for the human; remove entries the moment they are answered and record the answer as a closed decision.
- Recently closed decisions: dated one-liners with links, newest first. Prune entries older than the last few milestones — full history lives in implementation logs.
- Top risks: only risks the owner can act on, not an exhaustive register.

The dashboard compiles pointers, not state: operational state stays in handoffs and rationale in logs, so it never becomes a competing authority. When the plan lives outside the repo (issue tracker, external doc), update status there in its native format and do not bootstrap an in-repo dashboard on your own judgment.

When a slice starts, mark it `In progress` with an absolute date and link to the task dossier. When it completes, mark it `Done` with an absolute date and link to the handoff. When it is abandoned or replaced, mark that explicitly and link to the log entry explaining why.

## Task Dossier

`task-brief.md` is the contract. It should include the selected slice, success criteria, scope, constraints, source plan link, and expected docs touchpoints.

`implementation-log.md` is a conditional decision log; the triggers that justify creating it live in SKILL.md. It is append-only except for removing accidental secrets or obvious noise. Do not rewrite history after a plan changes; add a new entry explaining the change. The handoff always declares whether a log exists (references/handoff-discipline.md).

`handoff.md` is the takeover document. Rewrite it near completion so it is short, accurate, and useful without reading the whole log. references/handoff-discipline.md defines the required fields.

Use stable relative links when one module references another module's dossier, handoff, or docs. Prefer a predictable shape:

```markdown
- Depends on: [auth device flow](../2026-06-10-auth-device-flow/handoff.md) - token contract
- Referenced by: [billing import](../2026-06-12-billing-import/handoff.md) - user identity mapping
```

The new-session entry is the first landing point for a new chat on that task. It lives in the dossier as `next-session.md`, so tasks that are open at the same time each keep their own. Its role and rules live in references/handoff-discipline.md.

## Docs The Journal Does Not Own

Durable knowledge goes into the README and the docs the repo already has. Do not start a wiki on your own judgment; if the repo already keeps a hand-maintained one, treat its pages like any other docs.

A wiki maintained by an automated documenter (for example `openwiki/`, generated and refreshed by the OpenWiki CLI and its CI runs) is not journal territory. It describes what the code is and its own updater owns it: read it as context, never hand-reconcile into it, and do not duplicate its code-derivable facts into other docs. Decisions, constraints, and other knowledge not derivable from code still go to the journal's own targets: dossiers, logs, and README/docs.

The `bearings` parts list (`docs/parts.md`, or `PARTS.md` / `.bearings/parts.md` where the project keeps it), when a repo has one, is a doc like any other for this purpose: it is the picture people read, and it is updated when a part's paths or way of working changed.
