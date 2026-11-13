# Templates

Use these templates only when the repo has no established equivalent.

## Task Brief

```markdown
# Task Brief: <Milestone Name>

> Created: <YYYY-MM-DD>
> Parent plan: <link or "None found">
> Status: In progress

## Goal

<One concrete sentence describing this slice of work.>

## Success Criteria

- <Verifiable criterion>
- <Verifiable criterion>

## Scope

In scope:
- <Area>

Out of scope:
- <Area>

## Constraints

- <Technical, product, compatibility, or process constraint>

## Expected Knowledge Updates

- <Plan and docs pages likely to change, or "Unknown until implementation">
```

## Implementation Log

Start the log at the first log trigger. Do not create an empty implementation log just because a task dossier exists.

```markdown
# Implementation Log

> Created: <YYYY-MM-DD>

## Task

<Brief task statement.>

## Assumptions

- <Assumption or "None yet">

## Initial Approach

- <Starting approach or "To be discovered from the repo">

## Log

### <YYYY-MM-DD>

- <Decision, constraint, failed path, tradeoff, validation discovery, risk, or follow-up.> Commit: <hash or PR once the decision lands in code; omit until then>.
```

## Handoff

Core skeleton — these sections always appear (field rules and the read budget live in references/handoff-discipline.md):

````markdown
---
title: Handoff <YYYY-MM-DD> - <milestone or slice>
status: Complete | Provisional
updated: <YYYY-MM-DD>
supersedes: <previous handoff path, or omit if none>
---

# Handoff

## Summary

<What changed and why.>

## Current State

<One sentence describing where this milestone stands.>

## Git And Persistent State

- Branch: <branch and relevant commit hashes, or "Unknown/not applicable">
- Persistent state: <PRs, migrations, generated artifacts, external state, or "None known">

## Validation

- `<command/check>`: <result>

## Restart Verify

```bash
<command 1>  # expected: <observable output>; mismatch means: <diagnosis>
<command 2>  # expected: <observable output>; mismatch means: <diagnosis>
```

## Next Steps

1. <Next action by ROI and reason, or "None - milestone closed">

## Implementation Log

- <`implementation-log.md` path and summary, or "Not required - no meaningful decision trail occurred">
````

For People — only when the repo has a `bearings` parts list; it goes first, straight after `# Handoff`, written in the user's language (rules in references/handoff-discipline.md). The project map reads these keys. The first four say where the task stands; `Needs you` takes one line per item and is left out when nothing is waiting. The rest say what the last finished step came to and are written only when a step a person could notice was finished; `Not yet` and the three marks take one line per item:

````markdown
## For People

Name: <what the person would call this task>
Now: <where it stands, in one or two plain sentences>
Needs you: <one thing the work is waiting on the person for>
Next: <what happens once those are answered>
Done: <what a person can now do or see>
Try: <how they can see it for themselves>
Not yet: <one thing they might assume is done and is not>
Added: <Part> / <Box on its flow diagram>: <what is new, one sentence>
Changed: <Part> / <Box>: <what is different, one sentence>
Removed: <Part> / <Box>: <what was dropped and why>
````

Conditional sections — include only those with real content, in this order between `Git And Persistent State` and `Validation`; never write one whose only content would be "None" or "None known":

````markdown
## Environment State

<Special local/runtime state that changes the safe next action.>

## Key Decisions

- <Decision and rationale.>

## Closed Decisions / Do Not Reopen

- <Rejected option and one-line reason.>

## Changed Surfaces

- `<path or subsystem>`: <role of the change>

## Cross-Module References

- Depends on: [<module or task>](<relative path to handoff or docs>) - <contract or reason>
- Referenced by: [<module or task>](<relative path to handoff or docs>) - <contract or reason>

## Red Lines And Gotchas

- Red line: <enforceable instruction>
- Gotcha: <environment/data/process hazard>

## Docs

- Rewritten: <docs pages>
- Deleted: <docs pages>
- Created: <docs pages>

## Known Risks

- <Risk>

## Follow-ups

- <Follow-up>
````

## New-Session Entry

Written to `next-session.md` inside the dossier. It doubles as the restart opener: it must work when pasted as the first message of a new session.

```markdown
# Next Session

Project <path> (<name>). Read `<handoff path>` first.
Previous session: <one-sentence result with evidence>.
Errata: <known stale section in the handoff, or "None known">.
Current state: <one-sentence board>.
Environment: <special environment state or "None known">.
Now do: 1. <next step> 2. <next step>.
Red lines: <enforceable instruction>; <enforceable instruction>.
First verify: `<command>` (expected <output>; mismatch means <diagnosis>).
```

## Plan Status Dashboard

Lives inside the in-repo long-term plan; ownership rules in references/document-model.md.

```markdown
## Status Dashboard

> Updated: <YYYY-MM-DD>

| Milestone | Status | Updated | Evidence | Note |
|---|---|---|---|---|
| <milestone> | In progress | <YYYY-MM-DD> | [dossier](<task folder>/task-brief.md) | <short note> |
| <milestone> | Done | <YYYY-MM-DD> | [handoff](<task folder>/handoff.md) | <short note> |

### Needs your judgment

- <question that blocks or steers direction> - [context](<dossier or handoff path>) - <consequence if it stays unanswered>

### Recently closed decisions

- <YYYY-MM-DD> <decision> - <one-line rationale> ([detail](<log or handoff path>))

### Top risks

- <risk the owner can act on> - [detail](<path>)
```

Statuses: `In progress` with a dossier link at start, `Done` with a handoff link at completion, `Blocked` with the blocking question in Needs your judgment, and `Abandoned` or `Replaced` with a log/decision link explaining why. Omit the three subsections when empty, same as conditional handoff sections.
