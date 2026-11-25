# Call chains

Part of the `bearings` skill. `SKILL.md` covers the parts list, its diagrams and the script `scripts/bearings.py`; this file covers the call chains and a reader's notes on functions.

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
- A `function | sentence` line set in under the `展开` line gives that sentence to one of the functions filled in there, and changes nothing else about it. This is where the page puts a sentence a reader wrote for a filled-in function (see "A sentence a reader rewrote"); leave those lines as they are.
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

**A sentence a reader rewrote.** On a page opened with `bearings.py web --open`, the sentence on every function of a chain has a "Rewrite" button (a double-click on its line in the outline does the same). What the reader writes is saved straight into the calls file: on the function's own line, in place of the sentence after the bar, or, for a function the script filled in, on a line of its own set in under that `展开`. Nothing else in the file changes. So the calls file can change under you while a page is open: read it again right before you edit it, and when you rework a chain, keep a sentence that a person wrote unless the code has made it untrue. A plain-file page has no such button.

**A reader's notes.** On the page, each function on a chain opens into a page of its own: its place, its signature, what goes in and out, the comment the code carries, its source with line numbers, and beside that the reader's notes on it. Readers write there what they make of the function, or paste in the part of an AI's explanation they want to keep. The notes are kept in `calls-notes.md` beside the calls file. When the page was opened with `bearings.py web --open`, it is shown through a small service on this machine, and a note is written into that file as the reader types it: there is nothing for them to save. When the page is a plain file (one that was shared, or published), there is no service behind it; the note then stays in that reader's browser, with a button to copy it out.

````text
## motor_control/motor_ctl_sm.c:PosSpeedCtlLoopTask

先读位置，再估速度，最后按当前模式算电流目标。

- `motor_pos_sensor(...)` 这一行之后，`axis->pos_now` 才是这一周期的位置。
- 保护检查失败时直接进故障态，后面的 `ModeRun` 不会执行。
````

- A `##` heading names the function as a chain would (`path/file:function` is the safest); everything down to the next `##` heading is its note, as Markdown.
- The page shows a note as Markdown reads: headings (from `###` down, since `##` names a function), lists, tables, quotes, code, links, and formulas written as TeX between `$…$` (in a line) or `$$…$$` (on lines of their own; `\(…\)` and `\[…\]` work too). Three marks come from the buttons above the note and can be written by hand as well: `==lit up==`, `<font color="red">coloured</font>` (red, orange, green, blue, purple) and `<mark title="the remark">the words remarked on</mark>`. When you write a note, write formulas as TeX, and leave a reader's marks in place when you add to their note. Text a reader pastes from an AI's answer is turned into this Markdown by the page.
- The notes are the reader's. Write in that file only when asked, and never as part of writing a chain.
- A reader may have the page open and be typing while you work. Read the notes file again right before you edit it, change only the note you were asked about, and leave every other note exactly as it is.
- Asked to save notes ("把这些函数笔记存进项目", followed by text a plain-file page copied, which is already in this form): put each one into the notes file under its heading. A pasted note replaces the note under the same heading, since the page starts a reader off from the note the project has. Change nothing else in the file, and do not edit the reader's words.
- Asked for notes on a function ("给 `PosSpeedCtlLoopTask` 写逐行笔记", "解释一下这个函数"): read that one function and write its note: what each stretch of it does, in the order the code runs, quoting the short piece of code each remark is about rather than a line number, which moves. Keep it to what helps someone reading the code. If the function already has a note, add yours under it and leave what is there. One function at a time, as asked; do not write notes for a whole chain unless the user asks for exactly that, and say first how many functions that is.
- `bearings.py doctor` reports a note whose function the code no longer has. If the function was renamed or moved, correct the heading; do not delete a reader's note.
- The page carries the source of the functions on the chains, so that a reader can note against it. When the user is going to share the page and the code is not public, generate it with `bearings.py web --no-source` and say so. A page written with `web --out` ends by naming the files whose source is inside it: pass that list on to the user before they share the page. A function whose source looks like it holds a key or a password is shown without its source, and the command says which; tell the user, since a key in the code is worth knowing about either way.

**Chains written inside the parts list.** For a short while a `calls` block could stand inside `docs/parts.md`, under a part or with a route's title. Those are still read and shown. When you next work on such a list, move them into the calls file (`bearings.py calls` says how many there are), and give each a heading of its own.

## What to do, and when

- **The user asks for a call chain, which function calls which, or what goes into a function and comes out** ("给这个项目画函数调用链", "给“电机控制环”画函数调用链", "画一条从收到报文到电机转起来的调用链"; the page prints such a sentence where chains are missing): follow "Call chains" above and write it into the calls file, then regenerate the map. Asked for the project's chains without any being named, write the three to six main ones, tell the user which other entry points you saw, and let them ask for more: every chain costs reading, and the page is of use from the first one. Asked for a part, write the chain or chains of what that part's code does; they may run on into other parts, and need not stop at its edge. Asked about one function only ("`start_call` 调用了谁"), answer from `bearings.py calls --from start_call` and say that it is measured and what it cannot see.
- **The user says the code does it differently for different modes, devices, protocols or kinds of input**, or asks for those to be shown ("把三种控制模式都画进调用链", "编码器不一样的时候怎么走"): fork the chain that passes there, as "Where the chain forks" says. Read each way in the code before writing its case.
- **The user asks for a chain's ins and outs to be made clear, or says a chain is missing functions** ("把进出写清楚", "这条链不全"): read those functions again and fill in what is asked under "The frame is complete" and "What goes in and what comes out". `bearings.py calls` lists, under each function, the parameters the chain does not explain yet.
- **The user asks what a function does inside, asks for notes on a function, or pastes notes to save** ("给 `pid_step` 写逐行笔记", "把这些函数笔记存进项目"; the page prints both on a function's page): follow "A reader's notes" above, then regenerate the map.
