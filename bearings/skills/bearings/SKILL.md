---
name: bearings
description: "Help a person understand a project that AI is building: keep a plain-language list of its parts, a flow diagram of how each works and the chains of function calls behind them, and turn these into a visual map page. Use when finished work changed how a part works and docs/parts.md exists; when the user asks to see or understand the project, for the project map, the overall framework or architecture, how a part works, an explanation of a part, how the parts connect, what goes in and out of a part, or what depends on what; for a function call chain, which function calls which, what a function takes and gives back, how the code differs between modes, devices or protocols, or notes on a function; what recent work touched, which window or session is changing what, what is being worked on or what is waiting on them; to record a real run of a route or see the values at each step when it runs; or to set up a parts list. This skill only describes the project; it never limits how code is written."
---

# Bearings

When AI writes the code, a person stops learning their project as a side effect of writing it. This skill gives them a picture to look at instead: the project as named parts, how each part works, and where work has been landing.

It is for understanding only. It never tells the agent how to write code, which parts to leave alone, or when to stop and ask. Do the coding work exactly as you would without this skill; the skill's only claim on you is to keep the picture true afterwards.

Reply in the language the user works in. The parts list is written in that language too, for a reader who may not be able to program.

## The parts list

`docs/parts.md` is the single source for the picture of the project's parts. The map page is generated from it, from git history and from the code's own import statements. The call chains are a second description, kept in a file of their own and shown in a view of their own (see [references/calls.md](references/calls.md)); the list says nothing about functions.

- A `#` heading groups the parts under it into one wing of the map. Under it, before its first part, one plain line says what the wing is for, and `图标：` / `Icon:` picks its pictogram.
- A `##` heading names a part. Its first plain line says what the part is for.
- A `###` heading names a room inside that part (see "Rooms inside a part").
- `说明：<sentences>` or `Explain: <sentences>` explains the unit it stands under: a wing, a part or a room. Before the first heading it explains the whole project. One line is one paragraph (see "An explanation for every unit").
- Backticked bullets are the paths the part owns: `dir/` owns a folder, `*` is a wildcard, the most specific path wins.
- `图标：<name>` or `Icon: <name>` picks its pictogram: mic, speaker, phone, play, book, search, plug, user, card, database, mail, home, grid, spark, layout, lang, cloud, flask, note, lock, box.
- `敏感：<why>` or `Sensitive: <why>` marks a part people should look at with care (money, sign-in, stored data, production settings). It only changes how the part is drawn.
- `规矩：<rule>（<source>，<date>）` or `Rule: ...` shows a rule the project's own documents already state for that part, so a reader can see it. Copy rules; do not invent them, and remove one when the project drops it.

Name parts for what a person sees or does ("Payments and membership"), not for folders ("src/payment"). Ten to twenty parts. The names belong to the user: when drafting a list, ask them to correct the names.

### An explanation for every unit

The first line says what a unit is for, in a dozen words. The explanation is what a person reads when they open it and want to understand it: two to four sentences, for a reader who may not be able to program.

- Say what it does in the order it does it, why the project needs it (what would stop working without it), and anything a person should know before asking for a change in it.
- Plain words. No file names, and no code names unless the reader will meet that name on the page; then put it in backticks.
- It adds to the first line and to the diagram; it does not repeat them. If all you can write is the first line again, read more of the code.
- Every wing, every part and every room has one, and the project has one at the top of the file. Only code from outside goes without: its `外来：` line already says what it is.
- When a unit's diagram changes, read its explanation again and bring it along.

**Where the file lives.** `docs/parts.md` by default. Check first whether the project lints its docs or its Markdown. If the list would break a rule there, use `PARTS.md` in the repo root or `.bearings/parts.md` instead; the script finds any of the three. If the rule is "one top-level heading per file", start the file with a single `#` title and write everything one level deeper (`##` wing, `###` part, `####` room inside); the script recognises that form. A list that cannot be committed is no use to a team, so settle this before writing.

### Rooms inside a part

A part that holds several distinct things (a dozen models, the pages of an app, a framework someone else wrote) gets rooms inside it: `###` headings under the part, each with the same fields as a part (first line, icon, paths, optional flow diagram, rules).

- Give a part rooms when it has more than about 150 files, or when one flow diagram can only show a "typical" case. Three to twelve rooms. Small parts stay flat.
- A room's paths lie inside its part's paths and are more specific (`models/` on the part, `models/higgs/` on the room). Files no room claims stay with the part itself.
- The diagram of a part that has rooms uses those rooms as its boxes, named exactly so they become doors, plus what the part connects to: it shows how the rooms work together. A room's diagram shows the steps inside that room. If a part's diagram and one of its rooms' diagrams tell the same story, the part's is drawn at the wrong level; redraw it with rooms as boxes. See "Boxes inside boxes" below.
- A room's own flow diagram is drawn when someone asks for it, not in the first draft. Listing a room (name, first line, icon, paths) is cheap and already gives the reader the inner floor plan and the measured links between rooms. Drawing how it works inside means reading its code, and a diagram drawn in a hurry is worse than none. A reader opens a few rooms, not all of them; the page shows each undrawn room with its measured links and the sentence to say to have it drawn.
- When asked for one, read the room's code first. Usually three to six boxes: what comes in, the steps particular to this room, what goes out. A room that is only a collection (assets, pages of documentation, folders of tests, outside code) needs none; say so instead of inventing a story.

### Code from outside

Code copied into the repo but written elsewhere (vendored libraries, third-party frameworks, generated SDKs) is marked `外来：<what it is and where it comes from>` or `Vendored: ...` on the part or room that holds it. It is drawn with a dashed outline, counted apart from the project's own files, and left out of the activity figures, so it cannot make a part look bigger or busier than the project's own work. Look for folders named `third_party`, `vendor`, `external`, and for licence files of other projects.

### Flow diagrams

A part can carry a flow diagram of how it works, as a fenced block whose language is `flow`. It is the main thing a reader sees when they open a part:

````text
```flow
通话室 | 管这一通电话 | phone
耳朵 | 语音识别 | mic | 外部
看课页面 -> 通话室: 开始练习
通话室 -> 耳朵: 声音
通话室 <-> 课程知识检索: 查这门课
```
````

- `A -> B: label` is an arrow, `<->` points both ways. `Name | small note | icon | 外部` describes a box; `外部` (or `external`) marks a service outside the project and draws it dashed; the icon `user` marks a person.
- The label says what travels along the arrow, in plain words ("the question", "the model's reply"). Every arrow has one. For people who read code, the name the code gives that thing can follow in backticks: ``A -> B: 模型回复 `ModelResponse` `` (a type, a function, an endpoint). The page keeps it behind the fold for coders, and the check-up reports a name that the code at either end no longer holds, so write only names you have seen in the code.
- Tell it as one story from left to right: who starts, what passes along, who ends up with what. Five to nine boxes with arrows, and about a dozen arrows at most. A diagram that needs more is telling two stories: keep the main one, and leave the other to a route or to the diagram one level down. A request and its reply between the same two boxes are one `<->` arrow.
- Box names of at most eight characters or three words, in plain words ("the ears", not the class name); arrow labels of at most six characters or two words; notes of one short clause.
- Draw only what the code and docs show.
- When a box is a wing, a part or a room, give it exactly that name. The box becomes a door: it takes that unit's colour and pictogram, and a click opens it.

### Boxes inside boxes

The project holds wings, a wing holds parts, a part holds rooms. Every level has a diagram, and each is drawn with the boxes of the level below it. Read together they are one wiring, the way a block diagram opens into the block diagram inside a block:

| The diagram of | Where its flow block stands | Its boxes |
|---|---|---|
| the whole project | at the top of the file, before the first heading, with no title | the wings (the parts, when the list has no wings) |
| a wing | under the wing's `#` heading, before its first part, with no title | its parts |
| a part | inside the part | its rooms (its steps, when it has no rooms) |
| a room | inside the room | its steps |

On the page the reader starts at the diagram of the whole project and clicks a box to step into it. The box they opened is drawn as a tinted floor with its name on it; its own boxes sit on the floor; what it connects to stands off the floor, at the start where the story sets out from it and at the end otherwise. Above the diagram the page lists what goes into the box and what comes out, taken from every arrow drawn to it anywhere outside it. So the levels have to agree, and four habits keep them agreeing:

- **Every box is on the diagram of what holds it.** Each wing on the project's diagram, each part on its wing's, each room on its part's. One that is not on the path at run time (tests, documentation, release tooling, a collection of assets) is written as a line of its own with no arrow and a note saying whom it serves: `测试素材 | 图片和假服务，供各组测试取用`. The page puts those on a shelf under the diagram. Do not invent an arrow to get a box off the shelf.
- **A line drawn to a box arrives inside it.** If the level above draws `A -> B`, then B's own diagram shows A at its start, and A's own diagram shows B at its end, wired to the step or room that really deals with it. The neighbour can be named exactly, or as the box that holds it (the wing instead of the part), or as a box inside it.
- **A line drawn out of a box is drawn outside it too.** If a part's diagram reaches another part, the diagram of their wing (or of the project, when they sit in different wings) has that line. Otherwise the reader meets a connection inside that the overview never showed.
- **Outside boxes connect to the unit's own boxes, not to each other.** What happens between two neighbours belongs on the level above.

Draw from the top down: the project's diagram first, then each wing, then each part. That way each diagram starts from the lines the level above has already given it. A box with more than four neighbours on one side is usually standing for too much; name the neighbours one level coarser (the wing instead of its three parts).

When a check-up line says two levels disagree, find out which one is true from the code, and change the other. Removing a line that the code does not have is as good a fix as adding one.

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
- A route walks over the wiring: each of its steps between two parts is a line that the diagram of their wing, or of the project, also has.
- On the page the routes sit under the diagram of the whole project, as "follow one thing through": the reader picks one and its path is drawn. An arrow between two parts that the code does not connect is drawn dashed. That is correct for links over a network or between languages. If you expected a solid line, check the route against `bearings.py links` before keeping it.

### Which part uses which

Nobody writes this down. The script reads the import statements (Python, JavaScript/TypeScript, Go) and the `#include` lines of C and C++, and counts, for each pair of parts, how many files in one import from the other. The map uses it in two places: an arrow between two parts that the code does not back is drawn dashed, and every part's sheet lists "it uses" and "used by". `bearings.py links` prints the same numbers; read them before drafting flow diagrams and routes, so the descriptions agree with the code. Other languages (MATLAB and Simulink models among them) and links over a network are not measured; say so when it matters. For C and C++ a header that several folders each have their own copy of counts only when one copy sits clearly nearer the including file. It counts only an import it can pin to one file: a name that several files in the repo could answer to, or a lone script in a folder the importing file neither sits under nor adds to `sys.path` itself, is left out rather than guessed, so a link you know exists can be missing while a link that is listed is real.

## What else is on the map

The map shows more than the parts and their diagrams. Each of these has a file of its own under `references/` in this skill folder (beside `scripts/`), with its format, its rules, and what to do when asked. Read that file before you write, change or answer anything about its subject. None of it is repeated here.

- [references/calls.md](references/calls.md): **call chains, and a reader's notes on functions.** Which function calls which, a sentence on each, what goes into it and comes out, and where a chain forks into cases. Kept in `calls.md` beside the list, the notes in `calls-notes.md`. The chains are a second description beside the diagrams, and neither is changed to fit the other.
- [references/runs.md](references/runs.md): **a recorded run of a route.** The same journey measured once: the place in the code, the time and the values at each step. Kept in `docs/runs/`. Recorded only when the user asks.
- [references/translations.md](references/translations.md): **the page in two languages.** A file of translations beside the list and beside the calls file, so that the page can be read in Chinese and in English. Once it exists it is kept in step with every line that is reworded.
- [references/tasks.md](references/tasks.md): **tasks in progress and finished.** What the page reads from the task records the companion skill `implementation-journal` keeps (the `## For People` section of each), and how a finished step is shown as words and pictures.
- [references/windows.md](references/windows.md): **several windows at once.** Which Claude Code or Codex session is doing what on this project, what each one changed, and where two of them collide.

## What to do, and when

Everything the map shows is kept in the repo as plain files (the list, the task records) or measured from git each time; there is no database, and the page is rebuilt whole in a second or two with no model involved. So regenerate it freely.

The script is `scripts/bearings.py` in this skill folder (Claude Code: `${CLAUDE_SKILL_DIR}/scripts/bearings.py`; Codex: `~/.codex/skills/bearings/scripts/bearings.py`). Run it with python3 from inside the repo; `bearings.py --help` prints every keyword of the list format, so there is no need to read the script. It only reads: the project, including the task dossiers under `docs/tasks/` when there are any (`--tasks DIR` if the project keeps them elsewhere), the call chains in `calls.md` beside the list (`--calls-file FILE`) and the readers' notes in `calls-notes.md` beside that, the recorded runs under `docs/runs/` (`--runs DIR`), and, to tell windows apart, the session records Claude Code and Codex keep on this machine. What it writes stays under the repo's git directory: the page, and dated copies of the list. Two things are written into the project, both by the reader's own hand on the page: a note on a function goes into `calls-notes.md`, and a rewritten sentence on a function of a chain goes onto its line in `calls.md`.

- **The user wants to see the project** ("show me the project", "open the map", "how does X work"): run `bearings.py web --open`. It writes one HTML page under the repo's git directory and opens it in the browser through a small service on this machine (an address like `http://127.0.0.1:2xxxx/`), which rebuilds the page each time it is loaded and keeps the notes a reader types on it. The service stops by itself half an hour after the page was last used; running the command again starts it again. If it cannot start, the page opens as a plain file and the command still succeeds. Say in one sentence what they will see. To hand the page to someone else, write a file instead: `bearings.py web --out map.html` (add `--no-source` when the code is not public).
- **There is no parts list yet** and the user wants one. The first draft is the parts, done well; rooms are only listed.
  1. Read the repo and decide where the list can live.
  2. Write the parts with their paths, list the rooms inside the large parts, mark outside code. Run `bearings.py parts` until no file is unmapped.
  3. Run `bearings.py links`, then draw the diagrams from the top down: the whole project, each wing, then every part (a part with rooms uses its rooms as the boxes), and one to three routes. Spend the time here: read the code behind each diagram rather than guessing from file names. A part is left without a diagram only when it is a collection (assets, documentation, generated files) or code from outside; a small part still has a way it works, and the reader will click on it.
  4. Write the explanations while the code is fresh: the project's, every wing's, every part's, every room's. For a room, read enough of its code to say something true; two sentences that are right are better than four that are guessed.
  5. Run `bearings.py doctor` and settle what it reports about the list. It names every place where two levels disagree.
  6. Then, as a separate piece of work, write the call chains into the calls file (read [references/calls.md](references/calls.md) first): three to six of them, for the main things the code does, each a hand-written spine with `展开` under it, forked where the code forks. Run `bearings.py calls` and `bearings.py doctor` again for the chains. Do not go back and change a diagram to make it match a chain; if reading the code for a chain shows that a diagram is wrong, say so to the user and correct the diagram on its own account.
  7. Tell the user what you made, which parts you left without a diagram and why, how many rooms have no diagram of their own yet and that they can ask for any of them, which choices were yours, and ask them to correct the names.
- **The user asks how a room works, or asks for a room's diagram** ("给“运行循环”画流程图"): read that room's code, draw its diagram and, if it has none, write its explanation, then regenerate the map. Start from what the page already lists as going into the room and coming out of it: those lines come from the part's diagram, and the room's own diagram has to pick each of them up. Do the same for a part that has none.
- **The user asks about function calls**: for a call chain, which function calls which, or what goes into a function and comes out ("给这个项目画函数调用链"); says the code does it differently for different modes, devices, protocols or kinds of input; asks for a chain's ins and outs to be made clear, or says a chain is missing functions; asks what a function does inside, asks for notes on a function, or pastes notes to save ("给 `pid_step` 写逐行笔记", "把这些函数笔记存进项目"). Read [references/calls.md](references/calls.md) and do what it says for that request.
- **The user asks for an explanation of a part, or for the missing explanations** ("给“通话室”写一段说明", "把没有说明的都补上"; the page prints the first under a unit that has none): `bearings.py parts` lists the units without one. Read the unit's code and its diagram, write the `说明：` lines, regenerate the map.
- **The list was drafted before explanations and call chains existed** and the user asks to bring it up to date ("给清单补上说明和函数调用链"): write the explanation of every unit, as in step 4 above, then the call chains, as in step 6. Say how many units that is before starting.
- **The user asks for a wing's diagram, or for the diagram of the whole project** ("给“核心框架”这个区画一张图", "画一张整体框架图"): draw it with the boxes of the level below, from `bearings.py links` and the diagrams those boxes already have, then run `bearings.py doctor` to see whether the levels still agree.
- **You finished work that changed the picture**: a new area of the project, files that `bearings.py parts` reports as unmapped, or a part that now works differently from its flow diagram or its explanation. Update the parts list in the same change and mention it in one line. The call chains are kept true the same way, on their own: when a function on a chain was renamed or removed, no longer calls the one under it, changed its parameters, or gained or lost a case (`bearings.py doctor` says most of this), update the calls file; its format is in [references/calls.md](references/calls.md). If the picture is still true, do nothing. The page tells the reader when each diagram was drawn and how often the code has changed since, so a diagram you leave stale will show as such.
- **The user asks to put the unmapped files on the map** ("把没归类的文件补进清单"; the page prints this sentence when uncommitted work lies in files no part owns): `bearings.py parts --all` lists them. Give each file to the part it belongs to by widening that part's paths. When they form a new area of the project, add a part or a room for it, with its first line and icon. Rerun until no file is unmapped, then regenerate the map.
- **The user asks for all the missing flow diagrams**: `bearings.py parts` lists every part and room without one. Say how many there are before starting, since each one means reading code. Skip the ones that are only collections and say so.
- **The user asks to record a real run of a route, to record one again, what really happens at a step, or what a value looks like at run time** ("给“一次语音请求”录一次真实运行"): read [references/runs.md](references/runs.md) and do what it says for that request. Do not record a run unasked: it means running the project's code.
- **The user asks for the page in the other language, or for the missing translations** ("给项目地图补上中文对照"), **or the list or the calls file you are about to reword has a translations file beside it** (`parts.zh.md`, `parts.en.md`, `calls.zh.md`, `calls.en.md`): read [references/translations.md](references/translations.md). A reworded line takes its entry along in the same change. A user reading the page in the other language names parts in that language; that file says which part is meant.
- **The user asks whether the map is still right**, or you have just changed the list: run `bearings.py doctor`. It finds paths that no longer match any file, box names that just miss a part's name, a part whose diagram ignores its own rooms, arrows between parts that the code does not back, diagrams drawn long before the code last changed, and marks in a task's lines for people that name a part or box the list does not have. Where the list has a translations file it counts the texts with no translation yet and names the entries whose original the list no longer has. It checks every call chain against the code: a function that is not there, a name several functions answer to, a call the function above does not make, a `进`/`出` name the function does not have, a function with no sentence, a function with parameters and nothing written going in or out, a fork with a single case, and a reader's note on a function that is gone. It counts the units that have no explanation yet. It also checks the wiring between levels: a missing diagram of the project or of a wing, a box that is not on the diagram of what holds it, a line the level above draws that does not arrive inside the box, a line a box's own diagram draws that nothing outside it has, a route step the framework diagrams do not have, an arrow with no label, a diagram in more than one piece, and a code name on an arrow that the code no longer holds. Where a route has a recorded run it compares the two: a box drawn that the run did not pass, a step the route does not have, a place the run points at that is not in the code, a step whose file belongs to another part, and files changed since the recording. It only reports. It cannot tell whether a diagram is true: for that, reread the code and redraw.
- **The user has been away and asks what changed** ("这段时间变了什么", "what did I miss"): regenerate the map and point them at "what changed lately". It lists, for the last 7, 30 or 90 days, the parts added and removed, the diagrams redrawn, what happened to each task, the parts changed most, and the write-ups and diagrams the code has left behind. All of it is measured: the list against its own earlier version in git, the tasks against the history of their handoffs, the commits counted. The page opens on the stretch that reaches back to the reader's last visit. For a list that has never been committed there is no earlier version in git; the script keeps a dated copy beside the map page each time the list has changed and compares with that, so the first weeks after a list is drafted show no additions or redrawings. Do not write a summary of your own in place of this one.
- **The user asks what is being worked on, where a task stands, or what is waiting on them; asks to continue a task by the name the map shows** ("继续做“网站语音助手”")**; or asks for a task's lines for people, for its write-up after it is done, or to bring a finished task's write-up up to date**: read [references/tasks.md](references/tasks.md) and do what it says for that request.
- **The user asks how the parts connect or what depends on what**: `bearings.py links` for the numbers between parts, `bearings.py calls --from <function>` for which function calls which; on the map, each part's sheet lists what it uses and what uses it. For how the project works as a whole, the map opens on "how it works" when the list has a diagram of the whole project.
- **The user asks which window or session is doing what, which one is waiting on them, or whether two windows are in each other's way** ("哪个窗口在等我", "这几个窗口有没有撞车"): read [references/windows.md](references/windows.md) and do what it says.
- **The user asks what a piece of work touched**: `bearings.py check` lists the parts the uncommitted work touched; `--commit <rev>` does the same for one past commit, `--since <rev>` for everything after one. Report it using the part names as written.

## What this skill does not do

It does not plan work, review it, block it, or judge whether a change belonged where it landed. It does not ask the user questions before coding. If a rule shown on the map matters to the work, that is because the project's own guide says so, not because this skill does.
