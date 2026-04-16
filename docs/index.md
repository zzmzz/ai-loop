# AI Loop 文档索引

> AI 驱动的多角色产品迭代闭环框架

## 快速导航

| 文档 | 说明 | 适合谁 |
|------|------|--------|
| [系统架构](architecture.md) | 总体设计、组件关系、数据流 | 想理解全局的人 |
| [编排引擎](orchestration.md) | Orchestrator 完整流程、重试/升级/协作机制 | 想改编排逻辑的人 |
| [决策系统](brain.md) | Brain 6 个决策点、输入输出、JSON schema | 想调整决策逻辑的人 |
| [角色系统](roles.md) | RoleRunner + 三角色（Product/Developer/Reviewer）| 想改角色行为的人 |
| [记忆与上下文](memory-context.md) | 累积记忆、滑动窗口压缩、ContextCollector 依赖图 | 想理解跨轮次连续性的人 |
| [配置参考](config-reference.md) | config.yaml 全字段说明、三种项目类型配置示例 | 想用 AI Loop 的人 |
| [开发指南](development.md) | 开发环境、测试规范、模块改动注意事项、发版流程 | 想贡献代码的人 |

## 设计文档（历史）

| 文档 | 日期 | 说明 |
|------|------|------|
| [自托管设计](superpowers/specs/2026-04-14-self-hosting-design.md) | 2026-04-14 | AI Loop 自身 dogfooding 方案 |
| [自托管计划](superpowers/plans/2026-04-14-self-hosting.md) | 2026-04-14 | 自托管实施计划 |
| [人类决策等级设计](superpowers/specs/2026-04-15-human-decision-design.md) | 2026-04-15 | human_decision 分级机制设计 |
| [人类决策等级计划](superpowers/plans/2026-04-15-human-decision.md) | 2026-04-15 | human_decision 实施计划 |

## 源码结构速查

```
ai_loop/
├── cli.py              → CLI 入口（init / run）
├── orchestrator.py     → 编排引擎（见 orchestration.md）
├── brain.py            → 决策大脑（见 brain.md）
├── config.py           → 配置加载校验（见 config-reference.md）
├── context.py          → 阶段间上下文注入（见 memory-context.md）
├── detect.py           → 项目自动检测
├── logger.py           → 结构化事件日志（JSONL，见 orchestration.md）
├── memory.py           → 累积记忆管理（见 memory-context.md）
├── server.py           → Dev Server 生命周期
├── state.py            → 轮次/阶段/重试状态
├── roles/
│   ├── base.py         → RoleRunner 基类（见 roles.md）
│   ├── product.py      → 产品经理角色
│   ├── developer.py    → 开发者角色
│   └── reviewer.py     → 审查者角色
└── templates/          → 角色 CLAUDE.md 模板
```

## .ai-loop/ 运行时目录说明

`.ai-loop/` 是 `ai-loop init` 生成的运行时目录，**不属于源码**，用于存储迭代状态和产出物。AI agent 在开发 ai-loop 本身时通常不需要读取此目录。

```
.ai-loop/
├── config.yaml                  # 🔧 项目配置（load_config 的输入，改配置逻辑时可参考）
├── state.json                   # 📊 迭代状态（当前轮次、重试计数、历史摘要、上次运行的 ai-loop 包版本）
├── server.log                   # 🗑️ Dev Server 日志（调试 server.py 时才需要看）
├── code-digest.md               # 🗑️ 代码摘要缓存（Brain 每轮自动生成，不需要手动读）
├── product-knowledge/           # 📁 产品认知文档（Product 写入；`index.md` 会在探索阶段注入 prompt）
├── logs/                        # 📁 结构化事件日志（每轮一个 round-NNN.jsonl）
│
├── rounds/                      # 📁 每轮的角色产出物
│   ├── 001/
│   │   ├── requirement.md       #   Product 输出的需求文档
│   │   ├── design.md            #   Developer 输出的技术设计
│   │   ├── clarification.md     #   Product 回答的澄清（可选，仅 CLARIFY 流程产生）
│   │   ├── dev-log.md           #   Developer 输出的开发日志
│   │   ├── review.md            #   Reviewer 输出的审查报告
│   │   └── acceptance.md        #   Product 输出的验收结果
│   └── 002/
│       └── ...
│
└── workspaces/                  # 📁 角色工作空间（Claude Code 的 cwd）
    ├── orchestrator/
    │   └── CLAUDE.md            #   编排器上下文 + 累积记忆
    ├── product/
    │   ├── CLAUDE.md            #   产品经理上下文 + 累积记忆
    │   └── notes/               #   截图、证据等临时文件
    ├── developer/
    │   ├── CLAUDE.md            #   开发者上下文 + 累积记忆
    │   └── notes/
    └── reviewer/
        ├── CLAUDE.md            #   审查者上下文 + 累积记忆
        └── notes/
```

**何时需要关注此目录**：

| 场景 | 需要看的文件 |
|------|-------------|
| 改配置加载逻辑 (`config.py`) | `config.yaml` — 了解真实配置长什么样 |
| 改状态管理 (`state.py`) | `state.json` — 了解真实状态结构 |
| 改记忆管理 (`memory.py`) | `workspaces/*/CLAUDE.md` — 了解记忆追加/压缩后的实际效果 |
| 改上下文注入 (`context.py`) | `rounds/NNN/*.md` — 了解各阶段产出物的真实格式 |
| 改角色 prompt (`roles/*.py`) | `rounds/NNN/*.md` — 了解角色实际输出是否符合 prompt 要求 |
| 改产品认知 / Product 上下文 | `product-knowledge/*.md` — 索引与子文档格式见 [角色系统](roles.md) |
| 调试 Server (`server.py`) | `server.log` |
| 改事件日志 (`logger.py`) 或排查编排轨迹 | `logs/round-*.jsonl` |
| **其他情况** | **不需要读 .ai-loop/ 下的任何文件** |
