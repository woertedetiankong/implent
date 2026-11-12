# implent

用 AI 写代码时，帮人看懂自己的项目。

AI 写得比人读得快。代码是它写的，人就不再像自己动手时那样顺带弄懂项目。这个仓库里的技能 `bearings` 给人一张图来看：项目分成哪几块、每一块是怎么工作的、最近的改动落在了哪里。

它只做展示。它不规定 AI 怎么写代码，不拦任何改动，也不要求 AI 动手前先来问你。

> 现在是原型。只在一个真实项目上试过，名字 `bearings` 也是临时的。

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

Claude Code：

```sh
git clone https://github.com/woertedetiankong/implent.git
ln -s "$(pwd)/implent/bearings" ~/.claude/skills/bearings
```

Codex（还没有实际验证过）：

```sh
cp -R implent/bearings ~/.codex/skills/
```

## 使用

在你的项目里对 AI 说：

- “给这个项目建一份部分清单”：AI 读一遍仓库，写出 `docs/parts.md`，再请你改名字。
- “看看项目”或“打开项目地图”：生成并打开导览图。
- “刚才动了哪几块”：列出未提交的改动落在哪些部分。

也可以自己运行脚本：

```sh
python3 ~/.claude/skills/bearings/scripts/bearings.py web --open   # 生成并打开导览图
python3 ~/.claude/skills/bearings/scripts/bearings.py parts        # 列出各部分，检查有没有漏掉的文件
python3 ~/.claude/skills/bearings/scripts/bearings.py check        # 未提交的改动落在哪几块
python3 ~/.claude/skills/bearings/scripts/bearings.py check --commit <提交>   # 某一次提交落在哪几块
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

完整的写法见 [`bearings/SKILL.md`](bearings/SKILL.md)。

## 已知的不足

- 流程图要靠 AI 在改动后顺手更新。它会不会一直这样做，还没有在长期使用中验证过。
- 脚印旁边显示的是提交说明原文，不会编程的人可能看不懂。
- 手机宽度和深色模式没有充分检查。
