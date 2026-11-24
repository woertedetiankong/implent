# Tasks in progress and finished

Part of the `bearings` skill. `SKILL.md` covers the parts list, its diagrams and the script `scripts/bearings.py`; this file covers what the map shows of the tasks.

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
- The page also lists what the project can do now: every task that says what it made (`做成了`), with whether the reader has tried it (see "What the reader tried").
- A part's sheet lists the tasks whose work landed in that part, the ones in progress first; a click opens the task. This is measured the same way as the parts a task lights up, and a part no task on the page touched has no such list.
- The page shows nothing else from a record and never links to one. The rest is written for an agent.

## What the reader tried

What a task made is something a person can try, and for a reader who does not read code, trying it is the only check there is. The page keeps count. Under "what it can do now" it lists every task that says what it made, the ones that need the reader first: what they found broken, what worked but whose code has changed since, what nobody has tried, and last what was tried and works. A task's sheet says how its latest try stands.

- The try is the reader's to report. On a page opened with `bearings.py web --open` a task's sheet has two buttons, works and does not, and room for a line of their own. A plain-file page has no buttons; it prints the sentence to say to the AI instead.
- Tries are kept in `tried.md` beside the parts list, one heading per task and one line per try: the day and time, 能用 or 不能用 (`works` / `broken` in an English list), the commit the code stood at, and what the reader noted. A new try is a new line; the last line under a task is how it stands. Do not write this file by hand, and never change or remove a line in it: note a try with `bearings.py tried "<task name>" works|broken <a few words>`, which also keeps what it needs to tell later whether the code moved on.
- "Worth trying again" is measured: the task's files are no longer as they were when the thing was tried. On the machine where the try was noted this is exact, uncommitted work included. Read elsewhere (another checkout, a published page) it is measured against the commit the line names, and when the task's files had uncommitted work in them at the time it is not known and nothing is claimed.
- A try says that a person tried the thing once and what they saw. It is not a test, and the page does not say it is. Only the user's own report is a try: a test you ran, or a check you made yourself, is never noted as one.

## What to do, and when

- **The user asks what is being worked on, where a task stands, or what is waiting on them**: `bearings.py tasks` prints the tasks in progress, the ones finished lately and the ones finished earlier, with their lines for people and the parts each has touched; the map shows the same. Answer from those lines, in their words.
- **The user says they tried something, and whether it worked** ("“优惠券”我试过了，能用", "“订单编号”我试了不能用：第二单的编号和第一单一样"; the page prints these on a task's sheet when it has no buttons): run `bearings.py tried "<the task's name>" works` or `broken` followed by what they said, then regenerate the map. Note only what they reported. When they say it does not work and ask for it to be put right, that is ordinary work on that task from there on; when they only report it, note it and ask nothing more of them than they offered.
- **The user asks what the project can do now, or what they have not tried yet**: `bearings.py tried` prints every task that made something, with how to try it and how its latest try stands. Answer from it, in the words of those lines.
- **The user asks what changed after a task was finished** ("“优惠券”做完以后又改了什么？"; the page prints this under a finished task whose files were changed again): this is a question, so change nothing: no revert, no rewrite of the task's lines. `bearings.py tasks --json` says how often its files changed since (`changed_since`); read those later commits (`git log` on the files the task changed, from the record's date) and any uncommitted work in them. Say in plain words, part by part, what each later change did, and whether what the task made still works the way its lines say, as far as the code shows. Name the parts as the list names them; leave file names and commit hashes out unless the user asks for them. If the user then wants something undone, that is theirs to ask for.
- **The user asks to continue a task by the name the map shows** ("继续做“网站语音助手”"): `bearings.py tasks` says where its record is. From there it is the implementation-journal skill's job: read that record and carry on as it says.
- **The user asks for a task's lines for people** ("给“课程验收”写一份给人看的说明"): write the `## For People` section of that task's record, from what the rest of the record says, then regenerate the map. Read the file again right before the edit and add only that section: another session may be working from that record.
- **The user asks to bring a finished task's write-up up to date** ("按现在的代码更新“优惠券”的说明"; the page prints this under a finished task whose files were changed again): `bearings.py tasks --json` says how often (`changed_since`). Read the record's lines for people, then what those later commits did to the files (`git log` on them from the record's date), and rewrite `做成了` / `怎么试` / `还没做` and the marks so they are true of the code as it is now. Change only that section of that record, set its `updated:` date, and regenerate the map. If the later changes were really the same task carried further, say so to the user: the journal skill would open that task again rather than leave it finished.
- **The user asks what a task came to, or for its write-up after it is done** ("给“课程验收”写一份做完后的说明"): add the `做成了` / `怎么试` / `还没做` lines and the marks to that section, from the record and the code the task changed. Check each mark's box against the part's flow diagram, run `bearings.py tasks` (it reports a mark whose part or box it cannot find), then regenerate the map.
