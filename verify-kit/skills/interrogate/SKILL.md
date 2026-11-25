---
name: interrogate
description: "Use for \"interrogate\", \"adversarial review\", \"multi-model review\", \"challenge this\", \"stress test this code\", \"find blind spots\", or \"tear this apart\". Adversaries try to break a change or design, and only findings proven by a run survive."
disable-model-invocation: true
---

# Interrogate

Adversaries try to break a change or a design. A finding survives only when a run proves it. Report the findings. Do not apply fixes.

## Frame

The scope is what the user names. Otherwise it is the branch diff from its merge base with the base branch, through the working tree. Restate the intent in your own plain words from the user's message, the commits, and the PR description — covering the goal, the key invariants, and what would count as breaking it. Ask the user when the intent is unclear.

## Fan out

Spawn 2–3 independent adversarial subagents in parallel (using distinct models if your environment supports them, otherwise independent subagents on the session model). Give each adversary its own isolated git worktree (copying any uncommitted changes in scope into each worktree so they never overwrite one another). If worktrees are not possible, give each adversary an isolated scratch directory for its repro scripts.

Give each adversary the scope, the restated intent, and this brief:

> Break this change. Prove each finding with a run against the real code, such as a failing test, a repro script, or command output that shows the wrong behavior. For a design or plan, run a prototype or probe the current tree. Keep repros in your own worktree. Report each finding with a title, the exact command, the output it printed, and the output the intent requires. Leave out anything you did not run. That covers style, naming, structure, and risks that need a future change to matter. No findings is a valid result.

If an adversary produces no output, proceed with the remaining adversaries and note the dropout.

## Verify

Verify every reported finding yourself by rerunning its exact command against the real code. Keep a finding only when the output reproduces the failure and that failure breaks the stated intent. Drop everything else (unrun claims, style nits, speculative risks, or failures that do not violate the intent). Merge findings that share a root cause, keeping all distinct verified failures across adversaries.

Clean up any temporary worktrees or scratch repros created during the review.

## Output

- **Intent**: the plain-word restatement.
- **Findings**: for each verified finding, the command, its output, how it breaks the intent, and which adversaries found it. Say "no verified findings" when none survive.
- **Dropped**: for each adversary, the count of dropped findings and why.
