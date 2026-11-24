# The page in two languages

Part of the `bearings` skill. `SKILL.md` covers the parts list, its diagrams and the script `scripts/bearings.py`; this file covers showing the page in a second language.

The list is written in one language, the one the user works in, and so are the call chains. That file stays the single source: paths, diagrams and names are read from it alone. The page can show it in the other language as well (Chinese beside an English list, English beside a Chinese one), and the reader switches at the top of the page. The page's own words always switch. The words of the list switch where a translations file beside it gives them:

- `parts.zh.md` beside an English `parts.md`, `parts.en.md` beside a Chinese one, and `calls.zh.md` or `calls.en.md` beside the calls file. Both are read as one set, so an entry may stand in either.
- An entry is two lines: the original text exactly as the list has it, and under it a line that starts with a colon and holds the translation. A `#` heading or an HTML comment is for whoever keeps the file and is not read.

````text
## Experiment runner

Experiment runner
: 实验运行器

The one way to run an experiment: validate, preflight, cool-down, rehearsal, run, safe state.
: 运行实验的唯一途径：校验、预检、冷却、预演、运行、安全状态。

timed plan
: 定时计划
````

- Anything a person wrote can have an entry: a name, a first line, a paragraph of an explanation (without `Explain:`), a rule, a box's name or note, the words on an arrow, the title of a route or a chain, a function's sentence, what goes in or comes out. A text with no entry is shown as written, so a half-finished file is still of use.
- One entry serves every place its text stands. A name is translated once and changes on every diagram, sheet and chain together; that is what keeps a box a door to its part in either language.
- Two names must not be given the same translation: the page tells boxes apart by name. `bearings.py words` and `doctor` report a collision, and the page leaves those names as written.
- Keep to the same lengths as in the list: a box name of at most eight characters or three words, the words on an arrow at most six characters or two words. Leave code names in backticks as they are.
- `bearings.py words` says how many texts have a translation, lists the ones that have none, and lists the entries whose original the list no longer has. `bearings.py words --draft` prints every missing entry with an empty translation line, grouped by where it stands, ready to fill in and add to the file.
- Write this file when the user asks for the other language, not as part of a first draft of the list. Once it exists, keep it true the way the list is kept true: when you reword a line of the list or the calls file, change the first line of its entry in the same change, and give a new line an entry. `bearings.py doctor` counts the texts with no translation and names the entries left behind.
- On the page in the other language a reader cannot rewrite the sentence of a function: that sentence belongs to the calls file, in its language. Notes on functions are the reader's own and are kept the same in both.
- A user reading the page in the other language will name parts in that language ("给“实验运行器”画流程图" in a project whose list is English). Look the name up in the translations file to find the part, and write the list in the list's language.

The reader's pick is kept in the browser. Before one is made, the page opens in the browser's language when the project has translations for it, and in the list's language otherwise. `?lang=zh` or `?lang=en` on the address opens it in that language.

## What to do, and when

- **The user asks for the page in the other language, or for the missing translations** ("给项目地图补上中文对照", "Add the English translations to the project map"; the page prints this when it is read in a language the list is not all in): follow "The page in two languages". Run `bearings.py words --draft`, write the translations into the file beside the list (the chains' into the one beside the calls file), then run `bearings.py words` until nothing is missing and no name collides, and regenerate the map. Say how many texts there are before starting when it is more than a few hundred; the list comes first, the chains after.
