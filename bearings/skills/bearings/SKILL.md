---
name: bearings
description: "Help a person understand a project that AI is building, from a first look to its architecture: keep a plain-language list of the project's parts and a flow diagram of how each part works, and turn them into a visual map page (how it works: the project as boxes inside boxes, one diagram of the whole, a click on a box opens the diagram inside it, with what goes into each box and what comes out, an explanation of every part in plain words, and one thing followed through the whole project; function calls, kept apart from the diagrams: the complete frame of which function calls which, a sentence on each, what goes into it and comes out, where a chain forks into cases, and a page for each function with its code and the reader's own notes; where work landed: every part on one plan, the changed ones lit; which part uses which, measured from the code). Use when the user asks to see or understand the project, asks for the project map, the overall framework or architecture, asks how a part works, asks for an explanation of a part, asks for a function call chain, which function calls which, what a function takes and gives back, how the code differs between modes, devices or protocols, asks for notes on a function or to save function notes, asks how the parts connect, what goes in and out of a part, what depends on what, or what recent work touched, asks which window or session is changing what, asks what is being worked on or what is waiting on them, asks to record a real run of a route or what the values are at each step when it runs, asks to set up a parts list, or when finished work changed how a part works and docs/parts.md exists. This skill only describes the project; it never limits how code is written."
---

# Bearings

When AI writes the code, a person stops learning their project as a side effect of writing it. This skill gives them a picture to look at instead: the project as named parts, how each part works, and where work has been landing.

It is for understanding only. It never tells the agent how to write code, which parts to leave alone, or when to stop and ask. Do the coding work exactly as you would without this skill; the skill's only claim on you is to keep the picture true afterwards.

Reply in the language the user works in. The parts list is written in that language too, for a reader who may not be able to program.

## The parts list

`docs/parts.md` is the single source for the picture of the project's parts. The map page is generated from it, from git history and from the code's own import statements. The call chains are a second description, kept in a file of their own and shown in a view of their own (see "Call chains"); the list says nothing about functions.

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

### A recorded run of a route
### A recorded run of a route

A route is a written description. A recorded run is the same journey measured once: for each step, the box of the route it belongs to, the file and line the code was at, how long it took, and the values that went in and came out. It lives in `docs/runs/<name>.json`. On the page the latest run of a route sits under it: the steps in the order they began, and for the one the reader picks, its place in the code and its values. Each box on the route carries the numbers of the steps that passed it, and a box the run never passed is marked.

Record one when the user asks for it. Do not record runs unasked: it means running the project's code.

- Write a small script that drives the project's real code along the route, and record with `scripts/bearings_run.py` from this skill folder (its docstring has the whole API). `run.watch(owner, "function", "Box")` wraps a function for as long as the recording lasts, so the project's own code is not changed; `with run.step("Box", name=value) as s:` times a stretch of the script where no function marks the step.
- For C, use `scripts/bearings_run.h` (its opening comment has the whole API). Compile the project's sources with `-finstrument-functions -g` and link a small harness that names the functions to watch with `BR_WATCH(function, "Box", probe)`; a probe reads the values out of the program's own variables as the function starts and ends. The sources are not changed. Embedded code runs this way wherever it already runs on a desktop (a simulation build, a test harness); do not try to record on the target. Places are found on macOS only, and only when the object files are kept and `dsymutil` has run. A program in any other language can write the same file; `bearings.py --help` gives its shape.
- Name each step with a box of the route, exactly as the route writes it. Watch the function that does that box's work, one per box where the code allows it. A function called in a loop makes a step each time: record one pass of the loop, not a thousand.
- Run the real thing with a realistic input: a simulator, a test server, a local database. Never record against production, real customers' data or anything that costs money or sends messages, unless the user said so for this run. Say what you ran.
- Then run `bearings.py runs` and read it. Run `bearings.py doctor` as well: it reports a box the route draws that the run did not pass, a step the route does not have, a place that is not in the code, and a step whose file belongs to another part. For each, find out from the code which side is wrong. A box that was not passed because this input does not take that branch is not a mistake: say so to the user, or record a second run that does take it. Correct the route when the route is what was wrong.
- The file holds real values from a real run. The recorder cuts each to one line and writes values whose names look like secrets as dots, but read the file before it is committed, and tell the user that these values will be on the map page if they share it.
- The script that made the recording belongs to the user's project only if they want to keep it; ask, or leave it uncommitted and say where it is.

A run shows one path, taken once. Do not describe it as how the project always behaves. The page says when it was recorded and how often its files have changed since.

### Which part uses which

Nobody writes this down. The script reads the import statements (Python, JavaScript/TypeScript, Go) and the `#include` lines of C and C++, and counts, for each pair of parts, how many files in one import from the other. The map uses it in two places: an arrow between two parts that the code does not back is drawn dashed, and every part's sheet lists "it uses" and "used by". `bearings.py links` prints the same numbers; read them before drafting flow diagrams and routes, so the descriptions agree with the code. Other languages (MATLAB and Simulink models among them) and links over a network are not measured; say so when it matters. For C and C++ a header that several folders each have their own copy of counts only when one copy sits clearly nearer the including file. It counts only an import it can pin to one file: a name that several files in the repo could answer to, or a lone script in a folder the importing file neither sits under nor adds to `sys.path` itself, is left out rather than guessed, so a link you know exists can be missing while a link that is listed is real.

## Call chains

The parts list and its diagrams tell the idea of the project: boxes, and what travels between them. The call chains tell the code: which function calls which, what each one does, what goes into it and what comes out. They are two descriptions and they are kept apart, so that neither has to bend to fit the other. The chains have a file of their own and a view of their own on the page; nothing in a chain has to follow a route or stay inside a part, and a diagram never has to change because a chain was written.

A chain is the frame of the calls, whole: every function the work passes through, in order, what goes in and out of it, and every fork. It stops at the function's door. What a function does inside, line by line, is not written into the chain: the page gives every function a page of its own, with its code, and that is where a reader works it out and keeps notes (see "A reader's notes"). This keeps a chain cheap to write and true for longer, and it is why the same way of working fits any project.

**Where they live.** `calls.md` in the folder of the parts list (`docs/calls.md`; `CALLS.md` or `.bearings/calls.md` when the list lives there). A heading names a chain, the plain lines under it say what the chain is about, and a fenced block whose language is `calls` holds its functions:

````text
## 驱动器收到一个目标位置

总线主站发来一个新的目标位置，到电机开始朝它走为止。前半段每来一帧报文跑一次，后半段每个位置环周期跑一次。

```calls
canDispatch | 协议栈收到一帧报文，按类型分给处理函数。
  进 m: 这一帧 CAN 报文，含编号和最多 8 个字节的数据 | 驱动器板子的接收中断交来
  set_Target_position | 把主站写来的目标位置记下来，等下一个周期取用。
    进 val: 目标位置，单位是编码器计数 | 报文里解出来的
    出 target_position: 记下的目标位置 | 位置环下一个周期由 PpModeRun 读走
PosSpeedLoopCtrl | 位置环每个周期跑一次：读位置，跑当前的运动模式，算出电流目标。
  AppRun | 按现在的运动模式，调用那个模式的函数。
    分支 运动模式 | 由对象字典里的运动模式决定，经函数指针调用
      情况 轮廓位置 | 主站给目标位置，驱动器自己规划怎么走过去
        PpModeRun | 读出目标位置，交给规划器算这一周期该走到哪。
          出 pos_cmd: 这一周期的位置指令 | 交给位置环
      情况 轮廓速度 | 主站给目标速度
        PvModeRun | 把目标速度限幅后交给速度环。
  PosSpeedCtlLoopTask | 按位置指令和实际位置算出电流目标。
    进 axis: 这根轴的全部控制变量 | 上电时建好，一直用
    出 axis->iq_ref: 电流目标 | 电流环下一次中断读走
    展开 2
```
````

**One chain is one thing the code does.** Name it for what happens ("驱动器收到一个目标位置", "学员说一句，后台答一句"), and start it where the code is entered: a request handler, an interrupt, a command, a timer, a message. Pick the chains by reading the code's entry points, not by copying the routes.

**The frame is complete, and most of it is not written by hand.** Which function calls which is something the script reads from the code for nothing. Reading every function yourself in order to write it down is where the cost of a chain goes: on a firmware project of a thousand files, writing thirteen chains of about five hundred functions by hand took forty minutes of an agent's work. So write the spine, and have the script fill in the rest:

- **Write by hand** what only a reader of the code can supply: where the chain enters, the functions where the work passes from one stage to the next, every fork, and every call the script cannot see (through a function pointer, a callback, an interrupt vector, an event, a queue). Usually five to fifteen lines a chain.
- **Under a function whose callees are ordinary calls, write `展开 2`** (or `expand 2`): the script puts what that function calls, and what those call, into the chain at that place, two levels down (one to five; two when no number is given). Each filled-in function appears on the page with its place, its signature, its parameters and types, the comment the code carries on it, and its own page for notes, marked as filled in from the code. Functions of a few lines that call nothing further (getters, setters) are left out and counted.
- Nothing has to be written about a filled-in function, and the check-up asks nothing of it. If one of them matters to the story, write it by hand instead, with its sentence and its ins and outs; write `展开` under it again if its own callees should follow.
- When one chain grows past what can be read in a sitting, cut it where the code itself hands over (an interrupt returns, a message is queued, a layer ends) and make the rest a chain of its own.

**A function.** `function | what it does` names a function as the code names it. A function set in under another is called by it; functions at the same depth run one after the other. Write a method as `Class.method` and a constructor as the class's name; when several functions share a name, say which with `Class.method` or `path/file.py:function`.

- One short sentence after the bar says what the function is there for at this point of the chain: a clause, about as long as a line of a table of contents. Not a walk through its body, and not its constants, registers or error codes. Say what its name does not already say.
- Do not go on to explain how it does it. No account of its steps, its loops, its conditions, its error handling: that is what the function's own page and the reader's notes are for, and writing it for every function is where the cost of a chain would go. A further line under a function is for the one thing a reader must know to follow the chain and cannot see from the frame, such as how a call is made when the code does not show it ("经函数指针 `run` 调用").
- These are for a reader who reads code. Use the code's names freely, in backticks.

**What goes in and what comes out.** Under a function, `进 name: what it is | where it comes from` (or `in`) and `出 name: what it is | where it goes` (`out`). The name is the code's: a parameter, a variable or a field the function reads or sets (`self.turns`, `axis->iq_ref`, a global), and `出 返回: ...` (`out return: ...`) for the return value.

- For a function you write by hand: every parameter that carries data or changes what the function does, the return value when there is one, and the state the function reads or leaves behind for a later step. A reader should be able to follow one piece of data from the top of the chain to the bottom by these lines alone. Keep each to a clause.
- *What it is*: its meaning, with the unit, the range or an example where that matters ("目标位置，单位是编码器计数", "消息种类，voice、text 或 hangup"). Not its type: the page shows the type from the code.
- *Where it comes from / where it goes*: the function that produced it or will use it, the caller, a setting, the outside world. This is what joins the functions into a chain, so do not leave it out for the values that travel.
- A thing that is only handed on (a context pointer every function takes, say) is written once, where it enters the chain. Do not repeat it under each function it passes through.
- The page lists every parameter the code gives the function. One you say nothing about is shown as not explained, and the check-up lists a function with parameters of which none is written.

**Where the chain forks.** The same journey often goes one way or another: which bus the command came over, which encoder is fitted, which control mode is active, which kind of message arrived. Do not write one chain for each. Write the chain once, and fork it where the code does:

- `分支 what varies | how it is decided` (or `branch`) stands where the ways part: under the function that makes the choice, at the depth of the functions it would call.
- Under it, each `情况 name | when it applies` (or `case`) is one way through, with the functions that way calls set in under it. Further lines under a case say more about it.
- What all the cases share stays outside the fork: the functions before it, and the functions after it at the fork's own depth. So the shared stretch is written once and only the differing stretch is repeated. A case inside a case is fine where the code really nests.
- A fork has at least two cases. Name every case the code has, even one you do not expand; a case with nothing under it means "nothing more is called here". If only one way is worth following, it is not a fork: write the functions plainly and mention the other ways in a sentence.
- On the page the reader sees the whole chain as an outline with every fork and case, picks a case at each fork, and follows that one way through the cards.

**Measured, not written.** Nobody writes where a function is, its signature, the types of its parameters, the comment the code carries on it, the part it belongs to, or whether the function above really calls it: the script reads those from the code and the page shows them on each function's card. Python is read with its own parser; C/C++, JavaScript/TypeScript and Go by pattern; in any other language a function is only found by its name, so it gets a place and no more.

- Start from what is measured, not from memory: `bearings.py calls --from <function>` prints what a function calls, and those in turn. Use it to find where the chain forks and where the calls stop being visible, which is where your hand-written lines go. `--draft` prints the same as the frame of a `calls` block with every parameter listed, for a stretch you do want to write out in full.
- Then run `bearings.py calls` and read it, and `bearings.py doctor`. They report a function the code does not have, a name several functions answer to, a call the code does not show, a `进`/`出` name the function does not contain, a function with no sentence, a function with parameters and nothing written going in or out, and a fork with one case. A call that goes through a function pointer, a callback, an event, a queue or a network is real and cannot be measured: keep it, and say how it is made in that step's sentence or on the fork's line. Anything else, correct from the code.
- Where a recorded run passed the same function, its card can show that run's real values.
- A chain describes the code as it is. It is not a plan for the code and says nothing about how it ought to be written.

**A reader's notes.** On the page, each function on a chain opens into a page of its own: its place, its signature, what goes in and out, the comment the code carries, its source with line numbers, and beside that the reader's notes on it. Readers write there what they make of the function, or paste in the part of an AI's explanation they want to keep. The page saves a note in the reader's browser as it is typed. The notes the project keeps are in `calls-notes.md` beside the calls file:

````text
## motor_control/motor_ctl_sm.c:PosSpeedCtlLoopTask

先读位置，再估速度，最后按当前模式算电流目标。

- `motor_pos_sensor(...)` 这一行之后，`axis->pos_now` 才是这一周期的位置。
- 保护检查失败时直接进故障态，后面的 `ModeRun` 不会执行。
````

- A `##` heading names the function as a chain would (`path/file:function` is the safest); everything down to the next `##` heading is its note, as Markdown.
- The notes are the reader's. Write in that file only when asked, and never as part of writing a chain.
- Asked to save notes ("把这些函数笔记存进项目", followed by text the page copied, which is already in this form): put each one into the notes file under its heading. A pasted note replaces the note under the same heading, since the page starts a reader off from the note the project has. Change nothing else in the file, and do not edit the reader's words.
- Asked for notes on a function ("给 `PosSpeedCtlLoopTask` 写逐行笔记", "解释一下这个函数"): read that one function and write its note: what each stretch of it does, in the order the code runs, quoting the short piece of code each remark is about rather than a line number, which moves. Keep it to what helps someone reading the code. If the function already has a note, add yours under it and leave what is there. One function at a time, as asked; do not write notes for a whole chain unless the user asks for exactly that, and say first how many functions that is.
- `bearings.py doctor` reports a note whose function the code no longer has. If the function was renamed or moved, correct the heading; do not delete a reader's note.
- The page carries the source of the functions on the chains, so that a reader can note against it. When the user is going to share the page and the code is not public, generate it with `bearings.py web --no-source` and say so.

**Chains written inside the parts list.** For a short while a `calls` block could stand inside `docs/parts.md`, under a part or with a route's title. Those are still read and shown. When you next work on such a list, move them into the calls file (`bearings.py calls` says how many there are), and give each a heading of its own.

## Tasks in progress and finished

The map also shows what is being worked on. It takes that from the task records the companion skill `implementation-journal` keeps under `docs/tasks/`, one file per task (in older projects a folder per task, whose `handoff.md` is read the same way). A record is written for the next AI session, so the map reads one thing from it: its `## For People` section, the only part written for a person.

````text
## For People

名字：网站语音助手
现在：已经上线，但开关还关着。
等你：自己打一次电话试听
等你：定下给学员开放哪几种声音
下一步：你定了以后再打开线上的开关。
````

- `名字：` or `Name:` is what the person calls the task. `现在：` or `Now:` says where it stands. `等你：` or `Needs you:` takes one line for each thing the work is waiting on the person for, and no line when nothing waits. `下一步：` or `Next:` says what happens after.
- Plain words in the user's language: no file names, code names, commit hashes or backticks, and parts called what the parts list calls them. Keep the name the same from one rewrite to the next; the person asks for the task by it.
- A task is in progress until its record's `status:` says Complete. The page lists each one with those lines, flags the ones waiting on the reader, and lights the parts its work landed in. Those parts are measured, not written: the commits the record cites by hash or was committed with, and the uncommitted work of a window that is writing in that record.
- A task whose record has no such section is listed by its heading, with the sentence to say to have the lines written. One that has not moved in a month either is left out.
- The same section can say what the task's last finished step came to, and the page then shows it as words and pictures:

````text
做成了：学员在通话面板里可以选助手的声音。
怎么试：在自己电脑上打一次电话，把面板里的声音都听一遍。
还没做：还没有真人试过。
新增：语音助手 / 选音色：学员从网站给的列表里挑一个声音。
改了：语音助手 / 耳朵：默认不变，可以换成另一家。
去掉：语音助手 / 旧识别：试过后去掉了。
````

- `做成了：` or `Done:` says what a person can now do or see. `怎么试：` or `Try:` says how they can see it for themselves. `还没做：` or `Not yet:` takes one line for each thing a person might assume is done and is not, three at most.
- `新增：` `改了：` `去掉：` (or `Added:` `Changed:` `Removed:`) each name a box of a flow diagram on the parts list and say in one sentence what is different: `Part / Box: sentence`, or `Part / Room / Box: sentence` for a room's diagram. The page draws that part's diagram with those boxes marked and the rest faded. A line that names only a part (`改了：上线和环境配置：多了两个设置项`) is listed without a mark.
- The names must be the ones on the list, or the page cannot place the mark. So when a step changes how a part works, update the part's flow diagram first, then write the marks against the boxes it now has. A removed box is no longer on the diagram; it is listed under it.
- Write marks only for what the step changed in how the part works. A step that changed no diagram (a fix, a setting) has none, and the page shows the three lines and the lit rooms alone.
- A finished task (`status: Complete`) that has lines for people stays on the page for as long as its record is in the repo: for a month as "finished lately", after that folded under "finished earlier". One without lines for people leaves at once.
- A finished task's lines describe the code as it was when they were written. The page measures whether it has moved on since: later commits, and uncommitted work, in the files the task itself changed. When there are any, the card says "changed since" and the sheet gives the count and the sentence to say to have the lines brought up to date. This needs the task's commits to be known, which they are when the record cites them by hash or was committed with them.
- The page also shows how a task got to where it is (a step finished, finished, opened again, finished a second time). It reads that from the git history of the record, so only versions that were committed appear.
- The page shows nothing else from a record and never links to one. The rest is written for an agent.

## What to do, and when

Everything the map shows is kept in the repo as plain files (the list, the task records) or measured from git each time; there is no database, and the page is rebuilt whole in a second or two with no model involved. So regenerate it freely.

The script is `scripts/bearings.py` in this skill folder (Claude Code: `${CLAUDE_SKILL_DIR}/scripts/bearings.py`; Codex: `~/.codex/skills/bearings/scripts/bearings.py`). Run it with python3 from inside the repo; `bearings.py --help` prints every keyword of the list format, so there is no need to read the script. It only reads: the project, including the task dossiers under `docs/tasks/` when there are any (`--tasks DIR` if the project keeps them elsewhere), the call chains in `calls.md` beside the list (`--calls-file FILE`) and the readers' notes in `calls-notes.md` beside that, the recorded runs under `docs/runs/` (`--runs DIR`), and, to tell windows apart, the session records Claude Code and Codex keep on this machine. What it writes stays under the repo's git directory: the page, and dated copies of the list.

- **The user wants to see the project** ("show me the project", "open the map", "how does X work"): run `bearings.py web --open`. It writes one HTML page under the repo's git directory and opens it. Say in one sentence what they will see.
- **There is no parts list yet** and the user wants one. The first draft is the parts, done well; rooms are only listed.
  1. Read the repo and decide where the list can live.
  2. Write the parts with their paths, list the rooms inside the large parts, mark outside code. Run `bearings.py parts` until no file is unmapped.
  3. Run `bearings.py links`, then draw the diagrams from the top down: the whole project, each wing, then every part (a part with rooms uses its rooms as the boxes), and one to three routes. Spend the time here: read the code behind each diagram rather than guessing from file names. A part is left without a diagram only when it is a collection (assets, documentation, generated files) or code from outside; a small part still has a way it works, and the reader will click on it.
  4. Write the explanations while the code is fresh: the project's, every wing's, every part's, every room's. For a room, read enough of its code to say something true; two sentences that are right are better than four that are guessed.
  5. Run `bearings.py doctor` and settle what it reports about the list. It names every place where two levels disagree.
  6. Then, as a separate piece of work, write the call chains into the calls file (see "Call chains"): three to six of them, for the main things the code does, each a hand-written spine with `展开` under it, forked where the code forks. Run `bearings.py calls` and `bearings.py doctor` again for the chains. Do not go back and change a diagram to make it match a chain; if reading the code for a chain shows that a diagram is wrong, say so to the user and correct the diagram on its own account.
  7. Tell the user what you made, which parts you left without a diagram and why, how many rooms have no diagram of their own yet and that they can ask for any of them, which choices were yours, and ask them to correct the names.
- **The user asks how a room works, or asks for a room's diagram** ("给“运行循环”画流程图"): read that room's code, draw its diagram and, if it has none, write its explanation, then regenerate the map. Start from what the page already lists as going into the room and coming out of it: those lines come from the part's diagram, and the room's own diagram has to pick each of them up. Do the same for a part that has none.
- **The user asks for a call chain, which function calls which, or what goes into a function and comes out** ("给这个项目画函数调用链", "给“电机控制环”画函数调用链", "画一条从收到报文到电机转起来的调用链"; the page prints such a sentence where chains are missing): follow "Call chains" above and write it into the calls file, then regenerate the map. Asked for the project's chains without any being named, write the three to six main ones, tell the user which other entry points you saw, and let them ask for more: every chain costs reading, and the page is of use from the first one. Asked for a part, write the chain or chains of what that part's code does; they may run on into other parts, and need not stop at its edge. Asked about one function only ("`start_call` 调用了谁"), answer from `bearings.py calls --from start_call` and say that it is measured and what it cannot see.
- **The user says the code does it differently for different modes, devices, protocols or kinds of input**, or asks for those to be shown ("把三种控制模式都画进调用链", "编码器不一样的时候怎么走"): fork the chain that passes there, as "Where the chain forks" says. Read each way in the code before writing its case.
- **The user asks for a chain's ins and outs to be made clear, or says a chain is missing functions** ("把进出写清楚", "这条链不全"): read those functions again and fill in what is asked under "The frame is complete" and "What goes in and what comes out". `bearings.py calls` lists, under each function, the parameters the chain does not explain yet.
- **The user asks what a function does inside, asks for notes on a function, or pastes notes to save** ("给 `pid_step` 写逐行笔记", "把这些函数笔记存进项目"; the page prints both on a function's page): follow "A reader's notes" above, then regenerate the map.
- **The user asks for an explanation of a part, or for the missing explanations** ("给“通话室”写一段说明", "把没有说明的都补上"; the page prints the first under a unit that has none): `bearings.py parts` lists the units without one. Read the unit's code and its diagram, write the `说明：` lines, regenerate the map.
- **The list was drafted before explanations and call chains existed** and the user asks to bring it up to date ("给清单补上说明和函数调用链"): write the explanation of every unit, as in step 4 above, then the call chains, as in step 6. Say how many units that is before starting.
- **The user asks for a wing's diagram, or for the diagram of the whole project** ("给“核心框架”这个区画一张图", "画一张整体框架图"): draw it with the boxes of the level below, from `bearings.py links` and the diagrams those boxes already have, then run `bearings.py doctor` to see whether the levels still agree.
- **You finished work that changed the picture**: a new area of the project, files that `bearings.py parts` reports as unmapped, or a part that now works differently from its flow diagram or its explanation. Update the parts list in the same change and mention it in one line. The call chains are kept true the same way, on their own: when a function on a chain was renamed or removed, no longer calls the one under it, changed its parameters, or gained or lost a case (`bearings.py doctor` says most of this), update the calls file. If the picture is still true, do nothing. The page tells the reader when each diagram was drawn and how often the code has changed since, so a diagram you leave stale will show as such.
- **The user asks to put the unmapped files on the map** ("把没归类的文件补进清单"; the page prints this sentence when uncommitted work lies in files no part owns): `bearings.py parts --all` lists them. Give each file to the part it belongs to by widening that part's paths. When they form a new area of the project, add a part or a room for it, with its first line and icon. Rerun until no file is unmapped, then regenerate the map.
- **The user asks for all the missing flow diagrams**: `bearings.py parts` lists every part and room without one. Say how many there are before starting, since each one means reading code. Skip the ones that are only collections and say so.
- **The user asks to record a real run of a route, or to see the real values at each step** ("给“一次语音请求”录一次真实运行"; the page prints this sentence under a route that has no run): follow "A recorded run of a route" above, then regenerate the map.
- **The user asks to record a run again** ("重录“一次语音请求”的运行记录"; the page prints this when the run's files have changed since): rerun the script that made it if it is still there, otherwise write it again. A recording under the same route and name replaces the old file.
- **The user asks what really happens at a step, or what a value looks like at run time**: `bearings.py runs` prints every recorded step with its file, line and values. Answer from it, and say when it was recorded. If there is no run for that route, say so rather than guessing the values.
- **The user asks whether the map is still right**, or you have just changed the list: run `bearings.py doctor`. It finds paths that no longer match any file, box names that just miss a part's name, a part whose diagram ignores its own rooms, arrows between parts that the code does not back, diagrams drawn long before the code last changed, and marks in a task's lines for people that name a part or box the list does not have. It checks every call chain against the code: a function that is not there, a name several functions answer to, a call the function above does not make, a `进`/`出` name the function does not have, a function with no sentence, a function with parameters and nothing written going in or out, a fork with a single case, and a reader's note on a function that is gone. It counts the units that have no explanation yet. It also checks the wiring between levels: a missing diagram of the project or of a wing, a box that is not on the diagram of what holds it, a line the level above draws that does not arrive inside the box, a line a box's own diagram draws that nothing outside it has, a route step the framework diagrams do not have, an arrow with no label, a diagram in more than one piece, and a code name on an arrow that the code no longer holds. Where a route has a recorded run it compares the two: a box drawn that the run did not pass, a step the route does not have, a place the run points at that is not in the code, a step whose file belongs to another part, and files changed since the recording. It only reports. It cannot tell whether a diagram is true: for that, reread the code and redraw.
- **The user has been away and asks what changed** ("这段时间变了什么", "what did I miss"): regenerate the map and point them at "what changed lately". It lists, for the last 7, 30 or 90 days, the parts added and removed, the diagrams redrawn, what happened to each task, the parts changed most, and the write-ups and diagrams the code has left behind. All of it is measured: the list against its own earlier version in git, the tasks against the history of their handoffs, the commits counted. The page opens on the stretch that reaches back to the reader's last visit. For a list that has never been committed there is no earlier version in git; the script keeps a dated copy beside the map page each time the list has changed and compares with that, so the first weeks after a list is drafted show no additions or redrawings. Do not write a summary of your own in place of this one.
- **The user asks what is being worked on, where a task stands, or what is waiting on them**: `bearings.py tasks` prints the tasks in progress, the ones finished lately and the ones finished earlier, with their lines for people and the parts each has touched; the map shows the same. Answer from those lines, in their words.
- **The user asks to continue a task by the name the map shows** ("继续做“网站语音助手”"): `bearings.py tasks` says where its record is. From there it is the implementation-journal skill's job: read that record and carry on as it says.
- **The user asks for a task's lines for people** ("给“课程验收”写一份给人看的说明"): write the `## For People` section of that task's record, from what the rest of the record says, then regenerate the map. Read the file again right before the edit and add only that section: another session may be working from that record.
- **The user asks to bring a finished task's write-up up to date** ("按现在的代码更新“优惠券”的说明"; the page prints this under a finished task whose files were changed again): `bearings.py tasks --json` says how often (`changed_since`). Read the record's lines for people, then what those later commits did to the files (`git log` on them from the record's date), and rewrite `做成了` / `怎么试` / `还没做` and the marks so they are true of the code as it is now. Change only that section of that record, set its `updated:` date, and regenerate the map. If the later changes were really the same task carried further, say so to the user: the journal skill would open that task again rather than leave it finished.
- **The user asks what a task came to, or for its write-up after it is done** ("给“课程验收”写一份做完后的说明"): add the `做成了` / `怎么试` / `还没做` lines and the marks to that section, from the record and the code the task changed. Check each mark's box against the part's flow diagram, run `bearings.py tasks` (it reports a mark whose part or box it cannot find), then regenerate the map.
- **The user asks how the parts connect or what depends on what**: `bearings.py links` for the numbers between parts, `bearings.py calls --from <function>` for which function calls which; on the map, each part's sheet lists what it uses and what uses it. For how the project works as a whole, the map opens on "how it works" when the list has a diagram of the whole project.
- **The user asks which window is doing what, which one is waiting on them, or whether two windows are in each other's way** ("哪个窗口在等我", "这几个窗口有没有撞车"): `bearings.py windows`, or regenerate the map. Answer with the windows' names as shown, and for a collision name the file or the part and the two windows.
- **The user asks what a piece of work touched**: `bearings.py check` lists the parts the uncommitted work touched; `--commit <rev>` does the same for one past commit, `--since <rev>` for everything after one. Report it using the part names as written.

### Several windows at once

People often run several Claude Code or Codex sessions on one project, and soon cannot say which window is doing what. `git` cannot say which of them changed a file either. So the script reads the session records both tools keep on the machine and puts each window on the project:

- **Every window that has been at work here in the last day gets a row**, not only the ones with uncommitted files: a letter, the window's name (its journal task if it is writing in a task's record under `docs/tasks/`, otherwise the session's title or opening request), and which tool it is.
- **How it stands.** Working: it is in the middle of a turn and its record moved in the last few minutes. Waiting for your reply: the agent has handed back and nobody has answered. Held up: it stopped in the middle of a step for a while, which is what a window waiting for a permission looks like, and also one running a long command; the page says both. Idle: nothing for a long time.
- **What it was last asked**, in the person's own words, and when it last moved.
- **What it changed**: its uncommitted files by part, and the commits made while one of its shell commands was running.
- **Collisions**, worst first: a file two windows both changed in one checkout (one will overwrite the other), a file changed in two worktrees (a conflict when they are merged), and a part two windows are both changing (worth a look). The parts list itself is left out: every window keeps its own lines of it up to date.

`bearings.py windows` prints all of this; the map shows it as "who is working where", with the collisions above it, and marks each lit room with the letters of the windows in it. `bearings.py check` still adds its "by window" list. The map also counts uncommitted work in the repository's other worktrees.

- A file changed with an edit tool is matched for certain. A file changed by a shell command is matched by time, and only when exactly one window fits; a commit is matched to a window the same way. Anything else is listed as having no window on record; say so rather than guessing.
- A window's state is read from its record, so it is as old as the page: regenerate the map before answering "is it still working".
- `--no-windows` skips the session records. Nothing is sent anywhere. The window names and the latest request typed into each window end up in the generated page, so mention that if the user is about to share the page.

When the user asks what "this window" did and several windows are at work, find this session in the list by its name and report that row. When the list shows that another window has changed a file this session is about to change, tell the user; what to do about it is theirs to decide.

## What this skill does not do

It does not plan work, review it, block it, or judge whether a change belonged where it landed. It does not ask the user questions before coding. If a rule shown on the map matters to the work, that is because the project's own guide says so, not because this skill does.
