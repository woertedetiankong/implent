# verify-kit

精选自 [`cursor/plugins` 的 `pstack`](https://github.com/cursor/plugins/tree/main/pstack)（MIT 许可），去除了对 Cursor 私有规则和其它未打包 Skill 的耦合，适配 **Claude Code** 与 **Codex** 独立运行。

定位：**只保留“确定性验证、影响面实证、对抗式审查、错题固化、需求升维”这 11 个高杠杆手动 Skill**，平时零上下文负担，需要时按 `/` 手动调用。

## 包含的 Skill

### 第一梯队：确定性验证与硬门禁

| Skill | 用途 |
|---|---|
| `create-verification-skill` | 为当前项目生成本地可执行的行为验证 Skill 和功能地图（Feature Map），驱动真实应用并留存证据 |
| `maintain-verification-skill` | 定期核对项目验证 Skill 与功能地图是否和最新代码漂移，并做一次真实运行校验 |
| `create-formal-verification-skill` | 针对并发竞态、状态机、重试幂等、解析器、资金/权限核心等高风险模块，选用合适工具（TLA+/SMT/代码验证器/属性测试）生成本地形式化验证 Skill |
| `maintain-formal-verification-skill` | 在覆盖代码变更后同步形式化模型与校验脚本，区分“模型漂移”与“真实 Bug” |
| `statechart` | 配合 TLA+ / TLC 检查状态机模型，输出最短反例路径与 Mermaid 状态图 |
| `blast-radius` | 在改动合入前查出 grep 找不到的跨模块破坏面，并强制用真实代码运行证明安全前提 |
| `correct` | 汇总 AI 在仓库中反复犯的错误类别，按「架构 → 类型/Lint/CI → 测试 → 文档」优先级把规则焊死在工程结构里 |

### 第二梯队：深度审查、考古与需求升维

| Skill | 用途 |
|---|---|
| `interrogate` | 对抗式 Review：并行派出审稿视角尝试击穿当前改动或设计，只保留经运行命令实证的真 Bug |
| `why` | 从 Git commit、PR 讨论等历史记录回答“当初为何这样设计”，严格区分原文证据与推断 |
| `reframe` | 当需求难以命名时，提炼专业术语、对标真实项目与邻近领域方案并重写描述 |
| `sharpen` | 在开工前把需求变深而非变大，补齐专家会做的验证与前置实验并重写 Prompt |

## 安装

### Claude Code

```text
/plugin marketplace add woertedetiankong/implent
/plugin install verify-kit@implent
```

### Codex

```sh
git clone https://github.com/woertedetiankong/implent.git
cp -R implent/verify-kit/skills/* ~/.codex/skills/
```
