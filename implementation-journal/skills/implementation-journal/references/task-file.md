# The Task File

One file per task: `docs/tasks/<YYYY-MM-DD>-<slug>.md`. The date is the day the task was opened and never changes.

## Template

```markdown
---
status: Open
updated: 2026-11-14
---

# Partial refunds

## For People

Name: Refunds
Now: Whole orders can be refunded. Refunding only some items is not built yet; the rules are settled.
Needs you: Decide whether a refund reason must be given
Next: Build refunds for part of an order.
Done: Staff can refund a whole order, shipping included.
Not yet: Refunding only some of the items

## Decided

- 2026-11-09, user: a partial refund gives back the items only. The refund that returns the last items of an order also gives back the shipping. Not proportional.
- 2026-11-09, outside limit: the payment provider accepts at most 3 refunds against one charge and freezes the charge for a day on a 4th. Refuse a 4th before sending it.
- Guess: the provider counts a failed refund against the limit. Not confirmed; check this first if refunds start being refused early.
- Waiting on the user: whether a reason is required. Until they answer it stays optional; do not make it required and do not remove it.

## Next

1. Add `refund_items(order, lines, reason="")`.
2. Refuse quantities beyond what is left, and unknown items.
3. Check: `python3 tests/run.py` passes with the new tests.
```

## The header

- `status:` is `Open` or `Complete`. A task is open until its record says `Complete`; that word is what takes it off the list a new session sees and moves it to "finished" on the map.
- `updated:` is the date of the last change to the record, as `YYYY-MM-DD`. Dates in the file are always absolute, never "today" or "last week".
- The `#` heading names the task for someone reading the folder.

## For People

The record is written for the next AI session, with this one exception. The project map shows this section to the person steering the work: what the task is called, where it stands, and what is waiting on them. People who build with AI rarely open a task file, so this section is often the only way they learn that the work has stopped for them.

- Write it in the language the user works in, for a reader who may not be able to program. No file names, code names, commit hashes or commands, and no backticks. Where it names a part of the project, use the name the `bearings` parts list gives it.
- `Name:` is what the person would call this task, in a few words. Keep it the same from one update to the next: they use it to ask for the task ("continue the voice assistant").
- `Now:` says where the task stands in one or two sentences, in terms of what someone using the project would notice ("it is live but switched off"), not in terms of the code.
- `Needs you:` has one line for each thing the work is waiting on the person for: a decision, a check only they can make, an approval. Say what they should do. When nothing is waiting, write no such line; never "None". When one has been answered, remove it.
- `Next:` is one sentence on what happens once those are answered.
- The keys may be written in Chinese instead (`名字：` `现在：` `等你：` `下一步：`); the map reads either.

When the session finished a step a person could notice (something they can now do, see or try), the section also says what that step came to. The map turns these lines into a page of words and pictures, and for a finished task it is all that remains on the map. Leave them out for a session that only investigated or planned.

- `Done:` says what a person can now do or see, in one or two sentences. Not what was written or refactored.
- `Try:` says how they can see it for themselves, in steps they can follow without a terminal where that is possible. Leave it out when there is honestly nothing for them to try.
- `Not yet:` has one line for each thing a person might assume is done and is not (not committed, switched off, never tried with a real user). At most three, the ones that would surprise them most. No line when there is none.
- `Added:`, `Changed:` and `Removed:` mark boxes on the flow diagrams of the parts list: `Part / Box: one sentence on what is different`, or `Part / Room / Box: ...` for a room's diagram. The map draws that diagram with the marked boxes standing out. Rules for marks:
  - First update the parts list if the step changed how a part works. Then read the part's flow diagram as it now stands and write marks against the boxes it has, by their exact names. A mark whose name misses is shown as words only.
  - Mark what works differently for the person or the data passing through, not every box whose code was edited. Three to six marks is typical; a fix or a setting change usually has none.
  - `Removed:` names a box that was taken off the diagram, or a thing that was tried and dropped; say why in the sentence.
  - A line that names only a part (`Changed: Deployment: two new settings`) is fine when no box fits.
- These lines describe the last finished step. Replace them when a later step finishes; do not let them pile up. When the task is marked `Complete`, rewrite them to describe the task as a whole.
- When a finished task is opened again, leave the `Done` lines as they are until the new step is finished: they are still what a person can do today.
- Chinese keys: `做成了：` `怎么试：` `还没做：` `新增：` `改了：` `去掉：`.

The map also shows how a task got to where it is (finished, opened again, finished a second time) by reading this file's history from git, so it only sees versions that were committed.

## Decided

One line each: the date and who or what it came from, then the decision in a form the next session can act on, then the reason when it is not obvious. SKILL.md says what belongs here and what does not.

- A line that is no longer true is rewritten or removed, not left with a correction under it.
- When a `Waiting on the user` line is answered, it becomes a dated decision.
- If the section passes a dozen lines, the oldest ones are usually visible in the code by now: remove those.

## Next

A numbered list, most useful step first, each one something the next session can start on without asking. End with how to check that things stand as the record says: one command and what it should show. For a finished task the section says `None`.

## Read budget

The whole file competes for the next session's context and the person's patience. Aim for 300 to 400 words; the validator warns past 80 lines. A longer record usually means `Decided` has started to describe the code.
