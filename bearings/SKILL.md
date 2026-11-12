---
name: bearings
description: "Help a person understand a project that AI is building: keep a plain-language list of the project's parts and a flow diagram of how each part works, and turn them into a visual map page (the project as a building of rooms, each room's flow diagram, where recent work landed). Use when the user asks to see or understand the project, asks for the project map, asks how a part works or what recent work touched, asks to set up a parts list, or when finished work changed how a part works and docs/parts.md exists. This skill only describes the project; it never limits how code is written."
---

# Bearings

When AI writes the code, a person stops learning their project as a side effect of writing it. This skill gives them a picture to look at instead: the project as named parts, how each part works, and where work has been landing.

It is for understanding only. It never tells the agent how to write code, which parts to leave alone, or when to stop and ask. Do the coding work exactly as you would without this skill; the skill's only claim on you is to keep the picture true afterwards.

Reply in the language the user works in. The parts list is written in that language too, for a reader who may not be able to program.

## The parts list

`docs/parts.md` is the single source for the picture. The map page is generated from it and from git history; nothing else is stored.

- A `#` heading groups the parts under it into one wing of the map.
- A `##` heading names a part. Its first plain line says what the part is for.
- Backticked bullets are the paths the part owns: `dir/` owns a folder, `*` is a wildcard, the most specific path wins.
- `图标：<name>` or `Icon: <name>` picks its pictogram: mic, speaker, phone, play, book, search, plug, user, card, database, mail, home, grid, spark, layout, lang, cloud, flask, note, lock, box.
- `敏感：<why>` or `Sensitive: <why>` marks a part people should look at with care (money, sign-in, stored data, production settings). It only changes how the part is drawn.
- `规矩：<rule>（<source>，<date>）` or `Rule: ...` shows a rule the project's own documents already state for that part, so a reader can see it. Copy rules; do not invent them, and remove one when the project drops it.

Name parts for what a person sees or does ("Payments and membership"), not for folders ("src/payment"). Ten to twenty parts. The names belong to the user: when drafting a list, ask them to correct the names.

### Flow diagrams

A part can carry a flow diagram of how it works, as a fenced block whose language is `flow`. It is the main thing a reader sees when they open a part:

````text
```flow
学员 | 对着麦克风说话 | user
耳朵 | 语音识别 | mic | 外部
学员 -> 耳朵: 声音
大脑 <-> 课程知识检索: 查这门课
```
````

- `A -> B: label` is an arrow, `<->` points both ways. `Name | small note | icon | 外部` describes a box; `外部` (or `external`) marks a service outside the project and draws it dashed.
- Tell it as one story from left to right: who starts, what passes along, who ends up with what. Five to nine boxes. If the story returns to where it started, end on a new box ("the learner hears the answer") rather than an arrow back.
- Box names of at most eight characters or three words, in plain words ("the ears", not the class name); arrow labels of at most six characters or two words; notes of one short clause.
- Draw only what the code and docs show.

## What to do, and when

The script is `scripts/bearings.py` in this skill folder (Claude Code: `${CLAUDE_SKILL_DIR}/scripts/bearings.py`). Run it with python3 from inside the repo. It only reads the project.

- **The user wants to see the project** ("show me the project", "open the map", "how does X work"): run `bearings.py web --open`. It writes one HTML page under the repo's git directory and opens it. Say in one sentence what they will see.
- **There is no parts list yet** and the user wants one: read the repo, draft `docs/parts.md` with a flow diagram for each part that has a story to tell, run `bearings.py parts` until no file is unmapped, then ask the user to correct the names.
- **You finished work that changed the picture**: a new area of the project, files that `bearings.py parts` reports as unmapped, or a part that now works differently from its flow diagram. Update `docs/parts.md` in the same change and mention it in one line. If the picture is still true, do nothing.
- **The user asks what a piece of work touched**: `bearings.py check` lists the parts the uncommitted work touched; `--commit <rev>` does the same for one past commit, `--since <rev>` for everything after one. Report it using the part names as written.

## What this skill does not do

It does not plan work, review it, block it, or judge whether a change belonged where it landed. It does not ask the user questions before coding. If a rule shown on the map matters to the work, that is because the project's own guide says so, not because this skill does.
