# implent

用 AI 写代码时，让 AI 接得上，让人看得懂。

仓库里有两个配合使用的插件，Claude Code 和 Codex 都能用：

| 插件 | 给谁用 | 做什么 |
|---|---|---|
| `bearings` | 人 | 把项目画成一张导览图：分成哪几块、每块怎么工作、最近的改动落在哪 |
| `implementation-journal` | AI | 跨会话的记忆：任务书、决定日志、交接、下次开场白，让下一个会话接着干 |

两个都只做记录和展示。它们不规定 AI 怎么写代码，不拦任何改动。

它们怎么配合：AI 干活时用 `implementation-journal` 记下决定和进度；收尾时顺手更新 `bearings` 的清单；你想知道项目现在什么样，就打开导览图。两个可以各自单独安装。

> `bearings` 现在是原型，只在一个真实项目上试过，名字也是临时的。`implementation-journal` 已经在十几个项目里用过，这里是精简后的版本。

# bearings：给人看的导览图

## 你会看到什么

说一句“看看项目”，浏览器里打开一页导览图：

- **一栋楼**：项目分成几个区，每个区里有若干房间，一个房间就是项目的一块。
- **每个房间的流程图**：点开一个房间，看这一块是怎么工作的，谁把什么传给谁。
- **亮灯**：还没提交的改动落在哪几个房间。
- **脚印**：最近每次提交踩到了哪几块。
- **规矩和“要小心”**：项目自己文档里写过的规矩，以及涉及钱、登录、数据、线上配置的房间。

页面由脚本根据一份清单和 git 历史生成，生成时没有任何一句是 AI 现写的。

## 安装

需要 Python 3 和 git，不需要其他依赖。

### Claude Code

在 Claude Code 里输入：

```text
/plugin marketplace add woertedetiankong/implent
/plugin install bearings@implent
/plugin install implementation-journal@implent
```

以后更新：

```text
/plugin marketplace update implent
```

### Codex

把技能文件夹复制过去（`bearings` 在 Codex 里还没有实际验证过）：

```sh
git clone https://github.com/woertedetiankong/implent.git
cp -R implent/bearings/skills/bearings ~/.codex/skills/
cp -R implent/implementation-journal/skills/implementation-journal ~/.codex/skills/
```

## 使用 bearings

在你的项目里对 AI 说：

- “给这个项目建一份部分清单”：AI 读一遍仓库，写出 `docs/parts.md`，再请你改名字。
- “看看项目”或“打开项目地图”：生成并打开导览图。
- “刚才动了哪几块”：列出未提交的改动落在哪些部分。

在 Claude Code 里也可以直接输入 `/bearings:map` 打开导览图。

不装插件也能直接运行脚本。克隆仓库后，在你的项目目录里：

```sh
B=/path/to/implent/bearings/skills/bearings/scripts/bearings.py
python3 $B web --open            # 生成并打开导览图
python3 $B parts                 # 列出各部分，检查有没有漏掉的文件
python3 $B check                 # 未提交的改动落在哪几块
python3 $B check --commit <提交>  # 某一次提交落在哪几块
```

导览图写在仓库的 `.git/bearings/map.html`，不会进入版本历史。

## 部分清单长什么样

所有内容都来自项目里的一个文件 `docs/parts.md`：

````markdown
# 课程和学习

## 语音助手

学员在看课页面上用语音和 AI 练习一集。

图标：mic
规矩：不存录音和逐字记录（实施说明，2026-11-10）

- `src/voice/` `tests/unit/voice/`

```flow
学员 | 对着麦克风说话 | user
耳朵 | 语音识别 | mic | 外部
大脑 | 文字模型 | spark | 外部
学员 -> 耳朵: 声音
耳朵 -> 大脑: 文字
```
````

- 一级标题是一个区，二级标题是一块。
- 反引号里是这一块拥有的路径。
- `flow` 代码块描述它怎么工作：`甲 -> 乙: 传什么` 是一个箭头，`名字 | 说明 | 图标 | 外部` 是一个方框。

完整的写法见 [`bearings/skills/bearings/SKILL.md`](bearings/skills/bearings/SKILL.md)。

# implementation-journal：给 AI 的记忆

做里程碑级别的工作时，AI 在项目的 `docs/tasks/<日期>-<名字>/` 下为每个任务维护四份文件：

- `task-brief.md`：这次要做什么，做到什么算完。
- `implementation-log.md`：只记真正的决定、走不通的路和实测数字，只追加不改写。
- `handoff.md`：停下之前重写，说明现在到哪了、下一步、不能碰的红线、怎么验证现状。
- `next-session.md`：这个任务的下次开场白，贴给新会话就能接着干。

收尾时它还会把已经过时的 README 和文档改对，并在项目有 `docs/parts.md` 时更新导览图的清单。

**同时开多个窗口。** 每个任务的记录都在自己的文件夹里，没有全仓库共用、会被互相覆盖的文件。开新会话时：只有一个任务在进行，就自动带上它的开场白；有几个在进行，就列出来，由你说这个窗口做哪一个。各窗口只写自己任务的记录，改共用文档（README、计划、`docs/parts.md`）时只改自己那几行。任务的交接标成 Complete 之后，它就不再出现在列表里。

在 Claude Code 里，插件带两个钩子：开新会话时告诉 AI 有哪些任务在进行；改完记录后自动校验格式。Codex 没有钩子，靠技能说明里的步骤完成同样的事。

校验脚本可以手动运行：

```sh
python3 /path/to/implent/implementation-journal/skills/implementation-journal/scripts/validate_journal.py docs/tasks
```

小改动不需要用它，它只用于跨会话、跨模块的工作。

和原来的版本相比，这里去掉了三样东西：给人看的里程碑报告页（改由 `bearings` 来做）、任务索引、wiki 模板。已有项目里的这些旧文件不受影响，只是不会再更新。

## 已知的不足

- 多窗口并行的支持是新加的，钩子和校验都测过，但还没有在真实的并行开发里用过。
- `bearings` 的导览图显示的是整个工作目录的未提交改动。几个窗口在同一个目录里干活时，分不出哪个窗口动了哪里；用 worktree 时每个 worktree 只看得到自己的改动。

- 流程图要靠 AI 在改动后顺手更新。它会不会一直这样做，还没有在长期使用中验证过。
- 脚印旁边显示的是提交说明原文，不会编程的人可能看不懂。
- `/bearings:map` 命令还没有在真实会话里运行过。
- 手机宽度和深色模式没有充分检查。
