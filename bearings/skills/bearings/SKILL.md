---
name: bearings
description: "Help a person understand a project that AI is building, from a first look to its architecture: keep a plain-language list of the project's parts and a flow diagram of how each part works, and turn them into a visual map page (the project as a building of rooms, rooms inside rooms, which part uses which as measured from the code, routes through the whole project, where recent work landed). Use when the user asks to see or understand the project, asks for the project map, asks how a part works, how the parts connect, what depends on what, or what recent work touched, asks which window or session is changing what, asks to set up a parts list, or when finished work changed how a part works and docs/parts.md exists. This skill only describes the project; it never limits how code is written."
---

# Bearings

When AI writes the code, a person stops learning their project as a side effect of writing it. This skill gives them a picture to look at instead: the project as named parts, how each part works, and where work has been landing.

It is for understanding only. It never tells the agent how to write code, which parts to leave alone, or when to stop and ask. Do the coding work exactly as you would without this skill; the skill's only claim on you is to keep the picture true afterwards.

Reply in the language the user works in. The parts list is written in that language too, for a reader who may not be able to program.

## The parts list

`docs/parts.md` is the single source for the picture. The map page is generated from it, from git history and from the code's own import statements; nothing else is stored.

- A `#` heading groups the parts under it into one wing of the map.
- A `##` heading names a part. Its first plain line says what the part is for.
- A `###` heading names a room inside that part (see "Rooms inside a part").
- Backticked bullets are the paths the part owns: `dir/` owns a folder, `*` is a wildcard, the most specific path wins.
- `图标：<name>` or `Icon: <name>` picks its pictogram: mic, speaker, phone, play, book, search, plug, user, card, database, mail, home, grid, spark, layout, lang, cloud, flask, note, lock, box.
- `敏感：<why>` or `Sensitive: <why>` marks a part people should look at with care (money, sign-in, stored data, production settings). It only changes how the part is drawn.
- `规矩：<rule>（<source>，<date>）` or `Rule: ...` shows a rule the project's own documents already state for that part, so a reader can see it. Copy rules; do not invent them, and remove one when the project drops it.

Name parts for what a person sees or does ("Payments and membership"), not for folders ("src/payment"). Ten to twenty parts. The names belong to the user: when drafting a list, ask them to correct the names.

**Where the file lives.** `docs/parts.md` by default. Check first whether the project lints its docs or its Markdown. If the list would break a rule there, use `PARTS.md` in the repo root or `.bearings/parts.md` instead; the script finds any of the three. If the rule is "one top-level heading per file", start the file with a single `#` title and write everything one level deeper (`##` wing, `###` part, `####` room inside); the script recognises that form. A list that cannot be committed is no use to a team, so settle this before writing.

### Rooms inside a part

A part that holds several distinct things (a dozen models, the pages of an app, a framework someone else wrote) gets rooms inside it: `###` headings under the part, each with the same fields as a part (first line, icon, paths, optional flow diagram, rules).

- Give a part rooms when it has more than about 150 files, or when one flow diagram can only show a "typical" case. Three to twelve rooms. Small parts stay flat.
- A room's paths lie inside its part's paths and are more specific (`models/` on the part, `models/higgs/` on the room). Files no room claims stay with the part itself.
- The part keeps the flow diagram of what its rooms have in common; a room's own diagram shows what is particular to it.

### Code from outside

Code copied into the repo but written elsewhere (vendored libraries, third-party frameworks, generated SDKs) is marked `外来：<what it is and where it comes from>` or `Vendored: ...` on the part or room that holds it. It is drawn with a dashed outline, counted apart from the project's own files, and left out of the activity figures, so it cannot make a part look bigger or busier than the project's own work. Look for folders named `third_party`, `vendor`, `external`, and for licence files of other projects.

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
- When a box is another part or room, give it exactly that name. The box becomes a door: it takes that part's colour and pictogram, and a click opens it.

### Routes through the project

A flow block that stands outside every part (put these at the top of the file) is a route: how one thing travels through the whole project. Its title follows the word `flow`:

````text
```flow 一次语音请求
调用方 | 应用或脚本 | user
请求路由器
对外接口
调用方 -> 请求路由器: 请求
请求路由器 -> 对外接口: 转发
```
````

- Write one to three routes, for the things the project exists to do. Most boxes should be parts, named exactly; add a plain box only for whoever starts or ends the route.
- On the page, an arrow between two parts that the code does not connect is drawn dashed. That is correct for links over a network or between languages. If you expected a solid line, check the route against `bearings.py links` before keeping it.

### Which part uses which

Nobody writes this down. The script reads the import statements (Python, JavaScript/TypeScript, Go) and counts, for each pair of parts, how many files in one import from the other. The map draws it as a relation diagram and lists "it uses" and "used by" on every part. `bearings.py links` prints the same numbers; read them before drafting flow diagrams and routes, so the descriptions agree with the code. Other languages and links over a network are not measured; say so when it matters.

## What to do, and when

The script is `scripts/bearings.py` in this skill folder (Claude Code: `${CLAUDE_SKILL_DIR}/scripts/bearings.py`; Codex: `~/.codex/skills/bearings/scripts/bearings.py`). Run it with python3 from inside the repo. It only reads: the project, and, to tell windows apart, the session records Claude Code and Codex keep on this machine.

- **The user wants to see the project** ("show me the project", "open the map", "how does X work"): run `bearings.py web --open`. It writes one HTML page under the repo's git directory and opens it. Say in one sentence what they will see.
- **There is no parts list yet** and the user wants one: read the repo, decide where the list can live, draft it with a flow diagram for each part that has a story to tell, rooms inside the large parts, outside code marked, and one to three routes. Run `bearings.py parts` until no file is unmapped and `bearings.py links` to check the routes, then ask the user to correct the names.
- **You finished work that changed the picture**: a new area of the project, files that `bearings.py parts` reports as unmapped, or a part that now works differently from its flow diagram. Update `docs/parts.md` in the same change and mention it in one line. If the picture is still true, do nothing.
- **The user asks how the parts connect or what depends on what**: `bearings.py links` for the numbers, or open the map on its relation view.
- **The user asks what a piece of work touched**: `bearings.py check` lists the parts the uncommitted work touched; `--commit <rev>` does the same for one past commit, `--since <rev>` for everything after one. Report it using the part names as written.

### Several windows at once

People often run several Claude Code or Codex sessions on one project. `git` cannot say which of them changed a file, so the script reads the session records both tools keep on the machine and splits the uncommitted work by window:

- `bearings.py check` adds a "by window" list when more than one window has uncommitted work: a letter, the window's name (its journal task if it is writing in a `docs/tasks/<task>/` dossier, otherwise the session's title or opening request), and the parts it touched.
- The map shows the same thing as "who is working where", marks each lit room with the letters of the windows in it, and names files two windows both changed. It also counts uncommitted work in the repository's other worktrees.
- A file changed with an edit tool is matched for certain. A file changed by a shell command is matched by time, and only when exactly one window fits. Anything else is listed as having no window on record; say so rather than guessing.
- `--no-windows` skips the session records. Nothing is sent anywhere; the window names end up in the generated page, so mention that if the user is about to share the page.

When the user asks what "this window" did and several windows are at work, find this session in the list by its name and report that row.

## What this skill does not do

It does not plan work, review it, block it, or judge whether a change belonged where it landed. It does not ask the user questions before coding. If a rule shown on the map matters to the work, that is because the project's own guide says so, not because this skill does.
