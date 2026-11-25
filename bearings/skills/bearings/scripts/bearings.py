#!/usr/bin/env python3
"""bearings: show a project as named parts, and which parts a piece of work touched.

A project lists its parts in docs/parts.md (a heading per part, the paths it owns as
backticked bullets, optionally a flow diagram). This script only reads and reports;
it never tells anyone what to change or leave alone.

  bearings.py parts                        list the parts, their file counts and unmapped files
  bearings.py check [--since REF | --commit REV] [--json]
                                           which parts the uncommitted work (or one past commit) touched
  bearings.py links [--json]               which part uses which, measured from import statements
  bearings.py doctor [--json]              check the list against the code; it reports and stops nothing
  bearings.py web [--out FILE] [--open]    write the project map as one HTML page; --open shows it through a
                                           service on this machine, so notes typed on it are kept in the project
  bearings.py tasks [--json]               the tasks in progress, from the implementation-journal skill's
                                           records: the lines written there for people, and the parts touched
  bearings.py windows [--json]             every Claude Code and Codex window at work in this project: working,
                                           waiting for you or idle, what it was last asked, what it has changed
                                           and committed, and where two windows collide
  bearings.py runs [--json]                the recorded runs under docs/runs/: one real run of a route, step by
                                           step, with the file and line and the values that went in and came out
  bearings.py calls [--json]               the call chains (docs/calls.md), each function checked against the
                                           code: where it is, its parameters, whether the one above really calls it
  bearings.py calls --from NAME [--depth N]
                                           which functions NAME calls, and those in turn, measured from the code

Uncommitted work is split by window: which Claude Code or Codex session edited each file,
read from the session records those tools keep on this machine (--no-windows skips that).
A page written with --out is for handing to someone else, so it leaves out each window's name
and the latest request typed into it; --asks keeps them.
The map also counts the uncommitted work in the repository's other worktrees.

Read-only towards the project, with one exception. It writes the map page, under the git dir unless --out
says otherwise, and beside it a dated copy of the parts list whenever the list has changed, so that "what
changed lately" can be measured for a list nobody has committed. The exception: `web --open` shows the page
through a small service on this machine, and two things a reader writes on the page go into the project: a
note on a function's page, into calls-notes.md beside the call chains, and a rewritten sentence on a function
of a chain, onto that function's line in calls.md. The service listens on this machine only, writes those two
files only, and stops by itself when no page has asked anything of it for half an hour. Python 3 standard
library only; the page carries Temml (scripts/vendor, MIT) to set the formulas in notes.
"""
import argparse
import ast
import collections
import datetime
import difflib
import glob
import hmac
import http.server
import json
import mmap
import os
import posixpath
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

PARTS_FILES = ("docs/parts.md", "PARTS.md", ".bearings/parts.md", ".claude/parts.md")
SENSITIVE_RE = re.compile(r"^\s*(?:敏感|Sensitive)\s*[:：]\s*(.+)$", re.I)
ICON_RE = re.compile(r"^\s*(?:图标|Icon)\s*[:：]\s*([a-z-]+)\s*$", re.I)
FLOW_OPEN_RE = re.compile(r"^\s*```\s*flow\b[ \t]*(.*?)\s*$", re.I)  # a title may follow, for a project route
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
# What a unit is, told in a few plain sentences, and the chain of functions that does its work:
EXPLAIN_RE = re.compile(r"^\s*(?:说明|解释|Explain|Explanation)\s*[:：]\s*(.+)$", re.I)
CALLS_OPEN_RE = re.compile(r"^\s*```\s*calls\b[ \t]*(.*?)\s*$", re.I)  # a title may follow, as on a flow block
CALL_IO_RE = re.compile(r"^\s*(?:[-*]\s+)?(进|入|出|in|out)(?:\s*[:：]\s*|\s+)(\S.*)$", re.I)
CALL_SPLIT_RE = re.compile(r"\s*(?:(?<![:：])[:：](?![:：])|\|)\s*")  # `name: what it is`; a C++ `::` is part of the name
RETURN_WORDS = ("return", "returns", "返回", "返回值")
CALL_NAME_RE = re.compile(r"^[A-Za-z_$~][\w$.:~<>/\\-]*$")   # what a function is written as: a name, `Class.method`, `path/file:name`
# The call chains have a file of their own, beside the parts list: they describe the code one level closer
# than the diagrams do, and are read apart from them.
CALLS_FILES = ("calls.md", "CALLS.md")
# A chain gives the frame of the calls. What a function does line by line is the reader's to work out, and
# to keep: one note a function, in a file beside the chains. The script only reads it.
NOTES_FILE = "calls-notes.md"
SRC_LINES = 400      # lines of one function's source handed to the page
SRC_TOTAL = 1500000  # characters of source handed to the page in all
CHAIN_STEPS = 400  # lines of one chain handed to the page: its functions, and the branches and cases among them
# Which function calls which is something the script can read. So a chain need not write every function by
# hand: `展开 2` under a function has the script fill in what that function calls, two levels down, as measured.
CALL_EXPAND_RE = re.compile(r"^\s*(?:[-*]\s+)?(?:展开|expand)\s*[:：]?\s*(\d+)?\s*(?:层|levels?)?\s*$", re.I)
EXPAND_LEVELS, EXPAND_NODES = 2, 60   # how far `展开` goes when it gives no number, and how many functions at most
EXPAND_TINY = 8    # a function this short that calls nothing of the project's (a getter, a setter) is not filled in
# A chain can fork: the same journey goes one way or another depending on something (which bus, which
# encoder, which control mode). `分支 what varies` opens a fork, each `情况 name` under it is one way through.
CALL_FORK_RE = re.compile(r"^\s*(?:[-*]\s+)?(分支|情况|branch|case)(?:\s*[:：]\s*|\s+)([^|\s].*)$", re.I)
EXTERNAL_RE = re.compile(r"^\s*(?:外来|Vendored|Third-party)\s*[:：]\s*(.+)$", re.I)
FLOW_EDGE_RE = re.compile(r"^\s*(.+?)\s*(<->|->)\s*(.+?)\s*(?:[:：]\s*(.*))?$")
CODE_NAME_RE = re.compile(r"`([^`]+)`")
EXTERNAL_WORDS = ("外部", "external")
RULE_RE = re.compile(r"^\s*(?:规矩|Rule)\s*[:：]\s*(.+)$", re.I)
HISTORY = 200   # commits read for the map
RECENT_DAYS = 30
SHOWN = 80      # commits handed to the map page, which filters and trims them
SESSION_DAYS = 14   # session records older than this are not read
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
RUN_OPEN = 600      # seconds a shell command with no recorded result is taken to have run
WINDOW_HOURS = 24   # a window with no uncommitted work is still shown if it was at work here this recently
BUSY_SECONDS = 180  # a turn in progress whose record moved this recently: the window is working
HELD_SECONDS = 3600 # a turn in progress that has been still for longer than that is counted as stopped
PATCH_RE = re.compile(r'\*\*\* (?:Add File|Update File|Delete File|Move to): ([^\n\\"]+)')
# Tasks. The implementation-journal skill keeps one record per task under docs/tasks/, written for the
# next AI session. It carries a `## For People` section, the few lines meant for a person:
TASKS_DIR = "docs/tasks"
PEOPLE_HEAD_RE = re.compile(r"^##\s+(?:For People|给人看的?)\s*$", re.I)
PEOPLE_RE = re.compile(r"^\s*(?:[-*]\s+)?(名字|Name|现在|Now|等你|Needs you|下一步|Next|做成了|Done|怎么试|Try"
                       r"|还没做|Not yet|新增|Added|改了|Changed|去掉|Removed)\s*[:：]\s*(.+?)\s*$", re.I)
PEOPLE_KEYS = {"名字": "name", "name": "name", "现在": "now", "now": "now",
               "等你": "needs", "needs you": "needs", "下一步": "next", "next": "next",
               "做成了": "made", "done": "made", "怎么试": "try", "try": "try", "还没做": "left", "not yet": "left",
               "新增": "new", "added": "new", "改了": "chg", "changed": "chg", "去掉": "gone", "removed": "gone"}
# The lines above the first row say where a task stands. The rest say what a finished step came to: what was
# made, how to try it, what is left, and which boxes of which flow diagram are new, changed or gone
# (`Changed: Part / Box: one sentence`; a room goes between, `Part / Room / Box`; a line with no box is
# about the part as a whole).
MARK_RE = re.compile(r"^(.+?)\s*[:：]\s*(.+)$")
NOTHING_RE = re.compile(r"^(?:none|nothing|n/a|无|没有|暂无)\W*$", re.I)
# Recorded runs. A route is a written description; a run is the same journey measured once. One JSON file
# per run, written by scripts/bearings_run.py or by any program that writes the same shape.
RUNS_DIR = "docs/runs"
RUN_STEPS = 200    # steps of one run handed to the page
RUN_VALUES = 12    # values shown going into a step, and coming out of it
RUN_TEXT = 220     # characters of one value
RUN_HEAD = 6       # numbers shown from the start of a long list of numbers
COMMIT_RE = re.compile(r"^[0-9a-f]{4,40}$")
WHEN_RE = re.compile(r"^\d{4}-\d\d-\d\d(?:[T ]\d\d:\d\d(?::\d\d)?)?")

TEXT = {
    "zh": {
        "no_parts": "没找到部分清单（{files}）。先让 AI 按技能说明起草一份。",
        "parts_head": "{n} 个部分，{files} 个文件：",
        "files": "{n} 个文件",
        "unmapped": "未归类的文件 {n} 个：",
        "unmapped_none": "所有文件都归了类。",
        "empty_part": "没有文件的部分：{names}",
        "no_flow": "还没有流程图的 {n} 个：{names}",
        "nothing": "{since}没有任何改动。",
        "since_ref": "自 {ref} 起，",
        "since_head": "相对上次提交，",
        "since_commit": "提交 {ref}（{subject}）",
        "head": "{since}动了 {parts} 块、{files} 个文件：",
        "sensitive": "敏感：{why}",
        "unmapped_changed": "未归类",
        "by_window": "按窗口分：",
        "windows_head": "在这个项目里的窗口 {n} 个：",
        "windows_none": "没有找到最近在这个项目里干活的窗口。",
        "st_working": "在干活", "st_waiting": "停下来等你回话", "st_held": "停住了，可能在等你批准", "st_idle": "没在动", "st_": "",
        "win_said": "最近一次要它做：{x}", "win_clean": "没有未提交的改动", "win_commits": "提交了 {n} 次",
        "clash_head": "撞车 {n} 处：", "clash_none": "窗口之间没有撞车。",
        "clash_file": "{who} 都改了同一个文件：{file}（{part}）",
        "clash_merge": "同一个文件在几个工作区里都改了（{where}），合并时会冲突：{file}",
        "clash_part": "{who} 都在改“{part}”",
        "unknown_window": "没记到是哪个窗口",
        "last_at": "最后改动 {t}",
        "sep": "，",
        "words_head": "{lang}对照：{done}/{total} 处文字有译文（{files}）",
        "words_no_file": "还没有{lang}对照。页面上切到{lang}时，界面会换，清单里的文字仍按原文显示。把译文写进 {file}（函数调用链的写进 {calls}），格式见 --help；words --draft 打印待译的全部条目。",
        "words_missing": "还没有译文的 {n} 处（页面上按原文显示）：",
        "words_stale": "原文在清单里找不到了的译文 {n} 条（原文改过字？把这条的第一行改成现在的原文，或者删掉）：",
        "words_clash": "译出来和别的名字重了的 {n} 个名字（页面不用这几条，名字按原文显示；换一个译法）：",
        "words_all": "每一处文字都有译文。",
        "doctor_words_missing": "{n} 处文字还没有{lang}译文，页面切到{lang}时按原文显示（运行 words 看是哪些）",
        "doctor_head": "清单体检：{path}",
        "doctor_ok": "清单和代码对得上，没有发现问题。",
        "doctor_paths": "路径对不上任何文件的 {n} 处（代码可能挪过位置）：",
        "doctor_unmapped": "没有归类的文件 {n} 个（运行 parts 看是哪些）",
        "doctor_names": "方框的名字可能写错了 {n} 处（差一点就是另一块的名字，现在点不过去）：",
        "doctor_name": "{where} 的流程图里的“{box}”，像是“{unit}”",
        "doctor_level": "大块的流程图没有用自己的小房间当方框 {n} 个（可能和某个小房间画重了）：",
        "doctor_loose": "图上画了、代码里量不到的连接 {n} 条（走网络的属于正常，其余值得看一眼）：",
        "doctor_frame": "还没有整体框架图（清单最上面一个不带标题的 flow 块，用{level}当方框）",
        "level_wings": "各个区", "level_parts": "各个部分", "frame": "整体框架图",
        "doctor_wings": "还没有图的区 {n} 个（区标题下面一个不带标题的 flow 块，用区里的部分当方框）：",
        "doctor_orphans": "不在上一层图里的方框 {n} 个（每个方框都要出现在装着它的那张图上；不在运行路上的单独写一行，注明它服务谁）：",
        "doctor_shelf": "没有连线、也没写它服务谁的方框 {n} 个：",
        "doctor_shelf_row": "{on} 里的“{box}”",
        "doctor_open_in": "外面连着、里面没接上的线 {n} 条（上一层的图画了这条线，打开方框后里面找不到另一头）：",
        "doctor_open_in_row": "{unit}：上一层连着“{other}”{label}，它自己的图里没有",
        "doctor_said": "（{x}）",
        "doctor_open_out": "里面画了、外面没有的线 {n} 条（方框自己的图连到了外面，外面却没有一张图画这条线）：",
        "doctor_open_out_row": "{unit} 的图连着“{other}”",
        "doctor_routes_off": "主线上有、框架图里没有的连接 {n} 条：",
        "doctor_pieces": "断成几截的图 {n} 张：",
        "doctor_pieces_row": "{on}（{n} 截）",
        "doctor_unlabeled": "没写传的是什么的箭头 {n} 条：",
        "doctor_code": "箭头上写的代码名字在代码里找不到了 {n} 处（可能改过名）：",
        "doctor_code_row": "{on}：{arrow} 上的 `{name}`，“{unit}”的代码里没有",
        "doctor_stale": "画完流程图之后代码又改了不少的 {n} 个：",
        "doctor_stale_row": "{name}（画于 {date}，之后改了 {n} 次）",
        "doctor_bare": "还没有流程图的 {n} 个（运行 parts 看是哪些）",
        "doctor_limit": "体检查得出清单过时和写错，查不出一张流程图画得对不对。",
        "route": "主线",
        "outside_more": "（另有 {n} 个外来）",
        "outside": "外来：{why}",
        "uses": "{a} 用到 {b}（{n} 个文件）",
        "links_head": "从代码里量出来的连接，{n} 条（{langs}）：",
        "links_none": "没有量到连接。能量的语言：Python、JavaScript/TypeScript、Go、C/C++。",
        "mutual": "互相用到：{pairs}",
        "tasks_head": "正在做的事 {n} 件：",
        "tasks_none": "任务记录里没有正在做的事。",
        "tasks_old": "另有 {n} 件很久没动、也没有给人看的说明，没有列出。",
        "task_bare": "AI 还没有给它写给人看的说明",
        "task_updated": "{d} 更新",
        "task_now": "现在：{x}",
        "task_needs": "等你：{x}",
        "task_next": "下一步：{x}",
        "tasks_done_head": "最近做完的事 {n} 件：",
        "tasks_older_head": "更早做完的事 {n} 件：",
        "task_again": "做完过，现在重新打开了", "task_times": "第 {n} 次做完",
        "task_after": "做完之后它动过的文件又被改了 {n} 次",
        "task_made": "做成了：{x}",
        "task_try": "怎么试：{x}",
        "task_tried_ok": "试过：{d} 能用",
        "task_tried_no": "试过：{d} 不能用",
        "task_tried_again": "，之后它的代码改了 {n} 个文件，该重试了",
        "tried_head": "现在能做的事 {n} 件：",
        "tried_none": "任务记录里还没有写“做成了”的事，所以没有可以试的。",
        "tried_new": "还没试",
        "tried_ok": "试过能用（{d}）",
        "tried_no": "不能用（{d}）",
        "tried_again": "该重试（{d} 试过能用，之后改了 {n} 个文件）",
        "tried_how": "怎么试：{x}",
        "tried_note": "当时记的：{x}",
        "tried_saved": "记下了：“{name}”{d} {word}。存在 {file}。",
        "tried_which": "找不到叫“{name}”的事。能试的有：{names}",
        "tried_word": "第二个词要写 能用 或 不能用（works / broken 也行）。",
        "tried_ok_word": "能用", "tried_no_word": "不能用",
        "task_left": "还没做：{x}",
        "task_marks": "流程图上的变化：{x}",
        "mark_new": "新增", "mark_chg": "改了", "mark_gone": "去掉",
        "doctor_marks": "任务说明里对不上流程图的 {n} 处（名字要和清单里的一样，否则图上标不出来）：",
        "doctor_mark_unit": "“{task}”：清单里没有叫“{name}”的部分或房间",
        "doctor_mark_box": "“{task}”：“{unit}”的流程图里没有叫“{box}”的框",
        "task_rooms": "动过：{x}",
        "task_folder": "记录在：{x}",
        "runs_none": "还没有运行记录（{dir}/ 下没有能用的 .json）。",
        "runs_head": "{n} 条主线有运行记录：",
        "run_at": "录于 {d}", "run_commit": "提交 {c}", "run_steps": "{n} 步", "run_ms": "共 {t}",
        "run_dirty": "录制时有未提交的改动",
        "run_missed": "主线上画了、这次没经过：{x}",
        "run_aged": "录完之后这些文件又改了 {n} 次，数值可能过时",
        "run_bare": "没有运行记录的主线：{x}",
        "run_in": "进", "run_out": "出",
        "run_flag_strange": "主线上没有这个方框", "run_flag_lost": "代码里找不到这个位置",
        "run_flag_astray": "文件归“{u}”",
        "run_why_json": "不是合法的 JSON", "run_why_shape": "缺少 steps 列表",
        "run_why_route": "清单里没有叫“{route}”的主线",
        "doctor_run_missed": "主线上画了、运行时没经过的方框 {n} 个（图画错了，或者这条路径上代码跳过了它）：",
        "doctor_run_strange": "运行记录里有、主线上没有的方框 {n} 个：",
        "doctor_run_lost": "运行记录指向的代码位置找不到了 {n} 处：",
        "doctor_run_astray": "运行记录里，步骤所在的文件不归它对应的方框 {n} 处：",
        "doctor_run_astray_row": "{route}：“{box}”这一步在 {file}，这个文件归“{unit}”",
        "doctor_run_aged": "录完之后代码又改过的运行记录 {n} 份（数值可能过时）：",
        "doctor_run_aged_row": "{route}（录于 {date}，之后改了 {n} 次）",
        "doctor_run_loose": "用不上的运行记录 {n} 份：",
        "no_explain": "还没有说明的 {n} 个：{names}",
        "doctor_plain": "还没有说明的 {n} 个（运行 parts 看是哪些）",
        "doctor_calls_lost": "调用链里写了、代码里找不到的函数 {n} 个（可能改过名或删掉了）：",
        "doctor_calls_many": "调用链里的名字对得上好几个函数、分不清是哪一个的 {n} 处（写成 `类.方法` 或 `文件路径:函数`）：",
        "doctor_calls_loose": "调用链里画了、代码里量不到的调用 {n} 处（上面那个函数的代码里没有提到下面这个；经过回调、事件或网络的属于正常）：",
        "doctor_calls_names": "调用链里写的参数或变量，在那个函数里找不到的 {n} 处：",
        "doctor_calls_names_row": "{on}：{fn}() 里没有 `{name}`",
        "doctor_calls_untold": "调用链里没有写它做什么的函数 {n} 个：",
        "doctor_calls_bare": "调用链里有参数、却一个进出都没写的函数 {n} 个（写出重要的参数和变量：是什么、从哪来、到哪去）：",
        "calls_none": "还没有函数调用链。它们写在 {file} 里。",
        "calls_head": "函数调用链 {n} 条：",
        "calls_untold": "还有这些参数没写是什么：{x}",
        "calls_forks": "{n} 处分支", "calls_branch": "分支", "calls_case": "情况",
        "calls_auto": "其中 {n} 个是展开量出来的", "calls_filled": "[展开量出来的]",
        "calls_passed": "展开时略过了 {n} 个只有几行、不再调用别的函数的函数（多半是取值和设值）。",
        "calls_noted": "[有笔记]", "calls_notes": "读者的函数笔记 {n} 条，在 {file}。",
        "calls_note_lost": "笔记“{fn}”对应的函数在代码里找不到了",
        "doctor_notes_lost": "函数笔记对应的函数在代码里找不到了 {n} 条（函数改过名或删掉了；笔记是读者的，改标题，不要删）：",
        "calls_draft": "上面是量出来的调用框架：补上每个函数的一句话、每个进出的东西是什么和从哪来到哪去，删掉不值得列的，再在代码分叉的地方加分支。经回调、函数指针、事件的调用量不到，要自己读代码补。",
        "doctor_calls_forks": "只有一种情况的分支 {n} 处（分支至少要有两种走法；只有一种就直接写函数）：",
        "calls_in_list": "有 {n} 条还写在部分清单里。调用链现在有自己的文件，把它们挪到 {file}。",
        "calls_steps": "{n} 个函数，经过 {k} 个部分",
        "calls_flag_lost": "代码里找不到这个函数", "calls_flag_many": "有好几个同名函数，分不清是哪一个",
        "calls_flag_text": "这种语言不读，只按名字找到了位置",
        "calls_flag_loose": "上面那个函数的代码里没有提到它",
        "calls_flag_name": "函数里找不到这个名字",
        "calls_many": "有好几个函数叫 {fn}，写成 `类.方法` 或 `文件路径:函数` 来指明：",
        "calls_lost": "代码里找不到函数 {fn}。能读的语言：Python、JavaScript/TypeScript、Go、C/C++。",
        "calls_tree": "{fn} 调用了谁（从代码里量的，往下 {d} 层）：",
        "calls_again": "（上面列过）",
        "calls_unsure": "还调用了这些名字，各有好几个函数对得上，没有往下跟：{x}",
        "calls_limit": "只列项目自己定义的函数。经过回调、事件、继承或网络的调用量不到；按名字调用的方法只在对得上唯一一个函数时才跟。",
    },
    "en": {
        "no_parts": "No parts list found ({files}). Have the agent draft one first, following the skill.",
        "parts_head": "{n} parts, {files} files:",
        "files": "{n} files",
        "unmapped": "{n} unmapped files:",
        "unmapped_none": "Every file belongs to a part.",
        "empty_part": "Parts with no files: {names}",
        "no_flow": "{n} without a flow diagram: {names}",
        "nothing": "{since}nothing changed.",
        "since_ref": "Since {ref}, ",
        "since_head": "Against the last commit, ",
        "since_commit": "Commit {ref} ({subject}) ",
        "head": "{since}{parts} parts and {files} files changed:",
        "sensitive": "sensitive: {why}",
        "unmapped_changed": "Unmapped",
        "by_window": "By window:",
        "windows_head": "{n} windows at work in this project:",
        "windows_none": "No window has been at work in this project lately.",
        "st_working": "working", "st_waiting": "stopped, waiting for your reply", "st_held": "held up, perhaps waiting for your approval", "st_idle": "idle", "st_": "",
        "win_said": "last asked: {x}", "win_clean": "nothing uncommitted", "win_commits": "{n} commits",
        "clash_head": "{n} places where windows collide:", "clash_none": "No window is in another's way.",
        "clash_file": "{who} both changed the same file: {file} ({part})",
        "clash_merge": "the same file is changed in several checkouts ({where}) and will conflict on merge: {file}",
        "clash_part": "{who} are both changing \"{part}\"",
        "unknown_window": "no window on record",
        "last_at": "last edit {t}",
        "sep": ", ",
        "words_head": "{lang} translations: {done} of {total} texts have one ({files})",
        "words_no_file": "No {lang} translations yet. With the page switched to {lang}, its own words change and the list's stay as written. Write the translations into {file} (those of the call chains into {calls}); --help gives the format, and words --draft prints every entry still to translate.",
        "words_missing": "{n} texts with no translation yet (the page shows them as written):",
        "words_stale": "{n} translations whose original is no longer on the list (reworded? change the entry's first line to the text as it is now, or delete the entry):",
        "words_clash": "{n} names whose translation is the same as another name (the page leaves these names as written; choose another word):",
        "words_all": "Every text has a translation.",
        "doctor_words_missing": "{n} texts have no {lang} translation yet and show as written when the page is switched to {lang} (run words to see which)",
        "doctor_head": "Check-up of {path}",
        "doctor_ok": "The list agrees with the code; nothing found.",
        "doctor_paths": "{n} paths that match no file (the code may have moved):",
        "doctor_unmapped": "{n} unmapped files (run parts to see them)",
        "doctor_names": "{n} box names that may be misspelt (close to another unit's name, so no door opens):",
        "doctor_name": "\"{box}\" in the flow of {where} looks like \"{unit}\"",
        "doctor_level": "{n} parts whose flow does not use their own rooms as boxes (it may repeat a room's diagram):",
        "doctor_loose": "{n} arrows between parts that the code does not back (fine over a network, worth a look otherwise):",
        "doctor_frame": "No diagram of the whole project yet (one untitled flow block at the top of the list, with {level} as its boxes)",
        "level_wings": "the wings", "level_parts": "the parts", "frame": "the project diagram",
        "doctor_wings": "{n} wings without a diagram (one untitled flow block under the wing's heading, with its parts as the boxes):",
        "doctor_orphans": "{n} boxes missing from the diagram one level up (every box appears on the diagram of what holds it; one that is not on the path at run time gets a line of its own, with a note saying whom it serves):",
        "doctor_shelf": "{n} boxes with no arrow and no note saying whom they serve:",
        "doctor_shelf_row": "\"{box}\" in {on}",
        "doctor_open_in": "{n} lines drawn outside a box that do not arrive inside it (the level above draws the line; the box's own diagram does not show the other end):",
        "doctor_open_in_row": "{unit}: the level above connects it to \"{other}\"{label}; its own diagram does not show that",
        "doctor_said": " ({x})",
        "doctor_open_out": "{n} lines drawn inside a box that nothing outside it draws (its own diagram reaches out; no diagram outside it shows that line):",
        "doctor_open_out_row": "the diagram of {unit} connects to \"{other}\"",
        "doctor_routes_off": "{n} links on a route that the framework diagrams do not have:",
        "doctor_pieces": "{n} diagrams in more than one piece:",
        "doctor_pieces_row": "{on} ({n} pieces)",
        "doctor_unlabeled": "{n} arrows that do not say what travels along them:",
        "doctor_code": "{n} code names on arrows that the code no longer holds (renamed, perhaps):",
        "doctor_code_row": "{on}: `{name}` on {arrow} is not in the code of \"{unit}\"",
        "doctor_stale": "{n} units whose code changed a good deal after the flow was drawn:",
        "doctor_stale_row": "{name} (drawn {date}, {n} changes since)",
        "doctor_bare": "{n} without a flow diagram (run parts to see them)",
        "doctor_limit": "A check-up finds a list that is out of date or miswritten. It cannot tell whether a flow diagram is true.",
        "route": "route",
        "outside_more": " (plus {n} from outside)",
        "outside": "from outside: {why}",
        "uses": "{a} uses {b} ({n} files)",
        "links_head": "{n} links measured from the code ({langs}):",
        "links_none": "No links measured. Languages it can measure: Python, JavaScript/TypeScript, Go, C/C++.",
        "mutual": "use each other: {pairs}",
        "tasks_head": "{n} tasks in progress:",
        "tasks_none": "The task records hold nothing in progress.",
        "tasks_old": "{n} more have not moved in a long time and carry no lines for people; they are not listed.",
        "task_bare": "the agent has not written its lines for people yet",
        "task_updated": "updated {d}",
        "task_now": "Now: {x}",
        "task_needs": "Needs you: {x}",
        "task_next": "Next: {x}",
        "tasks_done_head": "{n} finished lately:",
        "tasks_older_head": "{n} finished earlier:",
        "task_again": "finished once, open again", "task_times": "finished for the {n}th time",
        "task_after": "the files it changed were changed {n} times since",
        "task_made": "Done: {x}",
        "task_try": "Try: {x}",
        "task_tried_ok": "Tried: {d}, works",
        "task_tried_no": "Tried: {d}, broken",
        "task_tried_again": "; {n} of its files changed since, worth trying again",
        "tried_head": "{n} things the project can do now:",
        "tried_none": "No task record says what was made yet, so there is nothing to try.",
        "tried_new": "not tried yet",
        "tried_ok": "tried, works ({d})",
        "tried_no": "broken ({d})",
        "tried_again": "try again (worked on {d}; {n} files changed since)",
        "tried_how": "Try: {x}",
        "tried_note": "Noted then: {x}",
        "tried_saved": "Kept: \"{name}\" {d} {word}. It is in {file}.",
        "tried_which": "No task called \"{name}\". The ones that can be tried: {names}",
        "tried_word": "The second word has to be works or broken (能用 / 不能用 are read too).",
        "tried_ok_word": "works", "tried_no_word": "broken",
        "task_left": "Not yet: {x}",
        "task_marks": "Changes on the flow diagrams: {x}",
        "mark_new": "added", "mark_chg": "changed", "mark_gone": "removed",
        "doctor_marks": "{n} marks in the tasks' lines for people that miss the flow diagrams (a name must match the list, or the page cannot mark it):",
        "doctor_mark_unit": '"{task}": no part or room on the list is called "{name}"',
        "doctor_mark_box": '"{task}": the flow diagram of "{unit}" has no box called "{box}"',
        "task_rooms": "Touched: {x}",
        "task_folder": "Recorded in: {x}",
        "runs_none": "No recorded runs yet (no usable .json under {dir}/).",
        "runs_head": "{n} routes have a recorded run:",
        "run_at": "recorded {d}", "run_commit": "commit {c}", "run_steps": "{n} steps", "run_ms": "{t} in all",
        "run_dirty": "recorded with uncommitted changes",
        "run_missed": "drawn on the route, not passed in this run: {x}",
        "run_aged": "these files changed {n} times after the recording; the values may be out of date",
        "run_bare": "routes with no recorded run: {x}",
        "run_in": "in", "run_out": "out",
        "run_flag_strange": "no such box on the route", "run_flag_lost": "this place is not in the code",
        "run_flag_astray": "the file belongs to \"{u}\"",
        "run_why_json": "not valid JSON", "run_why_shape": "no list of steps",
        "run_why_route": "the list has no route called \"{route}\"",
        "doctor_run_missed": "{n} boxes drawn on a route that its recorded run did not pass (the diagram is wrong, or the code skipped them on this path):",
        "doctor_run_strange": "{n} boxes in a recorded run that its route does not have:",
        "doctor_run_lost": "{n} places a recorded run points at that are no longer in the code:",
        "doctor_run_astray": "{n} steps of a recorded run whose file does not belong to the step's box:",
        "doctor_run_astray_row": "{route}: the step \"{box}\" is in {file}, which belongs to \"{unit}\"",
        "doctor_run_aged": "{n} recorded runs whose code changed after the recording (the values may be out of date):",
        "doctor_run_aged_row": "{route} (recorded {date}, {n} changes since)",
        "doctor_run_loose": "{n} recorded runs that cannot be used:",
        "no_explain": "{n} without an explanation: {names}",
        "doctor_plain": "{n} without an explanation (run parts to see them)",
        "doctor_calls_lost": "{n} functions named in a call chain that the code does not have (renamed or removed, perhaps):",
        "doctor_calls_many": "{n} names in a call chain that several functions answer to (write `Class.method` or `path/file:function`):",
        "doctor_calls_loose": "{n} calls drawn in a call chain that the code does not show (the function above never mentions the one below; fine through a callback, an event or a network):",
        "doctor_calls_names": "{n} parameters or variables written in a call chain that the function does not have:",
        "doctor_calls_names_row": "{on}: {fn}() has no `{name}`",
        "doctor_calls_untold": "{n} functions on a call chain with no sentence saying what they do:",
        "doctor_calls_bare": "{n} functions on a call chain that take parameters, with nothing written going in or coming out (name the important parameters and variables: what each is, where it comes from, where it goes):",
        "calls_none": "No call chains yet. They are kept in {file}.",
        "calls_head": "{n} call chains:",
        "calls_untold": "parameters it does not explain: {x}",
        "calls_forks": "{n} branches", "calls_branch": "branch", "calls_case": "case",
        "calls_auto": "{n} of them filled in from the code", "calls_filled": "[filled in from the code]",
        "calls_passed": "{n} functions of a few lines that call nothing further (getters and setters, mostly) were left out when filling in.",
        "calls_noted": "[has a note]", "calls_notes": "{n} function notes kept by readers, in {file}.",
        "calls_note_lost": "the note \"{fn}\" is on a function the code no longer has",
        "doctor_notes_lost": "{n} function notes on a function the code no longer has (renamed or removed; the notes are a reader's: change the heading, do not delete):",
        "calls_draft": "Above is the frame of the calls as measured: add each function's sentence, say what each thing going in or out is and where it comes from or goes, drop what is not worth listing, and fork it where the code forks. Calls through a callback, a function pointer or an event are not seen; read the code for those.",
        "doctor_calls_forks": "{n} branches with a single case (a branch has at least two ways through; with one, write the functions plainly):",
        "calls_in_list": "{n} are still written inside the parts list. Call chains have a file of their own now: move them to {file}.",
        "calls_steps": "{n} functions across {k} parts",
        "calls_flag_lost": "the code has no such function", "calls_flag_many": "several functions answer to this name",
        "calls_flag_text": "a language that is not read: found by name only",
        "calls_flag_loose": "the function above never mentions it",
        "calls_flag_name": "the function has no such name",
        "calls_many": "Several functions are called {fn}; write `Class.method` or `path/file:function` to say which:",
        "calls_lost": "No function {fn} in the code. Languages it can read: Python, JavaScript/TypeScript, Go, C/C++.",
        "calls_tree": "What {fn} calls (measured from the code, {d} levels down):",
        "calls_again": "(listed above)",
        "calls_unsure": "it also calls these names, each of which several functions answer to; not followed: {x}",
        "calls_limit": "Only functions the project itself defines are listed. Calls through a callback, an event, inheritance or a network are not seen; a method called by name is followed only when one function answers to it.",
    },
}


def git(root, *args, stdin=None):
    out = subprocess.run(["git", "-C", root, *args], input=stdin, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(out.stderr.decode("utf-8", "replace").strip() or "git failed")
    return out.stdout


def repo_root():
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("bearings: not inside a git repository")
    return out.stdout.strip()


def state_path(root):
    git_dir = git(root, "rev-parse", "--git-dir").decode().strip()
    if not os.path.isabs(git_dir):
        git_dir = os.path.join(root, git_dir)
    return os.path.join(git_dir, "bearings", "map.html")


def zlist(raw):
    return [p for p in raw.decode("utf-8", "surrogateescape").split("\0") if p]


# Parts list ---------------------------------------------------------------

class Part:
    """A part of the project, or a sub-part inside one (then .parent is set)."""

    def __init__(self, name, parent=None):
        self.name, self.what, self.sensitive, self.patterns, self.rules = name, "", "", [], []
        self.group, self.icon, self.flow = "", "", None
        self.parent, self.children, self.external = parent, [], ""
        self.wing = None     # the Wing a top-level part sits in, when the list has wings
        self.explain = []    # a few plain sentences: how it does its job, and why the project needs it
        self.calls = []      # the chains of functions that do its work, as written
        self.lines = [0, 0]  # where it is written in the list: first line, one past the last

    @property
    def top(self):
        return self.parent or self

    @property
    def outside(self):
        """Code copied in from elsewhere: it is drawn apart and left out of the project's own counts."""
        return self.external or (self.parent.external if self.parent else "")


class Wing:
    """The parts under one `#` heading. A wing can say what it is for and carry a diagram of how its parts
    work together; the diagram of the whole project uses the wings as its boxes."""

    def __init__(self, name):
        self.name, self.what, self.icon, self.flow, self.parts = name, "", "", None, []
        self.explain = []


def flow_node(flow, name):
    for node in flow["nodes"]:
        if node["name"] == name:
            return node
    node = {"name": name, "note": "", "icon": "", "ext": False}
    flow["nodes"].append(node)
    return node


def flow_line(flow, line):
    """`A -> B: label` draws an arrow (`<->` points both ways); `A | note | icon | 外部` describes a box."""
    if not line.strip():
        return
    edge = FLOW_EDGE_RE.match(line)
    if edge:
        a, arrow, b, label = edge.groups()
        flow_node(flow, a)
        flow_node(flow, b)
        label = label or ""
        code = [x.strip() for x in CODE_NAME_RE.findall(label) if x.strip()]  # `Name`: what the code calls it
        flow["edges"].append({"a": a, "b": b, "label": CODE_NAME_RE.sub("", label).strip(" ,，、"),
                              "both": arrow == "<->", "code": code})
        return
    fields = [x.strip() for x in line.split("|")]
    node = flow_node(flow, fields[0])
    for field in fields[1:]:
        if field.lower() in EXTERNAL_WORDS:
            node["ext"] = True
        elif re.fullmatch(r"[a-z-]+", field):
            node["icon"] = field
        elif field:
            node["note"] = field


def call_name(field):
    """A function as a chain writes it: `f`, `f()` and `f(a, b)` are f."""
    return re.sub(r"\s*\(.*\)\s*$", "", field.strip().strip("`").strip()).strip("`").strip()


def calls_line(chain, line, stack, at=None):
    """One line of a call chain. `function | what it does` names a function; one set in under another is
    called by it. Under a function, `进 name: what it is | where it comes from` (or `in`) is something that
    goes into it and `出 name: what it is | where it goes` (`out`) something that comes out: a parameter, a
    variable, a field, the return value. Any other line under a function is more of its explanation.
    A `function | sentence` line set in under `展开` gives that sentence to one of the functions filled in
    there. `at` is the number of the line in its file; a step remembers it, so the page can hand a
    sentence a reader rewrote back to that line."""
    if not line.strip():
        return
    line = line.expandtabs(4)
    io = CALL_IO_RE.match(line)
    if io and chain["steps"] and chain["steps"][-1]["kind"] == "fn":
        bits = CALL_SPLIT_RE.split(io.group(2).strip(), 1)
        name = bits[0].strip().strip("`").strip()
        rest = [x.strip() for x in (bits[1] if len(bits) > 1 else "").split("|")]
        if name:
            chain["steps"][-1]["outs" if io.group(1).lower() in ("出", "out") else "ins"].append(
                {"name": name, "what": rest[0], "via": " ".join(x for x in rest[1:] if x)})
        return
    indent = len(line) - len(line.lstrip())
    grow = CALL_EXPAND_RE.match(line)
    if grow:   # the functions called from here on are filled in from the code
        while stack and stack[-1] >= indent:
            stack.pop()
        chain["steps"].append({"kind": "expand", "fn": "", "what": "", "note": "", "more": [], "depth": min(len(stack), 60),
                               "levels": max(1, min(5, int(grow.group(1) or EXPAND_LEVELS))), "ins": [], "outs": [],
                               "at": at, "indent": indent, "says": {}})
        return
    fork = CALL_FORK_RE.match(line)
    fields = [x.strip() for x in re.sub(r"^\s*[-*]\s+", "", fork.group(2) if fork else line).strip().split("|")]
    last = chain["steps"][-1] if chain["steps"] else None
    if last and last["kind"] == "expand" and indent > last["indent"]:
        # set in under `展开`: a sentence for one of the functions the script fills in there
        if not fork and CALL_NAME_RE.match(call_name(fields[0])):
            last["says"][call_name(fields[0])] = " ".join(x for x in fields[1:] if x)
        return
    if fork:   # `分支 what varies | a note` and, under it, `情况 name | when it applies`
        kind, name = "branch" if fork.group(1).lower() in ("分支", "branch") else "case", ""
    else:
        kind = "fn"
        name = call_name(fields[0])
        if not CALL_NAME_RE.match(name):
            if chain["steps"]:   # a sentence, not a function: it belongs to the line above
                chain["steps"][-1]["more"].append(line.strip())
            return
    while stack and stack[-1] >= indent:
        stack.pop()
    chain["steps"].append({"kind": kind, "fn": name, "what": " ".join(x for x in (fields if fork else fields[1:]) if x)
                           if kind == "fn" else fields[0].rstrip(":："), "note": " ".join(x for x in fields[1:] if x) if fork else "",
                           "more": [], "depth": min(len(stack), 60), "ins": [], "outs": [], "at": at})
    stack.append(indent)


def read_calls(text):
    """The call chains of a file of their own: [chain]. A heading names a chain, the plain lines under it say
    what the chain is about, and a ```calls block holds its functions. A block can also carry its title on
    the fence. A heading with no block under it (the file's own title, say) names nothing."""
    chains, chain, stack, title, intro, fenced = [], None, [], "", [], False
    for at, line in enumerate(text.split("\n")):
        if chain is not None:
            if line.strip().startswith("```"):
                chain = None
            else:
                calls_line(chain, line, stack, at)
            continue
        if fenced:
            fenced = not line.strip().startswith("```")
            continue
        called = CALLS_OPEN_RE.match(line)
        if called:
            chain, stack = {"title": called.group(1) or title, "intro": intro, "steps": []}, []
            chains.append(chain)
            intro = []   # a second block under the same heading starts with no words of its own
            continue
        if line.strip().startswith("```"):
            fenced = True
            continue
        head = HEAD_RE.match(line)
        if head:
            title, intro = head.group(2).strip().strip("`"), []
        elif line.strip() and not line.lstrip().startswith(("<!--", "|", ">")):
            intro.append(re.sub(r"^\s*[-*]\s+", "", line).strip())
    return [c for c in chains if c["steps"]]


def read_notes(text):
    """The notes of a notes file: [(the function its heading names, the note)]. A `##` heading names a
    function, as a chain would (`name`, `Class.method`, `path/file:name`); everything down to the next such
    heading is the note, kept as written."""
    notes, name, body, fenced = [], None, [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        head = None if fenced else re.match(r"^##\s+(.+?)\s*$", line)
        if head:
            if name is not None:
                notes.append((name, "\n".join(body).strip("\n")))
            name, body = head.group(1).strip().strip("`").strip(), []
            name = re.sub(r"\s*\(.*\)\s*$", "", name)
        elif name is not None:
            body.append(line.rstrip())
    if name is not None:
        notes.append((name, "\n".join(body).strip("\n")))
    return [(n, b) for n, b in notes if b.strip()]


def calls_path(root, list_path, explicit=None):
    """Where the call chains are kept: beside the parts list. Returns (the file to read, or "" when there is
    none yet; where one would be written, relative to the repo)."""
    folder = os.path.dirname(os.path.abspath(list_path))
    want = os.path.join(root, explicit) if explicit and not os.path.isabs(explicit) else explicit
    cands = [want] if want else [os.path.join(folder, name) for name in CALLS_FILES]
    home = os.path.relpath(cands[0], root).replace(os.sep, "/")
    for path in cands:
        if os.path.isfile(path):
            return path, os.path.relpath(path, root).replace(os.sep, "/")
    return "", home


def literal_len(pattern):
    star = pattern.find("*")
    return len(pattern) if star < 0 else star


def compile_pattern(pattern):
    """Only * is special (it stops at a slash; ** crosses them). A trailing / owns the whole folder."""
    if pattern.endswith("/"):
        return lambda path, p=pattern: path.startswith(p)
    if "*" not in pattern:
        return lambda path, p=pattern: path == p
    rx = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.compile("^" + rx + "$").match


def title_form(lines):
    """A list may start with one `#` title, for projects whose Markdown rules allow a single top-level
    heading. Every level then sits one deeper: `##` is a wing, `###` a part, `####` a sub-part."""
    tops, deeper, owning, level, fenced = 0, False, False, 0, False
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if fenced:
            continue
        head = HEAD_RE.match(line)
        if head:
            level = len(head.group(1))
            tops += level == 1
            deeper = deeper or level == 3
        elif level == 2 and line.lstrip().startswith(("- ", "* ")) and "`" in line:
            owning = True  # a `##` that owns paths is a part, so `#` is a wing
    return tops == 1 and deeper and not owning


def load_parts(root, explicit=None):
    """Returns (parts, path, routes, top). Flow blocks outside any part are read by where they stand and
    whether they carry a title. With a title: a route, how one thing travels through the project. Without
    one: the diagram of the level they stand at, which is the whole project before the first heading and a
    wing right under its `#` heading. `top` holds those two: {"frame": flow or None, "wings": [Wing]},
    and with them what else stands outside every part: "explain", the project told in a few sentences, and
    "chains", the call chains that carry a title (one for a route goes by the route's title)."""
    candidates = [explicit] if explicit else list(PARTS_FILES)
    for rel in candidates:
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if os.path.isfile(path):
            break
    else:
        return None, None, [], {"frame": None, "wings": [], "explain": [], "chains": []}
    parts, routes, top = read_list(open(path, encoding="utf-8").read())
    return parts, path, routes, top


def read_list(text):
    """The parts list from its text: (parts, routes, top)."""
    lines = text.split("\n")
    shift = 1 if title_form(lines) else 0
    parts, routes, cur, top, group, flow = [], [], None, None, "", None
    frame, wings, wing = None, [], None
    chains, chain, stack, about, fenced = [], None, [], [], False
    for at, line in enumerate(lines):
        if cur is not None:
            cur.lines[1] = at + 1
        if flow is not None:
            if line.strip().startswith("```"):
                flow = None
            else:
                flow_line(flow, line)
            continue
        if chain is not None:
            if line.strip().startswith("```"):
                chain = None
            else:
                calls_line(chain, line, stack)
            continue
        if fenced:  # any other fenced block is not ours to read
            fenced = not line.strip().startswith("```")
            continue
        called = CALLS_OPEN_RE.match(line)
        if called:
            chain, stack = {"title": called.group(1), "intro": [], "steps": []}, []
            (cur.calls if cur is not None else chains).append(chain)
            continue
        opened = FLOW_OPEN_RE.match(line)
        if opened:
            if cur is not None:
                flow = cur.flow = cur.flow or {"nodes": [], "edges": []}
            elif opened.group(1):
                flow = {"title": opened.group(1), "nodes": [], "edges": []}
                routes.append(flow)
            elif wing is not None:
                flow = wing.flow = wing.flow or {"nodes": [], "edges": []}
            else:
                flow = frame = frame or {"nodes": [], "edges": []}
            continue
        if line.strip().startswith("```"):
            fenced = True
            continue
        head = HEAD_RE.match(line)
        if head:
            level, name = len(head.group(1)) - shift, head.group(2)
            if level == 1:    # a wing groups the parts under it
                group, cur, top = name, None, None
                wing = Wing(name)
                wings.append(wing)
            elif level == 2:
                cur = top = Part(name)
                cur.group, cur.lines = group, [at, at + 1]
                parts.append(cur)
                if wing is not None:
                    cur.wing = wing
                    wing.parts.append(cur)
            elif level == 3 and top is not None:
                cur = Part(name, top)
                cur.group, cur.lines = group, [at, at + 1]
                top.children.append(cur)
            elif level < 1:
                cur = top = wing = None
            continue
        if not line.strip():
            continue
        told = EXPLAIN_RE.match(line)
        if cur is None:
            if told:  # before the first heading it is about the whole project, under a wing's about the wing
                (wing.explain if wing is not None else about).append(told.group(1).strip())
            elif wing is not None:  # under a wing's heading: its pictogram, and one line on what the wing is for
                icon = ICON_RE.match(line)
                if icon:
                    wing.icon = icon.group(1).lower()
                elif not wing.what and not line.lstrip().startswith(("#", ">", "-", "*", "`", "|")):
                    wing.what = line.strip()
            continue
        if told:
            cur.explain.append(told.group(1).strip())
            continue
        sens = SENSITIVE_RE.match(line)
        rule = RULE_RE.match(line)
        icon = ICON_RE.match(line)
        ext = EXTERNAL_RE.match(line)
        if icon:
            cur.icon = icon.group(1).lower()
        elif sens:
            cur.sensitive = sens.group(1).strip()
        elif ext:
            cur.external = ext.group(1).strip()
        elif rule:
            cur.rules.append(rule.group(1).strip())
        elif line.lstrip().startswith(("- ", "* ")):
            for pat in re.findall(r"`([^`]+)`", line):
                cur.patterns.append((pat, compile_pattern(pat), literal_len(pat)))
        elif not cur.what and not line.startswith(("#", ">")):
            cur.what = line.strip()
    return parts, routes, {"frame": frame if frame and frame["nodes"] else None,
                           "wings": [w for w in wings if w.parts], "explain": about,
                           "chains": [c for c in chains if c["steps"]]}


# Wiring -------------------------------------------------------------------
# The list is a set of boxes inside boxes: the project holds wings, a wing holds parts, a part holds rooms.
# Each level has its own diagram, drawn with the boxes of the level below. Read together they are one
# wiring: an arrow drawn at one level has to come out somewhere at the level inside it, the way a wire
# into a block comes out at a port inside the block. This section resolves the two ends of every arrow to
# the units they stand for, so the page can show what goes in and out of each box and the check-up can say
# where two levels stopped agreeing.

def unit_up(u):
    """The unit that holds this one: a room's part, a part's wing."""
    return None if isinstance(u, Wing) else (u.parent or u.wing)


def unit_kids(u):
    return u.parts if isinstance(u, Wing) else u.children


def within(x, u):
    """Is unit u the unit x, or somewhere inside it?"""
    while u is not None and not isinstance(u, str):
        if u is x:
            return True
        u = unit_up(u)
    return False


def related(a, b):
    """The same box, or one inside the other. A name that stands for no unit matches only itself."""
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return within(a, b) or within(b, a)


def unit_label(u):
    if isinstance(u, str):
        return u
    return (u.parent.name + " / " if not isinstance(u, Wing) and u.parent else "") + u.name


class Wiring:
    """Every arrow of every diagram, with both ends resolved. An end is a unit (Wing or Part), or a plain
    name for someone or something outside the project (a person, an outside service, whoever starts or
    ends a route)."""

    def __init__(self, parts, routes, top):
        self.parts, self.wings, self.frame, self.routes = parts, top["wings"], top["frame"], routes
        self.rooms = [c for p in parts for c in p.children]
        self.ids = {}
        for i, w in enumerate(self.wings):
            self.ids[w] = "w%d" % i
        for i, p in enumerate(parts):
            self.ids[p] = "p%d" % i
            for j, c in enumerate(p.children):
                self.ids[c] = "p%d.%d" % (i, j)
        # (the unit whose diagram it is, or None; where it is; the flow; its kind)
        self.diagrams = [(None, "", self.frame, "frame")] if self.frame else []
        self.diagrams += [(None, r["title"], r, "route") for r in routes]
        self.diagrams += [(w, w.name, w.flow, "unit") for w in self.wings if w.flow and w.flow["nodes"]]
        self.diagrams += [(u, unit_label(u), u.flow, "unit") for p in parts for u in [p] + p.children
                          if u.flow and u.flow["nodes"]]
        # Names that stand outside the project wherever they appear: a person, an outside service, and
        # the plain boxes of the project's diagram and of the routes.
        self.actors = set()
        for owner, _, flow, kind in self.diagrams:
            for n in flow["nodes"]:
                if n["ext"] or ((n["icon"] == "user" or owner is None) and self.unit(n["name"], owner, kind) is None):
                    self.actors.add(n["name"])
        self.wires = []
        for owner, where, flow, kind in self.diagrams:
            ends = {n["name"]: self.end(n, owner, kind) for n in flow["nodes"]}
            for n in flow["nodes"]:
                e = ends[n["name"]]
                n["to"] = "" if isinstance(e, str) or e is owner else self.ids[e]
                # outside the box this diagram opens up: drawn at its edge, as something the box connects to
                n["outer"] = kind != "route" and (isinstance(e, str) or (owner is not None and not within(owner, e)))
            for edge in flow["edges"]:
                a, b = ends[edge["a"]], ends[edge["b"]]
                if a is b or (not isinstance(a, str) and not isinstance(b, str) and related(a, b)):
                    continue  # a step inside the unit, or between a unit and something in it
                self.wires.append({"a": a, "b": b, "edge": edge, "owner": owner, "where": where, "kind": kind})

    def unit(self, name, owner, kind="unit"):
        """The unit a box name stands for, in the diagram of `owner`. The nearest one wins: something
        inside the owner, then beside it, then anywhere."""
        if owner is None:
            order = self.wings + self.parts + self.rooms if kind == "frame" else self.parts + self.rooms + self.wings
        else:
            up = unit_up(owner)
            order = unit_kids(owner) + (unit_kids(up) if up is not None else []) + self.parts + self.wings + self.rooms
        for u in order:
            if u.name == name:
                return u
        return None

    def end(self, node, owner, kind):
        if node["ext"]:
            return node["name"]
        u = self.unit(node["name"], owner, kind)
        if u is not None:
            return u
        if owner is None or node["name"] in self.actors:
            return node["name"]
        return owner  # a plain box in a unit's own diagram is a step of that unit

    def boxes(self, unit):
        """What the unit's own diagram shows, each box resolved."""
        if not (unit.flow and unit.flow["nodes"]):
            return None
        return [self.end(n, unit, "unit") for n in unit.flow["nodes"]]

    def parent_flow(self, unit):
        """The diagram one level up, where this unit is a box: (flow, its owner or None), or (None, None)."""
        up = unit_up(unit)
        if up is None:
            return self.frame, None
        return (up.flow if up.flow and up.flow["nodes"] else None), up

    def crossings(self, unit):
        """Every arrow, drawn on a diagram outside the unit, with one end in the unit and the other not:
        (the other end, which way, the arrow, where it is drawn, must, met). `must` marks the ones on the
        diagram one level up, where the unit is a box: its own diagram has to show the other end of those.
        `met` says whether it does (None when the unit has no diagram yet)."""
        inside = self.boxes(unit)
        up = unit_up(unit)
        for w in self.wires:
            ia, ib = within(unit, w["a"]), within(unit, w["b"])
            if ia == ib or (w["owner"] is not None and within(unit, w["owner"])):
                continue
            other, via, e = (w["b"], w["a"], w["edge"]) if ia else (w["a"], w["b"], w["edge"])
            must = w["kind"] != "route" and w["owner"] is up and via is unit
            met = None if inside is None else any(related(x, other) for x in inside)
            yield other, "both" if e["both"] else ("out" if ia else "in"), e, w["where"], must, met

    def ports(self, unit):
        """What goes into the unit and what comes out, told at the unit's own level: a neighbour deep
        inside another part or wing is shown as the box that stands beside this unit and holds it. One
        row for each neighbour and direction, with the words of every arrow that runs between them."""
        above = set()
        up = unit_up(unit)
        while up is not None:
            above.add(up)
            up = unit_up(up)
        rows, seen = [], {}
        for other, way, e, where, must, met in self.crossings(unit):
            while not isinstance(other, str) and unit_up(other) is not None and unit_up(other) not in above:
                other = unit_up(other)
            key = (other if isinstance(other, str) else id(other), way)
            row = seen.get(key)
            if row is None:
                row = seen[key] = {"other": other, "dir": way, "labels": [], "code": [], "must": False,
                                   "met": None, "where": where}
                rows.append(row)
            if e["label"] and e["label"] not in row["labels"]:
                row["labels"].append(e["label"])
            row["code"] += [c for c in e["code"] if c not in row["code"]]
            if must:
                row["must"], row["where"] = True, where
                row["met"] = met if row["met"] is None else (row["met"] and met)
        # a neighbour that things travel both ways with is one row: its one-way arrows are folded into it
        for both in [r for r in rows if r["dir"] == "both"]:
            for r in [r for r in rows if r is not both and r["other"] is both["other"]]:
                both["labels"] += [x for x in r["labels"] if x not in both["labels"]]
                both["code"] += [x for x in r["code"] if x not in both["code"]]
                if r["must"]:
                    both["met"] = r["met"] if not both["must"] else (both["met"] and r["met"])
                    both["must"] = True
                rows.remove(r)
        return rows

    def backed(self, unit, other, routes=True):
        """Does any diagram outside `unit` draw a line from its box (or from something in it) to `other`,
        or to what holds `other`, or to something in `other`? An arrow drawn only inside a unit, reaching
        out to a neighbour that nothing outside the unit connects it to, is a wire with one loose end.
        A line between the wings the two sit in is not enough: that says the wings are connected, not
        that this box is."""
        for w in self.wires:
            if (w["owner"] is not None and within(unit, w["owner"])) or (w["kind"] == "route" and not routes):
                continue
            if (within(unit, w["a"]) and related(w["b"], other)) or (within(unit, w["b"]) and related(w["a"], other)):
                return True
        return False

    def problems(self):
        """Where the levels do not agree. Each finding is a short row of plain facts; nothing here is a rule
        about the code, only about the drawings."""
        out = {"open_in": [], "open_out": [], "orphans": [], "shelf": [], "routes_off": [], "unlabeled": [],
               "pieces": [], "wings_bare": [], "no_frame": False}
        units = self.wings + [u for p in self.parts for u in [p] + p.children]
        tops = self.wings or self.parts
        out["no_frame"] = self.frame is None and len(tops) > 1
        out["wings_bare"] = [w.name for w in self.wings if len(w.parts) > 1 and not (w.flow and w.flow["nodes"])]
        for u in units:
            if not isinstance(u, Wing) and u.outside:
                continue
            flow, owner = self.parent_flow(u)
            if flow is None:
                continue
            ends = [self.end(n, owner, "frame" if owner is None else "unit") for n in flow["nodes"]]
            if isinstance(u, Part) and u.parent and not any(e in u.parent.children for e in ends):
                continue  # the part's diagram uses none of its rooms: reported once, as drawn at the wrong level
            if not any(e is u for e in ends):
                out["orphans"].append({"unit": unit_label(u), "on": unit_label(owner) if owner else ""})
        for u in units:
            for other, way, e, _, must, met in self.crossings(u):
                if must and met is False:
                    out["open_in"].append({"unit": unit_label(u), "other": unit_label(other),
                                           "label": e["label"], "dir": way})
            seen = set()
            for w in self.wires if self.parent_flow(u)[0] is not None else []:
                if w["owner"] is not u:  # until the level above is drawn there is nothing to agree with
                    continue
                ia, ib = within(u, w["a"]), within(u, w["b"])
                if ia == ib:
                    continue
                other = w["b"] if ia else w["a"]
                if isinstance(other, str) or id(other) in seen:
                    continue
                seen.add(id(other))
                if not self.backed(u, other):
                    out["open_out"].append({"unit": unit_label(u), "other": unit_label(other)})
        structural = self.frame is not None or any(w.flow and w.flow["nodes"] for w in self.wings)
        for w in self.wires if structural else []:
            if w["kind"] != "route" or isinstance(w["a"], str) or isinstance(w["b"], str):
                continue
            # a route walks over the wiring: each step needs a line on the framework diagrams, drawn from
            # either of the two boxes (on the diagram that holds it, or on its own)
            if not any(x["kind"] != "route" and ((within(w["a"], x["a"]) and related(x["b"], w["b"])) or
                                                 (within(w["a"], x["b"]) and related(x["a"], w["b"])) or
                                                 (within(w["b"], x["a"]) and related(x["b"], w["a"])) or
                                                 (within(w["b"], x["b"]) and related(x["a"], w["a"])))
                       for x in self.wires):
                out["routes_off"].append({"route": w["where"], "a": unit_label(w["a"]), "b": unit_label(w["b"])})
        for owner, where, flow, kind in self.diagrams:
            wired = collections.defaultdict(set)
            for e in flow["edges"]:
                wired[e["a"]].add(e["b"])
                wired[e["b"]].add(e["a"])
                if not e["label"]:
                    out["unlabeled"].append({"on": where, "a": e["a"], "b": e["b"]})
            for n in flow["nodes"]:  # a box on the shelf: no arrow, so its note has to say whom it serves
                if n["name"] not in wired and not n["note"]:
                    out["shelf"].append({"on": where, "box": n["name"]})
            left, groups = set(wired), 0
            while left:
                groups += 1
                stack = [left.pop()]
                while stack:
                    for nxt in wired[stack.pop()]:
                        if nxt in left:
                            left.discard(nxt)
                            stack.append(nxt)
            if groups > 1:
                out["pieces"].append({"on": where, "n": groups})
        return out

    def code_gone(self, root, files, listed=""):
        """Names written on arrows (`Name`) that the code at either end no longer holds. An arrow says in
        plain words what travels along it; the name is what the code calls that, so a rename shows up here.
        The list itself (`listed`) is not searched: every name is written there."""
        asked = []  # (where, edge, name, unit)
        for owner, where, flow, kind in self.diagrams:
            ends = {n["name"]: self.end(n, owner, kind) for n in flow["nodes"]}
            for e in flow["edges"]:
                for unit in {id(x): x for x in (ends[e["a"]], ends[e["b"]]) if not isinstance(x, str)}.values():
                    asked += [(where, e, name, unit) for name in e["code"]]
        want = collections.defaultdict(set)
        for _, _, name, unit in asked:
            want[unit].add(name)
        if not want:
            return []
        for f in files:
            if f == listed:
                continue
            unit, text = leaf(f, self.parts), None
            while unit is not None:
                if want.get(unit):
                    text = read(root, f) if text is None else text
                    want[unit] -= {name for name in want[unit] if name in text}
                unit = unit_up(unit)
        return [{"on": where, "a": e["a"], "b": e["b"], "name": name, "unit": unit_label(unit)}
                for where, e, name, unit in asked if name in want[unit]]

    def loose(self, links):
        """Marks the arrows between two parts (or wings) of the project that the measured links do not back."""
        joined = {(x["a"], x["b"]) for x in links} | {(x["b"], x["a"]) for x in links}

        def tops(u):
            if isinstance(u, Wing):
                return {p.name for p in u.parts}
            return {u.top.name}
        for w in self.wires:
            if w["kind"] == "unit" and not isinstance(w["owner"], Wing):
                continue
            if isinstance(w["a"], str) or isinstance(w["b"], str):
                continue
            a, b = tops(w["a"]), tops(w["b"])
            if not (a & b) and not any((x, y) in joined for x in a for y in b):
                w["edge"]["loose"] = True


def leaf(path, parts, seen={}):
    """The part or sub-part that owns a path: the most specific pattern wins."""
    key = (id(parts), path)
    if key not in seen:
        best, best_rank = None, (-1, 0)
        for part in parts:
            for unit in [part] + part.children:
                for _, match, length in unit.patterns:
                    rank = (length, 1 if unit.parent else 0)  # on a tie the room inside wins
                    if rank > best_rank and match(path):
                        best, best_rank = unit, rank
        seen[key] = best
    return seen[key]


def owner(path, parts):
    """The top-level part that owns a path."""
    unit = leaf(path, parts)
    return unit.top if unit else None


def language(parts):
    return "zh" if any(ord(ch) > 0x2E7F for p in parts for ch in p.name) else "en"


def width(text):
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in text)


def pad(text, to):
    return text + " " * max(0, to - width(text))


# Tree state ---------------------------------------------------------------

def dirty_files(root, base):
    tracked = zlist(git(root, "diff", "--name-only", "-z", base, "--"))
    untracked = zlist(git(root, "ls-files", "--others", "--exclude-standard", "-z"))
    return sorted(set(tracked) | set(untracked))


def worktrees(root):
    """Every checkout of this repository, the current one first."""
    out = subprocess.run(["git", "-C", root, "worktree", "list", "--porcelain"], capture_output=True)
    trees, cur = [], None
    for line in out.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("worktree "):
            cur = {"path": os.path.realpath(line[9:]), "branch": ""}
            trees.append(cur)
        elif cur and line.startswith("branch "):
            cur["branch"] = line[7:].replace("refs/heads/", "", 1)
    here = os.path.realpath(root)
    trees = [w for w in trees if w["path"] != here and os.path.isdir(w["path"])]
    return [{"path": here, "branch": ""}] + trees


# Windows ------------------------------------------------------------------
# A window is one Claude Code or Codex session. Both tools keep a record of each session on
# this machine, and two things in it say which window changed a file:
#   edits  the file was named in one of the tool's own edit commands (certain);
#   runs   the file's modification time falls inside a shell command the session ran (a guess,
#          used only when no edit names the file and exactly one session fits).
# Nothing here is required: if the records are missing or their format has changed, every
# change simply has no window.

def stamp(text):
    try:
        return datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def inside(path, roots):
    return any(path == r or path.startswith(r + os.sep) for r in roots)


def first_ask(text, limit=60):
    """The opening line of what a person typed; "" for the context blocks the tool adds itself."""
    text = str(text).strip()
    if not text or text.startswith(("<", "#", "This session is being continued")):
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    line = next((x for x in lines if not x.startswith("[")), lines[0])
    return line if len(line) <= limit else line[: limit - 1] + "…"


def recent(paths, since):
    """Paths changed after `since`, newest first."""
    dated = []
    for path in paths:
        try:
            when = os.path.getmtime(path)
        except OSError:
            continue
        if when >= since:
            dated.append((when, path))
    return [path for _, path in sorted(dated, reverse=True)]


def mentions(path, roots):
    """Whether a session record names any of these checkouts at all; most records on a machine do not."""
    try:
        with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as data:
            return any(data.find(r.encode("utf-8")) >= 0 for r in roots)
    except (OSError, ValueError):
        return False


def new_session(tool, sid):
    # `turn`: "busy" while the agent is in the middle of a turn, "done" once it has handed back to the person.
    # `seen`: when the record last moved. `said`: the latest thing the person asked. `here`: started in a checkout.
    return {"tool": tool, "id": sid, "title": "", "edits": {}, "runs": [], "open": {},
            "turn": "", "seen": 0.0, "said": "", "here": False, "born": 0.0}


def born(path):
    """When a session record was started. Windows are lettered in this order, so a window keeps its letter
    from one look to the next while the same windows are open."""
    try:
        info = os.stat(path)
    except OSError:
        return 0.0
    return getattr(info, "st_birthtime", 0) or info.st_ctime


def claude_sessions(roots, since):
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    # Every project folder, not only this repo's: a session started elsewhere can edit files here.
    files = glob.glob(os.path.join(home, "projects", "*", "*.jsonl"))
    files += glob.glob(os.path.join(home, "projects", "*", "*", "subagents", "*.jsonl"))
    found, seen = {}, set()
    for path in recent(files, since):  # newest first, so a resumed session keeps the edits it copied
        if not mentions(path, roots):
            continue
        sub = os.path.basename(os.path.dirname(path)) == "subagents"
        sid = os.path.basename(os.path.dirname(os.path.dirname(path))) if sub else os.path.basename(path)[:-6]
        s = found.get(sid) or found.setdefault(sid, new_session("Claude Code", sid))
        newest = not sub and not s["seen"]  # a resumed session has several records; the newest says how it stands
        if newest:
            s["seen"] = os.path.getmtime(path)
        if not sub:
            s["born"] = min(s["born"] or born(path), born(path))
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not s["here"] and '"cwd":"' in line and any('"cwd":"%s' % json.dumps(r)[1:-1] in line for r in roots):
                    s["here"] = True
                if newest and '"stop_reason"' in line and '"type":"assistant"' in line:
                    # the agent's last word in a turn ends it; anything else means the turn is still running
                    s["turn"] = "done" if '"stop_reason":"end_turn"' in line else "busy"
                if '"tool_use"' in line and any(r in line for r in roots):
                    try:
                        d = json.loads(line)
                        blocks = d["message"]["content"] if d.get("type") == "assistant" else []
                    except (ValueError, KeyError, TypeError):
                        continue
                    when = stamp(d.get("timestamp"))
                    for b in blocks if isinstance(blocks, list) else []:
                        if not isinstance(b, dict) or b.get("type") != "tool_use" or b.get("id") in seen:
                            continue
                        seen.add(b.get("id"))
                        given = b.get("input") if isinstance(b.get("input"), dict) else {}
                        if b.get("name") in EDIT_TOOLS:
                            target = given.get("file_path") or given.get("notebook_path")
                            if target:
                                target = os.path.join(d.get("cwd") or "", target)
                                s["edits"][target] = max(when, s["edits"].get(target, 0))
                        elif b.get("name") in SHELL_TOOLS and not given.get("run_in_background"):
                            s["open"][b.get("id")] = when
                elif s["open"] and '"tool_result"' in line and any(k in line for k in s["open"]):
                    try:
                        d = json.loads(line)
                        blocks = d["message"]["content"] if d.get("type") == "user" else []
                    except (ValueError, KeyError, TypeError):
                        continue
                    for b in blocks if isinstance(blocks, list) else []:
                        if isinstance(b, dict) and b.get("tool_use_id") in s["open"]:
                            s["runs"].append((s["open"].pop(b["tool_use_id"]), stamp(d.get("timestamp"))))
                elif not sub and '"type":"user"' in line and '"tool_result"' not in line:
                    try:  # the opening request names a session that was never given a title
                        d = json.loads(line)
                        said = d["message"]["content"] if d.get("type") == "user" and not d.get("isMeta") else ""
                    except (ValueError, KeyError, TypeError):
                        continue
                    for b in said if isinstance(said, list) else [{"text": said}]:
                        ask = first_ask(b.get("text") or "" if isinstance(b, dict) else "")
                        if ask:
                            s["ask"] = s.get("ask") or ask
                            if newest:  # a new request opens a turn
                                s["said"], s["turn"] = ask, "busy"
                elif not sub and ('"ai-title"' in line or '"custom-title"' in line):
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("type") == "custom-title" and d.get("customTitle"):
                        s["named"] = s["title"] = str(d["customTitle"])
                    elif d.get("type") == "ai-title" and d.get("aiTitle") and not s.get("named"):
                        s["title"] = str(d["aiTitle"])
        s["runs"] += [(start, start + RUN_OPEN) for start in s["open"].values()]
        s["open"] = {}
    for s in found.values():
        s["title"] = s["title"] or s.get("ask", "")
    return list(found.values())


def codex_sessions(roots, since):
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    found = []
    for path in recent(glob.glob(os.path.join(home, "sessions", "**", "*.jsonl"), recursive=True), since):
        if not mentions(path, roots):
            continue
        s = new_session("Codex", os.path.basename(path)[:-6])
        cwd, local = "", False
        with open(path, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh):
                if n == 0:
                    try:
                        cwd = os.path.realpath(json.loads(line)["payload"]["cwd"])
                    except (ValueError, KeyError, TypeError):
                        break
                    local = inside(cwd, roots)  # only then can a command name its files relative to cwd
                    continue
                call = '_call"' in line and (local or any(r in line for r in roots))
                done = s["open"] and "_call_output" in line
                ask = '"user"' in line
                if '"task_started"' in line:
                    s["turn"] = "busy"
                elif '"task_complete"' in line or '"turn_aborted"' in line:
                    s["turn"] = "done"
                if not (call or done or ask):
                    continue
                try:
                    d = json.loads(line)
                    p = d.get("payload") or {}
                except ValueError:
                    continue
                kind, when = str(p.get("type")), stamp(d.get("timestamp"))
                if kind.endswith("_call"):
                    text = str(p.get("input") or p.get("arguments") or p.get("action") or "")
                    for target in PATCH_RE.findall(text):
                        target = os.path.join(cwd, target.strip())
                        s["edits"][target] = max(when, s["edits"].get(target, 0))
                    if call and p.get("call_id"):
                        s["open"][p["call_id"]] = when
                elif kind.endswith("_call_output") and p.get("call_id") in s["open"]:
                    s["runs"].append((s["open"].pop(p["call_id"]), when))
                elif ask and kind == "message" and p.get("role") == "user":
                    for c in p.get("content") or []:
                        said = first_ask(c.get("text") or "" if isinstance(c, dict) else "")
                        if said:
                            s["title"], s["said"] = s["title"] or said, said
        s["runs"] += [(start, start + RUN_OPEN) for start in s["open"].values()]
        s["open"] = {}
        s["here"], s["seen"], s["born"] = local, os.path.getmtime(path), born(path)
        if s["edits"] or s["runs"] or s["here"]:
            found.append(s)
    return found


def brief_name(folder):
    """What a task dossier calls its task: the heading of its brief, or the folder's name without the date."""
    try:
        with open(os.path.join(folder, "task-brief.md"), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("# "):
                    return re.sub(r"^(?:Task Brief|任务书)\s*[:：]\s*", "", line[2:].strip())
    except OSError:
        pass
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", os.path.basename(folder))


NOT_TASKS = ("next-session.md", "index.md", "readme.md")  # Markdown beside the task records that is not one


def file_title(path):
    """What a one-file task record calls its task: its `#` heading, or the file's name without the date."""
    for line in slurp(path).split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", os.path.basename(path)[:-3])


def task_of(path):
    """The journal task a file belongs to: (task id, task name). A task's record is one file,
    docs/tasks/<id>.md, or in older projects a folder of several, docs/tasks/<id>/."""
    m = re.match(r"(.*?/docs/tasks/([^/]+))/[^/]+$", path)
    if m:
        return m.group(2), brief_name(m.group(1))
    m = re.match(r".*?/docs/tasks/([^/]+)\.md$", path)
    if m and os.path.basename(path).lower() not in NOT_TASKS:
        return m.group(1), file_title(path)
    return None


def task_at(rest):
    """The task id a path inside the tasks folder belongs to, or None: `<id>/anything` or `<id>.md`."""
    first, slash, _ = rest.partition("/")
    if slash:
        return first
    return first[:-3] if first.lower().endswith(".md") and first.lower() not in NOT_TASKS else None


def slurp(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def read_handoff(handoff):
    """A handoff's header and its `## For People` section: (meta, said, marks)."""
    lines = handoff.split("\n")
    meta, body = {}, 0
    if lines[0].strip() == "---":
        for at, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                body = at + 1
                break
            key, sep, value = line.partition(":")
            if sep:
                meta[key.strip().lower()] = value.strip()
    said, inside = {"name": "", "now": "", "needs": [], "next": "", "made": [], "try": "", "left": []}, False
    marks = []
    for line in lines[body:]:
        if line.startswith("## "):
            inside = bool(PEOPLE_HEAD_RE.match(line))
        elif inside:
            m = PEOPLE_RE.match(line)
            if m and not NOTHING_RE.match(m.group(2)):
                key = PEOPLE_KEYS[m.group(1).lower()]
                if key in ("new", "chg", "gone"):
                    where = MARK_RE.match(m.group(2))
                    path = [x for x in re.split(r"\s+/\s+", where.group(1) if where else m.group(2)) if x]
                    marks.append({"kind": key, "path": path, "text": where.group(2) if where else ""})
                elif key in ("needs", "made", "left"):
                    said[key].append(m.group(2))
                else:
                    said[key] = said[key] or m.group(2)
    return meta, said, marks


def load_tasks(root, where):
    """The tasks the implementation-journal skill keeps, one dossier folder each: [{id, name, plain, now,
    needs, next, made, try, left, marks, done, updated, cited}]. Those records are written for the next AI
    session, so only two things are read from them: the handoff's status and date, and its `## For People`
    section, the few lines the agent writes there in the reader's own language: where the task stands
    (名字/Name, 现在/Now, 等你/Needs you, 下一步/Next) and what its last finished step came to (做成了/Done,
    怎么试/Try, 还没做/Not yet, 新增/Added, 改了/Changed, 去掉/Removed). A record without that section is
    still a task; it has a name from its heading and no more.

    A task's record is one file, `<id>.md` with a `status:` in its header, or, in projects that started
    with the older form, a folder `<id>/` whose `handoff.md` is read the same way. `home` is that file or
    folder, `file` the file the lines for people are in, both relative to the tasks folder."""
    base = where if os.path.isabs(where) else os.path.join(root, where)
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return []
    tasks = []
    for name in names:
        folder = os.path.join(base, name)
        single = not os.path.isdir(folder)
        if single and (not name.lower().endswith(".md") or name.lower() in NOT_TASKS):
            continue
        handoff = slurp(folder if single else os.path.join(folder, "handoff.md"))
        if not handoff:
            continue
        meta, said, marks = read_handoff(handoff)
        if single and "status" not in meta:
            continue  # some other Markdown file kept beside the task records
        when = re.search(r"\d{4}-\d{2}-\d{2}", meta.get("updated", "") or name)
        tasks.append({"id": name[:-3] if single else name, "home": name,
                      "file": name if single else name + "/handoff.md",
                      "name": said["name"] or (file_title(folder) if single else brief_name(folder)),
                      "plain": bool(said["name"] and said["now"]),
                      "now": said["now"], "needs": said["needs"][:5], "next": said["next"],
                      "made": said["made"][:4], "try": said["try"], "left": said["left"][:6], "marks": marks[:16],
                      "done": meta.get("status", "").lower().startswith("complete"),
                      "updated": when.group(0) if when else "",
                      "cited": set(re.findall(r"\b[0-9a-f]{7,40}\b", handoff + (
                          "" if single else slurp(os.path.join(folder, "implementation-log.md")))))})
    return tasks


STORY = 12   # past versions of a handoff read for a task's story


def task_stories(root, rel, tasks):
    """How each task got to where it is, read from the history of its handoff: {task id: [{date, done,
    made}]}, oldest first, one entry each time its status or what it had made changed. This is what shows
    that a finished task was opened again and finished a second time: the handoff itself only ever says
    how things stand now. A handoff that was never committed has no story."""
    if not rel or not tasks:
        return {}
    paths = {posixpath.join(rel, t["file"]): t["id"] for t in tasks}
    out = subprocess.run(["git", "-C", root, "log", "--format=%x01%H%x02%ad", "--date=short", "--name-only",
                          "--", *paths], capture_output=True)
    if out.returncode:
        return {}
    revs = collections.defaultdict(list)  # task id -> [(rev, date)], newest first
    for block in out.stdout.decode("utf-8", "replace").split("\x01")[1:]:
        head, _, names = block.partition("\n")
        rev, _, date = head.partition("\x02")
        for name in names.split("\n"):
            if name.strip() in paths:
                revs[paths[name.strip()]].append((rev, date.strip(), name.strip()))
    asked = [(tid, rev, date, path) for tid, rows in revs.items() for rev, date, path in rows[:STORY]]
    if not asked:
        return {}
    blobs = subprocess.run(["git", "-C", root, "cat-file", "--batch"], capture_output=True,
                           input="".join("%s:%s\n" % (rev, path) for _, rev, _, path in asked).encode())
    raw, at, stories = blobs.stdout, 0, collections.defaultdict(list)
    for tid, rev, date, path in asked:
        end = raw.find(b"\n", at)
        if end < 0:
            break
        head = raw[at:end].split()
        at = end + 1
        if len(head) < 3 or head[1] != b"blob":
            continue
        size = int(head[2])
        meta, said, _ = read_handoff(raw[at:at + size].decode("utf-8", "replace"))
        at += size + 1
        stories[tid].append({"date": date, "done": meta.get("status", "").lower().startswith("complete"),
                             "made": said["made"][0] if said["made"] else ""})
    for tid, rows in stories.items():
        rows.reverse()
        kept = []
        for row in rows:
            if not kept or (kept[-1]["done"], kept[-1]["made"]) != (row["done"], row["made"]):
                kept.append(row)
        stories[tid] = kept
    return stories


def task_rooms(task, commits, rel):
    """Where a task's committed work landed, as {part name: files}. Measured, not written: the commits
    its records cite by hash, and the commits that changed its dossier and no other task's. The dossier's
    own files are bookkeeping and are left out, so the picture is of the work itself."""
    rooms, prefix = collections.Counter(), rel + "/" if rel else None
    files, last, own = set(), 0, set()
    for c in commits:
        mine = any(t.startswith(c["hash"]) or c["hash"].startswith(t) for t in task["cited"])
        if not mine and prefix:
            mine = {task_at(f[len(prefix):]) for fs in c["groups"].values() for f in fs
                    if f.startswith(prefix)} - {None} == {task["id"]}
        if mine:
            own.add(c["hash"])
            last = max(last, c["when"])
            for name, fs in c["groups"].items():
                work = [f for f in fs if not (prefix and f.startswith(prefix))]
                files.update(work)
                if work:
                    rooms[name] += len(work)
    # What happened to those files afterwards, in commits that are not this task's. A finished task's
    # write-up describes the code as it was then; this is how a reader learns it has moved on since.
    task["after"] = None if not files else sum(
        1 for c in commits if c["when"] > last and c["hash"] not in own
        and any(f in files for fs in c["groups"].values() for f in fs))
    task["files"], task["last"], task["own"] = files, last, own
    return rooms


def older_commits(root, parts, rel, tasks, commits):
    """The commits a task's records point at that lie further back than the map's window: the ones cited
    by hash, and the ones that changed its dossier. Without them a task finished long ago would show no
    parts at all. Returns them in the form `history` gives."""
    known = {c["hash"] for c in commits}
    words = {w for t in tasks for w in t["cited"] if not any(w.startswith(k) or k.startswith(w) for k in known)}
    revs = set()
    if words:  # a word of hex digits in a record is not always a commit
        out = subprocess.run(["git", "-C", root, "cat-file", "--batch-check"], capture_output=True,
                             input="\n".join(sorted(words)).encode())
        for line in out.stdout.decode("utf-8", "replace").splitlines():
            bits = line.split()
            if len(bits) >= 2 and bits[1] == "commit":
                revs.add(bits[0])
    if rel:
        for t in tasks:
            out = subprocess.run(["git", "-C", root, "log", "--no-merges", "--format=%H", "-n", "100", "--",
                                  posixpath.join(rel, t["home"])], capture_output=True)
            revs.update(out.stdout.decode().split())
    revs = [r for r in revs if not any(r.startswith(k) for k in known)]
    return history(root, parts, revs) if revs else []


def changed_after(root, task):
    """How many later commits, not the task's own, changed the files the task changed. Asked of git over
    the whole history, so it does not stop at the map's window."""
    files = sorted(task["files"])[:300]
    if not files or not task["last"]:
        return task["after"]
    out = subprocess.run(["git", "-C", root, "rev-list", "--no-merges", "--abbrev-commit",
                          "--max-age=%d" % (task["last"] + 1), "HEAD", "--", *files],
                         capture_output=True)
    if out.returncode:
        return task["after"]
    revs = out.stdout.decode().split()
    return sum(1 for r in revs if not any(r.startswith(o) or o.startswith(r) for o in task["own"]))


def place_marks(task, parts):
    """Find each mark's part, room and box on the list. A mark names boxes of a flow diagram someone drew
    for the list, so a name can miss: `unit` stays "" when no part or room carries the name, and `drawn`
    says whether the box is in that unit's diagram. A removed box is not expected to be there."""
    tops = {p.name: p for p in parts}
    for m in task["marks"]:
        path, unit = m.pop("path"), None
        top = tops.get(path[0]) if path else None
        if path and not top:  # a room named without its part
            room = next((c for p in parts for c in p.children if c.name == path[0]), None)
            if room:
                top, path = room.parent, [room.parent.name] + path
        if top:
            room = next((c for c in top.children if len(path) > 1 and c.name == path[1]), None)
            unit, rest = (room, path[2:]) if room else (top, path[1:])
        else:
            rest = path[1:]
        m["part"], m["room"] = top.name if top else (path[0] if path else ""), unit.name if unit and unit.parent else ""
        m["unit"], m["box"] = unit.name if unit else "", " / ".join(rest)
        m["drawn"] = bool(unit and unit.flow and any(n["name"] == m["box"] for n in unit.flow["nodes"]))


TRIED_FILE = "tried.md"   # beside the parts list: what the reader tried, and whether it worked
TRIED_RE = re.compile(r"^\s*[-*]\s+(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?\s+(不能用|能用|works|broken)"
                      r"(?:\s+@([0-9a-f]{7,40})(\+)?)?(?:\s*[:：]\s*(.*?))?\s*$")


def tried_path(list_path):
    return os.path.join(os.path.dirname(os.path.abspath(list_path)), TRIED_FILE)


def tried_snaps(root):
    return os.path.join(os.path.dirname(state_path(root)), "tried.json")


def read_tried(text):
    """What the reader tried: {task id: [{date, time, ok, rev, dirty, note}]}, oldest first. One heading
    per task (`## <task id>`, the name of its record, with what people call it in brackets after it), one
    line per try: the day and time, whether it worked, the commit the code stood at (`+` when the task's
    files had uncommitted work in them), and what the reader noted."""
    out, cur = {}, None
    for line in text.split("\n"):
        head = re.match(r"^##\s+(.+?)\s*$", line)
        if head:
            cur = out.setdefault(re.sub(r"\s*[（(].*[）)]\s*$", "", head.group(1)).strip().strip("`"), [])
            continue
        m = TRIED_RE.match(line) if cur is not None else None
        if m:
            cur.append({"date": m.group(1), "time": m.group(2) or "", "ok": m.group(3) in ("能用", "works"),
                        "rev": m.group(4) or "", "dirty": bool(m.group(5)), "note": m.group(6) or ""})
    return out


def blobs(root, files):
    """{file: what git would call its content as it stands in the working folder; "" when it is not there}."""
    out = dict.fromkeys(files, "")
    here = [f for f in files if os.path.isfile(os.path.join(root, f))]
    if here:
        got = subprocess.run(["git", "-C", root, "hash-object", "--stdin-paths"], capture_output=True,
                             input="\n".join(here).encode("utf-8")).stdout.decode().split()
        if len(got) == len(here):
            out.update(zip(here, got))
    return out


def tried_states(root, tasks, list_path):
    """Gives each task `tried`: None, or how its latest try stands: {ok, date, note, changed, files, times}.
    `changed` is how many of the task's files are no longer as they were when it was tried, so the reader
    knows a thing that worked may be worth trying again. Measured two ways. On the machine where the try
    was noted, against the contents kept then (under the git directory). Elsewhere, against the commit the
    line names, when the task's files were all committed at the time. Otherwise it is not known (None), and
    nothing is claimed."""
    marks = read_tried(slurp(tried_path(list_path)))
    for t in tasks:
        t["tried"] = None
    if not marks:
        return
    try:
        snaps = json.loads(slurp(tried_snaps(root)) or "{}")
    except ValueError:
        snaps = {}
    mine = [t for t in tasks if marks.get(t["id"])]
    now = blobs(root, sorted({f for t in mine for f in snaps.get(t["id"], {}).get("files", {})}))
    for t in mine:
        last = marks[t["id"]][-1]
        when, snap, changed = (last["date"] + " " + last["time"]).strip(), snaps.get(t["id"]), None
        if snap and snap.get("when") == when:
            changed = sorted(f for f, was in snap.get("files", {}).items() if now.get(f, "") != was)
        elif last["rev"] and not last["dirty"] and t.get("files"):
            out = subprocess.run(["git", "-C", root, "diff", "--name-only", last["rev"], "--",
                                  *sorted(t["files"])[:300]], capture_output=True)
            if out.returncode == 0:
                changed = [x for x in out.stdout.decode("utf-8", "replace").split("\n") if x]
        t["tried"] = {"ok": last["ok"], "date": last["date"], "note": last["note"], "times": len(marks[t["id"]]),
                      "changed": None if changed is None else len(changed), "files": (changed or [])[:6]}


def write_tried(root, list_path, task, files, ok, note, zh=True):
    """Notes one try of a task in the tried file, as a new line under the task's heading: nothing that is
    there is changed. `files` are the task's files as they stand; their contents are kept under the git
    directory so that a later change to any of them can be told. Returns the task's `tried` as it now is."""
    when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    files = sorted(files)[:2000]
    out = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True)
    rev = out.stdout.decode().strip() if out.returncode == 0 else ""
    dirty = bool(files) and bool(subprocess.run(["git", "-C", root, "status", "--porcelain", "--", *files[:300]],
                                                capture_output=True).stdout.strip())
    note = " ".join((note or "").split())[:300]
    word = ("能用" if ok else "不能用") if zh else ("works" if ok else "broken")
    line = "- %s %s%s%s" % (when, word, " @%s%s" % (rev, "+" if dirty else "") if rev else "",
                            ("：" if zh else ": ") + note if note else "")
    path = tried_path(list_path)
    old = slurp(path) if os.path.isfile(path) else ""
    lines = old.rstrip("\n").split("\n") if old.strip() else (
        ["# 试用记录", "", "每件事下面，一行是一次试用：哪天、能用还是不能用、当时代码停在哪次提交（带 + 是还有没提交的改动）、当时记的话。"
         "在导览图上点的和对 AI 说的都记在这里。"] if zh else
        ["# Tried", "", "Under each task, a line is one try: the day, whether it worked, the commit the code stood at "
         "(a + means uncommitted work was in it), and what was noted. What is clicked on the map and what is "
         "told to the AI both end up here."])
    at = None
    for i, row in enumerate(lines):
        head = re.match(r"^##\s+(.+?)\s*$", row)
        if head:
            if at is not None:
                break
            if re.sub(r"\s*[（(].*[）)]\s*$", "", head.group(1)).strip().strip("`") == task["id"]:
                at = i
        elif at is not None and row.strip():
            at = i
    if at is None:
        named = task["name"] if task["name"] != task["id"] else ""
        lines += ["", "## %s%s" % (task["id"], ("（%s）" if zh else " (%s)") % named if named else ""), "", line]
    else:
        lines.insert(at + 1, line)
        if lines[at].startswith("## "):
            lines.insert(at + 1, "")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip("\n") + "\n")
    os.replace(path + ".tmp", path)
    try:
        snaps = json.loads(slurp(tried_snaps(root)) or "{}")
    except ValueError:
        snaps = {}
    snaps[task["id"]] = {"when": when, "files": blobs(root, files)}
    os.makedirs(os.path.dirname(tried_snaps(root)), exist_ok=True)
    with open(tried_snaps(root) + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(snaps, fh)
    os.replace(tried_snaps(root) + ".tmp", tried_snaps(root))
    return {"ok": ok, "date": when[:10], "note": note, "times": len(read_tried(slurp(path)).get(task["id"], [])),
            "changed": 0, "files": []}


def task_scope(root, task, windows):
    """The files a task's work is in as things stand: the ones its commits changed, and the uncommitted
    ones of a window that is writing in its record (in this checkout). It is what a try is a try of."""
    here = os.path.realpath(root)
    prefix = task["rel"] + "/" if task.get("rel") else None
    live = {r["file"] for w in windows if w.get("dossier") == task["id"] for r in w["rows"]
            if os.path.realpath(r["tree"]["path"]) == here and not (prefix and r["file"].startswith(prefix))}
    return set(task.get("files") or ()) | live


def tasks_shown(root, where, parts, commits, listed=None):
    """(tasks to show, how many were left out). A task is in progress until its handoff says Complete. A
    finished one is kept for as long as its record is, provided the agent wrote lines for people: for
    RECENT_DAYS as "finished lately", after that as `old`, which the page folds away. An unfinished one
    with no lines for people that has not moved in RECENT_DAYS is left out: it would be a stale name the
    reader can do nothing with. Each task gets `rooms`, [{name, n}] in the order of the list; `after`, how
    often the files it changed were changed again by later work (None when its commits are not known);
    `story`, how its status and result changed over time; `times`, how often it was finished; `again`,
    whether it was finished once and is open again."""
    base = where if os.path.isabs(where) else os.path.join(root, where)
    rel = os.path.relpath(base, root).replace(os.sep, "/")
    rel = None if rel.startswith("..") else rel
    today, shown, left_out = datetime.date.today(), [], 0
    loaded = load_tasks(root, where)
    commits = commits + older_commits(root, parts, rel, loaded, commits) if commits else commits
    for t in loaded:
        try:
            t["days"] = (today - datetime.date.fromisoformat(t["updated"])).days
        except ValueError:
            t["days"] = -1
        recent = 0 <= t["days"] <= RECENT_DAYS
        if t["done"] and not (t["plain"] or t["made"]):
            continue
        t["old"] = t["done"] and not recent  # finished a while ago: kept, but out of the way
        if not t["done"] and not t["plain"] and not recent:
            left_out += 1
            continue
        landed = task_rooms(t, commits, rel)
        t["rooms"] = [{"name": p.name, "n": landed[p.name]} for p in parts if landed[p.name]]
        if landed[""]:
            t["rooms"].append({"name": "", "n": landed[""]})
        t["rel"] = rel
        if t["done"] and commits:
            t["after"] = changed_after(root, t)
        place_marks(t, parts)
        shown.append(t)
    stories = task_stories(root, rel, shown)
    for t in shown:
        story = stories.get(t["id"], [])
        # the file as it stands may be ahead of its last commit
        if story and (story[-1]["done"], story[-1]["made"]) != (t["done"], t["made"][0] if t["made"] else ""):
            story.append({"date": t["updated"], "done": t["done"], "made": t["made"][0] if t["made"] else ""})
        t["story"] = story[-8:]
        t["times"] = sum(1 for i, row in enumerate(story) if row["done"] and (i == 0 or not story[i - 1]["done"]))
        t["again"] = not t["done"] and any(row["done"] for row in story)  # finished once, open again
    if listed:
        tried_states(root, shown, listed)
    else:
        for t in shown:
            t["tried"] = None
    shown.sort(key=lambda t: t["updated"], reverse=True)
    # what waits on the reader comes first, what is finished comes last, what was finished long ago after that
    shown.sort(key=lambda t: (t["old"], t["done"], not t["needs"]))
    return shown, left_out


def sessions(roots):
    """Recent sessions that worked in these checkouts: {tool, id, title, task, edits: {path: time}, runs,
    turn, seen, said, here}."""
    since = datetime.datetime.now().timestamp() - SESSION_DAYS * 86400
    found = []
    for reader in (claude_sessions, codex_sessions):
        try:
            found += reader(roots, since)
        except Exception:  # an unreadable or reshaped record must never break the map
            continue
    real, kept = {}, []
    for s in found:
        edits = {}
        for path, when in s["edits"].items():
            full = real.get(path) or real.setdefault(path, os.path.realpath(path))
            if inside(full, roots):
                edits[full] = max(when, edits.get(full, 0))
        if edits or s["runs"] or s["here"]:
            s["edits"], s["task"], s["dossier"] = edits, "", ""
            for path, _ in sorted(edits.items(), key=lambda kv: -kv[1]):
                hit = task_of(path)
                if hit:
                    s["dossier"], s["task"] = hit
                    break
            kept.append(s)
    return kept


def clock(when):
    then = datetime.datetime.fromtimestamp(when)
    if then.date() == datetime.date.today():
        return then.strftime("%H:%M")
    return then.strftime("%m-%d %H:%M")


def in_flight(root, parts, look=True, everywhere=False):
    """The uncommitted files, split by the window that edited them.

    Returns (rows, windows). A row is one changed file in one checkout. A window carries the
    rows it edited after the file's last commit; rows nobody is on record for go to a window
    marked unknown, one per checkout.
    """
    here = {"path": os.path.realpath(root), "branch": ""}
    trees = worktrees(root) if everywhere else [here]
    found = sessions([w["path"] for w in trees]) if look else []
    rows = []
    for w in trees:
        try:
            changed = dirty_files(w["path"], "HEAD")
        except SystemExit:
            if w is trees[0]:
                raise
            continue
        for f in changed:
            full = os.path.realpath(os.path.join(w["path"], f))
            who, guess = [(s, s["edits"][full]) for s in found if full in s["edits"]], False
            if who:
                done = git(w["path"], "log", "-1", "--format=%ct", "--", f).decode().strip()
                who = [(s, when) for s, when in who if when > float(done or 0)]
            if not who and os.path.isfile(full):  # no edit names it: whose shell command was running?
                made = os.path.getmtime(full)
                near = [s for s in found if any(a - 1 <= made <= b + 2 for a, b in s["runs"])]
                if len(near) == 1:
                    who, guess = [(near[0], made)], True
            unit = leaf(f, parts)
            rows.append({"file": f, "tree": w, "part": unit.top.name if unit else "",
                         "sub": unit.name if unit and unit.parent else "", "who": who, "guess": guess})

    windows, by_id = [], {}
    for row in rows:
        for s, when in row["who"]:
            if s["id"] not in by_id:
                by_id[s["id"]] = {"tool": s["tool"], "title": s["title"], "task": s["task"], "dossier": s["dossier"],
                                  "unknown": False, "when": 0, "rows": []}
                windows.append(by_id[s["id"]])
            win = by_id[s["id"]]
            win["rows"].append(row)
            win["when"] = max(win["when"], when)
    # A window with nothing uncommitted is still at work here if its session sat in a checkout lately:
    # reading, planning, or already committed.
    now = datetime.datetime.now().timestamp()
    by_session = {s["id"]: s for s in found}
    for s in found:
        if s["id"] not in by_id and s["here"] and now - s["seen"] <= WINDOW_HOURS * 3600:
            by_id[s["id"]] = {"tool": s["tool"], "title": s["title"], "task": s["task"], "dossier": s["dossier"],
                              "unknown": False, "when": 0, "rows": []}
            windows.append(by_id[s["id"]])
    for sid, win in by_id.items():
        s = by_session[sid]
        win["session"], win["seen"], win["said"] = s, max(s["seen"], win["when"]), s["said"]
        still = now - win["seen"]
        # working: in a turn and the record moved a moment ago. held: in a turn but still for a while, which is
        # what a window waiting for a permission looks like, or one running a long command. waiting: the agent
        # has handed back and the person has not answered. idle: nothing for a long time.
        win["state"] = ("working" if still <= BUSY_SECONDS else "held" if still <= HELD_SECONDS else "idle") \
            if s["turn"] == "busy" else ("waiting" if still <= WINDOW_HOURS * 3600 else "idle") \
            if s["turn"] == "done" else ("working" if still <= BUSY_SECONDS else "idle")
    windows.sort(key=lambda win: win["session"]["born"])  # oldest first: a window keeps its letter and its place
    for w in trees:
        loose = [row for row in rows if row["tree"] is w and not row["who"]]
        if loose:
            windows.append({"tool": "", "title": "", "task": "", "dossier": "", "unknown": True, "when": 0,
                            "rows": loose, "session": None, "seen": 0, "said": "", "state": ""})
    letters, unknown = 0, 0
    for win in windows:
        if not win["unknown"] and not win["dossier"]:
            # No edit command names a dossier, but a file this window changed by a shell command may lie in
            # one. That is enough to say which task the window is on; its name stays the session's own.
            for row in win["rows"]:
                hit = task_of(os.path.join(row["tree"]["path"], row["file"]))
                if hit:
                    win["dossier"] = hit[0]
                    break
        if win["unknown"]:
            unknown += 1
            win["key"] = "?" if unknown == 1 else "?%d" % unknown
        else:
            win["key"] = chr(65 + letters) if letters < 26 else str(letters + 1)
            letters += 1
        win["last"] = clock(win["seen"]) if win["seen"] else ""
        win["guessed"] = sum(1 for row in win["rows"] if row["guess"])
        win["where"] = sorted({row["tree"]["branch"] or os.path.basename(row["tree"]["path"])
                               for row in win["rows"] if row["tree"]["path"] != here["path"]})
        for row in win["rows"]:
            row.setdefault("keys", []).append(win["key"])
    return rows, windows


def clashes(rows, windows, records=()):
    """Where windows get in each other's way, worst first: the same file changed by two windows in one
    checkout (one will overwrite the other), the same file changed in two checkouts (a conflict when they
    are merged), and the same part being changed by two windows (worth a look). `records` is the parts
    list followed by the tasks folder. The list is left out altogether: every window keeps its own lines
    of it up to date, which is what it is for. Both are left out of the last kind."""
    out, seen = [], set()
    listed = records[0] if records else ""
    rows = [r for r in rows if r["file"] != listed]
    for r in rows:
        keys = [k for k in r.get("keys", []) if not k.startswith("?")]
        if len(keys) > 1:
            seen.add(r["file"])
            out.append({"kind": "file", "file": r["file"], "part": r["part"], "who": keys, "where": []})
    trees = collections.defaultdict(list)
    for r in rows:
        trees[r["file"]].append(r)
    for f, same in trees.items():
        if len({id(r["tree"]) for r in same}) > 1 and f not in seen:
            seen.add(f)
            out.append({"kind": "merge", "file": f, "part": same[0]["part"],
                        "who": sorted({k for r in same for k in r.get("keys", []) if not k.startswith("?")}),
                        "where": sorted({r["tree"]["branch"] or os.path.basename(r["tree"]["path"]) for r in same})})
    by_part = collections.defaultdict(lambda: collections.defaultdict(int))
    for r in rows:
        if r["part"] and not r["file"].startswith(tuple(records) or ("\0",)):
            for k in r.get("keys", []):
                if not k.startswith("?"):
                    by_part[r["part"]][k] += 1
    hard = {c["part"] for c in out}
    for part, who in by_part.items():
        if len(who) > 1 and part not in hard:
            out.append({"kind": "part", "file": "", "part": part, "who": sorted(who), "where": [],
                        "n": dict(who)})
    return out


def window_commits(windows, commits):
    """Gives each window the commits made while one of its shell commands was running, when exactly one
    window fits: the same reasoning that matches a file changed by a shell command. Each window gets
    `commits`, [{hash, subject, parts}], newest first."""
    for win in windows:
        win["commits"] = []
    for c in commits:
        near = [win for win in windows if win.get("session") and
                any(a - 1 <= c["when"] <= b + 2 for a, b in win["session"]["runs"])]
        if len(near) == 1:
            near[0]["commits"].append({"hash": c["hash"], "subject": c["subject"],
                                       "parts": sorted(name for name in c["groups"] if name)})


def grouped(rows, parts):
    """Rows as [{name, n, files}] in the order of the parts list, unmapped files last under ""."""
    groups = {}
    for row in rows:
        groups.setdefault(row["part"], []).append(row["file"])
    order = [p.name for p in parts if p.name in groups] + ([""] if "" in groups else [])
    return [{"name": name, "n": len(groups[name]), "files": groups[name]} for name in order]


# Commands -----------------------------------------------------------------

def tally(files, parts):
    """Files per part and sub-part as {unit: [own, outside]}, plus the unmapped files.
    A part's numbers include its sub-parts'; outside code is counted apart."""
    n, unmapped = collections.defaultdict(lambda: [0, 0]), []
    for f in files:
        unit = leaf(f, parts)
        if unit is None:
            unmapped.append(f)
            continue
        which = 1 if unit.outside else 0
        n[unit][which] += 1
        if unit.parent:
            n[unit.parent][which] += 1
    return n, unmapped


def cmd_parts(root, parts, t, args):
    routes = args.routes
    files = zlist(git(root, "ls-files", "-z"))
    n, unmapped = tally(files, parts)
    if args.json:
        def row(p):
            out = {"name": p.name, "what": p.what, "sensitive": p.sensitive,
                   "files": n[p][0], "paths": [x[0] for x in p.patterns]}
            if p.children or p.parent or routes:  # lists in the newer form also say what is still undrawn
                out["flow"] = bool(p.flow and p.flow["nodes"])
                out["explained"] = bool(p.explain)
            if n[p][1]:
                out["outside"] = n[p][1]
            if p.external:
                out["external"] = p.external
            if p.children:
                out["subs"] = [row(c) for c in p.children]
            return out
        print(json.dumps({"parts": [row(p) for p in parts], "unmapped": unmapped}, ensure_ascii=False, indent=2))
        return
    col = max(width(u.name) + (4 if u.parent else 0) for p in parts for u in [p] + p.children) + 2
    print(t["parts_head"].format(n=len(parts), files=len(files)))
    for p in parts:
        for u in [p] + p.children:
            marks = [t["sensitive"].format(why=u.sensitive)] if u.sensitive else []
            marks += [t["outside"].format(why=u.external)] if u.external else []
            mark = "  [" + "] [".join(marks) + "]" if marks else ""
            count = t["files"].format(n=n[u][1] if u.outside else n[u][0])
            if n[u][1] and not u.outside:
                count += t["outside_more"].format(n=n[u][1])
            indent = "      " if u.parent else "  "
            print(indent + pad(u.name, col - len(indent) + 2) + pad(count, 12) + (" " if width(count) >= 12 else "") + u.what + mark)
    empty = [u.name for p in parts for u in [p] + p.children if not sum(n[u])]
    if empty:
        print(t["empty_part"].format(names="、".join(empty)))
    bare = [(u.parent.name + " / " if u.parent else "") + u.name for p in parts for u in [p] + p.children
            if not u.outside and not (u.flow and u.flow["nodes"])]
    if bare:
        print(t["no_flow"].format(n=len(bare), names="、".join(bare[:30]) + (" …" if len(bare) > 30 else "")))
    plain = [unit_label(u) for u in list(args.top["wings"]) + [u for p in parts for u in [p] + p.children]
             if not u.explain and not (isinstance(u, Part) and u.outside)]
    if plain:
        print(t["no_explain"].format(n=len(plain), names="、".join(plain[:30]) + (" …" if len(plain) > 30 else "")))
    if unmapped:
        print(t["unmapped"].format(n=len(unmapped)))
        for f in unmapped[: None if args.all else 40]:
            print("  " + f)
    else:
        print(t["unmapped_none"])


# Links measured from the code ---------------------------------------------
# Which part uses which, read from import statements. Unlike the flow diagrams, nobody writes
# these down: they are counted. Python, JavaScript/TypeScript, Go and C/C++ are read; other languages,
# and links that go over a network, are not seen.

LANGS = {".py": "Python", ".go": "Go", ".ts": "TypeScript", ".tsx": "TypeScript", ".mts": "TypeScript",
         ".cts": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
         ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++", ".hh": "C++"}
C_EXT = (".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh")
C_INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*["<]([^">\n]+)[">]', re.M)
JS_EXT = (".ts", ".tsx", ".mts", ".js", ".jsx", ".mjs", ".cjs", ".d.ts", ".json")
PY_FROM = re.compile(r"^[ \t]*from[ \t]+(\.*)([\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n#]+)", re.M)
PY_IMPORT = re.compile(r"^[ \t]*import[ \t]+([\w., \t]+)", re.M)
JS_SPEC = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\(\s*)['"]([^'"\n]+)['"]""")
GO_STR = re.compile(r'"([\w.\-/]+)"')
SOURCE_MAX = 1500000   # bytes; larger files are generated or data


def loose_json(text):
    """tsconfig files allow comments and trailing commas."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))


def read(root, f):
    try:
        with open(os.path.join(root, f), "rb") as fh:
            return fh.read(SOURCE_MAX + 1).decode("utf-8", "replace")
    except OSError:
        return ""


def code_links(root, files, parts):
    """Returns ({(unit_a, unit_b): [files, examples]}, languages): the files in a that import from b."""
    tracked = set(files)
    # Python: every dotted name a file can be imported by -> [(the folder that name starts from, file,
    # whether the package layout says so)]. `a/b/c.py` is `c`, `b.c` or `a.b.c` depending on which folder
    # is on the import path: folders holding an __init__.py settle it, the longer names are looser guesses.
    py = collections.defaultdict(list)
    for f in files:
        if not f.endswith(".py"):
            continue
        bits = f[:-3].split("/")
        i = len(bits) - 1
        while i > 0 and "/".join(bits[:i]) + "/__init__.py" in tracked:
            i -= 1
        if bits[-1] == "__init__":
            bits = bits[:-1]
        for k in range(len(bits)):
            if k == i or k < len(bits) - 1:
                py[".".join(bits[k:])].append(("/".join(bits[:k]), f, k == i))

    def py_file(name, folder, text):
        """The file a dotted name means to code in `folder` (whose source is `text`), or None. Several
        files can answer to one name (`utils`, `config`) and a file can carry a standard-library name
        (`logging.py`), so: a name that one of the importer's own folders provides wins, the nearest
        one first; failing that, a package elsewhere in the repo counts when exactly one place provides
        it; a lone script in some other folder counts only when the importer puts that folder on its
        path itself (it touches sys.path and names the folder), since otherwise it cannot reach it."""
        found = py.get(name)
        if not found:
            return None
        near = [c for c in found if not c[0] or (folder + "/").startswith(c[0] + "/")]
        if near:
            return max(near, key=lambda c: (len(c[0]), c[2]))[1]
        if "." not in name:
            found = [c for c in found if c[1].endswith("/__init__.py") or ("sys.path" in text and re.search(
                r"""['"/\\]%s['"/\\]""" % re.escape(posixpath.basename(c[0])), text))]
        found = [c for c in found if c[2]] or found
        return found[0][1] if len(found) == 1 else None

    # JavaScript: path aliases from tsconfig, and the packages of a workspace.
    # An alias is (the folder its tsconfig sits in, prefix, target folder): `@/` in one app of a
    # monorepo is not `@/` in the app next to it.
    aliases, packages = [], []
    for f in files:
        base = posixpath.basename(f)
        if re.fullmatch(r"[tj]sconfig(\.[\w-]+)?\.json", base):
            try:
                opts = loose_json(read(root, f)).get("compilerOptions") or {}
            except (ValueError, AttributeError):
                continue
            scope = posixpath.dirname(f)
            home = posixpath.join(scope, opts.get("baseUrl") or ".")
            for pattern, targets in (opts.get("paths") or {}).items():
                if pattern.endswith("*") and targets and str(targets[0]).endswith("*"):
                    to = posixpath.normpath(posixpath.join(home, targets[0][:-1]))
                    aliases.append((scope, pattern[:-1], "" if to == "." else to + "/"))
        elif base == "package.json" and "/" in f and "node_modules" not in f:
            try:
                name = json.loads(read(root, f)).get("name")
            except (ValueError, AttributeError):
                continue
            if name:
                packages.append((str(name), posixpath.dirname(f)))
    if not aliases and any(f.startswith("src/") for f in files):
        aliases = [("", "@/", "src/"), ("", "~/", "src/")]
    aliases.sort(key=lambda x: (-len(x[0]), -len(x[1])))  # the nearest tsconfig first, then the longest prefix
    packages.sort(key=lambda x: -len(x[0]))
    # Go: module path -> folder, and one file per folder to stand for the package
    gomods, godirs = [], {}
    for f in files:
        if posixpath.basename(f) == "go.mod":
            m = re.search(r"^module\s+(\S+)", read(root, f), re.M)
            if m:
                gomods.append((m.group(1), posixpath.dirname(f)))
        elif f.endswith(".go"):
            godirs.setdefault(posixpath.dirname(f), f)

    # C and C++: every tracked file by its base name, to resolve an `#include` the build finds on an include path
    cnames = collections.defaultdict(list)
    if any(f.endswith(C_EXT) for f in files):
        for f in files:
            cnames[posixpath.basename(f)].append(f)

    def c_file(spec, folder):
        """The file an `#include` means to code in `folder`: the one beside the including file, else the only
        file in the repo whose path ends that way. When several do (one `board.h` per board), the one that
        shares more of its folders with the including file than any other; a tie is left out, not guessed."""
        spec = posixpath.normpath(spec.replace("\\", "/"))
        near = posixpath.normpath(posixpath.join(folder, spec))
        if near in tracked:
            return near
        if spec.startswith(".."):
            return None
        found = [c for c in cnames.get(posixpath.basename(spec), ()) if c == spec or c.endswith("/" + spec)]
        if len(found) < 2:
            return found[0] if found else None
        here = folder.split("/") if folder else []

        def shared(c):
            n = 0
            for x, y in zip(here, c.split("/")):
                if x != y:
                    break
                n += 1
            return n
        ranked = sorted(found, key=shared, reverse=True)
        return ranked[0] if shared(ranked[0]) > shared(ranked[1]) else None

    def js_file(stem):
        stem = posixpath.normpath(stem)
        if stem in tracked:
            return stem
        bare = re.sub(r"\.(js|jsx|mjs|cjs)$", "", stem)  # `./x.js` written for a `./x.ts` source
        for cand in (bare, stem):
            for ext in JS_EXT:
                for path in (cand + ext, cand + "/index" + ext):
                    if path in tracked:
                        return path
        return None

    def targets(f, ext, text):
        if ext == ".py":
            here = f.split("/")[:-1]
            folder = "/".join(here)
            for dots, module, names in PY_FROM.findall(text):
                names = [x.split(" as ")[0].strip() for x in names.strip("() \t").split(",")]
                mod = module.split(".") if module else []
                if dots:  # relative: resolved on the path
                    up = len(dots) - 1
                    if up > len(here):
                        continue
                    stem = "/".join(here[: len(here) - up] + mod)
                    for name in names:
                        for path in (stem + "/" + name + ".py", stem + "/" + name + "/__init__.py",
                                     stem + ".py", stem + "/__init__.py"):
                            if path.lstrip("/") in tracked:
                                yield path.lstrip("/")
                                break
                elif module:
                    for name in names:
                        hit = py_file(module + "." + name, folder, text) or py_file(module, folder, text)
                        if hit:
                            yield hit
            for line in PY_IMPORT.findall(text):
                for module in line.split(","):
                    bits = module.split(" as ")[0].strip().split(".")
                    while bits:
                        hit = py_file(".".join(bits), folder, text)
                        if hit:
                            yield hit
                            break
                        bits.pop()
        elif ext in C_EXT:
            folder = posixpath.dirname(f)
            for spec in C_INCLUDE.findall(text):
                hit = c_file(spec.strip(), folder)
                if hit:
                    yield hit
        elif ext == ".go":
            head = text.split("\nfunc ", 1)[0]
            for spec in GO_STR.findall(head):
                for mod, folder in gomods:
                    if spec == mod or spec.startswith(mod + "/"):
                        hit = godirs.get(posixpath.normpath(posixpath.join(folder, spec[len(mod):].lstrip("/"))))
                        if hit:
                            yield hit
                        break
        else:
            mine = [a for a in aliases if not a[0] or f.startswith(a[0] + "/")]  # from tsconfigs above this file
            for spec in JS_SPEC.findall(text):
                hit = None
                if spec.startswith("."):
                    hit = js_file(posixpath.join(posixpath.dirname(f), spec))
                else:
                    decides = None  # the nearest tsconfig that knows the prefix; one further up gets no say
                    for scope, prefix, to in mine:
                        if spec.startswith(prefix) and decides in (None, scope):
                            decides = scope
                            hit = js_file(to + spec[len(prefix):])
                            if hit:
                                break
                    if not hit:
                        for name, folder in packages:
                            if spec == name or spec.startswith(name + "/"):
                                rest = spec[len(name):].lstrip("/")
                                hit = (js_file(folder + "/" + rest) or js_file(folder + "/src/" + rest)) if rest else \
                                    (js_file(folder + "/src/index") or js_file(folder + "/index") or folder + "/package.json")
                                break
                if hit:
                    yield hit

    links, langs = {}, collections.Counter()
    for f in files:
        ext = posixpath.splitext(f)[1]
        if ext not in LANGS:
            continue
        a = leaf(f, parts)
        if a is None or a.outside:
            continue
        text = read(root, f)
        if len(text) > SOURCE_MAX:
            continue
        langs[LANGS[ext]] += 1
        seen = set()
        for g in targets(f, ext, text):
            b = leaf(g, parts)
            if b is None or b is a or b in seen:
                continue
            seen.add(b)
            link = links.setdefault((a, b), [set(), []])
            link[0].add(f)
            if len(link[1]) < 3:
                link[1].append([f, g])
    return links, [name for name, _ in langs.most_common()]


def lifted(links, level):
    """Links between top-level parts (level "top"), or between the sub-parts inside one part (a Part)."""
    out = {}
    for (a, b), (sources, examples) in links.items():
        if level == "top":
            ka, kb = a.top, b.top
        elif a.parent is level and b.parent is level:
            ka, kb = a, b
        else:
            continue
        if ka is kb:
            continue
        link = out.setdefault((ka, kb), [set(), []])
        link[0] |= sources  # a file that reaches several rooms of one part still counts once
        link[1] = (link[1] + examples)[:3]
    return [{"a": a.name, "b": b.name, "n": len(sources), "ex": ex} for (a, b), (sources, ex) in
            sorted(out.items(), key=lambda kv: -len(kv[1][0]))]


def cmd_links(root, parts, t, args):
    files = zlist(git(root, "ls-files", "-z"))
    links, langs = code_links(root, files, parts)
    top = lifted(links, "top")
    if args.json:
        print(json.dumps({"languages": langs, "links": top,
                          "inside": {p.name: lifted(links, p) for p in parts if p.children and lifted(links, p)}},
                         ensure_ascii=False, indent=2))
        return
    if not top:
        print(t["links_none"])
        return
    print(t["links_head"].format(n=len(top), langs="、".join(langs) if t is TEXT["zh"] else ", ".join(langs)))
    weight = {(x["a"], x["b"]): x["n"] for x in top}
    for x in top:
        print("  " + t["uses"].format(a=x["a"], b=x["b"], n=x["n"]))
    both = sorted({tuple(sorted(k)) for k, n in weight.items()  # a real two-way tie, not one stray import
                   if min(n, weight.get((k[1], k[0]), 0)) * 4 >= max(n, weight.get((k[1], k[0]), 0))})
    if both:
        print(t["mutual"].format(pairs="；".join("%s ⇄ %s" % pair for pair in both)))


# Functions measured from the code -------------------------------------------
# A call chain on the list names functions and says in plain words what each one does. Where each function
# is, what it takes and gives back, and whether the one above it really calls it are not written by anyone:
# they are read from the code. Python is read with its own parser. C/C++, JavaScript/TypeScript and Go are
# read by pattern, which finds ordinary definitions and can miss unusual ones. In any other language a
# function is only looked up by its name, so it gets a place and nothing more.

FN_KIND = {".py": "py", ".go": "go", ".vue": "js", ".svelte": "js"}
FN_KIND.update({e: "c" for e in C_EXT})
FN_KIND.update({e: "js" for e in (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")})
NAME_ONLY_EXT = (".rs", ".java", ".kt", ".kts", ".swift", ".cs", ".rb", ".php", ".m", ".mm", ".scala", ".lua",
                 ".dart", ".ex", ".exs", ".sh", ".jl", ".zig", ".r", ".pl")
NOT_FUNCTIONS = frozenset(
    "if for while switch return sizeof catch else do function new typeof await defined alignof decltype with super "
    "throw delete case in of void yield static_assert alignas __attribute__ __declspec __asm__ asm try".split())
STORAGE_WORDS = frozenset("static inline extern virtual constexpr explicit friend __inline __inline__ async export".split())
IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")
CALL_RE = re.compile(r"(\.|->)?[ \t]*([A-Za-z_$][\w$]*)[ \t]*\(")
BLANK_RE = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`', re.S)
C_PRE_RE = re.compile(r"^[ \t]*#(?:\\\n|[^\n])*", re.M)
C_NAME_RE = re.compile(r"((?:[A-Za-z_]\w*::)*~?[A-Za-z_]\w*)[ \t\n]*\(")
GO_DEF_RE = re.compile(r"^func[ \t]*(\([^)\n]*\))?[ \t]*([A-Za-z_]\w*)[ \t]*(?:\[[^\]\n]*\])?[ \t]*\(", re.M)
PY_DEF_RE = re.compile(r"^[ \t]*(?:(?:async[ \t]+)?def|class)[ \t]+(\w+)", re.M)
JS_CLASS_RE = re.compile(r"\bclass[ \t]+([A-Za-z_$][\w$]*)[^{;()]*\{")
JS_DEFS = (
    # function name(            a declaration
    ("fn", re.compile(r"\b(?:async[ \t]+)?function[ \t]*\*?[ \t]*([A-Za-z_$][\w$]*)[ \t]*(?:<[^>(){}]*>)?[ \t]*\(")),
    # const name = (            an arrow function, or a function expression
    ("eq", re.compile(r"\b(?:const|let|var)[ \t]+([A-Za-z_$][\w$]*)[ \t]*(?::[^=;\n]+?)?=[ \t\n]*(?:async[ \t]*)?"
                      r"(function\b[ \t]*\*?[ \t]*[\w$]*[ \t]*)?(?:<[^>(){}]*>[ \t]*)?\(")),
    # name(                     a method of a class or of an object
    ("method", re.compile(r"^[ \t]*(?:(?:export|default|public|private|protected|static|readonly|async|override|abstract"
                          r"|get|set)[ \t]+)*\*?[ \t]*([A-Za-z_$#][\w$]*)[ \t]*(?:<[^>(){}]*>)?[ \t]*\(", re.M)),
    # this.name = (            the same, assigned
    ("eq", re.compile(r"([A-Za-z_$][\w$]*)[ \t]*=[ \t]*(?:async[ \t]*)?(function\b[ \t]*\*?[ \t]*[\w$]*[ \t]*)?\(")),
    # name: (                  the same, as a property; it needs a body in braces, or a parameter's type
    # (`cb: (x: number) => void`) would be taken for a function
    ("prop", re.compile(r"([A-Za-z_$][\w$]*)[ \t]*:[ \t]*(?:async[ \t]*)?(function\b[ \t]*\*?[ \t]*[\w$]*[ \t]*)?\(")),
)
JS_AFTER_RE = re.compile(r"\s*(?::\s*([^;{}=()]+?))?\s*(?:(=>)\s*(\{)?|(\{))")  # `: Type`, then `=>` or a body
PAIRS = {"{": re.compile(r"[{}]"), "(": re.compile(r"[()]")}
SIG_TEXT = 220     # characters of one signature
DOC_TEXT = 480     # characters of the comment the code itself carries on a function
TREE_NODES = 80    # functions printed by `calls --from`


def _spaces(m):
    return re.sub(r"[^\n]", " ", m.group(0))


def blanked(text, pre=False):
    """The source with its comments and strings written as spaces, so that a brace or a name inside one is
    not taken for code. Every character keeps its place. `pre` also blanks C preprocessor lines."""
    code = BLANK_RE.sub(_spaces, text)
    return C_PRE_RE.sub(_spaces, code) if pre else code


def close_of(code, at, limit=600000):
    """The index just past the bracket that closes the one at `at`; -1 when nothing closes it."""
    depth, opener = 0, code[at]
    for m in PAIRS[opener].finditer(code, at, min(len(code), at + limit)):
        depth += 1 if m.group(0) == opener else -1
        if depth == 0:
            return m.end()
    return -1


def lead_comment(text, start):
    """The comment written right above a definition, as one stretch of plain text."""
    head = text[:start].rstrip()
    if head.endswith("*/"):
        at = head.rfind("/*")
        lines = [re.sub(r"^\s*[*!]+ ?", "", x) for x in head[at + 2:-2].split("\n")] if at >= 0 else []
    else:
        lines = []
        for x in reversed(head.split("\n")[-40:]):
            if not x.strip().startswith("//"):
                break
            lines.insert(0, x.strip().lstrip("/!").strip())
    return " ".join(" ".join(lines).split())[:DOC_TEXT]


def split_params(text):
    """A parameter list cut at its top-level commas."""
    out, depth, cur, last = [], 0, "", ""
    for ch in text:
        if ch in "([{<":
            depth += 1
        elif ch in ")]}" or (ch == ">" and last not in "=-"):
            depth -= 1
        if ch == "," and depth <= 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
        last = ch
    out.append(cur)
    return [" ".join(x.split()) for x in out if x.strip()]


def param_of(kind, text):
    """One written parameter as {name, type}."""
    if kind == "c":
        text = text.split("=")[0].strip()
        if text in ("void", ""):
            return None
        m = re.search(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)*$", text)
        if not m or m.start() == 0:   # `...`, or a type with no name
            return {"name": text, "type": ""}
        return {"name": m.group(1), "type": (text[:m.start()] + text[m.end(1):]).strip()}
    if kind == "go":
        bits = text.split(None, 1)
        return {"name": bits[0], "type": bits[1] if len(bits) > 1 else ""}
    m = re.match(r"((?:\.\.\.)?[A-Za-z_$][\w$]*|[\[{].*?[\]}])\s*\??\s*(?::\s*([^=]+?))?\s*(?:=.*)?$", text)   # js, ts
    if not m:
        return {"name": text, "type": ""}
    return {"name": m.group(1), "type": (m.group(2) or "").strip()}


def calls_in(body, own=""):
    """The names a stretch of blanked code calls, in the order they first appear: [(name, how)]. `how` is
    "attr" for a call made on something (`x.f()`, `x->f()`), "name" for a plain one."""
    seen, out = {own} if own else set(), []
    for m in CALL_RE.finditer(body):
        name = m.group(2)
        if name in NOT_FUNCTIONS or name in seen:
            continue
        seen.add(name)
        out.append((name, "attr" if m.group(1) else "name"))
    return out


def regex_function(kind, text, code, lines, name, qual, start, opened, closed, body_at, end, returns=""):
    """One function found by pattern. `start` is where its header begins, `opened`/`closed` bracket its
    parameter list, `body_at`..`end` is its body; all are offsets into the text."""
    params = [p for p in (param_of(kind, x) for x in split_params(text[opened + 1:closed - 1])) if p]
    body = code[body_at:end]
    return {"name": name, "qual": qual, "line": bisect_line(lines, start), "end": bisect_line(lines, max(start, end - 1)),
            "sig": " ".join(text[start:body_at].split()).rstrip("{ ")[:SIG_TEXT], "params": params,
            "returns": " ".join(x for x in returns.split() if x not in STORAGE_WORDS),
            "calls": calls_in(body, name), "refs": set(IDENT_RE.findall(body)),
            "words": set(IDENT_RE.findall(text[start:end])), "doc": lead_comment(text, start)}


def line_starts(text):
    out, at = [0], text.find("\n")
    while at >= 0:
        out.append(at + 1)
        at = text.find("\n", at + 1)
    return out


def bisect_line(starts, offset):
    lo, hi = 0, len(starts)
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid
    return lo + 1


def py_functions(text):
    """Every function a Python file defines, read with Python's own parser. A file this Python cannot parse
    gives none."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []
    lines, out, unparse = text.split("\n"), [], getattr(ast, "unparse", None)

    def show(node):
        try:
            return unparse(node) if unparse and node is not None else ""
        except Exception:
            return ""

    def said(node):
        try:
            return " ".join((ast.get_docstring(node) or "").split())[:DOC_TEXT]
        except Exception:
            return ""

    def one(node, prefix, in_class):
        a = node.args
        args = list(getattr(a, "posonlyargs", [])) + list(a.args) + ([a.vararg] if a.vararg else []) + \
            list(a.kwonlyargs) + ([a.kwarg] if a.kwarg else [])
        params = [{"name": x.arg, "type": show(x.annotation)} for x in args]
        if in_class and params and params[0]["name"] in ("self", "cls"):
            params = params[1:]
        calls, refs = [], set()
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name):
                    calls.append((n.lineno, n.col_offset, f.id, "name"))
                elif isinstance(f, ast.Attribute):
                    mine = isinstance(f.value, ast.Name) and f.value.id in ("self", "cls")
                    calls.append((n.lineno, n.col_offset, f.attr, "self" if mine else "attr"))
            elif isinstance(n, ast.Name):
                refs.add(n.id)
            elif isinstance(n, ast.Attribute):
                refs.add(n.attr)
        seen, ordered = {node.name}, []
        for _, _, name, how in sorted(calls):
            if name not in seen:
                seen.add(name)
                ordered.append((name, how))
        end = getattr(node, "end_lineno", None) or node.lineno
        head = ("async def " if isinstance(node, ast.AsyncFunctionDef) else "def ") + node.name + \
            "(" + (show(a) or ", ".join(x.arg for x in args)) + ")" + (" -> " + show(node.returns) if node.returns else "")
        return {"name": node.name, "qual": prefix + node.name, "line": node.lineno, "end": end,
                "sig": " ".join(head.split())[:SIG_TEXT], "params": params, "returns": show(node.returns),
                "calls": ordered, "refs": refs, "doc": said(node),
                "words": set(IDENT_RE.findall("\n".join(lines[node.lineno - 1:end])))}

    def a_class(node, prefix, inside):
        """A class is called like a function. It answers with the parameters of its `__init__`, or, when it
        has none (a dataclass, a model), with the fields its body declares."""
        made = [f for f in inside if f["qual"] == prefix + node.name + ".__init__"]
        fields = [{"name": x.target.id, "type": show(x.annotation)} for x in node.body
                  if isinstance(x, ast.AnnAssign) and isinstance(x.target, ast.Name)]
        end = getattr(node, "end_lineno", None) or node.lineno
        bases = ", ".join(filter(None, (show(b) for b in node.bases)))
        return {"name": node.name, "qual": prefix + node.name, "line": node.lineno, "end": end,
                "sig": (("class " + node.name + ("(" + bases + ")" if bases else "")) + (
                    ": " + ", ".join(p["name"] + (": " + p["type"] if p["type"] else "")
                                     for p in (made[0]["params"] if made else fields)) if made or fields else ""))[:SIG_TEXT],
                "params": made[0]["params"] if made else fields, "returns": "",
                "calls": made[0]["calls"] if made else [], "refs": made[0]["refs"] if made else set(),
                "words": set(IDENT_RE.findall("\n".join(lines[node.lineno - 1:end]))), "doc": said(node),
                "bases": [x for x in (re.sub(r"\[.*", "", show(b)).split(".")[-1] for b in node.bases) if x]}

    def walk(node, prefix, in_class):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append(one(child, prefix, in_class))
                walk(child, prefix + child.name + ".", False)
            elif isinstance(child, ast.ClassDef):
                first = len(out)
                walk(child, prefix + child.name + ".", True)
                out.append(a_class(child, prefix, out[first:]))
            elif not isinstance(child, ast.expr):
                walk(child, prefix, in_class)
    try:
        walk(tree, "", False)
    except RecursionError:
        pass
    return out


def c_functions(text):
    """The functions a C or C++ file defines. It walks the file from brace to brace: a brace that follows
    `name(...)` opens a function, whose body is then skipped whole, so nothing inside a body is mistaken
    for a definition. The braces of a class, a struct or a namespace are stepped into."""
    code, lines, out, at = blanked(text, pre=True), line_starts(text), [], 0
    while True:
        brace = code.find("{", at)
        if brace < 0:
            break
        start = max(code.rfind(";", 0, brace), code.rfind("}", 0, brace), code.rfind("{", 0, brace)) + 1
        head = code[start:brace]
        found = None
        for m in C_NAME_RE.finditer(head):
            if m.group(1).split("::")[-1].lstrip("~") not in NOT_FUNCTIONS:
                found = m
                break
        end = close_of(code, brace)
        if end < 0:
            break
        if found is None or "=" in head[:found.start()]:
            # no function here: a table of values is skipped, anything else may hold functions inside
            at = end if ("=" in head or re.search(r"\benum\b", head)) else brace + 1
            continue
        opened = start + found.end() - 1
        closed = close_of(code, opened)
        if closed < 0 or closed > brace:
            at = brace + 1
            continue
        qual = found.group(1).replace("::", ".")
        begin = start + len(head) - len(head.lstrip())
        out.append(regex_function("c", text, code, lines, qual.split(".")[-1], qual, begin, opened, closed, brace, end,
                                  returns=head[:found.start()].strip()))
        at = end
    return out


def go_functions(text):
    code, lines, out = blanked(text), line_starts(text), []
    for m in GO_DEF_RE.finditer(code):
        opened = m.end() - 1
        closed = close_of(code, opened)
        brace = code.find("{", closed) if closed > 0 else -1
        if brace < 0 or "\n\n" in code[closed:brace] or ";" in code[closed:brace]:
            continue
        end = close_of(code, brace)
        if end < 0:
            continue
        owner = IDENT_RE.findall(m.group(1) or "")
        name = m.group(2)
        out.append(regex_function("go", text, code, lines, name, (owner[-1] + "." if owner else "") + name,
                                  m.start(), opened, closed, brace, end, returns=code[closed:brace].strip()))
    return out


def js_functions(text):
    """The functions a JavaScript or TypeScript file defines, by pattern: declarations, arrow functions and
    function expressions given a name, and methods."""
    code, lines, found = blanked(text), line_starts(text), {}
    classes = []
    for m in JS_CLASS_RE.finditer(code):
        end = close_of(code, m.end() - 1)
        if end > 0:
            classes.append((m.end(), end, m.group(1)))
    for kind, rx in JS_DEFS:
        for m in rx.finditer(code):
            name = m.group(1)
            if name in NOT_FUNCTIONS or name == "constructor" and kind != "method":
                continue
            opened = m.end() - 1
            closed = close_of(code, opened, 20000)
            if closed < 0:
                continue
            after = JS_AFTER_RE.match(code, closed)
            if not after:
                continue
            arrow, brace = bool(after.group(2)), bool(after.group(3) or after.group(4))
            plain = kind in ("fn", "method") or bool(m.group(2))   # written with the word `function`, or as a method
            if (plain and (arrow or not brace)) or (not plain and not arrow) or (kind == "prop" and not brace):
                continue
            if brace:
                body_at = after.end() - 1
                end = close_of(code, body_at)
                if end < 0:
                    continue
            else:  # an arrow function that is one expression: it ends with its line
                body_at = after.end()
                stop = code.find("\n", body_at)
                end = len(code) if stop < 0 else stop
            start = m.start() + len(m.group(0)) - len(m.group(0).lstrip())
            owner = [c[2] for c in classes if c[0] <= start < c[1]] if kind == "method" else []
            fn = regex_function("js", text, code, lines, name.lstrip("#"), (owner[-1] + "." if owner else "") + name.lstrip("#"),
                                start, opened, closed, body_at, end, returns=(after.group(1) or "").strip())
            found.setdefault((fn["line"], fn["name"]), fn)   # one definition can answer to two patterns: the first stands
    out = [found[k] for k in sorted(found)]
    for at, end, name in classes:  # a class is called like a function: it answers with its constructor's parameters
        made = [f for f in out if f["qual"] == name + ".constructor"]
        head = code.rfind("class", 0, at)
        out.append({"name": name, "qual": name, "line": bisect_line(lines, head), "end": bisect_line(lines, end - 1),
                    "sig": " ".join(text[head:at - 1].split())[:SIG_TEXT], "params": made[0]["params"] if made else [],
                    "returns": "", "calls": made[0]["calls"] if made else [], "refs": made[0]["refs"] if made else set(),
                    "words": set(IDENT_RE.findall(text[head:end])), "doc": lead_comment(text, head),
                    "bases": re.findall(r"\bextends[ \t]+([A-Za-z_$][\w$]*)", text[head:at])})
    return out


class Code:
    """The functions of the project, read when asked for. Finding a function by name reads every source file
    once; that is only done when the list holds a call chain, or for `calls --from`."""

    def __init__(self, root, files, parts):
        self.root, self.parts = root, parts
        self.files = [f for f in files if posixpath.splitext(f)[1] in FN_KIND and not f.endswith((".min.js", ".d.ts"))]
        self.others = [f for f in files if posixpath.splitext(f)[1].lower() in NAME_ONLY_EXT]
        self.fns, self.index = {}, None

    def functions(self, f):
        if f not in self.fns:
            text = read(self.root, f)
            if len(text) > SOURCE_MAX or (len(text) > 20000 and text.count("\n") * 400 < len(text)):
                fns = []   # generated or minified
            else:
                kind = FN_KIND[posixpath.splitext(f)[1]]
                try:
                    fns = {"py": py_functions, "c": c_functions, "go": go_functions, "js": js_functions}[kind](text)
                except RecursionError:
                    fns = []
            last = {}
            for fn in fns:  # of several definitions under one name (overloads, a property and its setter) the last stands
                fn["file"] = f
                last[fn["qual"]] = fn
            self.fns[f] = sorted(last.values(), key=lambda fn: fn["line"])
        return self.fns[f]

    def names(self):
        """{a function's bare name: the files that define one}."""
        if self.index is None:
            self.index = collections.defaultdict(list)
            for f in self.files:
                if f.endswith(".py"):
                    names = set(PY_DEF_RE.findall(read(self.root, f)))
                else:
                    names = {fn["name"] for fn in self.functions(f)}
                for name in names:
                    self.index[name].append(f)
        return self.index

    def defined(self, bare, qual=None, depth=0):
        qual = qual or bare
        out = [fn for f in self.names().get(bare, ()) for fn in self.functions(f)
               if fn["name"] == bare and (fn["qual"] == qual or fn["qual"].endswith("." + qual))]
        if not out and "." in qual and depth < 6:   # `Class.method`, where the method is one the class inherits
            owner = qual.rsplit(".", 1)[0]
            for cls in self.defined(owner.split(".")[-1], owner, 6):
                for base in cls.get("bases", ()):
                    out += [fn for fn in self.defined(bare, base + "." + bare, depth + 1) if fn not in out]
        if not out and "." in qual:   # `module.function`: the part before the dot may be the file
            stem = qual.rsplit(".", 1)[0]
            out = [fn for f in self.names().get(bare, ()) for fn in self.functions(f) if fn["qual"] == bare and
                   ("/" + posixpath.splitext(f)[0].replace("/__init__", "")).replace("/", ".").endswith("." + stem)]
        return out

    def lookup(self, written, near="", unit=None):
        """The function a written name means: (state, function or None, the candidates when several fit).
        `state` is "ok", "many" (several functions answer to the name and nothing settles which), "text"
        (only found by its name, in a language that is not read) or "lost". A name can be narrowed as
        `Class.method` or `path/file.py:name`. Of several, the one in `unit`, then the one in the file
        `near`, then the project's own code, then code that is not a test, is taken when that leaves one."""
        hint, name = "", written.replace("::", ".").strip()
        if ":" in name:
            hint, name = [x.strip() for x in name.rsplit(":", 1)]
        bare = name.split(".")[-1]
        cands = self.defined(bare, name)
        if hint:
            cands = [c for c in cands if c["file"] == hint or c["file"].endswith("/" + hint)]
        tests = re.compile(r"(?:^|/)(?:tests?|__tests__|spec|examples?|docs?)/|(?:^|/)test_|[._]test\.|\.spec\.")
        for keep in (lambda c: unit is not None and within(unit, leaf(c["file"], self.parts)),
                     lambda c: c["file"] == near,
                     lambda c: not getattr(leaf(c["file"], self.parts), "outside", ""),
                     lambda c: not tests.search(c["file"]),
                     lambda c: c["qual"] == name):
            if len(cands) > 1:
                cands = [c for c in cands if keep(c)] or cands
        if len(cands) == 1:
            return "ok", cands[0], []
        if cands:
            return "many", None, cands
        found = self.by_name(bare, hint)
        return ("text", found, []) if found else ("lost", None, [])

    def by_name(self, bare, hint=""):
        """A function in a language that is not read: the first line that looks like its definition."""
        rx = re.compile(r"^[^\n]*?\b(?:fn|func|fun|def|function|sub|proc)\b[^\n;]*?\b%s\b|"
                        r"^[^\n;=]*\b(?:void|public|private|protected|static|internal|override)\b[^\n;=]*?\b%s[ \t]*\("
                        % (re.escape(bare), re.escape(bare)), re.M)
        for f in self.others:
            if hint and not (f == hint or f.endswith("/" + hint)):
                continue
            text = read(self.root, f)
            if bare not in text:
                continue
            m = rx.search(text)
            if m:
                return {"name": bare, "qual": bare, "file": f, "line": text.count("\n", 0, m.start()) + 1,
                        "end": 0, "sig": " ".join(m.group(0).split())[:SIG_TEXT], "params": [], "returns": "",
                        "calls": [], "refs": None, "words": None, "doc": ""}
        return None

    def callees(self, fn):
        """What a function calls, among the functions the project itself defines: ([function], [names that
        several functions answer to]). A call is followed to the same file first, then, for a call on
        `self`, to the same class; otherwise only a name that one function in the project answers to."""
        got, unsure = [], []
        for name, how in fn["calls"]:
            mine = FN_KIND.get(posixpath.splitext(fn["file"])[1])
            cands = [c for c in self.defined(name) if FN_KIND.get(posixpath.splitext(c["file"])[1]) == mine]
            if how == "name" and fn["file"].endswith(".py"):
                cands = [c for c in cands if "." not in c["qual"]]   # a plain call reaches a function or a class, not a method
            if not cands:
                continue
            here = [c for c in cands if c["file"] == fn["file"]]
            if how == "self" and "." in fn["qual"]:
                same = [c for c in here if c["qual"].rsplit(".", 1)[0] == fn["qual"].rsplit(".", 1)[0]]
                here = same or here
            cands = here or [c for c in cands if not getattr(leaf(c["file"], self.parts), "outside", "")] or cands
            if len(cands) == 1:
                if cands[0] is not fn:
                    got.append(cands[0])
            elif how != "attr" or len(cands) <= 3:
                unsure.append(name)
        return got, unsure


def one_line(fn, limit=96):
    """A function as one line of a listing: its signature as written, or, when that is long, its name with
    the names of its parameters."""
    if len(fn["sig"]) <= limit or not fn["params"]:
        return fn["sig"][:limit + 40] or fn["qual"] + "()"
    names = [p["name"] for p in fn["params"]]
    return "%s(%s%s)" % (fn["qual"], ", ".join(names[:6]), ", …" if len(names) > 6 else "")


def fn_key(fn):
    """What a function goes by wherever one of its own is kept (its note, its source on the page)."""
    return fn["file"] + ":" + fn["qual"]


def fn_unit(fn, parts):
    return leaf(fn["file"], parts) if fn else None


def io_rows(rows, fn, way):
    """The things a chain says go into a function, or come out of it, each looked for in the function: a
    parameter (with its type as the code writes it), the return value, or a name the function uses."""
    out = []
    for row in rows[:RUN_VALUES]:
        name = row["name"]
        new = {"name": name, "what": row["what"], "via": row.get("via", ""), "kind": "", "type": "", "lost": False}
        if name.lower() in RETURN_WORDS:
            new.update(kind="return", type=(fn or {}).get("returns", ""))
        elif fn and fn["words"] is not None:
            words = IDENT_RE.findall(name)
            by_name = {p["name"].lstrip(".*&"): p for p in fn["params"]}
            if words and words[0] in by_name:
                new.update(kind="param", type=by_name[words[0]]["type"] if len(words) == 1 else "")
            elif not words or not all(w in fn["words"] for w in words):
                new["lost"] = True
        out.append(new)
    return out


def read_chain(chain, code, parts, wiring, unit=None, seen=None):
    """One call chain as written, with what the code says about each of its functions. The lines of a chain
    are its functions and, where it forks, a branch with its cases. Every line says where it hangs: `up` is
    the line it stands under, `d` how many functions deep it is (a branch and a case add no depth: what a
    case holds is called by the function the branch stands under), `cases` the cases it lies inside, and,
    for a case, `group`, the first of the cases it is an alternative to."""
    steps, above, units, passed = [], [], [], [0]
    last_child = {}   # the line a line stands under -> the last line written under it so far
    queue, at_q = list(chain["steps"]), 0
    while at_q < len(queue) and len(steps) < CHAIN_STEPS:
        s, at = queue[at_q], len(steps)
        at_q += 1
        above = above[:s["depth"]]
        while len(above) < s["depth"]:   # set in by more than one level: it still hangs on the line above
            above.append(above[-1] if above else {"at": -1, "fn": None, "d": -1, "cases": [], "kind": "fn"})
        parent = above[-1] if above else None
        up = parent["at"] if parent else -1
        caller = parent["fn"] if parent else None   # the nearest function above; a branch or a case passes it on
        d = (parent["d"] + (1 if parent["kind"] == "fn" else 0)) if parent else 0
        cases = (parent["cases"] + ([parent["at"]] if parent["kind"] == "case" else [])) if parent else []
        if s["kind"] == "expand":
            # what the function above calls, read from the code, takes its place in the chain from here on
            add, had = [], {fn_key(caller)} if caller and caller.get("qual") else set()
            says = s.get("says") or {}   # the sentences written under `展开` for the functions it fills in

            def grow(fn, depth, level):
                for g in code.callees(fn)[0]:
                    if len(add) >= EXPAND_NODES:
                        return
                    if g["end"] - g["line"] < EXPAND_TINY and not code.callees(g)[0]:
                        passed[0] += 1   # a few lines that call nothing further: left out, and counted
                        continue
                    said = [says[k] for k in (g["file"] + ":" + g["qual"], g["qual"], g["name"]) if says.get(k)]
                    add.append({"kind": "fn", "fn": g["file"] + ":" + g["qual"], "what": said[0] if said else "",
                                "note": "", "more": [], "depth": depth, "ins": [], "outs": [], "auto": True,
                                "exp": s.get("at")})
                    if fn_key(g) not in had and level < s["levels"]:
                        had.add(fn_key(g))
                        grow(g, depth + 1, level + 1)
            if had:
                grow(caller, s["depth"], 1)
            queue[at_q:at_q] = add
            continue
        row = {"kind": s["kind"], "fn": s["fn"], "what": s["what"], "note": s.get("note", ""), "more": s.get("more", []),
               "up": up, "d": max(0, d), "cases": cases, "auto": bool(s.get("auto")),
               # where its sentence is written: its own line, or for a filled-in function the `展开` line
               "at": s.get("at"), "exp": s.get("exp")}
        if s["kind"] != "fn":
            if s["kind"] == "case":
                before = last_child.get(up)
                row["group"] = steps[before]["group"] if before is not None and steps[before]["kind"] == "case" else at
            last_child[up] = at
            steps.append(row)
            above.append({"at": at, "fn": caller, "d": row["d"], "cases": cases, "kind": s["kind"]})
            continue
        state, fn, cands = code.lookup(s["fn"], near=caller["file"] if caller else "", unit=unit)
        home = fn_unit(fn, parts)
        if home is not None and home not in units:
            units.append(home)
        called = None   # does the function above mention this one? None when that cannot be told
        if caller is not None and caller["refs"] is not None and state in ("ok", "text"):
            called = fn["name"] in caller["refs"] or (fn["name"] in ("__init__", "constructor") and
                                                      fn["qual"].split(".")[-2:-1] and fn["qual"].split(".")[-2] in caller["refs"])
        ran = (seen or {}).get((fn["file"], fn["name"])) if fn else None
        ins, outs = io_rows(s["ins"], fn, "ins"), io_rows(s["outs"], fn, "outs")
        told = {(IDENT_RE.findall(v["name"]) or [""])[0] for v in ins + outs}
        if row["auto"] and fn:
            row["fn"] = fn["qual"]
        row.update({"name": fn["qual"] if fn else s["fn"], "key": fn_key(fn) if fn else "",
                    "state": state, "file": fn["file"] if fn else "", "line": fn["line"] if fn else 0,
                    "sig": fn["sig"] if fn else "", "line1": one_line(fn) if fn else "",
                    "returns": fn["returns"] if fn else "", "doc": fn["doc"] if fn else "",
                    # every parameter the code gives the function, and whether the chain says what it is
                    "params": [{"name": p["name"], "type": p["type"], "told": p["name"].lstrip(".*&") in told}
                               for p in (fn["params"] if fn else [])],
                    "unit": wiring.ids.get(home, "") if home is not None else "",
                    "unitName": unit_label(home) if home is not None else "",
                    "loose": called is False, "caller": caller.get("written", "") if caller else "",
                    "cands": ["%s:%d %s" % (c["file"], c["line"], c["qual"]) for c in cands[:4]],
                    "ins": ins, "outs": outs, "ran": ran})
        last_child[up] = at
        steps.append(row)
        above.append({"at": at, "fn": dict(fn or {"file": "", "refs": None}, written=s["fn"]), "d": row["d"],
                      "cases": cases, "kind": "fn"})
    return {"title": chain["title"], "intro": chain.get("intro", []), "steps": steps,
            "n": sum(1 for x in steps if x["kind"] == "fn"), "auto": sum(1 for x in steps if x["auto"]),
            "passed": passed[0],
            "forks": len({x["group"] for x in steps if x["kind"] == "case"}),
            "units": [wiring.ids[u] for u in units if u in wiring.ids],
            "more": max(0, len(queue) - at_q)}


def load_chains(root, files, parts, routes, top, wiring, runs=(), calls_file="", listed="", source=True):
    """Every call chain, measured, and the book of the functions on them: ([chain], book). First the chains
    in the calls file, in its order. Then any that are still written inside the parts list, which is where
    they stood before they had a file of their own: those under no part, then each part's and each room's,
    which go by the unit's name when they carry no title. Nothing of the code is read when there are none.

    The book is {"fns": {key: {file, line, src, cut, note}}, "notes": how many notes the notes file holds,
    "notes_file": where it is or would be, "lost": the notes whose function the code does not have}. `src`
    is the function's own lines, for the page where a reader keeps notes on it; `note` is the note the
    notes file holds for it."""
    units = [u for p in parts for u in [p] + p.children]
    folder = os.path.dirname(calls_file) if calls_file else os.path.dirname(os.path.join(root, listed or "x"))
    notes_file = os.path.join(folder, NOTES_FILE)
    book = {"fns": {}, "notes": 0, "notes_file": os.path.relpath(notes_file, root).replace(os.sep, "/"), "lost": [],
            "heads": {}}   # function -> the headings its note stands under, as written
    written = [(c, os.path.relpath(calls_file, root).replace(os.sep, "/"), None)
               for c in (read_calls(slurp(calls_file)) if calls_file else [])]
    written += [(c, listed, None) for c in top.get("chains", [])]
    written += [(c, listed, u) for u in units for c in u.calls]
    if not written:
        return [], book
    code = Code(root, files, parts)
    seen = {}   # (file, function) -> what the latest recorded run noted at that function
    for run in filter(None, runs):
        for s in run["steps"]:
            key = (s["file"], s["fn"].split(".")[-1].replace("()", ""))
            if s["file"] and s["fn"] and key not in seen and (s["ins"] or s["outs"]):
                seen[key] = {"route": run["route"], "recorded": run["recorded"], "ins": s["ins"], "outs": s["outs"]}
    out = []
    for c, where, u in written:
        chain = read_chain(c, code, parts, wiring, unit=u, seen=seen)
        chain["title"] = (unit_label(u) + ("：" + c["title"] if c["title"] else "")) if u is not None else c["title"]
        chain["file"], chain["in_list"] = where, where == listed and bool(listed)
        if chain["in_list"] or not calls_file:   # only a line of the calls file can be handed back from the page
            for row in chain["steps"]:
                row["at"] = row["exp"] = None
        out.append(chain)
    # the notes a reader keeps, each found by the function its heading names
    noted = {}
    for name, body in (read_notes(slurp(notes_file)) if os.path.isfile(notes_file) else []):
        book["notes"] += 1
        state, fn, _ = code.lookup(name)
        if fn is None:
            book["lost"].append({"fn": name, "why": state})
        else:
            noted[fn_key(fn)] = (noted[fn_key(fn)] + "\n\n" if fn_key(fn) in noted else "") + body
            book["heads"].setdefault(fn_key(fn), []).append(name)
    budget = SRC_TOTAL
    for chain in out:
        for s in chain["steps"]:
            if s["kind"] != "fn" or not s["key"] or s["key"] in book["fns"]:
                continue
            lines, cut = [], False
            if source and budget > 0:
                text = read(root, s["file"]).split("\n")
                state, fn, _ = code.lookup(s["key"])
                end = fn["end"] if fn and fn["end"] >= s["line"] else s["line"] + 39   # found by name only: a screenful
                lines = text[s["line"] - 1:end]
                cut = len(lines) > SRC_LINES
                lines = [x.rstrip()[:400] for x in lines[:SRC_LINES]]
                budget -= sum(len(x) + 1 for x in lines)
            book["fns"][s["key"]] = {"file": s["file"], "line": s["line"], "src": "\n".join(lines), "cut": cut,
                                     "note": noted.get(s["key"], "")}
    for key, body in noted.items():   # a note on a function that no chain names is still the reader's: kept, not shown
        book["fns"].setdefault(key, {"file": key.split(":")[0], "line": 0, "src": "", "cut": False, "note": body,
                                     "off": True})
    return out, book


def chain_problems(chains):
    """Where a call chain and the code do not agree, and where a chain says too little to be read: a function
    with no sentence, a function the code gives parameters to of which the chain names none, and a branch
    with fewer than two ways through."""
    out = {"lost": [], "many": [], "loose": [], "names": [], "untold": [], "bare": [], "forks": []}
    for c in chains:
        where = c["title"] or "?"
        ways = collections.Counter(s["group"] for s in c["steps"] if s["kind"] == "case")
        out["forks"] += [{"on": where, "branch": c["steps"][g]["what"]} for g, n in ways.items() if n < 2]
        for s in c["steps"]:
            if s["kind"] != "fn":
                continue
            if s["state"] == "lost":
                out["lost"].append({"on": where, "fn": s["fn"]})
            elif s["state"] == "many":
                out["many"].append({"on": where, "fn": s["fn"], "candidates": s["cands"]})
            if s["loose"]:
                out["loose"].append({"on": where, "caller": s["caller"], "fn": s["fn"]})
            out["names"] += [{"on": where, "fn": s["fn"], "name": v["name"]} for v in s["ins"] + s["outs"] if v["lost"]]
            if s["auto"]:
                continue
            if not s["what"]:
                out["untold"].append({"on": where, "fn": s["fn"]})
            if s["state"] == "ok" and s["params"] and not s["ins"] and not s["outs"]:
                out["bare"].append({"on": where, "fn": s["fn"]})
    return out


def cmd_calls(root, parts, t, args):
    """Without --from: the chains written on the list, each function with what the code says of it. With
    --from: which functions one function calls, and those in turn, read from the code."""
    files = zlist(git(root, "ls-files", "-z"))
    zh = t is TEXT["zh"]
    if args.start:
        code = Code(root, files, parts)
        state, fn, cands = code.lookup(args.start)
        if state == "many":
            raise SystemExit(t["calls_many"].format(fn=args.start) + "\n  " +
                             "\n  ".join("%s:%d  %s" % (c["file"], c["line"], c["qual"]) for c in cands[:12]))
        if state != "ok":
            raise SystemExit(t["calls_lost"].format(fn=args.start))
        shown, rows = set(), []

        def walk(fn, depth):
            home = fn_unit(fn, parts)
            again = (fn["file"], fn["qual"]) in shown
            row = {"depth": depth, "fn": fn["qual"], "file": fn["file"], "line": fn["line"], "sig": fn["sig"],
                   "line1": one_line(fn), "params": [p["name"] for p in fn["params"]],
                   "unit": unit_label(home) if home is not None else "", "again": again, "unsure": []}
            rows.append(row)
            if again or depth >= args.depth or len(rows) >= TREE_NODES:
                return
            shown.add((fn["file"], fn["qual"]))
            got, row["unsure"] = code.callees(fn)
            for g in got:
                if len(rows) < TREE_NODES:
                    walk(g, depth + 1)
        walk(fn, 0)
        if args.json:
            print(json.dumps({"from": args.start, "depth": args.depth, "calls": rows}, ensure_ascii=False, indent=2))
            return
        if args.draft:   # the frame of a chain, as measured: the sentences and the meanings are left to write
            print("```calls")
            for r in rows:
                several = len(code.defined(r["fn"].split(".")[-1], r["fn"])) > 1
                print("%s%s | " % ("  " * r["depth"], (r["file"] + ":" if several else "") + r["fn"]))
                for name in r["params"]:
                    print("%s  %s %s: " % ("  " * r["depth"], t["run_in"], name))
            print("```")
            unsure = sorted({x for r in rows for x in r["unsure"]})
            if unsure:
                print(t["calls_unsure"].format(x=("、" if zh else ", ").join(unsure[:30])))
            print(t["calls_draft"])
            return
        print(t["calls_tree"].format(fn=fn["qual"], d=args.depth))
        for r in rows:
            pad_ = "  " + "    " * r["depth"]
            print("%s%s  %s:%d%s%s" % (pad_, r["line1"], r["file"], r["line"],
                                       "  [%s]" % r["unit"] if r["unit"] else "", "  " + t["calls_again"] if r["again"] else ""))
            if r["unsure"]:
                print(pad_ + "    " + t["calls_unsure"].format(x=("、" if zh else ", ").join(r["unsure"][:12])))
        if len(rows) >= TREE_NODES:
            print("  …")
        print(t["calls_limit"])
        return
    wiring = Wiring(parts, args.routes, args.top)
    runs = load_runs(root, args.runs, args.routes, parts, args.top)[0]
    listed = os.path.relpath(args.list_path, root).replace(os.sep, "/")
    chains, book = load_chains(root, files, parts, args.routes, args.top, wiring, runs, args.calls_path, listed,
                               source=False)
    if args.json:
        print(json.dumps({"file": args.calls_home, "chains": chains, "problems": chain_problems(chains),
                          "notes_file": book["notes_file"], "notes": {k: v["note"] for k, v in book["fns"].items() if v["note"]},
                          "notes_lost": book["lost"]}, ensure_ascii=False, indent=2))
        return
    if not chains:
        print(t["calls_none"].format(file=args.calls_home))
        return
    print(t["calls_head"].format(n=len(chains)))
    for c in chains:
        print("  %s  [%s%s%s%s%s]" % (c["title"] or "?", t["calls_steps"].format(n=c["n"], k=len(c["units"])),
                                      t["sep"] + t["calls_auto"].format(n=c["auto"]) if c["auto"] else "",
                                      t["sep"] + t["calls_forks"].format(n=c["forks"]) if c["forks"] else "", t["sep"], c["file"]))
        for line in c["intro"]:
            print("    " + line)
        k = 0
        for s in c["steps"]:
            pad_ = "      " + "    " * (s["d"] + len(s["cases"]))
            if s["kind"] != "fn":
                print("%s%s %s%s" % (pad_ if s["kind"] == "branch" else pad_ + "  ", t["calls_" + s["kind"]], s["what"],
                                     ("：" if zh else ": ") + s["note"] if s["note"] else ""))
                for line in s["more"]:
                    print(pad_ + "     " + line)
                continue
            k += 1
            pad_ += "    " if s["cases"] else ""
            flags = [t["calls_flag_" + s["state"]]] if s["state"] != "ok" else []
            flags += [t["calls_flag_loose"]] if s["loose"] else []
            at = "%s:%d" % (s["file"], s["line"]) if s["file"] else ""
            if s["auto"]:   # filled in from the code: one line, nothing was written about it
                print("%s%d. %s  %s%s  %s" % (pad_, k, s["line1"], at, "  [%s]" % s["unitName"] if s["unitName"] else "",
                                             t["calls_filled"]))
                continue
            print("%s%d. %s  %s%s%s%s" % (pad_, k, s["line1"] or s["name"] + "()", at,
                                          "  [%s]" % s["unitName"] if s["unitName"] else "",
                                          "  " + t["calls_noted"] if book["fns"].get(s["key"], {}).get("note") else "",
                                          "  ! " + t["sep"].join(flags) if flags else ""))
            for line in ([s["what"]] if s["what"] else []) + s["more"]:
                print(pad_ + "   " + line)
            for way, arrow, values in ((t["run_in"], "←", s["ins"]), (t["run_out"], "→", s["outs"])):
                for v in values:
                    print("%s   %s  %s%s%s%s%s" % (pad_, way, v["name"], " (%s)" % v["type"] if v["type"] else "",
                                                   ("：" if zh else ": ") + v["what"] if v["what"] else "",
                                                   "  %s %s" % (arrow, v["via"]) if v["via"] else "",
                                                   "  ! " + t["calls_flag_name"] if v["lost"] else ""))
            untold = [p["name"] for p in s["params"] if not p["told"]]
            if untold and (s["ins"] or s["outs"]):
                print(pad_ + "   " + t["calls_untold"].format(x=("、" if zh else ", ").join(untold)))
            for cand in s["cands"]:
                print(pad_ + "   ? " + cand)
        if c["passed"]:
            print("      " + t["calls_passed"].format(n=c["passed"]))
    if any(c["in_list"] for c in chains):
        print(t["calls_in_list"].format(n=sum(1 for c in chains if c["in_list"]), file=args.calls_home))
    if book["notes"]:
        print(t["calls_notes"].format(n=book["notes"], file=book["notes_file"]))
    for x in book["lost"]:
        print("  ! " + t["calls_note_lost"].format(fn=x["fn"]))


def cmd_check(root, parts, t, args):
    if args.commit:
        rev = git(root, "rev-parse", "--short", args.commit).decode().strip()
        subject = git(root, "log", "-1", "--format=%s", args.commit).decode().strip()
        since = t["since_commit"].format(ref=rev, subject=subject)
        changed = sorted(zlist(git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "--root", args.commit)))
    else:
        base = args.since or "HEAD"
        since = t["since_ref"].format(ref=args.since) if args.since else t["since_head"]
        changed = dirty_files(root, base)

    groups, unmapped = {}, []
    for f in changed:
        part = owner(f, parts)
        if part:
            groups.setdefault(part.name, []).append(f)
        else:
            unmapped.append(f)
    by_name = {p.name: p for p in parts}
    rows = [{"part": p.name, "files": groups[p.name], "sensitive": by_name[p.name].sensitive}
            for p in parts if p.name in groups]
    result = {"since": since.strip(), "parts": rows, "unmapped": unmapped}
    windows = []
    if not args.commit and not args.since and changed and not getattr(args, "no_windows", False):
        _, windows = in_flight(root, parts)
        result["windows"] = [{"key": w["key"], "tool": w["tool"], "title": w["task"] or w["title"], "last": w["last"],
                              "unknown": w["unknown"], "guessed": w["guessed"],
                              "parts": grouped(w["rows"], parts)} for w in windows]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not changed:
        print(t["nothing"].format(since=since))
        return
    print(t["head"].format(since=since, parts=len(rows) + bool(unmapped), files=len(changed)))
    print()
    col = max([width(r["part"]) for r in rows] + [width(t["unmapped_changed"])]) + 2
    for r in rows:
        note = t["sensitive"].format(why=r["sensitive"]) if r["sensitive"] else ""
        print(("  " + pad(r["part"], col) + pad(t["files"].format(n=len(r["files"])), 12) + note).rstrip())
        if args.files:
            for f in r["files"]:
                print("      " + f)
    if unmapped:
        print("  " + pad(t["unmapped_changed"], col) + t["files"].format(n=len(unmapped)))
        for f in unmapped[:6]:
            print("      " + f)
    if len(windows) > 1:  # with one window there is nothing to tell apart
        print()
        print(t["by_window"])
        for w in windows:
            name = t["unknown_window"] if w["unknown"] else (w["task"] or w["title"] or w["tool"])
            about = [] if w["unknown"] else [w["tool"], t["last_at"].format(t=w["last"])]
            where = "  ".join("%s %d" % (g["name"] or t["unmapped_changed"], g["n"]) for g in grouped(w["rows"], parts))
            print("  %-3s%s%s" % (w["key"], name, "（%s）" % t["sep"].join(about) if about else ""))
            print("      " + where)


def history(root, parts, revs=None):
    """The last HISTORY commits, each with the parts it changed; or, given `revs`, exactly those commits,
    however far back they are. Outside code is not the project's work."""
    # -z gives file names as they are. Without it git quotes every name that is not plain ASCII
    # ("docs/\344\275\277...md"), and a file with a Chinese name would match no part.
    span = ["--no-walk=unsorted", "--stdin"] if revs is not None else ["-n", str(HISTORY), "--no-merges"]
    if revs is not None and not revs:
        return []
    raw = git(root, "log", "-z", *span, "--date=short", "--name-only", "--format=%x01%h%x02%ad%x02%ct%x02%s",
              stdin="\n".join(revs).encode() if revs is not None else None).decode("utf-8", "replace")
    commits = []
    for block in raw.split("\x01")[1:]:
        head, _, rest = block.partition("\0")
        rev, date, when, subject = (head.rstrip("\n").split("\x02", 3) + ["", "", ""])[:4]
        groups, subs = {}, set()
        for f in filter(None, (name.strip("\n") for name in rest.split("\0"))):
            unit = leaf(f, parts)
            if unit is not None and unit.outside:
                continue
            groups.setdefault(unit.top.name if unit else "", []).append(f)
            if unit is not None and unit.parent:
                subs.add(unit)
        if groups:
            commits.append({"hash": rev, "date": date, "when": int(when or 0), "subject": subject,
                            "groups": groups, "subs": subs})
    return commits


def drawn_times(root, list_path, parts):
    """When each unit's lines in the list were last changed: {unit: unix time}. A unit written
    or edited but not yet committed counts as drawn when the file was last saved."""
    saved = os.path.getmtime(list_path)
    out = subprocess.run(["git", "-C", root, "blame", "--line-porcelain", "--", list_path], capture_output=True)
    times = []
    if out.returncode == 0:
        when, pending = 0.0, False
        for line in out.stdout.decode("utf-8", "replace").splitlines():
            if line.startswith("committer-time "):
                when = float(line[15:])
            elif re.match(r"^[0-9a-f]{40} ", line):
                pending = line.startswith("0" * 40)
            elif line.startswith("\t"):
                times.append(saved if pending else when)
    drawn = {}
    for p in parts:
        for u in [p] + p.children:
            start = u.lines[0]
            end = u.children[0].lines[0] if u.children else u.lines[1]  # a part's own lines stop at its first room
            span = times[start:end]
            drawn[u] = max(span) if span else saved
    return drawn


def aging(root, list_path, parts, commits):
    """For every unit with a flow diagram: {unit: (date drawn, commits to its code since)}."""
    drawn = drawn_times(root, list_path, parts)
    listed = os.path.relpath(list_path, root).replace(os.sep, "/")
    out = {}
    for p in parts:
        for u in [p] + p.children:
            if not (u.flow and u.flow["nodes"]):
                continue
            since = 0
            for c in commits:
                if c["when"] <= drawn[u]:
                    continue
                if u.parent:
                    since += u in c["subs"]
                else:
                    since += any(f != listed for f in c["groups"].get(p.name, []))
            out[u] = (datetime.date.fromtimestamp(drawn[u]).isoformat(), since)
    return out


STALE = 8   # commits to a unit's code after its flow was drawn, before the check-up mentions it
SPANS = (7, 30, 90)   # the stretches of days the page can report changes over
KEPT = 60             # copies of the list kept beside the map page, for a list that is not committed


def list_before(root, list_path, when):
    """The text of the parts list as it stood at unix time `when`, and where that came from: its last
    committed version before then ("git"), or, for a list that was not committed by then, the newest copy
    kept beside the map page ("local"). ("", "new") when the list was first committed after `when`;
    ("", "short") when it was never committed and the copies kept do not reach back that far; ("", "")
    when it was never committed and no copy has been kept yet."""
    rel = os.path.relpath(list_path, root).replace(os.sep, "/")
    if not rel.startswith(".."):
        out = subprocess.run(["git", "-C", root, "log", "-1", "--format=%H", "--before=%d" % when, "--", rel],
                             capture_output=True)
        rev = out.stdout.decode().strip()
        if rev:
            text = subprocess.run(["git", "-C", root, "show", "%s:%s" % (rev, rel)], capture_output=True)
            if text.returncode == 0:
                return text.stdout.decode("utf-8", "replace"), "git"
    kept = sorted(glob.glob(os.path.join(os.path.dirname(state_path(root)), "lists", "*.md")))
    day = datetime.date.fromtimestamp(when).isoformat()
    before = [k for k in kept if os.path.basename(k)[:10] <= day]
    if before:
        return slurp(before[-1]), "local"
    first = subprocess.run(["git", "-C", root, "log", "--diff-filter=A", "--format=%ct", "--", rel],
                           capture_output=True).stdout.decode().split() if not rel.startswith("..") else []
    if first:
        return "", "new"
    return "", "short" if kept else ""


def keep_list(root, list_path):
    """Keeps today's copy of the list beside the map page when it differs from the last one kept. A list
    that lives uncommitted for weeks has no history in git; these copies are what "changed lately" is
    measured against then. They are local, like the page itself."""
    folder = os.path.join(os.path.dirname(state_path(root)), "lists")
    text = slurp(list_path)
    kept = sorted(glob.glob(os.path.join(folder, "*.md")))
    if not text or (kept and slurp(kept[-1]) == text):
        return
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, datetime.date.today().isoformat() + ".md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    for old in sorted(glob.glob(os.path.join(folder, "*.md")))[:-KEPT]:
        os.remove(old)


def drawing(flow):
    """What a diagram says, in a form two versions can be compared by."""
    if not (flow and flow["nodes"]):
        return None
    return ({n["name"] for n in flow["nodes"]}, {(e["a"], e["b"], e["label"], e["both"]) for e in flow["edges"]})


def list_units(parts, routes, top):
    """{label: (kind, drawing)} for everything on a list that has a name: wings, parts, rooms, routes, and
    the diagram of the whole project under the label ""."""
    out = {"": ("frame", drawing(top["frame"]))}
    for w in top["wings"]:
        out["# " + w.name] = ("wing", drawing(w.flow))
    for p in parts:
        out[p.name] = ("part", drawing(p.flow))
        for c in p.children:
            out[p.name + " / " + c.name] = ("room", drawing(c.flow))
    for r in routes:
        out["~ " + (r["title"] or "")] = ("route", drawing(r))
    return out


def changes(root, list_path, parts, routes, top, wiring, commits, tasks, days, records=()):
    """What changed in the last `days` days, measured: the list as it stands against the list as it stood
    then, the tasks' own histories, and the commits. Nothing here is written by anyone."""
    now = datetime.datetime.now().timestamp()
    since = now - days * 86400
    day = datetime.date.fromtimestamp(since).isoformat()
    out = {"days": days, "since": day, "base": "", "added": [], "removed": [], "redrawn": [], "tasks": [],
           "busy": [], "commits": 0, "short": False}
    text, out["base"] = list_before(root, list_path, since)
    ids = {unit_label(u): wiring.ids[u] for u in wiring.ids if not isinstance(u, Wing)}
    ids.update({"# " + u.name: wiring.ids[u] for u in wiring.ids if isinstance(u, Wing)})
    if text:
        then = list_units(*read_list(text))
        today = list_units(parts, routes, top)
        plain = lambda label: label[2:] if label[:2] in ("# ", "~ ") else label
        for label, (kind, drew) in today.items():
            if label not in then:
                if kind in ("part", "room", "wing"):
                    out["added"].append({"name": plain(label), "to": ids.get(label, ""), "kind": kind})
                elif kind == "route" or drew:
                    out["redrawn"].append({"name": plain(label), "to": "", "kind": kind, "plus": len(drew[0]) if drew else 0,
                                           "minus": 0, "first": True})
                continue
            was = then[label][1]
            if drew != was and drew:
                out["redrawn"].append({"name": plain(label), "to": ids.get(label, ""), "kind": kind,
                                       "plus": len(drew[0] - was[0]) if was else len(drew[0]),
                                       "minus": len(was[0] - drew[0]) if was else 0, "first": not was})
        out["removed"] = [{"name": plain(label), "kind": kind} for label, (kind, _) in then.items()
                          if label not in today and kind in ("part", "room", "wing")]
    for at, t in enumerate(tasks):
        story = [r for r in t["story"]]
        events = []
        for i, row in enumerate(story):
            if row["date"] < day:
                continue
            before = story[i - 1] if i else None
            events.append("done" if row["done"] and not (before and before["done"]) else
                          "more" if row["done"] else "again" if before and before["done"] else
                          "new" if before is None else "step")
        if not story and t["updated"] >= day:
            events.append("done" if t["done"] else "step")
        if events:  # one line a task: where the stretch left it
            out["tasks"].append({"i": at, "what": events[-1]})
    busy = collections.Counter()
    for c in commits:
        if c["when"] >= since:
            out["commits"] += 1
            for name, fs in c["groups"].items():  # the list and the task records are bookkeeping, not work on a part
                if name and any(not f.startswith(records) for f in fs):
                    busy[name] += 1
    out["busy"] = [{"name": name, "n": n} for name, n in busy.most_common(6)]
    out["short"] = len(commits) >= HISTORY and commits[-1]["when"] > since  # the window ends inside the span
    return out


# Recorded runs --------------------------------------------------------------
# A route says in words how one thing travels through the project. A recorded run is that journey measured
# once: for each step, the box of the route it belongs to, the file and line the code was at, how long it
# took, and the values that went in and came out. One JSON file per run under docs/runs/:
#   {"route": "<the route's title>", "name": "what was run", "recorded": "2026-11-14T10:02:11",
#    "commit": "c50d8d2", "dirty": false,
#    "steps": [{"box": "<a box of that route>", "fn": "name_of_the_function", "file": "src/x.py", "line": 41,
#               "ms": 0.4, "depth": 0, "in": {"name": value}, "out": {"name": value}, "note": "..."}]}
# The page shows the latest run of each route under it. The check-up compares the two: a box the route
# draws that the run never passed, a step the route does not have, a place that is no longer in the code.
# A run shows one path taken once. It cannot show that every path is like it.

def brief(value, limit=RUN_TEXT):
    """One value as one short line of text. A long list of numbers is cut to its length and its start."""
    if isinstance(value, str):
        text = value
    elif (isinstance(value, list) and len(value) > RUN_HEAD
          and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value)):
        text = "%d × [%s, …]" % (len(value), ", ".join(json.dumps(x) for x in value[:RUN_HEAD]))
    else:
        text = json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def run_values(raw):
    """What went into a step, or came out: [{name, value}]. Written as {"name": value}."""
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, list):
        pairs = [(x.get("name", ""), x.get("value")) for x in raw if isinstance(x, dict)]
    else:
        pairs = [] if raw is None else [("", raw)]
    return [{"name": str(k), "value": brief(v)} for k, v in pairs[:RUN_VALUES]]


def line_count(path, seen={}):
    if path not in seen:
        try:
            with open(path, "rb") as fh:
                seen[path] = fh.read(SOURCE_MAX + 1).count(b"\n") + 1
        except OSError:
            seen[path] = 0
    return seen[path]


def commits_since(root, files, commit, when):
    """How often these files were committed to after a run was recorded: counted from the commit the run
    names, or, when the repository does not have that commit, from the time the run was recorded."""
    if not files:
        return 0
    spans = ([[commit + "..HEAD"]] if COMMIT_RE.match(commit) else []) + \
            ([["--since=" + when, "HEAD"]] if WHEN_RE.match(when) else [])
    for span in spans:
        out = subprocess.run(["git", "-C", root, "rev-list", "--count", *span, "--", *files],
                             capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip().isdigit():
            return int(out.stdout.strip())
    return 0


def read_run(root, raw, route, parts, top):
    """One run, checked against the route it says it followed and against the code as it is now."""
    units = {}
    for u in [x for p in parts for x in [p] + p.children] + list(top["wings"]):
        units.setdefault(u.name, u)
    on_route = {n["name"] for n in route["nodes"]}
    steps, hit = [], set()
    listed = [s for s in raw["steps"] if isinstance(s, dict)]
    for s in listed[:RUN_STEPS]:
        box = str(s.get("box") or "").strip()
        path = str(s.get("file") or "").strip().replace("\\", "/")
        if posixpath.isabs(path):
            path = os.path.relpath(path, root).replace(os.sep, "/")
        path = posixpath.normpath(path) if path else ""
        line = s.get("line") if isinstance(s.get("line"), int) and s.get("line") > 0 else 0
        ms = s.get("ms") if isinstance(s.get("ms"), (int, float)) and not isinstance(s.get("ms"), bool) else None
        depth = s.get("depth") if isinstance(s.get("depth"), int) else 0
        inside = bool(path) and not path.startswith("../") and path != ".."
        full = os.path.join(root, path) if inside else ""
        lost = bool(path) and (not inside or not os.path.isfile(full) or (line and line > line_count(full)))
        astray = ""
        if path and not lost and box in units:
            home = leaf(path, parts)
            if home is not None and not within(units[box], home):
                astray = unit_label(home)
        hit.add(box)
        steps.append({"box": box, "fn": brief(str(s.get("fn") or ""), 80), "file": path, "line": line, "ms": ms,
                      "depth": max(0, min(6, depth)),
                      "ins": run_values(s.get("in")), "outs": run_values(s.get("out")),
                      "note": brief(str(s.get("note") or "")), "known": box in on_route, "lost": lost,
                      "astray": astray})
    wired = {name for e in route["edges"] for name in (e["a"], e["b"])}
    # A person, and a service outside the project, are on the route but nothing of theirs can be recorded.
    missed = [n["name"] for n in route["nodes"] if n["name"] in wired and not n["ext"] and n["icon"] != "user"
              and n["name"] not in hit]
    total = raw.get("ms") if isinstance(raw.get("ms"), (int, float)) and not isinstance(raw.get("ms"), bool) else None
    if total is None and any(s["ms"] is not None for s in steps):
        total = round(sum(s["ms"] for s in steps if s["ms"] is not None and s["depth"] == 0), 3)
    when = str(raw.get("recorded") or "").strip()
    commit = str(raw.get("commit") or "").strip().lower()
    dropped = raw.get("dropped") if isinstance(raw.get("dropped"), int) else 0
    return {"route": route["title"], "name": brief(str(raw.get("name") or ""), 80),
            "recorded": when.replace("T", " ")[:16] if WHEN_RE.match(when) else "",
            "commit": commit[:10] if COMMIT_RE.match(commit) else "", "dirty": raw.get("dirty") is True,
            "command": brief(str(raw.get("command") or ""), 160), "ms": total, "steps": steps, "missed": missed,
            "dropped": dropped + max(0, len(listed) - RUN_STEPS),
            "aged": commits_since(root, sorted({s["file"] for s in steps if s["file"] and not s["lost"]}),
                                  commit, when)}


def load_runs(root, where, routes, parts, top):
    """Returns (runs, loose): for each route its latest recorded run, or None, in the order of `routes`; and
    the files in the runs folder that cannot be used, each with the reason."""
    base = where if os.path.isabs(where) else os.path.join(root, where)
    by_title = {r["title"]: r for r in routes}
    found, loose = collections.defaultdict(list), []
    for path in sorted(glob.glob(os.path.join(base, "*.json"))):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            loose.append({"file": rel, "why": "json", "route": ""})
            continue
        if not isinstance(raw, dict) or not isinstance(raw.get("steps"), list):
            loose.append({"file": rel, "why": "shape", "route": ""})
            continue
        title = str(raw.get("route") or "").strip()
        if title not in by_title:
            loose.append({"file": rel, "why": "route", "route": title})
            continue
        found[title].append((str(raw.get("recorded") or ""), os.path.getmtime(path), rel, raw))
    runs = []
    for r in routes:
        mine = sorted(found.get(r["title"], []), key=lambda x: x[:2], reverse=True)
        if not mine:
            runs.append(None)
            continue
        run = read_run(root, mine[0][3], r, parts, top)
        runs.append(dict(run, file=mine[0][2], earlier=len(mine) - 1))
    return runs, loose


def run_problems(runs, loose):
    """Where a recorded run and its route, or the code, do not agree."""
    out = {"missed": [], "strange": [], "lost": [], "astray": [], "aged": [], "unused": loose}
    for run in filter(None, runs):
        out["missed"] += [{"route": run["route"], "box": b} for b in run["missed"]]
        seen = set()
        for s in run["steps"]:
            row = {"route": run["route"], "box": s["box"], "file": s["file"], "line": s["line"]}
            if not s["known"] and ("box", s["box"]) not in seen:
                seen.add(("box", s["box"]))
                out["strange"].append({"route": run["route"], "box": s["box"]})
            if (s["lost"] or s["astray"]) and (s["box"], s["file"], s["line"]) not in seen:
                seen.add((s["box"], s["file"], s["line"]))
                if s["lost"]:
                    out["lost"].append(row)
                else:
                    out["astray"].append(dict(row, unit=s["astray"]))
        if run["aged"]:
            out["aged"].append({"route": run["route"], "recorded": run["recorded"], "changes_since": run["aged"]})
    return out


def ms_text(ms):
    if ms is None:
        return ""
    if ms < 0.005:
        return "<0.01 ms"
    if ms >= 1000:
        return "%.2f s" % (ms / 1000)
    return ("%.2f ms" if ms < 1 else "%.1f ms" if ms < 100 else "%.0f ms") % ms


def cmd_runs(root, parts, t, args):
    """The recorded runs: for each route its latest run, step by step."""
    runs, loose = load_runs(root, args.runs, args.routes, parts, args.top)
    if args.json:
        print(json.dumps({"folder": args.runs, "runs": [r for r in runs if r],
                          "routes_without": [x["title"] for x, r in zip(args.routes, runs) if not r],
                          "unused": loose}, ensure_ascii=False, indent=2))
        return
    have = [r for r in runs if r]
    print(t["runs_head"].format(n=len(have)) if have else t["runs_none"].format(dir=args.runs))
    for run in have:
        notes = [run["name"]] if run["name"] else []
        notes += [t["run_at"].format(d=run["recorded"])] if run["recorded"] else []
        notes += [t["run_commit"].format(c=run["commit"])] if run["commit"] else []
        notes += [t["run_steps"].format(n=len(run["steps"]))]
        notes += [t["run_ms"].format(t=ms_text(run["ms"]))] if run["ms"] is not None else []
        notes += [t["run_dirty"]] if run["dirty"] else []
        print("  %s  [%s]" % (run["route"], t["sep"].join(notes)))
        for k, s in enumerate(run["steps"], 1):
            flags = [t["run_flag_strange"]] if not s["known"] else []
            flags += [t["run_flag_lost"]] if s["lost"] else []
            flags += [t["run_flag_astray"].format(u=s["astray"])] if s["astray"] else []
            where = "%s:%d" % (s["file"], s["line"]) if s["line"] else s["file"]
            where = "  ".join(x for x in (s["fn"] + "()" if s["fn"] else "", where) if x)
            print("      %s%d. %s  %s  %s%s" % ("  " * s["depth"], k, s["box"], where, ms_text(s["ms"]),
                                              "  ! " + t["sep"].join(flags) if flags else ""))
            for way, values in ((t["run_in"], s["ins"]), (t["run_out"], s["outs"])):
                for v in values:
                    print("          %s%s  %s = %s" % ("  " * s["depth"], way, v["name"], v["value"]))
        if run["missed"]:
            print("      ! " + t["run_missed"].format(x=("、" if t is TEXT["zh"] else ", ").join(run["missed"])))
        if run["aged"]:
            print("      ! " + t["run_aged"].format(n=run["aged"]))
    bare = [x["title"] for x, r in zip(args.routes, runs) if not r]
    if bare:
        print(t["run_bare"].format(x=("、" if t is TEXT["zh"] else ", ").join(bare)))
    for x in loose:
        print("  ! %s%s%s" % (x["file"], "：" if t is TEXT["zh"] else ": ", t["run_why_" + x["why"]].format(route=x["route"])))


def cmd_doctor(root, parts, t, args):
    """What a machine can tell about the list: out of date, or miswritten. It reports and stops nothing."""
    files = zlist(git(root, "ls-files", "-z"))
    listed = os.path.relpath(args.list_path, root).replace(os.sep, "/")
    _, unmapped = tally(files, parts)
    units = [u for p in parts for u in [p] + p.children]
    label = lambda u: (u.parent.name + " / " if u.parent else "") + u.name
    def on_disk(pat):  # a file git does not track (a local secrets file, say) is not a stale path
        return bool(glob.glob(os.path.join(root, pat.rstrip("/")), recursive=True))
    dead = [(label(u), pat) for u in units for pat, match, _ in u.patterns
            if not any(match(f) for f in files) and not on_disk(pat)]
    names = {u.name for u in units}
    near = []
    flows = [(label(u), u.flow) for u in units if u.flow] + [(t["route"] + " " + (r["title"] or "?"), r) for r in args.routes]
    for where, flow in flows:
        for node in flow["nodes"]:
            if node["name"] in names or node["ext"] or len(node["name"]) < 3:
                continue
            close = difflib.get_close_matches(node["name"], names, n=1, cutoff=0.8)
            if close:
                near.append({"where": where, "box": node["name"], "unit": close[0]})
    level = [p.name for p in parts if p.children and p.flow and p.flow["nodes"]
             and not ({n["name"] for n in p.flow["nodes"]} & {c.name for c in p.children})]
    links, langs = code_links(root, files, parts)
    wiring = Wiring(parts, args.routes, args.top)
    flows += [(t["frame"], args.top["frame"])] if args.top["frame"] else []
    flows += [(w.name, w.flow) for w in args.top["wings"] if w.flow]
    if langs:
        wiring.loose(lifted(links, "top"))
    loose = [{"route": w["where"] or t["frame"], "a": w["edge"]["a"], "b": w["edge"]["b"]}
             for w in wiring.wires if w["edge"].get("loose")]
    wires = wiring.problems()
    gone = wiring.code_gone(root, files, listed)
    old = sorted(((label(u), d, n) for u, (d, n) in aging(root, args.list_path, parts, history(root, parts)).items()
                  if n >= STALE), key=lambda x: -x[2])
    bare = [label(u) for u in units if not u.outside and not (u.flow and u.flow["nodes"])]
    missed = mark_misses([x for x in tasks_shown(root, args.tasks, parts, [])[0] if not x["old"]], t)
    runs, runs_loose = load_runs(root, args.runs, args.routes, parts, args.top)
    ran = run_problems(runs, runs_loose)
    plain = [unit_label(u) for u in list(args.top["wings"]) + units if not u.explain and not (isinstance(u, Part) and u.outside)]
    chains, book = load_chains(root, files, parts, args.routes, args.top, wiring, runs, args.calls_path, listed,
                               source=False)
    chained = dict(chain_problems(chains), notes_lost=book["lost"])
    said = words_now(root, parts, args)
    if not said["have"]:
        said = dict(said, missing=[])      # no translations were ever started: nothing to report
    if args.json:
        print(json.dumps({"list": listed, "dead_paths": [{"unit": u, "path": p} for u, p in dead],
                          "unmapped": len(unmapped), "near_names": near, "wrong_level": level, "unbacked": loose,
                          "wiring": dict(wires, code_gone=gone),
                          "stale": [{"unit": u, "drawn": d, "changes_since": n} for u, d, n in old],
                          "undrawn": bare, "unexplained": plain, "marks_missed": missed, "runs": ran,
                          "call_chains": chained,
                          "translations": {k: v for k, v in said.items() if k != "words"}},
                         ensure_ascii=False, indent=2))
        return
    zh = t is TEXT["zh"]
    join = "；" if zh else "; "
    print(t["doctor_head"].format(path=listed))
    found = False

    def section(title, rows):
        nonlocal found
        if rows:
            found = True
            print("  " + title.format(n=len(rows)))
            for row in rows[:12]:
                print("      " + row)
            if len(rows) > 12:
                print("      …")
    section(t["doctor_paths"], ["%s  `%s`" % x for x in dead])
    if unmapped:
        found = True
        print("  " + t["doctor_unmapped"].format(n=len(unmapped)))
    section(t["doctor_names"], [t["doctor_name"].format(**x) for x in near])
    section(t["doctor_level"], level)
    section(t["doctor_loose"], ["%s → %s（%s）" % (x["a"], x["b"], x["route"]) if zh else
                                "%s -> %s (%s)" % (x["a"], x["b"], x["route"]) for x in loose])
    # The wiring: do the levels agree with each other?
    arrow = "%s → %s" if zh else "%s -> %s"
    here = lambda where: where or t["frame"]
    if wires["no_frame"]:
        found = True
        print("  " + t["doctor_frame"].format(level=t["level_wings" if args.top["wings"] else "level_parts"]))
    section(t["doctor_wings"], wires["wings_bare"])
    homes = collections.OrderedDict()
    for x in wires["orphans"]:
        homes.setdefault(here(x["on"]), []).append(x["unit"].split(" / ")[-1])
    if homes:
        found = True
        print("  " + t["doctor_orphans"].format(n=len(wires["orphans"])))
        for where, names in homes.items():
            print("      %s%s%s" % (where, "：" if zh else ": ", ("、" if zh else ", ").join(names)))
    section(t["doctor_shelf"], [t["doctor_shelf_row"].format(on=here(x["on"]), box=x["box"]) for x in wires["shelf"]])
    section(t["doctor_open_in"], [t["doctor_open_in_row"].format(unit=x["unit"], other=x["other"],
            label=(t["doctor_said"].format(x=x["label"]) if x["label"] else "")) for x in wires["open_in"]])
    section(t["doctor_open_out"], [t["doctor_open_out_row"].format(**x) for x in wires["open_out"]])
    section(t["doctor_routes_off"], [(arrow + ("（%s）" if zh else " (%s)")) % (x["a"], x["b"], x["route"])
                                     for x in wires["routes_off"]])
    section(t["doctor_pieces"], [t["doctor_pieces_row"].format(on=here(x["on"]), n=x["n"]) for x in wires["pieces"]])
    section(t["doctor_unlabeled"], [here(x["on"]) + ("：" if zh else ": ") + arrow % (x["a"], x["b"])
                                    for x in wires["unlabeled"]])
    section(t["doctor_code"], [t["doctor_code_row"].format(on=here(x["on"]), arrow=arrow % (x["a"], x["b"]),
                                                           name=x["name"], unit=x["unit"]) for x in gone])
    section(t["doctor_stale"], [t["doctor_stale_row"].format(name=u, date=d, n=n) for u, d, n in old])
    section(t["doctor_marks"], missed)
    # The recorded runs: does what was measured agree with what was drawn, and with the code as it is now?
    colon = "：" if zh else ": "
    section(t["doctor_run_missed"], [x["route"] + colon + x["box"] for x in ran["missed"]])
    section(t["doctor_run_strange"], [x["route"] + colon + x["box"] for x in ran["strange"]])
    section(t["doctor_run_lost"], ["%s%s%s → %s%s" % (x["route"], colon, x["box"], x["file"],
                                                        ":%d" % x["line"] if x["line"] else "") for x in ran["lost"]])
    section(t["doctor_run_astray"], [t["doctor_run_astray_row"].format(**x) for x in ran["astray"]])
    section(t["doctor_run_aged"], [t["doctor_run_aged_row"].format(route=x["route"], date=x["recorded"] or "?",
                                                                   n=x["changes_since"]) for x in ran["aged"]])
    section(t["doctor_run_loose"], [x["file"] + colon + t["run_why_" + x["why"]].format(route=x["route"])
                                    for x in ran["unused"]])
    # The call chains: does the code have these functions, and does each call the one written under it?
    section(t["doctor_calls_lost"], ["%s%s%s()" % (x["on"], colon, x["fn"]) for x in chained["lost"]])
    section(t["doctor_calls_many"], ["%s%s%s()  ← %s" % (x["on"], colon, x["fn"], " / ".join(x["candidates"]))
                                     for x in chained["many"]])
    section(t["doctor_calls_loose"], ["%s%s%s() → %s()" % (x["on"], colon, x["caller"], x["fn"]) for x in chained["loose"]])
    section(t["doctor_calls_names"], [t["doctor_calls_names_row"].format(**x) for x in chained["names"]])
    section(t["doctor_calls_untold"], ["%s%s%s()" % (x["on"], colon, x["fn"]) for x in chained["untold"]])
    section(t["doctor_calls_bare"], ["%s%s%s()" % (x["on"], colon, x["fn"]) for x in chained["bare"]])
    section(t["doctor_calls_forks"], [x["on"] + colon + x["branch"] for x in chained["forks"]])
    section(t["doctor_notes_lost"], [x["fn"] for x in chained["notes_lost"]])
    section(t["words_stale"], ["%s%s%s" % (x["file"], colon, x["text"]) for x in said["stale"]])
    section(t["words_clash"], ["%s / %s → %s" % (x["name"], x["same_as"], x["translation"]) for x in said["clash"]])
    if not found:
        print("  " + t["doctor_ok"])
    if bare:
        print("  " + t["doctor_bare"].format(n=len(bare)))
    if plain:
        print("  " + t["doctor_plain"].format(n=len(plain)))
    if said["missing"]:
        print("  " + t["doctor_words_missing"].format(n=len(said["missing"]), lang=LANG_NAMES["zh" if zh else "en"][said["lang"]]))
    print(t["doctor_limit"])


def mark_misses(tasks, t):
    """Marks that the page cannot draw where the agent meant: a part or room the list does not have, or a
    new or changed box that is not in that unit's diagram."""
    rows = []
    for x in tasks:
        for m in x["marks"]:
            if not m["unit"]:
                rows.append(t["doctor_mark_unit"].format(task=x["name"], name=m["room"] or m["part"]))
            elif m["box"] and m["kind"] != "gone" and not m["drawn"]:
                rows.append(t["doctor_mark_box"].format(task=x["name"], unit=m["unit"], box=m["box"]))
    return rows


def cmd_tasks(root, parts, t, args):
    """The tasks in progress and the ones finished lately: the lines the agent wrote for people in each
    dossier, and the parts touched."""
    tasks, left_out = tasks_shown(root, args.tasks, parts, history(root, parts), args.list_path)
    if args.json:
        print(json.dumps({"tasks": [{"folder": x["id"], "name": x["name"], "finished": x["done"],
                                     "for_people": x["plain"], "now": x["now"],
                                     "needs": x["needs"], "next": x["next"], "done": x["made"], "try": x["try"],
                                     "not_yet": x["left"], "marks": x["marks"], "updated": x["updated"],
                                     "parts": x["rooms"], "finished_long_ago": x["old"],
                                     "changed_since": x["after"], "times_finished": x["times"],
                                     "open_again": x["again"], "story": x["story"],
                                     "tried": x["tried"]} for x in tasks],
                          "not_listed": left_out,
                          "marks_missed": mark_misses([x for x in tasks if not x["old"]], t)},
                         ensure_ascii=False, indent=2))
        return
    older = [x for x in tasks if x["old"]]
    tasks = [x for x in tasks if not x["old"]]
    doing, done = [x for x in tasks if not x["done"]], [x for x in tasks if x["done"]]
    print(t["tasks_head"].format(n=len(doing)) if doing else t["tasks_none"])
    for x in doing + done:
        if done and x is done[0]:
            print(t["tasks_done_head"].format(n=len(done)))
        notes = [t["task_updated"].format(d=x["updated"] or "?")]
        notes += [t["task_again"]] if x["again"] else []
        notes += [t["task_times"].format(n=x["times"])] if x["done"] and x["times"] > 1 else []
        notes += [t["task_after"].format(n=x["after"])] if x["done"] and x["after"] else []
        print("  %s  [%s]" % (x["name"], t["sep"].join(notes)))
        said = [t["task_now"].format(x=x["now"])] if x["now"] else []
        said += [t["task_needs"].format(x=need) for need in x["needs"]]
        said += [t["task_next"].format(x=x["next"])] if x["next"] else []
        said += [t["task_made"].format(x=line) for line in x["made"]]
        said += [t["task_try"].format(x=x["try"])] if x["try"] else []
        if x["tried"]:
            said.append(t["task_tried_ok" if x["tried"]["ok"] else "task_tried_no"].format(d=x["tried"]["date"]) + (
                t["task_tried_again"].format(n=x["tried"]["changed"]) if x["tried"]["ok"] and x["tried"]["changed"] else ""))
        said += [t["task_left"].format(x=line) for line in x["left"]]
        if x["marks"]:
            said.append(t["task_marks"].format(x="  ".join(
                "%s %s" % (t["mark_" + m["kind"]], " / ".join(k for k in (m["unit"] or m["part"], m["box"]) if k))
                for m in x["marks"])))
        for line in said or [t["task_bare"]]:
            print("      " + line)
        if x["rooms"]:
            print("      " + t["task_rooms"].format(x="  ".join("%s %d" % (r["name"] or t["unmapped_changed"], r["n"])
                                                                for r in x["rooms"])))
        print("      " + t["task_folder"].format(x=posixpath.join(x["rel"] or args.tasks, x["home"])))
    if older:
        print(t["tasks_older_head"].format(n=len(older)))
        for x in older:
            print("  %s  [%s]%s" % (x["name"], t["task_updated"].format(d=x["updated"] or "?"),
                                   "  " + t["task_after"].format(n=x["after"]) if x["after"] else ""))
    if left_out:
        print(t["tasks_old"].format(n=left_out))
    for row in mark_misses(tasks, t):
        print("  ! " + row)


def tried_rank(x):
    """What needs the reader first: broken, then worth trying again, then never tried, then fine."""
    k = x["tried"]
    return 2 if not k else 0 if not k["ok"] else 1 if k["changed"] else 3


def cmd_tried(root, parts, t, args):
    """What the project can do now, and whether the reader tried it: every task that says what it made,
    with how to try it and how its latest try stands. With a task and a word, notes a try."""
    commits = history(root, parts)
    tasks = [x for x in tasks_shown(root, args.tasks, parts, commits, args.list_path)[0] if x["made"]]
    if args.task:
        said = (args.verdict or "").strip().lower()
        if said and said not in ("能用", "不能用", "works", "broken", "ok", "no"):
            raise SystemExit("bearings: " + t["tried_word"])
        want = args.task.strip().strip("“”\"'")
        hit = [x for x in tasks if want in (x["name"], x["id"])] or [x for x in tasks if want.lower() in x["name"].lower()]
        if len(hit) != 1:
            raise SystemExit("bearings: " + t["tried_which"].format(name=want, names="、".join(x["name"] for x in tasks) or "-"))
    if args.task and not said:   # a task and no word: how that one stands
        tasks = hit
    elif args.task:
        ok = said in ("能用", "works", "ok")
        _, windows = in_flight(root, parts, look=not args.no_windows, everywhere=True)
        kept = write_tried(root, args.list_path, hit[0], task_scope(root, hit[0], windows), ok, " ".join(args.note),
                           language(parts) == "zh")
        print(t["tried_saved"].format(name=hit[0]["name"], d=kept["date"], word=t["tried_ok_word" if ok else "tried_no_word"],
                                      file=os.path.relpath(tried_path(args.list_path), root).replace(os.sep, "/")))
        return
    if args.json:
        print(json.dumps({"can": [{"folder": x["id"], "name": x["name"], "finished": x["done"], "made": x["made"],
                                   "try": x["try"], "tried": x["tried"]} for x in sorted(tasks, key=tried_rank)]},
                         ensure_ascii=False, indent=2))
        return
    if not tasks:
        print(t["tried_none"])
        return
    print(t["tried_head"].format(n=len(tasks)))
    for x in sorted(tasks, key=tried_rank):
        k = x["tried"]
        state = t["tried_new"] if not k else t["tried_no"].format(d=k["date"]) if not k["ok"] else \
            t["tried_again"].format(d=k["date"], n=k["changed"]) if k["changed"] else t["tried_ok"].format(d=k["date"])
        print("  %s  [%s]" % (x["name"], state))
        for line in x["made"][:2]:
            print("      " + line)
        if x["try"]:
            print("      " + t["tried_how"].format(x=x["try"]))
        if k and k["note"]:
            print("      " + t["tried_note"].format(x=k["note"]))


def cmd_windows(root, parts, t, args):
    """Every window at work in this project: how it stands, what it was last asked, what it has changed and
    committed, and where two windows get in each other's way."""
    rows, windows = in_flight(root, parts, everywhere=True)
    window_commits(windows, history(root, parts))
    listed = os.path.relpath(args.list_path, root).replace(os.sep, "/")
    tasks_rel = os.path.relpath(args.tasks if os.path.isabs(args.tasks) else os.path.join(root, args.tasks), root)
    hits = clashes(rows, windows, (listed, tasks_rel.replace(os.sep, "/") + "/"))
    known = [w for w in windows if not w["unknown"]]
    if args.json:
        print(json.dumps({"windows": [{"key": w["key"], "tool": w["tool"], "name": w["task"] or w["title"],
                                       "state": w["state"], "last_active": w["last"], "last_asked": w["said"],
                                       "task": w["dossier"], "uncommitted": [{"part": g["name"], "files": g["n"]}
                                                                              for g in grouped(w["rows"], parts)],
                                       "commits": [c["hash"] for c in w["commits"]]} for w in known],
                          "no_window_on_record": sum(len(w["rows"]) for w in windows if w["unknown"]),
                          "clashes": hits}, ensure_ascii=False, indent=2))
        return
    if not known:
        print(t["windows_none"])
        return
    print(t["windows_head"].format(n=len(known)))
    for w in known:
        print("  %s  %s  [%s%s%s%s%s]" % (w["key"], w["task"] or w["title"] or w["tool"], w["tool"], t["sep"],
                                         t["st_" + w["state"]], t["sep"], t["last_at"].format(t=w["last"])))
        if w["said"] and w["said"] != (w["task"] or w["title"]):
            print("      " + t["win_said"].format(x=w["said"]))
        groups = grouped(w["rows"], parts)
        print("      " + (t["sep"].join("%s %d" % (g["name"] or t["unmapped_changed"], g["n"]) for g in groups)
                          if groups else t["win_clean"])
              + ((t["sep"] + t["win_commits"].format(n=len(w["commits"]))) if w["commits"] else ""))
    loose = sum(len(w["rows"]) for w in windows if w["unknown"])
    if loose:
        print("  ?  %s  %s" % (t["unknown_window"], t["files"].format(n=loose)))
    if not hits:
        print(t["clash_none"])
        return
    print(t["clash_head"].format(n=len(hits)))
    for c in hits:
        print("  " + t["clash_" + c["kind"]].format(who="、".join(c["who"]) if t is TEXT["zh"] else ", ".join(c["who"]),
                                                    file=c["file"], part=c["part"] or t["unmapped_changed"],
                                                    where="、".join(c["where"])))


# Two languages --------------------------------------------------------------------
# The list is written in one language, Chinese or English, and so are the call chains. A file beside each gives
# the other language: parts.zh.md beside an English parts.md (parts.en.md beside a Chinese one), and calls.zh.md
# or calls.en.md beside the calls file. It is a plain list of pairs: a line of the original text exactly as the
# list has it, and under it a line that starts with ":" and holds the translation. The list stays the one source of
# the picture: paths, diagrams and names are read from it alone, and a text with no translation is shown as
# written. The page carries both and the reader switches between them.
LANG_NAMES = {"zh": {"zh": "中文", "en": "英文"}, "en": {"zh": "Chinese", "en": "English"}}
WORDS_SKIP = frozenset((
    "icon", "to", "dir", "kind", "state", "key", "file", "sig", "line1", "returns", "doc", "type", "code", "paths",
    "files", "hash", "date", "subject", "fn", "caller", "cands", "ex", "fns", "save", "project", "lang", "generated",
    "list", "callsFile", "notesFile", "measured", "since", "base", "drawn", "last", "said", "tool", "i18n", "params", "tried",
    "in", "out", "ran"))
WORDS_DERIVED = frozenset(("ports", "together", "inner", "unit", "units", "unitName", "group", "parent"))
WORDS_NAMES = frozenset(("name", "a", "b", "title"))
WORDS_FIRST = ("name", "title", "what", "explain", "intro", "sensitive", "external", "rules", "nodes", "edges")


def other_lang(lang):
    return "en" if lang == "zh" else "zh"


def words_path(path, lang):
    stem, ext = os.path.splitext(path)
    return "%s.%s%s" % (stem, lang, ext or ".md")


def load_words(paths):
    """The translations: ({original: translation}, [(file, original, translation)] as written). A line that
    starts with "#" is a heading for the people who keep the file and is not read, nor is an HTML comment."""
    words, rows = {}, []
    for path in paths:
        if not os.path.isfile(path):
            continue
        src = None
        for line in re.sub(r"<!--.*?-->", "", open(path, encoding="utf-8").read(), flags=re.S).split("\n"):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            if text[0] in ":：":
                if src is not None:
                    rows.append((path, src, text[1:].strip()))
                    if text[1:].strip():
                        words.setdefault(src, text[1:].strip())
                src = None
                continue
            if src is not None:
                rows.append((path, src, ""))
            src = text
        if src is not None:
            rows.append((path, src, ""))
    return words, rows


def words_of(data):
    """Every text on the page that a person wrote in the list or the calls file, once each, in reading order:
    [(heading it stands under, text, whether it is a name, "list" or "calls")]. The page's own rule for what it
    translates is the same walk over the same keys (WORDS_SKIP goes to the page with the translations); a
    name that stands in several places is one text, so every place changes together."""
    out, seen = [], set()

    def walk(v, key, owner, group, home):
        if isinstance(v, str):
            if key == "name" and (owner.get("kind") is not None or "type" in owner or "via" in owner):
                return   # a function, a parameter: the code's own name
            text = v.strip()
            if text and text not in seen:
                seen.add(text)
                out.append((group, text, key in WORDS_NAMES, home))
        elif isinstance(v, list):
            for x in v:
                walk(x, key, owner, group, home)
        elif isinstance(v, dict):
            keys = sorted(v, key=lambda k: WORDS_FIRST.index(k) if k in WORDS_FIRST else len(WORDS_FIRST))
            for k in keys:
                if k not in WORDS_SKIP and k not in WORDS_DERIVED:
                    walk(v[k], k, v, group, home)

    walk(data.get("explain") or [], "explain", {}, "", "list")
    walk(data.get("frame") or {}, "frame", {}, "", "list")
    for r in data.get("routes") or []:
        walk(r, "route", {}, r.get("title") or "", "list")
    in_wing = set()
    for w in data.get("wings") or []:
        walk({k: w[k] for k in w if k != "parts"}, "wing", {}, w["name"], "list")
        for i in w["parts"]:
            in_wing.add(i)
            walk(data["parts"][i], "part", {}, data["parts"][i]["name"], "list")
    for i, part in enumerate(data.get("parts") or []):
        if i not in in_wing:
            walk(part, "part", {}, part["name"], "list")
    for c in data.get("chains") or []:
        walk(c, "chain", {}, c.get("title") or "", "calls")
    return out


def words_state(root, args, lang, data):
    """What the page and the check-up need to know about the other language: the translations that can be
    used, the texts that have none, the entries whose original is gone, and the names that would collide."""
    other = other_lang(lang)
    calls_home = os.path.join(root, args.calls_home)
    paths = [words_path(args.list_path, other), words_path(calls_home, other)]
    words, rows = load_words(paths)
    wanted = words_of(data)
    known = {text for _, text, _, _ in wanted}
    names = {text for _, text, is_name, _ in wanted if is_name}
    clash, taken = [], {}
    for _, text, is_name, _ in wanted:      # two boxes are told apart by their names, in either language
        tr = words.get(text)
        if not is_name or not tr:
            continue
        twin = taken.get(tr) or (tr if tr in names and tr != text and words.get(tr, tr) == tr else None)
        if twin and twin != text:
            clash.append({"name": text, "same_as": twin, "translation": tr})
        else:
            taken[tr] = text
    for x in clash:
        words.pop(x["name"], None)
    rel = lambda path: os.path.relpath(path, root).replace(os.sep, "/")
    return {"lang": other, "files": [rel(x) for x in paths], "have": [rel(x) for x in paths if os.path.isfile(x)],
            "words": words, "total": len(wanted),
            "missing": [{"under": g, "text": text, "in": home} for g, text, _, home in wanted if text not in words],
            "stale": [{"file": rel(f), "text": src} for f, src, _ in rows if src not in known],
            "clash": clash}


def words_now(root, parts, args):
    """The same, for a command that does not write the page."""
    quiet = dict(vars(args), no_links=True, no_windows=True, no_source=True, fragment=True)
    return web_page(root, parts, TEXT[language(parts)], argparse.Namespace(**quiet))[1]["words"]


def cmd_words(root, parts, t, args):
    """The other language of the page: how much of the list has a translation, what is still missing, and
    which translations no longer match the list. With --draft: the missing entries, ready to be filled in."""
    state = words_now(root, parts, args)
    if args.json:
        print(json.dumps({k: v for k, v in state.items() if k != "words"}, ensure_ascii=False, indent=2))
        return
    lang = LANG_NAMES["zh" if t is TEXT["zh"] else "en"][state["lang"]]
    if args.draft:
        for home, path in zip(("list", "calls"), state["files"]):
            rows = [x for x in state["missing"] if x["in"] == home]
            if not rows:
                continue
            print("# → %s\n" % path)
            under = None
            for x in rows:
                if x["under"] != under:
                    under = x["under"]
                    if under:
                        print("## %s\n" % under)
                print("%s\n: \n" % x["text"])
        return
    if not state["have"]:
        print(t["words_no_file"].format(lang=lang, file=state["files"][0], calls=state["files"][1]))
    print(t["words_head"].format(lang=lang, done=state["total"] - len(state["missing"]), total=state["total"],
                                 files=" / ".join(state["have"] or state["files"])))
    if state["missing"]:
        print(t["words_missing"].format(n=len(state["missing"])))
        for x in state["missing"][:40]:
            print("    %s%s" % ("[%s] " % x["under"] if x["under"] else "", x["text"]))
        if len(state["missing"]) > 40:
            print("    …")
    elif state["have"]:
        print(t["words_all"])
    if state["stale"]:
        print(t["words_stale"].format(n=len(state["stale"])))
        for x in state["stale"][:40]:
            print("    %s: %s" % (x["file"], x["text"]))
    if state["clash"]:
        print(t["words_clash"].format(n=len(state["clash"])))
        for x in state["clash"]:
            print("    %s / %s → %s" % (x["name"], x["same_as"], x["translation"]))


def cmd_web(root, parts, t, args):
    """Writes the map page. With --open it is shown through a small service on this machine, so that what a
    reader writes on the page (a note on a function) goes straight into the project's files; the page as a
    plain file is written too, and is what opens when the service cannot start."""
    page, _ = web_page(root, parts, t, args)
    out = args.out or state_path(root)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(os.path.abspath(out))
    if not args.open:
        return
    url = None if (args.out or args.fragment or args.no_serve) else ensure_server(root, args)
    if url:
        print(url)
    webbrowser.open(url or "file://" + os.path.abspath(out))


def web_page(root, parts, t, args, save=None):
    """The map page as text, and the book of the functions on its call chains. `save` is set when the page
    is being served: it then holds what the page needs to hand a note back."""
    lang = language(parts)
    files = zlist(git(root, "ls-files", "-z"))
    n, _ = tally(files, parts)
    commits = history(root, parts)
    cutoff = (datetime.date.today() - datetime.timedelta(days=RECENT_DAYS)).isoformat()
    touching = {p.name: [c for c in commits if p.name in c["groups"]] for p in parts}
    links, langs = ({}, []) if args.no_links else code_links(root, files, parts)

    # What is uncommitted, in every checkout of the repository, split by window.
    rows, windows = in_flight(root, parts, look=not args.no_windows, everywhere=True)
    window_commits(windows, commits)
    by_name = {p.name: p for p in parts}
    waiting = collections.Counter((r["part"], r["sub"]) for r in rows)

    age = aging(root, args.list_path, parts, commits)
    wiring = Wiring(parts, args.routes, args.top)
    if langs:
        wiring.loose(lifted(links, "top"))

    def ports(u):
        """What goes in and out of a unit, for the page: the neighbour's name and where a click on it leads."""
        return [{"name": x["other"] if isinstance(x["other"], str) else x["other"].name,
                 "to": "" if isinstance(x["other"], str) else wiring.ids[x["other"]], "dir": x["dir"],
                 "labels": x["labels"], "code": x["code"], "must": x["must"], "met": x["met"], "where": x["where"]}
                for x in wiring.ports(u)]

    runs = load_runs(root, args.runs, args.routes, parts, args.top)[0]
    listed = os.path.relpath(args.list_path, root).replace(os.sep, "/")
    chains, book = load_chains(root, files, parts, args.routes, args.top, wiring, runs, args.calls_path, listed,
                               source=not args.no_source)

    def card(u):
        """What the page shows for a part or a sub-part."""
        return {"explain": u.explain, "ports": ports(u), "drawn": age[u][0] if u in age else "", "since": age[u][1] if u in age else 0, "name": u.name, "icon": u.icon, "flow": u.flow, "what": u.what, "sensitive": u.sensitive,
                "rules": u.rules, "paths": [x[0] for x in u.patterns], "external": u.external,
                "files": n[u][1] if u.outside else n[u][0], "outside": 0 if u.outside else n[u][1]}

    out_parts = []
    for p in parts:
        mine = touching[p.name]
        together = []
        if len(mine) >= 3:
            for q in parts:
                if q.name == p.name:
                    continue
                both = sum(1 for c in mine if q.name in c["groups"])
                usual = len(touching[q.name]) / max(1, len(commits))  # how often q changes anyway
                if both * 4 >= len(mine) and both / len(mine) >= 1.5 * usual:
                    together.append({"name": q.name, "pct": round(100 * both / len(mine))})
            together.sort(key=lambda x: -x["pct"])
        subs = []
        for c in p.children:
            seen = [k for k in mine if c in k["subs"]]
            subs.append(dict(card(c), recent=sum(1 for k in seen if k["date"] >= cutoff),
                             pending=waiting[(p.name, c.name)]))
        out_parts.append(dict(card(p), group=p.group, subs=subs, inner=lifted(links, p) if p.children else [],
                              recent=sum(1 for c in mine if c["date"] >= cutoff),
                              last=mine[0]["date"] if mine else "", commits=len(mine), together=together[:4]))
    out_commits = [{"hash": c["hash"], "date": c["date"], "subject": c["subject"],
                    "parts": [{"name": name or "?", "n": len(fs), "files": fs[:6]} for name, fs in
                              sorted(c["groups"].items(), key=lambda kv: -len(kv[1]))]} for c in commits[:SHOWN]]

    def short(groups):
        return [{"name": g["name"], "n": g["n"], "files": g["files"][:6]} for g in groups]
    # Tasks in progress, from the journal's dossiers: the lines the agent wrote for people, and where the
    # work landed, which is measured. A window that is writing in a task's dossier is that task's window.
    tasks, tasks_old = tasks_shown(root, args.tasks, parts, commits, args.list_path)
    out_tasks, scopes = [], {}
    for task in tasks:
        on = [w for w in windows if w["dossier"] == task["id"]]
        mine = {(r["tree"]["path"], r["file"]): r for w in on for r in w["rows"]
                if not (task["rel"] and r["file"].startswith(task["rel"] + "/"))}
        if task["plain"]:
            for w in on:
                w["task"] = task["name"]  # the window goes by the name the reader knows the task by
        if task["made"]:
            scopes[task["id"]] = {"name": task["name"], "files": sorted(task_scope(root, task, windows))}
        out_tasks.append({"id": task["id"], "name": task["name"], "plain": task["plain"], "now": task["now"],
                          "tried": task["tried"],
                          "needs": task["needs"], "next": task["next"], "updated": task["updated"],
                          "finished": task["done"], "made": task["made"], "try": task["try"], "left": task["left"],
                          "marks": task["marks"], "old": task["old"], "after": task["after"], "story": task["story"],
                          "times": task["times"], "again": task["again"],
                          # uncommitted work in the task's files; none is reported when its own record is being
                          # rewritten in the same work, since then the lines are moving along with the code
                          "touched": 0 if task["rel"] and any(
                              task_at(r["file"][len(task["rel"]) + 1:]) == task["id"] for r in rows
                              if r["file"].startswith(task["rel"] + "/"))
                          else sum(1 for r in rows if r["file"] in task["files"]),
                          "days": task["days"], "parts": task["rooms"],
                          "pending": short(grouped(list(mine.values()), parts)), "wins": [w["key"] for w in on]})

    # A page written with --out is made to be handed to someone else. A window's name and the latest request
    # typed into it are the person's own words to their AI tool; they stay out of such a page unless asked for.
    hush = bool(getattr(args, "out", None)) and not getattr(args, "asks", False)
    pending = {
        # changed files that no part owns come last, under the name "": the page says they are not on the list
        "parts": [{"part": g["name"], "n": g["n"], "files": g["files"],
                   "sensitive": by_name[g["name"]].sensitive if g["name"] else ""}
                  for g in short(grouped(rows, parts))],
        "windows": [{"key": w["key"], "tool": w["tool"], "title": "" if hush else w["title"], "task": w["task"],
                     "last": w["last"],
                     "where": "、".join(w["where"]) if lang == "zh" else ", ".join(w["where"]),
                     "unknown": w["unknown"], "n": len(w["rows"]), "guessed": w["guessed"], "parts": short(grouped(w["rows"], parts)),
                     "state": w["state"], "said": "" if hush else w["said"],
                     "commits": [{"hash": c["hash"], "subject": c["subject"][:90], "parts": c["parts"]} for c in w["commits"][:6]],
                     "committed": len(w["commits"])}
                    for w in windows],
        "shared": [{"file": r["file"], "who": r["keys"]} for r in rows if len(r["who"]) > 1][:8],
    }

    records = tuple(x for x in (listed, args.calls_home,
                                (tasks[0]["rel"] + "/") if tasks and tasks[0]["rel"] else "") if x)
    lately = [changes(root, args.list_path, parts, args.routes, args.top, wiring, commits, tasks, days, records)
              for days in SPANS]
    pending["clashes"] = clashes(rows, windows, records)[:12]
    keep_list(root, args.list_path)
    data = {"project": os.path.basename(root), "lang": lang, "generated": datetime.date.today().isoformat(),
            "lately": lately,
            "files": len(files), "history": len(commits), "recentDays": RECENT_DAYS, "list": listed,
            "parts": out_parts, "commits": out_commits, "pending": pending,
            "links": lifted(links, "top"), "measured": langs, "routes": args.routes,
            # the latest recorded run of each route, in the routes' order; null where none was recorded
            "runs": runs,
            # the call chains, a view of their own; where they are kept; what the project is, in a few sentences
            "chains": chains, "callsFile": args.calls_home, "explain": args.top["explain"],
            # the functions on the chains: their own lines and the note the reader keeps on each
            "fns": {k: v for k, v in book["fns"].items() if not v.get("off")}, "notesFile": book["notes_file"],
            "frame": args.top["frame"],
            "wings": [{"name": w.name, "what": w.what, "icon": w.icon, "flow": w.flow, "ports": ports(w),
                       "explain": w.explain,
                       "parts": [parts.index(p) for p in w.parts]} for w in args.top["wings"]],
            "tasks": out_tasks, "tasksOld": tasks_old, "save": save}
    # the other language: the page carries the translations and the reader switches (see "Two languages")
    words = book["words"] = words_state(root, args, lang, data)
    book["tried"] = scopes
    data["i18n"] = {"lang": words["lang"], "map": words["words"], "missing": len(words["missing"]),
                    "total": words["total"], "file": words["files"][0], "skip": sorted(WORDS_SKIP)}
    here = os.path.dirname(os.path.abspath(__file__))
    page = open(os.path.join(here, "map_template.html"), encoding="utf-8").read()
    # Every "<" in the data is written as \u003c. A commit subject holding both "<!--" and "<script" would
    # otherwise put the browser in a state where the page's own </script> no longer ends the script.
    for mark, name in (("/*__MATH_CSS__*/", "temml.css"), ("/*__MATH_JS__*/", "temml.min.js")):
        lib = os.path.join(here, "vendor", name)   # sets the formulas in notes; without it they show as written
        note = "/*! Temml 0.14.0 | MIT License | Copyright (c) 2020 Ron Kok | https://github.com/ronkok/Temml */\n"
        page = page.replace(mark, note + slurp(lib) if os.path.isfile(lib) else "")   # the licence asks for its notice
    page = page.replace("__PROJECT__", data["project"]).replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"))
    if not args.fragment:
        page = ('<!doctype html>\n<html lang="%s">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n</head>\n<body style="margin:0">\n'
                % ("zh-CN" if lang == "zh" else "en")) + page + "\n</body>\n</html>\n"
    return page, book


# The page, served -----------------------------------------------------------------
# The map is a snapshot: one file, rebuilt whole. A reader's notes are the one thing written on the page
# that has to end up in the project. So `web --open` shows the page through a small service on this machine:
# it builds the page afresh each time it is loaded, and takes a note back and writes it into the notes file.
# So does the sentence on a function of a chain, when a reader rewrites it: it goes onto its line in the calls file.
# It listens on this machine only, writes those two files only, and stops by itself when no page has asked
# anything of it for a while.

SERVE_IDLE = 1800     # seconds without a request before the service stops; an open page asks every few minutes
NOTE_MAX = 400000     # bytes of one note handed back


def write_note(path, heads, key, text, zh=True):
    """Puts a reader's note on one function into the notes file: in place of the note that function has
    there (under `## key`, or under any of the headings in `heads`), or at the end when it has none. An
    empty note removes it. The rest of the file is left as it is. Returns the note as it now stands."""
    fenced, kept = False, []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").strip("\n").split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        # a `##` line would begin another function's note: inside a note it is set one level deeper
        kept.append("#" + line if not fenced and re.match(r"^##\s", line) else line.rstrip())
    text = "\n".join(kept).strip("\n")
    old = slurp(path) if os.path.isfile(path) else ""
    if not old and not text.strip():
        return ""
    lines = old.split("\n") if old else ["# 函数笔记" if zh else "# Function notes", ""]
    names, out, skip, placed, fenced = {key} | set(heads), [], False, False, False
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
        head = None if fenced else re.match(r"^##\s+(.+?)\s*$", line)
        if head:
            name = re.sub(r"\s*\(.*\)\s*$", "", head.group(1).strip().strip("`").strip())
            skip = name in names
            if skip:
                if not placed and text.strip():
                    out += ["## " + key, "", text, ""]
                placed = True
                continue
        if not skip:
            out.append(line)
    if not placed and text.strip():
        while out and not out[-1].strip():
            out.pop()
        out += ["", "## " + key, "", text, ""]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out).rstrip("\n") + "\n")
    os.replace(tmp, path)
    return text


def write_what(path, at, exp, fn, text):
    """Puts the sentence a reader wrote for one function of a chain into the calls file. `at` is the line
    the function is written on: the sentence after its bar is replaced. A function the script filled in has
    no line; `exp` is then the `展开` line it came from, and the sentence goes on a line of its own set in
    under that. No text takes the sentence away. Returns {"text": the sentence as it now stands, "from":
    a line, "shift": by how many lines everything below that line moved}, or None when the file no longer
    has that function on that line (it changed since the page was made)."""
    lines = slurp(path).split("\n")
    text = " ".join(str(text).replace("|", "｜").split())[:600]

    def named(k):   # the function line k names, or None
        line = lines[k].expandtabs(4)
        if not line.strip() or line.strip().startswith("```") or CALL_EXPAND_RE.match(line) or CALL_FORK_RE.match(line):
            return None
        return call_name(re.sub(r"^\s*[-*]\s+", "", line).split("|")[0])

    def dent(k):
        line = lines[k].expandtabs(4)
        return len(line) - len(line.lstrip())
    short, shift = fn.split(":")[-1], 0
    if isinstance(at, int) and 0 <= at < len(lines):
        if named(at) != fn:
            return None
        lines[at] = lines[at].split("|")[0].rstrip() + (" | " + text if text else "")
    elif isinstance(exp, int) and 0 <= exp < len(lines) and CALL_EXPAND_RE.match(lines[exp]):
        k, mine = exp + 1, None
        while k < len(lines) and lines[k].strip() and not lines[k].strip().startswith("```") and dent(k) > dent(exp):
            if named(k) in (fn, short):
                mine = k
            k += 1
        new = " " * (dent(exp) + 2) + short + " | " + text
        if mine is not None and text:
            lines[mine] = new
        elif mine is not None:
            del lines[mine]
            shift = -1
        elif text:
            lines.insert(exp + 1, new)
            shift = 1
    else:
        return None
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    os.replace(tmp, path)
    return {"text": text, "from": exp if shift else -1, "shift": shift}


def serve_file(root):
    return os.path.join(os.path.dirname(state_path(root)), "serve.json")


def serve_flags(args):
    return [f for f, on in (("--no-links", args.no_links), ("--no-windows", args.no_windows),
                            ("--no-source", args.no_source)) if on]


def serve_port(root):
    """A port that stays the same for one project, so the page keeps its address from one day to the next."""
    return 20000 + sum((i + 1) * b for i, b in enumerate(os.path.abspath(root).encode())) % 20000


def serve_asks(root, args):
    """What a running service has to answer to be the one for this project, as this script would start it."""
    return {"root": os.path.abspath(root), "stamp": os.path.getmtime(os.path.abspath(__file__)),
            "flags": serve_flags(args) + [args.file or "", args.tasks, args.runs, args.calls_file or ""]}


def ensure_server(root, args):
    """The address of the service for this project: the one already running, or one started now. None when
    it cannot be started (no leave to listen, say); the page is then opened as a plain file."""
    def answer(port, path="/ping"):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=2) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            return None

    def running():
        try:
            info = json.loads(slurp(serve_file(root)) or "{}")
        except ValueError:
            return None
        return info if isinstance(info.get("port"), int) else None
    want, info = serve_asks(root, args), running()
    if info:
        got = answer(info["port"])
        if got and all(got.get(k) == want[k] for k in want):
            return "http://127.0.0.1:%d/" % info["port"]
        if got and got.get("root") == want["root"]:   # an older one, or one started another way: it makes room
            answer(info["port"], "/quit?token=" + str(info.get("token", "")))
            for _ in range(15):   # until it has let go of the port, so the page keeps its address
                time.sleep(0.2)
                if answer(info["port"]) is None:
                    break
    cmd = [sys.executable, os.path.abspath(__file__)] + (["--file", args.file] if args.file else []) + \
        ["--tasks", args.tasks, "--runs", args.runs] + (["--calls-file", args.calls_file] if args.calls_file else []) + \
        ["serve"] + serve_flags(args)
    os.makedirs(os.path.dirname(serve_file(root)), exist_ok=True)
    detach = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}
    try:
        with open(os.path.join(os.path.dirname(serve_file(root)), "serve.log"), "ab") as log:
            subprocess.Popen(cmd, cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log, **detach)
    except OSError:
        return None
    for _ in range(30):
        time.sleep(0.2)
        info = running()
        got = answer(info["port"]) if info else None
        if got and got.get("root") == want["root"]:
            return "http://127.0.0.1:%d/" % info["port"]
    return None


def cmd_serve(root, parts, t, args):
    """The service behind `web --open`. Not meant to be run by hand."""
    token = secrets.token_urlsafe(18)
    state = {"last": time.time(), "heads": {}, "keys": set(), "notes": "", "zh": True, "calls": "", "tried": {},
             "list": ""}
    lock = threading.Lock()
    asks = serve_asks(root, args)

    def render():
        with lock:
            leaf.__defaults__[0].clear()        # what was worked out for the list as it was does not hold for the list as it is
            line_count.__defaults__[0].clear()
            now = argparse.Namespace(**vars(args))
            now_parts, now.list_path, now.routes, now.top = load_parts(root, args.file)
            if not now_parts:
                return "<!doctype html><meta charset=utf-8><p>" + TEXT["zh"]["no_parts"].format(files=" / ".join(PARTS_FILES))
            now.calls_path, now.calls_home = calls_path(root, now.list_path, args.calls_file)
            now.fragment, now.out = False, None
            page, book = web_page(root, now_parts, TEXT[language(now_parts)], now, save={"token": token})
            state.update(heads=book["heads"], keys=set(book["fns"]), notes=os.path.join(root, book["notes_file"]),
                         zh=language(now_parts) == "zh", calls=now.calls_path, tried=book["tried"],
                         list=now.list_path)
            return page

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, code, body, kind="application/json; charset=utf-8"):
            body = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def here(self):   # asked for by this machine's own name: another site cannot have the browser ask in its stead
            return (self.headers.get("Host") or "") in ("127.0.0.1:%d" % port, "localhost:%d" % port)

        def do_GET(self):
            state["last"] = time.time()
            path, _, query = self.path.partition("?")
            if not self.here():
                return self.reply(403, {"ok": False})
            if path == "/":
                try:
                    return self.reply(200, render().encode("utf-8"), "text/html; charset=utf-8")
                except SystemExit as e:   # git said no, the list is gone: say so on the page
                    return self.reply(500, ("<!doctype html><meta charset=utf-8><pre>%s</pre>" % e).encode("utf-8"),
                                      "text/html; charset=utf-8")
            if path == "/ping":
                return self.reply(200, dict(asks, ok=True))
            if path == "/quit" and hmac.compare_digest(query, "token=" + token):
                self.reply(200, {"ok": True})
                threading.Thread(target=server.shutdown, daemon=True).start()
                return
            self.reply(404, {"ok": False})

        def do_POST(self):
            state["last"] = time.time()
            try:
                size = int(self.headers.get("Content-Length") or 0)
                if not self.here() or self.path not in ("/note", "/what", "/tried") or not 0 < size <= NOTE_MAX:
                    return self.reply(403, {"ok": False})
                ask = json.loads(self.rfile.read(size).decode("utf-8"))
                key, text = ask.get("key"), ask.get("text")
                if not hmac.compare_digest(str(ask.get("token", "")), token) or not isinstance(text, str):
                    return self.reply(403, {"ok": False})
                if self.path == "/tried":   # the reader tried a thing a task made: one more line in the tried file
                    with lock:
                        scope = state["tried"].get(ask.get("id"))
                        kept = write_tried(root, state["list"], {"id": ask["id"], "name": scope["name"]},
                                           scope["files"], bool(ask.get("ok")), text, state["zh"]) \
                            if scope and state["list"] else None
                    return self.reply(200 if kept else 409, {"ok": bool(kept), "tried": kept})
                if self.path == "/what":   # the sentence on one function of a chain, into the calls file
                    fn = ask.get("fn")
                    with lock:
                        kept = write_what(state["calls"], ask.get("at"), ask.get("exp"), fn, text) \
                            if state["calls"] and isinstance(fn, str) and CALL_NAME_RE.match(fn) else None
                    return self.reply(200 if kept else 409, dict(kept or {}, ok=bool(kept)))
                if key not in state["keys"]:
                    return self.reply(403, {"ok": False})
                with lock:
                    kept = write_note(state["notes"], state["heads"].get(key, []), key, text, state["zh"])
                    state["heads"][key] = [key]
                self.reply(200, {"ok": True, "text": kept})
            except (ValueError, OSError) as e:
                self.reply(500, {"ok": False, "why": str(e)})

    server, port = None, args.port or serve_port(root)
    for port in range(port, port + 30):
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit("bearings: no free port to serve the page on")
    with open(serve_file(root), "w", encoding="utf-8") as fh:
        json.dump({"port": port, "token": token, "pid": os.getpid()}, fh)

    def watch():
        while time.time() - state["last"] < SERVE_IDLE:
            time.sleep(20)
        server.shutdown()
    threading.Thread(target=watch, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        try:
            if json.loads(slurp(serve_file(root)) or "{}").get("pid") == os.getpid():
                os.remove(serve_file(root))
        except (ValueError, OSError):
            pass


LIST_FORMAT = """\
the parts list (docs/parts.md, PARTS.md or .bearings/parts.md), every keyword it understands:
  # Wing            groups the parts under it        (with one `#` title on top, every level sits one deeper)
  ## Part           first plain line: what it is for
  ### Room          a room inside the part above; same fields as a part
  - `dir/` `a/*.py` paths it owns: a trailing / owns the folder, * stops at a slash, ** crosses them
  图标：name        or  Icon: name        mic speaker phone play book search plug user card database mail
                                          home grid spark layout lang cloud flask note lock box
  敏感：why         or  Sensitive: why    drawn hatched
  外来：what        or  Vendored: what    code written elsewhere: dashed, counted apart
  规矩：rule（source，date）  or  Rule: ...
  说明：sentences    or  Explain: ...      what it does and how, in a few plain sentences; one line a paragraph.
                                          Under a part, a room or a `# Wing` heading; before the first heading
                                          it is about the whole project
  ```flow           how the level it stands at works, drawn with the boxes of the level below:
                      before the first heading   the whole project    boxes: the wings (the parts, with no wings)
                      under a `# Wing` heading   that wing            boxes: its parts
                      inside a part              that part            boxes: its rooms (its steps, with no rooms)
                      inside a room              that room            boxes: its steps
  ```flow Title     outside every part: a route, how one thing travels through the project (boxes: parts)
    A -> B: label     an arrow, and what travels along it;  <->  points both ways
    A -> B: label `Name`   also what the code calls that (a type, a function, an endpoint); doctor checks it exists
    Name | note | icon | 外部     a box;  外部 / external marks a service outside the project; icon user, a person
    Name | note       with no arrow: a box that is not on the path at run time; the note says whom it serves
    a box named exactly like a wing, part or room is a door to it
  under a `# Wing` heading, before its first part: one plain line on what the wing is for, and 图标：/ Icon:

the call chains (calls.md beside the parts list: docs/calls.md, or CALLS.md, or .bearings/calls.md). They are kept
apart from the parts list and its diagrams, and the page shows them in a view of their own:
  ## Title                  one chain: something the code does, from where it enters to where it ends
  plain lines               what the chain is about: what sets it off, where it ends, how often it runs
  ```calls                  its functions, in the order they are called
    function | what it does       a function, named as the code names it; `Class.method` or
                                  `path/file.py:function` when several share the name
      more sentences              any further line under a function says more about it: when it is called,
                                  what it decides, what it leaves behind, what happens when it fails
      function | what it does     set in under another: called by it
      进 name: what it is | where it comes from     or  in name: ...     something that goes into the function
                                  above: a parameter, a variable or a field it reads
      出 name: what it is | where it goes           or  out name: ...    something that comes out: what it returns
                                  (`出 返回: ...`, `out return: ...`), a variable or a field it sets
      分支 what varies | note     or  branch ...     the chain forks here: which bus, which encoder, which mode
        情况 name | when it applies   or  case ...   one way through the fork; the functions it calls are set in
                                  under it. What every case shares is written once, above and below the fork
      展开 2        or  expand 2             under a function: the script fills in what that function calls, two
                                  levels down, as it reads it from the code. Nothing has to be written for those
        function | sentence          set in under 展开: a sentence for one of the functions filled in there
  where each function is, its signature, its parameters and their types, the comment the code carries on it and
  whether the function above calls it are read from the code (Python, JavaScript/TypeScript, Go, C/C++);
  `bearings.py calls --from NAME` prints what NAME calls, and with --draft prints it as the frame of a block to
  fill in. A ```calls block inside the parts list is still read.

a reader's notes on functions (calls-notes.md beside calls.md). The chain gives the frame; what a function does line
by line is for the reader to work out and keep. The page shows each function's source beside its note:
  ## path/file.py:function     or  ## function  /  ## Class.method  when the name is the only one
  anything                     the note, as Markdown, down to the next `##` heading
  opened with `web --open`, the page writes a note into this file as the reader types it; opened as a plain
  file it keeps the note in the browser, with a button to copy it out

a task's lines for people (the `## For People` section of its record, docs/tasks/<task>.md; in older
projects docs/tasks/<task>/handoff.md):
  名字：/ Name:  现在：/ Now:  等你：/ Needs you: (one line each)  下一步：/ Next:     where the task stands
  做成了：/ Done:  怎么试：/ Try:  还没做：/ Not yet:                     what its last finished step came to
  新增：/ Added:  改了：/ Changed:  去掉：/ Removed:   Part / Box: one sentence     (Part / Room / Box for a room)
    marks that box on the part's flow diagram; the names must be the ones on the list

the other language (parts.zh.md beside an English parts.md, parts.en.md beside a Chinese one; calls.zh.md or
calls.en.md beside the calls file). The page shows the list in the language it is written in, and in the other
where this file gives it; the reader switches at the top of the page. Paths, diagrams and names are read from the
list alone:
  # anything                   a heading for whoever keeps the file; not read (nor is <!-- a comment -->)
  the original text            one line, exactly as the list has it: a name, a first line, a paragraph of an
                               explanation (without `Explain:`), a box's name or note, the words on an arrow,
                               a route's or chain's title, a function's sentence, what goes in or comes out
  : the translation            the line under it, starting with a colon. Leave code names in backticks as they are
  a text with no entry is shown as written. `bearings.py words` lists the texts still without one and the
  entries whose original the list no longer has; `words --draft` prints the missing entries to fill in.
  Two names must not be given the same translation: the page tells boxes apart by name.

a recorded run (docs/runs/<name>.json): one real run of a route, written by scripts/bearings_run.py (Python),
scripts/bearings_run.h (C) or any program that writes this shape; the page shows the latest run of each route:
  {"route": "<the route's title>", "name": "what was run", "recorded": "2026-11-14T10:02:11",
   "commit": "<HEAD when it ran>", "dirty": false,
   "steps": [{"box": "<a box of that route>", "fn": "name_of_the_function", "file": "src/x.py", "line": 41,
              "ms": 0.4, "depth": 0, "in": {"name": value}, "out": {"name": value}, "note": "..."}]}
  steps are in the order they began; depth is 1 for a step that ran inside another, and so on;
  ms may be null (a time taken on a desktop says nothing about firmware on its target)

what the reader tried (tried.md beside the list): written by the page's buttons and by `bearings.py tried`,
not by hand; a new try is a new line, and the last line under a task is how it stands:
  ## <task id>（name）            the task's record, by its file name without .md
  - 2026-11-24 14:05 能用 @1a2b3c4        the day and time, 能用 / 不能用 (works / broken), the commit the code
  - 2026-11-25 09:10 不能用 @5d6e7f8+：…   stood at (+ : with uncommitted work in the task's files), a note
"""


def main():
    ap = argparse.ArgumentParser(prog="bearings", description=__doc__.split("\n\n")[0], epilog=LIST_FORMAT,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="parts list, relative to the repo root (default: docs/parts.md)")
    ap.add_argument("--tasks", default=TASKS_DIR, metavar="DIR",
                    help="folder of task dossiers kept by the implementation-journal skill (default: docs/tasks)")
    ap.add_argument("--calls-file", metavar="FILE",
                    help="the file of call chains, relative to the repo root (default: calls.md beside the parts list)")
    ap.add_argument("--runs", default=RUNS_DIR, metavar="DIR",
                    help="folder of recorded runs, one JSON file each (default: docs/runs)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("runs", help="the recorded runs: one real run of a route, step by step, with file, line and values")
    r.add_argument("--json", action="store_true")
    f = sub.add_parser("calls", help="the call chains (docs/calls.md) checked against the code; --from NAME: what NAME calls")
    f.add_argument("--from", dest="start", metavar="NAME", help="a function (`name`, `Class.method` or `path/file:name`): "
                   "print what it calls, and those in turn, measured from the code")
    f.add_argument("--depth", type=int, default=3, help="how many levels down --from follows (default 3)")
    f.add_argument("--draft", action="store_true",
                   help="with --from: print the measured calls as the frame of a ```calls block, to fill in")
    f.add_argument("--json", action="store_true")
    j = sub.add_parser("tasks", help="the tasks in progress and finished lately: what the agent wrote for people, and the parts touched")
    j.add_argument("--json", action="store_true")
    k = sub.add_parser("tried", help="what the project can do now and whether the reader tried it; "
                                     "`tried TASK works|broken [note]` notes a try")
    k.add_argument("task", nargs="?", help="the task, by the name people know it by")
    k.add_argument("verdict", nargs="?", help="works or broken (能用 / 不能用)")
    k.add_argument("note", nargs="*", help="what happened, in a few words")
    k.add_argument("--json", action="store_true")
    k.add_argument("--no-windows", action="store_true", help=argparse.SUPPRESS)
    v = sub.add_parser("windows", help="every Claude Code and Codex window at work here: how it stands, what it changed, where two collide")
    v.add_argument("--json", action="store_true")
    p = sub.add_parser("parts", help="list parts and unmapped files")
    p.add_argument("--json", action="store_true")
    p.add_argument("--all", action="store_true", help="list every unmapped file")
    c = sub.add_parser("check", help="report which parts changed")
    c.add_argument("--since", help="everything changed since this commit, instead of only what is uncommitted")
    c.add_argument("--commit", help="report what this one past commit changed")
    c.add_argument("--json", action="store_true")
    c.add_argument("--files", action="store_true", help="list every changed file")
    w = sub.add_parser("web", help="write the project map as one HTML page")
    w.add_argument("--out", help="where to write it (default: <git-dir>/bearings/map.html)")
    w.add_argument("--open", action="store_true", help="open it in the browser")
    w.add_argument("--fragment", action="store_true", help="omit the html/head/body wrapper")
    w.add_argument("--no-links", action="store_true", help="do not read the code to measure which part uses which")
    w.add_argument("--no-serve", action="store_true",
                   help="with --open: open the page as a plain file; notes written on it then stay in the browser")
    w.add_argument("--no-source", action="store_true",
                   help="leave the source of the functions on the call chains out of the page (for a page that will be shared)")
    w.add_argument("--asks", action="store_true",
                   help="with --out: keep each window's name and the latest request typed into it in the page; "
                        "a page written with --out leaves them out, since it is made to be handed on")
    k = sub.add_parser("links", help="which part uses which, measured from import statements")
    k.add_argument("--json", action="store_true")
    d = sub.add_parser("doctor", help="check the list against the code: stale paths, misspelt boxes, aged diagrams")
    d.add_argument("--json", action="store_true")
    wd = sub.add_parser("words", help="the page's other language: which texts of the list have a translation, which do not")
    wd.add_argument("--draft", action="store_true", help="print the entries still to translate, ready to fill in")
    wd.add_argument("--json", action="store_true")
    sv = sub.add_parser("serve", help=argparse.SUPPRESS)   # the service behind `web --open`
    sv.add_argument("--port", type=int, default=0)
    sv.add_argument("--no-links", action="store_true")
    sv.add_argument("--no-source", action="store_true")
    for cmd in (c, w, sv):
        cmd.add_argument("--no-windows", action="store_true",
                         help="do not read Claude Code and Codex session records to tell windows apart")
    args = ap.parse_args()

    root = repo_root()
    parts, args.list_path, args.routes, args.top = load_parts(root, args.file)
    if not parts:
        raise SystemExit(TEXT["zh"]["no_parts"].format(files=" / ".join(PARTS_FILES)) + "\n"
                         + TEXT["en"]["no_parts"].format(files=" / ".join(PARTS_FILES)))
    t = TEXT[language(parts)]
    args.calls_path, args.calls_home = calls_path(root, args.list_path, args.calls_file)
    {"parts": cmd_parts, "check": cmd_check, "web": cmd_web, "links": cmd_links, "doctor": cmd_doctor,
     "tasks": cmd_tasks, "windows": cmd_windows, "runs": cmd_runs, "calls": cmd_calls,
     "words": cmd_words, "serve": cmd_serve, "tried": cmd_tried}[args.cmd](root, parts, t, args)


if __name__ == "__main__":
    main()
