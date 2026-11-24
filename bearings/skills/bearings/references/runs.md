# A recorded run of a route

Part of the `bearings` skill. `SKILL.md` covers the parts list, its diagrams and the script `scripts/bearings.py`; this file covers recording a real run of a route.

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

## What to do, and when

- **The user asks to record a real run of a route, or to see the real values at each step** ("给“一次语音请求”录一次真实运行"; the page prints this sentence under a route that has no run): follow "A recorded run of a route" above, then regenerate the map.
- **The user asks to record a run again** ("重录“一次语音请求”的运行记录"; the page prints this when the run's files have changed since): rerun the script that made it if it is still there, otherwise write it again. A recording under the same route and name replaces the old file.
- **The user asks what really happens at a step, or what a value looks like at run time**: `bearings.py runs` prints every recorded step with its file, line and values. Answer from it, and say when it was recorded. If there is no run for that route, say so rather than guessing the values.
