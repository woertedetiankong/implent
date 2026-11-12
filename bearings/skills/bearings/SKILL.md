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
- Each level is drawn with the boxes of the level below it. A route's boxes are parts. The diagram of a part that has rooms uses those rooms as its boxes, named exactly so they become doors, plus whoever starts and ends the story: it shows how the rooms work together. A room's diagram shows the steps inside that room. If a part's diagram and one of its rooms' diagrams tell the same story, the part's is drawn at the wrong level; redraw it with rooms as boxes.
- A room's own flow diagram is drawn when someone asks for it, not in the first draft. Listing a room (name, first line, icon, paths) is cheap and already gives the reader the inner floor plan and the measured links between rooms. Drawing how it works inside means reading its code, and a diagram drawn in a hurry is worse than none. A reader opens a few rooms, not all of them; the page shows each undrawn room with its measured links and the sentence to say to have it drawn.
- When asked for one, read the room's code first. Usually three to six boxes: what comes in, the steps particular to this room, what goes out. A room that is only a collection (assets, pages of documentation, folders of tests, outside code) needs none; say so instead of inventing a story.

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

Nobody writes this down. The script reads the import statements (Python, JavaScript/TypeScript, Go) and counts, for each pair of parts, how many files in one import from the other. The map draws it as a relation diagram and lists "it uses" and "used by" on every part. `bearings.py links` prints the same numbers; read them before drafting flow diagrams and routes, so the descriptions agree with the code. Other languages and links over a network are not measured; say so when it matters. It counts only an import it can pin to one file: a name that several files in the repo could answer to, or a lone script in a folder the importing file neither sits under nor adds to `sys.path` itself, is left out rather than guessed, so a link you know exists can be missing while a link that is listed is real.

## What to do, and when

The script is `scripts/bearings.py` in this skill folder (Claude Code: `${CLAUDE_SKILL_DIR}/scripts/bearings.py`; Codex: `~/.codex/skills/bearings/scripts/bearings.py`). Run it with python3 from inside the repo; `bearings.py --help` prints every keyword of the list format, so there is no need to read the script. It only reads: the project, and, to tell windows apart, the session records Claude Code and Codex keep on this machine.

- **The user wants to see the project** ("show me the project", "open the map", "how does X work"): run `bearings.py web --open`. It writes one HTML page under the repo's git directory and opens it. Say in one sentence what they will see.
- **There is no parts list yet** and the user wants one. The first draft is the parts, done well; rooms are only listed.
  1. Read the repo and decide where the list can live.
  2. Write the parts with their paths, list the rooms inside the large parts, mark outside code. Run `bearings.py parts` until no file is unmapped.
  3. Run `bearings.py links`, then draw a flow diagram for each part that has a story to tell (a part with rooms uses its rooms as the boxes) and one to three routes. Spend the time here: read the code behind each diagram rather than guessing from file names.
  4. Run `bearings.py doctor` and fix what it reports.
  5. Tell the user what you made, how many rooms have no diagram of their own yet and that they can ask for any of them, which choices were yours, and ask them to correct the names.
- **The user asks how a room works, or asks for a room's diagram** ("给“运行循环”画流程图"): read that room's code, draw its diagram, regenerate the map. Do the same for a part that has none.
- **You finished work that changed the picture**: a new area of the project, files that `bearings.py parts` reports as unmapped, or a part that now works differently from its flow diagram. Update the parts list in the same change and mention it in one line. If the picture is still true, do nothing. The page tells the reader when each diagram was drawn and how often the code has changed since, so a diagram you leave stale will show as such.
- **The user asks to put the unmapped files on the map** ("把没归类的文件补进清单"; the page prints this sentence when uncommitted work lies in files no part owns): `bearings.py parts --all` lists them. Give each file to the part it belongs to by widening that part's paths. When they form a new area of the project, add a part or a room for it, with its first line and icon. Rerun until no file is unmapped, then regenerate the map.
- **The user asks for all the missing flow diagrams**: `bearings.py parts` lists every part and room without one. Say how many there are before starting, since each one means reading code. Skip the ones that are only collections and say so.
- **The user asks whether the map is still right**, or you have just changed the list: run `bearings.py doctor`. It finds paths that no longer match any file, box names that just miss a part's name, a part whose diagram ignores its own rooms, route arrows the code does not back, and diagrams drawn long before the code last changed. It only reports. It cannot tell whether a diagram is true: for that, reread the code and redraw.
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
